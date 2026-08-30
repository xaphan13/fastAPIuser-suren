# FastAPI User Management App

Серверное веб-приложение на **FastAPI** (Python ≥ 3.12), реализующее полноценную подсистему управления пользователями: регистрация, аутентификация (cookie-based с хранением токенов в БД), верификация email, сброс пароля, ролевой доступ (user / superuser), кэширование в Redis, HTML-страницы (Jinja2), email-уведомления, исходящие вебхуки и административная панель (SQLAdmin).

> 📚 **Подробная документация находится в каталоге [`docs/`](docs/)** — начните с [`docs/01_project_structure.md`](docs/01_project_structure.md).

## Возможности

- ✅ Регистрация и аутентификация через [`fastapi-users`](https://github.com/fastapi-users/fastapi-users) (Cookie-транспорт + Database-стратегия, токены в PostgreSQL)
- ✅ Верификация email (двухфазная: запрос токена → подтверждение по ссылке)
- ✅ Сброс пароля
- ✅ Ролевой доступ: `current_active_user` / `current_active_superuser`
- ✅ Кэширование списка пользователей в Redis (TTL 60s, `fastapi-cache2`) с инвалидацией при регистрации
- ✅ HTML-страницы: `/home/`, `/verify-email/` (Jinja2 + Bootstrap 5)
- ✅ Email-уведомления через aiosmtplib (рендер Jinja2-шаблонов)
- ✅ Исходящие вебхуки (aiohttp) + декларативные OpenAPI webhooks
- ✅ Административная панель SQLAdmin (`/admin`)
- ✅ Кастомные Swagger UI / ReDoc, ORJSONResponse, Gunicorn для production

## Технологический стек

| Слой | Технологии |
|---|---|
| Фреймворк | FastAPI, Starlette, Pydantic v2, pydantic-settings |
| БД | PostgreSQL 17 (asyncpg), SQLAlchemy 2 (async), Alembic |
| Аутентификация | fastapi-users[sqlalchemy] |
| Кэш | Redis 8, fastapi-cache2 |
| Шаблоны / Email | Jinja2, aiosmtplib (Maildev в dev) |
| HTTP-клиент | aiohttp (вебхуки) |
| Сервер | Uvicorn (dev), Gunicorn + UvicornWorker (prod) |
| Качество кода | ruff, black (line-length 120) |

## Структура проекта

```
fastAPIuser-suren/
├── docs/                        # 📚 Документация (7 файлов, см. ниже)
├── docker-compose.yml           # PostgreSQL 17, Redis 8, Maildev
├── pyproject.toml               # Зависимости, конфиг ruff/black
└── fastapi-application/         # Приложение (рабочая директория для запуска)
    ├── main.py                  # ASGI-приложение `main_app`, подключение роутеров
    ├── create_fastapi_app.py    # Фабрика приложения: lifespan, middleware, admin, docs
    ├── run_main.py / run        # Production-запуск через Gunicorn
    ├── core/                    # Конфиг, модели SQLAlchemy, схемы, аутентификация, gunicorn
    ├── api/                     # Роутеры /api/v1, DI-провайдеры, webhooks
    ├── views/                   # HTML-страницы (Jinja2)
    ├── middlewares/             # CORS, X-Process-Time, логирование, счётчик запросов
    ├── admin/                   # SQLAdmin ModelViews
    ├── mailing/                 # Отправка email (SMTP)
    ├── utils/                   # Утилиты, вебхуки
    ├── actions/                 # CLI (create_superuser)
    ├── alembic/                 # Миграции
    └── templates/               # Jinja2-шаблоны (страницы + email)
```

## Документация

| Файл | Содержание |
|---|---|
| [`docs/01_project_structure.md`](docs/01_project_structure.md) | Карта проекта, дерево файлов, внешние зависимости |
| [`docs/02_architecture.md`](docs/02_architecture.md) | Архитектура, паттерны проектирования, поток данных |
| [`docs/03_execution_flow.md`](docs/03_execution_flow.md) | Жизненный цикл приложения, бизнес-процессы, карта роутов, middleware |
| [`docs/04_code_quality.md`](docs/04_code_quality.md) | Оценка качества, технический долг |
| [`docs/05_optimization_roadmap.md`](docs/05_optimization_roadmap.md) | Дорожная карта развития, предложения по улучшению |
| [`docs/06_frontend_bootstrap_analysis.md`](docs/06_frontend_bootstrap_analysis.md) | Анализ frontend-части (Bootstrap, шаблоны) |
| [`docs/07_authorization_report.md`](docs/07_authorization_report.md) | Отчёт по авторизации и ролевому доступу |

## Быстрый старт

### 1. Инфраструктура

```shell
docker compose up -d        # PostgreSQL 17 :5432, Redis 8 :6379, Maildev
```

| Сервис | Адрес |
|---|---|
| PostgreSQL | `localhost:5432` (db: `shop`, user: `user`, pass: `password`) |
| Redis | `localhost:6379` |
| Maildev (web) | http://localhost:8080 |
| Maildev (SMTP) | `localhost:1025` |

### 2. Переменные окружения

```shell
cd fastapi-application
cp .env.template .env       # затем заполните секреты
```

Обязательные переменные (без дефолтов):

```env
APP_CONFIG__DB__URL=postgresql+asyncpg://user:password@localhost:5432/shop
APP_CONFIG__ACCESS_TOKEN__RESET_PASSWORD_TOKEN_SECRET=<сгенерируйте>
APP_CONFIG__ACCESS_TOKEN__VERIFICATION_TOKEN_SECRET=<сгенерируйте>
```

Конфигурация читается через `pydantic-settings`: префикс `APP_CONFIG__`, вложенность через `__` (например, `APP_CONFIG__GUNICORN__WORKERS`). Полное описание — в [`docs/02_architecture.md`](docs/02_architecture.md).

### 3. Миграции и суперпользователь

```shell
cd fastapi-application
uv run alembic upgrade head

# создание суперпользователя (env: DEFAULT_EMAIL, DEFAULT_PASSWORD)
uv run python -m actions.create_superuser
```

### 4. Запуск

Development (uvicorn с reload):

```shell
cd fastapi-application
uv run python main.py
```

Production (gunicorn):

```shell
./run
# или
python run_main.py
# или напрямую
gunicorn main:main_app --workers 4 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

### 5. Проверка

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- Админ-панель: http://localhost:8000/admin

```shell
# preflight CORS-проверка
http OPTIONS http://localhost:8000/api/v1/auth/login 'Access-Control-Request-Method:GET' 'Origin: http://localhost:8000'
```

## Основные эндпоинты

| Метод | Путь | Доступ | Описание |
|---|---|---|---|
| POST | `/api/v1/auth/register` | — | Регистрация |
| POST | `/api/v1/auth/login` | — | Вход (cookie `fastapiusersauth`) |
| POST | `/api/v1/auth/logout` | user | Выход |
| POST | `/api/v1/auth/request-verify-token` | user | Запрос токена верификации |
| POST | `/api/v1/auth/verify` | — | Подтверждение email |
| POST | `/api/v1/auth/forgot-password` | — | Запрос сброса пароля |
| POST | `/api/v1/auth/reset-password` | — | Сброс пароля |
| GET | `/api/v1/users` | bearer | Список пользователей (кэш 60s) |
| GET | `/api/v1/users/me` | user | Текущий пользователь |
| GET/PATCH/DELETE | `/api/v1/users/{id}` | superuser | Управление пользователем |
| GET | `/api/v1/service/stats` | bearer | Статистика запросов |
| GET | `/home/` | user | HTML-страница пользователя |
| GET | `/verify-email/` | — | HTML-страница верификации |

Полная карта роутов с описанием — в [`docs/03_execution_flow.md`](docs/03_execution_flow.md).

## Разработка

```shell
# линтинг и форматирование
uv run ruff check .
uv run ruff format .
uv run black .
```

Конфигурация ruff/black — в `pyproject.toml` (line-length 120).

## Полезные ссылки

- fastapi-users: [GitHub](https://github.com/fastapi-users/fastapi-users) · [Docs](https://fastapi-users.github.io/fastapi-users/latest/)
- Базовый шаблон проекта: [FastAPI-base-app](https://github.com/mahenzon/FastAPI-base-app)
