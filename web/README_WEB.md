# OGP Builder Web

Веб-версия приложения на `FastAPI` с авторизацией, личным кабинетом и генерацией жалобы.

## Структура

- `web/` - веб-часть проекта
- `shared/` - общее ядро, которое использует и web, и desktop
- `web/ogp_web/templates` - HTML-шаблоны
- `web/ogp_web/static` - CSS и JavaScript
- `web/data/` - логи и локальные служебные файлы веб-приложения

## База данных

Runtime-бэкенд веб-приложения: только PostgreSQL.

- `DATABASE_URL` обязателен для старта приложения.
- При отсутствии `DATABASE_URL` приложение завершается с понятной ошибкой и не стартует в fallback-режиме.

Пример для PostgreSQL:

```env
DATABASE_URL=postgresql://user:password@host:5432/dbname
```

## Локальный запуск

```powershell
cd web
py -m pip install -r requirements_web.txt
py run_web.py
```

После запуска откройте:

```text
http://127.0.0.1:8000
```

## Настройки через `.env`

Файл `web/.env` подхватывается автоматически.

Пример:

```env
OPENAI_API_KEY=sk-...
OPENAI_PROXY_URL=http://127.0.0.1:8080
OGP_WEB_SECRET=change-me
```

- `OPENAI_API_KEY` - ключ OpenAI
- `OPENAI_PROXY_URL` - прокси для OpenAI, если нужен
- `OGP_WEB_SECRET` - секрет для cookie-сессий

## Заливка на `ispmanager`

Ниже самый практичный вариант для этого проекта: `ispmanager` проксирует запросы на локальный `uvicorn`.

### 1. Что загрузить на сервер

Сохраняйте структуру каталогов:

```text
site-root/
  shared/
  web/
    .env
    requirements_web.txt
    run_web.py
    server.py
    ogp_web/
```

Важно: папки `web` и `shared` должны лежать рядом, потому что веб-часть импортирует общее ядро из `shared`.

### 2. Что включить в `ispmanager`

По инструкции ispmanager для Python-приложений сначала:

- установите Python в `Software configuration`;
- у пользователя сайта включите `Can use Python` и `Shell access`;
- создайте сайт и в расширенных настройках выберите Python handler с запуском серверного файла и портом.

Источник: официальная инструкция ispmanager по Python/Flask:
https://www.ispmanager.com/knowledge-base/flask-installation-in-ispmanager-6

### 3. Какой файл запускать

Для сервера используйте:

```text
web/server.py
```

Это production-entrypoint без `reload`, в отличие от локального `run_web.py`.

### 4. Какой порт указать

В `ispmanager` задайте любой свободный локальный порт, например:

```text
20000
```

И передайте его в аргументы запуска:

```text
--port 20000
```

При необходимости можно явно указать и host:

```text
--host 127.0.0.1 --port 20000
```

### 5. Установка зависимостей

В каталоге `web`:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements_web.txt
```

Если `ispmanager` создаёт окружение сам, просто установите зависимости в окружение сайта из `requirements_web.txt`.

### 6. Что проверить в `.env`

Минимум:

```env
OPENAI_API_KEY=sk-...
OPENAI_PROXY_URL=
OGP_WEB_SECRET=long-random-secret
```

### 7. Что должно заработать после запуска

- `/login` - вход и регистрация
- `/profile` - личный кабинет
- `/complaint` - форма жалобы

Если сайт открывается, но AI не работает, сначала проверьте:

- корректность `OPENAI_API_KEY`
- нужен ли `OPENAI_PROXY_URL`
- видит ли сервер интернет

## Почему такая схема хороша

- web остаётся основной версией проекта;
- `shared` используется в одном месте и не дублируется;
- локальный запуск и серверный запуск разделены;
- под `ispmanager` не нужно запускать dev-режим.
