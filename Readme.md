# IaC Platform — АИС УЖЦ ВВИ

Платформа управления жизненным циклом виртуализированной вычислительной
инфраструктуры с использованием подхода IaC (ТЗ RU.МИЭМ.000001.001.ТЗ,
курс «Технологии разработки программного обеспечения», НИУ ВШЭ).

Гипервизор: **zVirt** (oVirt-совместимый REST API v4, `/ovirt-engine/api`).

## Текущий статус (v0.3.0)

Работает против живого стенда zVirt 4.5 (проверено end-to-end):

- ✅ OAuth 2.0 аутентификация в zVirt Engine (password grant, Bearer, авто-refresh при 401)
- ✅ Инвентарь и мониторинг: хосты, кластеры, ЦД, домены хранения, сети, шаблоны, ISO, события (аудит)
- ✅ Жизненный цикл ВМ: создание (из шаблона или Blank + диск + vNIC + ISO), start/stop/shutdown/reboot/suspend/reset, удаление
- ✅ Декларативные стенды (IaC): YAML-спецификация → preview (аналог `terraform plan`) → идемпотентный apply → destroy
- ✅ Веб-интерфейс (SPA на `/`): Обзор, Виртуальные машины, Стенды IaC, Каталог (шаблоны/ISO)
- ✅ Единая схема именования ВМ `<стенд>-<роль>` (ТЗ 4.1.11) с валидацией
- ✅ Опрос асинхронных операций (статусы ВМ/дисков), повтор удаления при заблокированных дисках (HTTP 409)
- ✅ 28 модульных тестов (мапперы, спецификации, HTTP-клиент на моковом транспорте)

Покрытые пункты ТЗ: 2.1 (декларативное описание топологии, централизованное
управление ВМ, мониторинг), 4.1.10 (журнал аудита), 4.1.11 (схема
именования), 4.2.4 (подсистема интеграции с гипервизором).

Не реализовано пока: БД (PostgreSQL), оркестрация
Terraform/Ansible, аутентификация пользователей/LDAP, квоты, консоль VNC/SPICE.

## Архитектура

```
backend/app/
├── main.py              # FastAPI-приложение (роутеры + статика UI на /)
├── config.py            # Настройки из env (+ .env), тестируемая загрузка
├── schemas.py           # Pydantic: спецификация стенда, DTO, схема именования
├── static/index.html    # Веб-интерфейс (SPA, vanilla JS, без сборки)
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
tests/                   # pytest, 28 тестов без сети (httpx.MockTransport)
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
# Веб-интерфейс: http://localhost:8000/
# Swagger UI:    http://localhost:8000/docs
```

Переменные можно положить в `.env` (не коммитится) — см. `.env.example`.

## Веб-интерфейс

SPA на чистом JS (`backend/app/static/index.html`, без сборки и npm), раздаётся
FastAPI с корня `/`. Четыре вкладки:

- **Обзор** — сводка по хостам/ВМ/хранилищу, занятость доменов хранения, лента событий (аудит).
- **Виртуальные машины** — таблица ВМ со статусами и действиями
  (start/stop/shutdown/reboot/suspend/reset/удалить); кнопка «+ Создать ВМ»
  открывает форму с выбором шаблона, сети, ISO и домена хранения.
- **Стенды IaC** — редактор YAML-спецификации: Предпросмотр (plan),
  Применить (apply), Удалить стенд (destroy).
- **Каталог** — шаблоны ВМ и ISO-образы.

При transient-статусах ВМ (image_locked и т.п.) список обновляется автоматически.

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
- При создании ВМ из шаблона диск клонируется асинхронно: ВМ в статусе
  `image_locked` (на слабом железе — минуты). Действия в это время → 409,
  поэтому сервис ждёт разблокировки перед start/stop.
- ACPI shutdown на ВМ без ОС/гостевого агента висит — сервис делает
  fallback на принудительный stop по таймауту.
- ISO-образы — диски с `content_type=iso`; подключение к ВМ — через
  `PUT /vms/{id}/cdroms/00000000-0000-0000-0000-000000000000`.
- В zVirt 5.0 аутентификация — только OAuth2 (Keycloak, realm `internalsso`);
  Basic auth не работает.
