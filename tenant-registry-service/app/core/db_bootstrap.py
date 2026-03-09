import json
import logging
import time
from urllib.parse import quote, unquote, urlsplit, urlunsplit

import psycopg2
from psycopg2 import sql

from app.core.settings import get_settings

logger = logging.getLogger(__name__)


def _parse_database_name(url: str) -> str:
    split = urlsplit(url)
    raw = split.path.lstrip("/").strip()
    if not raw:
        return ""
    return unquote(raw.split("/")[0].strip())


def _build_admin_url(target_url: str) -> str:
    settings = get_settings()
    explicit = str(settings.db_bootstrap_admin_url or "").strip()
    if explicit:
        return explicit
    split = urlsplit(target_url)
    admin_db = quote(str(settings.db_bootstrap_admin_database or "postgres").strip())
    return urlunsplit((split.scheme, split.netloc, f"/{admin_db}", split.query, split.fragment))


def _ensure_database_exists(target_url: str) -> bool:
    settings = get_settings()
    db_name = _parse_database_name(target_url)
    if not db_name:
        raise RuntimeError("DATABASE_URL must include a database name")

    admin_url = _build_admin_url(target_url)
    conn = psycopg2.connect(admin_url, connect_timeout=settings.db_bootstrap_timeout_seconds)
    try:
        # CREATE DATABASE must run outside transactions.
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name,))
            exists = cur.fetchone() is not None
            if exists:
                return False
            logger.warning("Tenant Registry database '%s' not found; creating it now", db_name)
            cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(db_name)))
            logger.warning("Tenant Registry database '%s' created successfully", db_name)
            return True
    finally:
        conn.close()


def _collect_readiness_report(target_url: str) -> dict:
    settings = get_settings()
    db_name = _parse_database_name(target_url)
    report = {
        "database": db_name,
        "database_reachable": False,
        "public_schema_exists": False,
        "required_tables": {"expected_count": 1, "present_count": 0, "missing": ["tenants"]},
        "row_counts": {},
        "ready": False,
    }
    with psycopg2.connect(target_url, connect_timeout=settings.db_bootstrap_timeout_seconds) as conn:
        report["database_reachable"] = True
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 1
                FROM information_schema.schemata
                WHERE schema_name = 'public'
                """
            )
            report["public_schema_exists"] = cur.fetchone() is not None
            cur.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                """
            )
            present_tables = {str(row[0]).strip() for row in cur.fetchall()}
            has_tenants = "tenants" in present_tables
            report["required_tables"]["present_count"] = 1 if has_tenants else 0
            report["required_tables"]["missing"] = [] if has_tenants else ["tenants"]
            if has_tenants:
                cur.execute("SELECT COUNT(*) FROM public.tenants")
                report["row_counts"]["tenants"] = int(cur.fetchone()[0])
            report["ready"] = report["public_schema_exists"] and has_tenants
    return report


def ensure_registry_database_ready() -> bool:
    settings = get_settings()
    target_url = str(settings.database_url)
    attempts = max(1, int(settings.db_bootstrap_connect_retries))
    delay = max(0, int(settings.db_bootstrap_retry_delay_seconds))
    last_error: Exception | None = None

    for attempt in range(1, attempts + 1):
        try:
            if settings.db_auto_create_on_startup:
                created_now = _ensure_database_exists(target_url)
            else:
                created_now = False
            return created_now
        except Exception as exc:
            last_error = exc
            if attempt < attempts:
                logger.warning(
                    "Tenant Registry database bootstrap attempt %s/%s failed: %s",
                    attempt,
                    attempts,
                    str(exc),
                )
                if delay > 0:
                    time.sleep(delay)
                continue
            break
    raise RuntimeError(f"Tenant Registry database bootstrap failed after {attempts} attempts: {last_error}")


def log_registry_readiness(created_now: bool) -> None:
    report = _collect_readiness_report(str(get_settings().database_url))
    logger.warning(
        "Tenant Registry readiness summary before startup complete:\n%s",
        json.dumps(
            {
                "database_created_on_this_startup": bool(created_now),
                **report,
            },
            ensure_ascii=True,
            indent=2,
        ),
    )
