"""Runner helpers for agent execution."""

from __future__ import annotations

from agents import RunConfig, Runner

from app.agents.llm import get_semaphore


async def run_agent(agent, input_text: str, **kwargs):
    async with get_semaphore():
        return await Runner.run(agent, input_text, run_config=RunConfig(trace_include_sensitive_data=False), **kwargs)
