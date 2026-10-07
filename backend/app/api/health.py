"""!
@file health.py
@brief Служебные эндпоинты проверки состояния сервиса.
"""
from fastapi import APIRouter

from backend.app.config import settings

router = APIRouter(tags=["service"])


@router.get("/health")
def health() -> dict:
    """!
    @brief Проверка работоспособности сервиса.
    @return Словарь со статусом, названием и версией.
    """
    return {
        "status": "ok",
        "service": settings.app_name,
        "version": settings.version,
    }
