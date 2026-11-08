"""Tests for document upload and page-aware chunks."""

from __future__ import annotations

import io
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def test_upload_txt_and_list(client: AsyncClient):
    email = f"docs-{uuid.uuid4().hex[:8]}@example.com"
    reg = await client.post("/api/v1/auth/register", json={"email": email, "password": "password123"})
    assert reg.status_code == 201, reg.text
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    content = b"# Report\n\nRevenue grew 20% in 2024.\n\n# Risks\n\nSupply chain delays remain."
    upload = await client.post(
        "/api/v1/documents",
        files={"file": ("report.txt", io.BytesIO(content), "text/plain")},
        headers=headers,
    )
    assert upload.status_code == 201, upload.text
    doc = upload.json()
    assert doc["status"] == "ready"

    listing = await client.get("/api/v1/documents", headers=headers)
    assert listing.status_code == 200
    assert any(d["id"] == doc["id"] for d in listing.json())

    delete = await client.delete(f"/api/v1/documents/{doc['id']}", headers=headers)
    assert delete.status_code == 204
