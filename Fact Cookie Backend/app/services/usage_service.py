"""Usage metering and quota checks."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import QuotaExceededError
from app.db.models import Plan, Subscription, UsageEvent, User
from app.services.plan_service import get_or_create_subscription


def _period_start(subscription: Subscription) -> datetime:
    start = subscription.current_period_start
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    return start


async def get_usage_summary(db: AsyncSession, user: User) -> dict:
    subscription = await get_or_create_subscription(db, user)
    plan = await db.get(Plan, subscription.plan_id)
    period_start = _period_start(subscription)
    result = await db.execute(
        select(func.coalesce(func.sum(UsageEvent.claim_count), 0)).where(
            UsageEvent.user_id == str(user.id), UsageEvent.period_start >= period_start
        )
    )
    used = int(result.scalar_one())
    limit = plan.monthly_claim_limit if plan else 0
    remaining = None if limit is None else max(0, limit - used)
    return {
        "plan_id": subscription.plan_id,
        "plan_name": plan.name if plan else subscription.plan_id,
        "period_start": period_start.isoformat(),
        "period_end": subscription.current_period_end.isoformat() if subscription.current_period_end else None,
        "claims_used": used,
        "claims_limit": limit,
        "claims_remaining": remaining,
        "status": subscription.status,
    }


async def check_and_record_usage(
    db: AsyncSession,
    user: User,
    claim_count: int,
    source: str,
    verification_id: str | None = None,
) -> dict:
    subscription = await get_or_create_subscription(db, user)
    plan = await db.get(Plan, subscription.plan_id)
    period_start = _period_start(subscription)
    result = await db.execute(
        select(func.coalesce(func.sum(UsageEvent.claim_count), 0)).where(
            UsageEvent.user_id == str(user.id), UsageEvent.period_start >= period_start
        )
    )
    used = int(result.scalar_one())
    limit = plan.monthly_claim_limit if plan else 0
    if limit is not None and used + claim_count > limit:
        raise QuotaExceededError(
            "Plan claim limit reached.",
            code="plan_limit_exceeded",
            details={
                "claims_used": used,
                "claims_limit": limit,
                "claims_remaining": max(0, limit - used),
                "upgrade_hint": "Upgrade your plan to verify more claims.",
            },
        )
    db.add(
        UsageEvent(
            user_id=str(user.id),
            verification_id=verification_id,
            claim_count=claim_count,
            source=source,
            period_start=period_start,
        )
    )
    await db.commit()
    return await get_usage_summary(db, user)


async def get_usage_history(db: AsyncSession, user: User, limit: int = 50, offset: int = 0) -> list[UsageEvent]:
    result = await db.execute(
        select(UsageEvent)
        .where(UsageEvent.user_id == str(user.id))
        .order_by(UsageEvent.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all())
