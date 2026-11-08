# Manual test guide

## Local mock mode (no external keys)

1. `copy .env.example .env`
2. `alembic upgrade head`
3. `uvicorn app.main:app --reload`
4. `pytest` in another terminal.

## REST smoke

```powershell
python scripts\smoke_test.py
```

Expected: health OK, user registered, API key created, verification completes in mock mode, usage endpoint returns quota, MCP endpoint responds.

## MCP connector

1. Start the API.
2. Register a user and create an API key, or complete OAuth.
3. In an MCP client, connect to `http://localhost:8000/mcp`.
4. For API-key fallback, send `Authorization: Bearer fc_live_...`.
5. Call `get_usage`, then `verify_text` with a short answer containing a number/date.

## OAuth flow

1. `POST /oauth/register` with `redirect_uris`.
2. Open `GET /oauth/authorize?client_id=...&redirect_uri=...&response_type=code&code_challenge=...&code_challenge_method=S256`.
3. Log in on the frontend, then `POST /oauth/authorize` with the same parameters plus the user's REST JWT.
4. Exchange the returned code at `POST /oauth/token` with `code_verifier`.
5. Use the MCP-audience access token at `/mcp`; refresh via `grant_type=refresh_token`.

## Live checks

```powershell
$env:LLM_MODE="live"; $env:OPENROUTER_API_KEY="..."; python scripts\check_llm.py
$env:TAVILY_API_KEY="..."; python scripts\check_tavily.py
```

## Demo data

```powershell
python scripts\seed_demo.py
```

Creates/ensures plans and a demo user, then prints a demo API key once.
