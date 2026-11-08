"""Tests for plans, usage, and billing mock."""

from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.services import plan_service
from app.db.session import session_factory


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def _register(client: AsyncClient) -> dict:
    email = f"billing-{uuid.uuid4().hex[:8]}@example.com"
    reg = await client.post("/api/v1/auth/register", json={"email": email, "password": "password123"})
    assert reg.status_code == 201, reg.text
    return reg.json()


async def test_plans_seeded_and_subscription(client: AsyncClient):
    async with session_factory() as db:
        await plan_service.seed_plans(db)

    tokens = await _register(client)
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    plans = await client.get("/api/v1/billing/plans")
    assert plans.status_code == 200
    assert any(p["id"] == "free" for p in plans.json())

    sub = await client.get("/api/v1/billing/subscription", headers=headers)
    assert sub.status_code == 200, sub.text
    assert sub.json()["subscription"]["plan_id"] == "free"


async def test_usage_current_and_history(client: AsyncClient):
    tokens = await _register(client)
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    current = await client.get("/api/v1/usage/current", headers=headers)
    assert current.status_code == 200, current.text
    assert current.json()["claims_limit"] == 50

    history = await client.get("/api/v1/usage/history", headers=headers)
    assert history.status_code == 200


async def test_mock_checkout_and_webhook(client: AsyncClient):
    tokens = await _register(client)
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    checkout = await client.post("/api/v1/billing/checkout", json={"plan_id": "pro"}, headers=headers)
    assert checkout.status_code == 200, checkout.text
    assert checkout.json()["provider"] == "mock"

    webhook = await client.post(
        "/api/v1/billing/webhook",
        json={"id": "evt_test", "type": "checkout.session.completed", "data": {"object": {"metadata": {"user_id": "", "plan_id": "pro"}}}},
    )
    assert webhook.status_code == 200, webhook.text
