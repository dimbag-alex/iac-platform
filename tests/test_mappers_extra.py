"""! Дополнительные модульные тесты мапперов zVirt: граничные значения и форматы."""
import pytest

from backend.app.zvirt import mappers


# --- to_int: эквивалентные классы и граничные значения -----------------

@pytest.mark.parametrize(
    "raw, expected",
    [
        ("32212254720", 32212254720),  # число строкой (формат zVirt)
        (4096, 4096),                  # уже число
        ("0", 0),                      # граничное значение
        ("-5", -5),                    # отрицательное
    ],
)
def test_to_int_valid_inputs(raw, expected):
    assert mappers.to_int(raw) == expected


@pytest.mark.parametrize("raw", [None, "", "abc", "12.5", [], {}])
def test_to_int_invalid_inputs_return_default(raw):
    assert mappers.to_int(raw) == 0
    assert mappers.to_int(raw, default=7) == 7


# --- Конвертации величин -------------------------------------------------

def test_size_conversions_roundtrip():
    assert mappers.mib_to_bytes(1024) == 2 ** 30
    assert mappers.bytes_to_mib(2 ** 30) == 1024
    assert mappers.gib_to_bytes(6) == 6 * 2 ** 30
    assert mappers.bytes_to_gib("6442450944") == 6  # строка, как в JSON zVirt


def test_bytes_to_gib_rounds_down():
    assert mappers.bytes_to_gib(int(2.7 * 2 ** 30)) == 2


# --- unwrap_collection ---------------------------------------------------

def test_unwrap_collection_skips_non_dict_items():
    payload = {"vm": [{"id": "1"}, "garbage", None, {"id": "2"}]}
    assert mappers.unwrap_collection(payload, "vms") == [{"id": "1"}, {"id": "2"}]


def test_unwrap_collection_unknown_key_and_non_dict():
    assert mappers.unwrap_collection({"foo": [{"id": 1}]}, "foo") == [{"id": 1}]
    assert mappers.unwrap_collection("not-a-dict", "vms") == []
    assert mappers.unwrap_collection({"vm": "not-a-list"}, "vms") == []


# --- vm_summary / vm_detail ----------------------------------------------

RAW_VM = {
    "id": "vm-1",
    "name": "lab1-vm1",
    "status": "up",
    "description": None,
    "memory": "2147483648",
    "cpu": {"topology": {"sockets": "2", "cores": "3", "threads": "1"}},
    "cluster": {"name": "Default"},
    "template": {"id": "tpl-9"},
    "host": {"name": "zhost"},
    "os": {"type": "other_linux"},
    "type": "server",
    "creation_time": "2026-11-08T16:00:00Z",
    "stateless": "false",
    "delete_protected": "false",
    "fqdn": None,
}


def test_vm_summary_vcpu_multiplies_sockets_and_cores():
    dto = mappers.vm_summary(RAW_VM)
    assert dto["vcpu"] == 6            # 2 сокета × 3 ядра
    assert dto["memory_mib"] == 2048   # байты строкой → MiB
    assert dto["description"] == ""    # None → пустая строка
    assert dto["cluster"] == "Default"
    assert dto["template"] == "tpl-9"  # ссылка без имени → id


def test_vm_summary_defaults_without_topology():
    dto = mappers.vm_summary({"id": "x", "name": "y"})
    assert dto["vcpu"] == 1
    assert dto["memory_mib"] == 0
    assert dto["cluster"] is None


def test_vm_detail_extends_summary():
    dto = mappers.vm_detail(RAW_VM)
    assert dto["os_type"] == "other_linux"
    assert dto["fqdn"] == ""
    assert dto["stateless"] == "false"
    assert dto["vcpu"] == 6  # наследует vm_summary


# --- Остальные сущности ----------------------------------------------------

def test_host_summary_memory_to_gib():
    dto = mappers.host_summary({"id": "h1", "memory": "32918028288"})
    assert dto["memory_gib"] == 30.7


def test_network_summary_mtu_and_usages():
    dto = mappers.network_summary(
        {"id": "n1", "mtu": "1500", "usages": {"usage": ["vm"]}}
    )
    assert dto["mtu"] == 1500
    assert dto["usages"] == ["vm"]


def test_template_and_disk_summary():
    tpl = mappers.template_summary({"id": "t1", "memory": "4294967296"})
    assert tpl["memory_mib"] == 4096
    disk = mappers.disk_summary(
        {"id": "d1", "content_type": "iso", "provisioned_size": "1073741824"}
    )
    assert disk["content_type"] == "iso"
    assert disk["size_gib"] == 1


def test_event_summary_user_ref():
    dto = mappers.event_summary(
        {"id": "e1", "severity": "normal", "user": {"name": "admin@zvirt"}}
    )
    assert dto["severity"] == "normal"
    assert dto["user"] == "admin@zvirt"
