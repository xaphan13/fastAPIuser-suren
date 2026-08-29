# 07 — Отчёт по авторизации: fastapi-users, JWT и OAuth 2.0

## Что значит «проект поверх библиотеки fastapi-users»

### Назначение fastapi-users

[`fastapi-users`](https://github.com/fastapi-users/fastapi-users) — это библиотека для FastAPI, которая берёт на себя всю «боилерплейт»-логику управления пользователями:

- Регистрация (`/register`)
- Аутентификация / вход / выход (`/login`, `/logout`)
- Верификация email (`/request-verify-token`, `/verify`)
- Сброс пароля (`/forgot-password`, `/reset-password`)
- Управление профилем (`/me`, `PATCH /me`, `DELETE /me`, `GET /{id}`, `PATCH /{id}`, `DELETE /{id}`)
- Ролевой доступ: `current_active_user`, `current_active_superuser`

Библиотека предоставляет **роутеры** (`get_auth_router`, `get_register_router`, `get_verify_router`, `get_reset_password_router`, `get_users_router`), которые проект просто подключает к своему `APIRouter`:

```python
# api/api_v1/auth.py
router.include_router(fastapi_users.get_auth_router(authentication_backend))
router.include_router(fastapi_users.get_register_router(UserRead, UserCreate))
router.include_router(fastapi_users.get_verify_router(UserRead))
router.include_router(fastapi_users.get_reset_password_router())

# api/api_v1/users.py
router.include_router(fastapi_users.get_users_router(UserRead, UserUpdate))
```

Проект **не реализует логику регистрации или проверки пароля самостоятельно** — это делает fastapi-users. Проект лишь:

1. **Настраивает** библиотеку: определяет модель `User`, стратегию хранения токенов, транспорт (cookie), менеджер пользователей (`UserManager`).
2. **Расширяет** через хуки (callbacks): `on_after_register`, `on_after_request_verify`, `on_after_verify`, `on_after_forgot_password` — добавляет отправку email, вебхуки, инвалидацию кэша.
3. **Добавляет** собственный эндпоинт `GET /api/v1/users` (список пользователей с кэшированием в Redis), которого в fastapi-users нет по умолчанию.

### Архитектура fastapi-users в проекте

fastapi-users построен на принципе **композиции из трёх компонентов**:

```
AuthenticationBackend = Transport + Strategy
```

| Компонент | Назначение | Реализация в проекте |
|---|---|---|
| **Transport** | Как токен передаётся между клиентом и сервером | `CookieTransport` (cookie) |
| **Strategy** | Как токен создаётся, хранится и валидируется | `DatabaseStrategy` (токены в БД) |
| **Backend** | Связывает transport + strategy | `AuthenticationBackend(name="access-tokens-db")` |

---

## Что есть в проекте кроме пользователей

Проект не ограничивается только управлением пользователями. Вот полный перечень модулей:

### Модели данных (`core/models/`)

| Модель | Назначение |
|---|---|
| `User` | Пользователь (email, hashed_password, is_active, is_superuser, is_verified) — из fastapi-users |
| `AccessToken` | Токен доступа, привязанный к пользователю (один-ко-многим) — из fastapi-users DB strategy |

Других доменных моделей (постов, заказов, товаров и т.д.) **нет**. Проект сфокусирован на подсистеме аутентификации.

### API-эндпоинты (`api/api_v1/`)

| Роутер | Префикс | Эндпоинты | Назначение |
|---|---|---|---|
| `auth` | `/api/v1/auth` | `/login`, `/logout`, `/register`, `/request-verify-token`, `/verify`, `/forgot-password`, `/reset-password` | Полный цикл аутентификации (из fastapi-users) |
| `users` | `/api/v1/users` | `GET ""` (кастомный, с кэшем), `/me`, `PATCH /me`, `DELETE /me`, `GET /{id}`, `PATCH /{id}`, `DELETE /{id}` | Управление пользователями |
| `messages` | `/api/v1/messages` | `GET /error`, `GET ""`, `GET /secrets` | Демо-эндпоинты для проверки доступа (user vs superuser) |
| `service` | `/api/v1/service` | `GET /stats` | Статистика запросов (из middleware-счётчика) |

### Инфраструктура

| Модуль | Технология | Назначение |
|---|---|---|
| `mailing/` | aiosmtplib | Отправка email: верификация, подтверждение |
| `utils/webhooks/` | aiohttp | Исходящие вебхуки (уведомление о новом пользователе) |
| `admin/` | SQLAdmin | Админ-панель для User и AccessToken |
| `middlewares/` | Starlette | Логирование, CORS, счётчик запросов, X-Process-Time |
| Кэш | fastapi-cache + Redis | Кэширование `GET /users` |
| Миграции | Alembic | Версионирование схемы БД |
| HTML-страницы | Jinja2 | `/home/`, `/verify-email/` |

### Webhooks

В проекте есть отдельный webhook-эндпоинт (`api/webhooks/user.py`), который описывает **исходящий** webhook (событие «новый пользователь зарегистрирован» → POST на внешний URL). Это не входящая авторизация, а уведомление внешних систем.

---

## Авторизация в проекте: это JWT или нет?

### Короткий ответ

**Нет, это не JWT.** Проект использует **opaque-токены (непрозрачные токены)**, хранящиеся в базе данных.

### Подробное объяснение

В fastapi-users доступно **две стратегии** хранения токенов:

| Стратегия | Класс | Как работает |
|---|---|---|
| **JWT** | `JWTStrategy` | Сервер подписывает токен (HMAC/RSA). Токен самодостаточный — содержит все claims. Сервер **не хранит** токен. Валидация = проверка подписи + expiry. |
| **Database** | `DatabaseStrategy` | Сервер генерирует случайную строку (`secrets.token_urlsafe()`), сохраняет её в БД (таблица `access_tokens`). Валидация = поиск токена в БД. |

Проект выбрал **DatabaseStrategy**:

```python
# api/dependencies/authentication/strategy.py
def get_database_strategy(access_tokens_db) -> DatabaseStrategy:
    return DatabaseStrategy(
        database=access_tokens_db,
        lifetime_seconds=settings.access_token.lifetime_seconds,  # 3600
    )
```

Токен — это случайная строка, сохранённая в таблице `access_tokens` (модель `AccessToken`):

```python
# core/models/access_token.py
class AccessToken(Base, SQLAlchemyBaseAccessTokenTable[UserIdType]):
    user_id: Mapped[UserIdType] = mapped_column(...)
    user: Mapped["User"] = relationship(back_populates="access_tokens")
```

### Транспорт: Cookie, не Bearer

Хотя в коде определён `BearerTransport`, он **закомментирован**:

```python
# api/dependencies/authentication/backend.py
authentication_backend = AuthenticationBackend(
    name="access-tokens-db",
    # transport=bearer_transport,    ← закомментировано
    transport=cookie_transport,       ← используется
    get_strategy=get_database_strategy,
)
```

Токен передаётся в **HTTP-only cookie**, а не в заголовке `Authorization: Bearer <token>`:

```python
# core/authentication/transport.py
cookie_transport = CookieTransport(
    cookie_max_age=3600,
    cookie_secure=False,    # TODO: move to settings
)
```

### Сравнение: opaque-токены (проект) vs JWT

| Критерий | Проект (opaque + DB) | JWT |
|---|---|---|
| **Формат токена** | Случайная строка (`secrets.token_urlsafe()`) | JSON + подпись (header.payload.signature) |
| **Где хранится** | В таблице `access_tokens` в PostgreSQL | Нигде на сервере (stateless) |
| **Валидация** | SQL-запрос: `SELECT * FROM access_tokens WHERE token = ?` | Проверка криптографической подписи |
| **Self-contained** | Нет — нужен запрос к БД | Да — токен содержит email, id, роли, expiry |
| **Отзыв (revocation)** | Удалить строку из БД — мгновенно | Сложно — нужен blacklist или короткий TTL |
| **Производительность** | Дополнительный запрос к БД на каждый запрос | Без запросов к БД (проверка подписи в памяти) |
| **Размер токена** | ~22 байта (base64url) | ~200–500 байт |
| **Stateless** | Нет | Да |
| **Масштабируемость** | БД — узкое место при росте | Лучшая (нет обращения к хранилищу) |
| **Logout** | Удалить токен из БД — работает мгновенно | Токен «жив» до expiry (нужен blacklist) |

### Почему выбран opaque + DB, а не JWT

Вероятные причины (исходя из архитектуры проекта):

1. **Простота отзыва** — при logout достаточно удалить токен из БД. С JWT потребовался бы blacklist в Redis.
2. **Прозрачность для админки** — SQLAdmin показывает токены в панели администратора (`AccessTokenAdmin`), можно вручную отзывать.
3. **Меньше рисков** — opaque-токен не содержит данных пользователя, его компрометация не раскрывает claims.
4. **Учебный характер проекта** — DB-strategy нагляднее для понимания потока аутентификации.

### Недостатки текущего подхода

1. **Каждый запрос → запрос к БД** для валидации токена. Нет кэширования токенов (Redis есть, но для кэша списка пользователей, не токенов).
2. **`cookie_secure=False`** — cookie передаётся по HTTP. В production **критично** установить `secure=True`, `httponly=True`, `samesite="lax"`.
3. **Нет CSRF-защиты** — cookie-based auth уязвима к CSRF-атакам на POST-эндпоинты (`/auth/login`, `/auth/logout`, `/auth/register`).
4. **Нет refresh-токена** — после истечения `lifetime_seconds` (3600 = 1 час) пользователь должен логиниться заново.

---

## Отличие от OAuth 2.0

### Что такое OAuth 2.0

OAuth 2.0 — это **протокол делегирования доступа**, описанный в RFC 6749. Его суть: пользователь разрешает одному приложению (клиенту) получить доступ к своим данным на другом сервисе (ресурс-сервере) от своего имени, **не передавая пароль** клиенту.

Классический пример: «Войти через Google» — приложение получает токен доступа к API Google, не зная пароля пользователя.

### Ключевые отличия

| Критерий | Проект (fastapi-users) | OAuth 2.0 |
|---|---|---|
| **Цель** | Аутентификация пользователя в собственном приложении | Делегирование доступа третьим лицам |
| **Кто выдаёт токен** | Само приложение (собственный `/auth/login`) | Authorization Server (отдельный сервис) |
| **Участники** | 2: клиент (браузер) + сервер | 4: resource owner, client, authorization server, resource server |
| **Роли** | Пользователь = владелец ресурса = клиент | Роли разделены: resource owner ≠ client ≠ authorization server |
| **Grant types** | Нет (один поток: login → cookie) | Authorization Code, Implicit, Password, Client Credentials, Refresh Token, Device Code |
| **Redirect URI** | Нет | Да — OAuth перенаправляет пользователя на callback URL с кодом |
| **Scopes** | Нет (только is_superuser: yes/no) | Да — токен содержит scopes (`read:profile`, `write:posts` и т.д.) |
| **Токен для кого** | Для того же приложения | Для стороннего клиента, обращающегося к API от имени пользователя |
| **Consent screen** | Нет | Да — пользователь видит «Приложение X запрашивает доступ к Y» |
| **Client ID / Secret** | Нет | Да — каждый клиент регистрируется с client_id и client_secret |

### Наглядная аналогия

**Проект (fastapi-users)** — это как вход в свой дом своим ключом. Вы регистрируетесь, получаете ключ (cookie/токен), и этим ключом открываете двери своего же дома.

**OAuth 2.0** — это как дать другу временный пропуск в ваш офис. Вы не даёте ему свой ключ (пароль), а просите охрану (authorization server) выдать ему пропуск с ограниченными правами (scopes), который действует определённое время. Друг — это стороннее приложение.

### Может ли проект стать OAuth 2.0-провайдером?

Технически — да, но это требует значительной доработки:

1. **Authorization Server** — отдельный сервис (или модуль), реализующий endpoints: `/authorize`, `/token`, `/userinfo`. Библиотеки: `authlib`, `oauthlib`.
2. **Регистрация клиентов** — модель `OAuthClient` (client_id, client_secret, redirect_uris, allowed_scopes).
3. **Authorization Code flow** — `/authorize?response_type=code&client_id=...&redirect_uri=...&scope=...` → consent screen → redirect с `?code=...` → обмен кода на токен.
4. **Scopes** — модель разрешений, привязанная к токену.
5. **Refresh tokens** — долгоживущие токены для обновления access tokens.

fastapi-users **не поддерживает** OAuth 2.0 provider-функциональность «из коробки». Он реализует аутентификацию для собственного приложения, а не делегирование доступа.

### OAuth 2.0 как клиент (вход через Google/GitHub)

fastapi-users поддерживает **вход через внешние OAuth-провайдеры** (Google, Facebook, GitHub и т.д.) через модуль `fastapi-users[oauth]`. В этом случае:

- Проект выступает **OAuth-клиентом**, а не провайдером.
- Пользователь перенаправляется на Google → логинится там → возвращается с кодом → проект обменивает код на токен → создаёт/находит пользователя в своей БД.
- В текущем проекте этот модуль **не подключён** — вход только по email+password.

---

## Сводная таблица: три концепции

| | Проект (fastapi-users) | JWT | OAuth 2.0 |
|---|---|---|---|
| **Что это** | Библиотека для управления пользователями | Формат токена | Протокол делегирования доступа |
| **Уровень** | Прикладная библиотека | Формат данных (RFC 7519) | Протокол (RFC 6749) |
| **Токен** | Opaque (случайная строка в БД) | JSON + подпись | Зависит от реализации (может быть JWT или opaque) |
| **Stateless** | Нет (нужна БД) | Да | Зависит |
| **Цель** | «Кто этот пользователь?» | «Как компактно и проверяемо передать claims?» | «Может ли это приложение действовать от имени пользователя?» |
| **Применимо в проекте?** | ✅ Используется | ⚠️ Можно переключить (заменить `DatabaseStrategy` → `JWTStrategy`) | ❌ Не реализовано; можно добавить как клиент (вход через Google) или как провайдер (большой объём работ) |

---

## Рекомендации по авторизации

### Критично (🔴)

1. **`cookie_secure=True` в production** — иначе токен утекает по HTTP.
2. **CSRF-защита** — cookie-auth без CSRF-токена уязвима. Интегрировать `starlette-csrf` или double-submit-cookie.
3. **Не логировать токены** — в `user_manager.py` токены верификации и сброса пароля логируются через `log.warning("... token: %r", token)`. В production это утечка чувствительных данных.

### Архитектура (🟡)

4. **Рассмотреть JWT-strategy** — если важна производительность (убрать запрос к БД на каждый запрос) и stateless. Но потребуется Redis-blacklist для отзыва.
5. **Refresh-токены** — текущий access-токен живёт 1 час, после чего требуется повторный логин. Добавить refresh-токен (долгоживущий, с ротацией).
6. **Кэширование валидации токена** — если оставлять DB-strategy, кэшировать поиск токена в Redis (с коротким TTL, например 30 сек) для снижения нагрузки на БД.
7. **Rate limiting на `/auth/login`** — защита от brute-force (через `slowapi` или Redis-based limiter).

### Расширение (🟢)

8. **OAuth-клиент** — добавить вход через Google/GitHub через `fastapi-users[oauth]`, если нужен social login.
9. **2FA** — добавить двухфакторную аутентификацию (TOTP через `pyotp`).
10. **Sessions table** — при opaque-токенах можно вести таблицу сессий с метаданными (IP, user-agent, last_seen) для audit trail.

---

## Итог

Проект использует **fastapi-users** как фундамент для подсистемы пользователей, что избавляет от написания боилерплейта (регистрация, верификация, сброс пароля). Авторизация построена на **opaque-токенах в БД** (не JWT), передаваемых через **cookie** (не Bearer). Это не OAuth 2.0 — проект не делегирует доступ третьим лицам, а аутентифицирует пользователей в собственном приложении. Выбор DB-strategy оправдан простотой отзыва токенов и прозрачностью, но требует CSRF-защиты и настройки `secure`-cookie для production.
