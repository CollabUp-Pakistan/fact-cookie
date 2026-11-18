"""OAuth 2.1 authorization server for the MCP connector."""

from __future__ import annotations

import html
import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any, Literal
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.errors import AppError, NotFoundError, UnauthorizedError
from app.core.security import (
    ACCESS_TOKEN_AUDIENCE_MCP,
    create_access_token,
    hash_opaque_token,
    new_opaque_token,
    verify_pkce,
)
from app.db.models import OAuthAuthCode, OAuthClient, OAuthToken, User
from app.db.session import get_db

router = APIRouter(tags=["oauth"])


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _issuer() -> str:
    return settings.oauth_issuer.rstrip("/")


def _resource() -> str:
    return f"{_issuer()}/mcp/"


@router.get("/.well-known/oauth-authorization-server")
async def authorization_server_metadata() -> dict[str, Any]:
    issuer = _issuer()
    return {
        "issuer": issuer,
        "authorization_endpoint": f"{issuer}/oauth/authorize",
        "token_endpoint": f"{issuer}/oauth/token",
        "registration_endpoint": f"{issuer}/oauth/register",
        "revocation_endpoint": f"{issuer}/oauth/revoke",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256", "plain"],
        "token_endpoint_auth_methods_supported": ["none", "client_secret_post"],
        "scopes_supported": settings.oauth_scopes,
    }


@router.get("/.well-known/oauth-protected-resource")
@router.get("/.well-known/oauth-protected-resource/mcp")
async def protected_resource_metadata() -> dict[str, Any]:
    return {
        "resource": _resource(),
        "authorization_servers": [_issuer()],
        "scopes_supported": settings.oauth_scopes,
        "bearer_methods_supported": ["header"],
    }


class ClientRegistration(BaseModel):
    client_name: str = Field(default="MCP Client", max_length=200)
    redirect_uris: list[str] = Field(min_length=1)
    grant_types: list[str] = Field(default_factory=lambda: ["authorization_code", "refresh_token"])
    response_types: list[str] = Field(default_factory=lambda: ["code"])
    token_endpoint_auth_method: str = "none"
    scope: str | None = None


@router.post("/oauth/register", status_code=201)
async def register_client(body: ClientRegistration, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    if not settings.oauth_allow_dynamic_registration:
        raise AppError("Dynamic client registration is disabled.", code="registration_disabled", status_code=403)
    client_id = f"mcp_{secrets.token_urlsafe(16)}"
    client_secret = secrets.token_urlsafe(32) if body.token_endpoint_auth_method != "none" else None
    client = OAuthClient(
        client_id=client_id,
        client_secret_hash=hash_opaque_token(client_secret) if client_secret else None,
        client_name=body.client_name,
        redirect_uris=body.redirect_uris,
        grant_types=body.grant_types,
        response_types=body.response_types,
        token_endpoint_auth_method=body.token_endpoint_auth_method,
        scope=body.scope or " ".join(settings.oauth_scopes),
    )
    db.add(client)
    await db.commit()
    response: dict[str, Any] = {
        "client_id": client_id,
        "client_name": client.client_name,
        "redirect_uris": client.redirect_uris,
        "grant_types": client.grant_types,
        "response_types": client.response_types,
        "token_endpoint_auth_method": client.token_endpoint_auth_method,
        "scope": client.scope,
    }
    if client_secret:
        response["client_secret"] = client_secret
        response["client_secret_expires_at"] = 0
    return response


@router.get("/oauth/authorize", response_class=HTMLResponse)
async def authorize_get(
    request: Request,
    client_id: str = Query(...),
    redirect_uri: str = Query(...),
    response_type: str = Query("code"),
    scope: str | None = Query(None),
    state: str | None = Query(None),
    code_challenge: str | None = Query(None),
    code_challenge_method: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    client = await _get_client(db, client_id)
    _validate_authorize_request(client, redirect_uri, response_type)
    next_url = f"{request.url.path}?{request.url.query}"
    login_url = f"{settings.frontend_url.rstrip('/')}/login?{urlencode({'next': next_url})}"
    return HTMLResponse(_login_page(login_url))


@router.get("/oauth/authorize/context")
async def authorize_context(
    client_id: str = Query(...),
    redirect_uri: str = Query(...),
    response_type: str = Query("code"),
    scope: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Public pre-consent info for the frontend consent screen (client name + granted scopes)."""
    client = await _get_client(db, client_id)
    _validate_authorize_request(client, redirect_uri, response_type)
    scopes = _parse_scopes(scope)
    return {"client_name": client.client_name, "scopes": scopes, "scope": " ".join(scopes)}


class ConsentDecision(BaseModel):
    """Body of the frontend consent screen: OAuth params plus the user's decision."""

    client_id: str
    redirect_uri: str
    response_type: str = "code"
    scope: str | None = None
    state: str | None = None
    code_challenge: str | None = None
    code_challenge_method: str | None = None
    resource: str | None = None
    decision: Literal["allow", "deny"]


@router.post("/oauth/authorize/consent")
async def authorize_consent(
    body: ConsentDecision,
    user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Signed-in user allows or denies the connection. Returns the URL to send the browser to."""
    client = await _get_client(db, body.client_id)
    _validate_authorize_request(client, body.redirect_uri, body.response_type)
    params: dict[str, str] = {}
    if body.state:
        params["state"] = body.state
    if body.decision == "deny":
        params["error"] = "access_denied"
        return {"redirect_url": f"{body.redirect_uri}?{urlencode(params)}"}
    code = await _create_auth_code(
        db,
        user,
        client,
        redirect_uri=body.redirect_uri,
        scope=body.scope,
        code_challenge=body.code_challenge,
        code_challenge_method=body.code_challenge_method,
    )
    params["code"] = code
    return {"redirect_url": f"{body.redirect_uri}?{urlencode(params)}"}


@router.post("/oauth/authorize")
async def authorize_post(
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    client_id: str = Form(...),
    redirect_uri: str = Form(...),
    response_type: str = Form("code"),
    scope: str | None = Form(None),
    state: str | None = Form(None),
    code_challenge: str | None = Form(None),
    code_challenge_method: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    client = await _get_client(db, client_id)
    _validate_authorize_request(client, redirect_uri, response_type)
    code = await _create_auth_code(
        db, user, client,
        redirect_uri=redirect_uri, scope=scope,
        code_challenge=code_challenge, code_challenge_method=code_challenge_method,
    )
    params = {"code": code}
    if state:
        params["state"] = state
    return RedirectResponse(f"{redirect_uri}?{urlencode(params)}", status_code=302)


async def _create_auth_code(
    db: AsyncSession,
    user: User,
    client: OAuthClient,
    *,
    redirect_uri: str,
    scope: str | None,
    code_challenge: str | None,
    code_challenge_method: str | None,
) -> str:
    """Issue a single-use authorization code for this user + client (PKCE-aware)."""
    code = new_opaque_token(32)
    db.add(
        OAuthAuthCode(
            code_hash=hash_opaque_token(code),
            client_id=client.client_id,
            user_id=str(user.id),
            redirect_uri=redirect_uri,
            scopes=_parse_scopes(scope),
            code_challenge=code_challenge,
            code_challenge_method=code_challenge_method,
            expires_at=_utcnow() + timedelta(seconds=settings.oauth_auth_code_ttl_seconds),
        )
    )
    await db.commit()
    return code


@router.post("/oauth/token")
async def token_endpoint(
    grant_type: str = Form(...),
    code: str | None = Form(None),
    redirect_uri: str | None = Form(None),
    client_id: str | None = Form(None),
    client_secret: str | None = Form(None),
    code_verifier: str | None = Form(None),
    refresh_token: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    if grant_type == "authorization_code":
        return await _exchange_code(db, code, redirect_uri, client_id, client_secret, code_verifier)
    if grant_type == "refresh_token":
        return await _refresh(db, refresh_token, client_id, client_secret)
    raise AppError("Unsupported grant_type.", code="unsupported_grant_type", status_code=400)


@router.post("/oauth/revoke")
async def revoke_endpoint(
    token: str = Form(...),
    token_type_hint: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    token_hash = hash_opaque_token(token)
    result = await db.execute(
        select(OAuthToken).where(
            (OAuthToken.access_token_hash == token_hash) | (OAuthToken.refresh_token_hash == token_hash)
        )
    )
    oauth_token = result.scalar_one_or_none()
    if oauth_token and oauth_token.revoked_at is None:
        oauth_token.revoked_at = _utcnow()
        await db.commit()
    return JSONResponse({"revoked": True})


async def _get_client(db: AsyncSession, client_id: str) -> OAuthClient:
    client = await db.get(OAuthClient, client_id)
    if not client:
        raise NotFoundError("OAuth client not found.")
    return client


def _validate_authorize_request(client: OAuthClient, redirect_uri: str, response_type: str) -> None:
    if redirect_uri not in client.redirect_uris:
        raise AppError("redirect_uri is not registered for this client.", code="invalid_redirect_uri", status_code=400)
    if response_type not in client.response_types:
        raise AppError("Unsupported response_type.", code="unsupported_response_type", status_code=400)


def _parse_scopes(scope: str | None) -> list[str]:
    if not scope:
        return list(settings.oauth_scopes)
    requested = scope.split()
    allowed = set(settings.oauth_scopes)
    return [s for s in requested if s in allowed] or list(settings.oauth_scopes)


async def _exchange_code(
    db: AsyncSession,
    code: str | None,
    redirect_uri: str | None,
    client_id: str | None,
    client_secret: str | None,
    code_verifier: str | None,
) -> JSONResponse:
    if not code or not client_id:
        raise AppError("code and client_id are required.", code="invalid_request", status_code=400)
    result = await db.execute(select(OAuthAuthCode).where(OAuthAuthCode.code_hash == hash_opaque_token(code)))
    auth_code = result.scalar_one_or_none()
    if not auth_code or auth_code.used_at is not None or _ensure_aware(auth_code.expires_at) < _utcnow():
        raise UnauthorizedError("Invalid or expired authorization code.", code="invalid_grant")
    if auth_code.client_id != client_id or auth_code.redirect_uri != redirect_uri:
        raise UnauthorizedError("Authorization code client/redirect mismatch.", code="invalid_grant")
    client = await _get_client(db, client_id)
    _validate_client_secret(client, client_secret)
    if auth_code.code_challenge:
        if not code_verifier or not verify_pkce(code_verifier, auth_code.code_challenge, auth_code.code_challenge_method or "S256"):
            raise UnauthorizedError("PKCE verification failed.", code="invalid_grant")
    auth_code.used_at = _utcnow()
    return await _issue_tokens(db, auth_code.user_id, client.client_id, auth_code.scopes)


async def _refresh(
    db: AsyncSession,
    refresh_token: str | None,
    client_id: str | None,
    client_secret: str | None,
) -> JSONResponse:
    if not refresh_token or not client_id:
        raise AppError("refresh_token and client_id are required.", code="invalid_request", status_code=400)
    result = await db.execute(select(OAuthToken).where(OAuthToken.refresh_token_hash == hash_opaque_token(refresh_token)))
    oauth_token = result.scalar_one_or_none()
    if not oauth_token or oauth_token.revoked_at is not None or oauth_token.client_id != client_id:
        raise UnauthorizedError("Invalid refresh token.", code="invalid_grant")
    if oauth_token.refresh_expires_at and _ensure_aware(oauth_token.refresh_expires_at) < _utcnow():
        raise UnauthorizedError("Refresh token expired.", code="invalid_grant")
    client = await _get_client(db, client_id)
    _validate_client_secret(client, client_secret)
    oauth_token.revoked_at = _utcnow()
    return await _issue_tokens(db, oauth_token.user_id, client.client_id, oauth_token.scopes)


def _validate_client_secret(client: OAuthClient, client_secret: str | None) -> None:
    if client.token_endpoint_auth_method == "none":
        return
    if not client_secret or not client.client_secret_hash or hash_opaque_token(client_secret) != client.client_secret_hash:
        raise UnauthorizedError("Invalid client credentials.", code="invalid_client")


async def _issue_tokens(db: AsyncSession, user_id: str, client_id: str, scopes: list[str]) -> JSONResponse:
    access_token, jti, access_expires = create_access_token(
        user_id,
        audience=ACCESS_TOKEN_AUDIENCE_MCP,
        ttl_seconds=settings.oauth_access_token_ttl_seconds,
        extra_claims={"scope": " ".join(scopes), "client_id": client_id},
    )
    refresh = new_opaque_token(48)
    db.add(
        OAuthToken(
            jti=jti,
            access_token_hash=hash_opaque_token(access_token),
            refresh_token_hash=hash_opaque_token(refresh),
            user_id=user_id,
            client_id=client_id,
            scopes=scopes,
            access_expires_at=access_expires,
            refresh_expires_at=_utcnow() + timedelta(seconds=settings.oauth_refresh_token_ttl_seconds),
        )
    )
    await db.commit()
    return JSONResponse(
        {
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": settings.oauth_access_token_ttl_seconds,
            "refresh_token": refresh,
            "scope": " ".join(scopes),
        }
    )


def _login_page(login_url: str) -> str:
    safe_url = html.escape(login_url, quote=True)
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Fact Cookie Login</title></head>
<body style="font-family:system-ui;max-width:480px;margin:80px auto;padding:0 16px">
<h1>Fact Cookie</h1>
<p>Log in to connect your account to the MCP connector.</p>
<p><a href="{safe_url}">Continue to login</a></p>
<p><small>If your frontend handles login, open this URL after signing in:
<code>{safe_url}</code></small></p>
</body></html>"""
