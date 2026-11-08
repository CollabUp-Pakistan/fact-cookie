"""Deterministic post-validation for verdicts and evidence."""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from app.agents.models import ClaimVerdict, Verdict


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def snippet_matches_source(snippet: str, source_text: str, threshold: float = 0.6) -> bool:
    snippet_norm = _normalize(snippet)
    source_norm = _normalize(source_text)
    if not snippet_norm or not source_norm:
        return False
    if snippet_norm in source_norm:
        return True
    return SequenceMatcher(None, snippet_norm, source_norm).ratio() >= threshold


def validate_claim_verdict(verdict: ClaimVerdict) -> ClaimVerdict:
    if verdict.verdict == Verdict.unverifiable:
        return verdict
    has_evidence = any(e.source_url and e.snippet for e in verdict.evidence)
    if not has_evidence:
        verdict.verdict = Verdict.unverifiable
        verdict.confidence = 0.0
        verdict.explanation = (verdict.explanation or "") + " Downgraded: missing source URL or snippet."
        return verdict
    for evidence in verdict.evidence:
        if evidence.snippet and evidence.content and not snippet_matches_source(evidence.snippet, evidence.content):
            verdict.verdict = Verdict.unverifiable
            verdict.confidence = 0.0
            verdict.explanation = (verdict.explanation or "") + " Downgraded: snippet not found in source text."
            return verdict
    return verdict


def validate_verification_result(result) -> None:
    for claim in result.claims:
        validate_claim_verdict(claim)
