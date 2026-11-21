"""
Structured JSON log formatter for production.

Produces one JSON object per log record with consistent fields:
    timestamp, level, logger, message, request_id (if present),
    and any extra fields passed via the `extra` kwarg.

Sensitive fields (password, token, secret, key, authorization)
are automatically masked to prevent credential leakage in logs.
"""
from __future__ import annotations

import json
import logging
import traceback
from datetime import datetime, timezone


_SENSITIVE_KEYS = frozenset(
    {"password", "token", "secret", "key", "authorization", "database_url", "redis_url"}
)


def _mask_sensitive(data: dict) -> dict:
    """Recursively mask sensitive key values."""
    masked = {}
    for k, v in data.items():
        if any(s in k.lower() for s in _SENSITIVE_KEYS):
            masked[k] = "***MASKED***"
        elif isinstance(v, dict):
            masked[k] = _mask_sensitive(v)
        else:
            masked[k] = v
    return masked


class JsonFormatter(logging.Formatter):
    """JSON log formatter — one JSON object per line."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Include extra fields (passed via `extra={}` in logging calls)
        for key, value in record.__dict__.items():
            if key not in {
                "name", "msg", "args", "levelname", "levelno", "pathname",
                "filename", "module", "exc_info", "exc_text", "stack_info",
                "lineno", "funcName", "created", "msecs", "relativeCreated",
                "thread", "threadName", "processName", "process", "message",
                "taskName",
            }:
                log_entry[key] = value

        # Attach exception info if present
        if record.exc_info:
            log_entry["exception"] = traceback.format_exception(*record.exc_info)

        # Mask sensitive fields
        log_entry = _mask_sensitive(log_entry)

        return json.dumps(log_entry, default=str)
