"""!
@file mappers.py
@brief Преобразование сырых JSON-представлений zVirt в компактные DTO платформы.

Чистые функции без сетевого ввода-вывода — покрываются модульными тестами.
JSON-представление zVirt отдаёт числа строками, поэтому вся нормализация
чисел сосредоточена здесь.
"""
from typing import Any, Dict, List, Optional

MIB = 2 ** 20
GIB = 2 ** 30

#: Вложенные коллекции zVirt имеют вид {"vm": [...]} — ключ в единственном числе.
SINGULAR_KEYS: Dict[str, str] = {
    "hosts": "host",
    "clusters": "cluster",
    "datacenters": "data_center",
    "storagedomains": "storage_domain",
    "networks": "network",
    "templates": "template",
    "vms": "vm",
    "disks": "disk",
    "events": "event",
    "nics": "nic",
    "diskattachments": "disk_attachment",
    "files": "file",
    "vnicprofiles": "vnic_profile",
}


def to_int(value: Any, default: int = 0) -> int:
    """! Числа zVirt приходят строками; безопасное приведение к int."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def mib_to_bytes(value_mib: int) -> int:
    """! Мебибайты в байты (поле memory ВМ задаётся в байтах)."""
    return value_mib * MIB


def gib_to_bytes(value_gib: int) -> int:
    """! Гибибайты в байты (provisioned_size диска)."""
    return value_gib * GIB


def bytes_to_mib(value: Any) -> int:
    """! Байты в мебибайты с округлением вниз."""
    return to_int(value) // MIB


def bytes_to_gib(value: Any) -> int:
    """! Байты в гибибайты с округлением вниз."""
    return to_int(value) // GIB


def unwrap_collection(payload: Any, key: str) -> List[Dict[str, Any]]:
    """!
    @brief Извлекает элементы коллекции zVirt из ответа list-метода.
    @param payload JSON ответа (например, {"vm": [...]}).
    @param key Имя коллекции ("vms", "hosts", ...) или одиночный ключ.
    @return Список сырых представлений объектов.
    """
    if not isinstance(payload, dict):
        return []
    singular = SINGULAR_KEYS.get(key, key)
    items = payload.get(singular)
    if isinstance(items, list):
        return [item for item in items if isinstance(item, dict)]
    return []


def _ref(raw: Dict[str, Any], key: str) -> Optional[str]:
    """! Имя/идентификатор связанного объекта (ссылки zVirt)."""
    link = raw.get(key)
    if isinstance(link, dict):
        return link.get("name") or link.get("id")
    return None


def vm_summary(raw: Dict[str, Any]) -> Dict[str, Any]:
    """! Компактное представление ВМ для списков."""
    cpu = raw.get("cpu") or {}
    topology = cpu.get("topology") or {}
    return {
        "id": raw.get("id"),
        "name": raw.get("name"),
        "status": raw.get("status"),
        "description": raw.get("description") or "",
        "memory_mib": bytes_to_mib(raw.get("memory")),
        "vcpu": to_int(topology.get("sockets"), 1) * to_int(topology.get("cores"), 1),
        "cluster": _ref(raw, "cluster"),
        "template": _ref(raw, "template"),
        "host": _ref(raw, "host"),
    }


def vm_detail(raw: Dict[str, Any]) -> Dict[str, Any]:
    """! Расширенное представление ВМ."""
    detail = vm_summary(raw)
    os_info = raw.get("os") or {}
    detail.update(
        {
            "os_type": os_info.get("type"),
            "type": raw.get("type"),
            "creation_time": raw.get("creation_time"),
            "stateless": raw.get("stateless"),
            "delete_protected": raw.get("delete_protected"),
            "fqdn": raw.get("fqdn") or "",
        }
    )
    return detail


def host_summary(raw: Dict[str, Any]) -> Dict[str, Any]:
    """! Компактное представление хоста виртуализации."""
    return {
        "id": raw.get("id"),
        "name": raw.get("name"),
        "status": raw.get("status"),
        "address": raw.get("address"),
        "memory_gib": round(to_int(raw.get("memory")) / GIB, 1),
        "cluster": _ref(raw, "cluster"),
    }


def cluster_summary(raw: Dict[str, Any]) -> Dict[str, Any]:
    """! Компактное представление кластера."""
    return {
        "id": raw.get("id"),
        "name": raw.get("name"),
        "description": raw.get("description") or "",
        "data_center": _ref(raw, "data_center"),
    }


def datacenter_summary(raw: Dict[str, Any]) -> Dict[str, Any]:
    """! Компактное представление центра данных."""
    return {
        "id": raw.get("id"),
        "name": raw.get("name"),
        "status": raw.get("status"),
        "quota_mode": raw.get("quota_mode"),
    }


def storage_domain_summary(raw: Dict[str, Any]) -> Dict[str, Any]:
    """! Компактное представление домена хранения."""
    return {
        "id": raw.get("id"),
        "name": raw.get("name"),
        "type": raw.get("type"),
        "status": raw.get("status"),
        "available_gib": bytes_to_gib(raw.get("available")),
        "used_gib": bytes_to_gib(raw.get("used")),
        "committed_gib": bytes_to_gib(raw.get("committed")),
    }


def network_summary(raw: Dict[str, Any]) -> Dict[str, Any]:
    """! Компактное представление логической сети."""
    usages = raw.get("usages") or {}
    return {
        "id": raw.get("id"),
        "name": raw.get("name"),
        "description": raw.get("description") or "",
        "mtu": to_int(raw.get("mtu")),
        "usages": usages.get("usage", []),
        "data_center": _ref(raw, "data_center"),
    }


def template_summary(raw: Dict[str, Any]) -> Dict[str, Any]:
    """! Компактное представление шаблона ВМ."""
    return {
        "id": raw.get("id"),
        "name": raw.get("name"),
        "status": raw.get("status"),
        "type": raw.get("type"),
        "memory_mib": bytes_to_mib(raw.get("memory")),
        "description": raw.get("description") or "",
    }


def disk_summary(raw: Dict[str, Any]) -> Dict[str, Any]:
    """! Компактное представление диска (включая ISO-образы)."""
    return {
        "id": raw.get("id"),
        "name": raw.get("name"),
        "content_type": raw.get("content_type"),
        "format": raw.get("format"),
        "status": raw.get("status"),
        "size_gib": bytes_to_gib(raw.get("provisioned_size")),
    }


def event_summary(raw: Dict[str, Any]) -> Dict[str, Any]:
    """! Компактное представление события (журнал аудита zVirt)."""
    return {
        "id": raw.get("id"),
        "severity": raw.get("severity"),
        "time": raw.get("time"),
        "code": raw.get("code"),
        "description": raw.get("description") or "",
        "user": _ref(raw, "user"),
    }
