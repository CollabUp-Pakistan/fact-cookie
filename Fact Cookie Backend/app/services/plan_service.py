"""Plan seeding and subscription helpers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Plan, Subscription, User


DEFAULT_PLANS = [
    {"id": "free", "name": "Free", "monthly_claim_limit": 50, "price_cents": 0, "sort_order": 0},
    {"id": "pro", "name": "Pro", "monthly_claim_limit": 1000, "price_cents": 2000, "sort_order": 1},
    {"id": "team", "name": "Team", "monthly_claim_limit": 5000, "price_cents": 8000, "sort_order": 2},
    {"id": "enterprise", "name": "Enterprise", "monthly_claim_limit": None, "price_cents": 0, "sort_order": 3},
]


async def seed_plans(db: AsyncSession) -> None:
    for plan_data in DEFAULT_PLANS:
        result = await db.execute(select(Plan).where(Plan.id == plan_data["id"]))
        plan = result.scalar_one_or_none()
        if plan is None:
            db.add(Plan(**plan_data, features={}))
        else:
            plan.name = plan_data["name"]
            plan.monthly_claim_limit = plan_data["monthly_claim_limit"]
            plan.price_cents = plan_data["price_cents"]
            plan.sort_order = plan_data["sort_order"]
            plan.is_active = True
    await db.commit()


async def get_or_create_subscription(db: AsyncSession, user: User) -> Subscription:
    result = await db.execute(select(Subscription).where(Subscription.user_id == str(user.id)))
    subscription = result.scalar_one_or_none()
    if subscription:
        return subscription
    subscription = Subscription(
        user_id=str(user.id),
        plan_id="free",
        status="active",
        provider="mock",
        current_period_start=datetime.now(timezone.utc),
        current_period_end=datetime.now(timezone.utc) + timedelta(days=30),
    )
    db.add(subscription)
    await db.commit()
    await db.refresh(subscription)
    return subscription


async def get_plan(db: AsyncSession, plan_id: str) -> Plan | None:
    result = await db.execute(select(Plan).where(Plan.id == plan_id))
    return result.scalar_one_or_none()
