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

## Production Deployment

Production deployment for this repository is GitHub-backed and documented outside this file.

Start here:

- `../AGENTS.md`
- `../docs/OPERATIONS_INDEX.md`
- `../docs/github_deploy.md`
- `../docs/postgresql_migrations.md`

Key rule:

- do not deploy by manually copying local files into the live runtime directory
- update the server from `/srv/lawyer5rp-deploy/repo`
- preserve server-only runtime state such as `web/.env`, `web/.venv`, and `web/data`

## Production Entry Point

For production, use:

```text
web/server.py
```

This is the production entrypoint without local dev reload behavior.

## Quick Troubleshooting

If the site opens but AI-related behavior fails, check:

- correctness of `OPENAI_API_KEY`
- whether `OPENAI_PROXY_URL` is required in the current environment
- whether the server can reach external dependencies
