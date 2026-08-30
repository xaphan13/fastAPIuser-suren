# AGENTS.md — Инструкции для AI-агентов

> Этот файл — ориентир для AI-ассистентов (Copilot, Claude, Koda и др.), работающих с этим репозиторием. Он описывает контекст проекта, правила работы с кодом и указывает на существующую документацию.

## О проекте

`fastAPIuser-suren` — серверное веб-приложение на **FastAPI** (Python ≥ 3.12): подсистема управления пользователями. Регистрация, аутентификация через [`fastapi-users`](https://github.com/fastapi-users/fastapi-users) (cookie-транспорт + хранение токенов в PostgreSQL), верификация email, сброс пароля, ролевой доступ (user/superuser), кэширование списка пользователей в Redis (TTL 60s), Jinja2 HTML-страницы, email-рассылка (aiosmtplib), исходящие вебхуки (aiohttp), админ-панель (SQLAdmin).

Архитектура — **слоистый монолит**: `core` (конфиг, модели, аутентификация) → `api` (роутеры, DI) → `views` (HTML) → инфраструктура (`mailing`, `utils`, `middlewares`). Всё асинхронное.

## ⚠️ Обязательно: существующая документация

В репозитории есть подробная документация в **`docs/`** — читайте её перед изменениями:

| Файл | Когда читать |
|---|---|
| `docs/01_project_structure.md` | Перед навигацией по коду: полное дерево файлов и роль каждого модуля |
| `docs/02_architecture.md` | Перед изменением архитектуры, DI-цепочек, конфигурации, кэширования |
| `docs/03_execution_flow.md` | Перед изменением роутов, middleware, бизнес-процессов (регистрация/логин/верификация) |
| `docs/04_code_quality.md` | Перед рефакторингом: известный технический долг (21 пункт) |
| `docs/05_optimization_roadmap.md` | Перед добавлением фич: план развития, приоритеты, чтобы не конфликтовать с ним |
| `docs/06_frontend_bootstrap_analysis.md` | Перед изменением шаблонов/frontend-части |
| `docs/07_authorization_report.md` | Перед изменением авторизации и ролевого доступа |

Документация на русском языке и актуальна. При существенных изменениях кода обновляйте соответствующие файлы в `docs/`.

## Структура проекта

```
fastapi-application/          # рабочая директория для запуска (cwd!)
├── main.py                    # ASGI-приложение `main_app` (импорт: from main import main_app)
├── create_fastapi_app.py      # фабрика create_app(): lifespan, middleware, admin, docs
├── run_main.py / run          # production-запуск через Gunicorn
├── core/
│   ├── config.py              # Settings (pydantic-settings), префикс APP_CONFIG__, вложенность через __
│   ├── models/                # SQLAlchemy: Base, db_helper, User, AccessToken, mixins
│   ├── schemas/user.py        # Pydantic DTO: UserRead, UserCreate, UserUpdate
│   ├── authentication/        # fastapi_users инстанс, UserManager (хуки), transport (Cookie)
│   └── gunicorn/              # адаптер FastAPI → Gunicorn
├── api/
│   ├── dependencies/authentication/   # DI-цепочка: users_db → user_manager → strategy → backend
│   └── api_v1/                # роутеры: auth, users, messages, service
├── views/                     # Jinja2-страницы /home, /verify-email
├── middlewares/               # CORS, process-time, логирование, счётчик запросов
├── admin/                     # SQLAdmin ModelViews
├── mailing/                   # отправка email (SMTP localhost:1025)
├── utils/webhooks/            # исходящие вебхуки (aiohttp)
├── actions/                   # CLI: create_superuser
├── alembic/                   # миграции
└── templates/                 # Jinja2-шаблоны (страницы + email)
```

## Команды

```shell
# Инфраструктура (PostgreSQL 17, Redis 8, Maildev)
docker compose up -d

# Все команды запускаются из fastapi-application/
cd fastapi-application

# Dev-запуск (uvicorn, reload)
uv run python main.py

# Production-запуск (gunicorn)
uv run python run_main.py
# или: gunicorn main:main_app --workers 4 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000

# Миграции
uv run alembic upgrade head

# Суперпользователь (env DEFAULT_EMAIL / DEFAULT_PASSWORD)
uv run python -m actions.create_superuser

# Линтинг / форматирование
uv run ruff check .
uv run ruff format .
uv run black .
```

**Тестов в проекте нет** (pytest не подключён) — проверяйте изменения запуском приложения и ручными запросами.

## Ключевые конвенции и паттерны

1. **Dependency Injection** — центральный паттерн. Ресурсы предоставляются цепочкой async-генераторов `Depends`:
   `db_helper.session_getter → get_users_db → get_user_manager → get_access_tokens_db → get_database_strategy → authentication_backend`. Новые зависимости добавляйте в `api/dependencies/`.
2. **Конфигурация** — только через `core/config.py` (`Settings`). Префикс `APP_CONFIG__`, вложенность через `__` (пример: `APP_CONFIG__DB__URL`). Обязательные поля без дефолтов: `db.url`, оба token-secret.
3. **Синглтоны**: `settings`, `db_helper`, `templates` (`jinja_templates.py`), dispatch счётчика запросов.
4. **Хуки UserManager** (`core/authentication/user_manager.py`): `on_after_register`, `on_after_request_verify`, `on_after_verify`, `on_after_forgot_password`. Побочные эффекты (email, вебхуки, инвалидация кэша) — через `BackgroundTasks`.
5. **Кэш**: `@cache(expire=60, namespace="users-list")` на `GET /api/v1/users`; инвалидация — `FastAPICache.clear(namespace="users-list")` в `on_after_register`.
6. **Ответы** — `ORJSONResponse` по умолчанию (default_response_class).
7. **Стиль кода**: ruff + black, line-length **120**. Игнорируемые правила ruff: F401, E402, F541 (см. `pyproject.toml`). Современные идиомы Python 3.12: `type X = ...`, `Annotated[]` для зависимостей, `X | None` вместо `Optional[X]`.
8. **Модели**: наследование `Base` + `IdIntPkMixin`; авто-имена таблиц camelCase → snake_case.
9. **Миграции**: Alembic (async env). Существующие миграции написаны вручную — при изменении моделей генерируйте новые миграции, не редактируйте старые.

## Известный технический долг (не «чинить» молча)

Полный список — в `docs/04_code_quality.md`. Критичные пункты, о которых нужно помнить при работе рядом с этими местами:

- Redis-клиент в `lifespan` не закрывается (нет `await redis.aclose()`) — `create_fastapi_app.py`
- Хардкод: SMTP (`mailing/send_email.py`), webhook URL (`utils/webhooks/user.py`), CORS (`middlewares/middlewares.py`), cookie-параметры (`core/authentication/transport.py`)
- Счётчик запросов in-memory — некорректен при нескольких воркерах
- Токены сброса пароля логируются в warning (`user_manager.py`)
- Дефолтные креды суперпользователя в `actions/create_superuser.py`
- Дублирующие process-time middlewares

Если задача явно не требует — не переписывайте эти места без спроса. Дорожная карта приоритетов — в `docs/05_optimization_roadmap.md`.

## Правила для агентов

- **Читай `docs/` перед изменениями** — там описаны потоки данных, DI-цепочки и причины текущих решений.
- **Минимальные изменения**: не рефакторьте то, что не относится к задаче; не меняйте существующую логику и тестовое поведение.
- **Обновляйте документацию**: при изменении структуры, роутов, конфигурации или архитектуры — синхронизируйте соответствующий файл в `docs/`.
- **Не запускайте** `git commit`/`push` без явного запроса пользователя.
- **Комментарии в коде** — на английском (как в существующем коде).
- **Запуск**: всегда с `workdir = fastapi-application/` (относительные пути, `.env`, шаблоны рассчитаны на это).
- **Инфраструктура**: PostgreSQL/Redis/Maildev поднимаются только через `docker compose up -d`; не устанавливайте ничего вне виртуального окружения (`uv`).
