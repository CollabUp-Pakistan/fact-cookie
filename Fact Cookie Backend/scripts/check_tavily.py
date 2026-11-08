"""Check Tavily search/extract configuration with a tiny live query."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings
from app.retrieval.factory import get_fallback_fetcher, get_page_fetcher, get_search_provider


async def main() -> int:
    if not settings.tavily_enabled:
        print("TAVILY_API_KEY is not set; Tavily checks skipped.")
        return 0

    provider = get_search_provider()
    response = await provider.search("Fact Cookie verification", max_results=1, depth=settings.tavily_search_depth)
    print("provider:", response.provider, "results:", len(response.results), "error:", response.error)
    if response.quota_error:
        print("Tavily quota error; check plan/rate limits.")
        return 1
    if not response.results:
        print("No Tavily results returned.")
        return 1

    url = response.results[0].url
    fetcher = get_page_fetcher()
    page = await fetcher.fetch(url, max_chars=1000)
    if not page:
        page = await get_fallback_fetcher().fetch(url, max_chars=1000)
    print("fetch:", "ok" if page else "failed", url)
    return 0 if page else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
