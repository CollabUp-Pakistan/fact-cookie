"""Custom Agents SDK trace processor that writes JSONL traces."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agents.tracing import TracingProcessor
from agents.tracing.spans import Span
from agents.tracing.trace import Trace

from app.core.config import settings


class JsonlTraceProcessor(TracingProcessor):
    def __init__(self) -> None:
        self._path = Path(settings.llm_trace_dir) / "agent_traces.jsonl"
        self._path.parent.mkdir(parents=True, exist_ok=True)

    async def on_trace_start(self, trace: Trace) -> None:
        self._write({"event": "trace_start", "trace_id": trace.trace_id, "name": trace.name, "ts": _now()})

    async def on_trace_end(self, trace: Trace) -> None:
        self._write({"event": "trace_end", "trace_id": trace.trace_id, "name": trace.name, "ts": _now()})

    async def on_span_start(self, span: Span[Any]) -> None:
        self._write({"event": "span_start", "trace_id": span.trace_id, "span_id": span.span_id, "type": span.span_data.type, "ts": _now()})

    async def on_span_end(self, span: Span[Any]) -> None:
        self._write({"event": "span_end", "trace_id": span.trace_id, "span_id": span.span_id, "type": span.span_data.type, "ts": _now()})

    async def shutdown(self) -> None:
        return None

    async def force_flush(self) -> None:
        return None

    def _write(self, payload: dict[str, Any]) -> None:
        with self._path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, default=str) + "\n")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
