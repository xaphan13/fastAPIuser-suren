# 05 — Предложения по развитию

## Приоритизация

Предложения отсортированы по соотношению «эффект / усилие». Маркеры: 🔴 — критично/безопасность, 🟡 — архитектура/надёжность, 🟢 — DX/оптимизация.

---

## Архитектурные улучшения

### 🔴 A1. Закрытие Redis-клиента в `lifespan`

**Проблема**: `Redis()` создаётся в `lifespan`, но не закрывается при shutdown — утечка соединений.

**Файл**: `fastapi-application/create_fastapi_app.py`

**Решение**:
```python
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    redis = Redis(host=..., port=..., db=...)
    FastAPICache.init(RedisBackend(redis), prefix=...)
    yield
    await redis.aclose()           # <-- добавить
    await db_helper.dispose()
```

### 🟡 A2. Вынести всю инфраструктурную конфигурацию в `Settings`

**Проблема**: хардкод SMTP-хоста, webhook URL, CORS origins, cookie-параметров.

**Файлы**: `mailing/send_email.py`, `utils/webhooks/user.py`, `middlewares/middlewares.py`, `core/authentication/transport.py`, `core/config.py`

**Решение**: добавить подконфигурации в `Settings`:
```python
class SmtpConfig(BaseModel):
    host: str = "localhost"
    port: int = 1025
    sender_email: str = "noreply@example.com"

class WebhookConfig(BaseModel):
    user_created_url: str = "https://httpbin.org/post"

class CookieConfig(BaseModel):
    max_age: int = 3600
    secure: bool = False  # True в production
    httponly: bool = True
    samesite: str = "lax"

class CorsConfig(BaseModel):
    allow_origins: list[str] = ["http://localhost", "http://localhost:8000"]
```

### 🟡 A3. Ввести очередь задач вместо `BackgroundTasks`

**Проблема**: email и вебхуки выполняются в процессе worker'а; при сбое теряются; блокируют регистрацию при синхронном `await`.

**Решение**: внедрить `arq` (Redis-based) или `Celery` + Redis-брокер. Перенести `send_verification_email`, `send_email_confirmed`, `send_new_user_notification` в задачи с retry-политикой. Это также решает проблему рассылки при нескольких воркерах.

### 🟡 A4. Перенести счётчик запросов в Redis

**Проблема**: `RequestsCountMiddlewareDispatch` хранит данные in-memory — некорректно при нескольких gunicorn-воркерах и теряется при рестарте.

**Файл**: `fastapi-application/middlewares/requests_count_middleware.py`

**Решение**: использовать Redis INCR/HINCRBY с ключом `stats:paths:<path>`. Альтернатива — Prometheus-метрики (`prometheus-fastapi-instrumentator`) + Grafana.

### 🟡 A5. Добавить CSRF-защиту для cookie-аутентификации

**Проблема**: cookie-based auth без CSRF-токена уязвима для cross-site запросов (особенно для POST-эндпоинтов `/auth/*`).

**Решение**: интегрировать `starlette-csrf` или реализовать double-submit-cookie паттерн.

### 🟢 A6. Вынести статические JS из шаблонов

**Проблема**: inline-JS в `home.html` и `verification.html` — не кэшируется браузером, сложно тестировать.

**Решение**: переместить в `static/js/` с версионированием; подключить `StaticFiles`.

---

## Оптимизация производительности

### 🟡 P1. Пагинация `GET /api/v1/users`

**Проблема**: `get_users()` выполняет `SELECT * FROM users ORDER BY id` без LIMIT — полная загрузка в память.

**Файлы**: `api/api_v1/users.py`, `core/models/user.py`

**Решение**:
```python
# core/models/user.py
async def get_users(self, offset: int = 0, limit: int = 50) -> list[User]:
    statement = select(User).order_by(User.id).offset(offset).limit(limit)
    ...

# api/api_v1/users.py
@router.get("", response_model=list[UserRead])
@cache(expire=60, key_builder=users_list_key_builder, ...)
async def get_users_list(
    users_db: ...,
    offset: int = 0,
    limit: int = Query(default=50, le=200),
):
    users = await users_db.get_users(offset=offset, limit=limit)
    return [UserRead.model_validate(user) for user in users]
```
Кэш-ключ `users_list_key_builder` уже учитывает kwargs — `offset`/`limit` автоматически попадут в ключ.

### 🟡 P2. Асинхронный вебхук через очередь (связано с A3)

**Проблема**: `await send_new_user_notification(user)` в `on_after_register` блокирует ответ на RTT внешнего HTTP.

**Решение**: перенести в фоновую задачу (arq/Celery) или хотя бы обернуть в `BackgroundTasks`:
```python
async def on_after_register(self, user, request=None):
    self.background_tasks.add_task(FastAPICache.clear, namespace=...)
    self.background_tasks.add_task(send_new_user_notification, user=user)
```

### 🟢 P3. Переиспользование `aiohttp.ClientSession`

**Проблема**: `send_new_user_notification` создаёт новую `ClientSession` на каждый вызов.

**Файл**: `utils/webhooks/user.py`

**Решение**: создать singleton-сессию в `lifespan` и передавать через `app.state` или DI.

### 🟢 P4. Удалить дублирующий process-time middleware

**Проблема**: `add_process_time_to_requests` и `ProcessTimeHeaderMiddleware` делают одно и то же.

**Файл**: `middlewares/middlewares.py`

**Решение**: оставить один (рекомендуется `ProcessTimeHeaderMiddleware` как параметризуемый класс), удалить второй.

### 🟢 P5. Кэш-ключ без MD5

**Проблема**: `users_list_key_builder` использует MD5-хэш — избыточно для простого эндпоинта без параметров (после пагинации — можно строить читаемый ключ `users-list:offset:{offset}:limit:{limit}`).

**Файл**: `api/api_v1/users.py`

---

## Рефакторинг — первоочередные файлы

| Приоритет | Файл | Обоснование | Объём работ |
|---|---|---|---|
| 🔴 1 | `create_fastapi_app.py` | Закрытие Redis (A1); централизация startup/shutdown | Малый |
| 🔴 2 | `core/config.py` | Расширение `Settings` инфраструктурными конфигами (A2) | Средний |
| 🔴 3 | `mailing/send_email.py` | Убрать хардкод SMTP/sender; читать из `Settings` | Малый |
| 🔴 4 | `utils/webhooks/user.py` | Убрать хардкод URL; переиспользование сессии (P3) | Малый |
| 🔴 5 | `core/authentication/transport.py` | Вынести cookie-параметры в `Settings` (A2); `secure=True` в prod | Малый |
| 🟡 6 | `middlewares/middlewares.py` | Удалить дубликаты (P4); вынести CORS в `Settings` | Малый |
| 🟡 7 | `core/authentication/user_manager.py` | Упростить ветвление background_tasks; убрать логирование токенов; перенести webhook в очередь (P2) | Средний |
| 🟡 8 | `errors_handlers.py` | Исправить аннотацию `exc: ValidationError` → `DatabaseError`; добавить обработку `HTTPException`/generic `Exception` | Малый |
| 🟡 9 | `core/models/user.py` + `api/api_v1/users.py` | Пагинация (P1) | Средний |
| 🟡 10 | `middlewares/requests_count_middleware.py` | Redis-бэкенд (A4) | Средний |
| 🟢 11 | `actions/create_superuser.py` | Убрать дефолт `abc`; требовать env-переменные | Малый |

---

## Рекомендации по улучшению DX (Developer Experience)

### Тесты

**Текущее состояние**: тестов нет, pytest не в зависимостях.

**План**:
1. Добавить dev-зависимости в `pyproject.toml`:
   ```toml
   [project.optional-dependencies]
   dev = [
       "pytest>=8",
       "pytest-asyncio>=0.24",
       "httpx>=0.27",       # AsyncClient для тестов FastAPI
       "aiosqlite>=0.20",   # in-memory SQLite для изолированных тестов БД
       "fakeredis>=2",      # мок Redis
   ]
   ```
2. Создать `tests/` с фикстурами:
   - `tests/conftest.py` — override `get_users_db`, `get_user_manager`, `FastAPICache` через `app.dependency_overrides`
   - `tests/test_auth.py` — регистрация, login, verify, reset
   - `tests/test_users.py` — список, `/me`, `/users/{id}`, кэш-инвалидация
   - `tests/test_middleware.py` — headers, счётчик
3. Покрытие ≥ 70% как минимальный порог в CI.

### CI/CD

1. **GitHub Actions** (или GitLab CI):
   - `lint` — `ruff check .` + `ruff format --check .`
   - `test` — `pytest --cov`
   - `mypy` (опционально) — добавить в dev-зависимости
2. **Pre-commit hooks** (`.pre-commit-config.yaml`): ruff, black, trailing-whitespace
3. **Docker-образ** приложения: `Dockerfile` на базе `python:3.12-slim` + multi-stage build; расширить `docker-compose.yml` сервисом `app`

### Локальный запуск

1. **Makefile** или `justfile` с командами:
   ```makefile
   setup:     ## Установка зависимостей + создание .env из template
   dev:       ## uvicorn main:main_app --reload
   prod:      ## gunicorn (через run_main.py)
   migrate:   ## alembic upgrade head
   superuser: ## python -m actions.create_superuser
   test:      ## pytest
   lint:      ## ruff check + format
   ```
2. **`.env.example`** с полным списком переменных и комментариями (сейчас `.env.template` неполный — нет `REDIS__*`, `CACHE__*`, `RUN__*`, `LOGGING__*`)
3. **Health-check эндпоинт** `GET /health` → `{"status": "ok"}` (для Docker/k8s liveness probe)

### Документация

1. Дополнить `README.md`: архитектурная схема, список эндпоинтов, переменные окружения, команды запуска
2. Добавить `AGENTS.md` в корень — инструкции для AI-агентов (структура, конвенции, команды)
3. OpenAPI: добавить `description` и `tags` с метаданными для каждого роутера

### Зависимости

1. Зафиксировать версии: `uv lock` → `uv.lock` в репозитории (детерминированная установка)
2. Регулярный `dependabot` / `renovate` для обновления
3. Разделить `dependencies` (runtime) и `[project.optional-dependencies]` (dev) — сейчас `ruff` и `black` в runtime-зависимостях

---

## Итоговая дорожная карта (по спринтам)

| Спринт | Задачи | Эффект |
|---|---|---|
| **S1** (безопасность) | A1, A2 (SMTP/cookie/CORS), рефакторинг #1–5, #11 | Устранение хардкода и утечек; production-ready конфигурация |
| **S2** (надёжность) | A3 (очередь задач), A4 (Redis-счётчик), A5 (CSRF), P2 | Отказоустойчивость побочных эффектов; корректная статистика |
| **S3** (производительность) | P1 (пагинация), P3 (сессия), P4/P5 (middleware/кэш) | Масштабируемость при росте данных |
| **S4** (DX) | Тесты, CI/CD, Makefile, Dockerfile, health-check, AGENTS.md | Ускорение онбординга и итераций |
