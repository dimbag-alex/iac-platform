"""!
@file client.py
@brief Низкоуровневый HTTP-клиент REST API zVirt Engine.

Реализует контракт API версии 4 (oVirt-совместимый): JSON-представления,
Bearer-аутентификация с однократным обновлением токена при 401, разбор
элемента `fault` в исключение ZvirtApiError.
"""
from typing import Any, Dict, Optional, Tuple

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
        response = self._send(method, url, path, params, body)

        if response.status_code == 401 and _retry_on_401:
            # Токен истёк: обновляем и повторяем запрос один раз.
            self._tokens.invalidate()
            return self.request(method, path, params=params, body=body, _retry_on_401=False)

        if response.status_code >= 400:
            raise self._make_error(method, path, response)

        if not response.content:
            return {}
        return response.json()

    def _send(
        self,
        method: str,
        url: str,
        path: str,
        params: Optional[Dict[str, Any]],
        body: Optional[Dict[str, Any]],
    ) -> httpx.Response:
        """! Выполняет HTTP-запрос, приводя сетевые ошибки к типам подсистемы."""
        headers = {"Authorization": f"Bearer {self._tokens.get_token()}"}
        try:
            return self._http.request(method, url, params=params, json=body, headers=headers)
        except httpx.TimeoutException as exc:
            raise ZvirtTimeoutError(f"{method} {path}: таймаут запроса") from exc
        except httpx.HTTPError as exc:
            raise ZvirtConnectionError(f"{method} {path}: {exc}") from exc

    @staticmethod
    def _normalize_path(path: str) -> str:
        """! Гарантирует ведущий слэш у пути сервиса."""
        return path if path.startswith("/") else "/" + path

    @staticmethod
    def _make_error(method: str, path: str, response: httpx.Response) -> ZvirtApiError:
        """! Разбирает тело ошибки zVirt (элемент fault) в ZvirtApiError."""
        reason, detail = ZvirtClient._extract_fault(response)
        return ZvirtApiError(
            status_code=response.status_code,
            reason=reason,
            detail=detail,
            method=method,
            path=path,
        )

    @staticmethod
    def _extract_fault(response: httpx.Response) -> Tuple[str, str]:
        """! Извлекает (reason, detail) из тела ответа с элементом fault."""
        fallback = response.text.strip()[:300] or f"HTTP {response.status_code}"
        fault = ZvirtClient._fault_dict(response)
        if fault is None:
            return fallback, ""
        return str(fault.get("reason") or fallback), str(fault.get("detail") or "")

    @staticmethod
    def _fault_dict(response: httpx.Response) -> Optional[Dict[str, Any]]:
        """! Возвращает элемент fault ответа как словарь или None."""
        try:
            payload = response.json()
        except ValueError:
            return None
        if not isinstance(payload, dict):
            return None
        fault = payload.get("fault", payload)
        return fault if isinstance(fault, dict) else None
