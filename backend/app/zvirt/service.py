"""!
@file service.py
@brief Высокоуровневые операции подсистемы интеграции с гипервизором zVirt.

Инкапсулирует знание о путях сервисов zVirt (/vms, /hosts, ...) и форматах
их тел. Возвращает нормализованные DTO из mappers — верхние слои не видят
сырых представлений zVirt.
"""
import time
from typing import Any, Dict, List, Optional

from ..schemas import CDROM_ZERO_ID, VM_ACTIONS, ResolvedVm, StandSpec, VmCreateRequest
from .client import ZvirtClient
from .errors import ZvirtApiError, ZvirtNotFoundError, ZvirtTimeoutError
from . import mappers

#: Терминальные состояния ВМ, из которых допустим запуск.
_VM_STOPPED_STATES = ("down", "suspended")


def _is_retryable_lock(error: ZvirtApiError, attempt: int, attempts: int) -> bool:
    """! True, если ошибка — временная блокировка (HTTP 409) и остались попытки."""
    return error.status_code == 409 and attempt < attempts - 1


class ZvirtService:
    """!
    @brief Фасад подсистемы интеграции с гипервизором (п. 4.2.4 ТЗ).

    Реализует: опрос инвентаря и статусов ресурсов, операции жизненного
    цикла ВМ, идемпотентное применение декларативных спецификаций стендов.
    """

    def __init__(self, client: ZvirtClient) -> None:
        """! @param client Низкоуровневый клиент REST API zVirt."""
        self._client = client

    # ------------------------------------------------------------------
    # Инвентарь и мониторинг состояния
    # ------------------------------------------------------------------

    def engine_info(self) -> Dict[str, Any]:
        """! Точка входа API: версия Engine и сводка по ресурсам."""
        payload = self._client.get("")
        product = payload.get("product_info") or {}
        return {
            "product": product.get("name"),
            "version": (product.get("version") or {}).get("full_version"),
            "summary": payload.get("summary") or {},
        }

    def list_hosts(self) -> List[Dict[str, Any]]:
        """! Список хостов виртуализации с состоянием."""
        payload = self._client.get("/hosts")
        return [mappers.host_summary(h) for h in mappers.unwrap_collection(payload, "hosts")]

    def list_clusters(self) -> List[Dict[str, Any]]:
        """! Список кластеров."""
        payload = self._client.get("/clusters")
        return [mappers.cluster_summary(c) for c in mappers.unwrap_collection(payload, "clusters")]

    def list_datacenters(self) -> List[Dict[str, Any]]:
        """! Список центров данных."""
        payload = self._client.get("/datacenters")
        return [
            mappers.datacenter_summary(dc)
            for dc in mappers.unwrap_collection(payload, "datacenters")
        ]

    def list_storage_domains(self) -> List[Dict[str, Any]]:
        """! Список доменов хранения с ёмкостью."""
        payload = self._client.get("/storagedomains")
        return [
            mappers.storage_domain_summary(sd)
            for sd in mappers.unwrap_collection(payload, "storagedomains")
        ]

    def list_networks(self) -> List[Dict[str, Any]]:
        """! Список логических сетей."""
        payload = self._client.get("/networks")
        return [
            mappers.network_summary(n) for n in mappers.unwrap_collection(payload, "networks")
        ]

    def list_templates(self) -> List[Dict[str, Any]]:
        """! Список шаблонов ВМ (каталог шаблонов топологий, п. 4.2.1 ТЗ)."""
        payload = self._client.get("/templates")
        return [
            mappers.template_summary(t) for t in mappers.unwrap_collection(payload, "templates")
        ]

    def list_iso_images(self) -> List[Dict[str, Any]]:
        """! Список ISO-образов (диски с content_type=iso)."""
        payload = self._client.get("/disks")
        return [
            mappers.disk_summary(d)
            for d in mappers.unwrap_collection(payload, "disks")
            if d.get("content_type") == "iso"
        ]

    def list_events(
        self, search: Optional[str] = None, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """!
        @brief Журнал событий zVirt (аудит и мониторинг, п. 4.1.10 ТЗ).
        @param search Критерии на языке запросов zVirt (например, "severity>normal").
        @param limit Максимум событий (параметр max API).
        """
        params: Dict[str, Any] = {"max": limit}
        if search:
            params["search"] = search
        payload = self._client.get("/events", params=params)
        return [mappers.event_summary(e) for e in mappers.unwrap_collection(payload, "events")]

    # ------------------------------------------------------------------
    # Виртуальные машины
    # ------------------------------------------------------------------

    def list_vms(self, search: Optional[str] = None) -> List[Dict[str, Any]]:
        """! Список ВМ, опционально с критериями поиска zVirt."""
        params = {"search": search} if search else None
        payload = self._client.get("/vms", params=params)
        return [mappers.vm_summary(vm) for vm in mappers.unwrap_collection(payload, "vms")]

    def get_vm(self, vm_id: str) -> Dict[str, Any]:
        """! Детальная информация о ВМ по идентификатору."""
        return mappers.vm_detail(self._client.get(f"/vms/{vm_id}"))

    def find_vm_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """! Идемпотентность IaC: поиск ВМ по точному имени."""
        payload = self._client.get("/vms", params={"search": f"name={name}"})
        for raw in mappers.unwrap_collection(payload, "vms"):
            if raw.get("name") == name:
                return mappers.vm_summary(raw)
        return None

    def get_vm_status(self, vm_id: str) -> str:
        """! Текущий статус ВМ (для опроса после асинхронных операций)."""
        payload = self._client.get(f"/vms/{vm_id}")
        return str(payload.get("status") or "unknown")

    def create_vm(self, request: VmCreateRequest) -> Dict[str, Any]:
        """!
        @brief Создание ВМ из шаблона с диском, сетевой картой и опциональным ISO.
        @param request Валидированный запрос на создание.
        @return Детали созданной ВМ.
        """
        vm_id = self._create_vm_shell(
            name=request.name,
            cluster=request.cluster,
            template=request.template,
            memory_mib=request.memory_mib,
            vcpu=request.vcpu,
            description=request.description,
        )
        self._provision_vm_devices(
            vm_id,
            name=request.name,
            template=request.template,
            disk_gib=request.disk_gib,
            storage_domain=request.storage_domain,
            network=request.network,
            iso=request.iso,
            start=request.start,
        )
        return self.get_vm(vm_id)

    def delete_vm(self, vm_id: str, attempts: int = 6, retry_interval: float = 10.0) -> None:
        """!
        @brief Удаление ВМ вместе с созданными для неё дисками.

        Если диски ВМ ещё заблокированы фоновыми операциями (HTTP 409),
        удаление повторяется с паузой — это штатная ситуация сразу после
        создания ВМ.
        """
        for attempt in range(attempts):
            try:
                self._client.delete(f"/vms/{vm_id}")
                return
            except ZvirtApiError as exc:
                if not _is_retryable_lock(exc, attempt, attempts):
                    raise
                time.sleep(retry_interval)

    def vm_action(self, vm_id: str, action: str) -> Dict[str, Any]:
        """!
        @brief Действие жизненного цикла ВМ (start/stop/shutdown/...).
        @param vm_id Идентификатор ВМ.
        @param action Одно из VM_ACTIONS.
        @return Статус ВМ после приёма действия сервером.
        """
        if action not in VM_ACTIONS:
            raise ValueError(f"неподдерживаемое действие ВМ: {action}")
        self._client.post(f"/vms/{vm_id}/{action}", body={"async": True})
        return {"id": vm_id, "action": action, "status": self.get_vm_status(vm_id)}

    def stop_vm(self, vm_id: str, graceful_timeout: float = 60.0) -> str:
        """!
        @brief Остановка ВМ: сначала ACPI shutdown, при таймауте — принудительный stop.

        Без гостевого агента/ОС ACPI-выключение может не сработать —
        тогда применяется принудительное выключение питания.
        @return Итоговый статус ВМ ("down").
        """
        self.wait_for_vm_unlocked(vm_id)
        if self.get_vm_status(vm_id) in _VM_STOPPED_STATES:
            return "down"
        self.vm_action(vm_id, "shutdown")
        try:
            return self.wait_for_vm_status(vm_id, targets=("down",), timeout=graceful_timeout)
        except ZvirtTimeoutError:
            self.vm_action(vm_id, "stop")
            return self.wait_for_vm_status(vm_id, targets=("down",), timeout=graceful_timeout)

    def wait_for_vm_unlocked(self, vm_id: str, timeout: float = 900.0, poll_interval: float = 5.0) -> str:
        """!
        @brief Ожидание снятия блокировки ВМ (image_locked).

        Клонирование диска шаблона — длительная фоновая операция: всё это
        время ВМ заблокирована, и действия над ней отклоняются (HTTP 409).
        @return Статус ВМ после снятия блокировки.
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            status = self.get_vm_status(vm_id)
            if status != "image_locked":
                return status
            time.sleep(poll_interval)
        raise ZvirtTimeoutError(
            f"ВМ {vm_id} не разблокировалась за {timeout:.0f} с (клонирование диска)"
        )

    def wait_for_vm_status(
        self,
        vm_id: str,
        targets: tuple = ("down", "up"),
        timeout: float = 120.0,
        poll_interval: float = 3.0,
    ) -> str:
        """!
        @brief Опрос статуса ВМ до терминального состояния.

        Операции zVirt асинхронны (HTTP 202): успешное выполнение
        подтверждается только сменой статуса объекта.
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            status = self.get_vm_status(vm_id)
            if status in targets:
                return status
            time.sleep(poll_interval)
        raise ZvirtTimeoutError(
            f"ВМ {vm_id} не достигла статуса {targets} за {timeout:.0f} с"
        )

    # ------------------------------------------------------------------
    # Устройства ВМ
    # ------------------------------------------------------------------

    def attach_disk(
        self,
        vm_id: str,
        name: str,
        size_gib: int,
        storage_domain: Optional[str],
        bootable: bool = True,
    ) -> str:
        """!
        @brief Создание и подключение диска к ВМ.
        @return Идентификатор подключения диска (disk attachment).
        """
        disk: Dict[str, Any] = {
            "name": name,
            "format": "cow",
            "provisioned_size": mappers.gib_to_bytes(size_gib),
        }
        if storage_domain:
            disk["storage_domains"] = {"storage_domain": [{"name": storage_domain}]}
        payload = self._client.post(
            f"/vms/{vm_id}/diskattachments",
            body={
                "bootable": bootable,
                "interface": "virtio",
                "active": True,
                "disk": disk,
            },
        )
        # Создание диска асинхронно: до статуса ok диск заблокирован,
        # и удалить ВМ нельзя (HTTP 409 "disks are locked").
        disk_ref = payload.get("disk") or {}
        if disk_ref.get("id"):
            self.wait_for_disk_status(str(disk_ref["id"]), targets=("ok",))
        return str(payload.get("id") or "")

    def wait_for_disk_status(
        self,
        disk_id: str,
        targets: tuple = ("ok",),
        timeout: float = 180.0,
        poll_interval: float = 3.0,
    ) -> str:
        """! Опрос статуса диска до терминального состояния (напр., ok)."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            payload = self._client.get(f"/disks/{disk_id}")
            status = str(payload.get("status") or "unknown")
            if status in targets:
                return status
            time.sleep(poll_interval)
        raise ZvirtTimeoutError(
            f"Диск {disk_id} не достиг статуса {targets} за {timeout:.0f} с"
        )

    def attach_nic(self, vm_id: str, name: str, network: str) -> str:
        """!
        @brief Подключение сетевой карты ВМ к логической сети.
        @return Идентификатор созданной vNIC.
        """
        profile_id = self._vnic_profile_id(network)
        payload = self._client.post(
            f"/vms/{vm_id}/nics",
            body={"name": name, "interface": "virtio", "vnic_profile": {"id": profile_id}},
        )
        return str(payload.get("id") or "")

    def attach_iso(self, vm_id: str, iso_name: str) -> None:
        """!
        @brief Подключение ISO-образа к CD-ROM ВМ.

        Начиная с zVirt 4.4 ISO-образы хранятся как диски с
        content_type=iso; идентификатор диска передаётся как file id.
        """
        disk_id = self._find_iso_disk_id(iso_name)
        self._client.put(
            f"/vms/{vm_id}/cdroms/{CDROM_ZERO_ID}",
            body={"file": {"id": disk_id}},
        )

    # ------------------------------------------------------------------
    # Декларативные стенды (IaC)
    # ------------------------------------------------------------------

    def apply_stand(self, spec: StandSpec) -> Dict[str, Any]:
        """!
        @brief Идемпотентное развёртывание стенда по спецификации (п. 2.1 ТЗ).

        Для каждой ВМ: если ВМ с таким именем существует — пропускается,
        иначе создаётся с диском, сетевой картой и опциональным ISO.
        @return Отчёт: созданные, пропущенные и ошибочные ВМ.
        """
        report: Dict[str, Any] = {"stand": spec.stand, "created": [], "existing": [], "failed": {}}
        for vm in spec.resolved_vms():
            if self.find_vm_by_name(vm.name):
                report["existing"].append(vm.name)
                continue
            try:
                self._apply_stand_vm(spec, vm)
                report["created"].append(vm.name)
            except Exception as exc:  # отчёт агрегирует ошибки по всем ВМ
                report["failed"][vm.name] = str(exc)
        return report

    def destroy_stand(self, spec: StandSpec) -> Dict[str, Any]:
        """!
        @brief Вывод стенда из эксплуатации: удаление ВМ спецификации.
        @return Отчёт: удалённые, отсутствующие и ошибочные ВМ.
        """
        report: Dict[str, Any] = {"stand": spec.stand, "deleted": [], "missing": [], "failed": {}}
        for vm in spec.resolved_vms():
            existing = self.find_vm_by_name(vm.name)
            if not existing:
                report["missing"].append(vm.name)
                continue
            try:
                self.stop_vm(existing["id"])
                self.delete_vm(existing["id"])
                report["deleted"].append(vm.name)
            except Exception as exc:
                report["failed"][vm.name] = str(exc)
        return report

    # ------------------------------------------------------------------
    # Внутренние помощники
    # ------------------------------------------------------------------

    def _apply_stand_vm(self, spec: StandSpec, vm: ResolvedVm) -> None:
        """! Создание одной ВМ стенда со всеми устройствами."""
        vm_id = self._create_vm_shell(
            name=vm.name,
            cluster=spec.cluster,
            template=vm.template,
            memory_mib=vm.memory_mib,
            vcpu=vm.vcpu,
            description=vm.description or f"ВМ стенда {spec.stand}",
        )
        self._provision_vm_devices(
            vm_id,
            name=vm.name,
            template=vm.template,
            disk_gib=vm.disk_gib,
            storage_domain=spec.storage_domain,
            network=spec.network,
            iso=vm.iso,
            start=vm.start,
        )

    def _provision_vm_devices(
        self,
        vm_id: str,
        name: str,
        template: str,
        disk_gib: int,
        storage_domain: Optional[str],
        network: str,
        iso: Optional[str],
        start: bool,
    ) -> None:
        """!
        @brief Подключение устройств ВМ: диск (для Blank), vNIC, ISO, запуск.

        Диск нужен только при создании из шаблона Blank: при клонировании
        из шаблона с ОС диск наследуется от шаблона (тонкий клон).
        """
        if self._is_blank_template(template) and disk_gib > 0:
            self.attach_disk(vm_id, name=f"{name}-disk-0", size_gib=disk_gib,
                             storage_domain=storage_domain, bootable=True)
        self.attach_nic(vm_id, name="nic0", network=network)
        if iso:
            self.attach_iso(vm_id, iso)
        if start:
            # При клоне из шаблона ВМ заблокирована до окончания копирования диска.
            self.wait_for_vm_unlocked(vm_id)
            self.vm_action(vm_id, "start")

    @staticmethod
    def _is_blank_template(template_name: str) -> bool:
        """! Шаблон Blank не содержит дисков — диск создаётся отдельно."""
        return template_name.strip().lower() == "blank"

    def _create_vm_shell(
        self,
        name: str,
        cluster: str,
        template: str,
        memory_mib: int,
        vcpu: int,
        description: str,
    ) -> str:
        """!
        @brief Создание ВМ без устройств (POST /vms).
        @return Идентификатор созданной ВМ.
        """
        payload = self._client.post(
            "/vms",
            body={
                "name": name,
                "description": description,
                "cluster": {"name": cluster},
                "template": {"name": template},
                "memory": mappers.mib_to_bytes(memory_mib),
                "cpu": {"topology": {"sockets": 1, "cores": vcpu, "threads": 1}},
                "os": {"boot": {"devices": {"device": ["hd"]}}},
            },
        )
        vm_id = payload.get("id")
        if not vm_id:
            raise ZvirtNotFoundError("ВМ создана, но ответ не содержит id")
        return str(vm_id)

    def _vnic_profile_id(self, network_name: str) -> str:
        """! Идентификатор vNIC-профиля логической сети (нужен для создания vNIC)."""
        payload = self._client.get("/networks", params={"search": f"name={network_name}"})
        networks = mappers.unwrap_collection(payload, "networks")
        network = next((n for n in networks if n.get("name") == network_name), None)
        if not network:
            raise ZvirtNotFoundError(f"логическая сеть '{network_name}'")
        profiles = self._client.get(f"/networks/{network['id']}/vnicprofiles")
        items = mappers.unwrap_collection(profiles, "vnicprofiles")
        if not items:
            raise ZvirtNotFoundError(f"vNIC-профиль сети '{network_name}'")
        return str(items[0]["id"])

    def _find_iso_disk_id(self, iso_name: str) -> str:
        """! Идентификатор диска-образа ISO по имени."""
        payload = self._client.get("/disks", params={"search": f"name={iso_name}"})
        for disk in mappers.unwrap_collection(payload, "disks"):
            if disk.get("name") == iso_name and disk.get("content_type") == "iso":
                return str(disk["id"])
        raise ZvirtNotFoundError(f"ISO-образ '{iso_name}'")
