# Fact Cookie Backend

FastAPI backend for Fact Cookie: verifies AI answers by extracting checkable claims, retrieving evidence from Tavily/HTTP/documents, and returning per-claim verdicts with citations.

## Setup

```powershell
cd "Fact Cookie Backend"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -e "..\openai-agents-python"
copy .env.example .env
```

## Database

Default is SQLite. For Postgres set `DATABASE_URL=postgresql+asyncpg://user:pass@host/db`.

```powershell
alembic upgrade head
```

## Run

```powershell
uvicorn app.main:app --reload
```

Health: `http://localhost:8000/health`

## Test

```powershell
pytest
```

## Docker

```powershell
docker build -t factcookie-backend .
docker run -p 8000:8000 --env-file .env factcookie-backend
```

## MCP connector and OAuth

The FastMCP connector is mounted at `/mcp`. It accepts OAuth 2.1 access tokens (audience `factcookie:mcp`) and `fc_live_...` API keys. Discovery is at `/.well-known/oauth-authorization-server` and `/.well-known/oauth-protected-resource*`; dynamic registration, PKCE, refresh, and revocation are under `/oauth/*`. See `docs/API.md` and `docs/MANUAL_TEST.md`.

## Scripts

```powershell
python scripts\seed_demo.py      # plans + demo user/API key
python scripts\smoke_test.py     # REST + MCP smoke test against BASE_URL
python scripts\check_llm.py      # OpenRouter live check (LLM_MODE=live)
python scripts\check_tavily.py   # Tavily live check (TAVILY_API_KEY set)
```

## Notes

- `LLM_MODE=mock` runs without OpenRouter keys.
- `TAVILY_API_KEY` enables live Tavily search/extract; without it the HTTP/mock providers are used.
- `BILLING_PROVIDER=mock` works locally; Stripe activates only when Stripe keys are configured.
