"""Usage routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.models import User
from app.db.session import get_db
from app.services import usage_service

router = APIRouter(prefix="/usage", tags=["usage"])


@router.get("/current")
async def current_usage(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    return await usage_service.get_usage_summary(db, user)


@router.get("/history")
async def usage_history(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[dict]:
    events = await usage_service.get_usage_history(db, user, limit=limit, offset=offset)
    return [
        {
            "id": e.id,
            "verification_id": e.verification_id,
            "claim_count": e.claim_count,
            "source": e.source,
            "created_at": e.created_at.isoformat(),
            "period_start": e.period_start.isoformat(),
        }
        for e in events
    ]
