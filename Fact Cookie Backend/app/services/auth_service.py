"""Auth service: registration, login, refresh rotation, password reset."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import ConflictError, UnauthorizedError
from app.core.security import (
    create_access_token,
    hash_opaque_token,
    hash_password,
    new_opaque_token,
    verify_password,
)
from app.db.models import PasswordResetToken, RefreshToken, User


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(select(User).where(User.email == email.lower()))
    return result.scalar_one_or_none()


async def register_user(db: AsyncSession, email: str, password: str, name: str | None) -> User:
    email = email.lower()
    if await get_user_by_email(db, email):
        raise ConflictError("An account with this email already exists.", code="email_taken")
    user = User(email=email, password_hash=hash_password(password), name=name)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def authenticate_user(db: AsyncSession, email: str, password: str) -> User:
    user = await get_user_by_email(db, email.lower())
    if not user or not verify_password(password, user.password_hash):
        raise UnauthorizedError("Invalid email or password.", code="invalid_credentials")
    if not user.is_active:
        raise UnauthorizedError("Account is disabled.", code="account_disabled")
    user.last_login_at = _utcnow()
    await db.commit()
    return user


async def issue_tokens(db: AsyncSession, user: User, user_agent: str | None = None) -> tuple[str, str, int]:
    access_token, _, _ = create_access_token(str(user.id), audience="factcookie:rest")
    refresh_token = new_opaque_token(48)
    db.add(
        RefreshToken(
            user_id=str(user.id),
            token_hash=hash_opaque_token(refresh_token),
            expires_at=_utcnow() + timedelta(days=settings.refresh_token_expire_days),
            user_agent=user_agent[:300] if user_agent else None,
        )
    )
    await db.commit()
    return access_token, refresh_token, settings.access_token_expire_minutes * 60


async def refresh_tokens(db: AsyncSession, refresh_token: str, user_agent: str | None = None) -> tuple[str, str, int]:
    token_hash = hash_opaque_token(refresh_token)
    result = await db.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
    stored = result.scalar_one_or_none()
    if not stored or stored.revoked_at is not None or _ensure_aware(stored.expires_at) < _utcnow():
        raise UnauthorizedError("Invalid or expired refresh token.", code="invalid_refresh_token")
    user = await db.get(User, stored.user_id)
    if not user or not user.is_active:
        raise UnauthorizedError("User not found or inactive.")

    stored.revoked_at = _utcnow()
    stored.rotated_from = stored.token_hash
    access_token, _, _ = create_access_token(str(user.id), audience="factcookie:rest")
    new_refresh = new_opaque_token(48)
    db.add(
        RefreshToken(
            user_id=str(user.id),
            token_hash=hash_opaque_token(new_refresh),
            expires_at=_utcnow() + timedelta(days=settings.refresh_token_expire_days),
            user_agent=user_agent[:300] if user_agent else None,
        )
    )
    await db.commit()
    return access_token, new_refresh, settings.access_token_expire_minutes * 60


async def revoke_refresh_token(db: AsyncSession, refresh_token: str) -> None:
    token_hash = hash_opaque_token(refresh_token)
    result = await db.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
    stored = result.scalar_one_or_none()
    if stored and stored.revoked_at is None:
        stored.revoked_at = _utcnow()
        await db.commit()


async def request_password_reset(db: AsyncSession, email: str) -> str | None:
    user = await get_user_by_email(db, email.lower())
    if not user:
        return None
    token = new_opaque_token(32)
    db.add(
        PasswordResetToken(
            user_id=str(user.id),
            token_hash=hash_opaque_token(token),
            expires_at=_utcnow() + timedelta(hours=1),
        )
    )
    await db.commit()
    return token


async def confirm_password_reset(db: AsyncSession, token: str, password: str) -> None:
    token_hash = hash_opaque_token(token)
    result = await db.execute(select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash))
    stored = result.scalar_one_or_none()
    if not stored or stored.used_at is not None or _ensure_aware(stored.expires_at) < _utcnow():
        raise UnauthorizedError("Invalid or expired reset token.", code="invalid_reset_token")
    user = await db.get(User, stored.user_id)
    if not user:
        raise UnauthorizedError("User not found.")
    user.password_hash = hash_password(password)
    stored.used_at = _utcnow()
    await db.commit()
