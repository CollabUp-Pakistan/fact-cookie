"""Retrieval interfaces and shared types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    content: str = ""
    published_date: str | None = None
    score: float | None = None


@dataclass
class PageContent:
    url: str
    title: str
    text: str
    truncated: bool = False


@dataclass
class SearchResponse:
    results: list[SearchResult] = field(default_factory=list)
    provider: str = "mock"
    quota_error: bool = False
    error: str | None = None


@dataclass
class ExtractResponse:
    pages: list[PageContent] = field(default_factory=list)
    provider: str = "mock"
    quota_error: bool = False
    error: str | None = None


class SearchProvider(Protocol):
    async def search(
        self,
        query: str,
        *,
        max_results: int = 5,
        include_domains: list[str] | None = None,
        exclude_domains: list[str] | None = None,
        days: int | None = None,
        depth: str = "basic",
    ) -> SearchResponse: ...


class PageFetcher(Protocol):
    async def fetch(self, url: str, *, max_chars: int = 20000) -> PageContent | None: ...
