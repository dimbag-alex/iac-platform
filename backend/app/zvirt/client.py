"""!
@file client.py
@brief Низкоуровневый HTTP-клиент REST API zVirt Engine.

Реализует контракт API версии 4 (oVirt-совместимый): JSON-представления,
Bearer-аутентификация с однократным обновлением токена при 401, разбор
элемента `fault` в исключение ZvirtApiError.
"""
from typing import Any, Dict, Optional

import httpx

from .auth import OAuthTokenProvider
from .errors import (
    ZvirtApiError,
    ZvirtConnectionError,
    ZvirtTimeoutError,
)

#: Префикс путей REST API (версия API — 4, oVirt-совместимая).
API_PREFIX = "/ovirt-engine/api"

_JSON_HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json",
}


class ZvirtClient:
    """!
    @brief Синхронный клиент REST API zVirt с автоматической авторизацией.

    Потокобезопасен (httpx.Client + блокировки в OAuthTokenProvider),
    предназначен для разделяемого использования как синглтон приложения.
    """

    def __init__(
        self,
        engine_url: str,
        token_provider: OAuthTokenProvider,
        verify_tls: bool = True,
        timeout: float = 30.0,
        transport: Optional[httpx.BaseTransport] = None,
    ) -> None:
        """!
        @param engine_url Базовый URL Менеджера (например, https://zhost.lab.loc).
        @param token_provider Поставщик OAuth-токенов.
        @param verify_tls Проверять ли TLS-сертификат Engine.
        @param timeout Таймаут HTTP-запросов, секунды.
        @param transport Подмена транспорта (используется в тестах).
        """
        self._base = engine_url.rstrip("/") + API_PREFIX
        self._tokens = token_provider
        self._http = httpx.Client(
            verify=verify_tls,
            timeout=timeout,
            headers=_JSON_HEADERS,
            transport=transport,
        )

    def close(self) -> None:
        """! Освобождает соединения HTTP-клиента."""
        self._http.close()

    def get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """! GET-запрос (list/get сервисов zVirt)."""
        return self.request("GET", path, params=params)

    def post(self, path: str, body: Optional[Dict[str, Any]] = None) -> Any:
        """! POST-запрос (add и action-методы zVirt)."""
        return self.request("POST", path, body=body or {})

    def put(self, path: str, body: Optional[Dict[str, Any]] = None) -> Any:
        """! PUT-запрос (update-методы zVirt)."""
        return self.request("PUT", path, body=body or {})

    def delete(self, path: str) -> Any:
        """! DELETE-запрос (remove-методы zVirt)."""
        return self.request("DELETE", path)

    def request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        body: Optional[Dict[str, Any]] = None,
        _retry_on_401: bool = True,
    ) -> Any:
        """!
        @brief Универсальный запрос к API с авторизацией и разбором ошибок.
        @param method HTTP-метод.
        @param path Путь сервиса относительно /ovirt-engine/api (например, "/vms").
        @param params Query-параметры (search, max, follow и др.).
        @param body Тело запроса в JSON-представлении.
        @return Разобранный JSON ответа (dict/list) или {} для пустых ответов.
        """
        url = self._base + self._normalize_path(path)
        headers = {"Authorization": f"Bearer {self._tokens.get_token()}"}

        try:
            response = self._http.request(
                method, url, params=params, json=body, headers=headers
            )
        except httpx.TimeoutException as exc:
            raise ZvirtTimeoutError(f"{method} {path}: таймаут запроса") from exc
        except httpx.HTTPError as exc:
            raise ZvirtConnectionError(f"{method} {path}: {exc}") from exc

        if response.status_code == 401 and _retry_on_401:
            # Токен истёк: обновляем и повторяем запрос один раз.
            self._tokens.invalidate()
            return self.request(method, path, params=params, body=body, _retry_on_401=False)

        if response.status_code >= 400:
            raise self._make_error(method, path, response)

        if not response.content:
            return {}
        return response.json()

    @staticmethod
    def _normalize_path(path: str) -> str:
        """! Гарантирует ведущий слэш у пути сервиса."""
        return path if path.startswith("/") else "/" + path

    @staticmethod
    def _make_error(method: str, path: str, response: httpx.Response) -> ZvirtApiError:
        """! Разбирает тело ошибки zVirt (элемент fault) в ZvirtApiError."""
        reason = response.text.strip()[:300] or f"HTTP {response.status_code}"
        detail = ""
        try:
            payload = response.json()
        except ValueError:
            payload = None
        if isinstance(payload, dict):
            fault = payload.get("fault", payload)
            if isinstance(fault, dict):
                reason = str(fault.get("reason") or reason)
                detail = str(fault.get("detail") or "")
        return ZvirtApiError(
            status_code=response.status_code,
            reason=reason,
            detail=detail,
            method=method,
            path=path,
        )
