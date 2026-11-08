"""Mock LLM outputs for offline tests and development."""

from __future__ import annotations

import re

from app.agents.models import Claim, ClaimType, ExtractedClaims


_CLAIM_PATTERNS = [
    (ClaimType.number, re.compile(r"\b\d+(?:\.\d+)?%?\b")),
    (ClaimType.date, re.compile(r"\b(?:19|20)\d{2}\b|\b\d{1,2}/\d{1,2}/\d{2,4}\b")),
    (ClaimType.quote, re.compile(r"[\"“].+?[\"”]")),
]


def mock_extract_claims(text: str, max_claims: int = 8) -> ExtractedClaims:
    claims: list[Claim] = []
    sentences = re.split(r"(?<=[.!?])\s+", text)
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        claim_type = ClaimType.other
        for candidate_type, pattern in _CLAIM_PATTERNS:
            if pattern.search(sentence):
                claim_type = candidate_type
                break
        if claim_type != ClaimType.other or len(claims) < max_claims // 2:
            claims.append(Claim(text=sentence, claim_type=claim_type, position=len(claims)))
        if len(claims) >= max_claims:
            break
    return ExtractedClaims(claims=claims)


def mock_verdict(claim: Claim) -> dict:
    return {
        "verdict": "unverifiable",
        "confidence": 0.0,
        "explanation": "Mock mode: no live evidence retrieval.",
        "source_url": None,
        "snippet": None,
        "page_or_section": None,
        "corrected_text": None,
        "evidence": [],
    }


def mock_rewrite(text: str, verdicts: list[dict]) -> str:
    return text
