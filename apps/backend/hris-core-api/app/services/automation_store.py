import json
import re
import threading
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Optional

from app.core.settings import get_settings

_LOCK = threading.Lock()
_INITIALIZED = False


def _psycopg():
    try:
        import psycopg
        from psycopg.rows import dict_row
        return psycopg, dict_row
    except Exception as exc:
        raise RuntimeError(
            "PostgreSQL automation store requires psycopg. Install dependency: psycopg[binary]."
        ) from exc


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _db_url() -> str:
    settings = get_settings()
    url = str(settings.automation_store_database_url or "").strip()
    if not url:
        raise RuntimeError("AUTOMATION_STORE_DATABASE_URL is required for automation persistence.")
    return url


def _connect():
    psycopg, dict_row = _psycopg()
    return psycopg.connect(_db_url(), row_factory=dict_row)


def _table(name: str) -> str:
    settings = get_settings()
    schema = str(settings.automation_store_schema or "hris_automation").strip()
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", schema):
        raise RuntimeError("AUTOMATION_STORE_SCHEMA must be a valid PostgreSQL identifier.")
    return f"{schema}.{name}"


def _init_if_needed() -> None:
    global _INITIALIZED
    if _INITIALIZED:
        return
    with _LOCK:
        if _INITIALIZED:
            return
        settings = get_settings()
        schema = str(settings.automation_store_schema or "hris_automation").strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", schema):
            raise RuntimeError("AUTOMATION_STORE_SCHEMA must be a valid PostgreSQL identifier.")
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
                cur.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {_table('canonical_tenant_snapshots')} (
                        tenant_id TEXT PRIMARY KEY,
                        code TEXT NOT NULL,
                        name TEXT NOT NULL,
                        srms_schema TEXT,
                        srms_slug TEXT,
                        eappraisal_subdomain TEXT,
                        eleave_subdomain TEXT,
                        is_active BOOLEAN NOT NULL DEFAULT TRUE,
                        updated_at TIMESTAMPTZ NOT NULL
                    )
                    """
                )
                cur.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {_table('identity_mappings')} (
                        id BIGSERIAL PRIMARY KEY,
                        keycloak_sub TEXT,
                        tenant_id TEXT NOT NULL,
                        module_name TEXT NOT NULL,
                        module_user_id TEXT NOT NULL,
                        module_username TEXT,
                        email TEXT,
                        source TEXT NOT NULL,
                        confidence TEXT NOT NULL,
                        updated_at TIMESTAMPTZ NOT NULL,
                        UNIQUE (tenant_id, module_name, module_user_id)
                    )
                    """
                )
                cur.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {_table('sync_checkpoints')} (
                        id BIGSERIAL PRIMARY KEY,
                        checkpoint_type TEXT NOT NULL,
                        tenant_id TEXT,
                        payload_json JSONB NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL
                    )
                    """
                )
                cur.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {_table('provisioning_audit_store')} (
                        id BIGSERIAL PRIMARY KEY,
                        run_id TEXT,
                        tenant_id TEXT NOT NULL,
                        module_name TEXT NOT NULL,
                        employee_id TEXT,
                        email TEXT,
                        idempotency_key TEXT,
                        status TEXT NOT NULL,
                        payload_json JSONB NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL
                    )
                    """
                )
                cur.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {_table('module_probe_history')} (
                        id BIGSERIAL PRIMARY KEY,
                        tenant_id TEXT NOT NULL,
                        module_name TEXT NOT NULL,
                        ok BOOLEAN NOT NULL,
                        detail TEXT,
                        payload_json JSONB,
                        created_at TIMESTAMPTZ NOT NULL
                    )
                    """
                )
                cur.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {_table('module_handoff_replay')} (
                        jti TEXT PRIMARY KEY,
                        expires_at TIMESTAMPTZ NOT NULL,
                        payload_json JSONB NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL
                    )
                    """
                )
                cur.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {_table('drift_snapshots')} (
                        id BIGSERIAL PRIMARY KEY,
                        scope TEXT NOT NULL,
                        tenant_id TEXT,
                        payload_json JSONB NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL
                    )
                    """
                )
                cur.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {_table('federated_directory_snapshots')} (
                        id BIGSERIAL PRIMARY KEY,
                        tenant_id TEXT,
                        scope TEXT NOT NULL,
                        source_modules TEXT[] NOT NULL,
                        users_total INTEGER NOT NULL DEFAULT 0,
                        payload_json JSONB NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL
                    )
                    """
                )
                cur.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {_table('welcome_dispatch')} (
                        tenant_id TEXT NOT NULL,
                        email TEXT NOT NULL,
                        username TEXT,
                        keycloak_user_id TEXT,
                        status TEXT NOT NULL,
                        send_count INTEGER NOT NULL DEFAULT 1,
                        last_sent_at TIMESTAMPTZ NOT NULL,
                        last_payload_json JSONB NOT NULL,
                        PRIMARY KEY (tenant_id, email)
                    )
                    """
                )
                cur.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {_table('enrollment_jobs')} (
                        job_id TEXT PRIMARY KEY,
                        tenant_id TEXT,
                        mode TEXT NOT NULL,
                        requested_by TEXT NOT NULL,
                        status TEXT NOT NULL,
                        max_users INTEGER NOT NULL DEFAULT 0,
                        result_json JSONB,
                        error_message TEXT,
                        created_at TIMESTAMPTZ NOT NULL,
                        started_at TIMESTAMPTZ,
                        completed_at TIMESTAMPTZ
                    )
                    """
                )
                cur.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {_table('email_delivery_audit')} (
                        id BIGSERIAL PRIMARY KEY,
                        purpose TEXT NOT NULL,
                        tenant_id TEXT,
                        recipient_hash TEXT NOT NULL,
                        status TEXT NOT NULL,
                        provider TEXT NOT NULL,
                        detail TEXT,
                        correlation_id TEXT,
                        created_at TIMESTAMPTZ NOT NULL
                    )
                    """
                )
                cur.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {_table('tenant_runtime_settings')} (
                        tenant_id TEXT NOT NULL,
                        setting_key TEXT NOT NULL,
                        value_json JSONB NOT NULL,
                        updated_at TIMESTAMPTZ NOT NULL,
                        PRIMARY KEY (tenant_id, setting_key)
                    )
                    """
                )
                cur.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {_table('tenant_link_ledger')} (
                        id BIGSERIAL PRIMARY KEY,
                        source_tenant_id TEXT NOT NULL,
                        target_module TEXT NOT NULL,
                        target_tenant_ref TEXT,
                        decision TEXT NOT NULL,
                        evidence_json JSONB NOT NULL,
                        run_id TEXT,
                        created_at TIMESTAMPTZ NOT NULL,
                        updated_at TIMESTAMPTZ NOT NULL,
                        UNIQUE (source_tenant_id, target_module)
                    )
                    """
                )
                cur.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {_table('media_documents')} (
                        id BIGSERIAL PRIMARY KEY,
                        tenant_id TEXT NOT NULL,
                        owner_type TEXT NOT NULL,
                        owner_id TEXT NOT NULL,
                        document_key TEXT NOT NULL,
                        file_name TEXT NOT NULL,
                        content_type TEXT,
                        provider_name TEXT NOT NULL,
                        storage_uri TEXT NOT NULL,
                        file_size_bytes BIGINT NOT NULL,
                        content_hash_sha256 TEXT NOT NULL,
                        version INTEGER NOT NULL DEFAULT 1,
                        created_at TIMESTAMPTZ NOT NULL,
                        updated_at TIMESTAMPTZ NOT NULL,
                        UNIQUE (tenant_id, owner_type, owner_id, document_key)
                    )
                    """
                )
            conn.commit()
        _INITIALIZED = True


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True)


def ensure_ready() -> None:
    """
    Ensure automation persistence schema/tables exist.
    Safe to call repeatedly.
    """
    _init_if_needed()


def snapshot_tenant_mappings(rows: Iterable[Dict[str, Any]]) -> int:
    _init_if_needed()
    now = _utc_now()
    inserted = 0
    with _connect() as conn:
        for row in rows:
            tenant_id = str(row.get("tenant_id") or "").strip()
            code = str(row.get("code") or "").strip()
            name = str(row.get("name") or "").strip()
            if not tenant_id or not code or not name:
                continue
            conn.execute(
                f"""
                INSERT INTO {_table('canonical_tenant_snapshots')}
                (tenant_id, code, name, srms_schema, srms_slug, eappraisal_subdomain, eleave_subdomain, is_active, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT(tenant_id) DO UPDATE SET
                    code=excluded.code,
                    name=excluded.name,
                    srms_schema=excluded.srms_schema,
                    srms_slug=excluded.srms_slug,
                    eappraisal_subdomain=excluded.eappraisal_subdomain,
                    eleave_subdomain=excluded.eleave_subdomain,
                    is_active=excluded.is_active,
                    updated_at=excluded.updated_at
                """,
                (
                    tenant_id,
                    code,
                    name,
                    row.get("srms_schema"),
                    row.get("srms_slug"),
                    row.get("eappraisal_subdomain"),
                    row.get("eleave_subdomain"),
                    bool(row.get("is_active", True)),
                    now,
                ),
            )
            inserted += 1
        conn.commit()
    return inserted


def record_identity_mapping(
    *,
    keycloak_sub: Optional[str],
    tenant_id: str,
    module_name: str,
    module_user_id: str,
    module_username: Optional[str],
    email: Optional[str],
    source: str,
    confidence: str,
) -> None:
    _init_if_needed()
    with _connect() as conn:
        conn.execute(
            f"""
            INSERT INTO {_table('identity_mappings')}
            (keycloak_sub, tenant_id, module_name, module_user_id, module_username, email, source, confidence, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(tenant_id, module_name, module_user_id) DO UPDATE SET
                keycloak_sub=excluded.keycloak_sub,
                module_username=excluded.module_username,
                email=excluded.email,
                source=excluded.source,
                confidence=excluded.confidence,
                updated_at=excluded.updated_at
            """,
            (
                keycloak_sub,
                tenant_id,
                module_name,
                module_user_id,
                module_username,
                email,
                source,
                confidence,
                _utc_now(),
            ),
        )
        conn.commit()


def resolve_identity_mapping(
    *,
    tenant_id: str,
    module_name: str,
    keycloak_sub: Optional[str] = None,
    email: Optional[str] = None,
    username: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    _init_if_needed()
    tenant_id_value = str(tenant_id or "").strip()
    module_name_value = str(module_name or "").strip().lower()
    if not tenant_id_value or not module_name_value:
        return None

    keycloak_sub_value = str(keycloak_sub or "").strip()
    email_value = str(email or "").strip().lower()
    username_value = str(username or "").strip().lower()

    clauses = []
    args: list[Any] = [tenant_id_value, module_name_value]
    if keycloak_sub_value:
        clauses.append("keycloak_sub = %s")
        args.append(keycloak_sub_value)
    if email_value:
        clauses.append("LOWER(email) = %s")
        args.append(email_value)
    if username_value:
        clauses.append("LOWER(module_username) = %s")
        args.append(username_value)

    if not clauses:
        return None

    where_any = " OR ".join(clauses)
    with _connect() as conn:
        row = conn.execute(
            f"""
            SELECT keycloak_sub, tenant_id, module_name, module_user_id, module_username,
                   email, source, confidence, updated_at
            FROM {_table('identity_mappings')}
            WHERE tenant_id = %s
              AND module_name = %s
              AND ({where_any})
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            tuple(args),
        ).fetchone()
    return dict(row) if row else None


def resolve_identity_link(
    *,
    module_name: str,
    keycloak_sub: Optional[str] = None,
    email: Optional[str] = None,
    username: Optional[str] = None,
    preferred_tenant_id: Optional[str] = None,
    avoid_tenant_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    _init_if_needed()
    module_name_value = str(module_name or "").strip().lower()
    if not module_name_value:
        return None

    keycloak_sub_value = str(keycloak_sub or "").strip()
    email_value = str(email or "").strip().lower()
    username_value = str(username or "").strip().lower()

    clauses = []
    args: list[Any] = [module_name_value]
    if keycloak_sub_value:
        clauses.append("keycloak_sub = %s")
        args.append(keycloak_sub_value)
    if email_value:
        clauses.append("LOWER(email) = %s")
        args.append(email_value)
    if username_value:
        clauses.append("LOWER(module_username) = %s")
        args.append(username_value)
    if not clauses:
        return None

    where_any = " OR ".join(clauses)
    with _connect() as conn:
        rows = conn.execute(
            f"""
            SELECT tenant_id, module_name, module_user_id, module_username, email, keycloak_sub, source, confidence, updated_at
            FROM {_table('identity_mappings')}
            WHERE module_name = %s
              AND ({where_any})
            ORDER BY updated_at DESC
            LIMIT 20
            """,
            tuple(args),
        ).fetchall()

    if not rows:
        return None
    tenant_ids = {str(row.get("tenant_id") or "").strip() for row in rows if str(row.get("tenant_id") or "").strip()}
    if len(tenant_ids) != 1:
        preferred = str(preferred_tenant_id or "").strip()
        if preferred:
            preferred_rows = [row for row in rows if str(row.get("tenant_id") or "").strip() == preferred]
            if preferred_rows:
                return dict(preferred_rows[0])
        avoid = str(avoid_tenant_id or "").strip()
        candidate_rows = rows
        if avoid:
            non_avoid_rows = [row for row in rows if str(row.get("tenant_id") or "").strip() != avoid]
            if non_avoid_rows:
                candidate_rows = non_avoid_rows
        # Deterministic fallback for duplicated cross-tenant links:
        # if the same Keycloak principal maps to the same module user identity
        # across tenants, select the most recently updated row instead of failing auth.
        # This avoids SSO loops for migrated users while preserving strict behavior
        # for truly ambiguous identities.
        normalized_sub = keycloak_sub_value.strip().lower()
        if normalized_sub:
            same_sub_rows = [
                row
                for row in candidate_rows
                if str(row.get("keycloak_sub") or "").strip().lower() == normalized_sub
            ]
            if same_sub_rows:
                stable_user_keys = {
                    (
                        str(row.get("module_user_id") or "").strip().lower(),
                        str(row.get("module_username") or "").strip().lower(),
                        str(row.get("email") or "").strip().lower(),
                    )
                    for row in same_sub_rows
                }
                if len(stable_user_keys) == 1:
                    return dict(same_sub_rows[0])
        return None
    return dict(rows[0])


def record_checkpoint(*, checkpoint_type: str, tenant_id: Optional[str], payload: Dict[str, Any]) -> None:
    _init_if_needed()
    with _connect() as conn:
        conn.execute(
            f"""
            INSERT INTO {_table('sync_checkpoints')} (checkpoint_type, tenant_id, payload_json, created_at)
            VALUES (%s, %s, %s::jsonb, %s)
            """,
            (checkpoint_type, tenant_id, _json(payload), _utc_now()),
        )
        conn.commit()


def record_provisioning_audit(entry: Dict[str, Any]) -> None:
    _init_if_needed()
    with _connect() as conn:
        conn.execute(
            f"""
            INSERT INTO {_table('provisioning_audit_store')}
            (run_id, tenant_id, module_name, employee_id, email, idempotency_key, status, payload_json, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)
            """,
            (
                entry.get("run_id"),
                str(entry.get("tenant_id") or ""),
                str(entry.get("module") or "unknown"),
                entry.get("employee_id"),
                entry.get("email"),
                entry.get("idempotency_key"),
                str(entry.get("status") or "unknown"),
                _json(entry),
                _utc_now(),
            ),
        )
        conn.commit()


def list_provisioning_audit(
    *,
    tenant_id: Optional[str] = None,
    module_name: Optional[str] = None,
    limit: int = 100,
) -> list[Dict[str, Any]]:
    _init_if_needed()
    where_parts = []
    args: list[Any] = []
    tenant_id_value = str(tenant_id or "").strip()
    module_name_value = str(module_name or "").strip().lower()
    if tenant_id_value:
        where_parts.append("tenant_id = %s")
        args.append(tenant_id_value)
    if module_name_value:
        where_parts.append("module_name = %s")
        args.append(module_name_value)
    where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
    safe_limit = max(1, min(int(limit or 100), 500))
    with _connect() as conn:
        rows = conn.execute(
            f"""
            SELECT id, run_id, tenant_id, module_name, employee_id, email, idempotency_key, status, payload_json, created_at
            FROM {_table('provisioning_audit_store')}
            {where_sql}
            ORDER BY created_at DESC
            LIMIT {safe_limit}
            """,
            tuple(args),
        ).fetchall()
    return [dict(row) for row in rows]


def record_probe(*, tenant_id: str, module_name: str, ok: bool, detail: str, payload: Optional[Dict[str, Any]]) -> None:
    _init_if_needed()
    with _connect() as conn:
        conn.execute(
            f"""
            INSERT INTO {_table('module_probe_history')} (tenant_id, module_name, ok, detail, payload_json, created_at)
            VALUES (%s, %s, %s, %s, %s::jsonb, %s)
            """,
            (tenant_id, module_name, bool(ok), detail, _json(payload or {}), _utc_now()),
        )
        conn.commit()


def record_drift_snapshot(*, scope: str, tenant_id: Optional[str], payload: Dict[str, Any]) -> None:
    _init_if_needed()
    with _connect() as conn:
        conn.execute(
            f"""
            INSERT INTO {_table('drift_snapshots')} (scope, tenant_id, payload_json, created_at)
            VALUES (%s, %s, %s::jsonb, %s)
            """,
            (scope, tenant_id, _json(payload), _utc_now()),
        )
        conn.commit()


def record_federated_directory_snapshot(
    *,
    scope: str,
    tenant_id: Optional[str],
    source_modules: list[str],
    users_total: int,
    payload: Dict[str, Any],
) -> None:
    _init_if_needed()
    scope_value = str(scope or "").strip()
    if not scope_value:
        scope_value = "federated_directory"
    source_modules_value = [str(x or "").strip().lower() for x in (source_modules or []) if str(x or "").strip()]
    with _connect() as conn:
        conn.execute(
            f"""
            INSERT INTO {_table('federated_directory_snapshots')}
            (tenant_id, scope, source_modules, users_total, payload_json, created_at)
            VALUES (%s, %s, %s, %s, %s::jsonb, %s)
            """,
            (
                tenant_id,
                scope_value,
                source_modules_value,
                int(users_total or 0),
                _json(payload),
                _utc_now(),
            ),
        )
        conn.commit()


def get_latest_federated_directory_snapshot(
    *,
    scope: str = "federated_directory",
    tenant_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    _init_if_needed()
    scope_value = str(scope or "").strip() or "federated_directory"
    tenant_id_value = str(tenant_id or "").strip()
    where = "scope = %s"
    args: list[Any] = [scope_value]
    if tenant_id_value:
        where = where + " AND tenant_id = %s"
        args.append(tenant_id_value)
    with _connect() as conn:
        row = conn.execute(
            f"""
            SELECT id, tenant_id, scope, source_modules, users_total, payload_json, created_at
            FROM {_table('federated_directory_snapshots')}
            WHERE {where}
            ORDER BY created_at DESC
            LIMIT 1
            """,
            tuple(args),
        ).fetchone()
    return dict(row) if row else None


def was_welcome_sent(*, tenant_id: str, email: str) -> bool:
    _init_if_needed()
    with _connect() as conn:
        row = conn.execute(
            f"SELECT tenant_id FROM {_table('welcome_dispatch')} WHERE tenant_id = %s AND email = %s AND status = 'sent'",
            (tenant_id, email.lower().strip()),
        ).fetchone()
    return row is not None


def get_welcome_dispatch(*, tenant_id: str, email: str) -> Optional[Dict[str, Any]]:
    _init_if_needed()
    with _connect() as conn:
        row = conn.execute(
            f"SELECT * FROM {_table('welcome_dispatch')} WHERE tenant_id = %s AND email = %s",
            (tenant_id, email.lower().strip()),
        ).fetchone()
    return dict(row) if row else None


def create_enrollment_job(*, job_id: str, tenant_id: Optional[str], mode: str, requested_by: str, max_users: int) -> Dict[str, Any]:
    _init_if_needed()
    with _connect() as conn:
        lock_key = f"enrollment:{tenant_id or '*'}:{mode}"
        conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (lock_key,))
        existing = conn.execute(
            f"SELECT * FROM {_table('enrollment_jobs')} WHERE COALESCE(tenant_id, '')=COALESCE(%s, '') AND mode=%s AND status IN ('queued','running') ORDER BY created_at DESC LIMIT 1",
            (tenant_id, mode),
        ).fetchone()
        if existing:
            return dict(existing)
        row = conn.execute(
            f"""
            INSERT INTO {_table('enrollment_jobs')}
            (job_id, tenant_id, mode, requested_by, status, max_users, created_at)
            VALUES (%s, %s, %s, %s, 'queued', %s, %s)
            RETURNING *
            """,
            (job_id, tenant_id, mode, requested_by, max(0, int(max_users)), _utc_now()),
        ).fetchone()
        conn.commit()
    return dict(row)


def claim_next_enrollment_job() -> Optional[Dict[str, Any]]:
    """Atomically claim one job; safe when several Core/worker processes run."""
    _init_if_needed()
    with _connect() as conn:
        # Recover work abandoned by a killed/restarted worker. Individual
        # Keycloak and email operations remain idempotent.
        conn.execute(
            f"UPDATE {_table('enrollment_jobs')} SET status='queued', started_at=NULL WHERE status='running' AND started_at < NOW() - INTERVAL '1 hour'"
        )
        row = conn.execute(
            f"""
            WITH candidate AS (
                SELECT job_id FROM {_table('enrollment_jobs')}
                WHERE status = 'queued' ORDER BY created_at
                FOR UPDATE SKIP LOCKED LIMIT 1
            )
            UPDATE {_table('enrollment_jobs')} jobs
            SET status = 'running', started_at = %s
            FROM candidate WHERE jobs.job_id = candidate.job_id
            RETURNING jobs.*
            """,
            (_utc_now(),),
        ).fetchone()
        conn.commit()
    return dict(row) if row else None


def finish_enrollment_job(*, job_id: str, status: str, result: Optional[Dict[str, Any]] = None, error: Optional[str] = None) -> None:
    _init_if_needed()
    safe_error = str(error or "")[:1000] or None
    with _connect() as conn:
        conn.execute(
            f"UPDATE {_table('enrollment_jobs')} SET status=%s, result_json=%s::jsonb, error_message=%s, completed_at=%s WHERE job_id=%s",
            (status, _json(result or {}), safe_error, _utc_now(), job_id),
        )
        conn.commit()


def get_enrollment_job(job_id: str) -> Optional[Dict[str, Any]]:
    _init_if_needed()
    with _connect() as conn:
        row = conn.execute(f"SELECT * FROM {_table('enrollment_jobs')} WHERE job_id=%s", (job_id,)).fetchone()
    return dict(row) if row else None


def retry_enrollment_job(job_id: str) -> Optional[Dict[str, Any]]:
    """Retry a failed job. Running jobs are recovered only by the worker lease policy."""
    _init_if_needed()
    with _connect() as conn:
        row = conn.execute(
            f"""
            UPDATE {_table('enrollment_jobs')}
            SET status='queued', started_at=NULL, completed_at=NULL, error_message=NULL
            WHERE job_id=%s AND status='failed'
            RETURNING *
            """,
            (job_id,),
        ).fetchone()
        conn.commit()
    return dict(row) if row else None


def list_enrollment_jobs(limit: int = 50) -> list[Dict[str, Any]]:
    _init_if_needed()
    safe_limit = max(1, min(int(limit), 200))
    with _connect() as conn:
        rows = conn.execute(f"SELECT * FROM {_table('enrollment_jobs')} ORDER BY created_at DESC LIMIT {safe_limit}").fetchall()
    return [dict(row) for row in rows]


def record_email_delivery(*, purpose: str, recipient_hash: str, status: str, provider: str, tenant_id: Optional[str] = None, detail: Optional[str] = None, correlation_id: Optional[str] = None) -> None:
    _init_if_needed()
    with _connect() as conn:
        conn.execute(
            f"INSERT INTO {_table('email_delivery_audit')} (purpose, tenant_id, recipient_hash, status, provider, detail, correlation_id, created_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
            (purpose, tenant_id, recipient_hash, status, provider, str(detail or "")[:500] or None, correlation_id, _utc_now()),
        )
        conn.commit()


def list_email_delivery_audit(*, purpose: Optional[str] = None, limit: int = 100) -> list[Dict[str, Any]]:
    _init_if_needed()
    safe_limit = max(1, min(int(limit), 500))
    where, args = "", []
    if str(purpose or "").strip():
        where, args = "WHERE purpose=%s", [str(purpose).strip()]
    with _connect() as conn:
        rows = conn.execute(
            f"SELECT id,purpose,tenant_id,recipient_hash,status,provider,detail,correlation_id,created_at FROM {_table('email_delivery_audit')} {where} ORDER BY created_at DESC LIMIT {safe_limit}",
            tuple(args),
        ).fetchall()
    return [dict(row) for row in rows]


def record_welcome_dispatch(
    *,
    tenant_id: str,
    email: str,
    username: str,
    keycloak_user_id: Optional[str],
    status: str,
    payload: Dict[str, Any],
) -> None:
    _init_if_needed()
    with _connect() as conn:
        conn.execute(
            f"""
            INSERT INTO {_table('welcome_dispatch')}
            (tenant_id, email, username, keycloak_user_id, status, send_count, last_sent_at, last_payload_json)
            VALUES (%s, %s, %s, %s, %s, 1, %s, %s::jsonb)
            ON CONFLICT(tenant_id, email) DO UPDATE SET
                username=excluded.username,
                keycloak_user_id=excluded.keycloak_user_id,
                status=excluded.status,
                send_count={_table('welcome_dispatch')}.send_count + 1,
                last_sent_at=excluded.last_sent_at,
                last_payload_json=excluded.last_payload_json
            """,
            (
                tenant_id,
                email.lower().strip(),
                username,
                keycloak_user_id,
                status,
                _utc_now(),
                _json(payload),
            ),
        )
        conn.commit()


def upsert_tenant_setting(*, tenant_id: str, setting_key: str, value: Dict[str, Any]) -> None:
    _init_if_needed()
    with _connect() as conn:
        conn.execute(
            f"""
            INSERT INTO {_table('tenant_runtime_settings')}
            (tenant_id, setting_key, value_json, updated_at)
            VALUES (%s, %s, %s::jsonb, %s)
            ON CONFLICT(tenant_id, setting_key) DO UPDATE SET
                value_json=excluded.value_json,
                updated_at=excluded.updated_at
            """,
            (tenant_id, setting_key, _json(value), _utc_now()),
        )
        conn.commit()


def get_tenant_setting(*, tenant_id: str, setting_key: str) -> Optional[Dict[str, Any]]:
    _init_if_needed()
    with _connect() as conn:
        row = conn.execute(
            f"""
            SELECT value_json
            FROM {_table('tenant_runtime_settings')}
            WHERE tenant_id = %s AND setting_key = %s
            """,
            (tenant_id, setting_key),
        ).fetchone()
    if not row:
        return None
    value = row.get("value_json")
    if isinstance(value, dict):
        return value
    try:
        return json.loads(value or "{}")
    except Exception:
        return None


def list_tenant_settings_by_prefix(*, tenant_id: str, setting_key_prefix: str, limit: int = 200) -> list[Dict[str, Any]]:
    _init_if_needed()
    tenant_id_value = str(tenant_id or "").strip()
    key_prefix = str(setting_key_prefix or "").strip()
    if not tenant_id_value or not key_prefix:
        return []
    safe_limit = max(1, min(int(limit or 200), 1000))
    with _connect() as conn:
        rows = conn.execute(
            f"""
            SELECT tenant_id, setting_key, value_json, updated_at
            FROM {_table('tenant_runtime_settings')}
            WHERE tenant_id = %s AND setting_key LIKE %s
            ORDER BY updated_at DESC
            LIMIT {safe_limit}
            """,
            (tenant_id_value, f"{key_prefix}%"),
        ).fetchall()
    out: list[Dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        value = item.get("value_json")
        if not isinstance(value, dict):
            try:
                item["value_json"] = json.loads(value or "{}")
            except Exception:
                item["value_json"] = {}
        out.append(item)
    return out


def upsert_tenant_link(
    *,
    source_tenant_id: str,
    target_module: str,
    target_tenant_ref: Optional[str],
    decision: str,
    evidence: Dict[str, Any],
    run_id: Optional[str] = None,
) -> None:
    _init_if_needed()
    now = _utc_now()
    with _connect() as conn:
        conn.execute(
            f"""
            INSERT INTO {_table('tenant_link_ledger')}
            (source_tenant_id, target_module, target_tenant_ref, decision, evidence_json, run_id, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, %s)
            ON CONFLICT(source_tenant_id, target_module) DO UPDATE SET
                target_tenant_ref=excluded.target_tenant_ref,
                decision=excluded.decision,
                evidence_json=excluded.evidence_json,
                run_id=excluded.run_id,
                updated_at=excluded.updated_at
            """,
            (
                str(source_tenant_id or "").strip(),
                str(target_module or "").strip().lower(),
                str(target_tenant_ref or "").strip() or None,
                str(decision or "").strip().lower(),
                _json(evidence or {}),
                str(run_id or "").strip() or None,
                now,
                now,
            ),
        )
        conn.commit()


def get_tenant_link(*, source_tenant_id: str, target_module: str) -> Optional[Dict[str, Any]]:
    _init_if_needed()
    with _connect() as conn:
        row = conn.execute(
            f"""
            SELECT id, source_tenant_id, target_module, target_tenant_ref, decision, evidence_json, run_id, created_at, updated_at
            FROM {_table('tenant_link_ledger')}
            WHERE source_tenant_id = %s AND target_module = %s
            LIMIT 1
            """,
            (str(source_tenant_id or "").strip(), str(target_module or "").strip().lower()),
        ).fetchone()
    if not row:
        return None
    out = dict(row)
    value = out.get("evidence_json")
    if not isinstance(value, dict):
        try:
            out["evidence_json"] = json.loads(value or "{}")
        except Exception:
            out["evidence_json"] = {}
    return out


def list_tenant_links(*, source_tenant_id: str, limit: int = 50) -> list[Dict[str, Any]]:
    _init_if_needed()
    safe_limit = max(1, min(int(limit or 50), 500))
    with _connect() as conn:
        rows = conn.execute(
            f"""
            SELECT id, source_tenant_id, target_module, target_tenant_ref, decision, evidence_json, run_id, created_at, updated_at
            FROM {_table('tenant_link_ledger')}
            WHERE source_tenant_id = %s
            ORDER BY updated_at DESC
            LIMIT {safe_limit}
            """,
            (str(source_tenant_id or "").strip(),),
        ).fetchall()
    out: list[Dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        value = item.get("evidence_json")
        if not isinstance(value, dict):
            try:
                item["evidence_json"] = json.loads(value or "{}")
            except Exception:
                item["evidence_json"] = {}
        out.append(item)
    return out


def upsert_media_document(
    *,
    tenant_id: str,
    owner_type: str,
    owner_id: str,
    document_key: str,
    file_name: str,
    content_type: Optional[str],
    provider_name: str,
    storage_uri: str,
    file_size_bytes: int,
    content_hash_sha256: str,
) -> Dict[str, Any]:
    _init_if_needed()
    now = _utc_now()
    with _connect() as conn:
        row = conn.execute(
            f"""
            SELECT version
            FROM {_table('media_documents')}
            WHERE tenant_id = %s AND owner_type = %s AND owner_id = %s AND document_key = %s
            """,
            (tenant_id, owner_type, owner_id, document_key),
        ).fetchone()
        next_version = int(row.get("version") or 0) + 1 if row else 1
        conn.execute(
            f"""
            INSERT INTO {_table('media_documents')}
            (tenant_id, owner_type, owner_id, document_key, file_name, content_type, provider_name, storage_uri,
             file_size_bytes, content_hash_sha256, version, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(tenant_id, owner_type, owner_id, document_key) DO UPDATE SET
                file_name=excluded.file_name,
                content_type=excluded.content_type,
                provider_name=excluded.provider_name,
                storage_uri=excluded.storage_uri,
                file_size_bytes=excluded.file_size_bytes,
                content_hash_sha256=excluded.content_hash_sha256,
                version=excluded.version,
                updated_at=excluded.updated_at
            """,
            (
                tenant_id,
                owner_type,
                owner_id,
                document_key,
                file_name,
                content_type,
                provider_name,
                storage_uri,
                int(file_size_bytes),
                content_hash_sha256,
                next_version,
                now,
                now,
            ),
        )
        conn.commit()
    return {
        "tenant_id": tenant_id,
        "owner_type": owner_type,
        "owner_id": owner_id,
        "document_key": document_key,
        "provider_name": provider_name,
        "storage_uri": storage_uri,
        "version": next_version,
    }


def get_media_document(
    *,
    tenant_id: str,
    owner_type: str,
    owner_id: str,
    document_key: str,
) -> Optional[Dict[str, Any]]:
    _init_if_needed()
    with _connect() as conn:
        row = conn.execute(
            f"""
            SELECT tenant_id, owner_type, owner_id, document_key, file_name, content_type, provider_name,
                   storage_uri, file_size_bytes, content_hash_sha256, version, created_at, updated_at
            FROM {_table('media_documents')}
            WHERE tenant_id = %s AND owner_type = %s AND owner_id = %s AND document_key = %s
            """,
            (tenant_id, owner_type, owner_id, document_key),
        ).fetchone()
    return dict(row) if row else None


def claim_module_handoff_jti(*, jti: str, exp: int, payload: Dict[str, Any]) -> bool:
    """
    Claim a handoff token id once using the shared automation database.

    Returns False when the jti was already redeemed. Expired rows are pruned opportunistically.
    """
    _init_if_needed()
    now = _utc_now()
    expires_at = datetime.fromtimestamp(int(exp), timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(f"DELETE FROM {_table('module_handoff_replay')} WHERE expires_at <= NOW()")
        row = conn.execute(
            f"""
            INSERT INTO {_table('module_handoff_replay')}
                (jti, expires_at, payload_json, created_at)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (jti) DO NOTHING
            RETURNING jti
            """,
            (jti, expires_at, json.dumps(payload), now),
        ).fetchone()
        conn.commit()
    return bool(row)
