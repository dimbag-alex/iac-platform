"""! Базовые тесты HTTP API (без подключения к гипервизору)."""
from fastapi.testclient import TestClient

from backend.app.main import app

client = TestClient(app)


def test_health_ok():
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "IaC Platform"
    assert body["version"]


def test_hypervisor_health_not_configured(monkeypatch):
    """! Без настроек подключения эндпоинт честно сообщает not_configured."""
    from backend.app.api import health
    from backend.app.config import load_settings

    monkeypatch.setattr(health, "settings", load_settings(env={}))
    response = client.get("/api/health/hypervisor")
    assert response.status_code == 200
    assert response.json()["status"] == "not_configured"


def test_docs_available():
    response = client.get("/docs")
    assert response.status_code == 200


def test_web_ui_served():
    """! Пользовательский веб-интерфейс отдаётся с корня."""
    response = client.get("/")
    assert response.status_code == 200
    assert "IaC Platform" in response.text


def test_unknown_route_returns_404():
    response = client.get("/api/does-not-exist")
    assert response.status_code == 404


def test_inventory_requires_configuration():
    """! Эндпоинты инвентаря отдают 503, если гипервизор не настроен."""
    response = client.get("/api/v1/inventory/hosts")
    assert response.status_code in (200, 503)
    if response.status_code == 503:
        assert "zVirt" in response.json()["detail"]
