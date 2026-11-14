"""! Сквозные тесты HTTP API поверх мокового транспорта zVirt.

Проверяется вся цепочка: маршрутизация FastAPI → валидация Pydantic →
сервис → клиент → (моковый) REST API гипервизора → маппинг ошибок в HTTP.
"""
import pytest
from fastapi.testclient import TestClient

from backend.app.api import deps
from backend.app.main import create_app

from test_service_inventory import CREATE_FLOWS, INVENTORY, make_service


PAYLOADS = {
    **CREATE_FLOWS,
    ("POST", "/vms/vm1/start"): {},
    ("DELETE", "/vms/vm1"): {},
}


@pytest.fixture()
def client():
    """! TestClient с подменённым сервисом интеграции (без сети)."""
    app = create_app()
    app.dependency_overrides[deps.require_service] = lambda: make_service(PAYLOADS)
    with TestClient(app) as test_client:
        yield test_client


# --- Виртуальные машины ----------------------------------------------------

def test_list_vms(client):
    response = client.get("/api/v1/vms")
    assert response.status_code == 200
    assert response.json()[0]["name"] == "test-vm"


def test_get_vm(client):
    response = client.get("/api/v1/vms/vm1")
    assert response.status_code == 200
    assert response.json()["id"] == "vm1"


def test_get_missing_vm_maps_to_404(client):
    """! Ошибка гипервизора 404 транслируется в HTTP 404, а не 500."""
    response = client.get("/api/v1/vms/absent")
    assert response.status_code == 404


def test_create_vm_returns_201(client):
    response = client.post("/api/v1/vms", json={
        "name": "api-vm1", "memory_mib": 1024, "vcpu": 1, "disk_gib": 6,
        "network": "ovirtmgmt", "storage_domain": "zhost-Local",
    })
    assert response.status_code == 201
    assert response.json()["id"] == "vm-new"


def test_create_vm_validation_error(client):
    """! Pydantic отклоняет некорректный запрос до обращения к гипервизору."""
    response = client.post("/api/v1/vms", json={"name": "x", "memory_mib": 1})
    assert response.status_code == 422


def test_vm_action_unsupported_maps_to_404(client):
    response = client.post("/api/v1/vms/vm1/actions/destroy")
    assert response.status_code == 404


def test_vm_action_start(client):
    response = client.post("/api/v1/vms/vm1/actions/start")
    assert response.status_code == 200
    assert response.json()["action"] == "start"


def test_delete_vm(client):
    response = client.delete("/api/v1/vms/vm1")
    assert response.status_code == 200
    assert response.json()["status"] == "deleted"


# --- Декларативные стенды ---------------------------------------------------

def test_stand_preview(client):
    response = client.post("/api/v1/stands/preview", json={
        "stand": "lab1", "network": "ovirtmgmt", "storage_domain": "zhost-Local",
        "vms": [{"name": "lab1-vm9", "memory_mib": 1024}],
    })
    assert response.status_code == 200
    plan = response.json()["plan"]
    assert plan[0]["action"] == "create"


def test_stand_apply_and_destroy(client):
    spec = {"stand": "lab1", "network": "ovirtmgmt", "storage_domain": "zhost-Local",
            "vms": [{"name": "lab1-vm9", "memory_mib": 1024, "disk_gib": 6}]}
    response = client.post("/api/v1/stands/apply", json=spec)
    assert response.status_code == 200
    assert response.json()["created"] == ["lab1-vm9"]
    response = client.post("/api/v1/stands/destroy", json=spec)
    assert response.status_code == 200
    assert response.json()["missing"] == ["lab1-vm9"]


def test_stand_invalid_spec_422(client):
    response = client.post("/api/v1/stands/preview", json={"vms": "не список"})
    assert response.status_code == 422


# --- Инвентарь и мониторинг --------------------------------------------------

@pytest.mark.parametrize("path,key", [
    ("/api/v1/inventory/hosts", "memory_gib"),
    ("/api/v1/inventory/clusters", "name"),
    ("/api/v1/inventory/datacenters", "status"),
    ("/api/v1/inventory/storage-domains", "available_gib"),
    ("/api/v1/inventory/networks", "name"),
    ("/api/v1/inventory/templates", "memory_mib"),
    ("/api/v1/inventory/iso-images", "name"),
    ("/api/v1/inventory/events", "severity"),
])
def test_inventory_endpoints(client, path, key):
    response = client.get(path)
    assert response.status_code == 200
    assert key in response.json()[0]


def test_inventory_events_limit_validation(client):
    response = client.get("/api/v1/inventory/events", params={"limit": 0})
    assert response.status_code == 422
