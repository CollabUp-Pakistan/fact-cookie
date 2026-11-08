"""Deterministic pipeline orchestration and Agents SDK orchestration."""

from __future__ import annotations

import json
import re
from typing import Any

from agents import Runner, RunConfig, RunContextWrapper
from pydantic import ValidationError

from app.agents.guardrails import validate_verification_result
from app.agents.mock_llm import mock_extract_claims, mock_rewrite, mock_verdict
from app.agents.models import Claim, ClaimType, ClaimVerdict, Evidence, Verdict, VerificationResult
from app.agents.tools import AgentContext, fetch_page, get_user_preferences, save_verification, search_documents, web_search
from app.core.config import settings
from app.retrieval.factory import get_fallback_fetcher, get_page_fetcher, get_search_provider
from app.services import document_service


async def run_verification_pipeline(context: AgentContext, text: str, context_text: str | None = None) -> VerificationResult:
    if settings.llm_mode == "mock":
        return await _mock_pipeline(context, text, context_text)
    return await _live_pipeline(context, text, context_text)


async def verify_claims_pipeline(
    context: AgentContext,
    claims: list[Claim],
    context_text: str | None = None,
) -> VerificationResult:
    """Verify explicit claims without extraction or rewriting."""
    if settings.llm_mode == "mock":
        verdicts = [
            ClaimVerdict(
                claim=claim,
                verdict=Verdict.unverifiable,
                confidence=0.0,
                explanation="Mock mode: no live evidence retrieval.",
            )
            for claim in claims
        ]
        return VerificationResult(
            claims=verdicts,
            corrected_text=None,
            orchestration_mode="pipeline",
            llm_mode="mock",
        )

    from app.agents.specialists import build_agents
    from app.agents.llm import configure_agents_sdk

    configure_agents_sdk()
    verifier = build_agents()["verifier"]
    verdicts: list[ClaimVerdict] = []
    for claim in claims:
        evidence = await _gather_evidence(context, claim.text, context_text)
        verify_input = {
            "claim": claim.model_dump(),
            "evidence": [e.model_dump() for e in evidence],
            "context": context_text,
            "citation_check": claim.claim_type == ClaimType.citation,
        }
        verify_result = await Runner.run(
            verifier,
            json.dumps(verify_input),
            run_config=RunConfig(trace_include_sensitive_data=False),
        )
        verdict = _coerce_claim_verdict(verify_result.final_output, claim)
        verdict.evidence = evidence
        verdicts.append(verdict)

    result = VerificationResult(
        claims=verdicts,
        corrected_text=None,
        orchestration_mode="pipeline",
        llm_mode="live",
        tavily_search_count=context.search_count,
        tavily_extract_count=context.extract_count,
    )
    validate_verification_result(result)
    return result


async def _mock_pipeline(context: AgentContext, text: str, context_text: str | None) -> VerificationResult:
    extracted = mock_extract_claims(text, max_claims=settings.max_claims_per_verification)
    verdicts = []
    for claim in extracted.claims:
        verdicts.append(
            ClaimVerdict(
                claim=claim,
                verdict="unverifiable",
                confidence=0.0,
                explanation="Mock mode: no live evidence retrieval.",
            )
        )
    corrected = mock_rewrite(text, [v.model_dump() for v in verdicts])
    result = VerificationResult(
        claims=verdicts,
        corrected_text=corrected,
        orchestration_mode="pipeline",
        llm_mode="mock",
    )
    validate_verification_result(result)
    return result


async def _live_pipeline(context: AgentContext, text: str, context_text: str | None) -> VerificationResult:
    from app.agents.specialists import build_agents
    from app.agents.llm import configure_agents_sdk

    configure_agents_sdk()
    agents = build_agents()
    extractor = agents["extractor"]
    researcher = agents["researcher"]
    verifier = agents["verifier"]
    rewriter = agents["rewriter"]

    extract_result = await Runner.run(extractor, text, run_config=RunConfig(trace_include_sensitive_data=False))
    extracted = _coerce_extracted(extract_result.final_output)
    claims = extracted.claims[: settings.max_claims_per_verification]

    verdicts: list[ClaimVerdict] = []
    for claim in claims:
        evidence = await _gather_evidence(context, claim.text, context_text)
        verify_input = {
            "claim": claim.model_dump(),
            "evidence": [e.model_dump() for e in evidence],
        }
        verify_result = await Runner.run(
            verifier,
            json.dumps(verify_input),
            run_config=RunConfig(trace_include_sensitive_data=False),
        )
        verdict = _coerce_claim_verdict(verify_result.final_output, claim)
        verdict.evidence = evidence
        verdicts.append(verdict)

    rewrite_result = await Runner.run(
        rewriter,
        json.dumps({"text": text, "verdicts": [v.model_dump() for v in verdicts]}),
        run_config=RunConfig(trace_include_sensitive_data=False),
    )
    corrected = getattr(rewrite_result, "final_output", None)
    if hasattr(corrected, "corrected_text"):
        corrected_text = corrected.corrected_text
    else:
        corrected_text = str(corrected) if corrected else text

    result = VerificationResult(
        claims=verdicts,
        corrected_text=corrected_text,
        orchestration_mode="pipeline",
        llm_mode="live",
        tavily_search_count=context.search_count,
        tavily_extract_count=context.extract_count,
    )
    validate_verification_result(result)
    return result


async def run_verification_agents(context: AgentContext, text: str, context_text: str | None = None) -> VerificationResult:
    if settings.llm_mode == "mock":
        return await _mock_pipeline(context, text, context_text)
    from app.agents.specialists import build_agents
    from app.agents.llm import configure_agents_sdk

    configure_agents_sdk()
    agents = build_agents()
    lead = agents["lead"]
    result = await Runner.run(
        lead,
        json.dumps({"text": text, "context": context_text}),
        run_config=RunConfig(trace_include_sensitive_data=False),
    )
    output = result.final_output
    if isinstance(output, VerificationResult):
        verification = output
    else:
        verification = VerificationResult.model_validate(output)
    verification.orchestration_mode = "agents"
    verification.llm_mode = "live"
    validate_verification_result(verification)
    return verification


def _coerce_extracted(output: Any):
    from app.agents.models import ExtractedClaims

    if isinstance(output, ExtractedClaims):
        return output
    if isinstance(output, dict):
        return ExtractedClaims.model_validate(output)
    if isinstance(output, str):
        try:
            return ExtractedClaims.model_validate_json(output)
        except Exception:
            match = re.search(r"\{.*\}", output, re.DOTALL)
            if match:
                return ExtractedClaims.model_validate_json(match.group(0))
    return ExtractedClaims(claims=[])


def _coerce_claim_verdict(output: Any, claim):
    from app.agents.models import ClaimVerdict, Verdict

    if isinstance(output, ClaimVerdict):
        output.claim = claim
        return output
    if isinstance(output, dict):
        data = dict(output)
        data["claim"] = claim.model_dump()
        return ClaimVerdict.model_validate(data)
    if isinstance(output, str):
        try:
            data = json.loads(output)
            data["claim"] = claim.model_dump()
            return ClaimVerdict.model_validate(data)
        except Exception:
            pass
    return ClaimVerdict(claim=claim, verdict=Verdict.unverifiable, explanation="Could not parse verifier output.")


async def _gather_evidence(context: AgentContext, claim_text: str, context_text: str | None) -> list[Evidence]:
    evidence: list[Evidence] = []
    pref_result = await context.db.execute(__import__("sqlalchemy").select(__import__("app.db.models", fromlist=["Preference"]).Preference).where(__import__("app.db.models", fromlist=["Preference"]).Preference.user_id == str(context.user.id)))
    pref = pref_result.scalar_one_or_none()

    search_provider = get_search_provider()
    search_response = await search_provider.search(
        claim_text,
        max_results=settings.tavily_max_results,
        include_domains=pref.trusted_domains if pref else None,
        exclude_domains=pref.blocked_domains if pref else None,
        days=pref.recency_days if pref else None,
        depth=settings.tavily_search_depth if pref and pref.strictness != "strict" else settings.tavily_advanced_search_depth,
    )
    context.search_count += 1
    for result in search_response.results[: settings.max_searches_per_claim]:
        fetcher = get_page_fetcher()
        page = await fetcher.fetch(result.url, max_chars=settings.max_page_chars)
        if not page:
            fallback = get_fallback_fetcher()
            page = await fallback.fetch(result.url, max_chars=settings.max_page_chars)
        context.extract_count += 1
        content = page.text if page else result.content or result.snippet
        snippet = _extract_snippet(content, claim_text) or result.snippet
        evidence.append(
            Evidence(
                source_url=result.url,
                snippet=snippet[: settings.snippet_max_chars],
                title=result.title or (page.title if page else None),
                page_or_section=None,
                content=content[: settings.max_evidence_chars],
                provider=search_response.provider,
                published_date=result.published_date,
            )
        )

    doc_chunks = await document_service.search_documents(context.db, context.user, claim_text, limit=3)
    for chunk in doc_chunks:
        evidence.append(
            Evidence(
                source_url=f"document://{chunk.document_id}",
                snippet=chunk.content[: settings.snippet_max_chars],
                title=None,
                page_or_section=f"page {chunk.page_number}" + (f", {chunk.section}" if chunk.section else ""),
                content=chunk.content[: settings.max_evidence_chars],
                provider="documents",
            )
        )
    return evidence[: settings.max_fetches_per_claim + 3]


def _extract_snippet(text: str, claim: str, window: int = 300) -> str:
    lower = text.lower()
    claim_lower = claim.lower()
    idx = lower.find(claim_lower)
    if idx == -1:
        return text[:window]
    start = max(0, idx - window // 2)
    end = min(len(text), idx + len(claim) + window // 2)
    return text[start:end]
