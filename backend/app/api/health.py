"""!
@file health.py
@brief Служебные эндпоинты: состояние сервиса и связи с гипервизором.
"""
from fastapi import APIRouter

from ..config import settings
from ..zvirt import ZvirtError
from .deps import get_service

router = APIRouter(tags=["service"])


@router.get("/health")
def health() -> dict:
    """! Работоспособность самой платформы (без обращения к гипервизору)."""
    return {
        "status": "ok",
        "service": settings.app_name,
        "version": settings.version,
    }


@router.get("/health/hypervisor")
def hypervisor_health() -> dict:
    """!
    @brief Связь с zVirt Engine: версия продукта и сводка ресурсов.

    Используется мониторингом платформы как проверка подсистемы
    интеграции с гипервизором (п. 4.1.5 ТЗ).
    """
    service = get_service()
    if service is None:
        return {"status": "not_configured"}
    try:
        info = service.engine_info()
    except ZvirtError as exc:
        return {"status": "unavailable", "error": str(exc)}
    return {"status": "ok", **info}
