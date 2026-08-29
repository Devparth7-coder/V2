"""
VayuSutra APIx - Structured Logging & Request-ID Context
Provides a structured JSON-style logger and a request-id context used by middleware.
"""
import json
import logging
import sys
import threading
import uuid
from typing import Any, Dict


class StructuredFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        base = {
            "ts": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        ctx = getattr(record, "context", None) or {}
        if isinstance(ctx, dict):
            base.update(ctx)
        if record.exc_info:
            base["exc"] = self.formatException(record.exc_info)
        return json.dumps(base, default=str)


def setup_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(StructuredFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)


# --- Request-ID context ----------------------------------------------------
_request_ctx = threading.local()


def get_request_id() -> str:
    return getattr(_request_ctx, "request_id", "")


def set_request_id(request_id: str) -> None:
    _request_ctx.request_id = request_id


def new_request_id() -> str:
    return uuid.uuid4().hex[:16]


def log_with_context(logger: logging.Logger, level: str, msg: str, **context: Any) -> None:
    extra = {"context": {"request_id": get_request_id(), **context}}
    getattr(logger, level)(msg, extra=extra)
