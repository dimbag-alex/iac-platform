"""! Тесты конфигурации приложения."""
from backend.app.config import load_settings


def test_settings_defaults():
    """! Значения по умолчанию без переменных окружения."""
    settings = load_settings(env={})
    assert settings.app_name == "IaC Platform"
    assert settings.version
    assert settings.debug is False
    assert settings.zvirt.configured is False
    assert settings.zvirt.verify_tls is True
    assert settings.zvirt.timeout == 30.0


def test_settings_from_env():
    """! Чтение параметров подключения из окружения."""
    settings = load_settings(
        env={
            "ZVIRT_URL": "https://zhost.lab.loc/",
            "ZVIRT_USERNAME": "admin@zvirt@internalsso",
            "ZVIRT_PASSWORD": "secret",
            "ZVIRT_VERIFY_TLS": "false",
            "ZVIRT_TIMEOUT": "15",
        }
    )
    assert settings.zvirt.configured is True
    # завершающий слэш должен удаляться
    assert settings.zvirt.url == "https://zhost.lab.loc"
    assert settings.zvirt.verify_tls is False
    assert settings.zvirt.timeout == 15.0


def test_env_bool_variants():
    """! Разбор булевых значений окружения."""
    assert load_settings(env={"IAC_DEBUG": "yes"}).debug is True
    assert load_settings(env={"IAC_DEBUG": "0"}).debug is False
