"""Mock retrieval providers for tests and offline mode."""

from __future__ import annotations

from app.retrieval.interfaces import ExtractResponse, PageContent, SearchResponse, SearchResult


class MockSearchProvider:
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
        results = [
            SearchResult(
                title="Mock result",
                url="https://example.com/mock",
                snippet=f"Mock evidence for {query}",
                content=f"Mock evidence for {query}. This is deterministic fixture content.",
            )
        ]
        return SearchResponse(results=results[:max_results], provider="mock")


class MockPageFetcher:
    async def fetch(self, url: str, *, max_chars: int = 20000) -> PageContent | None:
        return PageContent(url=url, title="Mock page", text=f"Mock page content for {url}", truncated=False)


class MockExtractProvider:
    async def extract(self, urls: list[str], *, max_chars: int = 20000) -> ExtractResponse:
        pages = [PageContent(url=url, title="Mock page", text=f"Mock extracted content for {url}") for url in urls]
        return ExtractResponse(pages=pages, provider="mock")
