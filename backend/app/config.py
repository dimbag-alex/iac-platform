"""!
@file config.py
@brief Конфигурация приложения IaC Platform из переменных окружения.

Переменные (см. .env.example):
  ZVIRT_URL        — URL Менеджера управления, например https://zhost.lab.loc
  ZVIRT_USERNAME   — учётная запись user@realm (admin@zvirt@internalsso)
  ZVIRT_PASSWORD   — пароль учётной записи
  ZVIRT_VERIFY_TLS — проверка TLS-сертификата (true/false)
  ZVIRT_TIMEOUT    — таймаут HTTP-запросов к Engine, секунды
  IAC_DEBUG        — режим отладки приложения (true/false)
"""
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple


def _load_dotenv(path: Path) -> None:
    """!
    @brief Минимальный загрузчик .env (KEY=VALUE), без сторонних зависимостей.
    Не переопределяет уже установленные переменные окружения.
    """
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        entry = _parse_env_line(line)
        if entry is not None:
            key, value = entry
            os.environ.setdefault(key, value)


def _parse_env_line(line: str) -> Optional[Tuple[str, str]]:
    """! Разбирает строку .env в (ключ, значение) или None для пустых/комментариев."""
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or "=" not in stripped:
        return None
    key, _, value = stripped.partition("=")
    return key.strip(), value.strip().strip('"').strip("'")


_load_dotenv(Path(__file__).resolve().parents[2] / ".env")


def _env_bool(source: Dict[str, str], name: str, default: bool) -> bool:
    """! Булева переменная окружения с признанием true/false/1/0/yes/no."""
    raw = source.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _env_float(source: Dict[str, str], name: str, default: float) -> float:
    """! Числовая переменная окружения с откатом к умолчанию."""
    raw = source.get(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class ZvirtSettings:
    """! Параметры подключения к zVirt Engine."""

    url: str
    username: str
    password: str
    verify_tls: bool
    timeout: float

    @property
    def configured(self) -> bool:
        """! True, если заданы все обязательные параметры подключения."""
        return bool(self.url and self.username and self.password)


@dataclass(frozen=True)
class Settings:
    """! Настройки приложения, собранные из переменных окружения."""

    app_name: str
    version: str
    debug: bool
    zvirt: ZvirtSettings


def load_settings(env: Dict[str, str] = None) -> Settings:
    """!
    @brief Собирает настройки из переданного словаря или os.environ.
    Отдельная функция (а не код на импорте) — для тестируемости.
    """
    source = os.environ if env is None else env
    get = source.get
    zvirt = ZvirtSettings(
        url=(get("ZVIRT_URL") or "").rstrip("/"),
        username=get("ZVIRT_USERNAME") or "",
        password=get("ZVIRT_PASSWORD") or "",
        verify_tls=_env_bool(source, "ZVIRT_VERIFY_TLS", True),
        timeout=_env_float(source, "ZVIRT_TIMEOUT", 30.0),
    )
    return Settings(
        app_name="IaC Platform",
        version="0.3.0",
        debug=_env_bool(source, "IAC_DEBUG", False),
        zvirt=zvirt,
    )


settings = load_settings()
