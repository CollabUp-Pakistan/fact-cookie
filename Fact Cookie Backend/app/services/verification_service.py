"""Verification service: sync/async execution, persistence, usage."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.models import Claim as AgentClaim, ClaimVerdict, VerificationResult
from app.agents.pipeline import run_verification_agents, run_verification_pipeline, verify_claims_pipeline
from app.agents.tools import AgentContext
from app.core.config import settings
from app.core.errors import AppError, BudgetExceededError, PayloadTooLargeError
from app.db.models import Claim, Job, User, Verification
from app.jobs.worker import job_queue
from app.services import usage_service


async def create_verification(
    db: AsyncSession,
    user: User,
    text: str,
    context_text: str | None,
    mode: str,
    source: str = "rest",
) -> tuple[Verification, Job | None]:
    if not text.strip():
        raise AppError("Text must not be empty.", code="validation_error", status_code=422)
    if len(text) > settings.max_input_chars:
        raise PayloadTooLargeError("Input text exceeds maximum length.")
    if len(text) > settings.sync_max_chars and mode == "sync":
        mode = "async"

    verification = Verification(
        user_id=str(user.id),
        source_agent=source,
        status="pending",
        mode=mode,
        input_text=text,
        context_text=context_text,
        orchestration_mode=settings.orchestration_mode,
        llm_mode=settings.llm_mode,
    )
    db.add(verification)
    await db.flush()

    if mode == "async":
        job = await job_queue.enqueue(db, str(user.id), "verification", {"verification_id": verification.id, "text": text, "context": context_text, "source": source})
        job.verification_id = verification.id
        await db.commit()
        return verification, job

    await db.commit()
    await db.refresh(verification)
    await execute_verification(db, verification, user)
    return verification, None


async def create_claim_verification(
    db: AsyncSession,
    user: User,
    claims: list[AgentClaim],
    input_text: str,
    context_text: str | None,
    source: str = "rest",
) -> Verification:
    if not claims:
        raise AppError("At least one claim is required.", code="validation_error", status_code=422)
    if not input_text.strip():
        raise AppError("Text must not be empty.", code="validation_error", status_code=422)
    if len(input_text) > settings.max_input_chars:
        raise PayloadTooLargeError("Input text exceeds maximum length.")

    verification = Verification(
        user_id=str(user.id),
        source_agent=source,
        status="pending",
        mode="sync",
        input_text=input_text,
        context_text=context_text,
        orchestration_mode=settings.orchestration_mode,
        llm_mode=settings.llm_mode,
    )
    db.add(verification)
    await db.flush()
    await db.commit()
    await db.refresh(verification)
    await execute_claim_verification(db, verification, user, claims)
    return verification


async def execute_claim_verification(db: AsyncSession, verification: Verification, user: User, claims: list[AgentClaim]) -> VerificationResult:
    verification.status = "running"
    verification.started_at = datetime.now(timezone.utc)
    await db.commit()

    context = AgentContext(db=db, user=user, verification_id=verification.id)
    try:
        result = await verify_claims_pipeline(context, claims, verification.context_text)
        result.verification_id = verification.id
        await persist_result(db, verification, user, result, source=verification.source_agent)
        verification.status = "completed"
        verification.completed_at = datetime.now(timezone.utc)
        await db.commit()
        return result
    except Exception as exc:
        verification.status = "failed"
        verification.error = str(exc)
        verification.completed_at = datetime.now(timezone.utc)
        await db.commit()
        raise


async def execute_verification(db: AsyncSession, verification: Verification, user: User) -> VerificationResult:
    verification.status = "running"
    verification.started_at = datetime.now(timezone.utc)
    await db.commit()

    context = AgentContext(db=db, user=user, verification_id=verification.id)
    try:
        if settings.orchestration_mode == "agents":
            result = await run_verification_agents(context, verification.input_text, verification.context_text)
        else:
            result = await run_verification_pipeline(context, verification.input_text, verification.context_text)
        result.verification_id = verification.id
        await persist_result(db, verification, user, result, source=verification.source_agent)
        verification.status = "completed"
        verification.completed_at = datetime.now(timezone.utc)
        await db.commit()
        return result
    except Exception as exc:
        verification.status = "failed"
        verification.error = str(exc)
        verification.completed_at = datetime.now(timezone.utc)
        await db.commit()
        raise


async def persist_result(db: AsyncSession, verification: Verification, user: User, result: VerificationResult, source: str) -> None:
    verification.result_json = result.model_dump()
    verification.corrected_text = result.corrected_text
    verification.claim_count = len(result.claims)
    verification.tavily_search_count = result.tavily_search_count
    verification.tavily_extract_count = result.tavily_extract_count
    verification.trace_id = result.trace_id or uuid.uuid4().hex

    await usage_service.check_and_record_usage(db, user, len(result.claims), source=source, verification_id=verification.id)
    for verdict in result.claims:
        db.add(
            Claim(
                verification_id=verification.id,
                user_id=str(user.id),
                position=verdict.claim.position,
                text=verdict.claim.text,
                claim_type=verdict.claim.claim_type.value,
                verdict=verdict.verdict.value,
                confidence=verdict.confidence,
                explanation=verdict.explanation,
                source_url=verdict.source_url,
                snippet=verdict.snippet,
                page_or_section=verdict.page_or_section,
                corrected_text=verdict.corrected_text,
                evidence_json=[e.model_dump() for e in verdict.evidence],
            )
        )


async def run_verification_job(db: AsyncSession, job: Job) -> None:
    verification_id = job.payload_json.get("verification_id")
    verification = await db.get(Verification, verification_id)
    if not verification:
        raise AppError("Verification not found.", code="not_found", status_code=404)
    user = await db.get(User, verification.user_id)
    if not user:
        raise AppError("User not found.", code="not_found", status_code=404)
    await execute_verification(db, verification, user)
