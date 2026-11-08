"""!
@file deps.py
@brief Зависимости FastAPI: доступ к подсистеме интеграции с гипервизором.
"""
from functools import lru_cache
from typing import Optional

from fastapi import HTTPException

from ..config import settings
from ..zvirt import (
    ZvirtError,
    ZvirtService,
    build_service,
    error_detail,
    http_status_for,
)


@lru_cache(maxsize=1)
def _service_cache() -> ZvirtService:
    """! Синглтон сервиса интеграции на время жизни процесса."""
    return build_service(
        engine_url=settings.zvirt.url,
        username=settings.zvirt.username,
        password=settings.zvirt.password,
        verify_tls=settings.zvirt.verify_tls,
        timeout=settings.zvirt.timeout,
    )


def get_service() -> Optional[ZvirtService]:
    """! Сервис интеграции или None, если подключение не настроено."""
    if not settings.zvirt.configured:
        return None
    return _service_cache()


def require_service() -> ZvirtService:
    """! Сервис интеграции или HTTP 503 для эндпоинтов, требующих гипервизор."""
    service = get_service()
    if service is None:
        raise HTTPException(
            status_code=503,
            detail="Подключение к zVirt не настроено "
            "(задайте ZVIRT_URL, ZVIRT_USERNAME, ZVIRT_PASSWORD)",
        )
    return service


def raise_http(error: ZvirtError) -> None:
    """! Преобразует ошибку интеграции в HTTPException с подходящим статусом."""
    raise HTTPException(status_code=http_status_for(error), detail=error_detail(error))
