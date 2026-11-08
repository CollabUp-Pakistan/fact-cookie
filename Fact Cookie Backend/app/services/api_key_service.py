"""API key service."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.core.security import generate_api_key
from app.db.models import ApiKey


async def create_api_key(db: AsyncSession, user_id: str, name: str) -> tuple[ApiKey, str]:
    full_key, prefix, key_hash = generate_api_key()
    api_key = ApiKey(user_id=user_id, name=name, prefix=prefix, key_hash=key_hash)
    db.add(api_key)
    await db.commit()
    await db.refresh(api_key)
    return api_key, full_key


async def list_api_keys(db: AsyncSession, user_id: str) -> list[ApiKey]:
    result = await db.execute(select(ApiKey).where(ApiKey.user_id == user_id).order_by(ApiKey.created_at.desc()))
    return list(result.scalars().all())


async def revoke_api_key(db: AsyncSession, user_id: str, key_id: str) -> ApiKey:
    result = await db.execute(select(ApiKey).where(ApiKey.id == key_id, ApiKey.user_id == user_id))
    api_key = result.scalar_one_or_none()
    if not api_key:
        raise NotFoundError("API key not found.")
    if api_key.revoked_at is None:
        from datetime import datetime, timezone

        api_key.revoked_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(api_key)
    return api_key
