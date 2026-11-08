# Fact Cookie Frontend Integration

Use this file as the single integration guide for the Fact Cookie backend. Base URL for local development is `http://localhost:8000`. Interactive docs are available at `http://localhost:8000/docs`.

## Backend setup for frontend testing

In `Fact Cookie Backend/.env`:

```env
BASE_URL=http://localhost:8000
FRONTEND_URL=http://localhost:3000
CORS_ORIGINS=http://localhost:3000
LLM_MODE=live
OPENROUTER_API_KEY=sk-or-...
TAVILY_API_KEY=tvly-...
BILLING_PROVIDER=mock
```

Then:

```powershell
cd "Fact Cookie Backend"
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe scripts\seed_demo.py   # optional demo user + API key
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Demo login: `demo@factcookie.local` / `demo-password-123`.

## Auth

All `/api/v1/*` routes accept either:

- Dashboard JWT: `Authorization: Bearer <access_token>`
- API key: `Authorization: Bearer fc_live_...`

For a browser frontend, use the JWT flow. Do not ship API keys in client-side code.

### Register

`POST /api/v1/auth/register`

```json
{ "email": "user@example.com", "password": "password123", "name": "User" }
```

Response `201`:

```json
{ "access_token": "...", "refresh_token": "...", "token_type": "bearer", "expires_in": 1800 }
```

### Login

`POST /api/v1/auth/login`

```json
{ "email": "user@example.com", "password": "password123" }
```

### Refresh

`POST /api/v1/auth/refresh`

```json
{ "refresh_token": "..." }
```

Refresh rotates both tokens. Store the new pair and retry the original request once after a `401`.

### Current user / update / logout

- `GET /api/v1/auth/me`
- `PATCH /api/v1/auth/me` — `{ "name": "New Name", "email": "new@example.com" }`
- `POST /api/v1/auth/logout` — `{ "refresh_token": "..." }`

## API keys

API keys are for server-to-server calls and the MCP connector, not for browser apps.

- `POST /api/v1/api-keys` — `{ "name": "backend-worker" }` → returns `key` once
- `GET /api/v1/api-keys`
- `DELETE /api/v1/api-keys/{id}`

Example response:

```json
{ "id": "...", "name": "backend-worker", "prefix": "fc_live_abc", "key": "fc_live_...", "created_at": "..." }
```

## Core flow: verify AI text

### Sync verification

Use `mode: "sync"` for short inputs. If `text` is longer than `SYNC_MAX_CHARS` (default `2000`), the backend automatically switches it to async and returns `status: "pending"`.

`POST /api/v1/verifications`

```json
{
  "text": "The Eiffel Tower is 330 metres tall and was completed in 1889.",
  "context": "Optional source material or known-good text.",
  "mode": "sync"
}
```

Response `201`:

```json
{
  "id": "verification-id",
  "status": "completed",
  "mode": "sync",
  "source_agent": "rest",
  "input_text": "...",
  "context_text": null,
  "orchestration_mode": "pipeline",
  "llm_mode": "live",
  "trace_id": "...",
  "corrected_text": null,
  "result": { "claims": [] },
  "error": null,
  "claim_count": 2,
  "tavily_search_count": 2,
  "tavily_extract_count": 1,
  "created_at": "...",
  "started_at": "...",
  "completed_at": "...",
  "claims": [
    {
      "id": "claim-id",
      "position": 0,
      "text": "The Eiffel Tower is 330 metres tall",
      "claim_type": "factual",
      "verdict": "supported",
      "confidence": 0.91,
      "explanation": "Found matching evidence.",
      "source_url": "https://example.com",
      "snippet": "...",
      "page_or_section": null,
      "corrected_text": null,
      "evidence": []
    }
  ]
}
```

### Async verification

`POST /api/v1/verifications` with `"mode": "async"` returns a pending verification. Poll the verification until `status` is `completed` or `failed`.

```js
const created = await api.post('/api/v1/verifications', {
  text: longAnswer,
  mode: 'async',
});

let verification = created;
while (['pending', 'queued', 'running'].includes(verification.status)) {
  await new Promise((r) => setTimeout(r, 1500));
  verification = await api.get(`/api/v1/verifications/${verification.id}`);
}
```

Statuses: `pending`, `queued`, `running`, `completed`, `failed`.

### Verdicts

- `supported` — evidence supports the claim
- `outdated` — evidence suggests the claim is no longer current
- `contradicted` — evidence contradicts the claim
- `unverifiable` — not enough reliable evidence

Non-`unverifiable` verdicts should include `source_url` and/or `snippet` evidence.

## Verification history

- `GET /api/v1/verifications` — list; supports `verdict`, `status`, `source_agent`, `search`, `date_from`, `date_to`, `limit`, `offset`
- `GET /api/v1/verifications/{id}` — detail + claims
- `DELETE /api/v1/verifications/{id}`
- `GET /api/v1/verifications/{id}/export?format=json|csv`
- `GET /api/v1/jobs/{job_id}` — job status if you have a job id

## Usage and billing

- `GET /api/v1/usage/current`
- `GET /api/v1/usage/history?limit=50&offset=0`
- `GET /api/v1/billing/plans`
- `GET /api/v1/billing/subscription`
- `POST /api/v1/billing/checkout` — `{ "plan_id": "pro" }`
- `POST /api/v1/billing/portal`
- `POST /api/v1/billing/webhook` — Stripe only; do not call from frontend
- `POST /api/v1/billing/dev/simulate` — dev-only when `ENABLE_DEV_ENDPOINTS=true`

With `BILLING_PROVIDER=mock`, checkout/portal return mock URLs and subscription changes can be simulated locally.

## Documents

Upload `.pdf`, `.txt`, `.md`, or `.markdown` files for document-grounded verification.

- `POST /api/v1/documents` — `multipart/form-data` with `file` and optional `filename`
- `GET /api/v1/documents`
- `GET /api/v1/documents/{id}`
- `DELETE /api/v1/documents/{id}`

Browser example:

```js
const form = new FormData();
form.append('file', fileInput.files[0]);
await api.post('/api/v1/documents', form);
```

## Preferences

- `GET /api/v1/preferences`
- `PUT /api/v1/preferences`

```json
{
  "trusted_domains": ["who.int", "cdc.gov"],
  "blocked_domains": ["example-spam.com"],
  "strictness": "standard",
  "recency_days": 365,
  "citation_style": "apa",
  "language": "en"
}
```

## Insights

- `GET /api/v1/insights/top-claims?limit=10`
- `GET /api/v1/insights/top-domains?limit=10`
- `GET /api/v1/insights/verdict-breakdown`
- `GET /api/v1/insights/trends?days=30`

## MCP connector

MCP is mounted at `/mcp` for MCP clients, not normal browser REST calls. It supports OAuth 2.1 or `fc_live_...` API keys. Discovery:

- `GET /.well-known/oauth-authorization-server`
- `GET /.well-known/oauth-protected-resource`

MCP tools: `health`, `verify_text`, `verify_claim`, `check_citation`, `get_usage`, `get_verification`, `list_verifications`.

## Error handling

Errors use this envelope:

```json
{
  "error": {
    "code": "validation_error",
    "message": "Request validation failed.",
    "details": {},
    "request_id": "..."
  }
}
```

Common codes: `unauthorized` `401`, `forbidden` `403`, `not_found` `404`, `conflict` `409`, `validation_error` `422`, `rate_limited` `429`, `budget_exceeded` `429`, `quota_exceeded` `402`, `payload_too_large` `413`.

## Minimal frontend checklist

1. Register or login → store `access_token` and `refresh_token`.
2. On `401`, call `/api/v1/auth/refresh` once and retry.
3. For short answers, `POST /api/v1/verifications` with `mode: "sync"`.
4. For long answers, use `mode: "async"` and poll `GET /api/v1/verifications/{id}`.
5. Render `claims[]` with `verdict`, `confidence`, `explanation`, `source_url`, and `snippet`.
6. Show usage/quota from `GET /api/v1/usage/current`.
