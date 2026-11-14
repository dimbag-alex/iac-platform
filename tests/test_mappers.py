"""! Тесты мапперов zVirt -> DTO платформы."""
from backend.app.zvirt import mappers


def test_to_int_handles_strings():
    """! zVirt отдаёт числа строками в JSON."""
    assert mappers.to_int("1073741824") == 1073741824
    assert mappers.to_int(None) == 0
    assert mappers.to_int("nonsense", default=7) == 7


def test_size_conversions():
    assert mappers.mib_to_bytes(1024) == 1024 * mappers.MIB
    assert mappers.gib_to_bytes(8) == 8 * mappers.GIB
    assert mappers.bytes_to_mib(str(2 * mappers.GIB)) == 2048
    assert mappers.bytes_to_gib(str(3 * mappers.GIB)) == 3


def test_unwrap_collection():
    payload = {"vm": [{"id": "1"}, {"id": "2"}]}
    assert [v["id"] for v in mappers.unwrap_collection(payload, "vms")] == ["1", "2"]
    assert mappers.unwrap_collection({}, "vms") == []
    assert mappers.unwrap_collection(None, "vms") == []


def test_vm_summary_normalization():
    raw = {
        "id": "123",
        "name": "lab1-vm1",
        "status": "down",
        "memory": "1073741824",
        "cpu": {"topology": {"sockets": "2", "cores": "2", "threads": "1"}},
        "cluster": {"id": "c1", "name": "Default"},
        "template": {"id": "t0", "name": "Blank"},
    }
    summary = mappers.vm_summary(raw)
    assert summary["memory_mib"] == 1024
    assert summary["vcpu"] == 4
    assert summary["cluster"] == "Default"
    assert summary["template"] == "Blank"


def test_storage_domain_summary():
    raw = {
        "id": "sd1",
        "name": "zhost-Local",
        "type": "data",
        "status": "active",
        "available": str(370 * mappers.GIB),
        "used": str(52 * mappers.GIB),
        "committed": "0",
    }
    summary = mappers.storage_domain_summary(raw)
    assert summary["available_gib"] == 370
    assert summary["used_gib"] == 52


def test_event_summary():
    raw = {
        "id": "42",
        "severity": "normal",
        "time": "1794085530117",
        "description": "VM lab1-vm1 was started",
        "user": {"id": "u1", "name": "admin"},
    }
    summary = mappers.event_summary(raw)
    assert summary["severity"] == "normal"
    assert summary["user"] == "admin"
