"""Pydantic schemas for claims, evidence, verdicts, and verification results."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ClaimType(str, Enum):
    number = "number"
    date = "date"
    name = "name"
    quote = "quote"
    citation = "citation"
    other = "other"


class Verdict(str, Enum):
    supported = "supported"
    outdated = "outdated"
    contradicted = "contradicted"
    unverifiable = "unverifiable"


class Claim(BaseModel):
    text: str
    claim_type: ClaimType = ClaimType.other
    position: int = 0


class ExtractedClaims(BaseModel):
    claims: list[Claim] = Field(default_factory=list)


class Evidence(BaseModel):
    source_url: str
    snippet: str
    title: str | None = None
    page_or_section: str | None = None
    content: str = ""
    provider: str = "mock"
    published_date: str | None = None


class ClaimVerdict(BaseModel):
    claim: Claim
    verdict: Verdict = Verdict.unverifiable
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    explanation: str | None = None
    source_url: str | None = None
    snippet: str | None = None
    page_or_section: str | None = None
    corrected_text: str | None = None
    evidence: list[Evidence] = Field(default_factory=list)


class RewriteResult(BaseModel):
    corrected_text: str
    citations: list[str] = Field(default_factory=list)


class VerificationResult(BaseModel):
    verification_id: str | None = None
    claims: list[ClaimVerdict] = Field(default_factory=list)
    corrected_text: str | None = None
    trace_id: str | None = None
    orchestration_mode: str = "pipeline"
    llm_mode: str = "mock"
    tavily_search_count: int = 0
    tavily_extract_count: int = 0
    meta: dict[str, Any] = Field(default_factory=dict)
