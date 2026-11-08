"""!
@file schemas.py
@brief Pydantic-модели платформы: декларативное описание стенда и DTO API.

Слой валидации между внешним миром (YAML/HTTP) и подсистемой интеграции
с гипервизором. Имена сущностей формируются по единой схеме именования
(требование ТЗ 4.1.11): <стенд>-<роль>, строчные буквы, цифры, дефис.
"""
import re
from typing import List, Optional

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

#: Допустимое имя сущности: строчные буквы/цифры/дефис, начинается с буквы или цифры.
NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")

#: Допустимые действия жизненного цикла ВМ (action-методы zVirt).
VM_ACTIONS = ("start", "stop", "shutdown", "reboot", "suspend", "reset")

#: Служебный CD-ROM zVirt, через который подключаются ISO-образы.
CDROM_ZERO_ID = "00000000-0000-0000-0000-000000000000"

_NAME_RULE_MSG = "имя должно состоять из строчных букв, цифр и дефисов"


def _validate_entity_name(value: str) -> str:
    """! Общая проверка имени сущности по схеме именования платформы."""
    if not NAME_PATTERN.match(value):
        raise ValueError(_NAME_RULE_MSG)
    return value


class VmSpec(BaseModel):
    """!
    @brief Декларативное описание одной ВМ стенда.

    Поля memory_mib/vcpu/disk_gib равные None наследуются из defaults
    спецификации стенда (см. StandSpec.resolved_vms).
    """

    name: str = Field(..., description="Имя ВМ (уникально в пределах стенда)")
    memory_mib: Optional[int] = Field(None, ge=128, le=262144, description="Память, MiB")
    vcpu: Optional[int] = Field(None, ge=1, le=64, description="Число vCPU")
    disk_gib: Optional[int] = Field(None, ge=1, le=4096, description="Диск, GiB")
    description: str = Field("", max_length=400, description="Описание в свободной форме")
    iso: Optional[str] = Field(None, description="Имя ISO-образа для CD-ROM")
    template: str = Field("Blank", description="Шаблон ВМ (Blank или шаблон с ОС)")
    start: bool = Field(False, description="Запустить ВМ после создания")

    @field_validator("name")
    @classmethod
    def name_must_match_scheme(cls, value: str) -> str:
        """! Проверка имени по схеме именования платформы."""
        return _validate_entity_name(value)


class StandDefaults(BaseModel):
    """! Значения по умолчанию для ВМ стенда."""

    memory_mib: int = Field(1024, ge=128, le=262144)
    vcpu: int = Field(1, ge=1, le=64)
    disk_gib: int = Field(8, ge=1, le=4096)


class ResolvedVm(BaseModel):
    """! ВМ стенда с применёнными значениями по умолчанию (без None)."""

    name: str
    memory_mib: int = Field(..., ge=128, le=262144)
    vcpu: int = Field(..., ge=1, le=64)
    disk_gib: int = Field(..., ge=0, le=4096)
    description: str = ""
    iso: Optional[str] = None
    template: str = "Blank"
    start: bool = False


def _ensure_unique(names: List[str]) -> None:
    """! Проверяет уникальность имён ВМ в спецификации."""
    if len(names) != len(set(names)):
        raise ValueError("имена ВМ в спецификации стенда должны быть уникальны")


def _ensure_prefixed(names: List[str], prefix: str) -> None:
    """! Проверяет, что все имена ВМ начинаются с префикса стенда (ТЗ 4.1.11)."""
    offenders = [n for n in names if not n.startswith(prefix)]
    if offenders:
        raise ValueError(
            f"имена ВМ должны начинаться с префикса стенда '{prefix}': {offenders}"
        )


class StandSpec(BaseModel):
    """!
    @brief Декларативное описание топологии стенда (пункт 2.1 ТЗ).

    Применение спецификации идемпотентно: существующие ВМ (по имени)
    пропускаются, отсутствующие создаются.
    """

    stand: str = Field(..., description="Имя стенда — префикс имён всех ВМ")
    cluster: str = Field("Default", description="Кластер zVirt")
    storage_domain: str = Field(..., description="Домен хранения для дисков ВМ")
    network: str = Field("ovirtmgmt", description="Логическая сеть для vNIC")
    defaults: StandDefaults = Field(default_factory=StandDefaults)
    vms: List[VmSpec] = Field(..., min_length=1, description="Виртуальные машины стенда")

    @field_validator("stand")
    @classmethod
    def stand_must_match_scheme(cls, value: str) -> str:
        """! Имя стенда подчиняется той же схеме именования."""
        return _validate_entity_name(value)

    @model_validator(mode="after")
    def vms_must_be_unique_and_prefixed(self) -> "StandSpec":
        """! Имена ВМ уникальны и начинаются с префикса стенда."""
        names = [vm.name for vm in self.vms]
        _ensure_unique(names)
        _ensure_prefixed(names, prefix=f"{self.stand}-")
        return self

    def resolved_vms(self) -> List[ResolvedVm]:
        """! ВМ стенда с применёнными значениями по умолчанию."""
        return [
            ResolvedVm(
                name=vm.name,
                memory_mib=vm.memory_mib if vm.memory_mib is not None else self.defaults.memory_mib,
                vcpu=vm.vcpu if vm.vcpu is not None else self.defaults.vcpu,
                disk_gib=vm.disk_gib if vm.disk_gib is not None else self.defaults.disk_gib,
                description=vm.description,
                iso=vm.iso,
                template=vm.template,
                start=vm.start,
            )
            for vm in self.vms
        ]


class VmCreateRequest(BaseModel):
    """! Запрос API на создание одиночной ВМ (вне спецификации стенда)."""

    name: str
    memory_mib: int = Field(1024, ge=128, le=262144)
    vcpu: int = Field(1, ge=1, le=64)
    disk_gib: int = Field(8, ge=1, le=4096)
    cluster: str = "Default"
    storage_domain: Optional[str] = None
    network: str = "ovirtmgmt"
    template: str = "Blank"
    description: str = ""
    iso: Optional[str] = None
    start: bool = False

    @field_validator("name")
    @classmethod
    def name_must_match_scheme(cls, value: str) -> str:
        """! Проверка имени по схеме именования платформы."""
        return _validate_entity_name(value)


def load_stand_spec(text: str) -> StandSpec:
    """!
    @brief Разбирает YAML-спецификацию стенда в валидированную модель.
    @param text Содержимое YAML-файла.
    @return Валидированная спецификация стенда.
    """
    document = yaml.safe_load(text)
    if not isinstance(document, dict):
        raise ValueError("спецификация стенда должна быть YAML-документом (mapping)")
    return StandSpec(**document)
