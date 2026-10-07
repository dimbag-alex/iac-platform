from fastapi.testclient import TestClient

from backend.app.main import app

client = TestClient(app)


def test_health_has_version():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["version"] == "0.1.0"


def test_docs_available():
    response = client.get("/docs")
    assert response.status_code == 200


def test_unknown_route_returns_404():
    response = client.get("/api/does-not-exist")
    assert response.status_code == 404
