# Guru Ears

Guru Ears is an evidence-led listening portal for a focus brand and its competitive set. It
collects client-safe public/licensed sources, preserves provenance, measures uncertainty, and
turns the corpus into share-of-voice, sentiment, conversation-mix, app-review, theme, and
coverage views.

The product is two services: a **Flask JSON API** (`app.py` + `api/` + `core/`) and a
**Next.js App Router UI** (`web/`) in the "Studio Duotone" visual identity. The migration is
complete — Flask no longer renders HTML; every screen is native React talking to `/api/v1/*`.

## Architecture

```text
Browser :3000
  ├─ pages / assets ─────────────> Next.js (web/)
  └─ /api/* first-party proxy ──> Flask :5000
                                     ├─ /api/v1/* JSON  (api/)
                                     ├─ core/insights.py analytics
                                     ├─ collectors / scoring worker threads
                                     └─ SQLite guru.db
```

Flask owns authentication, tenancy, collection, scoring, analytics, and persistence. Next
renders typed API responses and never recalculates a backend metric. Session cookies stay
first-party because the browser reaches Flask through the Next rewrite (`web/next.config.ts`);
there is no CORS and no token auth. Every mutation sends `X-CSRF-Token` (fetched once from
`GET /api/v1/csrf`), which the API's `protect_portal` guard requires.

## Quickstart

Requirements: Python 3.10+, Node 20+, npm.

```powershell
python -m pip install -r requirements.txt
npm install
npm run dev
```

Open `http://127.0.0.1:3000`. The command runs Flask on `:5000` and Next on `:3000` via
`concurrently`. `guru.db` is created and seeded on first boot. Seed accounts are
`admin` / `admin123` and `bank` / `viewer123` — override both passwords before sharing.

`python app.py` alone serves only `/api/v1/*` and `/static/brand/*` on `:5000`; it refuses to
start if the port is already occupied.

## Environment

Copy `.env.example` to `.env`. Key settings:

- `GURU_SECRET_KEY`, `GURU_ADMIN_PASSWORD`, `GURU_VIEWER_PASSWORD`, `GURU_HOST`, `GURU_PORT`
- `GURU_API_ORIGIN` points Next's server-side auth check at a non-default Flask origin
- `HF_TOKEN`, `SENTIMENT_MODEL_ID`, `CLASSIFY_MODEL_ID`
- collection credentials allow-listed in `core/sources.py`: X, Reddit, YouTube, DataForSEO,
  Bluesky, App Store / Play Store, Meta, Google AI (Gemini), plus the model-id settings

The Admin UI (`/admin`) stores allow-listed provider settings per workspace, with shared
settings as fallback and environment variables taking precedence. Never commit `.env` or
`guru.db`.

## Commands

```powershell
npm run dev                     # Flask :5000 + Next :3000
npm run gen:types               # openapi.yaml -> web/lib/api-types.ts
npm run typecheck               # tsc --noEmit
npm run lint                    # eslint --max-warnings=0
npm run build                   # next build
npm run test:python             # unittest: core + API parity
npm run test:e2e                # Playwright journey (see below)
npm run check                   # test:python + typecheck + lint + build
```

Playwright needs its browser once: `npm run test:e2e:install --workspace web`. The e2e run
boots the dev stack itself unless one is already listening — stop a stale `:3000` / `:5000`
first, or it tests the running code.

## Repository map

- `app.py` — Flask app: session auth, CSRF, tenancy, worker threads, registers `api/`
- `api/` — the `/api/v1` blueprint; wraps `core/insights.*` and the helpers, no analytics of its own
- `core/`, `schema.sql` — analytics, collectors, entity matching, scoring, SQLite schema
- `openapi.yaml` — hand-authored API contract; `web/lib/api-types.ts` is generated from it
- `web/` — Next.js App Router, strict TypeScript, Studio Duotone; `web/tests/e2e` Playwright
- `static/brand/` — canonical brand assets, served by Flask and proxied by Next
- `tests/` — backend and API-parity tests (`test_api_parity.py` guards number drift)
- `docs/` — architecture, UX, design, parity, and the add-a-feature workflow

## Deployment

Run Flask and `next start` as separate processes behind one TLS reverse proxy: route `/api/*`
and `/static/brand/*` to Flask, everything else to Next. Keep both service hosts private, use
a long random `GURU_SECRET_KEY`, terminate TLS at the proxy so session cookies are `Secure`,
and back up `guru.db`.

For temporary Cloudflare sharing see `scripts/share.ps1` / `scripts/share.sh` — convenience
tools, not a production topology.
