"""Structured logging to stderr with request ids and secret redaction."""

from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any

request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)
user_id_ctx: ContextVar[str | None] = ContextVar("user_id", default=None)

_SECRET_KEYS = {
    "password",
    "password_hash",
    "api_key",
    "apikey",
    "authorization",
    "token",
    "access_token",
    "refresh_token",
    "secret",
    "secret_key",
    "openrouter_api_key",
    "tavily_api_key",
    "stripe_secret_key",
    "stripe_webhook_secret",
    "client_secret",
    "code_verifier",
}

_REDACTED = "[REDACTED]"


def redact(value: Any, depth: int = 0) -> Any:
    """Recursively redact obvious secret fields from log payloads."""
    if depth > 6:
        return "..."
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if str(key).lower() in _SECRET_KEYS:
                result[key] = _REDACTED
            else:
                result[key] = redact(item, depth + 1)
        return result
    if isinstance(value, (list, tuple)):
        return [redact(item, depth + 1) for item in value[:50]]
    if isinstance(value, str) and len(value) > 2000:
        return value[:2000] + "...[truncated]"
    return value


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = request_id_ctx.get()
        if request_id:
            payload["request_id"] = request_id
        user_id = user_id_ctx.get()
        if user_id:
            payload["user_id"] = user_id
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        extra = getattr(record, "extra_fields", None)
        if extra:
            payload.update(redact(extra))
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())
    for noisy in ("uvicorn.access", "httpx", "httpcore", "trafilatura"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def log_event(logger: logging.Logger, event: str, **fields: Any) -> None:
    logger.info(event, extra={"extra_fields": fields})
