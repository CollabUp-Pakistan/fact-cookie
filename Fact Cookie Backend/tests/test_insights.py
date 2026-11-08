"""Tests for insights endpoints."""

from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def test_insights_endpoints(client: AsyncClient):
    email = f"insights-{uuid.uuid4().hex[:8]}@example.com"
    reg = await client.post("/api/v1/auth/register", json={"email": email, "password": "password123"})
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    await client.post("/api/v1/verifications", json={"text": "Revenue grew 20% in 2024.", "mode": "sync"}, headers=headers)

    for endpoint in ["top-claims", "top-domains", "verdict-breakdown", "trends"]:
        response = await client.get(f"/api/v1/insights/{endpoint}", headers=headers)
        assert response.status_code == 200, response.text
