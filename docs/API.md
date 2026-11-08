# API платформы (v0.2.0)

Базовый URL: `http://localhost:8000`. Интерактивная документация: `/docs`.

Все эндпоинты `/api/v1/*` требуют настроенного подключения к zVirt
(иначе HTTP 503). Ошибки гипервизора проксируются с исходным статусом
(400/404/409/...) и текстом `fault.reason/detail` из zVirt.

## Служебные

| Метод | Путь | Описание |
|---|---|---|
| GET | `/api/health` | Состояние платформы (без гипервизора) |
| GET | `/api/health/hypervisor` | Связь с Engine: версия, сводка ресурсов; `not_configured`/`unavailable` при проблемах |

## Инвентарь и мониторинг (`/api/v1/inventory`)

| Метод | Путь | Описание |
|---|---|---|
| GET | `/hosts` | Хосты: статус, память, кластер |
| GET | `/clusters` | Кластеры |
| GET | `/datacenters` | Центры данных: статус, quota_mode |
| GET | `/storage-domains` | Домены хранения: тип, статус, available/used GiB |
| GET | `/networks` | Логические сети |
| GET | `/templates` | Шаблоны ВМ (каталог) |
| GET | `/iso-images` | ISO-образы (диски content_type=iso) |
| GET | `/events?search=&limit=` | Журнал событий/аудит zVirt; `search` — язык запросов zVirt (напр. `severity>normal`) |

## Виртуальные машины (`/api/v1`)

| Метод | Путь | Описание |
|---|---|---|
| GET | `/vms?search=` | Список ВМ (id, имя, статус, память, vCPU) |
| POST | `/vms` | Создать ВМ (201). Тело: `VmCreateRequest` — см. ниже |
| GET | `/vms/{id}` | Детали ВМ |
| POST | `/vms/{id}/actions/{action}` | Действие: `start` `stop` `shutdown` `reboot` `suspend` `reset` |
| DELETE | `/vms/{id}` | Удалить ВМ (с повторами при заблокированных дисках) |

`VmCreateRequest`:

```json
{
  "name": "lab1-vm1",
  "memory_mib": 1024,
  "vcpu": 1,
  "disk_gib": 6,
  "cluster": "Default",
  "storage_domain": "zhost-Local",
  "network": "ovirtmgmt",
  "template": "Blank",
  "iso": "redos8.0.3",
  "start": false
}
```

## Стенды IaC (`/api/v1/stands`)

Спецификацию можно передать как JSON-объект или как YAML в поле `yaml`.

| Метод | Путь | Описание |
|---|---|---|
| POST | `/stands/preview` | План без изменений (create/skip + текущие статусы) |
| POST | `/stands/apply` | Идемпотентное развёртывание: `created`/`existing`/`failed` |
| POST | `/stands/destroy` | Остановка (shutdown → stop) и удаление ВМ: `deleted`/`missing`/`failed` |

Схема спецификации (см. `examples/stand.yaml`): `stand`, `cluster`,
`storage_domain`, `network`, `defaults {memory_mib, vcpu, disk_gib}`,
`vms[] {name, memory_mib?, vcpu?, disk_gib?, iso?, start?, description?}`.
Имена ВМ валидируются по схеме `<стенд>-<роль>` (ТЗ 4.1.11).
