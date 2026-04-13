# Next.js Login Starter

Минимальный стартовый шаблон под login page.

## Стек

- Next.js 15 (App Router)
- TypeScript
- Tailwind CSS (подключается стандартно через `create-next-app`)
- React Hook Form + Zod (опционально на следующем шаге)

## Быстрый старт

```bash
npm install
npm run dev
```

Откройте `http://localhost:3000/login`.

## Интеграция с backend

В `lib/api.ts` укажите реальный `NEXT_PUBLIC_API_BASE_URL` и endpoint логина.

## Что доработать дальше

- Добавить валидацию через Zod.
- Подключить реальный токен-менеджмент (cookie/httpOnly или access+refresh).
- Добавить forgot-password и rate-limit сообщения.
