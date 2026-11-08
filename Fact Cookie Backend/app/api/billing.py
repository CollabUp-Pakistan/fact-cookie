"""Billing routes: plans, subscription, checkout, portal, webhook."""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.errors import AppError, NotFoundError
from app.db.models import BillingEvent, Plan, Subscription, User
from app.db.session import get_db
from app.services import plan_service, usage_service
from app.services.billing_service import get_billing_provider

router = APIRouter(prefix="/billing", tags=["billing"])


@router.get("/plans")
async def list_plans(db: Annotated[AsyncSession, Depends(get_db)]) -> list[dict[str, Any]]:
    result = await db.execute(select(Plan).where(Plan.is_active.is_(True)).order_by(Plan.sort_order))
    plans = result.scalars().all()
    return [
        {
            "id": p.id,
            "name": p.name,
            "monthly_claim_limit": p.monthly_claim_limit,
            "price_cents": p.price_cents,
            "currency": p.currency,
            "features": p.features,
        }
        for p in plans
    ]


@router.get("/subscription")
async def get_subscription(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    subscription = await plan_service.get_or_create_subscription(db, user)
    plan = await db.get(Plan, subscription.plan_id)
    usage = await usage_service.get_usage_summary(db, user)
    return {
        "subscription": {
            "id": subscription.id,
            "plan_id": subscription.plan_id,
            "plan_name": plan.name if plan else subscription.plan_id,
            "status": subscription.status,
            "provider": subscription.provider,
            "current_period_start": subscription.current_period_start.isoformat(),
            "current_period_end": subscription.current_period_end.isoformat() if subscription.current_period_end else None,
            "cancel_at_period_end": subscription.cancel_at_period_end,
        },
        "usage": usage,
    }


@router.post("/checkout")
async def create_checkout(
    body: dict[str, str],
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, str]:
    plan_id = body.get("plan_id")
    if not plan_id:
        raise AppError("plan_id is required.", code="validation_error", status_code=422)
    plan = await plan_service.get_plan(db, plan_id)
    if not plan or not plan.is_active:
        raise NotFoundError("Plan not found.")
    provider = get_billing_provider()
    session = await provider.create_checkout_session(str(user.id), plan_id, user.email)
    return {"id": session.id, "url": session.url, "provider": session.provider}


@router.post("/portal")
async def create_portal(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, str]:
    subscription = await plan_service.get_or_create_subscription(db, user)
    provider = get_billing_provider()
    session = await provider.create_portal_session(str(user.id), subscription.provider_customer_id)
    return {"id": session.id, "url": session.url, "provider": session.provider}


@router.post("/webhook")
async def billing_webhook(request: Request, db: Annotated[AsyncSession, Depends(get_db)]) -> dict[str, Any]:
    payload = await request.body()
    signature = request.headers.get("stripe-signature")
    provider = get_billing_provider()

    if settings.stripe_enabled:
        event = _verify_stripe_signature(payload, signature)
        provider_event_id = event.get("id", "")
        event_type = event.get("type", "")
    else:
        try:
            event = json.loads(payload.decode("utf-8"))
        except Exception as exc:
            raise AppError("Invalid webhook payload.", code="invalid_payload", status_code=400) from exc
        provider_event_id = event.get("id", hashlib.sha256(payload).hexdigest())
        event_type = event.get("type", "mock")

    existing = await db.execute(
        select(BillingEvent).where(BillingEvent.provider == provider.name, BillingEvent.provider_event_id == provider_event_id)
    )
    billing_event = existing.scalar_one_or_none()
    if billing_event and billing_event.status == "processed":
        return {"received": True, "duplicate": True}
    if not billing_event:
        billing_event = BillingEvent(
            provider=provider.name,
            provider_event_id=provider_event_id,
            event_type=event_type,
            payload_json=event,
        )
        db.add(billing_event)
    try:
        await _apply_billing_event(db, event, provider.name)
        billing_event.status = "processed"
        from datetime import datetime, timezone

        billing_event.processed_at = datetime.now(timezone.utc)
        await db.commit()
    except Exception as exc:
        billing_event.status = "failed"
        billing_event.error = str(exc)
        await db.commit()
        raise
    return {"received": True}


def _verify_stripe_signature(payload: bytes, signature: str | None) -> dict[str, Any]:
    if not signature:
        raise AppError("Missing Stripe signature.", code="invalid_signature", status_code=400)
    # Minimal Stripe signature verification: t=timestamp,v1=signature
    parts = dict(part.split("=", 1) for part in signature.split(",") if "=" in part)
    timestamp = parts.get("t")
    signatures = [v for k, v in parts.items() if k == "v1"]
    if not timestamp or not signatures:
        raise AppError("Invalid Stripe signature.", code="invalid_signature", status_code=400)
    signed_payload = f"{timestamp}.{payload.decode('utf-8')}".encode("utf-8")
    expected = hmac.new(settings.stripe_webhook_secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    if not any(hmac.compare_digest(expected, sig) for sig in signatures):
        raise AppError("Invalid Stripe signature.", code="invalid_signature", status_code=400)
    return json.loads(payload.decode("utf-8"))


async def _apply_billing_event(db: AsyncSession, event: dict[str, Any], provider: str) -> None:
    event_type = event.get("type", "")
    data = event.get("data", {}).get("object", {})
    metadata = data.get("metadata", {})
    user_id = metadata.get("user_id") or data.get("client_reference_id")
    plan_id = metadata.get("plan_id")
    if not user_id:
        return
    user = await db.get(User, user_id)
    if not user:
        return
    subscription = await plan_service.get_or_create_subscription(db, user)
    subscription.provider = provider
    if event_type in {"checkout.session.completed", "customer.subscription.created", "customer.subscription.updated"}:
        if plan_id:
            subscription.plan_id = plan_id
        subscription.status = "active"
        subscription.provider_customer_id = data.get("customer") or subscription.provider_customer_id
        subscription.provider_subscription_id = data.get("subscription") or data.get("id") or subscription.provider_subscription_id
        if data.get("current_period_start"):
            from datetime import datetime, timezone

            subscription.current_period_start = datetime.fromtimestamp(data["current_period_start"], tz=timezone.utc)
        if data.get("current_period_end"):
            from datetime import datetime, timezone

            subscription.current_period_end = datetime.fromtimestamp(data["current_period_end"], tz=timezone.utc)
    elif event_type in {"customer.subscription.deleted", "checkout.session.expired"}:
        subscription.status = "canceled"
        subscription.plan_id = "free"
    await db.commit()
