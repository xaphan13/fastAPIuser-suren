# 02 — Архитектура и паттерны

## Высокоуровневая архитектура

Проект представляет собой **слоистый монолит** на FastAPI с асинхронным I/O на всех уровнях. Слои разделены по директориям и связаны через FastAPI Dependency Injection.

```
┌─────────────────────────────────────────────────────────┐
│                    Клиент (HTTP / Browser)               │
└────────────┬──────────────────────────┬─────────────────┘
             │                          │
     ┌───────▼────────┐        ┌───────▼────────┐
     │  API /api/v1/* │        │  Views /home,  │
     │  (JSON, ORJSON)│        │  /verify-email │
     │  auth/users/   │        │  (Jinja2 HTML) │
     │  messages/     │        │                │
     │  service/      │        │                │
     └───────┬────────┘        └───────┬────────┘
             │                          │
     ┌───────▼──────────────────────────▼───────┐
     │           Middleware-стек                  │
     │  CORS → ProcessTime → Log → RequestsCount │
     └───────────────────┬───────────────────────┘
                         │
     ┌───────────────────▼───────────────────────┐
     │        Dependency Injection (FastAPI)      │
     │  get_users_db → get_user_manager →         │
     │  get_access_tokens_db → get_database_      │
     │  strategy → authentication_backend         │
     └───────┬───────────────────┬───────────────┘
             │                   │
     ┌───────▼───────┐   ┌──────▼──────────┐
     │  core/models  │   │  core/auth/     │
     │  SQLAlchemy   │   │  fastapi_users  │
     │  async ORM    │   │  UserManager    │
     └───────┬───────┘   └──────┬──────────┘
             │                  │
     ┌───────▼──────────────────▼───────────────┐
     │     PostgreSQL 17 (asyncpg)              │
     │     таблицы: users, access_tokens        │
     └───────────────────────────────────────────┘

     ┌───────────────────────────────────────────┐
     │     Redis 8 (fastapi-cache2)              │
     │     namespace: fastapi-cache:users-list   │
     └───────────────────────────────────────────┘

     ┌───────────────────────────────────────────┐
     │     SMTP (Maildev :1025)                  │
     │     aiosmtplib → email-verify шаблоны     │
     └───────────────────────────────────────────┘

     ┌───────────────────────────────────────────┐
     │     Внешний вебхук (aiohttp → httpbin)    │
     └───────────────────────────────────────────┘
```

---

## Основные паттерны проектирования

### 1. Factory (Фабрика приложения)

Файл: `fastapi-application/create_fastapi_app.py` → `create_app()`

Функция-фабрика создаёт и конфигурирует `FastAPI`-инстанс: регистрирует lifespan, middleware, error handlers, admin-панель, кастомные docs-роуты. Параметр `create_custom_static_urls` управляет режимом документации.

### 2. Dependency Injection (Внедрение зависимостей)

Центральный паттерн проекта. Все ресурсы (DB-сессии, user DB, access-token DB, user manager, strategy) предоставляются через цепочку `Depends`:

```
db_helper.session_getter          (core/models/db_helper.py)
  └─> get_users_db                (api/dependencies/authentication/users.py)
        └─> get_user_manager      (api/dependencies/authentication/user_manager.py)
  └─> get_access_tokens_db        (api/dependencies/authentication/access_tokens.py)
        └─> get_database_strategy (api/dependencies/authentication/strategy.py)
              └─> authentication_backend (api/dependencies/authentication/backend.py)
```

Каждый провайдер — асинхронный генератор (`yield`), обеспечивающий корректное закрытие сессии.

### 3. Repository (через fastapi-users)

Классы `SQLAlchemyUserDatabase` (`core/models/user.py`) и `SQLAlchemyAccessTokenDatabase` (`core/models/access_token.py`) инкапсулируют доступ к данным. Метод `get_db()` — фабрика репозитория из сессии. Кастомный метод `get_users()` расширяет базовый репозиторий.

### 4. Mixin (Примесь)

`IdIntPkMixin` (`core/models/mixins/id_int_pk.py`) — примесь для авто-добавления `id: Mapped[int]` PK. Используется моделью `User` через множественное наследование.

### 5. Strategy (Стратегия аутентификации)

`fastapi-users` использует паттерн Strategy: транспорт (`CookieTransport` / `BearerTransport`) и стратегия (`DatabaseStrategy`) комбинируются в `AuthenticationBackend`. Текущая конфигурация — **Cookie-транспорт + DB-стратегия** (токены хранятся в таблице `access_tokens`).

### 6. Singleton (Одиночка)

- `settings` (`core/config.py`) — единственный экземпляр `Settings`.
- `db_helper` (`core/models/db_helper.py`) — единственный `DatabaseHelper` с engine и session_factory.
- `templates` (`jinja_templates.py`) — единственный `Jinja2Templates`.
- `requests_count_middleware_dispatch` (`middlewares/requests_count_middleware.py`) — единственный счётчик.

### 7. Observer / Hook (Хуки жизненного цикла)

`UserManager` (`core/authentication/user_manager.py`) реализует хуки `on_after_register`, `on_after_forgot_password`, `on_after_request_verify`, `on_after_verify` — вызываются библиотекой `fastapi-users` после соответствующих операций. Внутри хуков запускаются `BackgroundTasks` (инвалидация кэша, отправка email, вебхуки).

### 8. Adapter (Адаптер)

`Application` (`core/gunicorn/application.py`) адаптирует FastAPI-приложение к интерфейсу Gunicorn `BaseApplication`, реализуя `load()` и `load_config()`.

---

## Схема потока данных (Data Flow)

### Пример: Регистрация пользователя (`POST /api/v1/auth/register`)

```
1. HTTP-запрос → FastAPI ASGI (uvicorn/gunicorn)
2. Middleware-стек (в порядке добавления, обратном выполнению):
   a. RequestsCountMiddleware — инкремент счётчика пути
   b. ProcessTimeHeaderMiddleware — старт таймера
   c. CORS — проверка origin
   d. log_new_requests — логирование метода и пути
   e. add_process_time_to_requests — X-Process-Time header
3. Роутинг: /api → /api/v1 → auth_router → fastapi_users.get_register_router
4. FastAPI разрешает зависимости:
   a. HTTPBearer (auto_error=False) — извлечение токена (опционально)
   b. db_helper.session_getter → AsyncSession
   c. get_users_db → SQLAlchemyUserDatabase(session, User)
   d. get_user_manager → UserManager(users_db, background_tasks)
5. UserManager.create(user_create) →
   a. Хэширование пароля (PasswordHelper)
   b. SQLAlchemyUserDatabase → INSERT INTO users
   c. COMMIT
6. on_after_register(user):
   a. BackgroundTask: FastAPICache.clear(namespace="users-list") → Redis DEL
   b. Логирование (log.warning)
   c. await send_new_user_notification(user) → aiohttp POST → httpbin.org
7. Ответ: ORJSONResponse → UserRead (Pydantic-схема)
8. Middleware: X-Process-Time, X-Process-Time-New-Again headers добавлены
9. RequestsCountMiddleware: статус-код записан
```

### Пример: Получение списка пользователей (`GET /api/v1/users`)

```
1. HTTP-запрос → Middleware-стек → роутинг
2. @cache(expire=60, key_builder=users_list_key_builder, namespace="users-list")
   a. key_builder формирует MD5-ключ из модуля:функции:args:kwargs
      (исключая SQLAlchemyUserDatabase из ключа)
   b. Проверка Redis: если есть — возврат кэшированного JSON
3. Cache miss → get_users_db → SQLAlchemyUserDatabase.get_users()
   → SELECT * FROM users ORDER BY id
4. Результат: [UserRead.model_validate(user) for user in users]
5. Запись в Redis (TTL 60s, namespace "users-list")
6. ORJSONResponse
```

### Пример: Верификация email

```
1. POST /api/v1/auth/request-verify-token (тело: {email})
   → fastapi_users генерирует verification token
   → on_after_request_verify:
     a. request.url_for("verify_email") + token → verification_link
     b. BackgroundTask: send_verification_email(user, link)
        → Jinja2 рендер verification-request.html
        → aiosmtplib.send → Maildev SMTP :1025

2. Пользователь кликает по ссылке → GET /verify-email/?token=...
   → Jinja2 verification.html (JS)
   → JS: POST /api/v1/auth/verify (тело: {token})
   → on_after_verify:
     a. BackgroundTask: send_email_confirmed(user)
        → Jinja2 рендер email-verified.html → SMTP
```

---

## Управление состоянием

### Состояние приложения

| Тип | Хранение | Механизм |
|---|---|---|
| Данные пользователей | PostgreSQL, таблица `users` | SQLAlchemy async ORM |
| Токены авторизации | PostgreSQL, таблица `access_tokens` | `DatabaseStrategy` (fastapi-users) |
| Кэш списка пользователей | Redis, DB 0 | `fastapi-cache2` + `RedisBackend` |
| Счётчик запросов | In-memory (процесс) | `RequestsCountMiddlewareDispatch` (dataclass + defaultdict) |
| Сессии БД | Async connection pool | `async_sessionmaker` (pool_size=50, max_overflow=10) |

### Кэширование

- **Backend**: Redis (`fastapi-application/create_fastapi_app.py` → `lifespan`)
- **Инициализация**: при старте приложения в `lifespan` через `FastAPICache.init(RedisBackend(redis), prefix="fastapi-cache")`
- **Использование**: декоратор `@cache` на `GET /api/v1/users` (`api/api_v1/users.py`)
- **Инвалидация**: `FastAPICache.clear(namespace="users-list")` в `on_after_register` (`core/authentication/user_manager.py`)
- **Ключ**: `users_list_key_builder` — MD5-хэш от `module:func:args:kwargs`, исключая DB-объекты

### Управление конфигурацией

Файл: `fastapi-application/core/config.py` → `Settings(BaseSettings)`

- **Источник**: `.env.template` (дефолт), затем `.env` (переопределение)
- **Префикс**: `APP_CONFIG__`
- **Вложенный делимитер**: `__` (например, `APP_CONFIG__DB__URL`)
- **Чувствительность к регистру**: отключена (`case_sensitive=False`)
- **Обязательные поля** (без дефолта): `db.url`, `access_token.reset_password_token_secret`, `access_token.verification_token_secret`

Подконфигурации:

| Класс | Назначение | Ключевые поля |
|---|---|---|
| `RunConfig` | Dev-запуск (uvicorn) | host, port |
| `GunicornConfig` | Production-запуск | host, port, workers, timeout |
| `LoggingConfig` | Логирование | log_level, log_format |
| `ApiPrefix` | URL-префиксы | /api/v1/{auth,users,messages,service} |
| `DatabaseConfig` | Подключение к БД | url, echo, pool_size, naming_convention |
| `AccessToken` | Токены | lifetime_seconds, reset_password_token_secret, verification_token_secret |
| `RedisConfig` | Redis | host, port, db.cache |
| `CacheConfig` | Кэш | prefix, namespace.users_list |
