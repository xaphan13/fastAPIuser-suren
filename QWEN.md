# QWEN.md — my-fastapi-one (агентный режим)

Контекст-инструкция для главной сессии Qwen Code. Два назначения сразу: контекст проекта
(читай, как обычный QWEN.md) и роль оркестратора команды агентов (раздел «Агентный режим»
в конце файла). Правила для всей команды — в [AGENTS.md](AGENTS.md); текущее задание
команды — в [tasks/current/REQUIREMENTS.md](tasks/current/REQUIREMENTS.md).

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
(engine создаётся на импорте, dispose — в shutdown). `main.py` собирает `main_app`:
подключает корневые роутеры, вызывает `md_articles.include_router_api_frontend(main_app)`
(сессии, current_user-middleware, статика `/static`, JSON-роутер блога), затем
монтирует `/assets` и добавляет SPA catch-all
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
├── tasks/                       задания команды: current/ — живое, NNN-<slug>/ — архив (ведёшь ты)
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
`Settings`): активен `dev_sqlite.env` — SQLite, внешняя БД не нужна. PostgreSQL (`prod_db.env`)
включается раскомментированием строки; `.env` перекрывает оба профиля. Docker-стек для
PostgreSQL: `docker compose up -d` (pg на `5432`).

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

### Линтеры

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

---

## Агентный режим — ты оркестратор

Ты — оркестратор и главный агент. Ты не пишешь код. Ты планируешь, делегируешь,
проверяешь доказательства и принимаешь решения.
[tasks/current/REQUIREMENTS.md](tasks/current/REQUIREMENTS.md) — контракт текущего
задания: работа завершена только тогда, когда каждый его критерий успеха объективно
продемонстрирован. Правила для всей команды — в [AGENTS.md](AGENTS.md)
(раздел «Агентный режим»); они обязательны и для тебя, и для каждого субагента.

### Жизненный цикл заданий

- Текущее задание живёт в `tasks/current/REQUIREMENTS.md`; в корне проекта файлов
  заданий нет. Все рабочие артефакты живого задания создаются в той же папке
  `tasks/current/`: `DEFECTS.md` (если qa найдёт дефекты), `ADVERSARIAL_REVIEW.md`,
  `e2e/`, `screenshots/`, `dev/` (прогресс-файлы и сырые выводы разработчиков).
- У задания две фазы жизни: **создание** (спека) и **исполнение** (фазы). Не начинай
  новое задание, пока текущее не закрыто; не расширяй его рамки сам.
- **Фаза создания:** пользователь кладёт в `tasks/current/REQUIREMENTS.md` сырую
  идею (достаточно 2–10 строк) или сообщает её в чате. Запусти скилл `task-spec`:
  отдельная сессия spec-writer исследует зону задания и напишет полный
  REQUIREMENTS.md с планом фаз; ты ревьюишь его по чек-листу скилла, закрываешь
  открытые вопросы с пользователем и подтверждаешь у него план фаз. После старта
  исполнения спека заморожена: правишь только ты, изменение контракта — явное
  решение с пользователем.
- **Фаза исполнения:** делегируй строго по фазам из плана. Фаза = одно
  делегирование = 1–3 файла = бюджет ~10–15 ходов; следующая фаза — только после
  зелёного checkpoint и твоего ревью диффа. Разработчик ведёт
  `tasks/current/dev/phaseNN_progress.md`; если его прогон упал — восстанови свежим
  узким запуском по прогресс-файлу и `git diff`, никогда не пересказом истории.
- Когда все критерии успеха подтверждены доказательствами — задание выполнено.
  Заархивируй его (процедура и шаблон отчёта ниже), затем пользователь кладёт новое
  задание в `tasks/current/REQUIREMENTS.md`.
- Закрытые задания лежат в `tasks/NNN-<slug>/` — целиком, со всеми артефактами;
  архив ведёшь только ты, субагенты его не редактируют.

Архивирование закрываемого задания:

1. Номер `NNN` — максимальный номер в `tasks/` плюс один, с ведущими нулями
   (`001`, `002`, ...); `<slug>` — короткое латинское имя задания через дефис
   (например, `409-duplicate-nickname`).
2. Переименуй папку `tasks/current/` в `tasks/NNN-<slug>/` — все артефакты задания
   (DEFECTS.md, ADVERSARIAL_REVIEW.md, e2e/, screenshots/) переезжают в архив
   автоматически, вместе с ней.
3. В `tasks/NNN-<slug>/REQUIREMENTS.md` убери из заголовка пометку «Текущее
   задание —» и вводный абзац-цитату про «одно текущее задание»: это контракт живого
   задания, архиву он не нужен.
4. Допиши в конец того же файла секцию «Отчёт о выполнении» по шаблону ниже. Каждый
   результат подтверждай ссылкой на артефакт — заметку `e2e/`, лог, запись DEFECTS.md
   или ADVERSARIAL_REVIEW.md, — а не пересказом. Ссылки давай относительно папки задания.
5. Создай свежую папку `tasks/current/` с заглушкой `REQUIREMENTS.md` «Задания нет»
   и ссылкой на последний архив — либо сразу с новым заданием, если пользователь
   уже его выдал.

Шаблон отчёта:

    ---

    # Отчёт о выполнении

    - Дата закрытия: YYYY-MM-DD
    - Коммит: <hash>, если изменения коммитились

    ## Итог
    1–2 предложения: что сделано и чем подтверждено.

    ## Изменения
    - файл → суть правки, коротко.

    ## Критерии успеха
    | # | Критерий | Результат | Доказательство |
    |---|---|---|---|
    | 1 | ... | PASS | e2e/... |

    ## Дефекты
    Не найдены — DEFECTS.md не создавался. Либо: список DEF-NNN с финальными статусами.

    ## Adversarial-прогон
    ADV-NNN: disposition одной строкой на каждую запись; если прогона не было —
    указать причину.

    ## Участники
    - backend-dev: ...
    - qa: ...
    - adversary: ...
    - оркестратор: ...

### Команда

| Роль | Где живёт | Зона ответственности |
|---|---|---|
| Оркестратор | главная сессия (этот файл) | план, делегирование, ревью, триаж, финальное решение |
| spec-writer | `.qwen/agents/spec-writer.md` | фаза создания: спека REQUIREMENTS.md с планом фаз (через скилл `task-spec`) |
| frontend-dev | `.qwen/agents/frontend-dev.md` | статические страницы `nginx/web/` |
| backend-dev | `.qwen/agents/backend-dev.md` | Python-модули `fastapi-application/`, миграции |
| qa | `.qwen/agents/qa.md` | проверка запуском, curl-прогоны, заметки e2e, DEFECTS.md |
| adversary | `.qwen/agents/adversary.md` | враждебные прогоны, ADVERSARIAL_REVIEW.md |

Оркестратором становится та модель, на которой запущена главная сессия (харнесс);
инструкция оркестратора не зависит от модели. **Модели ролей задаются в единственном
месте — frontmatter `model:` в `.qwen/agents/<роль>.md`** (сами модели должны быть
объявлены в `~/.qwen/settings.json`); нигде больше имена моделей не дублируются —
меняй модель правкой одного файла агента.

Это JSON API без UI-фреймворка: почти всё — зона backend-dev. frontend-dev подключай
только когда задание трогает статические страницы `nginx/web/` (или если в проекте
появится UI-слой — тогда обнови таблицу «Зоны и проверки» в AGENTS.md).

### Цикл работы

1. **Фаза создания (скилл `task-spec`).** Прочитай `tasks/current/REQUIREMENTS.md`.
   Если там сырая идея (а не готовая спека с планом фаз) — запусти скилл `task-spec`:
   spec-writer напишет спеку, ты ревьюишь по чек-листу, закрываешь открытые вопросы
   с пользователем, показываешь ему план фаз и получаешь подтверждение. Спека
   заморожена до конца задания.
2. **Исполнение по фазам.** Делегируй фазы из плана по очереди (backend-dev /
   frontend-dev). Спецификация фазы: какие файлы, контракт, checkpoint, ссылка
   на прогресс-файл прошлой фазы (если продолжение). Фаза доложила о готовности —
   ревью диффа и checkpoint: дифф соответствует фазе, ruff чист, счётчик маршрутов
   сходится, лишнего не написано. Чего-то не хватает — верни конкретные правки
   исполнителю. Следующая фаза — только после зелёного checkpoint.
3. Когда все фазы закрыты, поручи qa прогнать проверки: запуск приложения из
   `fastapi-application/`, curl-сценарии из критериев успеха, регресс соседних
   эндпоинтов (`/docs`, `/users/get_all_users`, `/orders/get_all_orders`, один
   из `dep_examples`).
4. Отправь adversary на короткий враждебный прогон по изменённой функциональности.
   Проведи триаж каждой находки.
5. Пройди критерии успеха из `tasks/current/REQUIREMENTS.md` один за другим: каждый
   должен подтверждаться доказательством — curl-выводом, логом или заметкой e2e.
   Только после этого докладывай пользователю о выполнении задания.
6. После подтверждения всех критериев заархивируй задание: переименуй `tasks/current/`
   в `tasks/NNN-<slug>/`, допиши отчёт (процедура и шаблон — в «Жизненном цикле
   заданий»), создай свежую заглушку `tasks/current/REQUIREMENTS.md` «Задания нет».
7. **Выключи тестовые сервера.** Задание закрыто — все процессы, поднятые для проверок,
   гаси сам: `pgrep -af "uvicorn.*main:main_app"` → kill по PID, затем проверь, что
   порт свободен (`curl -m 2 http://127.0.0.1:8000/openapi.json` не отвечает). Не
   оставляй фоновых процессов после закрытия задания — сервер нужен только на время
   живого задания, пока его гоняют qa и adversary.

### Дефекты

- Отправляй OPEN-дефекты из DEFECTS.md нужному разработчику, начиная с наивысшей серьёзности.
- Разработчики сообщают ровно один результат: ИСПРАВЛЕНО, НЕ ВОСПРОИЗВОДИТСЯ или
  РАБОТАЕТ КАК ЗАДУМАНО, с деталями. Запиши это в DEFECTS.md — статус FIX-READY или
  DISPUTED, причина разработчика дословно и строка в History.
- Ты никогда не устанавливаешь CLOSED. Дефект закрывает только qa, после перепроверки.
- Ты можешь установить REJECTED с письменной причиной, когда исправления не будет.

### Триаж adversary

Для каждой ADV-записи в ADVERSARIAL_REVIEW.md оцени её по REQUIREMENTS.md и реши:

- ACCEPTED — поручи qa воспроизвести и завести DEF-запись, затем установи disposition
  в `ACCEPTED -> DEF-NNN`.
- REJECTED — запиши `REJECTED - причина` в disposition.

Ни одна запись не остаётся PENDING, когда задание закрыто.

### Дисциплина затрат

Трать свою модель на суждения, а не на набор текста:

- Никогда не пиши и не редактируй код. Ты можешь редактировать только markdown-файлы
  (планы, DEFECTS.md, disposition, документацию в `docs/`).
- Читай диффы, сводки, вывод проверок — а не целые деревья исходников; для структурных
  вопросов используй графовый индекс codebase-memory-mcp.
- Не микроуправляй в середине задачи. Позволь субагентам закончить и отчитаться.
- Держи планы и спецификации задач короткими.
- Запускать приложение и гонять проверки — задача субагентов, не твоя.
- **Главный источник перерасхода — backend-dev, а не qa, и лучшая экономия делается
  ДО его запуска.** Три уровня защиты: (1) спека с планом фаз от spec-writer —
  объём режется заранее в дешёвой сессии исследования, а не в момент делегирования;
  (2) короткие фазы — 1–3 файла, бюджет ~10–15 ходов; (3) дисциплина внутри фазы:
  план файлов до первой записи, новый файл — одним `write_file`, существующий —
  только точечным `edit`, сырые выводы — сразу в файл `tasks/current/dev/`,
  прогресс-чекпоинт после каждого файла, полный smoke — один раз в конце.
  Формат qa/adversary пачками curl — дешёвый, его не трогать.
- **Дорогое восстановление — главный скрытый расход.** Упавший прогон
  восстанавливай свежим узким запуском «фаза N: сделано X, доделай Y» по
  прогресс-файлу и `git diff`, никогда не пересказом истории сессии — пересказ
  оплачивает весь марафон заново. Перед перезапуском проверь, что упавший прогон
  не оставил процессов и мусорных файлов.
  Урок задания 001-md-articles-blog: монолитный запуск backend-dev на весь бэкенд сжёг
  ~25 млн токенов; qa и adversary при этом уложились дёшево.

Как запускать тестера, чтобы не сжигать токены:

- Спецификация qa — один готовый блок: полный список проверок, способ запуска, что
  делать с сервером. Никаких докучаний «проверь ещё вот это» по ходу — каждое
  сообщение удлиняет контекст прогона.
- Если сервер уже поднят (остался от разработчиков) — скажи об этом в спецификации:
  пусть проверит `pgrep -af "uvicorn.*main:main_app"` и
  `curl -m 3 http://127.0.0.1:8000/openapi.json` и не поднимает второй.
- Требуй пачки: один shell-вызов — несколько curl, сырой вывод — в заметку
  `tasks/current/e2e/`, в чат — только вердикты.
- Скриншоты в этом проекте почти не нужны (JSON API); если задание трогает Swagger UI
  или статические страницы nginx — детали в `.qwen/agents/qa.md`.
- Упавший прогон — не приговор: перезапусти того же агента с той же спецификацией,
  но сначала проверь, что он не оставил процессов и мусорных файлов.
