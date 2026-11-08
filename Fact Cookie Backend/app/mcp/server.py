"""FastMCP connector for Fact Cookie.

Exposes verification tools over MCP with bearer-token auth that accepts either
Fact Cookie API keys or MCP-audience JWT access tokens.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastmcp import FastMCP
from fastmcp.server.auth import AccessToken, TokenVerifier
from fastmcp.server.dependencies import CurrentAccessToken
from sqlalchemy import select

from app.agents.models import Claim, ClaimType
from app.core.config import settings
from app.core.security import (
    ACCESS_TOKEN_AUDIENCE_MCP,
    decode_access_token,
    hash_api_key,
    is_api_key,
)
from app.db.models import ApiKey, OAuthToken, User
from app.db.session import session_factory


class FactCookieTokenVerifier(TokenVerifier):
    """Verify Fact Cookie API keys and MCP-audience JWTs."""

    async def verify_token(self, token: str) -> AccessToken | None:
        async with session_factory() as db:
            if is_api_key(token):
                result = await db.execute(select(ApiKey).where(ApiKey.key_hash == hash_api_key(token)))
                api_key = result.scalar_one_or_none()
                if not api_key or api_key.revoked_at is not None:
                    return None
                user = await db.get(User, api_key.user_id)
                if not user or not user.is_active:
                    return None
                api_key.last_used_at = datetime.now(timezone.utc)
                await db.commit()
                return AccessToken(
                    token=token,
                    client_id=str(user.id),
                    scopes=list(settings.oauth_scopes),
                    subject=str(user.id),
                    claims={"user_id": str(user.id), "auth_method": "api_key", "api_key_id": api_key.id},
                )

            try:
                payload = decode_access_token(token, audience=ACCESS_TOKEN_AUDIENCE_MCP)
            except Exception:
                return None
            user = await db.get(User, payload["sub"])
            if not user or not user.is_active:
                return None
            oauth_result = await db.execute(select(OAuthToken).where(OAuthToken.jti == payload.get("jti")))
            oauth_token = oauth_result.scalar_one_or_none()
            if not oauth_token or oauth_token.revoked_at is not None:
                return None
            if oauth_token.access_expires_at and oauth_token.access_expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
                return None
            return AccessToken(
                token=token,
                client_id=str(user.id),
                scopes=list(settings.oauth_scopes),
                expires_at=payload.get("exp"),
                subject=str(user.id),
                claims={**payload, "user_id": str(user.id), "auth_method": "jwt"},
            )


mcp = FastMCP(
    name="Fact Cookie",
    instructions="Verify AI-generated answers claim-by-claim with citations and evidence.",
    auth=FactCookieTokenVerifier(base_url=settings.base_url, required_scopes=None),
)


async def _current_user(token: AccessToken) -> User:
    user_id = token.claims.get("user_id") or token.subject or token.client_id
    async with session_factory() as db:
        user = await db.get(User, user_id)
        if not user or not user.is_active:
            raise ValueError("User not found or inactive")
        return user


def _verification_payload(verification) -> dict[str, Any]:
    return {
        "id": verification.id,
        "status": verification.status,
        "mode": verification.mode,
        "claim_count": verification.claim_count,
        "corrected_text": verification.corrected_text,
        "result": verification.result_json,
        "error": verification.error,
    }


@mcp.tool
def health() -> dict[str, str]:
    """Health check for the Fact Cookie MCP connector."""
    return {"status": "ok", "service": settings.app_name}


@mcp.tool
async def verify_text(text: str, context: str | None = None, mode: str = "sync", token: AccessToken = CurrentAccessToken()) -> dict[str, Any]:
    """Verify an AI answer and return per-claim verdicts with evidence.

    Use when an answer contains numbers, dates, names, quotes or citations.

    Args:
        text: The AI-generated answer to verify.
        context: Optional source material or additional context.
        mode: "sync" for short inputs or "async" for long-running verification.
    """
    try:
        user = await _current_user(token)
        async with session_factory() as db:
            from app.services import verification_service

            verification, job = await verification_service.create_verification(
                db, user, text, context, mode, source="mcp"
            )
            if job:
                return {
                    "id": verification.id,
                    "status": verification.status,
                    "mode": verification.mode,
                    "job_id": job.id,
                    "message": "Verification queued. Poll get_verification until completed.",
                }
            await db.refresh(verification)
            return _verification_payload(verification)
    except Exception as exc:
        return {"error": str(exc), "verdict": "unverifiable"}


@mcp.tool
async def get_verification(verification_id: str, token: AccessToken = CurrentAccessToken()) -> dict[str, Any]:
    """Fetch a verification result by ID."""
    try:
        from app.db.models import Verification

        user = await _current_user(token)
        async with session_factory() as db:
            result = await db.execute(select(Verification).where(Verification.id == verification_id, Verification.user_id == str(user.id)))
            verification = result.scalar_one_or_none()
            if not verification:
                return {"error": "Verification not found"}
            return {
                "id": verification.id,
                "status": verification.status,
                "mode": verification.mode,
                "claim_count": verification.claim_count,
                "corrected_text": verification.corrected_text,
                "result": verification.result_json,
                "error": verification.error,
                "created_at": verification.created_at.isoformat(),
                "completed_at": verification.completed_at.isoformat() if verification.completed_at else None,
            }
    except Exception as exc:
        return {"error": str(exc)}


@mcp.tool
async def list_verifications(limit: int = 10, token: AccessToken = CurrentAccessToken()) -> list[dict[str, Any]]:
    """List recent verifications for the authenticated user."""
    try:
        from app.db.models import Verification

        user = await _current_user(token)
        async with session_factory() as db:
            result = await db.execute(
                select(Verification)
                .where(Verification.user_id == str(user.id))
                .order_by(Verification.created_at.desc())
                .limit(min(limit, 50))
            )
            return [
                {
                    "id": v.id,
                    "status": v.status,
                    "mode": v.mode,
                    "claim_count": v.claim_count,
                    "created_at": v.created_at.isoformat(),
                }
                for v in result.scalars().all()
            ]
    except Exception as exc:
        return [{"error": str(exc)}]


@mcp.tool
async def verify_claim(claim: str, context: str | None = None, token: AccessToken = CurrentAccessToken()) -> dict[str, Any]:
    """Verify one factual claim and return verdict, confidence, source_url, snippet, page_or_section, explanation, and corrected_text.

    Use for a single number, date, name, quote, or citation that needs checking.
    """
    try:
        user = await _current_user(token)
        async with session_factory() as db:
            from app.services import verification_service

            agent_claim = Claim(text=claim, claim_type=ClaimType.other, position=0)
            verification = await verification_service.create_claim_verification(
                db, user, [agent_claim], claim, context, source="mcp"
            )
            await db.refresh(verification)
            payload = _verification_payload(verification)
            claims = (payload.get("result") or {}).get("claims") or []
            if claims:
                payload["claim"] = claims[0]
                payload["verdict"] = claims[0].get("verdict")
            return payload
    except Exception as exc:
        return {"error": str(exc), "verdict": "unverifiable"}


@mcp.tool
async def check_citation(citation_text: str, claim: str | None = None, context: str | None = None, token: AccessToken = CurrentAccessToken()) -> dict[str, Any]:
    """Check whether a cited source, page, or section exists and supports the claim.

    Use when you have a citation string and want to know if it is real and relevant.
    """
    try:
        user = await _current_user(token)
        context_text = claim or context
        if claim and context:
            context_text = f"{context}\n\nClaim being checked: {claim}"
        async with session_factory() as db:
            from app.services import verification_service

            agent_claim = Claim(text=citation_text, claim_type=ClaimType.citation, position=0)
            verification = await verification_service.create_claim_verification(
                db, user, [agent_claim], citation_text, context_text, source="mcp"
            )
            await db.refresh(verification)
            payload = _verification_payload(verification)
            claims = (payload.get("result") or {}).get("claims") or []
            if claims:
                payload["claim"] = claims[0]
                payload["verdict"] = claims[0].get("verdict")
            return payload
    except Exception as exc:
        return {"error": str(exc), "verdict": "unverifiable"}


@mcp.tool
async def get_usage(token: AccessToken = CurrentAccessToken()) -> dict[str, Any]:
    """Return the authenticated user's remaining quota and current plan."""
    try:
        user = await _current_user(token)
        async with session_factory() as db:
            from app.services import usage_service

            return await usage_service.get_usage_summary(db, user)
    except Exception as exc:
        return {"error": str(exc)}


mcp_app = mcp.http_app(path="/")
