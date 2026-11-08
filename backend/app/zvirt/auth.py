"""!
@file auth.py
@brief OAuth 2.0 аутентификация в zVirt Engine (RFC 6749, password grant).

zVirt поддерживает только предоставление учётных данных владельца ресурса
(RFC 6749 §4.3) с обязательным scope `ovirt-app-api`. Refresh-токены не
поддерживаются: при ответе 401 токен запрашивается заново тем же способом.
"""
import threading
import time
from typing import Optional

import httpx

from .errors import ZvirtAuthError, ZvirtConnectionError

#: Endpoint службы единого входа Менеджера управления.
TOKEN_PATH = "/ovirt-engine/sso/oauth/token"

#: Обязательный scope для доступа к API (несмотря на необязательность в RFC).
API_SCOPE = "ovirt-app-api"

#: Запас по времени жизни токена, если сервер сообщает expires_in.
_EXPIRY_MARGIN_SECONDS = 60.0


class OAuthTokenProvider:
    """!
    @brief Потокобезопасный поставщик Bearer-токенов zVirt.

    Кеширует токен и обновляет его по требованию (`invalidate`) — клиент
    инвалидирует токен при получении HTTP 401 от API.
    """

    def __init__(
        self,
        engine_url: str,
        username: str,
        password: str,
        verify_tls: bool = True,
        timeout: float = 10.0,
        transport: Optional[httpx.BaseTransport] = None,
    ) -> None:
        """!
        @param engine_url Базовый URL Менеджера (например, https://zhost.lab.loc).
        @param username Учётная запись вида `user@realm` (например, admin@zvirt@internalsso).
        @param password Пароль учётной записи.
        @param verify_tls Проверять ли TLS-сертификат Engine.
        @param timeout Таймаут запроса токена, секунды.
        @param transport Подмена транспорта (используется в тестах).
        """
        self._token_url = engine_url.rstrip("/") + TOKEN_PATH
        self._username = username
        self._password = password
        self._timeout = timeout
        self._http = httpx.Client(verify=verify_tls, timeout=timeout, transport=transport)
        self._token: Optional[str] = None
        self._expires_at: float = 0.0
        self._lock = threading.Lock()

    def get_token(self) -> str:
        """!
        @brief Возвращает валидный access_token, при необходимости запрашивая новый.
        @return Строка токена для заголовка Authorization: Bearer.
        """
        with self._lock:
            if self._token and time.monotonic() < self._expires_at:
                return self._token
            return self._request_token()

    def invalidate(self) -> None:
        """! Сбрасывает кешированный токен (вызывается при HTTP 401 от API)."""
        with self._lock:
            self._token = None
            self._expires_at = 0.0

    def _request_token(self) -> str:
        """! Запрашивает новый токен у службы единого входа."""
        try:
            response = self._http.post(
                self._token_url,
                data={
                    "grant_type": "password",
                    "scope": API_SCOPE,
                    "username": self._username,
                    "password": self._password,
                },
                headers={"Accept": "application/json"},
            )
        except httpx.HTTPError as exc:
            raise ZvirtConnectionError(
                f"Служба единого входа zVirt недоступна: {exc}"
            ) from exc

        if response.status_code != 200:
            raise ZvirtAuthError(
                f"Получение токена отклонено (HTTP {response.status_code}): "
                f"проверьте логин/пароль и realm"
            )

        payload = response.json()
        token = payload.get("access_token")
        if not token:
            raise ZvirtAuthError("В ответе службы единого входа нет access_token")

        expires_in = payload.get("expires_in")
        if expires_in:
            lifetime = max(float(expires_in) - _EXPIRY_MARGIN_SECONDS, 60.0)
        else:
            # zVirt/Keycloak может не сообщать срок жизни: токен живёт до 401.
            lifetime = float("inf")

        self._token = str(token)
        self._expires_at = time.monotonic() + lifetime
        return self._token
