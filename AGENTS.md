# AGENTS.md — fastAPIuser-suren (агентный режим)

Контекст-инструкция для AI-агентов, работающих с кодом в этом репозитории, плюс
правила команды агентов (раздел «Агентный режим» в конце файла). `QWEN.md`
содержит тот же проектный контекст и инструкции оркестратора для главной сессии
Qwen Code — проектные части обоих файлов держите синхронными. Текущее задание
команды — `tasks/current/REQUIREMENTS.md`.

## Обзор проекта

Серверное веб-приложение на **FastAPI 0.111+ / Python 3.12** — слоистый монолит
для подсистемы управления пользователями поверх [`fastapi-users`](https://github.com/fastapi-users/fastapi-users)
и шаблона [FastAPI-base-app](https://github.com/mahenzon/FastAPI-base-app). Три
части:

1. **Аутентификация и пользователи** — `fastapi-users` с cookie-transport и
   БД-стратегией токенов: регистрация, вход/выход, верификация email, сброс
   пароля, ролевой доступ (`is_active` / `is_superuser` / `is_verified`).
2. **Кэш + админка + сервис** — `fastapi-cache2` поверх Redis для списка
   пользователей; `sqladmin` под `/admin` для `User` и `AccessToken`;
   `GET /api/v1/service/stats` отдаёт счётчик запросов из middleware.
3. **HTML и почта** — Jinja2-страницы `/home/` и `/verify-email/` (Bootstrap 5
   с CDN); email-уведомления через `aiosmtplib` (SMTP → `maildev` локально) с
   Jinja2-шаблонами писем; исходящий webhook о регистрации через `aiohttp`;
   входящий webhook `POST /webhooks/user-created` (объявлен в фабрике, роут
   не зарегистрирован — см. [docs/04_code_quality.md](docs/04_code_quality.md)).

Дублирования маршрутов и обработчиков **нет** — проект не учебный, это
функциональный каркас. Изучать построчно сравнивая — нечего; сравнивать
есть что с fastapi-users/sqladmin.

**Стек**

| Область | Выбор |
|---|---|
| Язык | Python 3.12 (`.python-version`) |
| Менеджер пакетов | `uv` (`uv.lock` — единственный источник истины) |
| Веб-фреймворк | FastAPI 0.111+ (ORJSONResponse по умолчанию) |
| Валидация / конфигурация | Pydantic 2 + pydantic-settings (префикс `APP_CONFIG__`, разделитель `__`) |
| ORM | SQLAlchemy 2.0 async (`asyncpg`) |
| Миграции | Alembic (асинхронный `env.py`) |
| Аутентификация | `fastapi-users[sqlalchemy]` 14.x (cookie-transport, БД-стратегия токенов) |
| Админка | `sqladmin[full]` (mount `/admin`) |
| Кэш | `fastapi-cache2` + Redis 8 |
| Шаблоны | Jinja2 (`jinja_templates.py` → `templates/`) |
| Email | `aiosmtplib` 4.x (SMTP → `maildev` локально) |
| Вебхуки (исходящие) | `aiohttp` |
| ASGI-сервер | uvicorn (dev), gunicorn + UvicornWorker (multi-worker) |
| Сериализация | orjson |
| Линтеры | ruff 0.14+ + black 25+ (объявлены в зависимостях) |

**В проекте нет тестов** — изменения проверяются запуском приложения и curl.

### Архитектура

`fastapi-application/create_fastapi_app.py` — фабрика `create_app(create_custom_static_urls=True)`:
`lifespan` поднимает Redis-бэкенд и инициализирует `FastAPICache`; `register_static_docs_routes`
регистрирует кастомные `/docs`/`/redoc` (CDN `unpkg`); `register_middlewares` —
CORS + `X-Process-Time` + лог-запросов + `requests_count_middleware_dispatch`;
создаётся `Admin(app, session_maker=db_helper.session_factory)` и подключаются
view-классы из `admin/`. `main.py` собирает `main_app`, подключает
`api/__init__.py::router` (prefix `/api`, дальше `/v1/{auth,users,messages,service}`)
и `views/__init__.py::router` (`/home`, `/verify-email`). Плюс mount
`/admin` (sqladmin) и вебхук `POST /webhooks/user-created` — он объявлен через
`webhooks=webhooks_router` в фабрике, но **сам `webhooks_router` в `main.py` не
включён** (см. [docs/04_code_quality.md](docs/04_code_quality.md)).

| Роутер | Модуль | Префикс | Что внутри |
|---|---|---|---|
| `router` (api) | `api/__init__.py` | `/api/v1` | `auth/` (login/logout/register/request-verify-token/verify/forgot-password/reset-password), `users/` (список + `/{id}` + `/me`), `messages/` (`/`, `/secrets`, `/error`), `service/` (`/stats`) |
| `router` (views) | `views/__init__.py` | `/home`, `/verify-email` | Jinja2: `home.html` (информация о пользователе + Verify-кнопка), `verification.html` (страница-обработчик токена) |
| `webhooks_router` | `api/webhooks/user.py` | `/webhooks/user-created` | **в `main.py` не подключён** — только объявлен в фабрике |
| `Admin` | `admin/__init__.py` | `/admin` | sqladmin: `UserAdmin` (с хешированием пароля при редактировании), `AccessTokenAdmin` (с автогенерацией токена) |

Итого **7 route-объектов**: 1 `Route` (`/openapi.json`) + 3 `APIRoute` служебных
(`/docs`, `/docs/oauth2-redirect`, `/redoc`) + 1 `Mount` (`/admin`) + 2
`_IncludedRouter` (`/api/v1`, `/home`+`/verify-email`). Проверка счётчика:
`cd fastapi-application && ../.venv/bin/python -c "from main import main_app; print(len(main_app.routes))"` → `7`.

```
fastAPIuser-suren/                          # корень репозитория; здесь запускается qwen-code
├── QWEN.md AGENTS.md README.md             # контекст + правила команды (этот комплект)
├── tasks/                                  # задания команды: current/ — живое, NNN-<slug>/ — архив (создаётся по первому заданию)
├── .qwen/agents/                           # субагенты: spec-writer, frontend-dev, backend-dev, qa, adversary
├── docs/                                   # подробная документация по проекту (8 файлов, рус.)
├── docker-compose.yml                      # инфраструктура: pg + redis + maildev
├── pyproject.toml uv.lock                  # зависимости (uv) + конфиг ruff/black
│
└── fastapi-application/                    # корень Python-приложения (= BASE_DIR)
    ├── main.py                             # main_app: create_app(...) + include_router(api, views)
    ├── run_main.py                         # точка входа gunicorn (использует main_app)
    ├── run                                 # python-скрипт → run_main.main()
    ├── create_fastapi_app.py               # фабрика create_app(): lifespan, middleware, admin, docs
    ├── errors_handlers.py                  # глобальные хендлеры ValidationError / DatabaseError
    ├── jinja_templates.py                  # singleton Jinja2Templates(directory=BASE_DIR/templates)
    ├── .env.template                       # шаблон APP_CONFIG__* (закоммичен, без секретов)
    ├── alembic.ini                         # конфиг Alembic
    │
    ├── core/                               # конфиг, модели, схемы, типы, аутентификация, gunicorn
    │   ├── config.py                       # Settings (pydantic-settings), BASE_DIR
    │   ├── models/                         # Base, db_helper, User, AccessToken, mixins
    │   ├── schemas/user.py                 # UserRead, UserCreate, UserUpdate, UserRegisteredNotification
    │   ├── types/user_id.py                # UserIdType = int
    │   ├── authentication/                 # FastAPIUsers, UserManager, transport
    │   └── gunicorn/                       # Application, get_app_options, GunicornLogger
    │
    ├── api/                                # JSON API + зависимости
    │   ├── api_v1/                         # auth, users, messages, service
    │   ├── dependencies/authentication/    # backend, strategy, users, access_tokens, user_manager
    │   └── webhooks/user.py                # POST /webhooks/user-created (НЕ подключён в main)
    │
    ├── actions/                            # CLI-скрипты
    │   └── create_superuser.py             # python -m actions.create_superuser
    │
    ├── admin/                              # sqladmin: User, AccessToken, converter (TIMESTAMPAware)
    │
    ├── middlewares/                        # CORS, X-Process-Time, log, requests_count
    │
    ├── views/                              # Jinja2 views (home, verify-email)
    │
    ├── mailing/                            # aiosmtplib: send_email, send_verification_email, send_email_confirmed
    │
    ├── templates/                          # Jinja2: base.html, home.html, verification.html + mailing/
    │
    ├── utils/                              # case_converter (camelCase→snake_case), webhooks/user (исходящий)
    │
    └── alembic/                            # асинхронные миграции (2 ревизии: users, access_tokens)
```

## Документация

В папке [docs/](docs/) — подробная документация (на русском). Сверяйтесь с ней
перед правками:

| Файл | Что внутри |
|---|---|
| [docs/01_project_structure.md](docs/01_project_structure.md) | карта проекта: дерево, зависимости, инварианты окружения |
| [docs/02_architecture.md](docs/02_architecture.md) | архитектура и слои, потоки данных, развёртывание |
| [docs/03_execution_flow.md](docs/03_execution_flow.md) | жизненный цикл, маршруты, ключевые процессы, логирование |
| [docs/04_code_quality.md](docs/04_code_quality.md) | оценка качества кодовой базы, дефекты по критичности |
| [docs/05_optimization_roadmap.md](docs/05_optimization_roadmap.md) | дорожная карта оптимизаций (из анализа качества) |
| [docs/06_frontend_bootstrap_analysis.md](docs/06_frontend_bootstrap_analysis.md) | анализ клиентского слоя (Jinja2 + Bootstrap, без SPA) |
| [docs/07_authorization_report.md](docs/07_authorization_report.md) | отчёт по авторизации: модель, потоки, грабли |
| [docs/08_authentication_guide.md](docs/08_authentication_guide.md) | пошаговое руководство по аутентификации через fastapi-users |

## Индекс кодовой базы

Для структурных запросов по коду (кто вызывает функцию, что она вызывает,
мёртвый код, анализ влияния изменений) используйте графовый индекс через
**codebase-memory-mcp** — это быстрее и точнее, чем обход исходников вручную.
Скилл `codebase-memory` описывает доступные MCP-инструменты (`search_graph`,
`trace_path`, `detect_changes` и др.). Перед структурным исследованием
проверяйте наличие/свежесть индекса через `index_status`.

## Сборка и запуск

### Настройка

```bash
uv sync                      # создаёт .venv по uv.lock
docker compose up -d         # pg + redis + maildev
```

`.env` создаётся вручную рядом с `.env.template` (в `fastapi-application/`).
Обязательные поля: `APP_CONFIG__DB__URL` (по умолчанию из шаблона),
`APP_CONFIG__ACCESS_TOKEN__RESET_PASSWORD_TOKEN_SECRET`,
`APP_CONFIG__ACCESS_TOKEN__VERIFICATION_TOKEN_SECRET`.

### Локальный запуск

```bash
cd fastapi-application
../.venv/bin/alembic upgrade heads            # миграции (cwd обязателен)
../.venv/bin/uvicorn main:main_app --host 0.0.0.0 --port 8000 --reload   # dev (предпочтительно)
../.venv/bin/python main.py                  # dev + баннер в лог
../.venv/bin/python run                      # gunicorn (прод; см. run_main.py)
../.venv/bin/python -m actions.create_superuser   # CLI: суперюзер
```

**Плоские импорты.** Приложение не устанавливается как пакет
(`pyproject.toml`: `package = false`). Все импорты `from core.config import …`
работают только если `fastapi-application/` — текущий каталог. `BASE_DIR` в
`core/config.py` всегда указывает на `fastapi-application/`, поэтому лог-файл
и `.env.template` он найдёт независимо от cwd; но **Alembic требует cwd =
`fastapi-application/`** — иначе `from core.config import settings` в
`alembic/env.py` не найдёт модуль.

Multi-worker (gunicorn): `python run` запускает `run_main.py::main()`, который
читает `settings.gunicorn.{host,port,timeout,workers,log_level}`.

### Линтеры и форматирование

```bash
uv run ruff check .
uv run ruff format .     # либо: uv run black .
```

ruff игнорирует `F401` (неиспользуемые импорты), `E402` (импорт не в начале
файла) и `F541` (f-строка без подстановок) — эти исключения заданы в
`pyproject.toml` и несут смысловую нагрузку: код осознанно импортирует
`UserManager` через `TYPE_CHECKING` и `core/__init__.py` реэкспортирует имена
(`Base`, `db_helper`, `User`, `AccessToken`). Не «исправляйте» их.

Длина строки в `pyproject.toml`: ruff 120, black 120; отступ 4 пробела.

### Проверка работоспособности

Тестов нет, поэтому изменения проверяются запуском самого приложения:

```bash
cd fastapi-application && ../.venv/bin/python -c "from main import main_app; print(len(main_app.routes))"   # ожидается 7
../.venv/bin/uvicorn main:main_app --port 8000    # затем curl:
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/docs
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/admin/login
curl -s -X POST http://127.0.0.1:8000/api/v1/auth/register \
     -H "Content-Type: application/json" \
     -d '{"email":"u@example.com","password":"strongpass","is_active":true,"is_superuser":false,"is_verified":false}'
curl -s http://127.0.0.1:8000/api/v1/service/stats
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/home/   # 401 без cookie, 200 c активным пользователем
```

Не утверждайте, что изменение проверено, без фактического запуска. Если
проверить невозможно — сообщите об этом прямо.

## Соглашения разработки

### Стиль кода

- Длина строки: **ruff 120**, black 120; отступ 4 пробела (`pyproject.toml`).
- ruff игнорирует `F401`, `E402`, `F541` (см. выше). Не «исправляйте».
- Крупные декоративные комментарии-разделители (`# ====`, `# ----`, `#***`)
  разделяют логические секции. Соблюдайте локальный стиль файла при правках,
  не удаляйте их.
- Русский язык используется для комментариев, docstring'ов и документации.
  Новый текст и комментарии пишите на том же языке, что и окружающий файл.

### Паттерн модуля роутера

- **Импорты плоские, не пакетные**: `from core.config import settings`, а не
  `from fastapi-application.core...`. Приложение не устанавливается как пакет —
  любой запуск (uvicorn, alembic, `python -c`) выполняется с cwd или `--app-dir`
  = `fastapi-application/`, где эти модули лежат в корне `sys.path`.
- Объект `APIRouter` объявляется на уровне модуля с `prefix=settings.api...` и
  `tags=[...]`; включение вложенных роутеров — в `__init__.py` своей папки.
- Сессия БД — через `db_helper.session_getter` (DI через
  `Depends(db_helper.session_getter)` в `api/dependencies/authentication/{users,access_tokens}.py`).
- Логирование — стандартный `logging` (имя логгера = `__name__`,
  `logging.basicConfig` настраивается в `main.py` по `settings.logging`).

### Конфигурация

- Весь конфиг — вложенные pydantic-модели в `core/config.py`, читаются из
  env-файлов с префиксом `APP_CONFIG__` и разделителем `__`. Обязательные
  поля: `db.url`, `access_token.reset_password_token_secret`,
  `access_token.verification_token_secret`.
- **Один источник истины для секретов токенов**: переменные
  `APP_CONFIG__ACCESS_TOKEN__RESET_PASSWORD_TOKEN_SECRET` и
  `APP_CONFIG__ACCESS_TOKEN__VERIFICATION_TOKEN_SECRET` объявлены обязательными
  в `core/config.py::AccessToken`. Если они не заданы — приложение не стартует
  на импорте `main`. Захардкоженный fallback запрещён.
- Новые настройки добавляйте как поля соответствующей вложенной модели с
  дефолтом, а не читайте `os.environ` напрямую.

### Модели и схемы

- SQLAlchemy 2.0-стиль: `Mapped[]` + `mapped_column`, общий `Base`
  (`core/models/base.py`) с auto-tablename (`camelCase → snake_case` +
  суффикс `s`).
- `IdIntPkMixin` (`core/models/mixins/id_int_pk.py`) — общий авто-PK
  `id INTEGER`. Используется в `User` и `AccessToken` (там PK — `token`, а
  `id` нет вообще).
- Все модели обязательно реэкспортируются в `core/models/__init__.py`:
  `Base`, `db_helper`, `User`, `AccessToken`. Именно этот импорт наполняет
  `Base.metadata` для Alembic `--autogenerate`.
- Pydantic-схемы — `core/schemas/user.py` (рядом с `core/models/`):
  `UserRead`, `UserCreate`, `UserUpdate` (наследники
  `fastapi_users.schemas.BaseUser*`), плюс `UserRegisteredNotification` для
  вебхука.

### Аутентификация

- `fastapi-users[sqlalchemy]` настраивается в два слоя:
  - ядро (`core/authentication/`): `FastAPIUsers[User, UserIdType]`,
    `UserManager` с хуками `on_after_register` / `on_after_request_verify` /
    `on_after_verify` / `on_after_forgot_password`, `transport.py` (cookie
    активно, bearer закомментирован).
  - зависимости (`api/dependencies/authentication/`): `authentication_backend`,
    `get_database_strategy`, `get_users_db`, `get_access_tokens_db`,
    `get_user_manager` — каждая через `Depends(db_helper.session_getter)`.
- `current_active_user`, `current_active_superuser` — алиасы из
  `core/authentication/fastapi_users.py`.
- Cookie-transport: `cookie_max_age=3600` (1 час, **захардкожено** в
  `core/authentication/transport.py` — TODO: перенести в `Settings`),
  `cookie_secure=False` (для dev). См. [docs/04_code_quality.md](docs/04_code_quality.md).
- Email-уведомления идут через `BackgroundTasks.add_task` в хуках
  `UserManager` (`send_verification_email`, `send_email_confirmed`,
  `FastAPICache.clear`, `send_new_user_notification`).

## Грабли — сверьтесь с этим списком перед отладкой

### Запуск и окружение

- **Плоские импорты.** `from core.config import settings` работает только
  если `fastapi-application/` в `sys.path` (cwd или `--app-dir`). Иначе —
  `ModuleNotFoundError`. Alembic и uvicorn должны запускаться из
  `fastapi-application/`.
- **Побочные эффекты на импорте.** `main.py` при импорте:
  (1) поднимает `logging.basicConfig` по `settings.logging`;
  (2) импортирует `from api import router` (тот импортирует `core.config`);
  (3) вызывает `create_app(...)` — создаёт SQLAlchemy-движок, Admin, Redis-клиент
  в `lifespan`. Любой сбой конфигурации (например, отсутствие
  `APP_CONFIG__ACCESS_TOKEN__VERIFICATION_TOKEN_SECRET`) ловится здесь же.
- **Секреты токенов обязательны.** Без `RESET_PASSWORD_TOKEN_SECRET` и
  `VERIFICATION_TOKEN_SECRET` в `.env` приложение не стартует. Это сделано
  намеренно: захардкоженный fallback в проде — дыра.
- **Cookie `secure=False`.** `core/authentication/transport.py` жёстко задаёт
  `cookie_secure=False` — для прода нужно поднять до `True` за reverse-proxy
  с TLS, иначе токены уходят по HTTP. См. [docs/04_code_quality.md](docs/04_code_quality.md).

### Известные дефекты (из docs/04_code_quality.md) — не «исправляйте» без отдельного задания

- Входящий webhook `POST /webhooks/user-created` объявлен в фабрике через
  `webhooks=webhooks_router`, но `webhooks_router` в `main.py` не подключён —
  эндпоинт не отвечает.
- `cookie_secure=False` и `cookie_max_age=3600` захардкожены в
  `core/authentication/transport.py`, минуя `Settings`.
- `utils/case_converter.py` импортируется как `from utils import camel_case_to_snake_case`
  в `core/models/base.py` — создаёт циклический риск: при импорте модели
  подтягивается `utils`, при импорте `utils` (внутри пайплайна) подтягивается
  вся `core/models`. Сейчас работает, но хрупко.
- `core/authentication/transport.py` экспортирует и `bearer_transport`, и
  `cookie_transport`, но активен только cookie; `bearer_transport` — мёртвый
  код на случай переключения.
- `CookieTransport.cookie_name` не задан — берётся дефолт `"fastapiusersauth"`.
  Для прода стоит зафиксировать имя.

### Docker

- `docker-compose.yml` — инфраструктура (pg 5432 + redis 6379 + maildev 1025/1080),
  креды `user/password`, база `shop` — учебный проект, секреты закоммичены.
- Приложение само в compose не входит — запускается локально/gunicorn и
  подключается к этим сервисам по `localhost`. Для внешнего HTTP нужен свой
  reverse-proxy (nginx/caddy) — в репо его нет.

## Git

Ветка на момент написания: `new-docs`. Заголовки коммитов короткие и в нижнем
регистре (`rename project`, `ruff format and check`, `added new docs`,
`first start agents mode`). Держитесь той же лаконичности. Учтите, что
`__pycache__/`, `*.py[cod]`, `*.log`, `uv.lock` (несмотря на `uv.lock` в
зависимостях — он в `.gitignore`!), `.venv/`, `.env`, `.idea/`, `.vscode/`,
`logs/` находятся в `.gitignore` — никогда не добавляйте их. Индексируйте
только файлы, относящиеся к изменению.

> В репо **нет** `Makefile`, `nginx_pg_admin.yml`, `frontend/`, `md_articles/`,
> `static/`, `db_core/`, `ex_user_post/`, `ex_order_product/`, `tasks/` —
> всё это из предыдущего проекта-шаблона. Не добавляйте упоминания этих путей
> в новый код или доки. Если задание требует, например, статики — обсудите
> с оркестратором.

---

## Агентный режим

Эти правила применяются к каждому агенту команды, работающему над заданием из
`tasks/current/REQUIREMENTS.md`. Оркестратор — главная сессия Qwen Code
(инструкции в [QWEN.md](QWEN.md)). При сомнениях главенствует текущее
задание, затем проектные соглашения выше.

### Жизненный цикл заданий

- Текущее задание живёт в `tasks/current/REQUIREMENTS.md`; в корне проекта
  файлов заданий нет. Все рабочие артефакты живого задания создаются в той
  же папке `tasks/current/`: `DEFECTS.md` (если qa найдёт дефекты),
  `ADVERSARIAL_REVIEW.md`, `e2e/`, `screenshots/`, `dev/` (прогресс-файлы
  и сырые выводы разработчиков).
- Папки `tasks/` в репо ещё нет — она появляется, когда пользователь кладёт
  первое задание. До этого оркестратор работает по QWEN.md, но `tasks/current/`
  не существует.
- У задания две фазы жизни: **создание** и **исполнение**. Создание:
  оркестратор запускает скилл `task-spec` и субагента `spec-writer` — сырая
  идея пользователя превращается в полный REQUIREMENTS.md с планом фаз
  (шаблон — `.qwen/skills/task-spec/TEMPLATE.md`); открытые вопросы
  закрываются с пользователем, план фаз подтверждается, спека замораживается.
  Исполнение: строго по фазам из этого плана — фаза = одно делегирование =
  1–3 файла = бюджет ~10–15 ходов; следующая фаза стартует только после
  зелёного checkpoint и ревью диффа оркестратором. Детали — в скилле
  `task-spec` и в QWEN.md.
- Упавший прогон не возобновляют пересказом истории. Сначала проверить, что
  процесс не остался (`pgrep -af "uvicorn.*main:main_app"`) и мусора нет;
  затем прочитать `tasks/current/dev/phaseNN_progress.md` и `git diff`; затем
  запустить свежий узкий прогон «фаза N: сделано X, доделай Y». Это касается
  и backend-dev, и frontend-dev.
- Когда все критерии успеха подтверждены, оркестратор архивирует задание:
  переименовывает папку `tasks/current/` в `tasks/NNN-<slug>/` (`NNN` —
  следующий порядковый номер от 001, `<slug>` — короткое латинское имя через
  дефис) — так все артефакты переезжают в архив вместе с заданием; в
  `tasks/NNN-<slug>/REQUIREMENTS.md` убирает пометку «Текущее задание» и
  дописывает в конец секцию «Отчёт о выполнении»: дата закрытия, итог,
  изменения, таблица критериев с результатами и ссылками на доказательства,
  дефекты, disposition находок adversary, участники. Шаблон отчёта — в
  QWEN.md. Затем создаёт свежую заглушку `tasks/current/REQUIREMENTS.md`
  «Задания нет», в которую пользователь кладёт новое задание, и цикл
  повторяется тем же составом команды.
- Закрытые задания лежат в `tasks/NNN-<slug>/` — целиком, со всеми
  артефактами (задание + отчёт, ADVERSARIAL_REVIEW.md, DEFECTS.md, e2e/,
  screenshots/); пишет туда только оркестратор.
- Комплект агентного режима переносим: чтобы использовать его в другом
  проекте, достаточно адаптировать проектный контекст в `README.md`,
  `QWEN.md`, `AGENTS.md` и папку `.qwen/`; `tasks/current/REQUIREMENTS.md`
  каждый раз получает новое задание, архив `tasks/` начинается пустым.

### Команда

- **оркестратор** (главная сессия, `QWEN.md`) — планирует, делегирует,
  ревьюит, контролирует критерии успеха. Код не пишет.
- **spec-writer** — отдельная сессия фазы создания задания: исследует зону
  будущего задания и пишет `tasks/current/REQUIREMENTS.md` с планом фаз
  (запускается оркестратором через скилл `task-spec`). Код не пишет.
- **frontend-dev** — клиентский слой. В этом проекте это Jinja2-шаблоны
  (`templates/`, `templates/mailing/`) и встроенный JS на
  `home.html`/`verification.html` (fetch на `/api/v1/auth/...`). Настоящего
  SPA-фронтенда нет.
- **backend-dev** — серверная часть: роуты, схемы, модели, CRUD,
  конфигурация, миграции, sqladmin, mailing, webhooks, middleware.
- **qa** — проверки запуском и curl-сценариями, заметки e2e, реестр
  DEFECTS.md. Код продукта не исправляет.
- **adversary** — пытается сломать изменённую функциональность нешаблонными
  способами; записывает находки в ADVERSARIAL_REVIEW.md.

Определения агентов в `.qwen/agents/` универсальны и переносятся между
проектами без правок: каждый агент первым шагом читает AGENTS.md и
привязывается к проекту таблицей ниже. При переносе агентного режима в
другой проект меняется только эта таблица.

### Зоны и проверки (привязка к этому проекту)

| Агент | Зона (можно редактировать) | Чем проверяет изменения | Особые запреты |
|---|---|---|---|
| `frontend-dev` | `fastapi-application/templates/` (Jinja2: `base.html`, `home.html`, `verification.html`, `mailing/`), встроенный JS внутри шаблонов | `cd fastapi-application && ../.venv/bin/python -c "from main import main_app"` без ошибок импорта; `curl /home/` и `/verify-email/` возвращают 200 (с активной cookie) или 401; скриншот в `tasks/current/screenshots/` | Python-модули — зона backend-dev; ничего не добавлять в `frontend/`, `nginx/web/`, `static/` — этих каталогов нет |
| `backend-dev` | `fastapi-application/` (все Python-модули: `main.py`, `create_fastapi_app.py`, `core/`, `api/`, `actions/`, `admin/`, `middlewares/`, `views/`, `mailing/`, `utils/`, `errors_handlers.py`, `jinja_templates.py`, `alembic/`, `.env.template`); `docker-compose.yml` | `uv run ruff check .`; `cd fastapi-application && ../.venv/bin/python -c "from main import main_app; print(len(main_app.routes))"` (текущее значение: **7**); curl изменённых эндпоинтов на запущенном приложении; `../.venv/bin/alembic upgrade heads` для изменений моделей | `frontend/`, `nginx/web/`, `Makefile`, `nginx_pg_admin.yml` (не создавать, если не было); `docs/`, `AGENTS.md`, `QWEN.md`, `README.md` — зона оркестратора |
| `qa` | `tasks/current/e2e/`, `tasks/current/DEFECTS.md`, `tasks/current/screenshots/` | curl-сценарии из критериев успеха текущего задания; регресс: `/docs`, `/admin/login`, `/api/v1/auth/register` (или login), `/api/v1/service/stats`, `/home/` | любой код продукта |
| `adversary` | `tasks/current/ADVERSARIAL_REVIEW.md`, `tasks/current/screenshots/` | curl по запущенному приложению; логи stdout (формат `settings.logging.log_format`) | всё, кроме своих файлов |
| `spec-writer` | `tasks/current/REQUIREMENTS.md` — только на фазе создания задания, одним `write_file` по шаблону `.qwen/skills/task-spec/TEMPLATE.md` | чек-лист скилла `task-spec` (проверяет оркестратор) | код продукта; всё, кроме REQUIREMENTS.md на фазе создания |

Общее для всех: не редактировать `.qwen/`, `tasks/current/REQUIREMENTS.md`,
папки архивных заданий `tasks/NNN-*`, `AGENTS.md`, `QWEN.md`, `README.md`,
`docs/`, `pyproject.toml` без решения оркестратора; не добавлять зависимости
и тестовые фреймворки без решения оркестратора. Обновление документации в
`docs/` координирует оркестратор. Единственное исключение: `spec-writer` на
фазе создания пишет `tasks/current/REQUIREMENTS.md`; после старта исполнения
файл заморожен для всех, кроме оркестратора.

Границы ролей обеспечиваются системным промптом каждого агента и
конфигурацией инструментов. Не обходите их командами оболочки: если
инструкции говорят, что файл запрещён, не изменяйте его никаким другим
способом.

### Соглашения репозитория агентного режима

- Всё о задании живёт в его папке. Текущее задание — `tasks/current/`
  (контракт `REQUIREMENTS.md` + рабочие артефакты `DEFECTS.md`,
  `ADVERSARIAL_REVIEW.md`, `e2e/`, `screenshots/`, `dev/`); закрытое —
  `tasks/NNN-<slug>/` с тем же набором плюс отчёт. В корне проекта файлов
  заданий нет.
- Проверочные сценарии и доказательства qa живут в `tasks/current/e2e/`
  (скрипты, заметки прогонов с командами и сырыми выводами). Писать туда
  может только qa.
- Прогресс-файлы и сырые выводы разработчиков живут в `tasks/current/dev/`
  (`phaseNN_progress.md` — по одному на фазу, плюс `*.txt` для сырых
  выводов команд). Пишут туда backend-dev и frontend-dev; прогресс-файлы —
  страховка восстановления: по ним свежий прогон продолжает упавшую фазу
  без пересказа истории.
- `tasks/current/DEFECTS.md` ведут qa и оркестратор (см. ниже);
  `tasks/current/ADVERSARIAL_REVIEW.md` — adversary и оркестратор.
- Никаких эмодзи в коде, комментариях и логах.
- Тестовые сервера живут только на время живого задания: субагент поднимает
  сервер по своей спецификации и не глушит поднятый другим (его переиспользуют
  qa/adversary), но все тестовые процессы гасит оркестратор при закрытии
  задания — ни одного оставленного uvicorn после архивирования.
- Новых тяжёлых зависимостей (фреймворки тестов, браузерные драйверы и т.п.)
  не добавлять без явного решения оркестратора, согласованного с
  пользователем: проект живёт без тест-инфраструктуры, и проверки делаются
  запуском приложения и curl.

### DEFECTS.md — реестр дефектов

Все дефекты живут в `tasks/current/DEFECTS.md` (папка текущего задания;
создаётся при первом дефекте), одна запись на дефект, новые сверху. При
архивировании задания файл переезжает в `tasks/NNN-<slug>/` вместе с
папкой. Авторы: **qa** (создание, закрытие, переоткрытие) и **оркестратор**
(фиксация ответов разработчиков, отклонение). Больше никто никогда его не
редактирует.

Формат, точно:

    ## DEF-001: Краткий заголовок

    - Status: OPEN
    - Severity: HIGH | MEDIUM | LOW
    - Found by: qa | adversary (ADV-003)
    - Task: <название текущего задания из tasks/current/REQUIREMENTS.md>

    Steps to reproduce:
    1. Пронумерованные, конкретные, начиная с запуска приложения.

    Expected: Что должно произойти.
    Actual: Что происходит вместо этого.
    Screenshot: tasks/current/screenshots/def-001.png (опционально)

    History:
    - qa: opened

Статусы и кто их устанавливает:

| Статус | Значение | Кто устанавливает |
|---|---|---|
| OPEN | Заведён или переоткрыт после неудачного ретеста | qa |
| FIX-READY | Разработчик сообщил, что исправление внесено | оркестратор, передавая слова разработчика |
| DISPUTED | Разработчик сообщил НЕ ВОСПРОИЗВОДИТСЯ или РАБОТАЕТ КАК ЗАДУМАНО, с причиной | оркестратор, дословно |
| CLOSED | qa перетестировал и подтвердил исправление либо принял спор | только qa |
| REJECTED | Исправляться не будет, с письменной причиной | только оркестратор |

Каждая смена статуса добавляет строку в History с указанием, кто, что и
почему сделал. Дефект не завершён, потому что так сказал разработчик, — он
завершён, когда qa его закрывает.

### ADVERSARIAL_REVIEW.md — находки adversary

Все находки adversary живут в `tasks/current/ADVERSARIAL_REVIEW.md` (папка
текущего задания; создаётся при первом прогоне; при архивировании
переезжает в `tasks/NNN-<slug>/` вместе с папкой). Авторы: **adversary**
(создание записей) и **оркестратор** (заполнение Disposition). Больше
никто.

Формат, точно:

    ## ADV-001: Краткий заголовок

    - Session: <задание> | final
    - Suggested severity: HIGH | MEDIUM | LOW

    What I did: ...
    Expected: ...
    Actual: ...
    Screenshot: tasks/current/screenshots/adv-001.png (опционально)

    Disposition: PENDING

Оркестратор заменяет PENDING на `ACCEPTED -> DEF-NNN` или `REJECTED -
причина`. Принятые находки воспроизводятся и заводятся в DEFECTS.md
силами qa. Когда задание закрыто, ни одна запись не может оставаться
PENDING.
