"""Verification REST routes."""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.errors import NotFoundError
from app.core.rate_limit import rate_limiter
from app.db.models import Claim, User, Verification
from app.db.session import get_db
from app.jobs.worker import job_queue
from app.services import verification_service

router = APIRouter(prefix="/verifications", tags=["verifications"])
jobs_router = APIRouter(prefix="/jobs", tags=["jobs"])


class VerificationRequest(BaseModel):
    text: str = Field(min_length=1)
    context: str | None = None
    mode: str = Field(default="sync", pattern="^(sync|async)$")


class ClaimOut(BaseModel):
    id: str
    position: int
    text: str
    claim_type: str
    verdict: str
    confidence: float
    explanation: str | None
    source_url: str | None
    snippet: str | None
    page_or_section: str | None
    corrected_text: str | None
    evidence: list[dict[str, Any]]


class VerificationOut(BaseModel):
    id: str
    status: str
    mode: str
    source_agent: str
    input_text: str
    context_text: str | None
    orchestration_mode: str
    llm_mode: str
    trace_id: str | None
    corrected_text: str | None
    result: dict[str, Any] | None
    error: str | None
    claim_count: int
    tavily_search_count: int
    tavily_extract_count: int
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    claims: list[ClaimOut] = []


@router.post("", response_model=VerificationOut, status_code=201)
async def create_verification(
    body: VerificationRequest,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> VerificationOut:
    client_ip = request.client.host if request.client else "unknown"
    await rate_limiter.check(f"verification:{user.id}:{client_ip}", settings.rate_limit_verification, settings.rate_limit_verification_window)
    verification, job = await verification_service.create_verification(db, user, body.text, body.context, body.mode, source="rest")
    if job:
        return _verification_out(verification, [])
    await db.refresh(verification)
    claims = await _get_claims(db, verification.id)
    return _verification_out(verification, claims)


@router.get("", response_model=list[VerificationOut])
async def list_verifications(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    verdict: str | None = None,
    status: str | None = None,
    source_agent: str | None = None,
    search: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[VerificationOut]:
    stmt = select(Verification).where(Verification.user_id == str(user.id))
    if verdict:
        stmt = stmt.where(Verification.result_json["claims"].contains(verdict))
    if status:
        stmt = stmt.where(Verification.status == status)
    if source_agent:
        stmt = stmt.where(Verification.source_agent == source_agent)
    if search:
        stmt = stmt.where(Verification.input_text.contains(search))
    if date_from:
        stmt = stmt.where(Verification.created_at >= date_from)
    if date_to:
        stmt = stmt.where(Verification.created_at <= date_to)
    stmt = stmt.order_by(Verification.created_at.desc()).limit(limit).offset(offset)
    result = await db.execute(stmt)
    verifications = result.scalars().all()
    out = []
    for v in verifications:
        claims = await _get_claims(db, v.id)
        out.append(_verification_out(v, claims))
    return out


@router.get("/{verification_id}", response_model=VerificationOut)
async def get_verification(
    verification_id: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> VerificationOut:
    verification = await db.get(Verification, verification_id)
    if not verification or verification.user_id != str(user.id):
        raise NotFoundError("Verification not found.")
    claims = await _get_claims(db, verification.id)
    return _verification_out(verification, claims)


@router.delete("/{verification_id}", status_code=204)
async def delete_verification(
    verification_id: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    verification = await db.get(Verification, verification_id)
    if not verification or verification.user_id != str(user.id):
        raise NotFoundError("Verification not found.")
    await db.delete(verification)
    await db.commit()


@router.get("/{verification_id}/export")
async def export_verification(
    verification_id: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    format: str = Query("json", pattern="^(json|csv)$"),
):
    verification = await db.get(Verification, verification_id)
    if not verification or verification.user_id != str(user.id):
        raise NotFoundError("Verification not found.")
    claims = await _get_claims(db, verification.id)
    data = _verification_out(verification, claims).model_dump()
    if format == "json":
        return JSONResponse(data)
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["position", "text", "claim_type", "verdict", "confidence", "source_url", "snippet", "page_or_section"])
    writer.writeheader()
    for claim in claims:
        writer.writerow(claim.model_dump())
    return StreamingResponse(io.BytesIO(output.getvalue().encode("utf-8")), media_type="text/csv", headers={"Content-Disposition": f"attachment; filename=verification-{verification_id}.csv"})


@jobs_router.get("/{job_id}")
async def get_job(
    job_id: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    job = await job_queue.get(db, job_id, str(user.id))
    if not job:
        raise NotFoundError("Job not found.")
    return {
        "id": job.id,
        "type": job.type,
        "status": job.status,
        "verification_id": job.verification_id,
        "error": job.error,
        "attempts": job.attempts,
        "created_at": job.created_at.isoformat(),
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }


async def _get_claims(db: AsyncSession, verification_id: str) -> list[Claim]:
    result = await db.execute(select(Claim).where(Claim.verification_id == verification_id).order_by(Claim.position))
    return list(result.scalars().all())


def _verification_out(v: Verification, claims: list[Claim]) -> VerificationOut:
    return VerificationOut(
        id=v.id,
        status=v.status,
        mode=v.mode,
        source_agent=v.source_agent,
        input_text=v.input_text,
        context_text=v.context_text,
        orchestration_mode=v.orchestration_mode,
        llm_mode=v.llm_mode,
        trace_id=v.trace_id,
        corrected_text=v.corrected_text,
        result=v.result_json,
        error=v.error,
        claim_count=v.claim_count,
        tavily_search_count=v.tavily_search_count,
        tavily_extract_count=v.tavily_extract_count,
        created_at=v.created_at,
        started_at=v.started_at,
        completed_at=v.completed_at,
        claims=[
            ClaimOut(
                id=c.id,
                position=c.position,
                text=c.text,
                claim_type=c.claim_type,
                verdict=c.verdict,
                confidence=c.confidence,
                explanation=c.explanation,
                source_url=c.source_url,
                snippet=c.snippet,
                page_or_section=c.page_or_section,
                corrected_text=c.corrected_text,
                evidence=c.evidence_json,
            )
            for c in claims
        ],
    )
