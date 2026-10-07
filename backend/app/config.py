"""!
@file config.py
@brief Конфигурация приложения IaC Platform.
"""
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    """!
    @brief Настройки приложения, читаются из переменных окружения.
    """
    app_name: str = "IaC Platform"
    version: str = "0.1.0"
    debug: bool = os.getenv("IAC_DEBUG", "false").lower() == "true"


settings = Settings()
