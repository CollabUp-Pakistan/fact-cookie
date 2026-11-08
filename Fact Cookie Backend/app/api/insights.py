"""Insights routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.models import Claim, User, Verification
from app.db.session import get_db

router = APIRouter(prefix="/insights", tags=["insights"])


@router.get("/top-claims")
async def top_claims(user: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)], limit: int = 10):
    result = await db.execute(
        select(Claim.text, func.count(Claim.id).label("count"))
        .where(Claim.user_id == str(user.id))
        .group_by(Claim.text)
        .order_by(func.count(Claim.id).desc())
        .limit(limit)
    )
    return [{"claim": row[0], "count": row[1]} for row in result.all()]


@router.get("/top-domains")
async def top_domains(user: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)], limit: int = 10):
    result = await db.execute(
        select(Claim.source_url, func.count(Claim.id).label("count"))
        .where(Claim.user_id == str(user.id), Claim.source_url.is_not(None))
        .group_by(Claim.source_url)
        .order_by(func.count(Claim.id).desc())
        .limit(limit)
    )
    return [{"source_url": row[0], "count": row[1]} for row in result.all()]


@router.get("/verdict-breakdown")
async def verdict_breakdown(user: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    result = await db.execute(select(Claim.verdict, func.count(Claim.id)).where(Claim.user_id == str(user.id)).group_by(Claim.verdict))
    return {row[0]: row[1] for row in result.all()}


@router.get("/trends")
async def trends(user: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)], days: int = 30):
    result = await db.execute(
        select(func.date(Verification.created_at).label("day"), func.count(Verification.id))
        .where(Verification.user_id == str(user.id))
        .group_by(func.date(Verification.created_at))
        .order_by(func.date(Verification.created_at))
        .limit(days)
    )
    return [{"date": str(row[0]), "count": row[1]} for row in result.all()]
