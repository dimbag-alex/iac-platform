from backend.app.config import settings


def test_settings_defaults():
    assert settings.app_name == "IaC Platform"
    assert settings.version == "0.1.0"


def test_debug_is_bool():
    assert isinstance(settings.debug, bool)
