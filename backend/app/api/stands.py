"""!
@file stands.py
@brief Эндпоинты декларативного управления стендами (IaC, п. 2.1 и 4.2.3 ТЗ).

Спецификация стенда передаётся в теле запроса как YAML (text/yaml)
или как уже разобранный JSON-объект той же структуры.
"""
from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import ValidationError

from ..schemas import StandSpec, load_stand_spec
from ..zvirt import ZvirtError, ZvirtService
from .deps import raise_http, require_service

router = APIRouter(tags=["stands"])


def _parse_spec(payload: dict) -> StandSpec:
    """! Валидация тела запроса как спецификации стенда."""
    try:
        if isinstance(payload, dict) and "yaml" in payload:
            return load_stand_spec(str(payload["yaml"]))
        return StandSpec(**payload)
    except (ValidationError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"Некорректная спецификация стенда: {exc}")


@router.post("/stands/preview")
def preview_stand(
    payload: dict = Body(...),
    service: ZvirtService = Depends(require_service),
) -> dict:
    """!
    @brief Предпросмотр применения спецификации: что будет создано.

    Ничего не изменяет в гипервизоре — только сопоставляет желаемое
    состояние с фактическим (аналог terraform plan).
    """
    spec = _parse_spec(payload)
    try:
        plan = []
        for vm in spec.resolved_vms():
            existing = service.find_vm_by_name(vm.name)
            plan.append(
                {
                    "name": vm.name,
                    "action": "skip (уже существует)" if existing else "create",
                    "memory_mib": vm.memory_mib,
                    "vcpu": vm.vcpu,
                    "disk_gib": vm.disk_gib,
                    "iso": vm.iso,
                    "start": vm.start,
                    "current_status": existing["status"] if existing else None,
                }
            )
        return {"stand": spec.stand, "plan": plan}
    except ZvirtError as exc:
        raise_http(exc)


@router.post("/stands/apply")
def apply_stand(
    payload: dict = Body(...),
    service: ZvirtService = Depends(require_service),
) -> dict:
    """! Идемпотентное развёртывание стенда по спецификации."""
    spec = _parse_spec(payload)
    try:
        return service.apply_stand(spec)
    except ZvirtError as exc:
        raise_http(exc)


@router.post("/stands/destroy")
def destroy_stand(
    payload: dict = Body(...),
    service: ZvirtService = Depends(require_service),
) -> dict:
    """! Вывод стенда из эксплуатации: остановка и удаление ВМ спецификации."""
    spec = _parse_spec(payload)
    try:
        return service.destroy_stand(spec)
    except ZvirtError as exc:
        raise_http(exc)
