"""Shared pytest fixtures."""

from __future__ import annotations

import os

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test_factcookie.db"
os.environ["LLM_MODE"] = "mock"
os.environ["ORCHESTRATION_MODE"] = "pipeline"
os.environ["TAVILY_API_KEY"] = ""
os.environ["OPENROUTER_API_KEY"] = ""
os.environ["BILLING_PROVIDER"] = "mock"
os.environ["STRIPE_SECRET_KEY"] = ""
os.environ["STRIPE_WEBHOOK_SECRET"] = ""
os.environ["BASE_URL"] = "http://localhost:8000"
os.environ["FRONTEND_URL"] = "http://localhost:3000"
os.environ["RATE_LIMIT_REGISTER"] = "10000"
os.environ["RATE_LIMIT_LOGIN"] = "10000"
os.environ["RATE_LIMIT_VERIFICATION"] = "10000"

import pytest

from app.core.rate_limit import rate_limiter
from app.db.base import Base
from app.db.session import engine, session_factory
from app.services import plan_service


@pytest.fixture(autouse=True)
async def _prepare_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with session_factory() as db:
        await plan_service.seed_plans(db)
    await rate_limiter.reset()
    yield
    await engine.dispose()
