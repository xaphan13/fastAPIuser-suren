# 04 — Оценка качества кодовой базы

## Общая оценка

Проект — качественный учебно-демонстрационный пример архитектуры FastAPI. Кодовая база компактная (~40 модулей Python), консистентно структурирована, активно использует современные идиомы Python 3.12 (type alias `type X = ...`, `Annotated`, generics). Структура слоёв (`core` → `api` → `views` → `infra`) читаема и предсказуема.

**Вердикт**: 7.5/10. Сильная архитектура, слабые места — в операционной надёжности (утечки ресурсов, хардкод, отсутствие тестов) и дублировании.

---

## Соответствие стандартам

### SOLID

| Принцип | Оценка | Комментарий |
|---|---|---|
| **S** (Single Responsibility) | ✅ | Классы узкоспециализированы: `DatabaseHelper`, `UserManager`, `Application`, `ModelConverter` |
| **O** (Open/Closed) | ⚠️ | `Base` + mixin-композиция открыты к расширению; но middleware-слой закрыт для конфигурации (списки жёстко заданы) |
| **L** (Liskov) | ✅ | Подклассы (`SQLAlchemyUserDatabase`, `GunicornLogger`) корректно расширяют базовые интерфейсы |
| **I** (Interface Segregation) | ✅ | Маленькие примеси и хуки вместо толстых интерфейсов |
| **D** (Dependency Inversion) | ✅ | Зависимости внедряются через `Depends()`; модули зависят от абстракций `BaseUserDatabase`, `AccessTokenDatabase` |

### DRY / KISS

- **DRY**: нарушен в middleware — дважды реализован один и тот же расчёт process-time (`add_process_time_to_requests` и `ProcessTimeHeaderMiddleware`). Дублируется `FastAPICache.clear`-логика в `user_manager.py` (ветка if/else для background_tasks).
- **KISS**: в целом соблюдается; усложнение есть в `users_list_key_builder` (MD5-кэширование для простого эндпоинта — избыточно, но допустимо).

### Идиомы языка

- ✅ `Annotated[]` для зависимостей (современный стиль FastAPI)
- ✅ `type` alias statements (Python 3.12)
- ✅ `dataclass` + `field(default_factory=...)` для `PathCounts`
- ✅ Async-генераторы для DI-провайдеров
- ⚠️ Использование `Dict`, `Tuple`, `Optional` из `typing` в `api/api_v1/users.py` вместо встроенных `dict | None` и т.п. (устаревший стиль)
- ⚠️ `list["User"]` в строковых аннотациях — устаревший подход (совместим с Py3.12, но избыточен при `from __future__ import annotations`)

---

## Выявленный технический долг

### Критичный

| # | Проблема | Файл | Эффект |
|---|---|---|---|
| 1 | **Утечка Redis-клиента**: `Redis()` создаётся в `lifespan`, но не закрывается (`await redis.aclose()` отсутствует) | `create_fastapi_app.py` | Неявные соединения на shutdown; при перезапуске lifespan (reload) накапливаются файловые дескрипторы |
| 2 | **In-memory счётчик запросов не является потокобезопасным** (в Gunicorn режиме) и обнуляется на рестарте; при reload-разработке данные теряются | `middlewares/requests_count_middleware.py` | Некорректная статистика `/service/stats`; состояние размазано по воркерам |
| 3 | **Секреты хардкод-дефолты в скрипте**: `DEFAULT_EMAIL=admin@admin.com`, `DEFAULT_PASSWORD=abc` | `actions/create_superuser.py` | Суперпользователь с тривиальным паролем при запуске без env-переменных — дыра в безопасности |
| 4 | **SMTP hostname хардкод** `0.0.0.0:1025` и `admin@site.com` | `mailing/send_email.py` | Невозможность конфигурации SMTP; в production отправка сломана |
| 5 | **Webhook URL хардкод** `https://httpbin.org/post` | `utils/webhooks/user.py` | Неконфигурируемый внешний вызов; в production невалиден |
| 6 | **CORS origins хардкод** в `ALLOW_ORIGINS` | `middlewares/middlewares.py` | Жёсткая привязка к localhost |
| 7 | **Токены сброса пароля логируются в warning** | `core/authentication/user_manager.py` | Секретные данные в логах — риск утечки |

### Средний приоритет

| # | Проблема | Файл | Эффект |
|---|---|---|---|
| 8 | **Отсутствие обработчика `ValidationError`-исключений на уровне роутов** — handler ловит только pydantic-ошибки, проброшенные наружу (например, `UserRead.model_validate(None)` в `messages.py`) | `errors_handlers.py` | Ответ 422 с сырыми `errors()`; нестандартный формат ошибок API |
| 9 | **Неверная аннотация типа** `exc: ValidationError` в обработчике `DatabaseError` | `errors_handlers.py` | Маскирует реальный тип; может запутать tooling/литературу |
| 10 | **Дублирование process-time middleware** (две реализации) | `middlewares/middlewares.py` | Лишние headers `X-Process-Time` и `X-Process-Time-New-Again`; двойной замер времени |
| 11 | **`BaseHTTPMiddleware` для счётчика запросов** — известная проблема с async-генераторами и streaming-ответами (Starlette) | `middlewares/middlewares.py` | Потенциальные edge-кейсы с телами ответов |
| 12 | **Кэш-ключ MD5 без namespace-контекста**: `users_list_key_builder` смешивает args (кортеж сессии) — риск нестабильности ключа | `api/api_v1/users.py` | Лишние cache-miss |
| 13 | **`cookie_secure=False` и `cookie_max_age=3600` захардкожены** (TODO в коде) | `core/authentication/transport.py` | Куки без `Secure`-флага недопустимы в production |
| 14 | **`HTTPBearer` зависимость на уровне `/api/v1`** не выполняет аутентификацию (auto_error=False) | `api/api_v1/__init__.py` | Вводит в заблуждение: токен извлекается, но не валидируется |
| 15 | **Ветвление `if self.background_tasks ... else await`** для инвалидации кэша | `core/authentication/user_manager.py` | Дублирование логики; background_tasks всегда присутствует при запросе |
| 16 | **`mailing/send_verification_email.py` использует `f-string` внутри `dedent`** с `{...}` | `mailing/send_verification_email.py` | Хрупкий формат при добавлении фигурных скобок |

### Низкий приоритет

| # | Проблема | Файл |
|---|---|---|
| 17 | `views/home.html` — inline-JS вместо отдельного статического файла; Bootstrap через CDN | `templates/home.html` |
| 18 | Нет тестов вовсе (нет `tests/`, pytest не в зависимостях) | — |
| 19 | Нет `requirements.lock` / `uv.lock` — недетерминированная установка зависимостей | `pyproject.toml` |
| 20 | `.env` игнорируется, но не документированы все переменные окружения | `core/config.py` |
| 21 | Alembic миграции сгенерированы вручную (не autogenerate): возможен дрейф с моделями | `alembic/versions/` |

---

## Оценка безопасности и надёжности

### Хардкод

- Секреты в env-переменных корректно вынесены (secrets токенов в `Settings`), **но**:
  - `DEFAULT_PASSWORD=abc` в `actions/create_superuser.py`
  - `cookie_secure=False` в `core/authentication/transport.py`
  - CORS-список, SMTP-адрес, webhook URL — в коде
  - Отсутствие проверки пустых secrets: `.env.template` содержит `RESET_PASSWORD_TOKEN_SECRET=` пустым — приложение стартует с пустым secret (fastapi-users сгенерирует предупреждение, но токены будут предсказуемы)

### Утечки ресурсов

- Redis-клиент не закрывается (см. п.1)
- `aiohttp.ClientSession` создаётся на каждый вызов вебхука без переиспользования (накладные расходы на установку соединения); соединение при этом закрывается корректно через `async with`
- SQLAlchemy engine/пул корректно утилизируется через `db_helper.dispose()`

### Валидация

- ✅ Pydantic-схемы (v2) для всех входных/выходных DTO
- ✅ Email-валидация через `pydantic[email]`
- ⚠️ Нет rate-limiting (защита от brute-force на `/auth/login`, `/auth/register` отсутствует)
- ⚠️ Нет валидации длины/сложности пароля (дефолт fastapi-users — минимальные проверки)
- ⚠️ Webhook-схема `UserRegisteredNotification` не валидируется на стороне отправителя (`model_dump()` без проверки)

### Надёжность

- **Отсутствие транзакционных гарантий** для побочных эффектов: webhook/email выполняются после COMMIT без retry — при сбое SMTP или сети данные потеряются навсегда (нет очередей/бэкенда задач)
- **`on_after_register` выполняется в фоне** (background_tasks), но вебхук — синхронный `await` внутри хука; при недоступности httpbin регистрация упадёт с 500
- **`/service/stats`** отдаёт состояние из памяти — при нескольких gunicorn-воркерах статистика некорректна
- **`@cache` на `get_users_list`** не инвалидируется при UPDATE/DELETE пользователя (только при регистрации) — возможна устаревшая выдача до 60 секунд

### Дополнительные замечания

- `errors_handlers.py`: `DatabaseError` ловится глобально, но не выполняется rollback/повторный запрос — сессия остаётся в «сломанном» состоянии до её закрытия (FastAPI закрывает её после запроса, но пользователь получит 500 при следующем запросе с той же сессией в рамках одного request lifecycle — некритично)
- Отсутствует логирование входящих payload-ов (намеренно, и это хорошо)
- Нет защиты от CSRF для cookie-based аутентификации (актуально для форм/вебхуков)

---

## Узкие места (bottlenecks)

1. **`GET /api/v1/users`**: полная выборка всех пользователей + построение `list[UserRead]` без пагинации. На больших таблицах — рост latency и памяти.
2. **`get_users()`** (`core/models/user.py`): `SELECT *` без ограничения — связан с п.1.
3. **Синхронный webhook в `on_after_register`**: блокирует завершение регистрации на внешний HTTP-запрос (RTT httpbin ~сотни мс).
4. **Email в `BackgroundTasks`**: отправка выполняется после отправки ответа, но внутри того же worker'а; при высокой нагрузке и медленном SMTP воркер занят.
5. **Пустой `default_response_class` на уровне FastAPI, но `ORJSONResponse` не используется в `views`** (TemplateResponse) — ок, но смешение форматов.

## Сильные стороны (что стоит сохранить)

- Чистая фабрика `create_app()` — единая точка сборки приложения
- Централизованная конфигурация через pydantic-settings с вложенным namespace
- DI-цепочки полностью через `Depends` — легко тестировать с mock-объектами
- Миграции с naming_convention — предсказуемые имена constraint'ов
- Компактность: ~2k строк на весь проект — отличная «база-образец» для расширения