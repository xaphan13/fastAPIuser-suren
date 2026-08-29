# 06 — Фронтенд: Bootstrap, текущие страницы, рекомендации

## Общая характеристика фронтенда

Проект не имеет отдельного фронтенд-приложения (React, Vue и т.д.). Вся клиентская часть — это **серверно-рендеренные HTML-шаблоны на Jinja2** с минимальным inline-JavaScript и CSS-фреймворком **Bootstrap 5.3**. Шаблоны лежат в `fastapi-application/templates/`.

Рендеринг происходит на стороне FastAPI через `Jinja2Templates` (файл `jinja_templates.py`):
```python
templates = Jinja2Templates(directory=BASE_DIR / "templates")
```

Маршруты, отдающие HTML, вынесены в пакет `views/` и помечены `include_in_schema=False` (не попадают в OpenAPI-документацию).

---

## Использование Bootstrap

### Как подключён

Bootstrap подключается через **CDN** (jsDelivr) в базовом шаблоне `templates/base.html`:

```html
<link
  href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.7/dist/css/bootstrap.min.css"
  rel="stylesheet"
  integrity="sha384-..."
  crossorigin="anonymous"
>
```

Подключается **только CSS** — JS-бандл Bootstrap (`bootstrap.bundle.min.js`) не подключён. Это значит, что интерактивные компоненты Bootstrap (dropdowns, modals, collapse, tooltips, carousels), требующие Popper.js и JS-инициализации, **не работают**. В проекте они пока и не используются — весь интерактив реализован собственным inline-JS через `fetch()`.

### Версия

Bootstrap 5.3.7 — актуальная версия на момент анализа. Это современная ветка (без зависимости от jQuery, с CSS-переменными, dark mode support, RTL). Версия выбрана корректно.

### Какие компоненты Bootstrap используются

| Компонент | Где | Классы |
|---|---|---|
| Контейнер / сетка | `base.html` | `container`, `my-3` |
| List group | `home.html` | `list-group`, `list-group-item` |
| Badges | `home.html` | `badge text-bg-success`, `text-bg-warning` |
| Buttons | `home.html` | `btn btn-primary` |
| Spinner | `home.html`, `verification.html` | `spinner-border`, `visually-hidden` |
| Alerts | `home.html`, `verification.html` | `alert alert-success`, `alert-danger` |
| Flexbox-утилиты | `verification.html` | `d-flex flex-column align-items-center` |
| Скрытие элементов | везде | `d-none` |

Использование утилитарных классов (`d-none`, `my-3`, `visually-hidden`) — идиоматичный подход для Bootstrap 5.

---

## Текущие страницы

В проекте **6 HTML-шаблонов**, разделённых на две группы:

### Пользовательские страницы (рендерятся через `views/`)

| Шаблон | Маршрут | Назначение |
|---|---|---|
| `base.html` | — | Базовый каркас: `<head>`, Bootstrap CDN, блок `{% block main %}` |
| `home.html` | `GET /home/` | Главная страница авторизованного пользователя. Показывает email и статус верификации. Если email не подтверждён — кнопка «Verify e-mail», которая через `fetch` отправляет POST на `/api/v1/auth/request-verify-token` |
| `verification.html` | `GET /verify-email/` | Страница подтверждения email. Читает `token` из query-параметров, через `fetch` отправляет POST на `/api/v1/auth/verify`, при успехе редиректит на `/home/` |

### Email-шаблоны (рендерятся в `mailing/`)

| Шаблон | Назначение |
|---|---|
| `mailing/base.html` | Базовый каркас для писем (без Bootstrap, чистый HTML) |
| `mailing/email-verify/verification-request.html` | Письмо со ссылкой подтверждения email |
| `mailing/email-verify/email-verified.html` | Письмо-уведомление об успешном подтверждении |

### Чего нет (страницы, которые отсутствуют)

В проекте **нет** следующих страниц, типичных для приложения с аутентификацией:

- **Login** — страница входа (форма логина). Сейчас `/api/v1/auth/login` — это JSON-эндпоинт, возвращающий cookie. Веб-формы для входа нет.
- **Register** — страница регистрации. Аналогично, `/api/v1/auth/register` — JSON-API без HTML-формы.
- **Forgot password / Reset password** — нет HTML-страниц для ввода email и нового пароля, хотя API-эндпоинты (`/forgot-password`, `/reset-password`) подключены через `fastapi_users.get_reset_password_router()`.
- **Profile / Edit profile** — нет страницы редактирования данных пользователя (хотя `/api/v1/users/me` PATCH доступен).
- **Logout** — нет кнопки/страницы выхода (эндпоинт `/api/v1/auth/logout` существует).
- **404 / Error pages** — нет кастомных страниц ошибок.
- **Admin UI** — SQLAdmin предоставляет свою панель, но это не часть Jinja-фронтенда.

---

## Насколько современный подход

### Что сделано хорошо

1. **Bootstrap 5.3** — актуальная версия, без jQuery, с CSS-переменными.
2. **SRI-integrity** на CDN-ссылке — защита от подмены CDN-ресурса.
3. **Jinja2 template inheritance** — `home.html` и `verification.html` наследуются от `base.html`, используется `{% block %}`. Это правильный паттерн.
4. **Progressive enhancement** — страницы работают без JS на базовом уровне (показывается контент), а JS добавляет интерактив (fetch-запросы верификации).
5. **Responsive viewport meta** — корректный `<meta name="viewport">`.
6. **Accessibility** — используется `role="status"` для спиннеров, `visually-hidden` для скринридеров, `alert` role для ошибок.

### Что устарело или не соответствует современным практикам

| Проблема | Описание | Серьёзность |
|---|---|---|
| **Inline JS в шаблонах** | Весь JavaScript встроен прямо в HTML через `<script>` теги внутри `home.html` и `verification.html`. Не кэшируется браузером, не проходит линтинг, сложно тестировать. | 🟡 |
| **Нет отдельного JS-файла** | Отсутствует каталог `static/` и `StaticFiles`. Нет возможности подключить `app.js` как внешний ресурс. | 🟡 |
| **Нет JS-фреймворка / билд-системы** | Если проект будет расти, inline-JS в шаблонах не масштабируется. Нет ни Vite, ни esbuild, ни даже простого `static/js/app.js`. | 🟢 (зависит от планов) |
| **CDN вместо self-hosted** | Bootstrap подключён через CDN. Для production это зависимость от внешнего сервиса. SRI-хэш смягчает, но не решает проблему доступности. | 🟢 |
| **CSS Bootstrap без кастомизации** | Нет `custom.css` или SCSS-сборки. Нельзя переопределить тему, цвета бренда и т.д. | 🟢 |
| **Нет favicon / meta-тегов** | Отсутствует `<link rel="icon">`, Open Graph теги, `<meta name="description">`. | 🟢 |
| **Нет тёмной темы** | Bootstrap 5.3 поддерживает `data-bs-theme="dark"`, но это не настроено. | 🟢 |
| **Email-шаблоны без инлайн-стилей** | Письма (`mailing/base.html`) — чистый HTML без CSS. Многие почтовые клиенты (Outlook, Gmail) требуют инлайн-стили. | 🟡 |

---

## Что можно улучшить

### Краткосрочные (низкие усилия)

1. **Вынести inline-JS в `static/js/`**
   - Создать каталог `fastapi-application/static/js/`
   - Подключить `StaticFiles` в `create_fastapi_app.py`:
     ```python
     from fastapi.staticfiles import StaticFiles
     app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
     ```
   - Переместить JS из `home.html` → `static/js/home.js`, из `verification.html` → `static/js/verification.js`
   - Подключить в шаблонах: `<script src="{{ url_for('static', path='js/home.js') }}"></script>`
   - Передавать URL через `data-` атрибуты вместо интерполяции Jinja в JS:
     ```html
     <button id="verify-button" data-url="{{ url_for('verify:request-token') }}" ...>
     ```

2. **Добавить страницу логина (HTML-форма)**
   - Создать `templates/login.html` с формой (email + password)
   - Добавить маршрут в `views/login.py`
   - Форма отправляет POST на `/api/v1/auth/login` с `application/x-www-form-urlencoded` (fastapi-users cookie-транспорт поддерживает это)

3. **Добавить страницу регистрации**
   - Создать `templates/register.html` с формой
   - POST на `/api/v1/auth/register`

4. **Добавить кнопку Logout**
   - На `home.html` — кнопка, отправляющая POST на `/api/v1/auth/logout`

5. **Добавить favicon и базовые meta-теги** в `base.html`

6. **Добавить `custom.css`** — переопределить цвета бренда, шрифты

### Среднесрочные

7. **Self-hosted Bootstrap** — скачать CSS в `static/css/bootstrap.min.css`, убрать CDN-зависимость. Для production это надёжнее.

8. **Email-шаблоны с инлайн-CSS** — использовать `premailer` или `juice` (Python-библиотеки) для инлайнинга стилей в email-шаблонах. Либо прописать стили inline вручную.

9. **Страницы forgot-password / reset-password** — HTML-формы для этих потоков, поскольку API уже есть.

10. **Кастомные страницы ошибок** — `templates/404.html`, `templates/500.html`, зарегистрировать через `@app.exception_handler(404)` и т.д.

### Долгосрочные (если фронтенд будет расти)

11. **Решение о архитектуре фронтенда**: если проект останется небольшим — Jinja2 + Bootstrap + vanilla JS вполне достаточно. Если планируется сложный UI (дашборды, таблицы с сортировкой, real-time) — рассмотреть:
    - **HTMX + Alpine.js** — минимальный шаг от текущей архитектуры, серверный рендеринг с AJAX-обновлениями без SPA
    - **React/Vue SPA** — отдельный фронтенд-проект, общение через REST API (API уже есть)

12. **Бандлер (Vite)** — если появится много JS/CSS, использовать Vite для сборки, минификации, tree-shaking.

---

## Итоговая оценка

| Критерий | Оценка | Комментарий |
|---|---|---|
| Версия Bootstrap | ✅ 5.3.7 | Актуальная |
| Template inheritance | ✅ | Jinja2 `{% extends %}` используется правильно |
| Responsive | ✅ | viewport meta есть, Bootstrap grid адаптивен |
| Accessibility | ⚠️ Частично | role/aria есть на ключевых элементах, но нет skip-links, lang-атрибут = "en" хотя проект русскоязычный |
| JS-организация | ❌ | Inline-JS в шаблонах, нет static-каталога |
| Покрытие страницами | ❌ | Нет login/register/logout/forgot-password HTML-форм |
| Production-readiness | ⚠️ | CDN-зависимость, нет favicon, нет кастомизации |
| Email-стили | ❌ | Без CSS, плохо отобразится в почтовых клиентах |

**Общий вывод**: фронтенд минимально жизнеспособен для демонстрационного проекта. Подход (Jinja2 + Bootstrap через CDN) прост и понятен, но для production требуется как минимум вынести JS в статические файлы, добавить недостающие страницы (login, register, logout) и убрать зависимость от CDN. Если проект будет расширяться — стоит рассмотреть HTMX как эволюционный путь без перехода к SPA.
