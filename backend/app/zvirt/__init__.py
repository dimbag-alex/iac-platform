"""!
@file __init__.py
@brief Подсистема интеграции с гипервизором zVirt (п. 4.2.4 ТЗ).

Публичный интерфейс подсистемы: фабрика build_service() и типы ошибок.
"""
from .auth import OAuthTokenProvider
from .client import ZvirtClient
from .errors import (
    ZvirtApiError,
    ZvirtAuthError,
    ZvirtConfigError,
    ZvirtConnectionError,
    ZvirtError,
    ZvirtNotFoundError,
    ZvirtTimeoutError,
    error_detail,
    http_status_for,
)
from .service import ZvirtService

__all__ = [
    "OAuthTokenProvider",
    "ZvirtClient",
    "ZvirtService",
    "ZvirtError",
    "ZvirtApiError",
    "ZvirtAuthError",
    "ZvirtConfigError",
    "ZvirtConnectionError",
    "ZvirtNotFoundError",
    "ZvirtTimeoutError",
    "build_service",
    "error_detail",
    "http_status_for",
]


def build_service(
    engine_url: str,
    username: str,
    password: str,
    verify_tls: bool = True,
    timeout: float = 30.0,
) -> ZvirtService:
    """!
    @brief Собирает сервис интеграции из параметров подключения.
    @param engine_url URL Менеджера управления (например, https://zhost.lab.loc).
    @param username Учётная запись вида user@realm.
    @param password Пароль учётной записи.
    @param verify_tls Проверять ли TLS-сертификат Engine.
    @param timeout Таймаут HTTP-запросов, секунды.
    """
    tokens = OAuthTokenProvider(
        engine_url=engine_url,
        username=username,
        password=password,
        verify_tls=verify_tls,
    )
    client = ZvirtClient(
        engine_url=engine_url,
        token_provider=tokens,
        verify_tls=verify_tls,
        timeout=timeout,
    )
    return ZvirtService(client)
