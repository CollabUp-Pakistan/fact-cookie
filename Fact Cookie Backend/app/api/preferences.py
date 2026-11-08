"""User preferences routes."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.models import Preference, User
from app.db.session import get_db

router = APIRouter(prefix="/preferences", tags=["preferences"])


class PreferencesIn(BaseModel):
    trusted_domains: list[str] = Field(default_factory=list)
    blocked_domains: list[str] = Field(default_factory=list)
    strictness: Literal["lenient", "standard", "strict"] = "standard"
    recency_days: int | None = Field(default=None, ge=1, le=3650)
    citation_style: str = "apa"
    language: str = "en"


class PreferencesOut(PreferencesIn):
    pass


async def _get_or_create(db: AsyncSession, user: User) -> Preference:
    result = await db.execute(select(Preference).where(Preference.user_id == str(user.id)))
    pref = result.scalar_one_or_none()
    if not pref:
        pref = Preference(user_id=str(user.id))
        db.add(pref)
        await db.commit()
        await db.refresh(pref)
    return pref


@router.get("", response_model=PreferencesOut)
async def get_preferences(user: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)]) -> PreferencesOut:
    pref = await _get_or_create(db, user)
    return PreferencesOut(
        trusted_domains=pref.trusted_domains,
        blocked_domains=pref.blocked_domains,
        strictness=pref.strictness,
        recency_days=pref.recency_days,
        citation_style=pref.citation_style,
        language=pref.language,
    )


@router.put("", response_model=PreferencesOut)
async def put_preferences(body: PreferencesIn, user: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)]) -> PreferencesOut:
    pref = await _get_or_create(db, user)
    pref.trusted_domains = body.trusted_domains
    pref.blocked_domains = body.blocked_domains
    pref.strictness = body.strictness
    pref.recency_days = body.recency_days
    pref.citation_style = body.citation_style
    pref.language = body.language
    await db.commit()
    await db.refresh(pref)
    return PreferencesOut(
        trusted_domains=pref.trusted_domains,
        blocked_domains=pref.blocked_domains,
        strictness=pref.strictness,
        recency_days=pref.recency_days,
        citation_style=pref.citation_style,
        language=pref.language,
    )
