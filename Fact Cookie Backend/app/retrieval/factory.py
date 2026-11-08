"""Retrieval factory: choose Tavily/HTTP/mock providers."""

from __future__ import annotations

from app.core.config import settings
from app.retrieval.http_fetcher import HttpPageFetcher
from app.retrieval.interfaces import PageFetcher, SearchProvider
from app.retrieval.mock import MockPageFetcher, MockSearchProvider
from app.retrieval.tavily import TavilyPageFetcher, TavilySearchProvider


def get_search_provider() -> SearchProvider:
    if settings.tavily_enabled:
        return TavilySearchProvider()
    return MockSearchProvider()


def get_page_fetcher() -> PageFetcher:
    if settings.tavily_enabled:
        return TavilyPageFetcher()
    return HttpPageFetcher()


def get_fallback_fetcher() -> PageFetcher:
    return HttpPageFetcher()
