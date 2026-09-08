# 03 — Логика и работа кода

## Жизненный цикл приложения

### Инициализация (startup)

Точка входа определяется способом запуска:

| Способ | Файл | ASGI-сервер | Режим |
|---|---|---|---|
| `python run` или `python run_main.py` | `fastapi-application/run_main.py` | Gunicorn + UvicornWorker | Production |
| `python main.py` | `fastapi-application/main.py` | Uvicorn (reload=True) | Development |
| `gunicorn main:main_app --workers 4 ...` | — | Gunicorn (внешний) | Production |

**Последовательность инициализации:**

```
1. Импорт core/config.py → settings = Settings()
   └─ Чтение .env.template → .env → валидация pydantic-settings
2. Импорт main.py:
   a. logging.basicConfig(level, format) из settings.logging
   b. create_app(create_custom_static_urls=True):
      ├─ FastAPI(default_response_class=ORJSONResponse, lifespan=lifespan, webhooks=webhooks_router)
      ├─ register_static_docs_routes(app) → /docs, /redoc, /docs/oauth2-redirect
      ├─ register_errors_handlers(app) → ValidationError, DatabaseError
      ├─ register_middlewares(app) → log, process-time, CORS, process-time-new, requests-count
      ├─ Admin(app, session_maker=db_helper.session_factory)
      └─ register_admin_views(admin) → UserAdmin, AccessTokenAdmin
   c. main_app.include_router(api_router)   → /api/v1/*
   d. main_app.include_router(views_router)  → /home, /verify-email
3. Запуск ASGI-сервера:
   ├─ Gunicorn: Application.load() → main_app, config_options → cfg
   └─ Uvicorn: uvicorn.run("main:main_app", reload=True)
4. lifespan(app) — startup-фаза:
   a. Redis(host, port, db=0) — создание async-клиента
   b. FastAPICache.init(RedisBackend(redis), prefix="fastapi-cache")
   c. yield — приложение готово к обслуживанию запросов
```

### Завершение работы (shutdown)

```
lifespan(app) — shutdown-фаза (после yield):
  └─ await db_helper.dispose()
       └─ await self.engine.dispose()  # закрытие всех соединений в пуле
```

> **Важно**: Redis-клиент не закрывается явно в `lifespan`. Соединение закрывается неявно при завершении event-loop. См. раздел «Технический долг» в `04_code_quality.md`.

---

## Ключевые бизнес-процессы

### 1. Регистрация пользователя

**Эндпоинт**: `POST /api/v1/auth/register` (роутер из `fastapi_users.get_register_router`)

```
Шаг 1: Клиент отправляет {email, password} (схема UserCreate)
Шаг 2: FastAPI резолвит Depends:
       get_users_db → get_user_manager
Шаг 3: UserManager.create(user_create, safe=True)
       ├─ Валидация email (уникальность)
       ├─ PasswordHelper.hash(password)
       ├─ INSERT INTO users (email, hashed_password, is_active, is_superuser, is_verified)
       │   # safe=True: поля is_superuser/is_verified из запроса отбрасываются —
       │   # клиент не может сам себя сделать суперпользователем (safe=False
       │   # используется только в actions/create_superuser.py)
       └─ COMMIT
Шаг 4: on_after_register(user):
       ├─ Инвалидация кэша: FastAPICache.clear(namespace="users-list")
       │   ├─ Если есть background_tasks → BackgroundTask (неблокирующе)
       │   └─ Иначе → await (блокирующе)
       ├─ log.warning("User %r has registered.", user.id)
       └─ await send_new_user_notification(user)
            └─ aiohttp POST → https://httpbin.org/post
               тело: {user: UserRead, ts: int}
Шаг 5: Ответ 201 → UserRead (email, id, is_active, is_superuser, is_verified)
```

### 2. Аутентификация (login)

**Эндпоинт**: `POST /api/v1/auth/login` (роутер из `fastapi_users.get_auth_router`)

```
Шаг 1: Клиент отправляет {email, password}
Шаг 2: UserManager.authenticate(credentials)
       ├─ SELECT user BY email
       ├─ PasswordHelper.verify(password, hashed_password)
       └─ Возврат User или None
Шаг 3: authentication_backend.login(strategy, user)
       ├─ get_database_strategy → DatabaseStrategy(access_tokens_db, lifetime=3600)
       ├─ Генерация токена (secrets.token_urlsafe)
       ├─ INSERT INTO access_tokens (token, user_id, created_at)
       └─ CookieTransport: Set-Cookie "fastapiusersauth" (max_age=3600, secure=False)
Шаг 4: Ответ 200 → UserRead
```

> **¹Примечание**: logout в fastapi-users требует валидный токен (`current_user_token`), но **не** проверяет `is_active`/`is_verified` — заблокированный пользователь всё равно может разлогиниться.

### 3. Верификация email

Двухфазный процесс:

**Фаза A — Запрос токена верификации**:
```
POST /api/v1/auth/request-verify-token (тело: {email})
  └─ UserManager.request_verify(user)
     └─ Генерация verification_token (подписанный JWT с verification_token_secret)
     └─ on_after_request_verify(user, token):
        ├─ verification_link = request.url_for("verify_email") + ?token=...
        └─ BackgroundTask: send_verification_email(user, link)
             ├─ Jinja2: mailing/email-verify/verification-request.html
             └─ aiosmtplib.send → SMTP localhost:1025
```

**Фаза B — Подтверждение**:
```
Пользователь открывает GET /verify-email/?token=...
  └─ Jinja2: verification.html (JS-клиент)
     └─ JS: POST /api/v1/auth/verify (тело: {token})
        └─ UserManager.verify(token)
           ├─ Декодирование токена (verification_token_secret)
           ├─ UPDATE users SET is_verified=True WHERE id=...
           └─ on_after_verify(user):
              └─ BackgroundTask: send_email_confirmed(user)
                   ├─ Jinja2: mailing/email-verify/email-verified.html
                   └─ aiosmtplib.send → SMTP
```

### 4. Сброс пароля

```
POST /api/v1/auth/forgot-password ({email})
  └─ Генерация reset_password_token
  └─ on_after_forgot_password(user, token):
     └─ log.warning("Reset token: %r", token)  # только логирование, без отправки email

POST /api/v1/auth/reset-password ({token, password})
  └─ UserManager.reset_password(token, password)
     ├─ Декодирование токена (reset_password_token_secret)
     ├─ PasswordHelper.hash(password)
     └─ UPDATE users SET hashed_password=...
```

> **Примечание**: Сброс пароля логирует токен в `warning`, но не отправляет email. Это demo-поведение.

### 5. Получение кэшированного списка пользователей

```
GET /api/v1/users
  └─ @cache(expire=60, key_builder=users_list_key_builder, namespace="users-list")
     ├─ key_builder: MD5("api.api_v1.users:get_users_list:():{...}")
     │   исключает SQLAlchemyUserDatabase из kwargs
     ├─ Redis GET fastapi-cache:users-list:<md5>
     │   ├─ HIT → возврат JSON из кэша (без обращения к БД)
     │   └─ MISS →
     │       ├─ get_users_db → SQLAlchemyUserDatabase.get_users()
     │       │   └─ SELECT * FROM users ORDER BY id
     │       ├─ [UserRead.model_validate(user) for user in users]
     │       └─ Redis SETEX (TTL 60s)
```

### 6. Создание суперпользователя (CLI)

**Скрипт**: `python -m actions.create_superuser` (из `fastapi-application/`)

```
1. Чтение env: DEFAULT_EMAIL (default: admin@admin.com), DEFAULT_PASSWORD (default: abc)
2. UserCreate(email, password, is_active=True, is_superuser=True, is_verified=True)
3. async with db_helper.session_factory() as session:
     async with get_users_db_context(session) as users_db:
       async with get_user_manager_context(users_db) as user_manager:
         user = await user_manager.create(user_create, safe=False)
         # safe=False → позволяет установить is_superuser=True
4. Пользователь создан в БД
```

---

## Роутинг и middleware

### Карта роутов

| Метод | Путь | Auth | Описание | Файл |
|---|---|---|---|---|
| — | `/docs` | Нет | Swagger UI (кастомный CDN) | `create_fastapi_app.py` |
| — | `/redoc` | Нет | ReDoc (кастомный CDN) | `create_fastapi_app.py` |
| — | `/admin/*` | Session | SQLAdmin-панель | `admin/` |
| GET | `/home/` | `current_active_user` | HTML-страница пользователя | `views/home.py` |
| GET | `/verify-email/` | Нет | HTML-страница верификации | `views/verification.py` |
| POST | `/api/v1/auth/register` | Нет | Регистрация | `api/api_v1/auth.py` |
| POST | `/api/v1/auth/login` | Нет | Вход (cookie) | `api/api_v1/auth.py` |
| POST | `/api/v1/auth/logout` | `current_user_token`¹ | Выход | `api/api_v1/auth.py` |
| POST | `/api/v1/auth/request-verify-token` | `current_active_user` | Запрос токена верификации | `api/api_v1/auth.py` |
| POST | `/api/v1/auth/verify` | Нет | Подтверждение email | `api/api_v1/auth.py` |
| POST | `/api/v1/auth/forgot-password` | Нет | Запрос сброса пароля | `api/api_v1/auth.py` |
| POST | `/api/v1/auth/reset-password` | Нет | Сброс пароля | `api/api_v1/auth.py` |
| GET | `/api/v1/users` | Нет* | Список пользователей (кэш 60s) | `api/api_v1/users.py` |
| GET | `/api/v1/users/me` | `current_active_user` | Текущий пользователь | `api/api_v1/users.py` |
| GET/PATCH/DELETE | `/api/v1/users/{id}` | `current_active_superuser` | Управление пользователем | `api/api_v1/users.py` |
| GET | `/api/v1/messages` | `current_active_user` | Demo-сообщения | `api/api_v1/messages.py` |
| GET | `/api/v1/messages/error` | Нет | Demo-эндпоинт ошибки | `api/api_v1/messages.py` |
| GET | `/api/v1/messages/secrets` | `current_active_superuser` | Demo-секреты | `api/api_v1/messages.py` |
| GET | `/api/v1/service/stats` | Нет* | Статистика запросов | `api/api_v1/service.py` |

> **\*Примечание про `HTTPBearer`**: на весь роутер `/api/v1` навешена зависимость `http_bearer = HTTPBearer(auto_error=False)` (`api/api_v1/__init__.py`). Она **не выполняет аутентификацию**: `auto_error=False` означает «извлеки заголовок `Authorization`, а если его нет — молча верни `None`». Извлечённый токен нигде не валидируется. Фактический эффект — только кнопка «Authorize» в Swagger UI. Все эндпоинты без явной зависимости (`current_active_user` / `current_active_superuser`) — публичные, включая `GET /users` и `GET /service/stats`.

### Middleware-стек

Регистрация в `fastapi-application/middlewares/middlewares.py` → `register_middlewares()`:

| Порядок добавления | Middleware | Тип | Назначение |
|---|---|---|---|
| 1 | `log_new_requests` | `@app.middleware("http")` | Логирование method + path (`log.info`) |
| 2 | `add_process_time_to_requests` | `@app.middleware("http")` | Header `X-Process-Time` (seconds) |
| 3 | `CORSMiddleware` | `add_middleware` | CORS: origins=[localhost, localhost:8000], methods=*, headers=* |
| 4 | `ProcessTimeHeaderMiddleware` | `BaseHTTPMiddleware` | Header `X-Process-Time-New-Again` (дублирующий) |
| 5 | `RequestsCountMiddlewareDispatch` | `BaseHTTPMiddleware` | In-memory счётчик по path + status_code |

> **Порядок выполнения**: обратный порядку добавления. Запрос проходит снизу вверх: RequestsCount → ProcessTimeNew → CORS → ProcessTime → Log → роутер. Ответ — сверху вниз.

---

## Обработка ошибок и логирование

### Exception handlers

Файл: `fastapi-application/errors_handlers.py` → `register_errors_handlers()`

| Исключение | HTTP-статус | Тело ответа | Логирование |
|---|---|---|---|
| `pydantic.ValidationError` | 422 | `{"message": "Unhandled error", "error": [...]}` | Нет |
| `sqlalchemy.exc.DatabaseError` | 500 | `{"message": "An unexpected error has occurred..."}` | `log.error` с `exc_info` |

> **Примечание**: Обработчик `DatabaseError` имеет аннотацию типа `exc: ValidationError` — это ошибка копипасты; фактически передаётся `DatabaseError`.

### Логирование

| Компонент | Уровень | Источник |
|---|---|---|
| Root logger | `settings.logging.log_level` (default: `info`) | `main.py` → `logging.basicConfig()` |
| `UserManager` | `warning` | `core/authentication/user_manager.py` → `log = logging.getLogger(__name__)` |
| Middleware (log_new_requests) | `info` | `middlewares/middlewares.py` |
| Webhook (send_new_user_notification) | `info` | `utils/webhooks/user.py` |
| DB error handler | `error` | `errors_handlers.py` |
| Gunicorn | `settings.logging.log_level` | `core/gunicorn/logger.py` → `GunicornLogger` (кастомный формат) |

Формат лога (по умолчанию):
```
[%(asctime)s.%(msecs)03d] %(module)10s:%(lineno)-3d %(levelname)-7s - %(message)s
```

### Вебхуки (OpenAPI webhooks)

Файл: `fastapi-application/api/webhooks/user.py`

Webhook `user-created` — декларативное описание в OpenAPI-схеме (не активный HTTP-роут). Описывает контракт уведомления о создании пользователя: тело `UserRegisteredNotification` (`{user: UserRead, ts: int}`). Фактическая отправка вебхука выполняется в `utils/webhooks/user.py` → `send_new_user_notification()`.
