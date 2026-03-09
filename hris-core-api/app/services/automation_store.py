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


def was_welcome_sent(*, tenant_id: str, email: str) -> bool:
    _init_if_needed()
    with _connect() as conn:
        row = conn.execute(
            f"SELECT tenant_id FROM {_table('welcome_dispatch')} WHERE tenant_id = %s AND email = %s",
            (tenant_id, email.lower().strip()),
        ).fetchone()
    return row is not None


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
