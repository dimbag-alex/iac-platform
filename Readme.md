# IaC Platform — АИС УЖЦ ВВИ

Платформа управления жизненным циклом виртуализированной вычислительной
инфраструктуры с использованием подхода IaC (ТЗ RU.МИЭМ.000001.001.ТЗ,
курс «Технологии разработки программного обеспечения», НИУ ВШЭ).

Гипервизор: **zVirt** (oVirt-совместимый REST API v4, `/ovirt-engine/api`).

## Текущий статус (v0.2.0)

Работает против живого стенда zVirt 4.5 (проверено end-to-end):

- ✅ OAuth 2.0 аутентификация в zVirt Engine (password grant, Bearer, авто-refresh при 401)
- ✅ Инвентарь и мониторинг: хосты, кластеры, ЦД, домены хранения, сети, шаблоны, ISO, события (аудит)
- ✅ Жизненный цикл ВМ: создание (шаблон + диск + vNIC + ISO), start/stop/shutdown/reboot/suspend/reset, удаление
- ✅ Декларативные стенды (IaC): YAML-спецификация → preview (аналог `terraform plan`) → идемпотентный apply → destroy
- ✅ Единая схема именования ВМ `<стенд>-<роль>` (ТЗ 4.1.11) с валидацией
- ✅ Опрос асинхронных операций (статусы ВМ/дисков), повтор удаления при заблокированных дисках (HTTP 409)
- ✅ 27 модульных тестов (мапперы, спецификации, HTTP-клиент на моковом транспорте)

Покрытые пункты ТЗ: 2.1 (декларативное описание топологии, централизованное
управление ВМ, мониторинг), 4.1.10 (журнал аудита), 4.1.11 (схема
именования), 4.2.4 (подсистема интеграции с гипервизором).

Не реализовано пока: веб-интерфейсы, БД (PostgreSQL), оркестрация
Terraform/Ansible, аутентификация пользователей/LDAP, квоты, консоль VNC/SPICE.

## Архитектура

```
backend/app/
├── main.py              # FastAPI-приложение (роутеры)
├── config.py            # Настройки из env (+ .env), тестируемая загрузка
├── schemas.py           # Pydantic: спецификация стенда, DTO, схема именования
├── api/                 # HTTP-слой
│   ├── health.py        #   /api/health, /api/health/hypervisor
│   ├── inventory.py     #   /api/v1/inventory/* (мониторинг ресурсов)
│   ├── vms.py           #   /api/v1/vms* (жизненный цикл ВМ)
│   ├── stands.py        #   /api/v1/stands/{preview,apply,destroy} (IaC)
│   └── deps.py          #   DI: синглтон сервиса, маппинг ошибок
└── zvirt/               # Подсистема интеграции с гипервизором (ТЗ 4.2.4)
    ├── auth.py          #   OAuthTokenProvider (RFC 6749 §4.3, scope ovirt-app-api)
    ├── client.py        #   HTTP-клиент REST API zVirt (JSON, Bearer, fault → ошибки)
    ├── service.py       #   ZvirtService: операции и идемпотентный apply/destroy
    ├── mappers.py       #   Сырой JSON zVirt → DTO (чистые функции)
    └── errors.py        #   Иерархия исключений + маппинг на HTTP-статусы
examples/stand.yaml      # Пример декларативной спецификации стенда
tests/                   # pytest, 27 тестов без сети (httpx.MockTransport)
```

## Установка и запуск

```bash
python3.9 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

export ZVIRT_URL="https://zhost.lab.loc"
export ZVIRT_USERNAME="admin@zvirt@internalsso"
export ZVIRT_PASSWORD="..."
export ZVIRT_VERIFY_TLS=false      # самоподписанный сертификат стенда

uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
# Swagger UI: http://localhost:8000/docs
```

Переменные можно положить в `.env` (не коммитится) — см. `.env.example`.

## Примеры

```bash
# Связь с гипервизором
curl -s localhost:8000/api/health/hypervisor | jq

# Инвентарь
curl -s localhost:8000/api/v1/inventory/hosts | jq
curl -s localhost:8000/api/v1/inventory/events?limit=10 | jq

# Стенд из спецификации
curl -s -X POST localhost:8000/api/v1/stands/preview \
  -H 'Content-Type: application/json' \
  -d "{\"yaml\": $(jq -Rs . < examples/stand.yaml)}" | jq

curl -s -X POST localhost:8000/api/v1/stands/apply \
  -H 'Content-Type: application/json' \
  -d "{\"yaml\": $(jq -Rs . < examples/stand.yaml)}" | jq

# Жизненный цикл ВМ
curl -s -X POST localhost:8000/api/v1/vms/<vm_id>/actions/start | jq
curl -s -X DELETE localhost:8000/api/v1/vms/<vm_id> | jq

# Вывод стенда из эксплуатации
curl -s -X POST localhost:8000/api/v1/stands/destroy \
  -H 'Content-Type: application/json' \
  -d "{\"yaml\": $(jq -Rs . < examples/stand.yaml)}" | jq
```

## Тестирование

```bash
pytest tests/ -v
```

## Практические заметки по zVirt (из конспекта docs)

- API v4 oVirt-совместимый; JSON: числа приходят строками — нормализация в `zvirt/mappers.py`.
- Операции асинхронны (HTTP 202 ≠ успех): подтверждение — опросом статуса объекта.
- Удаление ВМ сразу после создания может вернуть 409 («disks are locked») —
  клиент ждёт статуса диска `ok` и повторяет удаление.
- ISO-образы — диски с `content_type=iso`; подключение к ВМ — через
  `PUT /vms/{id}/cdroms/00000000-0000-0000-0000-000000000000`.
- В zVirt 5.0 аутентификация — только OAuth2 (Keycloak, realm `internalsso`);
  Basic auth не работает.
