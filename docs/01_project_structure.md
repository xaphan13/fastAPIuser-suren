# 01 — Карта проекта

## Назначение проекта

`fastAPIuser-suren` — серверное веб-приложение на **FastAPI** (Python ≥ 3.12), реализующее подсистему управления пользователями: регистрация, аутентификация (cookie-based с БД-стратегией токенов), верификация email, сброс пароля, ролевой доступ (user / superuser), кэширование списка пользователей в Redis, HTML-страницы (Jinja2) для домашних и верификационных экранов, email-уведомления (aiosmtplib), исходящие вебхуки (aiohttp) и административная панель (SQLAdmin).

Архитектура — **слоистый монолит** с чётким разделением: конфигурация, модели данных, аутентификация, API-роутеры, представления (views), middleware, инфраструктура (почта, вебхуки, кэш). Проект построен поверх библиотеки [`fastapi-users`](https://github.com/fastapi-users/fastapi-users) и базового шаблона [FastAPI-base-app](https://github.com/mahenzon/FastAPI-base-app).

---

## Дерево директорий и ключевых файлов

```
fastAPIuser-suren/                       # Корень репозитория
├── .python-version                      # Версия Python: 3.12
├── .gitignore
├── pyproject.toml                       # Метаданные проекта, зависимости, конфиг ruff/black
├── docker-compose.yml                   # Инфраструктура: PostgreSQL 17, Redis 8, Maildev
├── README.md                            # Краткая инструкция по запуску
├── docs/                                # Документация (этот каталог)
│
└── fastapi-application/                 # Рабочая директория приложения (cwd для запуска)
    ├── .env.template                    # Шаблон переменных окружения (APP_CONFIG__*)
    ├── alembic.ini                      # Конфигурация Alembic (миграции)
    ├── run                              # Точка входа: python-скрипт → run_main.main()
    ├── run_main.py                      # Запуск через Gunicorn (production-режим)
    ├── main.py                          # Создание ASGI-приложения `main_app`, подключение роутеров
    ├── create_fastapi_app.py            # Фабрика приложения: lifespan, middleware, admin, docs
    ├── errors_handlers.py               # Глобальные exception handlers (ValidationError, DatabaseError)
    ├── jinja_templates.py               # Singleton `Jinja2Templates` (каталог `templates/`)
    │
    ├── core/                            # Ядро: конфигурация, модели, аутентификация, gunicorn
    │   ├── __init__.py
    │   ├── config.py                    # `Settings` (pydantic-settings): БД, Redis, кэш, токены, логирование
    │   │
    │   ├── models/                      # SQLAlchemy-модели и DB-хелпер
    │   │   ├── __init__.py              # Реэкспорт: AccessToken, Base, User, db_helper
    │   │   ├── base.py                  # `Base` (DeclarativeBase) с auto-tablename (camelCase → snake_case)
    │   │   ├── db_helper.py             # `DatabaseHelper`: async engine, session_factory, session_getter
    │   │   ├── user.py                  # `User` + кастомный `SQLAlchemyUserDatabase.get_users()`
    │   │   ├── access_token.py          # `AccessToken` (токен авторизации в БД)
    │   │   └── mixins/
    │   │       ├── __init__.py
    │   │       └── id_int_pk.py         # `IdIntPkMixin` — примесь: автоинкрементный PK `id`
    │   │
    │   ├── schemas/                     # Pydantic-схемы (DTO)
    │   │   ├── __init__.py
    │   │   └── user.py                  # UserRead, UserCreate, UserUpdate, UserRegisteredNotification
    │   │
    │   ├── types/                       # Псевдонимы типов
    │   │   ├── __init__.py
    │   │   └── user_id.py               # `UserIdType = int`
    │   │
    │   ├── authentication/              # Конфигурация fastapi-users
    │   │   ├── __init__.py
    │   │   ├── fastapi_users.py         # `FastAPIUsers`-инстанс, зависимости current_active_user
    │   │   ├── user_manager.py          # `UserManager`: хуки on_after_register/verify/forgot_password
    │   │   └── transport.py             # Bearer / Cookie транспорты (активен Cookie)
    │   │
    │   └── gunicorn/                    # Обёртка Gunicorn для production
    │       ├── __init__.py              # Реэкспорт: Application, get_app_options
    │       ├── application.py           # `Application(BaseApplication)` — адаптер FastAPI → Gunicorn
    │       ├── app_options.py           # `get_app_options()` — dict-конфиг (bind, workers, timeout…)
    │       └── logger.py                # `GunicornLogger` — кастомный формат логов
    │
    ├── api/                             # API-слой
    │   ├── __init__.py                  # Корневой роутер с prefix `/api`
    │   ├── webhooks/                    # OpenAPI webhooks (декларативные, не HTTP-роуты)
    │   │   ├── __init__.py              # `webhooks_router`
    │   │   └── user.py                  # Webhook `user-created` (схема UserRegisteredNotification)
    │   ├── dependencies/               # FastAPI-зависимости (Depends)
    │   │   ├── __init__.py
    │   │   └── authentication/          # DI-провайдеры для аутентификации
    │   │       ├── __init__.py          # Реэкспорт всех провайдеров
    │   │       ├── users.py             # `get_users_db` — сессия → SQLAlchemyUserDatabase
    │   │       ├── access_tokens.py     # `get_access_tokens_db` — сессия → AccessTokenDatabase
    │   │       ├── user_manager.py      # `get_user_manager` — UserManager с BackgroundTasks
    │   │       ├── strategy.py          # `get_database_strategy` — DatabaseStrategy (lifetime из config)
    │   │       └── backend.py           # `authentication_backend` — Cookie + DB-strategy
    │   └── api_v1/                      # Версионированный API v1 (prefix `/api/v1`)
    │       ├── __init__.py              # Роутер v1, HTTPBearer-зависимость
    │       ├── auth.py                  # Роуты: /login, /logout, /register, /verify, /forgot-password
    │       ├── users.py                 # GET /users (кэшированный, 60s) + /users/me, /users/{id}
    │       ├── messages.py              # Demo-эндпоинты: /messages, /messages/error, /messages/secrets
    │       └── service.py               # GET /service/stats — статистика запросов из middleware
    │
    ├── views/                           # HTML-представления (Jinja2)
    │   ├── __init__.py                  # `router` — объединяет home + verification
    │   ├── home.py                      # GET /home/ — страница пользователя (требует active user)
    │   └── verification.py              # GET /verify-email/ — JS-страница верификации токена
    │
    ├── middlewares/                     # HTTP-middleware
    │   ├── __init__.py                  # Реэкспорт register_middlewares + dispatch-объект
    │   ├── middlewares.py               # CORS, X-Process-Time, логирование, регистрация
    │   └── requests_count_middleware.py # Подсчёт запросов по путям (in-memory, dataclass)
    │
    ├── admin/                           # SQLAdmin-панель
    │   ├── __init__.py                  # `register_admin_views(admin)`
    │   ├── user.py                      # `UserAdmin` — ModelView для User (хэширование пароля)
    │   ├── access_token.py              # `AccessTokenAdmin` — ModelView (авто-генерация токена)
    │   └── converter.py                 # `ModelConverter` — конвертер TIMESTAMPAware → DateTimeField
    │
    ├── mailing/                         # Асинхронная отправка email (aiosmtplib)
    │   ├── __init__.py
    │   ├── send_email.py                # `send_email()` — базовая функция (SMTP localhost:1025)
    │   ├── send_verification_email.py   # Рендер verification-request.html → отправка
    │   └── send_email_confirmed.py      # Рендер email-verified.html → отправка
    │
    ├── utils/                           # Утилиты
    │   ├── __init__.py                  # Реэкспорт camel_case_to_snake_case
    │   ├── case_converter.py            # `camel_case_to_snake_case()` для авто-имён таблиц
    │   └── webhooks/
    │       ├── __init__.py
    │       └── user.py                  # `send_new_user_notification()` — POST вебхук (aiohttp)
    │
    ├── actions/                         # CLI-скрипты
    │   ├── __init__.py
    │   └── create_superuser.py          # Скрипт создания суперпользователя (env DEFAULT_EMAIL/PASSWORD)
    │
    ├── alembic/                         # Миграции БД
    │   ├── env.py                       # Async-окружение Alembic (async_engine_from_config)
    │   └── versions/
    │       ├── 2024_05_10_1954-…_create_users_table.py
    │       └── 2024_05_10_2013-…_create_access_tokens_table.py
    │
    └── templates/                       # Jinja2-шаблоны
        ├── base.html                    # Базовый layout (Bootstrap 5 CDN)
        ├── home.html                    # Страница пользователя + JS-запрос верификации
        ├── verification.html            # JS-страница: POST verify-токена
        └── mailing/
            ├── base.html                # Базовый layout для email
            └── email-verify/
                ├── verification-request.html
                └── email-verified.html
```

---

## Внешние зависимости и их роль

| Зависимость | Роль в проекте | Файл конфигурации |
|---|---|---|
| **PostgreSQL 17** | Основная БД. Хранит таблицы `users` и `access_tokens`. Доступ через `asyncpg`. | `docker-compose.yml`, `core/config.py` → `DatabaseConfig` |
| **Redis 8** | Backend для кэширования (`fastapi-cache2` + `RedisBackend`). Кэш списка пользователей (TTL 60s). | `docker-compose.yml`, `core/config.py` → `RedisConfig` |
| **Maildev** | Локальный SMTP-сервер + web-интерфейс для разработки email. Порт SMTP 1025, web 8080. | `docker-compose.yml`, `mailing/send_email.py` |
| **httpbin.org** | Внешний endpoint для отправки вебхука о создании пользователя (demo). | `utils/webhooks/user.py` → `WEBHOOK_URL` |
| **unpkg.com (CDN)** | Swagger UI / ReDoc JS и CSS для кастомных docs-роутов. | `create_fastapi_app.py` → `register_static_docs_routes` |

### Python-зависимости (`pyproject.toml`)

| Пакет | Назначение |
|---|---|
| `fastapi` | Веб-фреймворк (ASGI) |
| `uvicorn[standard]` | ASGI-сервер (dev-режим и как Gunicorn worker) |
| `gunicorn` | WSGI/ASGI-менеджер процессов (production) |
| `pydantic[email]` | Валидация данных, email-тип |
| `pydantic-settings` | Конфигурация из `.env` с вложенным делимитером `__` |
| `sqlalchemy[asyncio]` | ORM, async-движок |
| `asyncpg` | PostgreSQL DBAPI-драйвер |
| `alembic` | Миграции схемы БД |
| `fastapi-users[sqlalchemy]` | Подсистема аутентификации пользователей |
| `aiohttp` | HTTP-клиент для исходящих вебхуков |
| `orjson` | Быстрый JSON-сериализатор (ORJSONResponse по умолчанию) |
| `jinja2` | HTML-шаблоны (страницы + email) |
| `aiosmtplib` | Асинхронная отправка email |
| `sqladmin[full]` | Административная панель |
| `fastapi-cache2` | Декоратор `@cache` для кэширования эндпоинтов |
| `redis` | Async Redis-клиент (backend для кэша) |
| `ruff`, `black` | Линтинг и форматирование |
