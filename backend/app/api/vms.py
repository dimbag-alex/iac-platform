"""!
@file vms.py
@brief Эндпоинты централизованного управления виртуальными машинами (п. 2.1 ТЗ).
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, Query

from ..schemas import VM_ACTIONS, VmCreateRequest
from ..zvirt import ZvirtError, ZvirtNotFoundError, ZvirtService
from .deps import raise_http, require_service

router = APIRouter(tags=["virtual-machines"])


@router.get("/vms")
def list_vms(
    search: Optional[str] = Query(None, description="Критерии поиска zVirt, напр. name=lab1-*"),
    service: ZvirtService = Depends(require_service),
) -> List[dict]:
    """! Список виртуальных машин с состоянием."""
    try:
        return service.list_vms(search=search)
    except ZvirtError as exc:
        raise_http(exc)


@router.post("/vms", status_code=201)
def create_vm(
    request: VmCreateRequest,
    service: ZvirtService = Depends(require_service),
) -> dict:
    """! Создание ВМ из шаблона с диском, vNIC и опциональным ISO."""
    try:
        if service.find_vm_by_name(request.name):
            return service.get_vm(service.find_vm_by_name(request.name)["id"])
        return service.create_vm(request)
    except ZvirtError as exc:
        raise_http(exc)


@router.get("/vms/{vm_id}")
def get_vm(vm_id: str, service: ZvirtService = Depends(require_service)) -> dict:
    """! Детальная информация о ВМ."""
    try:
        return service.get_vm(vm_id)
    except ZvirtError as exc:
        raise_http(exc)


@router.post("/vms/{vm_id}/actions/{action}")
def vm_action(
    vm_id: str,
    action: str,
    service: ZvirtService = Depends(require_service),
) -> dict:
    """!
    @brief Действие жизненного цикла ВМ.
    Допустимые действия: start, stop, shutdown, reboot, suspend, reset.
    """
    if action not in VM_ACTIONS:
        raise_http(ZvirtNotFoundError(f"действие '{action}' (допустимы: {', '.join(VM_ACTIONS)})"))
    try:
        return service.vm_action(vm_id, action)
    except ZvirtError as exc:
        raise_http(exc)


@router.delete("/vms/{vm_id}")
def delete_vm(vm_id: str, service: ZvirtService = Depends(require_service)) -> dict:
    """! Удаление ВМ (вывод из эксплуатации)."""
    try:
        service.delete_vm(vm_id)
        return {"status": "deleted", "id": vm_id}
    except ZvirtError as exc:
        raise_http(exc)
