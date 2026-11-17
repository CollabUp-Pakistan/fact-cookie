"""Tests for the OAuth 2.1 authorization server used by the MCP connector."""

from __future__ import annotations

import uuid
from urllib.parse import parse_qs, urlparse

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.security import create_pkce_challenge
from app.main import app
from app.mcp.server import FactCookieTokenVerifier


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", follow_redirects=False) as c:
        yield c


async def _register_user(client: AsyncClient) -> dict:
    email = f"oauth-{uuid.uuid4().hex[:8]}@example.com"
    reg = await client.post("/api/v1/auth/register", json={"email": email, "password": "password123"})
    assert reg.status_code == 201, reg.text
    return reg.json()


async def test_oauth_discovery_and_dynamic_registration(client: AsyncClient):
    as_meta = await client.get("/.well-known/oauth-authorization-server")
    assert as_meta.status_code == 200, as_meta.text
    assert as_meta.json()["issuer"] == "http://localhost:8000"
    assert as_meta.json()["registration_endpoint"].endswith("/oauth/register")

    pr_meta = await client.get("/.well-known/oauth-protected-resource/mcp")
    assert pr_meta.status_code == 200, pr_meta.text
    assert pr_meta.json()["resource"].endswith("/mcp")

    reg = await client.post(
        "/oauth/register",
        json={
            "client_name": "Test MCP Client",
            "redirect_uris": ["http://localhost:3000/callback"],
            "token_endpoint_auth_method": "none",
        },
    )
    assert reg.status_code == 201, reg.text
    assert reg.json()["client_id"].startswith("mcp_")


async def test_authorize_context(client: AsyncClient):
    reg = await client.post(
        "/oauth/register",
        json={
            "client_name": "Context Client",
            "redirect_uris": ["http://localhost:3000/callback"],
            "token_endpoint_auth_method": "none",
        },
    )
    client_id = reg.json()["client_id"]

    ctx = await client.get(
        "/oauth/authorize/context",
        params={
            "client_id": client_id,
            "redirect_uri": "http://localhost:3000/callback",
            "response_type": "code",
            "scope": "factcookie:verify",
        },
    )
    assert ctx.status_code == 200, ctx.text
    body = ctx.json()
    assert body["client_name"] == "Context Client"
    assert body["scopes"] == ["factcookie:verify"]

    # Unknown client and unregistered redirect must fail.
    missing = await client.get(
        "/oauth/authorize/context",
        params={"client_id": "mcp_does_not_exist", "redirect_uri": "http://localhost:3000/callback"},
    )
    assert missing.status_code == 404, missing.text
    bad_redirect = await client.get(
        "/oauth/authorize/context",
        params={"client_id": client_id, "redirect_uri": "https://evil.example/callback"},
    )
    assert bad_redirect.status_code == 400, bad_redirect.text


async def test_consent_allow_and_deny(client: AsyncClient):
    tokens = await _register_user(client)
    user_headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    client_reg = await client.post(
        "/oauth/register",
        json={
            "client_name": "Consent Client",
            "redirect_uris": ["http://localhost:3000/callback"],
            "token_endpoint_auth_method": "none",
        },
    )
    client_id = client_reg.json()["client_id"]
    base = {"client_id": client_id, "redirect_uri": "http://localhost:3000/callback", "response_type": "code"}

    deny = await client.post(
        "/oauth/authorize/consent",
        json={**base, "state": "s-deny", "decision": "deny"},
        headers=user_headers,
    )
    assert deny.status_code == 200, deny.text
    deny_url = deny.json()["redirect_url"]
    assert deny_url.startswith("http://localhost:3000/callback?")
    assert parse_qs(urlparse(deny_url).query)["error"] == ["access_denied"]
    assert parse_qs(urlparse(deny_url).query)["state"] == ["s-deny"]

    verifier = "consent-verifier-456"
    challenge = create_pkce_challenge(verifier)
    allow = await client.post(
        "/oauth/authorize/consent",
        json={
            **base,
            "state": "s-allow",
            "scope": "factcookie:verify",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "decision": "allow",
        },
        headers=user_headers,
    )
    assert allow.status_code == 200, allow.text
    allow_url = allow.json()["redirect_url"]
    query = parse_qs(urlparse(allow_url).query)
    assert query["state"] == ["s-allow"]
    code = query["code"][0]

    # The consent-issued code must exchange for real MCP tokens.
    token = await client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": "http://localhost:3000/callback",
            "client_id": client_id,
            "code_verifier": verifier,
        },
    )
    assert token.status_code == 200, token.text
    assert token.json()["token_type"] == "Bearer"

    # Without login the consent endpoint must reject.
    anon = await client.post("/oauth/authorize/consent", json={**base, "decision": "allow"})
    assert anon.status_code == 401, anon.text


async def test_authorization_code_pkce_refresh_and_revoke(client: AsyncClient):
    tokens = await _register_user(client)
    user_headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    client_reg = await client.post(
        "/oauth/register",
        json={
            "client_name": "PKCE Client",
            "redirect_uris": ["http://localhost:3000/callback"],
            "token_endpoint_auth_method": "none",
        },
    )
    assert client_reg.status_code == 201, client_reg.text
    client_id = client_reg.json()["client_id"]

    verifier = "test-verifier-123"
    challenge = create_pkce_challenge(verifier)
    auth = await client.post(
        "/oauth/authorize",
        data={
            "client_id": client_id,
            "redirect_uri": "http://localhost:3000/callback",
            "response_type": "code",
            "scope": "factcookie:verify",
            "state": "state-123",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        },
        headers=user_headers,
    )
    assert auth.status_code == 302, auth.text
    location = auth.headers["location"]
    assert location.startswith("http://localhost:3000/callback?")
    query = parse_qs(urlparse(location).query)
    assert query["state"] == ["state-123"]
    code = query["code"][0]

    token = await client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": "http://localhost:3000/callback",
            "client_id": client_id,
            "code_verifier": verifier,
        },
    )
    assert token.status_code == 200, token.text
    token_data = token.json()
    assert token_data["token_type"] == "Bearer"
    assert token_data["access_token"]
    assert token_data["refresh_token"]

    verifier_instance = FactCookieTokenVerifier()
    access = await verifier_instance.verify_token(token_data["access_token"])
    assert access is not None
    assert access.claims["user_id"]

    refresh = await client.post(
        "/oauth/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": token_data["refresh_token"],
            "client_id": client_id,
        },
    )
    assert refresh.status_code == 200, refresh.text
    new_tokens = refresh.json()
    assert new_tokens["access_token"] != token_data["access_token"]

    revoke = await client.post("/oauth/revoke", data={"token": new_tokens["refresh_token"]})
    assert revoke.status_code == 200, revoke.text

    # Refresh token is now revoked; access token issued from the same grant is also revoked.
    access_after_revoke = await verifier_instance.verify_token(new_tokens["access_token"])
    assert access_after_revoke is None
