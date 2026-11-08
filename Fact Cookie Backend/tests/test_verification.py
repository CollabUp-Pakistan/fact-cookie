"""Tests for verification service in mock mode."""

from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def test_sync_verification_mock(client: AsyncClient):
    email = f"verify-{uuid.uuid4().hex[:8]}@example.com"
    reg = await client.post("/api/v1/auth/register", json={"email": email, "password": "password123"})
    assert reg.status_code == 201, reg.text
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    response = await client.post(
        "/api/v1/verifications",
        json={"text": "Revenue grew 20% in 2024.", "mode": "sync"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["status"] == "completed"
    assert data["claim_count"] >= 1
    assert all(c["verdict"] == "unverifiable" for c in data["claims"])


async def test_async_verification_job(client: AsyncClient):
    email = f"verify-async-{uuid.uuid4().hex[:8]}@example.com"
    reg = await client.post("/api/v1/auth/register", json={"email": email, "password": "password123"})
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    response = await client.post(
        "/api/v1/verifications",
        json={"text": "This is a longer text that should run asynchronously for testing the job lifecycle.", "mode": "async"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["mode"] == "async"
