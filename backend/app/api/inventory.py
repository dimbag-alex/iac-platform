"""!
@file inventory.py
@brief Эндпоинты инвентаря и мониторинга: хосты, кластеры, ЦД, хранилища,
сети, шаблоны, ISO-образы и журнал событий гипервизора.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, Query

from ..zvirt import ZvirtError, ZvirtService
from .deps import raise_http, require_service

router = APIRouter(tags=["inventory"])


@router.get("/hosts")
def list_hosts(service: ZvirtService = Depends(require_service)) -> List[dict]:
    """! Состояние хостов виртуализации (мониторинг серверов, п. 2.1 ТЗ)."""
    try:
        return service.list_hosts()
    except ZvirtError as exc:
        raise_http(exc)


@router.get("/clusters")
def list_clusters(service: ZvirtService = Depends(require_service)) -> List[dict]:
    """! Список кластеров."""
    try:
        return service.list_clusters()
    except ZvirtError as exc:
        raise_http(exc)


@router.get("/datacenters")
def list_datacenters(service: ZvirtService = Depends(require_service)) -> List[dict]:
    """! Список центров данных."""
    try:
        return service.list_datacenters()
    except ZvirtError as exc:
        raise_http(exc)


@router.get("/storage-domains")
def list_storage_domains(service: ZvirtService = Depends(require_service)) -> List[dict]:
    """! Домены хранения с доступной ёмкостью (контроль ресурсов)."""
    try:
        return service.list_storage_domains()
    except ZvirtError as exc:
        raise_http(exc)


@router.get("/networks")
def list_networks(service: ZvirtService = Depends(require_service)) -> List[dict]:
    """! Логические сети гипервизора."""
    try:
        return service.list_networks()
    except ZvirtError as exc:
        raise_http(exc)


@router.get("/templates")
def list_templates(service: ZvirtService = Depends(require_service)) -> List[dict]:
    """! Каталог шаблонов ВМ (п. 4.2.1 ТЗ)."""
    try:
        return service.list_templates()
    except ZvirtError as exc:
        raise_http(exc)


@router.get("/iso-images")
def list_iso_images(service: ZvirtService = Depends(require_service)) -> List[dict]:
    """! Доступные ISO-образы установщиков ОС."""
    try:
        return service.list_iso_images()
    except ZvirtError as exc:
        raise_http(exc)


@router.get("/events")
def list_events(
    search: Optional[str] = Query(None, description="Критерии поиска zVirt, напр. severity>normal"),
    limit: int = Query(50, ge=1, le=1000),
    service: ZvirtService = Depends(require_service),
) -> List[dict]:
    """! Журнал событий гипервизора (аудит, п. 4.1.10 ТЗ)."""
    try:
        return service.list_events(search=search, limit=limit)
    except ZvirtError as exc:
        raise_http(exc)
