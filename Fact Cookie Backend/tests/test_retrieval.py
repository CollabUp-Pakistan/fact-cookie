"""Tests for SSRF guard and document indexing."""

from __future__ import annotations

import pytest

from app.retrieval.ssrf import SSRFError, validate_url


@pytest.mark.asyncio
async def test_ssrf_blocks_localhost():
    with pytest.raises(SSRFError):
        await validate_url("http://localhost:8000")


@pytest.mark.asyncio
async def test_ssrf_blocks_private_ip():
    with pytest.raises(SSRFError):
        await validate_url("http://192.168.1.1")


@pytest.mark.asyncio
async def test_ssrf_blocks_metadata_ip():
    with pytest.raises(SSRFError):
        await validate_url("http://169.254.169.254/latest/meta-data")


@pytest.mark.asyncio
async def test_ssrf_blocks_non_http():
    with pytest.raises(SSRFError):
        await validate_url("ftp://example.com")
