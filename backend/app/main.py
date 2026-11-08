"""!
@file main.py
@brief Точка входа FastAPI-приложения АИС УЖЦ ВВИ (IaC Platform).
"""
from fastapi import FastAPI

from .api import health, inventory, stands, vms
from .config import settings


def create_app() -> FastAPI:
    """!
    @brief Фабрика приложения: создаёт FastAPI и подключает роутеры.
    @return Готовый экземпляр FastAPI.
    """
    app = FastAPI(
        title=settings.app_name,
        version=settings.version,
        description=(
            "АИС управления жизненным циклом виртуализированной "
            "вычислительной инфраструктуры (подход IaC, гипервизор zVirt)"
        ),
    )
    app.include_router(health.router, prefix="/api")
    app.include_router(inventory.router, prefix="/api/v1/inventory")
    app.include_router(vms.router, prefix="/api/v1")
    app.include_router(stands.router, prefix="/api/v1")
    return app


app = create_app()
