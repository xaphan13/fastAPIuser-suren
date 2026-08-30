---
name: md_articles blog vs auth layer separation
description: Архитектурное разделение пакета md_articles на блог и авторизацию; порядок middleware в Starlette
type: project
---

В `fastapi-application/md_articles/` три разнородных слоя разнесены по разным файлам (названия длинные — осознанно, для полной самодокументации):

- `setup_frontend.py` — plug-in блога: `setup_auth_static_include(app)` (вызывает `add_middleware_auth`, монтирует `/static`, подключает `router_blog_api`).
- `auth_middleware_helpers.py` — ВСЯ авторизация в одном файле: `auth_add_middleware(app)` (`add_middleware(BaseHTTPMiddleware, dispatch=inject_current_user_middleware)`, `add_middleware(SessionMiddleware, ...)`, `add_exception_handler(RequestValidationError, custom_request_validation_exception_handler)`), плюс CSRF/`require_login_api`/сессионные/парольные хелперы.
- `api_blog.py` — только роуты + `UserOut` + `_user_out`.
- (старый `web_utils.py` удалён).

Аналогично в `fastapi-application/`:
- `frontend_routing.py` — `setup_react_routing_assets(app)` (mount `/assets` + catch-all React Router).

**Why:** Пользователь явно классифицировал `inject_current_user_middleware` как авторизацию, а не как часть blog setup, и попросил раскидать `register_md_articles` на два слоя — настройки блога и настройки авторизации. Цель — переиспользуемый auth-слой, независимый от блога. Также выяснилось, что в исходном коде `app.middleware("http")(...)` ставил current_user middleware снаружи SessionMiddleware, и `request.session` падал с `AssertionError` — баг был, просто не все пути его триггерили. Фикс: добавлять current_user middleware ДО SessionMiddleware, а не после. Имена файлов и функций подобраны так, чтобы по `git grep` сразу читалось: что файл делает, без заглядывания внутрь (`frontend_*` = про фронтенд, `auth_*` = про авторизацию, `*_include` = подключает роутер, `setup_*` = инициализирует).

**How to apply:** Новые auth-зависимости (CSRF, `require_login`, сессионные helpers) класть в `auth_middleware_helpers.py`; хелперы работы с паролями/сессией — туда же. JSON-роутер блога должен импортировать auth-хелперы из `auth_middleware_helpers`, а не из `web_utils`. Имена длинные — не сокращать без явного запроса пользователя.

## Starlette middleware order (важно)

В Starlette `app.add_middleware(cls, ...)` делает `user_middleware.insert(0, ...)`, и в `build_middleware_stack` стек оборачивается в обратном порядке (`reversed(middleware)`). Это значит:

- middleware, добавленная **позже**, окажется **снаружи** (ближе к `ServerErrorMiddleware`).
- middleware, добавленная **раньше**, окажется **внутри** (ближе к роуту).

**Следствие для current_user + SessionMiddleware:** чтобы `request.session` работало в current_user middleware, добавлять нужно в порядке:

```python
app.add_middleware(BaseHTTPMiddleware, dispatch=current_user_mw)   # раньше → внутри
app.add_middleware(SessionMiddleware, ...)                          # позже  → снаружи
```

Если перепутать порядок (как было в старом `__init__.py` через `app.middleware("http")(...)`), то `get_current_user` упадёт с `AssertionError: SessionMiddleware must be installed to access request.session`.
