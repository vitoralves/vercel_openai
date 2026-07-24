# IdeaGen

AI-powered business idea generator for the agent economy.

**Live demo:** [https://vercel-openai-red.vercel.app/](https://vercel-openai-red.vercel.app/)

Authenticated users get a **shared lifetime request pool**: **1 on Free**, **5 on Premium** (`premium_subscription` via Clerk Billing). **Generate and score each consume one request.**

**Stack:** Next.js (App Router) · FastAPI · Clerk Auth + Billing · OpenAI SSE streaming · Upstash Redis

## Architecture

```text
Browser (Clerk session)
   │  Bearer JWT
   ▼
Next.js ──rewrite──► FastAPI (/api/*)
                       ├─ JWT verify (Clerk JWKS)
                       ├─ hourly rate limit (Redis)
                       ├─ Premium check (Clerk Billing API)
                       ├─ request quota reserve/refund (Redis INCR)
                       ├─ stream structured idea (OpenAI SSE)
                       ├─ persist history on stream success (Redis list)
                       └─ optional score (OpenAI JSON, same quota)
```

| Choice | Why |
|--------|-----|
| Next.js + Python on one deploy | Portfolio-ready full stack; Vercel hosts both |
| Quota on the server | UI is advisory; Redis atomic `INCR` prevents abuse |
| SSE | Faster perceived UX than waiting for a full completion |
| History saved server-side at end of stream | Avoids lost paid generations if the client fails to POST |

## Features

- Sign-in required for `/product` and API routes
- Industry chips + optional context (max 500 chars)
- Structured Markdown: Problem, ICP, MVP, Moat, Risks, Go-to-market
- Generate / regenerate (no auto-fire on mount)
- Usage banner: `Free/Premium · N requests left` (generate & score share the pool)
- Idea history with favorites (Upstash)
- Copy Markdown + download `.md`
- Optional **Score this idea** (novelty / feasibility / overall; costs 1 request)
- Generate rate limit: 10/hour/user; score rate limit: 20/hour/user
- Failed/empty/aborted-before-content generations and failed scores refund the request credit
- Successful streams emit a final SSE `idea` event after server-side history save

## API

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/usage` | `{ plan, used, limit, remaining }` |
| `POST` | `/api/generate` | `{ context? }` → SSE stream + usage headers |
| `GET` | `/api/ideas` | List saved ideas |
| `POST` | `/api/ideas` | Save `{ content, context? }` |
| `POST` | `/api/ideas/{id}/favorite` | `{ favorite: boolean }` |
| `POST` | `/api/ideas/score` | `{ content, idea_id? }` → scores + usage (1 request) |

OpenAPI: `http://127.0.0.1:8000/docs` when the API is running locally.

Response headers on generate: `X-Plan`, `X-Used`, `X-Limit`, `X-Remaining`, `X-Model`.

## Local setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
npm install
```

`.env.local`:

```bash
OPENAI_API_KEY=
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=
CLERK_SECRET_KEY=
CLERK_JWKS_URL=https://YOUR_INSTANCE.clerk.accounts.dev/.well-known/jwks.json
UPSTASH_REDIS_REST_URL=
UPSTASH_REDIS_REST_TOKEN=
# optional
OPENAI_MODEL=gpt-5-nano
```

Python API SSE streams are configured with `maxDuration: 300` in `vercel.json` (plan limits still apply).

```bash
source .venv/bin/activate
npm run dev
```

- App: [http://localhost:3000](http://localhost:3000)
- API: [http://127.0.0.1:8000](http://127.0.0.1:8000)

### Tests

```bash
source .venv/bin/activate
pytest -q
```

## Deploy

Framework must be **Next.js**. Mirror all env vars on Vercel (Production + Preview), then:

```bash
vercel --prod
```

## Design decisions

1. **Shared lifetime pool (1 free / 5 premium)** — generate and score both spend credits; keyed by Clerk `user_id`.
2. **Reserve-then-refund** — blocks concurrent double-spends; refunds empty/failed streams and failed scores.
3. **Score is opt-in but metered** — useful product signal without an unbounded OpenAI path.
4. **Export is client-side `.md`** — useful immediately; PDF/public shares deferred.
5. **Empty/aborted streams refund** — credits stick only when tokens were produced; ideas persist via a final SSE `idea` event.

## What I’d do next

- Public shareable links (`/i/[id]`) with privacy controls
- PDF export
- Auto-eval after every generation (or Premium-only stronger model)
- Richer observability (latency dashboards, token estimates)
- Idea comparison view across history
