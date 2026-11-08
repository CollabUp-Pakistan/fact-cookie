# Decisions

## Database

SQLAlchemy 2.0 async with Alembic. SQLite+aiosqlite is the default for zero-setup local/dev; `DATABASE_URL` switches to Postgres+asyncpg. Repositories/services keep DB access swappable.

## OAuth for MCP

Implemented a minimal OAuth 2.1 authorization server in FastAPI rather than relying on FastMCP's provider storage. Reasons: one account system for dashboard and connector, full control over DCR/PKCE/refresh rotation, and FastMCP only needs to validate tokens. FastMCP uses a custom `TokenVerifier` that accepts:

- MCP-audience JWTs issued by `/oauth/token` (audience `factcookie:mcp`), with revocation/expiry checked against `oauth_tokens`.
- `fc_live_...` API keys for agents without OAuth.

Discovery is served at `/.well-known/oauth-authorization-server` and `/.well-known/oauth-protected-resource*`. Dynamic registration, authorization code + PKCE, refresh rotation, and revocation are implemented. The login/consent handoff is a minimal backend page that redirects to `FRONTEND_URL`; the frontend team can replace it later.

## LLM

OpenRouter is accessed through the Agents SDK `OpenAIChatCompletionsModel` (Chat Completions, not Responses). `LLM_MODE=mock` gives deterministic offline results. Default orchestration is `pipeline` because free models are unreliable at tool calling; `agents` mode is available for stronger models. Tracing uses a custom JSONL processor and does not require an OpenAI key.

## Retrieval

Tavily SDK is primary when `TAVILY_API_KEY` is set. HTTP+trafilatura is the fallback with an SSRF guard that validates every redirect hop. Documents are extracted page-aware (PyMuPDF for PDF) and searched with SQLite FTS5 when available.

## Billing

Provider interface with `MockBillingProvider` for local/dev and a Stripe-style implementation activated only when Stripe keys are configured. Webhooks are signature-verified and idempotent via `billing_events`.

## Verification guardrails

Deterministic post-validation enforces the golden rule: no `supported`/`outdated`/`contradicted` verdict without non-empty `source_url` and `snippet`. Failures downgrade to `unverifiable` instead of crashing.
