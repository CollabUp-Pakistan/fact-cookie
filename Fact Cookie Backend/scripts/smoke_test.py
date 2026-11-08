"""Smoke test the running Fact Cookie API."""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx


BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000")


async def main() -> int:
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
        health = await client.get("/health")
        health.raise_for_status()
        print("health:", health.json())

        email = f"smoke-{uuid.uuid4().hex[:8]}@example.com"
        register = await client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "password123", "name": "Smoke"},
        )
        register.raise_for_status()
        tokens = register.json()
        headers = {"Authorization": f"Bearer {tokens['access_token']}"}
        print("registered:", email)

        api_key = await client.post("/api/v1/api-keys", json={"name": "smoke"}, headers=headers)
        api_key.raise_for_status()
        key = api_key.json()["key"]
        print("api key created:", api_key.json()["prefix"] + "...")

        verification = await client.post(
            "/api/v1/verifications",
            json={"text": "The sky is blue. Water boils at 100C.", "mode": "sync"},
            headers=headers,
        )
        verification.raise_for_status()
        body = verification.json()
        print("verification:", body["id"], body["status"], "claims:", body["claim_count"])

        usage = await client.get("/api/v1/usage/current", headers=headers)
        usage.raise_for_status()
        print("usage:", usage.json())

        mcp_health = await client.post(
            "/mcp/",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
            headers={"Authorization": f"Bearer {key}", "Accept": "application/json, text/event-stream"},
        )
        print("mcp status:", mcp_health.status_code)
        if mcp_health.status_code >= 500:
            print(mcp_health.text[:500])
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
