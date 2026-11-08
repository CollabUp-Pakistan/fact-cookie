"""OpenRouter model factory for the Agents SDK."""

from __future__ import annotations

import asyncio
from functools import lru_cache

from openai import AsyncOpenAI
from agents import OpenAIChatCompletionsModel, set_default_openai_api, set_default_openai_client, set_tracing_disabled

from app.core.config import settings


_client: AsyncOpenAI | None = None
_semaphore: asyncio.Semaphore | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        headers = {}
        if settings.openrouter_http_referer:
            headers["HTTP-Referer"] = settings.openrouter_http_referer
        if settings.openrouter_x_title:
            headers["X-Title"] = settings.openrouter_x_title
        _client = AsyncOpenAI(
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
            default_headers=headers or None,
            timeout=settings.llm_timeout_seconds,
        )
    return _client


def configure_agents_sdk() -> None:
    """Configure the Agents SDK for OpenRouter chat-completions and disable default tracing export."""
    set_default_openai_api("chat_completions")
    set_default_openai_client(_get_client(), use_for_tracing=False)
    set_tracing_disabled(True)


def get_model(kind: str = "fast") -> OpenAIChatCompletionsModel:
    model_name = settings.model_fast if kind == "fast" else settings.model_strong
    return OpenAIChatCompletionsModel(model=model_name, openai_client=_get_client())


def get_model_with_fallbacks(kind: str = "fast") -> list[str]:
    primary = settings.model_fast if kind == "fast" else settings.model_strong
    fallbacks = list(settings.model_fallbacks)
    if primary not in fallbacks:
        fallbacks.insert(0, primary)
    return fallbacks


def get_semaphore() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(settings.llm_max_concurrency)
    return _semaphore
