"""Password hashing, JWT helpers, opaque token helpers, API key helpers."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import settings
from app.core.errors import UnauthorizedError

_hasher = PasswordHasher()

ACCESS_TOKEN_AUDIENCE_REST = "factcookie:rest"
ACCESS_TOKEN_AUDIENCE_MCP = "factcookie:mcp"


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    try:
        return _hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return False


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def create_access_token(
    user_id: str,
    *,
    audience: str = ACCESS_TOKEN_AUDIENCE_REST,
    ttl_seconds: int | None = None,
    extra_claims: dict[str, Any] | None = None,
) -> tuple[str, str, datetime]:
    """Create a signed JWT. Returns (token, jti, expires_at)."""
    issued_at = now_utc()
    expires_at = issued_at + timedelta(
        seconds=ttl_seconds if ttl_seconds is not None else settings.access_token_expire_minutes * 60
    )
    jti = uuid.uuid4().hex
    payload: dict[str, Any] = {
        "sub": user_id,
        "aud": audience,
        "iss": settings.oauth_issuer if audience == ACCESS_TOKEN_AUDIENCE_MCP else settings.app_name,
        "iat": int(issued_at.timestamp()),
        "nbf": int(issued_at.timestamp()),
        "exp": int(expires_at.timestamp()),
        "jti": jti,
        "typ": "access",
    }
    if extra_claims:
        payload.update(extra_claims)
    token = jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)
    return token, jti, expires_at


def decode_access_token(token: str, *, audience: str | None = None) -> dict[str, Any]:
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.jwt_algorithm],
            audience=audience,
            options={"require": ["exp", "sub", "jti"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise UnauthorizedError("Access token has expired.", code="token_expired") from exc
    except jwt.InvalidTokenError as exc:
        raise UnauthorizedError("Invalid access token.", code="invalid_token") from exc
    if payload.get("typ") != "access":
        raise UnauthorizedError("Invalid token type.", code="invalid_token")
    return payload


def new_opaque_token(n_bytes: int = 32) -> str:
    return secrets.token_urlsafe(n_bytes)


def hash_opaque_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_api_key() -> tuple[str, str, str]:
    """Return (full_key, visible_prefix, key_hash)."""
    secret = secrets.token_urlsafe(32)
    full = f"{settings.api_key_prefix}{secret}"
    prefix = full[: len(settings.api_key_prefix) + 8]
    return full, prefix, hash_api_key(full)


def hash_api_key(full_key: str) -> str:
    return hashlib.sha256(full_key.encode("utf-8")).hexdigest()


def is_api_key(token: str) -> bool:
    return token.startswith(settings.api_key_prefix)


def safe_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def create_pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    import base64

    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def verify_pkce(verifier: str, challenge: str, method: str) -> bool:
    if method.lower() == "plain":
        return safe_equals(verifier, challenge)
    if method.upper() == "S256":
        return safe_equals(create_pkce_challenge(verifier), challenge)
    return False
