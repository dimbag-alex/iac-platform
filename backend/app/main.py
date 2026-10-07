"""!
@file main.py
@brief Точка входа FastAPI-приложения.
"""
from fastapi import FastAPI

from backend.app.api import health
from backend.app.config import settings


def create_app() -> FastAPI:
    """!
    @brief Фабрика приложения: создаёт FastAPI и подключает роутеры.
    @return Готовый экземпляр FastAPI.
    """
    app = FastAPI(title=settings.app_name, version=settings.version)
    app.include_router(health.router, prefix="/api")
    return app


app = create_app()
