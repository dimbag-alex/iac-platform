"""! Тесты валидации декларативных спецификаций стендов."""
import pytest
from pydantic import ValidationError

from backend.app.schemas import StandSpec, load_stand_spec

VALID_YAML = """
stand: lab1
storage_domain: zhost-Local
defaults:
  memory_mib: 2048
  vcpu: 2
  disk_gib: 10
vms:
  - name: lab1-vm1
    iso: redos8.0.3
  - name: lab1-vm2
    memory_mib: 4096
"""


def test_valid_spec_parses_and_resolves_defaults():
    spec = load_stand_spec(VALID_YAML)
    assert spec.stand == "lab1"
    assert spec.cluster == "Default"
    resolved = {vm.name: vm for vm in spec.resolved_vms()}
    # lab1-vm1 наследует все defaults
    assert resolved["lab1-vm1"].memory_mib == 2048
    assert resolved["lab1-vm1"].vcpu == 2
    assert resolved["lab1-vm1"].disk_gib == 10
    assert resolved["lab1-vm1"].iso == "redos8.0.3"
    # lab1-vm2 переопределяет память, остальное наследует
    assert resolved["lab1-vm2"].memory_mib == 4096
    assert resolved["lab1-vm2"].disk_gib == 10


def test_duplicate_vm_names_rejected():
    with pytest.raises(ValidationError):
        StandSpec(
            stand="lab1",
            storage_domain="sd",
            vms=[{"name": "lab1-vm1"}, {"name": "lab1-vm1"}],
        )


def test_vm_names_must_have_stand_prefix():
    with pytest.raises(ValidationError):
        StandSpec(stand="lab1", storage_domain="sd", vms=[{"name": "other-vm"}])


def test_invalid_names_rejected():
    with pytest.raises(ValidationError):
        StandSpec(stand="Lab_1", storage_domain="sd", vms=[{"name": "lab1-vm"}])
    with pytest.raises(ValidationError):
        StandSpec(stand="lab1", storage_domain="sd", vms=[{"name": "lab1-ВМ"}])


def test_resource_limits_validated():
    with pytest.raises(ValidationError):
        StandSpec(
            stand="lab1",
            storage_domain="sd",
            vms=[{"name": "lab1-vm1", "memory_mib": 64}],
        )


def test_non_mapping_yaml_rejected():
    with pytest.raises(ValueError):
        load_stand_spec("- just\n- a\n- list\n")
