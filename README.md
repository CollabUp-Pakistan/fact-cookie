---
title: Fact Cookie Backend
emoji: 🍪
colorFrom: blue
colorTo: green
sdk: docker
app_port: 7860
pinned: false
---

# Fact Cookie Backend

FastAPI backend for Fact Cookie — AI claim verification with Supabase Postgres, OpenRouter LLM, Tavily search, and an MCP connector.

## Layout

- `Fact Cookie Backend/` — FastAPI app, Alembic migrations, tests, docs
- `openai-agents-python/` — local OpenAI Agents SDK dependency

## Deploy

Docker image built from the root `Dockerfile`. Required env vars (set as Space secrets):

- `DATABASE_URL` — Supabase Postgres connection string
- `SECRET_KEY` — long random string
- `BASE_URL` — public URL of this Space
- `FRONTEND_URL` — frontend origin
- `CORS_ORIGINS` — JSON array, e.g. `["*"]` for testing
- `LLM_MODE` — `mock` or `live`
- `OPENROUTER_API_KEY`, `TAVILY_API_KEY` — optional for live mode
- `BILLING_PROVIDER` — `mock` or `stripe`

Health check: `GET /health`
