"""Check the configured OpenRouter model with a tiny chat completion."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from openai import AsyncOpenAI

from app.core.config import settings


async def main() -> int:
    if settings.llm_mode != "live":
        print("LLM_MODE is not 'live'; set LLM_MODE=live and OPENROUTER_API_KEY to check OpenRouter.")
        return 0
    if not settings.openrouter_api_key:
        print("OPENROUTER_API_KEY is not set.")
        return 1

    headers = {}
    if settings.openrouter_http_referer:
        headers["HTTP-Referer"] = settings.openrouter_http_referer
    if settings.openrouter_x_title:
        headers["X-Title"] = settings.openrouter_x_title

    client = AsyncOpenAI(
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
        default_headers=headers or None,
        timeout=settings.llm_timeout_seconds,
    )
    try:
        response = await client.chat.completions.create(
            model=settings.model_fast,
            messages=[{"role": "user", "content": "Reply with exactly: OK"}],
            max_tokens=8,
            temperature=0,
        )
        content = response.choices[0].message.content if response.choices else ""
        print("model:", settings.model_fast)
        print("response:", content)
        return 0
    except Exception as exc:
        print("OpenRouter check failed:", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
