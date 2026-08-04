import logging
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


def configure_logging(app_env: str) -> None:
    """Verbose, sanitized diagnostics in development; normal INFO elsewhere."""
    development = str(app_env or "").strip().lower() == "development"
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if development else logging.INFO)
    formatter = SafeDevelopmentFormatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s" if development
        else "%(levelname)s %(name)s %(message)s"
    )
    for handler in root.handlers:
        handler.setLevel(logging.DEBUG if development else logging.INFO)
        if development:
            handler.setFormatter(formatter)
    # Avoid dumping HTTP wire data (including headers) even in development.
    logging.getLogger("httpcore").setLevel(logging.INFO)
    logging.getLogger("httpx").setLevel(logging.INFO)
