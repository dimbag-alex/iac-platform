"""!
@file errors.py
@brief Иерархия исключений подсистемы интеграции с гипервизором zVirt.

Все ошибки взаимодействия с zVirt приводятся к типам этого модуля,
чтобы верхние слои (API, оркестрация) не зависели от httpx и формата
ответов zVirt Engine.
"""
from typing import Optional


class ZvirtError(Exception):
    """! Базовое исключение подсистемы интеграции с zVirt."""


class ZvirtConfigError(ZvirtError):
    """! Подключение к zVirt не настроено (нет URL/учётных данных)."""


class ZvirtAuthError(ZvirtError):
    """! Ошибка получения OAuth-токена у службы единого входа zVirt."""


class ZvirtConnectionError(ZvirtError):
    """! Сетевая ошибка при обращении к zVirt Engine."""


class ZvirtTimeoutError(ZvirtError):
    """! Превышено время ожидания (HTTP или опрос состояния объекта)."""


class ZvirtApiError(ZvirtError):
    """!
    @brief Ошибка REST API zVirt (ответ со статусом >= 400).

    Соответствует элементу `fault` документации zVirt: reason — краткая
    причина, detail — детализация (например, «Vm [name] required for add»).
    """

    def __init__(
        self,
        status_code: int,
        reason: str,
        detail: str = "",
        method: str = "",
        path: str = "",
    ) -> None:
        self.status_code = status_code
        self.reason = reason
        self.detail = detail
        self.method = method
        self.path = path
        super().__init__(self._format())

    def _format(self) -> str:
        parts = [f"HTTP {self.status_code}"]
        if self.method and self.path:
            parts.append(f"{self.method} {self.path}")
        parts.append(self.reason)
        if self.detail:
            parts.append(f"({self.detail})")
        return ": ".join(parts[:3]) + (" " + parts[3] if len(parts) > 3 else "")


class ZvirtNotFoundError(ZvirtApiError):
    """! Объект не найден в zVirt (HTTP 404)."""

    def __init__(self, what: str, method: str = "", path: str = "") -> None:
        self.what = what
        super().__init__(404, f"Not found: {what}", method=method, path=path)


#: Маппинг типов ошибок на HTTP-статусы (порядок важен: частные типы — раньше).
_STATUS_MAP = (
    (ZvirtConfigError, 503),
    (ZvirtAuthError, 502),
    (ZvirtTimeoutError, 504),
    (ZvirtConnectionError, 502),
    (ZvirtNotFoundError, 404),
)


def http_status_for(error: ZvirtError) -> int:
    """!
    @brief Маппинг внутренних ошибок интеграции на HTTP-статусы нашего API.
    @param error Исключение подсистемы интеграции.
    @return HTTP-статус для ответа FastAPI.
    """
    for error_type, status in _STATUS_MAP:
        if isinstance(error, error_type):
            return status
    if isinstance(error, ZvirtApiError):
        code: int = error.status_code
        return code if 400 <= code < 600 else 502
    return 500


def error_detail(error: Optional[ZvirtError]) -> str:
    """! Безопасное текстовое представление ошибки для ответа API."""
    if error is None:
        return ""
    if isinstance(error, ZvirtApiError) and error.detail:
        return f"{error.reason}: {error.detail}"
    return str(error)
