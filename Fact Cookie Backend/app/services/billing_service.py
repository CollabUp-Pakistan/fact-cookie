"""Billing provider interface and implementations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from app.core.config import settings
from app.core.errors import AppError


@dataclass
class CheckoutSession:
    id: str
    url: str
    provider: str


@dataclass
class PortalSession:
    id: str
    url: str
    provider: str


class BillingProvider(Protocol):
    name: str

    async def create_checkout_session(self, user_id: str, plan_id: str, email: str) -> CheckoutSession: ...
    async def create_portal_session(self, user_id: str, customer_id: str | None) -> PortalSession: ...
    async def handle_webhook(self, payload: bytes, signature: str | None) -> dict[str, Any]: ...


class MockBillingProvider:
    name = "mock"

    async def create_checkout_session(self, user_id: str, plan_id: str, email: str) -> CheckoutSession:
        return CheckoutSession(id=f"mock_cs_{user_id}_{plan_id}", url=f"{settings.frontend_url}/billing/mock?plan={plan_id}", provider=self.name)

    async def create_portal_session(self, user_id: str, customer_id: str | None) -> PortalSession:
        return PortalSession(id=f"mock_portal_{user_id}", url=f"{settings.frontend_url}/billing/portal", provider=self.name)

    async def handle_webhook(self, payload: bytes, signature: str | None) -> dict[str, Any]:
        return {"received": True, "mock": True}


class StripeBillingProvider:
    name = "stripe"

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(base_url=settings.stripe_api_base, timeout=30)

    async def create_checkout_session(self, user_id: str, plan_id: str, email: str) -> CheckoutSession:
        price_id = {
            "free": settings.stripe_price_free,
            "pro": settings.stripe_price_pro,
            "team": settings.stripe_price_team,
            "enterprise": settings.stripe_price_enterprise,
        }.get(plan_id)
        if not price_id:
            raise AppError("No Stripe price configured for this plan.", code="billing_not_configured", status_code=400)
        response = await self._client.post(
            "/v1/checkout/sessions",
            auth=(settings.stripe_secret_key, ""),
            data={
                "mode": "subscription",
                "customer_email": email,
                "line_items[0][price]": price_id,
                "line_items[0][quantity]": "1",
                "success_url": settings.billing_success_url,
                "cancel_url": settings.billing_cancel_url,
                "metadata[user_id]": user_id,
                "metadata[plan_id]": plan_id,
            },
        )
        response.raise_for_status()
        data = response.json()
        return CheckoutSession(id=data["id"], url=data["url"], provider=self.name)

    async def create_portal_session(self, user_id: str, customer_id: str | None) -> PortalSession:
        if not customer_id:
            raise AppError("No Stripe customer found for this account.", code="billing_not_configured", status_code=400)
        response = await self._client.post(
            "/v1/billing_portal/sessions",
            auth=(settings.stripe_secret_key, ""),
            data={"customer": customer_id, "return_url": settings.billing_portal_return_url},
        )
        response.raise_for_status()
        data = response.json()
        return PortalSession(id=data["id"], url=data["url"], provider=self.name)

    async def handle_webhook(self, payload: bytes, signature: str | None) -> dict[str, Any]:
        if not signature:
            raise AppError("Missing Stripe signature.", code="invalid_signature", status_code=400)
        # Stripe signature verification is implemented in billing_service using the webhook secret.
        return {"received": True, "provider": self.name}


def get_billing_provider() -> BillingProvider:
    if settings.stripe_enabled:
        return StripeBillingProvider()
    return MockBillingProvider()
