# my-fast-react-case — агентный режим

Учебно-демонстрационный проект на **FastAPI 0.111+ / Python 3.12** — исполняемый каталог
приёмов, а не продуктовый сервис, — с внедрённым **агентным режимом**: задания по развитию
проекта выполняет команда агентов Qwen Code — оркестратор плюс субагенты на разных моделях.

Проект сознательно совмещает **две части**:
hh
1. **Демонстрационная** (`api/`) — показывает варианты одного и того же решения рядом:
   четыре способа извлечения параметров HTTP-запроса (один эндпоинт
   `/my_items/{item_id}` в четырёх стилях), девять способов `Depends`, два стиля
   объявления pydantic-полей, два способа валидации.
2. **Рабочая** (`ex_user_post/`, `ex_order_product/`, `db_core/`) — асинхронный слой данных
   на SQLAlchemy 2.0 (`AsyncSession`, `asyncpg`/`aiosqlite`) с миграциями Alembic и двумя
   предметными областями: `User`/`Post` (one-to-many) и `Order`/`Product` (many-to-many).
3. **Блог** (`md_articles/` + `frontend/`) — React SPA на JSON API `/api/blog`:
   статьи из YAML-реестра с серверным Markdown-рендером и клиентской подсветкой
   highlight.js, вход/регистрация/аккаунт (cookie-сессии, bcrypt, аватары),
   управление реестром. Детали по архитектуре блога — в
   [`docs/11_md_articles.md`](docs/11_md_articles.md).

> Дублирование маршрутов и обработчиков в `api/` **намеренное** — сравнивать файлы
> построчно и есть учебная цель. Не «рефакторьте» это в общий код.
> Язык комментариев, docstring'ов и документации — **русский**.

## Агентный режим

Проект развивается командой агентов Qwen Code по одному заданию за раз:

| Файл | Назначение |
|---|---|
| [QWEN.md](QWEN.md) | контекст проекта + инструкции оркестратора (главная сессия) |
| [AGENTS.md](AGENTS.md) | контекст проекта + правила команды, процесс дефектов |
| [tasks/current/REQUIREMENTS.md](tasks/current/REQUIREMENTS.md) | **текущее задание** команды + его рабочие артефакты |
| [tasks/](tasks/) | архив закрытых заданий: `NNN-<slug>/` — задание, отчёт и все доказательства в одной папке |
| `.qwen/agents/` | субагенты: spec-writer, frontend-dev, backend-dev, qa, adversary (модели — в frontmatter `model:` этих файлов) |
| [docs/](docs/) | подробная документация по проекту (15 файлов, рус.) |

Схема работы: пользователь кладёт задание в `tasks/current/REQUIREMENTS.md` и запускает
Qwen Code в корне проекта. Главная сессия (оркестратором становится модель, с которой
запущен харнесс) по `QWEN.md` действует как
оркестратор: пишет план, делегирует разработку субагентам, проверяет доказательства,
отправляет qa проверить работу запуском и curl-сценариями, adversary — враждебный
прогон; всё о живом задании — дефекты, находки, сценарии — создаётся в той же папке
`tasks/current/`. Когда все критерии успеха подтверждены, задание закрывается:
оркестратор переименовывает папку в `tasks/NNN-<slug>/` и дописывает в `REQUIREMENTS.md`
секцию «Отчёт о выполнении» (итог, изменения, критерии с доказательствами, дефекты,
disposition adversary, участники), а в свежую заглушку `tasks/current/REQUIREMENTS.md`
пользователь кладёт следующее. В корне проекта файлов заданий нет.

Модели команды задаются в единственном месте — frontmatter `model:` в файлах
`.qwen/agents/<роль>.md` (spec-writer, backend-dev, frontend-dev, qa, adversary);
оркестратор — модель главной сессии. Смена модели роли = правка одного файла агента.
Сами модели должны быть объявлены в `~/.qwen/settings.json` (authType `openai`).

Комплект переносим: чтобы внедрить агентный режим в другой проект, скопируйте эти файлы
и `.qwen/`, а затем адаптируйте проектный контекст в `README.md`, `QWEN.md`, `AGENTS.md`
под новый проект. `tasks/current/REQUIREMENTS.md` каждый раз получает задание нового
проекта, архив `tasks/` начинается пустым.

## Возможности

- 41 route-объект: 21 API-эндпоинт плюс служебные `/docs`, `/redoc`,
  `/openapi.json`, `/docs/oauth2-redirect` (кастомный Swagger/ReDoc на CDN через
  `utils/docs.py`) + 13 JSON-роутов блога `/api/blog` + mount `/static` (аватары),
  mount `/assets` (сборка фронтенда) и SPA catch-all `/{full_path:path}`.
- Демонстрация 9 способов `Depends`: функции, классы с `__call__`, метод-генератор с
  teardown, фабрики зависимостей, вложенные зависимости.
- Один эндпоинт `/my_items/{item_id}` в четырёх стилях: `Path()/Query()/Header()/Cookie()`
  как default-значения, то же через `Annotated`, параметры в классах, параметры в функциях.
- Async-слой данных: `AsyncDbManager` + DI-алиас `CurrentSession`, SQLite и PostgreSQL
  через один `APP__DB__URL`, `PRAGMA foreign_keys=ON` для SQLite.
- Миграции Alembic (3 ревизии: users/posts, orders/products/association,
  blog_user/blog_post) с асинхронным runner'ом.
- Блог `md_articles/` + `frontend/`: React SPA (Vite + TypeScript + Tailwind CSS v4)
  на JSON API `/api/blog`, cookie-сессии (14 дней), bcrypt, CSRF, аватары с
  Pillow-миниатюрой 125×125, Markdown-рендер статей на сервере, 4 темы сайта и
  15 тёмных тем подсветки highlight.js — переключение без перезагрузки.
- Своя подсистема логирования `ConfigLogger` на `logging.config.dictConfig` (файл+stdout).
- gunicorn + UvicornWorker для multi-worker запуска; nginx с TLS — в Docker-стеке.

## Стек

| Область | Выбор |
|---|---|
| Язык | Python 3.12 (`.python-version`) |
| Менеджер пакетов | `uv` (`uv.lock` — источник истины) |
| Веб-фреймворк | FastAPI 0.111+ (ORJSONResponse по умолчанию) |
| Валидация / конфигурация | Pydantic 2 + pydantic-settings (префикс `APP__`) |
| ORM | SQLAlchemy 2.0 async (`asyncpg` / `aiosqlite`) |
| Миграции | Alembic (асинхронный env.py) |
| ASGI-сервер | uvicorn (dev), gunicorn + UvicornWorker (multi-worker) |
| Сериализация | orjson |
| Фронтенд блога | React 18 + TypeScript + Vite 6 + Tailwind CSS v4 + React Router 6 (в `frontend/`) |
| Линтеры | ruff + black (объявлены в зависимостях) |

## Быстрый старт (локально)

```bash
uv sync                      # создаёт .venv по uv.lock
```

Профиль БД выбирается в `fastapi-application/core/config.py` (поле `env_file` класса
`Settings`): по умолчанию активен `dev_sqlite.env` — SQLite (`sqlite+aiosqlite:///./one_simple.db`),
никакой внешней БД не нужно. Профиль PostgreSQL (`prod_db.env`,
`postgresql+asyncpg://user:password@localhost:5432/shop`) включается раскомментированием
строки в `env_file`; файл `.env`, если существует, перекрывает оба.

Запуск приложения (из каталога `fastapi-application/`):

```bash
cd fastapi-application
../.venv/bin/uvicorn main:main_app --host 0.0.0.0 --port 8000 --reload    # предпочтительно
../.venv/bin/python main.py                                               # то же + баннер в лог
# из корня проекта: make run_app11_lin  (uvicorn --app-dir fastapi-application)
```

> ⚠️ **cwd имеет значение.** Файл SQLite `./one_simple.db` и относительные пути
> резолвятся от рабочего каталога: запуск из корня через `--app-dir` создаст базу в корне
> проекта, а не в `fastapi-application/`. Логи при этом всегда пишутся в
> `fastapi-application/log/` (путь привязан к `BASE_DIR`). Предпочтителен запуск из
> `fastapi-application/`. Swagger: <http://127.0.0.1:8000/docs>.

Фронтенд блога собирается отдельно — сборка `frontend/dist` **не коммитится**:

```bash
cd frontend && npm install && npm run build   # → frontend/dist
```

Без сборки JSON API (`/api/blog/*`) и Swagger работают, а SPA-страницы (`/`,
`/art/...`) отвечают 404 JSON с подсказкой выполнить `npm run build`. Dev-режим
фронтенда — два процесса: `cd frontend && npm run dev` (порт 5173, Vite проксирует
`/api` и `/static` на `:8000`), бэкенд — как выше.

Для PostgreSQL поднимите dev-стек из `docker-compose.yml` (pg на `5432`, adminer на
`8080`, pgadmin на `5050`; креды `user/password`, база `shop`) и переключите профиль на
`prod_db.env`.

## Запуск агентного режима

1. Убедитесь, что модели, указанные в frontmatter `model:` файлов `.qwen/agents/`,
   объявлены в `~/.qwen/settings.json` (authType `openai`); оркестратор — модель,
   с которой запущена главная сессия.
2. Поднимите приложение (см. «Быстрый старт» — для SQLite внешний сервис не нужен) —
   агентам нужен работающий URL для проверок.
3. Запустите `qwen-code` в корне проекта. `QWEN.md` превратит главную сессию в
   оркестратора; субагенты подхватятся из `.qwen/agents/`.
4. Дайте команду:

   > Выполни текущее задание из tasks/current/REQUIREMENTS.md и не останавливайся,
   > пока все критерии успеха не будут подтверждены доказательствами.

Пока команда работает: дефекты появляются в `tasks/current/DEFECTS.md`, находки
adversary — в `tasks/current/ADVERSARIAL_REVIEW.md`, сценарии и сырые выводы проверок —
в `tasks/current/e2e/`. Закрытые задания лежат в `tasks/NNN-<slug>/` — целиком, с
отчётом о выполнении.

## Конфигурация

Вся конфигурация — вложенные pydantic-модели в `fastapi-application/core/config.py`,
читаются из env-файлов с префиксом `APP__` и разделителем `__` (например,
`APP__DB__URL`, `APP__RUN__PORT`, `APP__GUNICORN__WORKERS`). Единственное обязательное
поле — `db.url`.

| Переменная | Обязательна | По умолчанию / профиль |
|---|---|---|
| `APP__DB__URL` | да | `dev_sqlite.env`: sqlite, `prod_db.env`: postgres |
| `APP__DB__ECHO` | нет | `0` |
| `APP__RUN__HOST` / `APP__RUN__PORT` | нет | `0.0.0.0` / `8000` |
| `APP__GUNICORN__WORKERS` | нет | `1` |
| `APP__WEB__SECRET_KEY` | нет | dev-значение (подпись сессий блога) |

Env-файлы лежат в `fastapi-application/` и **закоммичены** (`prod_db.env`, `dev_sqlite.env`) — это
учебный проект без секретов; `.env` (если создаёте) тоже в каталоге приложения и имеет
высший приоритет.

## Маршруты

41 route-объект всего (проверка: `cd fastapi-application && ../.venv/bin/python -c "from main import main_app; print(len(main_app.routes))"` → `41`; 21 API + 4 служебных (`/docs`, `/redoc`, `/openapi.json`, `/docs/oauth2-redirect`) + 13 JSON-роутов блога (`/api/blog/csrf`, `/current_user`, `/register`, `/login`, `/logout`, `/account` ×2, `/sections`, `/articles`, `/articles/{id}`, `/art_manage`, `/art_manage/add_all`, `/art_manage/meta`) + mount `/static` + mount `/assets` + SPA catch-all).

| Методы | Маршрут | Назначение |
|---|---|---|
| GET | `/docs`, `/redoc`, `/docs/oauth2-redirect`, `/openapi.json` | служебные (кастомный Swagger/ReDoc) |
| GET | `/api/v1/dep_examples/*` (9 роутов) | демонстрация механики `Depends` |
| GET | `/api/v1/{fastapi_class_old,fastapi_class_annotated,depends_class_annotated,depends_function_annotated}/my_items/{item_id}` | один эндпоинт в четырёх стилях |
| GET | `/users/get_all_users`, POST `/users/create_user` | домен User/Post (CRUD-слой) |
| POST | `/orders/add_order`, `/orders/insert_order` | запись Order (ORM- и Core-путь) |
| GET | `/orders/get_order_filter_by`, `/get_order_where`, `/get_all_orders`, `/get_all_join` | чтение Order (фильтры, сортировка, joinedload) |
| GET | `/api/blog/csrf`, `/api/blog/current_user` | блог: CSRF-токен и текущий пользователь |
| POST | `/api/blog/register`, `/api/blog/login`, `/api/blog/logout` | блог: регистрация, вход, выход (CSRF, bcrypt) |
| GET/POST | `/api/blog/account` | блог: аккаунт и аватар (multipart, CSRF полем формы) |
| GET | `/api/blog/articles`, `/api/blog/articles/{art_id}` | блог: список статей и статья (Markdown → HTML на сервере) |
| GET | `/api/blog/art_manage`; POST `.../add_all`, `.../meta` | блог: управление реестром статей (авторизация + CSRF) |
| GET | `/static/*` | статика аватаров (StaticFiles) |
| GET | `/assets/*` | сборка фронтенда `frontend/dist/assets` (StaticFiles) |
| GET | `/{full_path:path}` | SPA catch-all → `frontend/dist/index.html`; `/api*` → 404 JSON |

## Модель данных

```python
User(id, firstname, surname, nickname UNIQUE, password) -> posts
Post(id, title, body, created_at, user_id FK -> users.id CASCADE)
Order(id, promo, count_total) <-> OrderProductAssociation(order_id, product_id, count, unit_price)
Product(id, promo, title, description, price)
BlogUser(id, username UNIQUE(20), email UNIQUE(120), image_file, password(60)) -> posts
BlogPost(id, title(100), date_posted, content, user_id FK -> blog_user.id)
```

`__tablename__` генерируется автоматически из имени класса (`CamelCase` → `snake_case`);
`OrderProductAssociation` переопределяет его вручную. Миграции: 3 ревизии Alembic в
`fastapi-application/alembic/versions/`. Реестр статей блога — `md_articles/articles.yaml`
(контент-статьи `.md` пользователь кладёт в `fastapi-application/content_art/`).

## Запуск в Docker

Два стека:

```bash
# dev: postgres + adminer + pgadmin (креды внутри файла)
docker compose up -d

# прод-подобный: pg + pgadmin + redis + nginx (TLS)
make create-net                 # внешняя сеть app_net_new 172.20.0.0/16
docker compose -f nginx_pg_admin.yml up -d
```

`nginx_pg_admin.yml` требует `.env` рядом с compose-файлом (`DB_USER`, `DB_PASSWORD`,
`DB_NAME`, `PGADMIN_EMAIL`, `PGADMIN_PASSWORD`) и self-signed сертификаты в
`nginx/cert/` (в `.gitignore`); `nginx.conf` ссылается на `xaphan.ru`. Доступ: nginx
на `:443`, pg на `127.0.0.1:7032`, redis на `:7079`.

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

## Индекс кодовой базы

Для структурных запросов по коду (кто вызывает функцию, что она вызывает, мёртвый код,
анализ влияния изменений) используйте графовый индекс через **codebase-memory-mcp** —
это быстрее и точнее, чем обход исходников вручную. Скилл `codebase-memory` описывает
доступные MCP-инструменты (`search_graph`, `trace_path`, `detect_changes` и др.).
Перед структурным исследованием проверяйте наличие/свежесть индекса через `index_status`.

## Линтеры и проверка изменений

```bash
uv run ruff check .                                                        # линтер (ruff в зависимостях)
cd fastapi-application && ../.venv/bin/python -c "from main import main_app; print(len(main_app.routes))"   # 42
cd fastapi-application && ../.venv/bin/uvicorn main:main_app --port 8000    # затем curl /docs, /users/get_all_users, /api/blog/articles, /
```

Тестов нет — изменения проверяются запуском приложения и curl-запросами. Подробные
соглашения, грабли и правила для агентов см. в [AGENTS.md](AGENTS.md).
