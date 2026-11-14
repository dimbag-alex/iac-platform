"""! Интеграционные тесты сервисного слоя на моковом транспорте zVirt API.

Эмулируется вся поверхность REST API, необходимая сервису: инвентарь,
создание ВМ со всеми устройствами, apply/destroy декларативного стенда.
"""
import httpx
import pytest

from backend.app.schemas import VmCreateRequest, load_stand_spec
from backend.app.zvirt.client import ZvirtClient
from backend.app.zvirt.errors import ZvirtNotFoundError
from backend.app.zvirt.service import ZvirtService

ENGINE = "https://engine.test"
PREFIX = "/ovirt-engine/api"
CDROM = "00000000-0000-0000-0000-000000000000"


class StubTokens:
    """! Поставщик токенов без сети."""

    def get_token(self) -> str:
        return "t"

    def invalidate(self) -> None:
        pass


def router(payloads):
    """! Маршрутизатор ответов: (method, path) → (status, json)."""

    def handler(request: httpx.Request) -> httpx.Response:
        key = (request.method, request.url.path[len(PREFIX):] or "/")
        value = payloads.get(key)
        if value is None:
            status, body = 404, {"fault": {"reason": f"no route {key}"}}
        elif isinstance(value, tuple):
            status, body = value
        else:
            status, body = 200, value
        return httpx.Response(status, json=body)

    return handler


def make_service(payloads) -> ZvirtService:
    client = ZvirtClient(
        engine_url=ENGINE,
        token_provider=StubTokens(),
        transport=httpx.MockTransport(router(payloads)),
    )
    return ZvirtService(client)


# --- Инвентарь и мониторинг ----------------------------------------------

INVENTORY = {
    ("GET", "/"): {"product_info": {"name": "zVirt Engine",
                                    "version": {"full_version": "4.5.6"}},
                   "summary": {"vms": {"total": "3"}}},
    ("GET", "/hosts"): {"host": [{"id": "h1", "memory": "32918028288"}]},
    ("GET", "/clusters"): {"cluster": [{"id": "c1", "name": "Default"}]},
    ("GET", "/datacenters"): {"data_center": [{"id": "dc1", "status": "up"}]},
    ("GET", "/storagedomains"): {"storage_domain": [
        {"id": "sd1", "available": "64424509440", "used": "10737418240"}]},
    ("GET", "/networks"): {"network": [{"id": "n1", "name": "ovirtmgmt"}]},
    ("GET", "/templates"): {"template": [{"id": "t1", "memory": "4294967296"}]},
    ("GET", "/disks"): {"disk": [
        {"id": "iso1", "name": "redos8.0.3", "content_type": "iso",
         "provisioned_size": "1073741824"},
        {"id": "d0", "name": "data", "content_type": "data"}]},
    ("GET", "/events"): {"event": [{"id": "e1", "severity": "normal"}]},
    ("GET", "/vms"): {"vm": [{"id": "vm1", "name": "test-vm", "status": "down",
                              "memory": "1073741824"}]},
    ("GET", "/vms/vm1"): {"id": "vm1", "status": "down"},
}


def test_engine_info():
    info = make_service(INVENTORY).engine_info()
    assert info["product"] == "zVirt Engine"
    assert info["version"] == "4.5.6"


def test_inventory_listings():
    service = make_service(INVENTORY)
    assert service.list_hosts()[0]["memory_gib"] == 30.7
    assert service.list_clusters()[0]["name"] == "Default"
    assert service.list_datacenters()[0]["status"] == "up"
    assert service.list_storage_domains()[0]["available_gib"] == 60
    assert service.list_networks()[0]["name"] == "ovirtmgmt"
    assert service.list_templates()[0]["memory_mib"] == 4096
    # ISO-образы фильтруются по content_type=iso
    isos = service.list_iso_images()
    assert len(isos) == 1 and isos[0]["name"] == "redos8.0.3"
    assert service.list_events()[0]["severity"] == "normal"


def test_list_vms_and_find_by_name():
    service = make_service(INVENTORY)
    vms = service.list_vms()
    assert vms[0]["memory_mib"] == 1024
    assert service.find_vm_by_name("test-vm")["id"] == "vm1"
    assert service.find_vm_by_name("absent") is None


# --- Создание ВМ со всеми устройствами -------------------------------------

CREATE_FLOWS = {
    **INVENTORY,
    ("POST", "/vms"): {"id": "vm-new"},
    ("GET", "/vms/vm-new"): {"id": "vm-new", "status": "down"},
    ("POST", "/vms/vm-new/diskattachments"): {"id": "att1", "disk": {"id": "d-new"}},
    ("GET", "/disks/d-new"): {"id": "d-new", "status": "ok"},
    ("GET", "/networks/n1/vnicprofiles"): {"vnic_profile": [{"id": "vp1"}]},
    ("POST", "/vms/vm-new/nics"): {"id": "nic1"},
    ("PUT", f"/vms/vm-new/cdroms/{CDROM}"): {},
    ("POST", "/vms/vm-new/start"): {},
}


def test_create_vm_from_blank_template_full_flow():
    service = make_service(CREATE_FLOWS)
    request = VmCreateRequest(
        name="lab1-vm9", memory_mib=1024, vcpu=1, disk_gib=6,
        storage_domain="zhost-Local", network="ovirtmgmt",
        iso="redos8.0.3", start=True,
    )
    dto = service.create_vm(request)
    assert dto["id"] == "vm-new"


def test_create_vm_from_os_template_skips_disk():
    service = make_service(CREATE_FLOWS)
    request = VmCreateRequest(
        name="lab1-vm8", template="redos8.0.3-base", network="ovirtmgmt",
        storage_domain="zhost-Local",
    )
    dto = service.create_vm(request)
    assert dto["id"] == "vm-new"


# --- Декларативные стенды ---------------------------------------------------

STAND_YAML = """
stand: lab1
cluster: Default
storage_domain: zhost-Local
network: ovirtmgmt
vms:
  - name: lab1-vm9
    memory_mib: 1024
    vcpu: 1
    disk_gib: 6
"""


def test_apply_stand_creates_missing_vm():
    service = make_service(CREATE_FLOWS)
    report = service.apply_stand(load_stand_spec(STAND_YAML))
    assert report["created"] == ["lab1-vm9"]
    assert not report["failed"]


def test_apply_stand_skips_existing_vm():
    # ВМ с таким именем уже существует → идемпотентный пропуск
    service = make_service({
        **INVENTORY,
        ("GET", "/vms"): {"vm": [{"id": "vm1", "name": "lab1-vm9"}]},
    })
    report = service.apply_stand(load_stand_spec(STAND_YAML))
    assert report["existing"] == ["lab1-vm9"]
    assert report["created"] == []


def test_destroy_stand_stops_and_deletes():
    deleted = []

    base = router({
        **INVENTORY,
        ("GET", "/vms"): {"vm": [{"id": "vm1", "name": "lab1-vm9"}]},
        ("GET", "/vms/vm1"): {"id": "vm1", "status": "down"},
    })

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "DELETE":
            deleted.append(request.url.path)
            return httpx.Response(200)
        return base(request)

    client = ZvirtClient(engine_url=ENGINE, token_provider=StubTokens(),
                         transport=httpx.MockTransport(handler))
    service = ZvirtService(client)
    report = service.destroy_stand(load_stand_spec(STAND_YAML))
    assert report["deleted"] == ["lab1-vm9"]
    assert deleted == [f"{PREFIX}/vms/vm1"]


def test_destroy_stand_reports_missing_vm():
    service = make_service(INVENTORY)
    report = service.destroy_stand(load_stand_spec(STAND_YAML))
    assert report["missing"] == ["lab1-vm9"]


# --- Поиск вспомогательных объектов -----------------------------------------

def test_attach_iso_unknown_image_raises():
    service = make_service(CREATE_FLOWS)
    with pytest.raises(ZvirtNotFoundError):
        service.attach_iso("vm-new", "no-such-iso")
