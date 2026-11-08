"""Shared API dependencies: auth, current user, rate limits."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import UnauthorizedError
from app.core.rate_limit import rate_limiter
from app.core.security import (
    ACCESS_TOKEN_AUDIENCE_MCP,
    ACCESS_TOKEN_AUDIENCE_REST,
    decode_access_token,
    hash_api_key,
    is_api_key,
)
from app.db.models import ApiKey, User
from app.db.session import get_db


async def get_current_user(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise UnauthorizedError("Missing bearer token.")
    token = authorization.split(" ", 1)[1].strip()
    if is_api_key(token):
        result = await db.execute(select(ApiKey).where(ApiKey.key_hash == hash_api_key(token)))
        api_key = result.scalar_one_or_none()
        if not api_key or api_key.revoked_at is not None:
            raise UnauthorizedError("Invalid API key.", code="invalid_api_key")
        user = await db.get(User, api_key.user_id)
        if not user or not user.is_active:
            raise UnauthorizedError("User not found or inactive.", code="invalid_api_key")
        api_key.last_used_at = datetime.now(timezone.utc)
        await db.commit()
        request.state.auth_method = "api_key"
        request.state.api_key_id = api_key.id
        return user

    audience = ACCESS_TOKEN_AUDIENCE_MCP if request.url.path.startswith("/mcp") else ACCESS_TOKEN_AUDIENCE_REST
    payload = decode_access_token(token, audience=audience)
    user = await db.get(User, payload["sub"])
    if not user or not user.is_active:
        raise UnauthorizedError("User not found or inactive.")
    request.state.auth_method = "jwt"
    request.state.token_jti = payload.get("jti")
    return user


async def require_login_rate_limit(request: Request) -> None:
    client_ip = request.client.host if request.client else "unknown"
    await rate_limiter.check(
        f"login:{client_ip}",
        settings.rate_limit_login,
        settings.rate_limit_login_window,
    )


async def require_register_rate_limit(request: Request) -> None:
    client_ip = request.client.host if request.client else "unknown"
    await rate_limiter.check(
        f"register:{client_ip}",
        settings.rate_limit_register,
        settings.rate_limit_register_window,
    )
