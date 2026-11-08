# Fact Cookie Backend — Plan

Status: implementation in progress.

## Product in one paragraph

Fact Cookie verifies AI-written answers. It extracts checkable claims (numbers, dates,
names, quotes, citations), looks each one up in live web pages (Tavily) and the user's
uploaded documents, and returns a per-claim verdict with evidence. The golden rule is
enforced deterministically in code: any verdict other than `unverifiable` must carry a
real source URL and a snippet that actually appears in the retrieved source text.

## Milestones

| # | Milestone | Exit criteria |
|---|-----------|---------------|
| a | Skeleton, config, DB, migrations, health | `uvicorn app.main:app` boots; `/health` 200; tables created / migrations run; pytest green |
| b | Auth + API keys | register/login/refresh/logout/me/password reset; argon2; JWT access + rotating refresh; `fc_live_` keys hashed, prefix, last-used, revoke |
| c | Plans, usage, billing | seeded plans; limits checked in REST+MCP; usage events; mock provider + dev simulate; Stripe-signature webhook handler idempotent |
| d | Retrieval + documents | Tavily search/extract providers, HTTP fallback with SSRF guard, mock providers, page-aware PDF/TXT/MD indexing and search |
| e | LLM layer | OpenRouter via Agents SDK Chat Completions model; mock mode deterministic; custom trace processor to JSONL; typed outputs + repair + tolerant parsing; fallbacks; both orchestration modes |
| f | Verification service, jobs, cache, REST, insights | sync+async verification; persistence; cache; export; insights; tests |
| f | (merged above) | |
| g | FastMCP connector | `/mcp` mounted with custom verifier accepting JWT and API keys; 4 tools; tests with FastMCP Client |
| h | OAuth for connector | PRM/ASM discovery, DCR, auth code + PKCE, token/refresh, login+consent page; API-key fallback; tests |
| i | Docker, docs, scripts, final verification | Dockerfile, README, API.md, DECISIONS.md, MANUAL_TEST.md, seed/smoke/check scripts, full pytest run |

Milestones a–g are the hard requirement; h is next; i closes the loop. If OAuth cannot be
completed, the missing pieces are documented in `docs/DECISIONS.md`.

## Key decisions (see docs/DECISIONS.md for rationale)

1. **Database**: SQLAlchemy 2.0 async. SQLite+aiosqlite is the zero-setup default;
   `DATABASE_URL` switches to Postgres+asyncpg. All DB access sits behind repositories.
2. **OAuth**: an authorization server implemented in FastAPI (DCR + PKCE + JWT access
   tokens + rotating refresh tokens). FastMCP validates tokens with a custom
   `TokenVerifier` that accepts both our JWT and `fc_live_...` API keys. This avoids
   fighting FastMCP's provider storage interfaces and keeps one account system.
3. **LLM**: OpenRouter through `OpenAIChatCompletionsModel` (Chat Completions, not
   Responses). Tracing exporter disabled; a custom processor appends run/span metadata
   to JSONL linked by verification id. Default orchestration is `pipeline` because free
   models are unreliable at tool calling; `agents` mode uses `agent.as_tool()`.
4. **Retrieval**: Tavily SDK for search/extract, HTTP+trafilatura fallback with an
   explicit SSRF guard that re-checks every redirect hop.
5. **Billing**: provider interface; Mock provider always available; Stripe-style
   implementation active only when keys are configured.
6. **Documents**: PyMuPDF page extraction; chunked with page number and nearest heading;
   SQLite FTS5 when available, in-Python BM25-style scoring fallback. Postgres can use
   the same chunk table plus ILIKE/prefilter until a tsvector migration is added.

## Risks and mitigations

- **Free OpenRouter model slugs change and are rate-limited.** Mitigation: configurable
  slugs, ordered fallbacks, retries with jitter, low default caps, mock mode for tests,
  `scripts/check_llm.py` to probe the live slug.
- **Free-model tool calling / strict JSON is unreliable.** Mitigation: `pipeline` mode
  default, typed output + repair retry + tolerant JSON extractor, final `unverifiable`
  fallback; deterministic evidence post-validation.
- **Tavily free quota.** Mitigation: DB-backed query/URL cache, per-claim and global caps,
  429/quota errors downgrade claims instead of failing requests.
- **SSRF.** Mitigation: dedicated guard with DNS resolution and per-hop validation.
- **OAuth complexity.** Mitigation: implement the minimal server ourselves; API keys remain
  a working fallback for every client.

## Layout

```
app/main.py            FastAPI app, lifespan, CORS, routers, /health, MCP mount
app/core/              config, security, logging, errors, rate limiting
app/db/                models, session, repositories
app/api/               auth, api_keys, verifications, usage, insights, documents, preferences, billing, oauth
app/services/          verification, usage, billing, documents, preferences
app/agents/            models, llm, tools, specialists, lead, pipeline, guardrails, tracing, runner
app/retrieval/         interfaces, tavily, http, documents, ssrf, mocks
app/jobs/              queue interface, asyncio worker, cache
app/mcp/               FastMCP server, tools, auth verifier
tests/                 offline pytest suite
scripts/               seed_demo, smoke_test, check_llm, check_tavily
docs/                  PLAN, API, DECISIONS, MANUAL_TEST
```
