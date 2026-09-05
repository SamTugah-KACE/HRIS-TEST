import logging
import json
from datetime import datetime, timezone
import re
from typing import Any


_SENSITIVE = re.compile(r"(?i)(authorization|cookie|password|secret|token)=([^\s,]+)")
_EXTRA_KEYS = (
    "correlation_id", "tenant_id", "module", "operation", "status_code",
    "duration_ms", "job_id", "mode", "processed_users",
)


class SafeDevelopmentFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        rendered = super().format(record)
        rendered = _SENSITIVE.sub(r"\1=<redacted>", rendered)
        extras = []
        for key in _EXTRA_KEYS:
            value: Any = getattr(record, key, None)
            if value not in (None, ""):
                extras.append(f"{key}={value}")
        return f"{rendered} {' '.join(extras)}".rstrip()


class SafeJsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        message = _SENSITIVE.sub(r"\1=<redacted>", record.getMessage())
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "stream": getattr(record, "log_stream", "platform_system"),
            "message": message,
        }
        for key in _EXTRA_KEYS + ("method", "route", "actor_id", "actor_role", "resource_type", "resource_id", "outcome"):
            value = getattr(record, key, None)
            if value not in (None, ""):
                payload[key] = value
        if record.exc_info:
            payload["exception_type"] = record.exc_info[0].__name__ if record.exc_info[0] else "Exception"
        return json.dumps(payload, ensure_ascii=True, default=str)


def configure_logging(app_env: str) -> None:
    """Verbose, sanitized diagnostics in development; normal INFO elsewhere."""
    development = str(app_env or "").strip().lower() == "development"
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if development else logging.INFO)
    formatter = SafeDevelopmentFormatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s" if development
        else "%(levelname)s %(name)s %(message)s"
    )
    json_formatter = SafeJsonFormatter()
    for handler in root.handlers:
        handler.setLevel(logging.DEBUG if development else logging.INFO)
        handler.setFormatter(formatter if development else json_formatter)
    # Avoid dumping HTTP wire data (including headers) even in development.
    logging.getLogger("httpcore").setLevel(logging.INFO)
    logging.getLogger("httpx").setLevel(logging.INFO)
