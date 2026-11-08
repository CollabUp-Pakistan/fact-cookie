# Fact Cookie API

Base URL: `http://localhost:8000`. REST routes are under `/api/v1`. Auth accepts either a dashboard JWT (`Authorization: Bearer <access_token>`) or an API key (`Authorization: Bearer fc_live_...`).

## Health

- `GET /health`
- `GET /api/v1/health`

## Auth

- `POST /api/v1/auth/register` — `{email, password, name?}` → token pair
- `POST /api/v1/auth/login` — `{email, password}` → token pair
- `POST /api/v1/auth/refresh` — `{refresh_token}` → rotated token pair
- `POST /api/v1/auth/logout` — `{refresh_token}`
- `GET /api/v1/auth/me`
- `PATCH /api/v1/auth/me` — `{name?, email?}`
- `POST /api/v1/auth/password-reset/request` — `{email}`
- `POST /api/v1/auth/password-reset/confirm` — `{token, password}`

## API keys

- `POST /api/v1/api-keys` — `{name}` → full key shown once
- `GET /api/v1/api-keys`
- `DELETE /api/v1/api-keys/{key_id}`

## Verifications

- `POST /api/v1/verifications` — `{text, context?, mode: "sync"|"async"}` → verification with per-claim verdicts
- `GET /api/v1/verifications` — list
- `GET /api/v1/verifications/{id}` — detail + claims
- `DELETE /api/v1/verifications/{id}`
- `GET /api/v1/verifications/{id}/export` — CSV
- `GET /api/v1/jobs/{job_id}` — async job status

Verdicts: `supported`, `outdated`, `contradicted`, `unverifiable`. Non-`unverifiable` verdicts are only returned when deterministic guardrails find real evidence (source URL + snippet).

## Usage and billing

- `GET /api/v1/usage/current`
- `GET /api/v1/usage/history`
- `GET /api/v1/billing/plans`
- `GET /api/v1/billing/subscription`
- `POST /api/v1/billing/checkout` — `{plan_id}`
- `POST /api/v1/billing/portal`
- `POST /api/v1/billing/webhook` — Stripe signature-verified, idempotent
- `POST /api/v1/billing/dev/simulate` — dev-only mock subscription changes when `ENABLE_DEV_ENDPOINTS=true`

## Documents and preferences

- `POST /api/v1/documents` — multipart upload (`.pdf`, `.txt`, `.md`, `.markdown`)
- `GET /api/v1/documents`
- `GET /api/v1/documents/{id}`
- `DELETE /api/v1/documents/{id}`
- `GET /api/v1/preferences`
- `PUT /api/v1/preferences`

## Insights

- `GET /api/v1/insights/summary`
- `GET /api/v1/insights/trends`

## MCP connector

Mounted at `/mcp` (Streamable HTTP). Discovery:

- `GET /.well-known/oauth-authorization-server`
- `GET /.well-known/oauth-protected-resource` and `/.well-known/oauth-protected-resource/mcp`

OAuth endpoints:

- `POST /oauth/register` — dynamic client registration
- `GET /oauth/authorize` — validates client and shows login handoff
- `POST /oauth/authorize` — authenticated consent; returns redirect with code
- `POST /oauth/token` — `authorization_code` or `refresh_token` grants (PKCE supported)
- `POST /oauth/revoke`

MCP tools: `verify_text`, `verify_claim`, `check_citation`, `get_usage`, `get_verification`, `list_verifications`, `health`.
