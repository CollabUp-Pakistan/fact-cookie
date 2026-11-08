"""Tests for user preferences."""

from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def test_preferences_roundtrip(client: AsyncClient):
    email = f"prefs-{uuid.uuid4().hex[:8]}@example.com"
    reg = await client.post("/api/v1/auth/register", json={"email": email, "password": "password123"})
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    body = {
        "trusted_domains": ["example.com"],
        "blocked_domains": ["spam.example"],
        "strictness": "strict",
        "recency_days": 30,
        "citation_style": "apa",
        "language": "en",
    }
    put = await client.put("/api/v1/preferences", json=body, headers=headers)
    assert put.status_code == 200, put.text
    assert put.json()["strictness"] == "strict"

    get = await client.get("/api/v1/preferences", headers=headers)
    assert get.status_code == 200
    assert get.json()["trusted_domains"] == ["example.com"]
