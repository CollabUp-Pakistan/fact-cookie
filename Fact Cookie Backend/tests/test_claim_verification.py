"""Tests for explicit-claim verification used by MCP verify_claim/check_citation."""

from __future__ import annotations

import uuid

import pytest

from app.agents.models import Claim, ClaimType
from app.db.session import session_factory
from app.services import auth_service, plan_service, verification_service


@pytest.mark.asyncio
async def test_create_claim_verification_mock_mode():
    async with session_factory() as db:
        await plan_service.seed_plans(db)
        user = await auth_service.register_user(db, f"claim-{uuid.uuid4().hex[:8]}@example.com", "password123", "Claim User")
        claim = Claim(text="Water boils at 100C.", claim_type=ClaimType.number, position=0)
        verification = await verification_service.create_claim_verification(
            db, user, [claim], claim.text, None, source="mcp"
        )
        assert verification.status == "completed"
        assert verification.claim_count == 1
        assert verification.result_json["claims"][0]["verdict"] == "unverifiable"
