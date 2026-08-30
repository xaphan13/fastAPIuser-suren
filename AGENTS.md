# AGENTS.md — my-fastapi-one (агентный режим)

Контекст-инструкция для AI-агентов, работающих с кодом в этом репозитории, плюс правила
команды агентов (раздел «Агентный режим» в конце файла). `QWEN.md` содержит тот же
проектный контекст и инструкции оркестратора для главной сессии Qwen Code — проектные
части обоих файлов держите синхронными. Текущее задание команды —
[tasks/current/REQUIREMENTS.md](tasks/current/REQUIREMENTS.md).

## Обзор проекта

Учебно-демонстрационный проект на **FastAPI 0.111+ / Python 3.12** — исполняемый каталог
приёмов, а не продуктовый сервис. Три части:

1. **Демонстрационная** (`api/`) — показывает варианты одного и того же решения рядом:
   девять способов `Depends`, один эндпоинт `/my_items/{item_id}` в четырёх стилях
   извлечения параметров, два стиля pydantic-полей, два способа валидации.
2. **Рабочая** (`ex_user_post/`, `ex_order_product/`, `db_core/`) — асинхронный слой
   данных на SQLAlchemy 2.0 с миграциями Alembic и двумя доменами: `User`/`Post`
   (one-to-many) и `Order`/`Product` (many-to-many через явную ассоциативную модель).
3. **Блог** (`md_articles/` + `frontend/`) — React SPA на JSON API `/api/blog`:
   статьи из YAML-реестра с серверным Markdown-рендером и клиентской подсветкой
   highlight.js, вход/регистрация/аккаунт (cookie-сессии, bcrypt, аватары),
   управление реестром, темы сайта/подсветки. Подробности по архитектуре блога —
   [`docs/11_md_articles.md`](docs/11_md_articles.md) и [`docs/15_md_articles_package.md`](docs/15_md_articles_package.md).

**Дублирование маршрутов и обработчиков в `api/` намеренное** — сравнивать файлы
построчно и есть учебная цель. Не «рефакторьте» это в общий код, не выяснив задачу.

**Стек**

| Область | Выбор |
|---|---|
| Язык | Python 3.12 (`.python-version`) |
| Менеджер пакетов | `uv` (`uv.lock` — источник истины) |
| Веб-фреймворк | FastAPI 0.111+ (ORJSONResponse по умолчанию) |
| Валидация / конфигурация | Pydantic 2 + pydantic-settings (префикс `APP__`, разделитель `__`) |
| ORM | SQLAlchemy 2.0 async (`asyncpg` / `aiosqlite`) |
| Миграции | Alembic (асинхронный env.py) |
| ASGI-сервер | uvicorn (dev), gunicorn + UvicornWorker (multi-worker) |
| Сериализация | orjson |
| Фронтенд блога | React 18 + TypeScript + Vite + Tailwind CSS v4 (в `frontend/`) |
| Линтеры | ruff + black (объявлены в зависимостях проекта) |

**В проекте нет тестов** — изменения проверяются запуском приложения и curl.

### Архитектура

`fastapi-application/create_fastapi.py` предоставляет фабрику `create_app()` с `lifespan`
(engine создаётся на импорте, dispose — в shutdown). `main.py` собирает `main_app`,
подключает три корневых роутера, вызывает `md_articles.include_router_api_frontend(main_app)`
(сессии, статика `/static`, JSON-роутер блога) и затем `mount_vite_react_assets(main_app)`
(детали — [`docs/11_md_articles.md`](docs/11_md_articles.md)):

| Роутер | Модуль | Префикс | Что внутри |
|---|---|---|---|
| `router_api` | `api/__init__.py` | `/api/v1` | `dep_examples/` (9 роутов Depends) + 4 стиля `/my_items/{item_id}` |
| `r_users_sql` | `ex_user_post/router_users.py` | `/users` | CRUD-слой домена User/Post (2 роута) |
| `r_order_one` | `ex_order_product/router_order_one.py` | `/orders` | 6 роутов Order: ORM/Core запись, фильтры, сортировка, joinedload |
| `router_blog_api` | `md_articles/api_blog.py` | `/api/blog` | JSON API блога для React SPA: csrf, current_user, register/login/logout, account (GET/POST), articles, articles/{id}, art_manage + add_all + meta |

Итого 41 route-объект: 21 API + служебные `/docs`, `/redoc`, `/openapi.json`,
`/docs/oauth2-redirect` (кастомные Swagger/ReDoc регистрирует `utils/docs.py`)
+ 13 JSON-роутов блога + mount `/static` (аватары) + mount `/assets`
(сборка фронтенда) + SPA catch-all `/{full_path:path}` (отдаёт
`frontend/dist/index.html`, для `/api*` — 404 JSON). Клиентская часть блога —
React SPA в `frontend/` (Vite + TypeScript + Tailwind v4, сборка не коммитится).

Проверка счётчика: `cd fastapi-application && ../.venv/bin/python -c "from main import main_app; print(len(main_app.routes))"` → `41`.
Разбивка: 34 `APIRoute` (21 из `router_api`/`r_users_sql`/`r_order_one` + 13 из `api_blog.py`) + 5 `Route` (4 служебных + SPA catch-all) + 2 `Mount` (`/static` блога, `/assets` SPA).

```
my-fastapi-one/                 <- корень репозитория; здесь запускается qwen-code
├── QWEN.md AGENTS.md README.md  контекст + правила команды (этот комплект)
├── tasks/                       задания команды: current/ — живое, NNN-<slug>/ — архив (ведёт оркестратор)
├── .qwen/agents/                субагенты: frontend-dev, backend-dev, qa, adversary
├── frontend/                    React SPA блога: Vite + TS + Tailwind v4 (dist/ не коммитится)
├── docs/                        подробная документация по проекту (15 файлов, рус.)
├── templates_qwen_agents/       комплект агентного режима из другого проекта — ТОЛЬКО пример, не трогать
├── docker-compose.yml           dev-стек: pg + adminer + pgadmin
├── nginx_pg_admin.yml           прод-подобный стек: pg + pgadmin + redis + nginx (TLS)
├── Makefile                     запуск uvicorn, alembic, docker network
├── pyproject.toml uv.lock       зависимости (uv) + конфиг ruff/black
└── fastapi-application/         корень Python-приложения (= BASE_DIR)
    ├── main.py                  main_app + подключение роутеров + mount_vite_react_assets() (SPA-слой в setup_frontend.py)
    ├── md_articles/setup_frontend.py  mount /assets + SPA catch-all + защита /api* (см. docs/13)
    ├── main_gunicorn.py         точка входа gunicorn (переиспользует main_app)
    ├── create_fastapi.py        фабрика create_app() + lifespan (блог подключается в main.py)
    ├── base_dir_path.py         DIR_CWD / BASE_DIR (Path)
    ├── config_log.py            ConfigLogger: dictConfig, файл+stdout
    ├── one.env two.env          профили БД: postgres / sqlite (закоммичены, sqlite активен)
    ├── core/config.py           Settings: весь конфиг, env_file-профили
    ├── db_core/                 Base, AsyncDbManager, CurrentSession, типы колонок
    ├── api/                     демонстрационная часть: dependencies/ + my_routes_dep/
    ├── ex_user_post/             домен User/Post: router + crud + models + schemas
    ├── ex_order_product/        домен Order/Product: router + models + schemas
    ├── md_articles/             блог: api_blog.py (JSON API), schema_art, модели, auth_middleware_helpers
    ├── content_art/             .md-статьи блога (кладёт пользователь)
    ├── static/                  profile_pics/ (аватары)
    ├── alembic/                 асинхронные миграции (3 ревизии)
    ├── utils/docs.py            кастомные Swagger/ReDoc
    └── log/                     вывод логов (путь от BASE_DIR)
```

## Документация

В папке [`docs/`](docs/) лежит подробная документация по проекту (на русском) —
обращайтесь к ней, прежде чем блуждать по исходникам:

| Файл | Что внутри |
|---|---|
| [`docs/01_project_structure.md`](docs/01_project_structure.md) | карта проекта: дерево, зависимости, инварианты окружения |
| [`docs/02_architecture.md`](docs/02_architecture.md) | архитектура и слои, потоки данных, развёртывание |
| [`docs/03_execution_flow.md`](docs/03_execution_flow.md) | жизненный цикл, маршруты, ключевые процессы, логирование |
| [`docs/04_code_quality.md`](docs/04_code_quality.md) | оценка качества кодовой базы, дефекты по критичности |
| [`docs/05_patterns_di.md`](docs/05_patterns_di.md) | обучающий разбор: 9 паттернов внедрения зависимостей |
| [`docs/06_patterns_parameters.md`](docs/06_patterns_parameters.md) | обучающий разбор: 4 стиля извлечения параметров, pydantic |
| [`docs/07_patterns_data_layer.md`](docs/07_patterns_data_layer.md) | обучающий разбор: 11 паттернов async-слоя данных |
| [`docs/08_ideas_di_api.md`](docs/08_ideas_di_api.md) | идеи развития: DI и API-слой |
| [`docs/09_ideas_data_layer.md`](docs/09_ideas_data_layer.md) | идеи развития: слой данных |
| [`docs/10_ideas_testing_infra.md`](docs/10_ideas_testing_infra.md) | идеи развития: тесты, конфигурация, инфраструктура |
| [`docs/11_md_articles.md`](docs/11_md_articles.md) | блог md_articles: архитектура, маршруты, JSON API для React SPA |
| [`docs/12_fastapi_react_integration.md`](docs/12_fastapi_react_integration.md) | связка FastAPI + React: способы организации фронтенда, dev vs прод |
| [`docs/13_frontend_spa_module.md`](docs/13_frontend_spa_module.md) | модуль `setup_frontend.py`: как код подключает собранный React, dev-режим без `dist/` |
| [`docs/14_create_fastapi_factory.md`](docs/14_create_fastapi_factory.md) | фабрика `create_app()` и `lifespan` в `create_fastapi.py`: каркас vs наполнение |
| [`docs/15_md_articles_package.md`](docs/15_md_articles_package.md) | пакет `md_articles`: JSON API блога, реестр статей, сессии |

## Индекс кодовой базы

Для структурных запросов по коду (кто вызывает функцию, что она вызывает, мёртвый код,
анализ влияния изменений) используйте графовый индекс через **codebase-memory-mcp** —
это быстрее и точнее, чем обход исходников вручную. Скилл `codebase-memory` описывает
доступные MCP-инструменты (`search_graph`, `trace_path`, `detect_changes` и др.).
Перед структурным исследованием проверяйте наличие/свежесть индекса через `index_status`.

## Сборка и запуск

### Настройка

```bash
uv sync                      # создаёт .venv по uv.lock
```

Профиль БД выбирается в `fastapi-application/core/config.py` (`env_file` класса
`Settings`): активен `dev_sqlite.env` — SQLite (`sqlite+aiosqlite:///./one_simple.db`), внешняя
БД не нужна. PostgreSQL (`prod_db.env`, `postgresql+asyncpg://user:password@localhost:5432/shop`)
включается раскомментированием строки; `.env` перекрывает оба профиля. Docker-стек для
PostgreSQL: `docker compose up -d` (pg на `5432`, adminer `8080`, pgadmin `5050`).

### Локальный запуск

```bash
cd fastapi-application
../.venv/bin/uvicorn main:main_app --host 0.0.0.0 --port 8000 --reload    # предпочтительно
../.venv/bin/python main.py                                               # то же + баннер в лог
# из корня проекта: make run_app11_lin  (uvicorn --app-dir fastapi-application)
```

**cwd имеет значение**: файл SQLite `./one_simple.db` резолвится относительно рабочего
каталога — запуск из корня через `--app-dir` создаст базу в корне, а не в
`fastapi-application/`. Логи всегда в `fastapi-application/log/` (привязка к `BASE_DIR`).
Предпочтителен запуск из `fastapi-application/`.

Multi-worker: `gunicorn main:main_app --workers 4 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000` (из `fastapi-application/`; сборка — `main_gunicorn.py`).

Alembic (требует cwd = `fastapi-application/`):

```bash
cd fastapi-application && ../.venv/bin/alembic upgrade heads
../.venv/bin/alembic revision --autogenerate
```

### Линтеры и форматирование

```bash
uv run ruff check .
uv run ruff format .     # либо: uv run black .
```

Ruff и black объявлены в зависимостях проекта — отдельная установка не нужна.

### Проверка работоспособности

Тестов нет, поэтому изменения проверяются запуском самого приложения:

```bash
cd fastapi-application && ../.venv/bin/python -c "from main import main_app; print(len(main_app.routes))"   # ожидается 40
../.venv/bin/uvicorn main:main_app --port 8000    # затем curl:
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/docs
curl -s http://127.0.0.1:8000/api/v1/dep_examples/single-direct-dependency
curl -s http://127.0.0.1:8000/users/get_all_users
curl -s http://127.0.0.1:8000/api/blog/articles          # JSON API блога
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/   # SPA (нужен frontend/dist: cd frontend && npm run build)
```

Не утверждайте, что изменение проверено, без фактического запуска. Если проверить
невозможно — сообщите об этом прямо.

## Соглашения разработки

### Стиль кода

- Длина строки: **ruff 100**, black 120; отступ 4 пробела (`pyproject.toml`).
- Ruff намеренно игнорирует `F401` (неиспользуемые импорты), `E402` (импорты не в начале
  файла) и `F541` (f-строка без подстановок). Эти исключения несут смысловую нагрузку:
  код осознанно импортирует логгер раньше остальных модулей и реэкспортирует имена
  (`db_core/__init__.py`). Не «исправляйте» их.
- Крупные декоративные комментарии-разделители (`# ====`, `# ----`, `#***`) разделяют
  логические секции. Соблюдайте локальный стиль файла при правках, не удаляйте их.
- Русский язык используется для комментариев, docstring'ов и документации. Новый текст
  и комментарии пишите на том же языке, что и окружающий файл.

### Паттерн модуля роутера

- **Импорты плоские, не пакетные**: `from core.config import settings`, а не
  `from fastapi-application.core...`. Приложение не устанавливается как пакет —
  любой запуск (uvicorn, alembic, `python -c`) выполняется с cwd или `--app-dir`
  = `fastapi-application/`, где эти модули лежат в корне `sys.path`.
- Объект `APIRouter` объявляется на уровне модуля с `prefix=settings.api...` и
  `tags=[...]`; включение вложенных роутеров — в `__init__.py` своей папки.
- Сессия БД — только через DI-алиас `CurrentSession`
  (`Annotated[AsyncSession, Depends(db_manager.get_async_session)]` из `db_core/db_async.py`).
- Логирование — через `logF` из `config_log.py` (файл+stdout); в демонстрационных
  роутах допустимы подробные `logF.info` с составами данных.

### Конфигурация

- Весь конфиг — вложенные pydantic-модели в `core/config.py`, читаются из env-файлов
  с префиксом `APP__` и разделителем `__` (`APP__DB__URL`, `APP__RUN__PORT`).
  Единственное обязательное поле — `db.url`.
- Переключение профиля БД — правка списка `env_file` в `core/config.py`
  (раскомментировать `prod_db.env`), **не** переменная окружения.
- Новые настройки добавляйте как поля соответствующей вложенной модели с дефолтом,
  а не читайте `os.environ` напрямую.

### Модели и схемы

- SQLAlchemy 2.0-стиль: `Mapped[]` + `mapped_column`, переиспользуемые `Annotated`-типы
  из `db_core/type_for_models.py` (`int_primary_key`, `str_len_100` и др.).
- `__tablename__` генерируется автоматически (`CamelCase` → `snake_case`,
  `db_core/model_base.py`); переопределяйте только при необходимости
  (как `OrderProductAssociation`).
- Новые модели обязательно реэкспортируйте в `db_core/__init__.py` — именно этот импорт
  наполняет `Base.metadata` для Alembic `--autogenerate`. Модели вне реэкспорта
  (например `TestUser`) миграциям невидимы.
- Pydantic-схемы — рядом с доменом (`schemas/` или `schema_*.py`), имена
  `XxxCreate`/`XxxResp`; сериализация FastAPI — `response_model` в декораторе.

## Грабли — сверьтесь с этим списком перед отладкой

### Запуск и окружение

- **cwd-зависимость SQLite.** `sqlite+aiosqlite:///./one_simple.db` резолвится от
  рабочего каталога процесса: запуск из корня (`make run_app11_lin`, `--app-dir`)
  создаст базу в корне проекта, а не в `fastapi-application/`. Данные «пропали» после
  смены способа запуска — проверьте, где лежит `*.db`.
- **Побочные эффекты на импорте.** `config_log` создаёт каталог `fastapi-application/log/`
  и настраивает логгеры в момент импорта; `db_manager` (engine) создаётся на импорте
  `db_core/db_async.py`. Это значит: импорт `main` уже поднимает логи и требует
  валидного `APP__DB__URL`; подменить сессию в тестах можно только через
  `app.dependency_overrides`.
- **Alembic требует cwd = `fastapi-application/`** (там `alembic.ini` и плоские импорты
  `db_core`/`core.config` в `env.py`). Цели Makefile `migr_gener`/`migr_to_base`
  используют устаревший путь `venv/bin/alembic` — фактический интерпретатор в `.venv/`.
- **Профиль БД переключается правкой кода** (`core/config.py`, `env_file`), env-файлы
  `prod_db.env`/`dev_sqlite.env` закоммичены намеренно (учебный проект, секретов нет).

### Известные дефекты (из docs/04_code_quality.md) — не «исправляйте» без отдельного задания

- `GET /api/v1/depends_function_annotated/my_items/{item_id}` без query-параметра
  `param_id` возвращает **500** (`validate_query_safe` сравнивает `1 <= None` →
  `TypeError`). Сравните с корректной реализацией в `pydantic_validator.py`
  (`RespAfterValid`, `Field(ge=1, le=1000)`).
- Дублирующийся `nickname` в `POST /users/create_user` даёт **500** (`IntegrityError`)
  вместо 409 — нет перехвата исключения целостности.
- `UserResp` наследует поле `password` от `UserCreate` (утечка в ответе).
- `ex_user_post/models/model_user_mix.py::TestUser` не реэкспортирован в
  `db_core/__init__.py` — невидим для Alembic (намеренная демонстрация примеси).

### Docker

- `docker-compose.yml` — dev-стек (pg `5432` + adminer `8080` + pgadmin `5050`),
  креды захардкожены (`user/password`, база `shop`) — учебный проект.
- `nginx_pg_admin.yml` — прод-подобный стек: требует внешний сеть `app_net_new`
  (`make create-net`), `.env` рядом с compose (`DB_USER`, `DB_PASSWORD`, `DB_NAME`,
  `PGADMIN_EMAIL`, `PGADMIN_PASSWORD`) и сертификаты в `nginx/cert/` (не в git);
  `nginx.conf` ссылается на `xaphan.ru`.
- Приложение само в compose не входит — запускается локально/gunicorn и проксируется
  через nginx.

## Git

Ветка на момент написания: `new_agents_mode`. Заголовки коммитов короткие и в нижнем
регистре (`new agents files templates`, `update docs`, `pattern code and new idea`).
Держитесь той же лаконичности. Учтите, что `log/`, `*.db`, `*.log`, `pg_db/`, серты
nginx находятся в `.gitignore` — никогда не добавляйте их. Индексируйте только файлы,
относящиеся к изменению. `adminGit.sh` — CLI-обёртка над git, `adminDock.sh` — над docker.

---

## Агентный режим

Эти правила применяются к каждому агенту команды, работающему над заданием из
[tasks/current/REQUIREMENTS.md](tasks/current/REQUIREMENTS.md). Оркестратор — главная сессия Qwen Code (инструкции
в `QWEN.md`). При сомнениях главенствует текущее задание, затем проектные соглашения
выше.

### Жизненный цикл заданий

- Текущее задание живёт в `tasks/current/REQUIREMENTS.md`; в корне проекта файлов
  заданий нет. Все рабочие артефакты живого задания создаются в той же папке
  `tasks/current/`: `DEFECTS.md` (если qa найдёт дефекты), `ADVERSARIAL_REVIEW.md`,
  `e2e/`, `screenshots/`, `dev/` (прогресс-файлы и сырые выводы разработчиков).
- У задания две фазы жизни: **создание** и **исполнение**. Создание: оркестратор
  запускает скилл `task-spec` и субагента spec-writer — сырая идея пользователя
  превращается в полный REQUIREMENTS.md с планом фаз (шаблон —
  `.qwen/skills/task-spec/TEMPLATE.md`); открытые вопросы закрываются с пользователем,
  план фаз подтверждается, спека замораживается. Исполнение: строго по фазам из
  этого плана — фаза = одно делегирование = 1–3 файла = бюджет ~10–15 ходов;
  следующая фаза стартует только после зелёного checkpoint и ревью диффа
  оркестратором. Детали — в скилле `task-spec` и в QWEN.md.
- Упавший прогон не возобновляют пересказом истории. Сначала проверить, что процесс
  не остался (`pgrep -af "uvicorn.*main:main_app"`) и мусора нет; затем прочитать
  `tasks/current/dev/phaseNN_progress.md` и `git diff`; затем запустить свежий узкий
  прогон «фаза N: сделано X, доделай Y». Это касается и backend-dev, и frontend-dev.
- Когда все критерии успеха подтверждены, оркестратор архивирует задание:
  переименовывает папку `tasks/current/` в `tasks/NNN-<slug>/` (`NNN` — следующий
  порядковый номер от 001, `<slug>` — короткое латинское имя через дефис) — так все
  артефакты переезжают в архив вместе с заданием; в `tasks/NNN-<slug>/REQUIREMENTS.md`
  убирает пометку «Текущее задание» и дописывает в конец секцию «Отчёт о выполнении»:
  дата закрытия, итог, изменения, таблица критериев с результатами и ссылками на
  доказательства, дефекты, disposition находок adversary, участники. Шаблон отчёта —
  в QWEN.md. Затем создаёт свежую заглушку `tasks/current/REQUIREMENTS.md`
  «Задания нет», в которую пользователь кладёт новое задание, и цикл повторяется
  тем же составом команды.
- Закрытые задания лежат в `tasks/NNN-<slug>/` — целиком, со всеми артефактами
  (задание + отчёт, ADVERSARIAL_REVIEW.md, DEFECTS.md, e2e/, screenshots/); пишет
  туда только оркестратор.
- Комплект агентного режима переносим: чтобы использовать его в другом проекте,
  достаточно адаптировать проектный контекст в `README.md`, `QWEN.md`, `AGENTS.md`
  и папку `.qwen/`; `tasks/current/REQUIREMENTS.md` каждый раз получает новое
  задание, архив `tasks/` начинается пустым. `templates_qwen_agents/` — исходный
  пример комплекта из другого проекта, только для образца.

### Команда

- **оркестратор** (главная сессия, `QWEN.md`) — планирует, делегирует, ревьюит,
  контролирует критерии успеха. Код не пишет.
- **spec-writer** — отдельная сессия фазы создания задания: исследует зону будущего
  задания и пишет `tasks/current/REQUIREMENTS.md` с планом фаз (запускается
  оркестратором через скилл `task-spec`). Код не пишет.
- **frontend-dev** — UI-слой проекта. В этом проекте это статические страницы
  `nginx/web/` и разметка ошибок nginx; основная работа — у backend-dev.
- **backend-dev** — серверная часть: роуты, схемы, модели, CRUD, конфигурация,
  миграции.
- **qa** — проверки запуском и curl-сценариями, заметки e2e, реестр DEFECTS.md. Код
  продукта не исправляет.
- **adversary** — пытается сломать изменённую функциональность нешаблонными способами;
  записывает находки в ADVERSARIAL_REVIEW.md.

Определения агентов в `.qwen/agents/` универсальны и переносятся между проектами без
правок: каждый агент первым шагом читает AGENTS.md и привязывается к проекту таблицей
ниже. При переносе агентного режима в другой проект меняется только эта таблица.

### Зоны и проверки (привязка к этому проекту)

| Агент | Зона (можно редактировать) | Чем проверяет изменения | Особые запреты |
|---|---|---|---|
| frontend-dev | `frontend/` (React SPA: источники, Vite-конфиги, сборка), `nginx/web/` (если появится в задании) | `cd frontend && npm run build` без ошибок; просмотр страницы; скриншот в `tasks/current/screenshots/` | Python-модули `fastapi-application/` — зона backend-dev; `frontend/dist` не коммитится |
| backend-dev | Python-модули `fastapi-application/` (включая `alembic/`, env-профили, `md_articles/` с JSON API `api_blog.py`) | `uv run ruff check .`; `cd fastapi-application && ../.venv/bin/python -c "from main import main_app; print(len(main_app.routes))"` (текущее значение: 42); curl изменённых эндпоинтов на запущенном приложении | `frontend/`, `nginx/web/`; устаревшие API из раздела «Известные дефекты» — не чинить без отдельного задания; дублирование `api/my_routes_dep/` — намеренное |
| qa | `tasks/current/e2e/`, `tasks/current/DEFECTS.md`, `tasks/current/screenshots/` | curl-сценарии из критериев успеха текущего задания; регресс: `/docs`, `/users/get_all_users`, `/orders/get_all_orders`, один из `/api/v1/dep_examples/*`, `/art_home` | любой код продукта |
| adversary | `tasks/current/ADVERSARIAL_REVIEW.md`, `tasks/current/screenshots/` | curl по запущенному приложению; логи `fastapi-application/log/` | всё, кроме своих файлов |
| spec-writer | `tasks/current/REQUIREMENTS.md` — только на фазе создания задания, одним `write_file` по шаблону `.qwen/skills/task-spec/TEMPLATE.md` | чек-лист скилла `task-spec` (проверяет оркестратор) | код продукта; всё, кроме REQUIREMENTS.md на фазе создания |

Общее для всех: не редактировать `.qwen/`, `tasks/current/REQUIREMENTS.md`, папки
архивных заданий `tasks/NNN-*`, `AGENTS.md`, `QWEN.md`, `README.md`, `docs/`,
`templates_qwen_agents/`; не добавлять зависимости и тестовые
фреймворки без решения оркестратора. Обновление документации в `docs/` координирует
оркестратор. Единственное исключение: spec-writer на фазе создания пишет
`tasks/current/REQUIREMENTS.md`; после старта исполнения файл заморожен для всех,
кроме оркестратора.

Границы ролей обеспечиваются системным промптом каждого агента и конфигурацией
инструментов. Не обходите их командами оболочки: если инструкции говорят, что файл
запрещён, не изменяйте его никаким другим способом.

### Соглашения репозитория агентного режима

- Всё о задании живёт в его папке. Текущее задание — `tasks/current/` (контракт
  `REQUIREMENTS.md` + рабочие артефакты `DEFECTS.md`, `ADVERSARIAL_REVIEW.md`,
  `e2e/`, `screenshots/`, `dev/`); закрытое — `tasks/NNN-<slug>/` с тем же набором
  плюс отчёт. В корне проекта файлов заданий нет.
- Проверочные сценарии и доказательства qa живут в `tasks/current/e2e/` (скрипты,
  заметки прогонов с командами и сырыми выводами). Писать туда может только qa.
- Прогресс-файлы и сырые выводы разработчиков живут в `tasks/current/dev/`
  (`phaseNN_progress.md` — по одному на фазу, плюс `*.txt` для сырых выводов команд).
  Пишут туда backend-dev и frontend-dev; прогресс-файлы — страховка восстановления:
  по ним свежий прогон продолжает упавшую фазу без пересказа истории.
- `tasks/current/DEFECTS.md` ведут qa и оркестратор (см. ниже);
  `tasks/current/ADVERSARIAL_REVIEW.md` — adversary и оркестратор.
- Никаких эмодзи в коде, комментариях и логах.
- Тестовые сервера живут только на время живого задания: субагент поднимает сервер
  по своей спецификации и не глушит поднятый другим (его переиспользуют qa/adversary),
  но все тестовые процессы гасит оркестратор при закрытии задания — ни одного
  оставленного uvicorn после архивирования.
- Новых тяжёлых зависимостей (фреймворки тестов, браузерные драйверы и т.п.) не
  добавлять без явного решения оркестратора, согласованного с пользователем: проект
  живёт без тест-инфраструктуры, и проверки делаются запуском приложения и curl.

### Экономия токенов субагентов

Каждый ход субагента пересылает весь накопленный контекст (~40–50K токенов), поэтому
длинный прогон дорожает с каждым ходом, а упавший на 50+ ходу — миллионы токенов
впустую. Общие правила для всех субагентов:

- AGENTS.md и `tasks/current/REQUIREMENTS.md` читать один раз в начале прогона,
  не перечитывать.
- Не читать исходники продукта целиком: разработчик смотрит только свою зону правок,
  qa проверяет поведение, а не код.
- Объединять команды проверки в пачки (один shell-вызов — несколько curl/команд),
  сырые выводы сразу писать в файл (`tasks/current/e2e/` у qa, `tasks/current/dev/`
  у разработчиков), а не пересказывать в чате.
- Ошибку читать и исправлять, а не повторять ту же команду вслепую. Две подряд
  неудачные попытки починить одно и то же — стоп и доклад оркестратору.
- Работать на минимум ходов: чем короче прогон, тем дешевле каждый следующий ход.

Правило для оркестратора: главный источник перерасхода — **backend-dev**, и лучшая
экономия делается ДО его запуска. Порядок защиты: (1) спека с планом фаз от
spec-writer — объём режется на фазы заранее, а не в момент делегирования;
(2) короткие фазы — фаза = 1–3 файла = бюджет ~10–15 ходов; (3) дисциплина внутри
фазы. Прогон, который пишет код, тяжелеет быстрее всех: каждый ход дописывает
контекст чтением исходников, полными `write_file` и traceback'ами ошибок. Формат
qa/adversary (пачки curl одним shell-вызовом, сырые выводы сразу в файл) дешёвый —
его не менять. Правила делегирования backend-dev:

1. Делегируй строго по фазам из REQUIREMENTS.md; план фаз уже разрезан spec-writer'ом
   и подтверждён пользователем. Фаза кажется большой — режь её сам ДО запуска,
   а не после.
2. В спецификации — только: какие файлы, контракт (имена/поведение), checkpoint,
   ссылка на прогресс-файл (для продолжения). Детали — в REQUIREMENTS.md, который
   читается один раз, а не в текст спецификации, пересылаемый каждый ход.
3. В спецификацию backend-dev явно включать: читать только свою зону правок (не весь
   репозиторий), план файлов до первой записи, новый файл — одним `write_file`,
   существующий — только точечным `edit`, сырые выводы команд — сразу в файл
   (`tasks/current/dev/`), прогресс-чекпоинт после каждого файла, ошибку чинить
   узко (правка + одна контрольная команда), полный smoke — один раз в конце фазы.
4. Упёршийся в лимит / упавший прогон не продолжать: узкий перезапуск «доделай X»
   с чистым контекстом по прогресс-файлу и `git diff`, а не резюме марафона (резюме
   проигрывает весь контекст заново — это удваивает стоимость).

Урок 001-md-articles-blog (2026-08-31): монолитный запуск backend-dev на весь бэкенд
(~8 модулей + миграция) обошёлся в ~25 млн токенов, при этом qa и adversary уложились
дёшево — проблема была только в монолитном код-писателе.

Как правильно запускать тестера (qa) — см. раздел «Экономия токенов» в
`.qwen/agents/qa.md`: короткий сфокусированный прогон, пачки curl-проверок, сервер
проверяется `pgrep`/`curl http://127.0.0.1:8000/openapi.json` до подъёма (не дублировать
процессы). Оркестратор запускает qa одним блоком задания с готовым списком проверок —
без промежуточных «проверь ещё вот это».

### DEFECTS.md — реестр дефектов

Все дефекты живут в `tasks/current/DEFECTS.md` (папка текущего задания; создаётся при
первом дефекте), одна запись на дефект, новые сверху. При архивировании задания файл
переезжает в `tasks/NNN-<slug>/` вместе с папкой.
Авторы: **qa** (создание, закрытие, переоткрытие) и **оркестратор** (фиксация ответов
разработчиков, отклонение). Больше никто никогда его не редактирует.

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

Каждая смена статуса добавляет строку в History с указанием, кто, что и почему сделал.
Дефект не завершён, потому что так сказал разработчик, — он завершён, когда qa его закрывает.

### ADVERSARIAL_REVIEW.md — находки adversary

Все находки adversary живут в `tasks/current/ADVERSARIAL_REVIEW.md` (папка текущего
задания; создаётся при первом прогоне; при архивировании переезжает в
`tasks/NNN-<slug>/` вместе с папкой).
Авторы: **adversary** (создание записей) и **оркестратор** (заполнение Disposition). Больше
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

Оркестратор заменяет PENDING на `ACCEPTED -> DEF-NNN` или `REJECTED - причина`.
Принятые находки воспроизводятся и заводятся в DEFECTS.md силами qa. Когда задание
закрыто, ни одна запись не может оставаться PENDING.
