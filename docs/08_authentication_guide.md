# 08 — Гайд по авторизации: как это работает и почему

> Этот документ — обучающий разбор подсистемы аутентификации/авторизации проекта.
> Цель — не «скопируй и заработает», а **понимание**: почему каждый элемент находится
> именно там, где находится, и что произойдёт, если его убрать или заменить.
> Справочная сводка (без объяснений) — в `07_authorization_report.md`.

---

## 0. Термины: аутентификация ≠ авторизация

Эти слова путают постоянно, а в проекте они разделены очень чётко — поэтому начнём с определений:

| Термин | Вопрос | Пример из проекта |
|---|---|---|
| **Аутентификация** (authentication) | «К ты?" — кто этот пользователь?» | Проверка cookie `fastapiusersauth` → поиск токена в БД → получение `User` |
| **Авторизация** (authorization) | «А что ему можно?» | `is_superuser=True` → доступ к `GET /api/v1/messages/secrets` |

В этом проекте:

- **Аутентификация** = fastapi-users: cookie-транспорт + opaque-токен в PostgreSQL.
- **Авторизация** = два простых уровня: «любой активный пользователь» (`current_active_user`)
  и «суперпользователь» (`current_active_superuser`). Разделение прав на `is_superuser` —
  это грубая, но честная модель: нет гранулярных прав, нет scopes, только «обычный» и «админ».

---

## 1. Карта участников: кто за что отвечает

Подсистема разложена по трём слоям проекта. Важно понять это разделение — оно повторяет
слоистую архитектуру всего приложения (см. `02_architecture.md`):

```
core/authentication/          ← ЧТО использовать (конфигурация библиотеки)
├── fastapi_users.py          FastAPIUsers-инстанс + зависимости current_active_user / current_active_superuser
├── user_manager.py           UserManager — бизнес-логика пользователя + хуки (email, вебхуки, кэш)
└── transport.py              cookie_transport / bearer_transport — КАК токен ездит по сети

api/dependencies/authentication/   ← КАК это собрать (DI-провайдеры)
├── users.py                  get_users_db:        AsyncSession → SQLAlchemyUserDatabase
├── user_manager.py           get_user_manager:    users_db → UserManager
├── access_tokens.py          get_access_tokens_db: AsyncSession → AccessTokenDatabase
├── strategy.py               get_database_strategy: tokens_db → DatabaseStrategy
└── backend.py                authentication_backend: transport + strategy → AuthenticationBackend

api/api_v1/auth.py, users.py  ← ГДЕ это подключено (роутеры)
```

Ключевая мысль: **сам проект не пишет ни строчки логики логина, регистрации или проверки
пароля**. Он только конфигурирует fastapi-users и подключает его роутеры. Вся «магия» —
это правильно собранная цепочка зависимостей.

---

## 2. Три строительных блока: Transport + Strategy = Backend

fastapi-users построен на композиции из трёх компонентов. Это центральная идея, без которой
дальше ничего не понять:

```
AuthenticationBackend = Transport + Strategy
```

### 2.1 Transport — «по какому каналу ездит токен»

Отвечает на два вопроса: **где клиент хранит токен** и **как сервер его извлекает из запроса**.

В проекте (`core/authentication/transport.py`):

```python
bearer_transport = BearerTransport(tokenUrl=...)   # заголовок Authorization: Bearer <token>
cookie_transport = CookieTransport(                # cookie
    cookie_max_age=3600,
    cookie_secure=False,   # TODO: move to settings
)
```

В `backend.py` используется **только cookie** (bearer закомментирован). Итоговые параметры
cookie — комбинация явных настроек проекта и дефолтов библиотеки:

| Параметр | Значение | Откуда |
|---|---|---|
| Имя cookie | `fastapiusersauth` | дефолт библиотеки |
| `max_age` | 3600 с (1 час) | проект |
| `httponly` | `True` | дефолт библиотеки |
| `secure` | `False` | проект (хардкод) |
| `samesite` | `lax` | дефолт библиотеки |

Что это значит на практике:

- `httponly=True` — JavaScript в браузере **не может прочитать** cookie. Это защита от кражи
  токена через XSS: даже если злоумышленник внедрит скрипт на страницу, `document.cookie`
  не отдаст токен. Браузер сам приложит cookie к каждому запросу на этот домен.
- `samesite="lax"` — браузер **не отправит** cookie при cross-site POST-запросах с чужих
  сайтов. Это встроенная (частичная) защита от CSRF — см. раздел 10.
- `secure=False` — cookie уходит и по обычному HTTP. Для localhost — ок, для production —
  недопустимо (токен перехватывается по сети).

**Почему cookie, а не Bearer?** Проект рассчитан на браузерный сценарий (Jinja2-страницы
`/home/`, `/verify-email/`). Cookie с `httponly` — самый безопасный способ хранения токена
в браузере: его нельзя украсть скриптом, в отличие от токена в `localStorage` при Bearer-схеме.
Bearer-транспорт оставлен в коде как альтернатива для API-клиентов (мобильных приложений, скриптов).

### 2.2 Strategy — «как токен рождается, живёт и умирает»

Отвечает на три вопроса: как токен **создаётся** при логине, как **проверяется** на каждом
запросе и как **уничтожается** при логауте.

В проекте (`api/dependencies/authentication/strategy.py`):

```python
def get_database_strategy(
    access_tokens_db: Annotated["AccessTokenDatabase[AccessToken]", Depends(get_access_tokens_db)],
) -> DatabaseStrategy:
    return DatabaseStrategy(
        database=access_tokens_db,
        lifetime_seconds=settings.access_token.lifetime_seconds,  # 3600
    )
```

`DatabaseStrategy` — это **opaque-токены** (непрозрачные): случайная строка из
`secrets.token_urlsafe()`, которая ничего не значит сама по себе. Вся информация о ней —
в таблице `access_tokens` PostgreSQL. Альтернатива — `JWTStrategy` (самоподписанный токен,
сервер ничего не хранит). Почему выбрана DB-стратегия — подробный разбор в разделе 8.

### 2.3 Backend — «склейка»

```python
# api/dependencies/authentication/backend.py
authentication_backend = AuthenticationBackend(
    name="access-tokens-db",
    transport=cookie_transport,        # токен живёт в cookie
    get_strategy=get_database_strategy,  # токен живёт в БД
)
```

Backend — это просто пара «транспорт + фабрика стратегий» под общим именем. Имя
(`"access-tokens-db"`) используется в OpenAPI-схеме для секции security.

Смысл паттерна: транспорт и стратегия **независимы**. Можно взять cookie-транспорт с JWT
(токен в cookie, но самодостаточный) или Bearer с БД-стратегией. Проект использует
«cookie + БД» — комбинацию «браузерная сессия с серверным состоянием», по сути классические
серверные сессии, но с токеном вместо session_id в привычном виде.

---

## 3. Модели данных: где что лежит

### `User` (`core/models/user.py`)

```python
class User(Base, IdIntPkMixin, SQLAlchemyBaseUserTable[UserIdType]):
    access_tokens: Mapped[list["AccessToken"]] = relationship(back_populates="user")
```

`SQLAlchemyBaseUserTable` из fastapi-users даёт стандартные поля:

| Поле | Смысл | Роль в авторизации |
|---|---|---|
| `email` | Логин (уникальный) | Идентификация при логине |
| `hashed_password` | Пароль (bcrypt-хэш) | Проверка при логине |
| `is_active` | «Аккаунт включён» | Гейт `current_active_user` → 403 |
| `is_verified` | «Email подтверждён» | Гейт при `requires_verification=True` (сейчас выключен) |
| `is_superuser` | «Админ» | Гейт `current_active_superuser` → 403 |

### `AccessToken` (`core/models/access_token.py`)

```python
class AccessToken(Base, SQLAlchemyBaseAccessTokenTable[UserIdType]):
    user_id: Mapped[UserIdType] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="cascade"), nullable=False,
    )
    user: Mapped["User"] = relationship(back_populates="access_tokens")
```

Базовый класс даёт поля `token` (уникальная строка) и `created_at` (используется для
проверки срока жизни). Связь **один-ко-многим**: у одного пользователя может быть
несколько активных токенов (логин из браузера + логин из curl = два разных токена).
`ondelete="cascade"` — при удалении пользователя его токены удаляются автоматически.

---

## 4. DI-цепочка: как всё это собирается на каждый запрос

FastAPI разрешает зависимости лениво и **кэширует их в рамках одного запроса**: если два
эндпоинта зависят от одного и того же провайдера, он выполнится один раз. Цепочка строится
снизу вверх:

```
db_helper.session_getter (core/models/db_helper.py)
  │  открывает AsyncSession из пула, закрывает после запроса (yield-генератор)
  ▼
get_users_db (api/dependencies/authentication/users.py)
  │  session → SQLAlchemyUserDatabase(session, User) — «репозиторий пользователей»
  ▼
get_user_manager (api/dependencies/authentication/user_manager.py)
  │  users_db + BackgroundTasks → UserManager — «сервис пользователя»
  ▼ (эта ветка нужна для register/verify/reset и всех current_user-зависимостей)

get_access_tokens_db (api/dependencies/authentication/access_tokens.py)
  │  ещё одна AsyncSession → AccessTokenDatabase(session, AccessToken)
  ▼
get_database_strategy (api/dependencies/authentication/strategy.py)
  │  tokens_db → DatabaseStrategy — «механика токена»
  ▼
authentication_backend (api/dependencies/authentication/backend.py)
   transport + strategy → AuthenticationBackend — готов к логину/логауту/проверке
```

Замечания, которые важно понимать:

1. **Две отдельные сессии БД**. `get_users_db` и `get_access_tokens_db` каждая открывает
   свою `AsyncSession` (обе зависят от `session_getter`, но FastAPI кэширует зависимости
   по функции — а это одна и та же функция `session_getter`… однако `get_users_db` и
   `get_access_tokens_db` вызывают её через разные `Depends`, и в рамках одного запроса
   FastAPI закэширует `session_getter` — сессия будет одна, общая). Это не баг, а следствие
   того, что репозитории fastapi-users требуют разных типов баз.
2. **`UserManager` получает `BackgroundTasks`** — это то, как хуки (`on_after_register` и др.)
   планируют email/вебхуки после ответа. Без этого параметра хуки бы блокировали ответ.
3. **`yield`-генераторы** гарантируют, что сессия закроется даже при исключении в эндпоинте.

---

## 5. Логин: пошаговый разбор `POST /api/v1/auth/login`

Роутер создаётся библиотекой (`api/api_v1/auth.py`):

```python
router.include_router(fastapi_users.get_auth_router(authentication_backend))
```

Что происходит на запрос (здесь и дальше — поведение fastapi-users v14):

```
1. Клиент шлёт FORM-DATA (не JSON!):
       username=<email>&password=<пароль>
   Формат — OAuth2PasswordRequestForm: поле называется username, но fastapi-users
   кладёт туда email. Это частая ошибка при первом знакомстве с библиотекой.

2. Зависимости роута:
       get_user_manager (→ users_db → session)   — для проверки пароля
       backend.get_strategy                      — для создания токена

3. UserManager.authenticate(credentials):
       SELECT * FROM users WHERE email = :email
       PasswordHelper.verify_and_update(password, user.hashed_password)  # bcrypt
       → User | None

4. Если пользователь не найден / пароль неверен → 400 LOGIN_BAD_CREDENTIALS
   (заметьте: одна ошибка на оба случая — не раскрываем, существует ли email)

5. backend.login(strategy, user_manager, user):
       strategy.write_token(user):
           token = secrets.token_urlsafe()          # случайная строка
           INSERT INTO access_tokens (token, user_id, created_at)
           return token
       transport.get_login_response(token, user_manager):
           response.set_cookie("fastapiusersauth", token, max_age=3600,
                               httponly=True, samesite="lax", secure=False)

6. Ответ 200 → UserRead (email, id, is_active, is_superuser, is_verified)
```

Проверка curl'ом:

```shell
# Логин (обратите внимание: -F, а не -H 'Content-Type: application/json'!)
curl -c cookies.txt -X POST http://localhost:8000/api/v1/auth/login \
  -F "username=user@example.com" -F "password=secret"

# Cookie-файл теперь содержит fastapiusersauth=<случайная строка>
```

**Почему пароль не логируется и не хранится**: `PasswordHelper` хэширует bcrypt'ом при
регистрации и сверяет хэши при логине. Сервер никогда не видит пароль в открытом виде
после получения запроса (кроме момента проверки — и он не логируется).

---

## 6. Каждый следующий запрос: как сервер узнаёт, кто вы

Вот здесь — сердце всей системы. Возьмём защищённый эндпоинт:

```python
# api/api_v1/messages.py
@router.get("")
def get_user_messages(
    user: Annotated[User, Depends(current_active_user)],
):
    ...
```

`current_active_user` (`core/authentication/fastapi_users.py`) — это **фабрика зависимостей**:

```python
fastapi_users = FastAPIUsers[User, UserIdType](get_user_manager, [authentication_backend])
current_active_user = fastapi_users.current_user(active=True)
current_active_superuser = fastapi_users.current_user(active=True, superuser=True)
```

Что делает FastAPI, разрешая `Depends(current_active_user)`:

```
1. Authenticator перебирает бэкенды (у нас один):
   а) transport.get_token(request)
      → request.cookies.get("fastapiusersauth")
      → если cookie нет → 401 UNAUTHORIZED (конец, до эндпоинта дело не дойдёт)
   б) strategy.read_token(token, user_manager):
      → SELECT * FROM access_tokens WHERE token = :token
      → если строки нет → 401 (токен отозван/несуществует)
      → проверка срока: created_at + lifetime_seconds (3600) < now → 401 (истёк)
      → user_manager.get(access_token.user_id)
        → SELECT * FROM users WHERE id = :user_id
        → если пользователя нет (удалён) → 401
   Результат: (user, token)

2. Обёртки current_user применяют фильтры по флагам:
   active=True  → if not user.is_active → 403 FORBIDDEN
   superuser=True → if not user.is_superuser → 403 FORBIDDEN

3. User попадает в параметр user эндпоинта.
```

**Запомните разницу кодов** — она говорит о том, *на каком этапе* вас отфутболили:

| Код | Причина | Этап |
|---|---|---|
| **401** | Нет cookie / токена, токена нет в БД, токен истёк, пользователь удалён | «Я не могу установить, кто ты» |
| **403** | Ты известен, но `is_active=False` или `is_superuser=False` | «Я знаю, кто ты, но тебе нельзя» |

**Цена этой схемы**: каждый защищённый запрос = 2 запроса к PostgreSQL
(токен + пользователь). Плюс `UPDATE access_tokens` при логине, `DELETE` при логауте.
Это осознанный компромисс — см. раздел 8.

---

## 7. Роли и флаги: три гейта

| Зависимость | Требует | Ошибка при провале | Где используется |
|---|---|---|---|
| `current_active_user` | валидный токен + `is_active` | 401 / 403 | `/users/me`, `/messages`, `/home/`, `request-verify-token` |
| `current_active_superuser` | всё выше + `is_superuser` | 401 / 403 | `GET/PATCH/DELETE /users/{id}`, `/messages/secrets` |
| (без зависимости) | ничего | — | `/register`, `/login`, `/verify`, `/forgot-password`, `/reset-password`, `/users` (список!), `/service/stats` |

Как «выдать роль»: флаг `is_superuser` ставится только через `UserManager.create(safe=False)`
(скрипт `actions/create_superuser.py`) или напрямую в БД/админке. При регистрации через API
`safe=True` — клиент физически не может сам себе выдать суперпользователя: лишние поля
из `UserCreate` отбрасываются.

Про `is_verified`: роутер аутентификации подключён с закомментированным параметром:

```python
# api/api_v1/auth.py
router.include_router(
    router=fastapi_users.get_auth_router(authentication_backend),
    # requires_verification=True,   ← выключено
)
```

Если раскомментировать — все эндпоинты аутентификации начнут требовать подтверждённый email
(`current_active_verified_user` под капотом). Сейчас верификация работает, но ничего не
блокирует: неподтверждённый пользователь пользуется всем, кроме… тоже всего.

---

## 8. Почему opaque-токен в БД, а не JWT

Это ключевой архитектурный выбор проекта. Разберём честно, с обеих сторон.

### Как это работает сейчас (DatabaseStrategy)

- Логин: сервер генерирует случайную строку, сохраняет в БД, отдаёт в cookie.
- Каждый запрос: `SELECT` по таблице `access_tokens`.
- Логаут/отзыв: `DELETE` строки — токен умирает **мгновенно, гарантированно**.

### Как было бы с JWT

- Логин: сервер подписывает токен секретом (HMAC), отдаёт в cookie. В БД — ничего.
- Каждый запрос: проверка подписи и `exp` в памяти. Ноль обращений к БД.
- Логаут/отзыв: **проблема**. JWT нельзя «отозвать» — сервер лишь проверяет подпись.
  Нужен blacklist (обычно Redis с TTL до конца жизни токена), что возвращает состояние
  на сервер и обесценивает главное преимущество JWT.

### Сравнение

| Критерий | Opaque + DB (проект) | JWT |
|---|---|---|
| Валидация запроса | SELECT к БД | Проверка подписи (память) |
| Отзыв токена | Мгновенный (DELETE строки) | Сложный (blacklist) |
| Состояние сервера | Есть (stateful) | Нет (stateless) |
| Утечка содержимого | Не раскрывает ничего | Claims читаемы всеми (payload — base64, не шифрован) |
| Горизонтальное масштабирование | БД — общая точка | Ничего общего не нужно |
| Сложность кода | Минимальная | + секреты, + ротация, + blacklist |

### Почему для этого проекта DB-стратегия — разумный выбор

1. **Logout действительно работает.** В учебно-демо проекте с cookie-сессиями это главная
   фича: удалил строку — пользователь разлогинен везде, где используется этот токен.
2. **Отзыв из админки.** `AccessTokenAdmin` (SQLAdmin) показывает все токены — компрометированный
   токен можно удалить руками.
3. **Масштаб нагрузки это прощает.** При количестве пользователей, на которое рассчитан
   проект, два SELECT'а на запрос — ничто. Узкое место JWT (statelessness) тут не нужно.
4. **Простота и наглядность.** Весь поток аутентификации виден в одной таблице БД —
   идеально для понимания (и для этого гайда).

Когда стоит пересмотреть решение: высокая нагрузка (тысячи RPS на защищённые эндпоинты),
микросервисы (несколько сервисов должны валидировать токены без общей БД), mobile API с
refresh-токенами. Тогда — JWT или гибрид: opaque-токен, кэшируемый в Redis вместо БД.

---

## 9. Логаут: `POST /api/v1/auth/logout`

```
1. Требуется валидный токен (current_user_token) — но НЕ проверяется is_active.
   Заблокированный пользователь может разлогиниться. Это осознанное поведение.
2. strategy.destroy_token(token, user):
       DELETE FROM access_tokens WHERE token = :token
3. transport.get_logout_response():
       Set-Cookie: fastapiusersauth=""; (пустое значение, истекает сразу)
```

После этого cookie в браузере остаётся, но пустая и невалидная — следующий запрос вернёт 401.

---

## 10. Верификация email и сброс пароля — а тут уже JWT!

Неожиданный факт: **в проекте используются оба вида токенов, но для разных целей**.

| Токен | Тип | Где живёт | Как проверяется |
|---|---|---|---|
| Access-токен (логин) | Opaque, случайная строка | Таблица `access_tokens` | SELECT по БД |
| Verification-токен | **JWT** (подпись HS256) | Нигде (только в ссылке из письма) | Проверка подписи секретом |
| Reset-токен | **JWT** | Нигде (только в логе/письме) | Проверка подписи секретом |

Почему разница? Это разные задачи:

- **Access-токен** живёт долго, используется тысячи раз, должен отзываться → нужно состояние → БД.
- **Verification/reset-токен** используется **один раз** в короткий срок (1 час по умолчанию).
  Хранить его в БД незачем: подпись секретом (`verification_token_secret` /
  `reset_password_token_secret` из Settings) гарантирует, что токен выдан именно сервером,
  а `exp` — что он не просрочен. Состояние не нужно → JWT идеален.

Механика верификации:

```
1. POST /api/v1/auth/request-verify-token {email}   (требует current_active_user!)
2. UserManager.request_verify(user):
   → token = jwt.encode({aud: "fastapi-users:verification", exp: +3600, ...},
                        verification_token_secret)
3. on_after_request_verify(user, token):
   → ссылка http://host/verify-email/?token=... → письмо через Maildev
4. Пользователь открывает страницу → JS шлёт POST /api/v1/auth/verify {token}
5. UserManager.verify(token):
   → jwt.decode(token, secret, audience="fastapi-users:verification")  # подпись+срок
   → UPDATE users SET is_verified = true
```

Сброс пароля — то же самое с аудиторией `fastapi-users:reset` и секретом
`reset_password_token_secret`. Один нюанс: в `on_after_forgot_password` токен пишется в
**лог** вместо письма (demo-поведение, отмечено в `04_code_quality.md` как уязвимость).

> Забавный артефакт: подпись JWT-токенов проверяется по секрету из Settings, а
> `.env.template` содержит **пустые** значения секретов. Приложение стартует, но токены
> верификации подписываются пустым секретом — в production это критично заполнить.

---

## 11. Два «ложных» слоя защиты, о которых надо знать

### 11.1 `HTTPBearer(auto_error=False)` на роутере `/api/v1`

```python
# api/api_v1/__init__.py
http_bearer = HTTPBearer(auto_error=False)
router = APIRouter(prefix=..., dependencies=[Depends(http_bearer)])
```

Выглядит как «весь API требует Bearer-токен», но это не так:

- `auto_error=False` → если заголовка `Authorization` нет, зависимость молча вернёт `None`
  и запрос продолжится.
- Извлечённые учётные данные **никто не валидирует** — они просто выбрасываются.

Единственный реальный эффект — в Swagger UI появляется кнопка «Authorize», в которую можно
вставить токен для удобства (но он всё равно ни на что не влияет, т.к. токен ездит в cookie).
Эндпоинты `GET /api/v1/users` и `GET /api/v1/service/stats` — **публичные**: никакой
зависимости `current_*` у них нет.

### 11.2 Админка SQLAdmin — отдельная система

`Admin(app, session_maker=...)` (`create_fastapi_app.py`) — это самостоятельная панель со
**своей** session-based аутентификацией, никак не связанной с fastapi-users, таблицей
`users` и флагом `is_superuser`. Знание пароля обычного пользователя приложения не даёт
доступа в админку — и наоборот. Это важно понимать при аудите доступа: два независимых
периметра.

---

## 12. Шпаргалка: как защитить новый эндпоинт

```python
from typing import Annotated
from fastapi import APIRouter, Depends

from core.authentication.fastapi_users import current_active_user, current_active_superuser
from core.models import User

router = APIRouter(prefix="/things", tags=["Things"])

# Любой активный пользователь:
@router.get("")
async def list_things(user: Annotated[User, Depends(current_active_user)]):
    ...

# Только суперпользователь:
@router.delete("/{thing_id}")
async def delete_thing(
    thing_id: int,
    user: Annotated[User, Depends(current_active_superuser)],  # user можно не использовать —
):                                                             # зависимость сама вернёт 403
    ...
```

Правила большого пальца:

1. Нужен только факт входа → `current_active_user`.
2. Нужны админские права → `current_active_superuser`.
3. Эндпоинт должен быть публичным → не добавляйте зависимость (и помните, что
   роутер-уровневый `http_bearer` вас не защищает — см. 11.1).
4. Проверка «это мои данные» (владелец объекта) — **вручную в теле эндпоинта**:
   `if obj.user_id != user.id and not user.is_superuser: raise HTTPException(403)`.
   Библиотека за вас это не сделает.

---

## 13. Итоговая схема (всё на одном рисунке)

```
 Браузер                        Сервер                              PostgreSQL
 ───────                        ──────                              ──────────
 POST /auth/login          ──►  authenticate() ─ SELECT users ────► users
 (form: username,password)      write_token()  ─ INSERT token ────► access_tokens
 ◄── Set-Cookie:           ──┐
     fastapiusersauth=…      │
                             │
 GET /messages (cookie)    ──►  transport.get_token()
                                strategy.read_token() ─ SELECT ───► access_tokens
                                user_manager.get() ──── SELECT ───► users
                                is_active? ──► 200 | 401 | 403
 ◄── JSON ─────────────────┘

 POST /auth/logout         ──►  destroy_token() ─ DELETE ────────► access_tokens
 ◄── пустая cookie ────────┘

 (верификация/reset — вне этой схемы: JWT, подписанный секретом, состояние не нужно)
```

## 14. Что почитать дальше

- `07_authorization_report.md` — сравнение с JWT и OAuth 2.0, таблицы, рекомендации.
- `03_execution_flow.md` — все бизнес-процессы (регистрация, верификация, сброс).
- Исходники fastapi-users (в вашем venv): `fastapi_users/router/auth.py`,
  `fastapi_users/authentication/strategy/db.py`, `fastapi_users/manager.py` —
  после этого гайда они читаются легко и дают финальное понимание.
