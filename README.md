# fastAPIuser-suren — агентный режим

Серверное веб-приложение на **FastAPI 0.111+ / Python 3.12** — слоистый монолит для
подсистемы управления пользователями поверх библиотеки
[fastapi-users](https://github.com/fastapi-users/fastapi-users) и шаблона
[FastAPI-base-app](https://github.com/mahenzon/FastAPI-base-app). Проект развивается
**командой агентов Qwen Code** — оркестратор и субагенты на разных моделях; одна
задача за раз, через `tasks/current/`.

## Что внутри

1. **Аутентификация и пользователи** — регистрация, вход/выход, верификация email,
   сброс пароля, ролевой доступ (`is_active`, `is_superuser`, `is_verified`).
   Cookie-based сессии, стратегия токенов — БД (`DatabaseStrategy`).
2. **Кэширование** — список пользователей через `fastapi-cache2` поверх Redis
   (`prefix="fastapi-cache"`, namespace `users-list`); при регистрации/верификации
   кэш сбрасывается через `FastAPICache.clear` в `BackgroundTasks`.
3. **HTML-страницы (Jinja2)** — `/home/` (информация о текущем пользователе,
   кнопка «Verify e-mail» с fetch на `/api/v1/auth/request-verify-token`) и
   `/verify-email/` (страница-обработчик токена из письма). Bootstrap 5 с CDN.
4. **Email-уведомления** — `aiosmtplib` + Jinja2-шаблоны писем
   (`templates/mailing/email-verify/`), отправка в фоне (`BackgroundTasks`).
   Локальный SMTP — `maildev` (порт 1025, web UI 1080).
5. **Вебхуки** — исходящее уведомление о регистрации через `aiohttp`
   (`utils/webhooks/user.py`), плюс входящий вебхук `POST /webhooks/user-created`
   (объявлен через `webhooks=webhooks_router` в фабрике, **роут не зарегистрирован**
   в `main.py` — см. «Известные особенности» в `docs/04_code_quality.md`).
6. **Админка** — `sqladmin` под `/admin`: пользователи (с хешированием пароля при
   редактировании) и access-токены (с автогенерацией `secrets.token_urlsafe`).
7. **Сервисный эндпоинт** — `GET /api/v1/service/stats` отдаёт счётчик запросов
   по путям и статус-кодам (собирает `RequestsCountMiddlewareDispatch`).
8. **Middleware** — CORS (`localhost:8000`), `X-Process-Time`, лог-запросов,
   `requests_count_middleware_dispatch`. На ошибки Pydantic `ValidationError` и
   SQLAlchemy `DatabaseError` установлены кастомные хендлеры в
   `errors_handlers.py`.
9. **Документация API** — кастомные Swagger `/docs` и ReDoc `/redoc` (CDN
   `unpkg`), `oauth2-redirect`.

В проекте нет SPA, нет React/Vite, нет Markdown-блога. Всё — Jinja2 + JSON API.
Карта архитектуры, дерева и соглашений — в [docs/](docs/).

## Агентный режим

Проект развивается командой агентов Qwen Code по одному заданию за раз:

| Файл | Назначение |
|---|---|
| [QWEN.md](QWEN.md) | контекст проекта + инструкции оркестратора (главная сессия) |
| [AGENTS.md](AGENTS.md) | контекст проекта + правила команды, процесс дефектов |
| `tasks/current/REQUIREMENTS.md` | **текущее задание** команды + его рабочие артефакты |
| `tasks/` | архив закрытых заданий: `NNN-<slug>/` — задание, отчёт и все доказательства в одной папке |
| `.qwen/agents/` | субагенты: `spec-writer`, `frontend-dev`, `backend-dev`, `qa`, `adversary` (модели — в frontmatter `model:` этих файлов) |
| [docs/](docs/) | подробная документация по проекту (8 файлов, рус.) |

Схема работы: пользователь кладёт задание в `tasks/current/REQUIREMENTS.md` и
запускает Qwen Code в корне проекта. Главная сессия (оркестратором становится
модель, с которой запущен харнесс) по `QWEN.md` действует как оркестратор: пишет
план, делегирует разработку субагентам, проверяет доказательства, отправляет qa
проверить работу запуском и curl-сценариями, adversary — враждебный прогон; всё о
живом задании — дефекты, находки, сценарии — создаётся в той же папке
`tasks/current/`. Когда все критерии успеха подтверждены, задание закрывается:
оркестратор переименовывает папку в `tasks/NNN-<slug>/` и дописывает в
`REQUIREMENTS.md` секцию «Отчёт о выполнении» (итог, изменения, критерии с
доказательствами, дефекты, disposition adversary, участники), а в свежую заглушку
`tasks/current/REQUIREMENTS.md` пользователь кладёт следующее. В корне проекта
файлов заданий нет.

> В текущем снимке репозитория папка `tasks/` ещё не создана. Она появляется,
> когда пользователь кладёт первое задание в `tasks/current/REQUIREMENTS.md`. До
> этого агенты работают по QWEN.md, но `tasks/current/` не существует — это
> нормальное исходное состояние, не сбой.

Модели команды задаются в единственном месте — frontmatter `model:` в файлах
`.qwen/agents/<роль>.md` (`spec-writer`, `backend-dev`, `frontend-dev`, `qa`,
`adversary`); оркестратор — модель главной сессии. Смена модели роли = правка
одного файла агента. Сами модели должны быть объявлены в `~/.qwen/settings.json`.

Комплект переносим: чтобы внедрить агентный режим в другой проект, скопируйте
`QWEN.md`, `AGENTS.md`, `README.md` и `.qwen/`, а затем адаптируйте проектный
контекст в этих файлах под новый проект. `tasks/current/REQUIREMENTS.md` каждый
раз получает задание нового проекта, архив `tasks/` начинается пустым.

## Стек

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
| Кэш | `fastapi-cache2` + Redis 8 (`redis.asyncio`) |
| Шаблоны | Jinja2 (`jinja_templates.py` → `templates/`) |
| Email | `aiosmtplib` 4.x (SMTP → `maildev` локально) |
| Вебхуки (исходящие) | `aiohttp` |
| ASGI-сервер | uvicorn (dev), gunicorn + UvicornWorker (multi-worker) |
| Сериализация | orjson |
| Линтеры | ruff 0.14+ + black 25+ (объявлены в зависимостях) |

В проекте нет тестов — изменения проверяются запуском приложения и curl.
Тестовых фреймворков не подключаем без явного решения.

## Быстрый старт (локально)

```bash
uv sync                      # создаёт .venv по uv.lock
```

Поднимите инфраструктуру (PostgreSQL 17, Redis 8, maildev):

```bash
docker compose up -d
```

Создайте `.env` рядом с `.env.template` (в `fastapi-application/`) и заполните
обязательные поля — минимум `APP_CONFIG__ACCESS_TOKEN__RESET_PASSWORD_TOKEN_SECRET`
и `APP_CONFIG__ACCESS_TOKEN__VERIFICATION_TOKEN_SECRET`. `APP_CONFIG__DB__URL`
по умолчанию берётся из `.env.template`
(`postgresql+asyncpg://user:pwd@localhost:5432/app`).

Примените миграции (cwd = `fastapi-application/`, иначе плоские импорты в
`alembic/env.py` не найдут `core.config` и `core.models`):

```bash
cd fastapi-application
../.venv/bin/alembic upgrade heads
```

Запустите приложение (предпочтительно из `fastapi-application/`):

```bash
cd fastapi-application
../.venv/bin/uvicorn main:main_app --host 0.0.0.0 --port 8000 --reload    # dev
../.venv/bin/python main.py                                               # dev + баннер
../.venv/bin/python run                                                  # gunicorn (прод)
```

> ⚠️ **Плоские импорты.** Приложение не устанавливается как пакет
> (`pyproject.toml`: `package = false`), все импорты `from core.config import …`
> работают только если `fastapi-application/` — текущий каталог процесса или
> `--app-dir`/`cwd`. Запуск из корня через `uvicorn --app-dir fastapi-application`
> или через `make` (если бы был) — рабочий, но `BASE_DIR` (см.
> `core/config.py`) всегда указывает на `fastapi-application/`, поэтому лог-файл
> и `.env.template` он найдёт, а вот Alembic — нет: для Alembic cwd обязательно
> `fastapi-application/`.

Swagger: <http://127.0.0.1:8000/docs>. Админка: <http://127.0.0.1:8000/admin>.
Главная (требует логин): <http://127.0.0.1:8000/home/>.

CLI для создания суперюзера (после `alembic upgrade`):

```bash
cd fastapi-application
../.venv/bin/python -m actions.create_superuser
# переменные DEFAULT_EMAIL/DEFAULT_PASSWORD из env, по умолчанию admin@admin.com / abc
```

## Конфигурация

Вся конфигурация — вложенные pydantic-модели в `fastapi-application/core/config.py`,
читаются из env-файлов с префиксом `APP_CONFIG__` и разделителем `__`. Файлы:
`.env.template` (закоммичен, без секретов) и `.env` (создаёте локально, в
`.gitignore`).

| Переменная | Обязательна | По умолчанию |
|---|---|---|
| `APP_CONFIG__DB__URL` | да | из `.env.template`: `postgresql+asyncpg://user:pwd@localhost:5432/app` |
| `APP_CONFIG__DB__ECHO` | нет | `False` |
| `APP_CONFIG__DB__POOL_SIZE` | нет | `50` |
| `APP_CONFIG__DB__MAX_OVERFLOW` | нет | `10` |
| `APP_CONFIG__RUN__HOST` / `APP_CONFIG__RUN__PORT` | нет | `0.0.0.0` / `8000` |
| `APP_CONFIG__GUNICORN__WORKERS` | нет | `1` |
| `APP_CONFIG__GUNICORN__TIMEOUT` | нет | `900` |
| `APP_CONFIG__ACCESS_TOKEN__LIFETIME_SECONDS` | нет | `3600` |
| `APP_CONFIG__ACCESS_TOKEN__RESET_PASSWORD_TOKEN_SECRET` | да | — |
| `APP_CONFIG__ACCESS_TOKEN__VERIFICATION_TOKEN_SECRET` | да | — |
| `APP_CONFIG__REDIS__HOST` / `APP_CONFIG__REDIS__PORT` | нет | `localhost` / `6379` |
| `APP_CONFIG__REDIS__DB__CACHE` | нет | `0` |
| `APP_CONFIG__CACHE__PREFIX` | нет | `fastapi-cache` |
| `APP_CONFIG__CACHE__NAMESPACE__USERS_LIST` | нет | `users-list` |
| `APP_CONFIG__LOGGING__LOG_LEVEL` | нет | `info` |

## Маршруты

7 route-объектов всего (проверка:
`cd fastapi-application && ../.venv/bin/python -c "from main import main_app; print(len(main_app.routes))"` → `7`).

| Тип | Методы | Префикс | Что внутри |
|---|---|---|---|
| `Route` | `GET`, `HEAD` | `/openapi.json` | служебный (FastAPI) |
| `APIRoute` | `GET` | `/docs`, `/docs/oauth2-redirect`, `/redoc` | кастомные Swagger/ReDoc (CDN `unpkg`) |
| `Mount` | — | `/admin` | sqladmin: UserAdmin, AccessTokenAdmin |
| `_IncludedRouter` | — | `/api/v1` | auth (login/logout/register/verify/forgot-password/reset-password), users (список + `/{id}` + `/me`), messages (`/`, `/secrets`, `/error`), service (`/stats`) |
| `_IncludedRouter` | — | `/home`, `/verify-email` | Jinja2 views (не входят в OpenAPI: `include_in_schema=False`) |

Подробная разбивка — в [docs/03_execution_flow.md](docs/03_execution_flow.md).

## Модель данных

```python
User(id, email UNIQUE, hashed_password, is_active, is_superuser, is_verified)
    -> access_tokens
AccessToken(token PK, created_at, user_id FK -> users.id CASCADE)
```

`__tablename__` генерируется автоматически: `camel_case_to_snake_case` +
суффикс `s` (`User` → `users`). `IdIntPkMixin` — общий авто-PK `id INTEGER`.
Свои `tablename` пока не переопределял никто. 2 ревизии Alembic:
`96249c3db1f2_create_users_table`, `1c8ec6e08c44_create_access_tokens_table`.

## Docker

```bash
docker compose up -d
```

Стек: **PostgreSQL 17** (5432, `user/password`, база `shop`),
**Redis 8-alpine** (6379), **maildev** (SMTP 1025, web UI 1080). Приложение
само в compose не входит — запускается локально через uvicorn/gunicorn и
ходит в эти сервисы по `localhost`.

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

## Линтеры и проверка изменений

```bash
uv run ruff check .                                                              # линтер
uv run ruff format .                                                             # формат (или: uv run black .)
cd fastapi-application && ../.venv/bin/python -c "from main import main_app; print(len(main_app.routes))"   # 7
cd fastapi-application && ../.venv/bin/uvicorn main:main_app --port 8000         # затем curl:
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/docs
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/admin/login
curl -s -X POST http://127.0.0.1:8000/api/v1/auth/register \
     -H "Content-Type: application/json" \
     -d '{"email":"u@example.com","password":"strongpass","is_active":true,"is_superuser":false,"is_verified":false}'
```

Тестов нет — изменения проверяются запуском приложения и curl-запросами.
Подробные соглашения, грабли и правила для агентов — в [AGENTS.md](AGENTS.md).
