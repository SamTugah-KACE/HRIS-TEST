import logging
import time
import json
from urllib.parse import quote, unquote, urlsplit, urlunsplit

from app.core.settings import get_settings
from app.services import automation_store

logger = logging.getLogger(__name__)


def _requires_automation_store() -> bool:
    settings = get_settings()
    return bool(
        (settings.automation_store_database_url or "").strip()
        or settings.module_handoff_enabled
        or settings.enable_post_deploy_sync_automation
        or settings.enable_auto_sync_loop
        or settings.onboarding_welcome_email_enabled
        or settings.post_deploy_welcome_emails_enabled
    )


def _parse_database_name(url: str) -> str:
    split = urlsplit(url)
    raw = split.path.lstrip("/").strip()
    if not raw:
        return ""
    return unquote(raw.split("/")[0].strip())


def _build_admin_url(target_url: str) -> str:
    settings = get_settings()
    explicit = (settings.db_bootstrap_admin_url or "").strip()
    if explicit:
        return explicit
    split = urlsplit(target_url)
    admin_db = quote(str(settings.db_bootstrap_admin_database or "postgres").strip())
    admin_path = f"/{admin_db}"
    return urlunsplit((split.scheme, split.netloc, admin_path, split.query, split.fragment))


def _connect(url: str, *, timeout_seconds: int):
    import psycopg
    from psycopg.rows import dict_row

    return psycopg.connect(url, connect_timeout=timeout_seconds, row_factory=dict_row)


def _is_missing_database_error(exc: Exception, db_name: str) -> bool:
    message = str(exc).lower()
    if "does not exist" in message and "database" in message:
        return True
    if db_name and db_name.lower() in message and "unknown database" in message:
        return True
    return False


def _ensure_database_exists(target_url: str) -> bool:
    settings = get_settings()
    db_name = _parse_database_name(target_url)
    if not db_name:
        raise RuntimeError("AUTOMATION_STORE_DATABASE_URL must include a database name")
    admin_url = _build_admin_url(target_url)

    from psycopg import sql

    with _connect(admin_url, timeout_seconds=settings.db_bootstrap_timeout_seconds) as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name,))
            exists = cur.fetchone() is not None
            if exists:
                return False
            logger.warning("Automation database '%s' not found; creating it now", db_name)
            cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(db_name)))
            logger.warning("Automation database '%s' created successfully", db_name)
            return True


def _required_automation_tables() -> list[str]:
    return [
        "canonical_tenant_snapshots",
        "identity_mappings",
        "sync_checkpoints",
        "provisioning_audit_store",
        "module_probe_history",
        "module_handoff_replay",
        "module_handoff_codes",
        "drift_snapshots",
        "federated_directory_snapshots",
        "welcome_dispatch",
        "email_provider_state",
        "enrollment_jobs",
        "email_delivery_audit",
        "tenant_runtime_settings",
        "tenant_link_ledger",
        "native_tenant_inventory",
        "tenant_module_projections",
        "tenant_link_claims",
        "tenant_link_events",
        "tenant_memberships",
        "media_documents",
        "auth_sessions",
        "recovery_directory",
        "recovery_challenges",
        "recovery_sessions",
        "tenant_domains",
        "tenant_activity_audit",
    ]


def _collect_database_readiness_report(target_url: str) -> dict:
    settings = get_settings()
    schema = str(settings.automation_store_schema or "hris_automation").strip()
    db_name = _parse_database_name(target_url)
    report: dict = {
        "database": db_name,
        "automation_schema": schema,
        "database_reachable": False,
        "schema_exists": False,
        "required_tables": {},
        "row_counts": {},
        "ready": False,
    }
    with _connect(target_url, timeout_seconds=settings.db_bootstrap_timeout_seconds) as conn:
        report["database_reachable"] = True
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 1
                FROM information_schema.schemata
                WHERE schema_name = %s
                """,
                (schema,),
            )
            report["schema_exists"] = cur.fetchone() is not None
            cur.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = %s
                """,
                (schema,),
            )
            present_tables = {str(row.get("table_name") or "").strip() for row in cur.fetchall()}
            required_tables = _required_automation_tables()
            missing = [table for table in required_tables if table not in present_tables]
            report["required_tables"] = {
                "expected_count": len(required_tables),
                "present_count": len([table for table in required_tables if table in present_tables]),
                "missing": missing,
            }

            from psycopg import sql

            for table in required_tables:
                if table not in present_tables:
                    continue
                cur.execute(
                    sql.SQL("SELECT COUNT(*) AS c FROM {}.{}").format(
                        sql.Identifier(schema),
                        sql.Identifier(table),
                    )
                )
                row = cur.fetchone() or {}
                report["row_counts"][table] = int(row.get("c") or 0)
            report["ready"] = report["schema_exists"] and not missing
    return report


def ensure_runtime_databases_ready() -> dict:
    settings = get_settings()
    if not _requires_automation_store():
        logger.warning(
            "Database readiness check skipped because automation persistence features are disabled"
        )
        return {
            "database_created_on_this_startup": False,
            "ready": True,
            "skipped": True,
        }
    target_url = str(settings.automation_store_database_url or "").strip()
    if not target_url:
        raise RuntimeError("AUTOMATION_STORE_DATABASE_URL is required for enabled automation services")

    attempts = max(1, int(settings.db_bootstrap_connect_retries))
    delay = max(0, int(settings.db_bootstrap_retry_delay_seconds))
    last_error: Exception | None = None

    for attempt in range(1, attempts + 1):
        try:
            created_now = _ensure_database_exists(target_url)
            automation_store.ensure_ready()
            readiness_report = _collect_database_readiness_report(target_url)
            logger.warning(
                "Database readiness summary before startup complete:\n%s",
                json.dumps(
                    {
                        "database_created_on_this_startup": bool(created_now),
                        **readiness_report,
                    },
                    ensure_ascii=True,
                    indent=2,
                ),
            )
            logger.warning("Database health bootstrap completed for automation persistence")
            return {
                "database_created_on_this_startup": bool(created_now),
                **readiness_report,
            }
        except Exception as exc:
            last_error = exc
            should_retry = attempt < attempts
            if _is_missing_database_error(exc, _parse_database_name(target_url)) and settings.db_auto_create_on_startup:
                try:
                    created_now = _ensure_database_exists(target_url)
                    automation_store.ensure_ready()
                    readiness_report = _collect_database_readiness_report(target_url)
                    logger.warning(
                        "Database auto-created and initialized successfully before startup complete:\n%s",
                        json.dumps(
                            {
                                "database_created_on_this_startup": bool(created_now),
                                **readiness_report,
                            },
                            ensure_ascii=True,
                            indent=2,
                        ),
                    )
                    return {
                        "database_created_on_this_startup": bool(created_now),
                        **readiness_report,
                    }
                except Exception as create_exc:
                    last_error = create_exc
            if should_retry:
                logger.warning(
                    "Database bootstrap attempt %s/%s failed: %s",
                    attempt,
                    attempts,
                    str(last_error),
                )
                if delay > 0:
                    time.sleep(delay)
                continue
            break

    raise RuntimeError(f"Database bootstrap failed after {attempts} attempt(s): {last_error}")
