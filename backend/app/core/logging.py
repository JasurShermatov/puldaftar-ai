"""Strukturalangan (JSON) loglar + maxfiy qiymatlarni maskalash."""
from __future__ import annotations

import contextvars
import json
import logging
import re
import sys
import time

correlation_id: contextvars.ContextVar[str] = contextvars.ContextVar("correlation_id", default="-")

_SECRET_PATTERNS = [
    re.compile(r"\d{8,10}:[A-Za-z0-9_-]{30,}"),      # telegram bot token
    re.compile(r"sk-[A-Za-z0-9_-]{16,}"),             # openai key
    re.compile(r"\b(?:\d[ -]?){16}\b"),               # karta raqami
]


def mask(text: str) -> str:
    for p in _SECRET_PATTERNS:
        text = p.sub("***", text)
    return text


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)),
            "lvl": record.levelname,
            "logger": record.name,
            "cid": correlation_id.get(),
            "msg": mask(record.getMessage()),
        }
        if record.exc_info:
            data["exc"] = mask(self.formatException(record.exc_info))
        return json.dumps(data, ensure_ascii=False)


def setup_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
    for noisy in ("httpx", "httpcore", "openai", "aiogram.event"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
