# DineSmartAI — public website (React + Tailwind)

Marketing and auth entry before the **DineSmartAI** AI chat at `/assistant`.

## Commands

Run everything from the **`web`** folder (the one that contains `package.json` and `vite.config.ts`), not a subfolder named `#` or any other path.

```bash
cd web
npm install
npm run dev
```

Do **not** append shell comments on the same line when copying scripts (e.g. avoid `npm run build # comment` in some terminals). Use a newline or run `npm run build` alone.

Dev server: `http://127.0.0.1:5173` (proxies `/assistant` and `/v1` to port 8000).

```bash
npm run build
```

Outputs to `web/dist`. When present, FastAPI serves this SPA at `/` and the chat at `/assistant`.

## Guest / demo mode

**Continue as guest** sets `localStorage` keys `dinesmartai_guest` and `dinesmartai_demo_prefs`, then opens `/assistant?demo=1`. The chat page shows a dismissible demo banner.

Sign-in / sign-up forms (demo) clear guest keys and navigate to `/assistant` on submit.

## Env

- `VITE_ASSISTANT_URL` — override assistant URL (default `/assistant`).
