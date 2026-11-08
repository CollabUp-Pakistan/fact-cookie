"""HTTP page fetcher with SSRF protection and readable-text extraction."""

from __future__ import annotations

import httpx
import trafilatura

from app.core.config import settings
from app.retrieval.interfaces import PageContent
from app.retrieval.ssrf import validate_url


class HttpPageFetcher:
    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            timeout=settings.http_fetch_timeout_seconds,
            follow_redirects=False,
            headers={"User-Agent": settings.http_fetch_user_agent},
        )

    async def fetch(self, url: str, *, max_chars: int = 20000) -> PageContent | None:
        current = url
        for _ in range(settings.http_fetch_max_redirects + 1):
            await validate_url(current)
            try:
                response = await self._client.get(current)
            except httpx.HTTPError:
                return None
            if response.is_redirect:
                location = response.headers.get("location")
                if not location:
                    return None
                current = str(response.url.join(location))
                continue
            if response.status_code >= 400:
                return None
            content_type = response.headers.get("content-type", "")
            if "text" not in content_type and "html" not in content_type and "xml" not in content_type:
                return None
            html = response.text
            text = trafilatura.extract(html, include_comments=False, include_tables=False) or ""
            if not text:
                from bs4 import BeautifulSoup

                soup = BeautifulSoup(html, "html.parser")
                for tag in soup(["script", "style", "nav", "footer", "header"]):
                    tag.decompose()
                text = soup.get_text("\n", strip=True)
            title = ""
            try:
                from bs4 import BeautifulSoup

                title = BeautifulSoup(html, "html.parser").title.string if BeautifulSoup(html, "html.parser").title else ""
            except Exception:
                title = ""
            truncated = len(text) > max_chars
            return PageContent(url=current, title=title or current, text=text[:max_chars], truncated=truncated)
        return None
