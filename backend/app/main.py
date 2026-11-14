"""!
@file main.py
@brief Точка входа FastAPI-приложения АИС УЖЦ ВВИ (IaC Platform).
"""
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .api import health, inventory, stands, vms
from .config import settings

#: Каталог статики пользовательского веб-интерфейса (ТЗ 4.2.1).
STATIC_DIR = Path(__file__).resolve().parent / "static"


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
    # Веб-интерфейс монтируется последним: /api/* имеет приоритет.
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="web-ui")
    return app


app = create_app()
