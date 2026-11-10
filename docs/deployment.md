# Deployment

Taking it beyond a laptop.

[&larr; Back to the README](../README.md)

---

## Deployment

The two halves deploy independently to different kinds of host, because they are
different kinds of program: the SPA is static files, the API is a long-lived
Python process.

```
Browser ──► Vercel (frontend/dist, static)
               │  /api/* rewritten (vercel.json), same origin, cookie stays first-party
               ▼
            Render / Railway / Fly  (uvicorn app.main:app)
               ▼
            Neon PostgreSQL
```

### 1. Database: Neon

Any managed PostgreSQL works; Neon is what was used here. The repo no longer
carries a `neon.ts` - it was a leftover from the Next.js version and was removed
along with the other stale Node tooling. Recreate it only if you want Neon's
infrastructure-as-code:

```bash
npm i -g neon@latest && neon login
neon config init     # writes a fresh neon.ts
neon link --project-id <your-project-id> --branch production -y
neon deploy          # applies neon.ts to the branch
```

Or skip all of it and copy the connection string out of the Neon dashboard.

`neon link` and `neon deploy` write the live credentials into `.env.local`
(git-ignored): `DATABASE_URL` (pooled), `DATABASE_URL_UNPOOLED` (direct),
`NEON_BRANCH`, and the Neon Auth URLs.

> **Convert the scheme before handing the URL to this backend.** Neon emits
> `postgresql://…`; SQLAlchemy here uses psycopg 3, so it needs
> `postgresql+psycopg://…`. Passing Neon's string unchanged fails with
> `ModuleNotFoundError: No module named 'psycopg2'`.
>
> ```
> postgresql://…        →  postgresql+psycopg://…
> ```

Use the **pooled** URL for the running API and the **unpooled** one for
migrations. Apply the schema once:

```bash
cd backend
DATABASE_URL="postgresql+psycopg://…<unpooled host>…/neondb?sslmode=require" alembic upgrade head
```

Verify: `SELECT version_num FROM alembic_version;` returns `0009_payment_modes`
(the newest file in `backend/alembic/versions/`), and `information_schema.tables`
lists the 19 application tables.

Run the same command again after every pull that adds a migration. The API
does not migrate on start, so a new column the code expects and the database
lacks shows up as a 500 on the first request that touches it.

### 2. Backend: Render, Railway or Fly

Not Vercel: this app runs a background worker thread and holds a database
connection pool across requests, neither of which survives in a serverless
function.

- **Root directory** `backend`
- **Build** `pip install -r requirements.txt`
- **Start** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

Environment:

```bash
DATABASE_URL="…-pooler…?sslmode=require"   # the pooled string
AUTH_SECRET="<32+ random chars>"           # python -c "import secrets; print(secrets.token_hex(32))"
CORS_ORIGINS="https://your-app.vercel.app"
SEED_DEMO_DATA=false                       # true only if you want the demo tenant in production
COOKIE_SECURE=true                         # HTTPS
COOKIE_SAMESITE=lax                        # lax works because of the rewrite in step 3
APP_TIMEZONE="Asia/Kolkata"                # the shop's clock; this is the default, see below
GOOGLE_API_KEY="…"                         # optional, free; smarter NLP + OCR
```

Health check: `GET /api/health`.

**The clock.** Render, Railway and Fly all run in UTC, and every date in this
app is the server's local time: "today" on the dashboard, the date stamped on
an order accepted from Telegram, the day a payment is checked against. For a
shop in India, UTC is five and a half hours behind, so from midnight to 5:30
in the morning the server would still be on yesterday, and a payment dated
today would be refused as being in the future. `APP_TIMEZONE` puts the whole
process on the shop's clock at start-up. It defaults to `Asia/Kolkata`, so a
deployment in India needs nothing set; a shop elsewhere sets its own IANA name
(`Asia/Dubai`, `Europe/London`). Three details:

- A `TZ` variable set on the host wins over `APP_TIMEZONE`. Use one or the
  other, not both with different values.
- An unknown name is logged as a warning and the machine clock is kept.
- Rows written before this setting existed were stamped in UTC and are not
  rewritten. For India they read up to five and a half hours early, never
  late, so none of them is dated in the future.

### 3. Frontend: Vercel

The API client calls **relative** `/api/...` paths, so production needs those
paths to resolve on the same origin. [`frontend/vercel.json`](../frontend/vercel.json)
does that with a rewrite. Edit `REPLACE-WITH-YOUR-BACKEND-HOST` to your step-2
host before the first deploy.

- **Root Directory** `frontend`  ← set this in Project Settings, or the build fails
- Framework preset, build command and output directory come from `vercel.json`

Because the browser only ever talks to the Vercel origin, the session cookie
stays first-party: no CORS preflight, and `SameSite=lax` is enough. If you
instead point the SPA straight at the API's own domain, you must switch to
`COOKIE_SAMESITE=none` with `COOKIE_SECURE=true`, and some browsers will still
drop the cookie.

### Serverless note

If you do put the API somewhere without a persistent process, set
`DISABLE_WORKER=true` and rely on the synchronous `drain_queue()` that already
runs after every business write. `POST /api/events/drain` is available as a cron
target for retrying dead-lettered events.

---

