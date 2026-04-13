# Reflex Login Starter

Python-first шаблон для login page.

## Стек

- Reflex
- Python 3.11+

## Быстрый старт

```bash
python -m venv .venv
source .venv/bin/activate
pip install reflex
reflex init
reflex run
```

Затем замените созданные файлы на шаблон из этой папки и снова выполните `reflex run`.

## Что есть в шаблоне

- Поля email/password.
- Состояния `loading/error/success`.
- Функция для вызова backend API (`/auth/login`).

## Что доработать

- Перенести токен в cookie-based flow.
- Добавить forgot-password, captcha и ограничение попыток.
