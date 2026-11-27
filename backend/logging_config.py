"""
logging_config.py
------------------
Structured (JSON-line) logging setup. The one privacy-relevant behavior
here: raw customer address text is truncated/redacted by default before
it hits logs, since full addresses are personal data. Set
LOG_FULL_ADDRESS_TEXT=true in `.env` only for local debugging.
"""

import json
import logging
import sys

from config import settings


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if hasattr(record, "extra_fields"):
            payload.update(record.extra_fields)
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def redact_address(raw_address: str, max_chars: int = 12) -> str:
    """Truncate a raw address for safe logging unless full logging is
    explicitly enabled. Never logs PIN codes or unit numbers in the clear
    beyond the truncation boundary."""
    if settings.log_full_address_text:
        return raw_address
    if len(raw_address) <= max_chars:
        return raw_address[:max_chars] + "…" if raw_address else raw_address
    return raw_address[:max_chars] + f"…(+{len(raw_address) - max_chars} chars)"


def configure_logging() -> None:
    root = logging.getLogger()
    root.setLevel(settings.log_level.upper())
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.handlers = [handler]


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
