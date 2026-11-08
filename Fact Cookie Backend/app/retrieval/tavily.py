"""Tavily search and extract providers."""

from __future__ import annotations

from typing import Any

import httpx

from app.core.config import settings
from app.retrieval.interfaces import ExtractResponse, PageContent, SearchResponse, SearchResult


class TavilySearchProvider:
    def __init__(self) -> None:
        self._client = httpx.AsyncClient(base_url="https://api.tavily.com", timeout=settings.tavily_timeout_seconds)

    async def search(
        self,
        query: str,
        *,
        max_results: int = 5,
        include_domains: list[str] | None = None,
        exclude_domains: list[str] | None = None,
        days: int | None = None,
        depth: str = "basic",
    ) -> SearchResponse:
        if not settings.tavily_api_key:
            return SearchResponse(provider="tavily", error="TAVILY_API_KEY not configured")
        payload: dict[str, Any] = {
            "api_key": settings.tavily_api_key,
            "query": query,
            "max_results": max_results,
            "search_depth": depth,
            "include_answer": False,
            "include_raw_content": False,
        }
        if include_domains:
            payload["include_domains"] = include_domains
        if exclude_domains:
            payload["exclude_domains"] = exclude_domains
        if days is not None:
            payload["days"] = days
        try:
            response = await self._client.post("/search", json=payload)
            if response.status_code == 429:
                return SearchResponse(provider="tavily", quota_error=True, error="Tavily rate limit reached")
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPError as exc:
            return SearchResponse(provider="tavily", error=str(exc))
        results = [
            SearchResult(
                title=item.get("title", ""),
                url=item.get("url", ""),
                snippet=item.get("content", ""),
                content=item.get("raw_content", ""),
                published_date=item.get("published_date"),
                score=item.get("score"),
            )
            for item in data.get("results", [])
        ]
        return SearchResponse(results=results, provider="tavily")


class TavilyPageFetcher:
    def __init__(self) -> None:
        self._client = httpx.AsyncClient(base_url="https://api.tavily.com", timeout=settings.tavily_timeout_seconds)

    async def fetch(self, url: str, *, max_chars: int = 20000) -> PageContent | None:
        if not settings.tavily_api_key:
            return None
        try:
            response = await self._client.post(
                "/extract",
                json={"api_key": settings.tavily_api_key, "urls": [url], "extract_depth": settings.tavily_extract_depth},
            )
            if response.status_code == 429:
                return None
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPError:
            return None
        results = data.get("results", [])
        if not results:
            return None
        item = results[0]
        text = item.get("raw_content") or item.get("content") or ""
        return PageContent(url=url, title=item.get("title", ""), text=text[:max_chars], truncated=len(text) > max_chars)


class TavilyExtractProvider:
    def __init__(self) -> None:
        self._fetcher = TavilyPageFetcher()

    async def extract(self, urls: list[str], *, max_chars: int = 20000) -> ExtractResponse:
        pages = []
        quota_error = False
        for url in urls:
            page = await self._fetcher.fetch(url, max_chars=max_chars)
            if page:
                pages.append(page)
        return ExtractResponse(pages=pages, provider="tavily", quota_error=quota_error)
