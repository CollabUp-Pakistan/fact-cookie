"""Offline tests for auth and API keys."""

from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def test_register_login_me_and_api_key(client: AsyncClient):
    email = f"test-{uuid.uuid4().hex[:8]}@example.com"
    password = "password123"

    reg = await client.post("/api/v1/auth/register", json={"email": email, "password": password, "name": "Test"})
    assert reg.status_code == 201, reg.text
    tokens = reg.json()
    assert tokens["access_token"]
    assert tokens["refresh_token"]

    me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"})
    assert me.status_code == 200
    assert me.json()["email"] == email

    key = await client.post(
        "/api/v1/api-keys",
        json={"name": "test-key"},
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert key.status_code == 201, key.text
    key_data = key.json()
    assert key_data["key"].startswith("fc_live_")

    me_with_key = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {key_data['key']}"})
    assert me_with_key.status_code == 200

    delete = await client.delete(
        f"/api/v1/api-keys/{key_data['id']}",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert delete.status_code == 200

    revoked = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {key_data['key']}"})
    assert revoked.status_code == 401


async def test_login_and_refresh(client: AsyncClient):
    email = f"refresh-{uuid.uuid4().hex[:8]}@example.com"
    password = "password123"
    await client.post("/api/v1/auth/register", json={"email": email, "password": password})

    login = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200, login.text
    tokens = login.json()

    refreshed = await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert refreshed.status_code == 200, refreshed.text
    new_tokens = refreshed.json()
    assert new_tokens["access_token"] != tokens["access_token"]
