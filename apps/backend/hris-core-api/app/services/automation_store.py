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
                        keycloak_issuer TEXT,
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
                cur.execute(f"ALTER TABLE {_table('identity_mappings')} ADD COLUMN IF NOT EXISTS keycloak_issuer TEXT")
                cur.execute(
                    f"""
                    CREATE INDEX IF NOT EXISTS identity_mapping_principal_idx
                    ON {_table('identity_mappings')} (keycloak_issuer, keycloak_sub, tenant_id)
                    WHERE keycloak_sub IS NOT NULL
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
                    CREATE TABLE IF NOT EXISTS {_table('module_handoff_codes')} (
                        code_hash TEXT PRIMARY KEY,
                        module_id TEXT NOT NULL,
                        tenant_id TEXT NOT NULL,
                        expires_at TIMESTAMPTZ NOT NULL,
                        payload_json JSONB NOT NULL,
                        consumed_at TIMESTAMPTZ,
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
                cur.execute(f"ALTER TABLE {_table('welcome_dispatch')} ADD COLUMN IF NOT EXISTS attempt_count INTEGER NOT NULL DEFAULT 0")
                cur.execute(f"ALTER TABLE {_table('welcome_dispatch')} ADD COLUMN IF NOT EXISTS next_attempt_at TIMESTAMPTZ")
                cur.execute(f"ALTER TABLE {_table('welcome_dispatch')} ADD COLUMN IF NOT EXISTS lease_started_at TIMESTAMPTZ")
                cur.execute(f"ALTER TABLE {_table('welcome_dispatch')} ADD COLUMN IF NOT EXISTS error_category TEXT")
                cur.execute(f"ALTER TABLE {_table('welcome_dispatch')} ADD COLUMN IF NOT EXISTS provider_status INTEGER")
                cur.execute(
                    f"CREATE INDEX IF NOT EXISTS welcome_dispatch_queue_idx ON {_table('welcome_dispatch')} (status, next_attempt_at)"
                )
                cur.execute(
                    f"""CREATE TABLE IF NOT EXISTS {_table('email_provider_state')} (
                        provider TEXT PRIMARY KEY,
                        circuit_open_until TIMESTAMPTZ,
                        reason TEXT,
                        updated_at TIMESTAMPTZ NOT NULL
                    )"""
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
                    CREATE UNIQUE INDEX IF NOT EXISTS tenant_link_target_identity_uq
                    ON {_table('tenant_link_ledger')} (target_module, target_tenant_ref)
                    WHERE target_tenant_ref IS NOT NULL
                    """
                )
                cur.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {_table('native_tenant_inventory')} (
                        module_name TEXT NOT NULL,
                        native_tenant_id TEXT NOT NULL,
                        reported_canonical_tenant_id TEXT,
                        display_name TEXT NOT NULL,
                        normalized_name TEXT NOT NULL,
                        routing_key TEXT,
                        source_version TEXT,
                        source_updated_at TIMESTAMPTZ,
                        inventory_status TEXT NOT NULL DEFAULT 'unclaimed',
                        metadata_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                        first_seen_at TIMESTAMPTZ NOT NULL,
                        last_seen_at TIMESTAMPTZ NOT NULL,
                        PRIMARY KEY (module_name, native_tenant_id)
                    )
                    """
                )
                cur.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {_table('tenant_module_projections')} (
                        canonical_tenant_id TEXT NOT NULL,
                        module_name TEXT NOT NULL,
                        native_tenant_id TEXT,
                        state TEXT NOT NULL,
                        routing_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                        link_version BIGINT NOT NULL DEFAULT 1,
                        last_verified_at TIMESTAMPTZ,
                        created_at TIMESTAMPTZ NOT NULL,
                        updated_at TIMESTAMPTZ NOT NULL,
                        PRIMARY KEY (canonical_tenant_id, module_name),
                        UNIQUE (module_name, native_tenant_id)
                    )
                    """
                )
                cur.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {_table('tenant_link_claims')} (
                        claim_id UUID PRIMARY KEY,
                        canonical_tenant_id TEXT NOT NULL,
                        module_name TEXT NOT NULL,
                        native_tenant_id TEXT NOT NULL,
                        state TEXT NOT NULL,
                        reason TEXT NOT NULL,
                        initiated_by TEXT NOT NULL,
                        approved_by TEXT,
                        challenge_hash TEXT,
                        assertion_hash TEXT,
                        expected_link_version BIGINT,
                        expires_at TIMESTAMPTZ,
                        created_at TIMESTAMPTZ NOT NULL,
                        decided_at TIMESTAMPTZ,
                        updated_at TIMESTAMPTZ NOT NULL
                    )
                    """
                )
                cur.execute(
                    f"""
                    CREATE UNIQUE INDEX IF NOT EXISTS tenant_link_claim_open_uq
                    ON {_table('tenant_link_claims')} (canonical_tenant_id, module_name, native_tenant_id)
                    WHERE state IN ('candidate_review', 'verification_pending', 'native_confirmed')
                    """
                )
                cur.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {_table('tenant_link_events')} (
                        event_id UUID PRIMARY KEY,
                        claim_id UUID,
                        canonical_tenant_id TEXT NOT NULL,
                        module_name TEXT NOT NULL,
                        native_tenant_id TEXT,
                        actor_sub TEXT NOT NULL,
                        action TEXT NOT NULL,
                        before_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                        after_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                        correlation_id TEXT,
                        created_at TIMESTAMPTZ NOT NULL
                    )
                    """
                )
                cur.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {_table('tenant_memberships')} (
                        keycloak_issuer TEXT NOT NULL,
                        keycloak_sub TEXT NOT NULL,
                        canonical_tenant_id TEXT NOT NULL,
                        status TEXT NOT NULL,
                        source TEXT NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL,
                        updated_at TIMESTAMPTZ NOT NULL,
                        PRIMARY KEY (keycloak_issuer, keycloak_sub, canonical_tenant_id)
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
                cur.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {_table('auth_sessions')} (
                        session_hash TEXT PRIMARY KEY,
                        token_ciphertext TEXT NOT NULL,
                        subject TEXT,
                        tenant_id TEXT,
                        refresh_fingerprint TEXT,
                        user_agent_hash TEXT,
                        created_at TIMESTAMPTZ NOT NULL,
                        last_seen_at TIMESTAMPTZ NOT NULL,
                        expires_at TIMESTAMPTZ NOT NULL,
                        revoked_at TIMESTAMPTZ
                    )
                    """
                )
                cur.execute(
                    f"CREATE INDEX IF NOT EXISTS auth_sessions_expiry_idx ON {_table('auth_sessions')} (expires_at)"
                )
                cur.execute(
                    f"""CREATE TABLE IF NOT EXISTS {_table('recovery_directory')} (
                        user_id TEXT PRIMARY KEY,
                        tenant_id TEXT NOT NULL,
                        username TEXT NOT NULL,
                        role_class TEXT NOT NULL,
                        active BOOLEAN NOT NULL DEFAULT TRUE,
                        lookup_hashes_json JSONB NOT NULL,
                        phone_ciphertext TEXT,
                        email_ciphertext TEXT,
                        phone_verified_at TIMESTAMPTZ,
                        email_verified_at TIMESTAMPTZ,
                        second_factor_enrolled BOOLEAN NOT NULL DEFAULT FALSE,
                        updated_at TIMESTAMPTZ NOT NULL
                    )"""
                )
                cur.execute(
                    f"""CREATE TABLE IF NOT EXISTS {_table('recovery_challenges')} (
                        challenge_hash TEXT PRIMARY KEY,
                        user_id TEXT,
                        tenant_id TEXT,
                        provider TEXT,
                        destination_ciphertext TEXT,
                        provider_reference TEXT,
                        attempts INTEGER NOT NULL DEFAULT 0,
                        status TEXT NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL,
                        expires_at TIMESTAMPTZ NOT NULL,
                        consumed_at TIMESTAMPTZ
                    )"""
                )
                cur.execute(
                    f"""CREATE TABLE IF NOT EXISTS {_table('recovery_sessions')} (
                        session_hash TEXT PRIMARY KEY,
                        user_id TEXT NOT NULL,
                        tenant_id TEXT NOT NULL,
                        username TEXT NOT NULL,
                        role_class TEXT NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL,
                        expires_at TIMESTAMPTZ NOT NULL,
                        revoked_at TIMESTAMPTZ
                    )"""
                )
                cur.execute(
                    f"""CREATE TABLE IF NOT EXISTS {_table('tenant_domains')} (
                        hostname TEXT PRIMARY KEY,
                        tenant_id TEXT NOT NULL,
                        domain_type TEXT NOT NULL,
                        status TEXT NOT NULL,
                        verification_hash TEXT,
                        redirect_hostname TEXT,
                        created_at TIMESTAMPTZ NOT NULL,
                        verified_at TIMESTAMPTZ,
                        updated_at TIMESTAMPTZ NOT NULL
                    )"""
                )
                cur.execute(
                    f"CREATE INDEX IF NOT EXISTS tenant_domains_tenant_idx ON {_table('tenant_domains')} (tenant_id,status)"
                )
                cur.execute(
                    f"""CREATE TABLE IF NOT EXISTS {_table('tenant_activity_audit')} (
                        id BIGSERIAL PRIMARY KEY,
                        tenant_id TEXT NOT NULL,
                        actor_id TEXT,
                        actor_role TEXT,
                        action TEXT NOT NULL,
                        resource_type TEXT,
                        resource_id TEXT,
                        outcome TEXT NOT NULL,
                        correlation_id TEXT,
                        detail_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                        previous_hash TEXT,
                        integrity_hash TEXT NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL
                    )"""
                )
                cur.execute(
                    f"CREATE INDEX IF NOT EXISTS tenant_activity_audit_query_idx ON {_table('tenant_activity_audit')} (tenant_id,created_at DESC)"
                )
            conn.commit()
        _INITIALIZED = True


def _json(value: Any) -> str:
    # Audit/event payloads can contain UUID and timezone-aware datetime values
    # returned by psycopg.  Persist their stable textual representation rather
    # than letting an otherwise successful atomic workflow fail during audit.
    return json.dumps(value, ensure_ascii=True, default=str)


def ensure_ready() -> None:
    """
    Ensure automation persistence schema/tables exist.
    Safe to call repeatedly.
    """
    _init_if_needed()


def create_auth_session(
    *, session_hash: str, token_ciphertext: str, subject: Optional[str], tenant_id: Optional[str],
    refresh_fingerprint: Optional[str], user_agent_hash: Optional[str], expires_at: str,
) -> None:
    _init_if_needed()
    now = _utc_now()
    with _connect() as conn:
        conn.execute(f"DELETE FROM {_table('auth_sessions')} WHERE expires_at <= NOW() OR revoked_at IS NOT NULL")
        conn.execute(
            f"""INSERT INTO {_table('auth_sessions')}
            (session_hash,token_ciphertext,subject,tenant_id,refresh_fingerprint,user_agent_hash,created_at,last_seen_at,expires_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (session_hash, token_ciphertext, subject, tenant_id, refresh_fingerprint, user_agent_hash, now, now, expires_at),
        )
        conn.commit()


def get_auth_session(*, session_hash: str) -> Optional[Dict[str, Any]]:
    _init_if_needed()
    with _connect() as conn:
        row = conn.execute(
            f"""SELECT * FROM {_table('auth_sessions')}
            WHERE session_hash=%s AND revoked_at IS NULL AND expires_at > NOW()""",
            (session_hash,),
        ).fetchone()
        if row:
            conn.execute(
                f"UPDATE {_table('auth_sessions')} SET last_seen_at=%s WHERE session_hash=%s",
                (_utc_now(), session_hash),
            )
            conn.commit()
    return dict(row) if row else None


def revoke_auth_session(*, session_hash: str) -> None:
    _init_if_needed()
    with _connect() as conn:
        conn.execute(
            f"UPDATE {_table('auth_sessions')} SET revoked_at=%s WHERE session_hash=%s",
            (_utc_now(), session_hash),
        )
        conn.commit()


def upsert_recovery_user(*, row: Dict[str, Any]) -> None:
    _init_if_needed()
    with _connect() as conn:
        conn.execute(
            f"""INSERT INTO {_table('recovery_directory')}
            (user_id,tenant_id,username,role_class,active,lookup_hashes_json,phone_ciphertext,email_ciphertext,
             phone_verified_at,email_verified_at,second_factor_enrolled,updated_at)
            VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s,%s)
            ON CONFLICT(user_id) DO UPDATE SET
              tenant_id=excluded.tenant_id,username=excluded.username,role_class=excluded.role_class,
              active=excluded.active,lookup_hashes_json=excluded.lookup_hashes_json,
              phone_ciphertext=excluded.phone_ciphertext,email_ciphertext=excluded.email_ciphertext,
              phone_verified_at=excluded.phone_verified_at,email_verified_at=excluded.email_verified_at,
              second_factor_enrolled=excluded.second_factor_enrolled,updated_at=excluded.updated_at""",
            (
                row["user_id"], row["tenant_id"], row["username"], row["role_class"], bool(row.get("active", True)),
                _json(row.get("lookup_hashes", [])), row.get("phone_ciphertext"), row.get("email_ciphertext"),
                row.get("phone_verified_at"), row.get("email_verified_at"), bool(row.get("second_factor_enrolled")), _utc_now(),
            ),
        )
        conn.commit()


def find_recovery_user(*, lookup_hash: str) -> Optional[Dict[str, Any]]:
    _init_if_needed()
    with _connect() as conn:
        row = conn.execute(
            f"""SELECT * FROM {_table('recovery_directory')}
            WHERE active=TRUE AND lookup_hashes_json ? %s LIMIT 1""",
            (lookup_hash,),
        ).fetchone()
    return dict(row) if row else None


def get_recovery_user_by_id(*, user_id: str) -> Optional[Dict[str, Any]]:
    _init_if_needed()
    with _connect() as conn:
        row = conn.execute(
            f"SELECT * FROM {_table('recovery_directory')} WHERE user_id=%s AND active=TRUE",
            (user_id,),
        ).fetchone()
    return dict(row) if row else None


def create_recovery_challenge(*, row: Dict[str, Any]) -> None:
    _init_if_needed()
    with _connect() as conn:
        if row.get("user_id"):
            conn.execute(
                f"UPDATE {_table('recovery_challenges')} SET status='superseded' WHERE user_id=%s AND status='pending'",
                (row["user_id"],),
            )
        conn.execute(
            f"""INSERT INTO {_table('recovery_challenges')}
            (challenge_hash,user_id,tenant_id,provider,destination_ciphertext,provider_reference,attempts,status,created_at,expires_at)
            VALUES (%s,%s,%s,%s,%s,%s,0,'pending',%s,%s)""",
            (row["challenge_hash"], row.get("user_id"), row.get("tenant_id"), row.get("provider"),
             row.get("destination_ciphertext"), row.get("provider_reference"), _utc_now(), row["expires_at"]),
        )
        conn.commit()


def get_recovery_challenge(*, challenge_hash: str) -> Optional[Dict[str, Any]]:
    _init_if_needed()
    with _connect() as conn:
        row = conn.execute(
            f"""SELECT * FROM {_table('recovery_challenges')}
            WHERE challenge_hash=%s AND status='pending' AND expires_at > NOW()""",
            (challenge_hash,),
        ).fetchone()
    return dict(row) if row else None


def increment_recovery_attempt(*, challenge_hash: str, consume: bool = False) -> None:
    _init_if_needed()
    with _connect() as conn:
        conn.execute(
            f"""UPDATE {_table('recovery_challenges')}
            SET attempts=attempts+1,status=CASE WHEN %s THEN 'consumed' ELSE status END,
                consumed_at=CASE WHEN %s THEN %s::timestamptz ELSE consumed_at END
            WHERE challenge_hash=%s""",
            (consume, consume, _utc_now(), challenge_hash),
        )
        conn.commit()


def create_recovery_session(*, row: Dict[str, Any]) -> None:
    _init_if_needed()
    with _connect() as conn:
        conn.execute(
            f"""INSERT INTO {_table('recovery_sessions')}
            (session_hash,user_id,tenant_id,username,role_class,created_at,expires_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s)""",
            (row["session_hash"],row["user_id"],row["tenant_id"],row["username"],row["role_class"],_utc_now(),row["expires_at"]),
        )
        conn.commit()


def get_recovery_session(*, session_hash: str) -> Optional[Dict[str, Any]]:
    _init_if_needed()
    with _connect() as conn:
        row = conn.execute(
            f"""SELECT * FROM {_table('recovery_sessions')}
            WHERE session_hash=%s AND revoked_at IS NULL AND expires_at > NOW()""",
            (session_hash,),
        ).fetchone()
    return dict(row) if row else None


def revoke_recovery_session(*, session_hash: str) -> None:
    _init_if_needed()
    with _connect() as conn:
        conn.execute(
            f"UPDATE {_table('recovery_sessions')} SET revoked_at=%s WHERE session_hash=%s",
            (_utc_now(), session_hash),
        )
        conn.commit()


def upsert_tenant_domain(*, hostname: str, tenant_id: str, domain_type: str, status: str, verification_hash: Optional[str]) -> None:
    _init_if_needed()
    now = _utc_now()
    with _connect() as conn:
        conn.execute(
            f"""INSERT INTO {_table('tenant_domains')}
            (hostname,tenant_id,domain_type,status,verification_hash,created_at,updated_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT(hostname) DO UPDATE SET tenant_id=excluded.tenant_id,domain_type=excluded.domain_type,
              status=excluded.status,verification_hash=excluded.verification_hash,updated_at=excluded.updated_at""",
            (hostname,tenant_id,domain_type,status,verification_hash,now,now),
        )
        conn.commit()


def verify_tenant_domain(*, hostname: str) -> None:
    _init_if_needed()
    with _connect() as conn:
        conn.execute(
            f"UPDATE {_table('tenant_domains')} SET status='verified',verified_at=%s,updated_at=%s WHERE hostname=%s",
            (_utc_now(),_utc_now(),hostname),
        )
        conn.commit()


def get_tenant_domain(*, hostname: str) -> Optional[Dict[str, Any]]:
    _init_if_needed()
    with _connect() as conn:
        row = conn.execute(
            f"SELECT * FROM {_table('tenant_domains')} WHERE hostname=%s",
            (hostname,),
        ).fetchone()
    return dict(row) if row else None


def list_tenant_domains(*, tenant_id: str) -> list[Dict[str, Any]]:
    _init_if_needed()
    with _connect() as conn:
        rows = conn.execute(
            f"SELECT hostname,domain_type,status,redirect_hostname,created_at,verified_at,updated_at FROM {_table('tenant_domains')} WHERE tenant_id=%s ORDER BY created_at",
            (tenant_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def append_tenant_audit(*, row: Dict[str, Any]) -> Dict[str, Any]:
    _init_if_needed()
    now = _utc_now()
    with _connect() as conn:
        previous = conn.execute(
            f"SELECT integrity_hash FROM {_table('tenant_activity_audit')} WHERE tenant_id=%s ORDER BY id DESC LIMIT 1 FOR UPDATE",
            (row["tenant_id"],),
        ).fetchone()
        previous_hash = str((previous or {}).get("integrity_hash") or "")
        canonical = _json({
            "tenant_id": row["tenant_id"], "actor_id": row.get("actor_id"), "action": row["action"],
            "resource_type": row.get("resource_type"), "resource_id": row.get("resource_id"),
            "outcome": row.get("outcome", "success"), "correlation_id": row.get("correlation_id"),
            "detail": row.get("detail", {}), "created_at": now, "previous_hash": previous_hash,
        })
        import hashlib
        integrity_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        inserted = conn.execute(
            f"""INSERT INTO {_table('tenant_activity_audit')}
            (tenant_id,actor_id,actor_role,action,resource_type,resource_id,outcome,correlation_id,detail_json,previous_hash,integrity_hash,created_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s) RETURNING id""",
            (row["tenant_id"],row.get("actor_id"),row.get("actor_role"),row["action"],row.get("resource_type"),
             row.get("resource_id"),row.get("outcome","success"),row.get("correlation_id"),_json(row.get("detail",{})),
             previous_hash or None,integrity_hash,now),
        ).fetchone()
        conn.commit()
    return {"id": inserted["id"], "integrity_hash": integrity_hash, "created_at": now}


def list_tenant_audit(*, tenant_id: str, limit: int = 100) -> list[Dict[str, Any]]:
    _init_if_needed()
    safe_limit = max(1, min(500, int(limit)))
    with _connect() as conn:
        rows = conn.execute(
            f"""SELECT id,tenant_id,actor_id,actor_role,action,resource_type,resource_id,outcome,correlation_id,
            detail_json,integrity_hash,created_at FROM {_table('tenant_activity_audit')}
            WHERE tenant_id=%s ORDER BY created_at DESC LIMIT %s""",
            (tenant_id,safe_limit),
        ).fetchall()
    return [dict(row) for row in rows]


def try_acquire_scheduler_lock(lock_key: int = 824_731_119):
    """Return the owning connection, or None when another replica owns it."""
    _init_if_needed()
    conn = _connect()
    row = conn.execute("SELECT pg_try_advisory_lock(%s) AS acquired", (int(lock_key),)).fetchone()
    if not row or not bool(row.get("acquired")):
        conn.close()
        return None
    return conn


def release_scheduler_lock(conn, lock_key: int = 824_731_119) -> None:
    if conn is None:
        return
    try:
        conn.execute("SELECT pg_advisory_unlock(%s)", (int(lock_key),))
    finally:
        conn.close()


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
    keycloak_issuer: Optional[str] = None,
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
            (keycloak_issuer, keycloak_sub, tenant_id, module_name, module_user_id, module_username, email, source, confidence, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(tenant_id, module_name, module_user_id) DO UPDATE SET
                keycloak_issuer=excluded.keycloak_issuer,
                keycloak_sub=excluded.keycloak_sub,
                module_username=excluded.module_username,
                email=excluded.email,
                source=excluded.source,
                confidence=excluded.confidence,
                updated_at=excluded.updated_at
            """,
            (
                str(keycloak_issuer or "").strip() or None,
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
    keycloak_issuer: Optional[str] = None,
    keycloak_sub: Optional[str] = None,
    email: Optional[str] = None,
    username: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    _init_if_needed()
    tenant_id_value = str(tenant_id or "").strip()
    module_name_value = str(module_name or "").strip().lower()
    if not tenant_id_value or not module_name_value:
        return None

    keycloak_issuer_value = str(keycloak_issuer or "").strip()
    keycloak_sub_value = str(keycloak_sub or "").strip()
    email_value = str(email or "").strip().lower()
    username_value = str(username or "").strip().lower()

    clauses = []
    args: list[Any] = [tenant_id_value, module_name_value]
    if keycloak_sub_value:
        if keycloak_issuer_value:
            clauses.append("(keycloak_issuer = %s AND keycloak_sub = %s)")
            args.extend([keycloak_issuer_value, keycloak_sub_value])
        else:
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
    keycloak_issuer: Optional[str] = None,
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

    keycloak_issuer_value = str(keycloak_issuer or "").strip()
    keycloak_sub_value = str(keycloak_sub or "").strip()
    email_value = str(email or "").strip().lower()
    username_value = str(username or "").strip().lower()

    clauses = []
    args: list[Any] = [module_name_value]
    if keycloak_sub_value:
        if keycloak_issuer_value:
            clauses.append("(keycloak_issuer = %s AND keycloak_sub = %s)")
            args.extend([keycloak_issuer_value, keycloak_sub_value])
        else:
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
            SELECT tenant_id, module_name, module_user_id, module_username, email,
                   keycloak_issuer, keycloak_sub, source, confidence, updated_at
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
        # Never choose a tenant from recency or matching profile attributes.
        # An ambiguous principal-to-tenant relationship must be explicitly
        # resolved through canonical membership administration.
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


def enqueue_keycloak_invitation(
    *, tenant_id: str, email: str, username: str, keycloak_user_id: str,
) -> Dict[str, Any]:
    """Durably queue one invitation while preserving successful idempotency."""
    _init_if_needed()
    now = _utc_now()
    with _connect() as conn:
        provider_state = conn.execute(
            f"SELECT circuit_open_until FROM {_table('email_provider_state')} WHERE provider='keycloak_smtp'"
        ).fetchone()
        eligible_at = (
            provider_state.get("circuit_open_until")
            if provider_state and provider_state.get("circuit_open_until")
            else now
        )
        row = conn.execute(
            f"""
            INSERT INTO {_table('welcome_dispatch')}
              (tenant_id,email,username,keycloak_user_id,status,send_count,last_sent_at,
               last_payload_json,attempt_count,next_attempt_at,lease_started_at,error_category,provider_status)
            VALUES (%s,%s,%s,%s,'pending',0,%s,%s::jsonb,0,%s,NULL,NULL,NULL)
            ON CONFLICT(tenant_id,email) DO UPDATE SET
              username=excluded.username,
              keycloak_user_id=excluded.keycloak_user_id,
              status=CASE WHEN {_table('welcome_dispatch')}.status IN ('sent','failed') THEN {_table('welcome_dispatch')}.status ELSE 'pending' END,
              next_attempt_at=CASE WHEN {_table('welcome_dispatch')}.status IN ('sent','failed') THEN NULL ELSE excluded.next_attempt_at END,
              lease_started_at=NULL,
              error_category=CASE WHEN {_table('welcome_dispatch')}.status IN ('sent','failed') THEN {_table('welcome_dispatch')}.error_category ELSE NULL END,
              provider_status=CASE WHEN {_table('welcome_dispatch')}.status IN ('sent','failed') THEN {_table('welcome_dispatch')}.provider_status ELSE NULL END,
              last_payload_json=CASE WHEN {_table('welcome_dispatch')}.status IN ('sent','failed') THEN {_table('welcome_dispatch')}.last_payload_json ELSE excluded.last_payload_json END
            RETURNING *
            """,
            (tenant_id, email.lower().strip(), username, keycloak_user_id, now,
             _json({"source": "federated_directory_sync", "delivery": "keycloak_action_email"}), eligible_at),
        ).fetchone()
        conn.commit()
    return dict(row)


def claim_next_keycloak_invitation() -> Optional[Dict[str, Any]]:
    _init_if_needed()
    now = _utc_now()
    with _connect() as conn:
        conn.execute(
            f"""UPDATE {_table('welcome_dispatch')}
                SET status='retry_wait', next_attempt_at=%s, lease_started_at=NULL,
                    error_category='abandoned_worker_lease'
                WHERE status='sending' AND lease_started_at < NOW() - INTERVAL '10 minutes'""",
            (now,),
        )
        row = conn.execute(
            f"""
            WITH candidate AS (
              SELECT tenant_id,email FROM {_table('welcome_dispatch')}
              WHERE status IN ('pending','retry_wait')
                AND COALESCE(next_attempt_at,NOW()) <= NOW()
                AND NOT EXISTS (
                  SELECT 1 FROM {_table('email_provider_state')}
                  WHERE provider='keycloak_smtp' AND circuit_open_until > NOW()
                )
                AND (
                  SELECT count(*) FROM {_table('welcome_dispatch')}
                  WHERE status='sent' AND last_sent_at >= date_trunc('day',NOW())
                ) < %s
              ORDER BY COALESCE(next_attempt_at,last_sent_at),tenant_id,email
              FOR UPDATE SKIP LOCKED LIMIT 1
            )
            UPDATE {_table('welcome_dispatch')} dispatch
            SET status='sending', lease_started_at=%s, attempt_count=attempt_count+1
            FROM candidate
            WHERE dispatch.tenant_id=candidate.tenant_id AND dispatch.email=candidate.email
            RETURNING dispatch.*
            """,
            (int(get_settings().invitation_dispatch_daily_limit), now),
        ).fetchone()
        conn.commit()
    return dict(row) if row else None


def finish_keycloak_invitation(
    *, tenant_id: str, email: str, status: str, payload: Dict[str, Any],
    next_attempt_at: Optional[str] = None, error_category: Optional[str] = None,
    provider_status: Optional[int] = None,
) -> None:
    _init_if_needed()
    now = _utc_now()
    with _connect() as conn:
        conn.execute(
            f"""UPDATE {_table('welcome_dispatch')}
                SET status=%s, send_count=send_count+CASE WHEN %s='sent' THEN 1 ELSE 0 END,
                    last_sent_at=%s,last_payload_json=%s::jsonb,next_attempt_at=%s,
                    lease_started_at=NULL,error_category=%s,provider_status=%s
                WHERE tenant_id=%s AND email=%s""",
            (status, status, now, _json(payload), next_attempt_at, error_category,
             provider_status, tenant_id, email.lower().strip()),
        )
        conn.commit()


def defer_pending_keycloak_invitations(*, next_attempt_at: str, error_category: str) -> int:
    """Open a provider-wide circuit breaker after transient SMTP/Keycloak failure."""
    _init_if_needed()
    with _connect() as conn:
        conn.execute(
            f"""INSERT INTO {_table('email_provider_state')}
                (provider,circuit_open_until,reason,updated_at)
                VALUES ('keycloak_smtp',%s,%s,%s)
                ON CONFLICT(provider) DO UPDATE SET
                  circuit_open_until=GREATEST({_table('email_provider_state')}.circuit_open_until,excluded.circuit_open_until),
                  reason=excluded.reason,updated_at=excluded.updated_at""",
            (next_attempt_at, error_category, _utc_now()),
        )
        result = conn.execute(
            f"""UPDATE {_table('welcome_dispatch')}
                SET next_attempt_at=GREATEST(COALESCE(next_attempt_at,NOW()),%s),
                    error_category=COALESCE(error_category,%s)
                WHERE status IN ('pending','retry_wait')""",
            (next_attempt_at, error_category),
        )
        conn.commit()
    return int(result.rowcount or 0)


def get_keycloak_invitation_queue_summary() -> Dict[str, Any]:
    _init_if_needed()
    with _connect() as conn:
        rows = conn.execute(
            f"SELECT status,count(*) AS count FROM {_table('welcome_dispatch')} GROUP BY status ORDER BY status"
        ).fetchall()
        next_row = conn.execute(
            f"""SELECT min(next_attempt_at) AS next_attempt_at
                FROM {_table('welcome_dispatch')}
                WHERE status IN ('pending','retry_wait')"""
        ).fetchone()
        provider = conn.execute(
            f"SELECT circuit_open_until,reason,updated_at FROM {_table('email_provider_state')} WHERE provider='keycloak_smtp'"
        ).fetchone()
    return {
        "counts": {str(row["status"]): int(row["count"]) for row in rows},
        "next_attempt_at": next_row.get("next_attempt_at") if next_row else None,
        "provider_circuit": dict(provider) if provider else None,
    }


def retry_failed_keycloak_invitations(*, limit: int = 100) -> int:
    """Explicitly reset terminal failures; never invoked automatically."""
    _init_if_needed()
    safe_limit = max(1, min(int(limit), 1000))
    now = _utc_now()
    with _connect() as conn:
        result = conn.execute(
            f"""WITH candidates AS (
                  SELECT tenant_id,email FROM {_table('welcome_dispatch')}
                  WHERE status='failed' ORDER BY last_sent_at LIMIT %s
                  FOR UPDATE SKIP LOCKED
                )
                UPDATE {_table('welcome_dispatch')} dispatch
                SET status='pending',attempt_count=0,next_attempt_at=%s,lease_started_at=NULL,
                    error_category=NULL,provider_status=NULL
                FROM candidates
                WHERE dispatch.tenant_id=candidates.tenant_id AND dispatch.email=candidates.email""",
            (safe_limit, now),
        )
        conn.commit()
    return int(result.rowcount or 0)


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


def upsert_native_tenant_inventory(
    *, module_name: str, native_tenant_id: str, reported_canonical_tenant_id: Optional[str],
    display_name: str, normalized_name: str, routing_key: Optional[str],
    source_version: Optional[str], source_updated_at: Optional[str], metadata: Dict[str, Any],
    inventory_status: str = "unclaimed",
) -> Dict[str, Any]:
    """Store module inventory without creating or linking a canonical tenant."""
    _init_if_needed()
    now = _utc_now()
    with _connect() as conn:
        row = conn.execute(
            f"""
            INSERT INTO {_table('native_tenant_inventory')}
              (module_name, native_tenant_id, reported_canonical_tenant_id, display_name,
               normalized_name, routing_key, source_version, source_updated_at,
               inventory_status, metadata_json, first_seen_at, last_seen_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s)
            ON CONFLICT(module_name, native_tenant_id) DO UPDATE SET
              reported_canonical_tenant_id=excluded.reported_canonical_tenant_id,
              display_name=excluded.display_name, normalized_name=excluded.normalized_name,
              routing_key=excluded.routing_key, source_version=excluded.source_version,
              source_updated_at=excluded.source_updated_at,
              inventory_status=CASE
                WHEN native_tenant_inventory.inventory_status='claimed' THEN 'claimed'
                ELSE excluded.inventory_status END,
              metadata_json=excluded.metadata_json,
              last_seen_at=excluded.last_seen_at
            RETURNING *
            """,
            (module_name.strip().lower(), native_tenant_id.strip(),
             str(reported_canonical_tenant_id or "").strip() or None, display_name.strip(),
             normalized_name.strip(), str(routing_key or "").strip() or None,
             str(source_version or "").strip() or None, source_updated_at,
             inventory_status.strip().lower(),
             _json(metadata), now, now),
        ).fetchone()
        conn.commit()
    return dict(row)


def list_native_tenant_inventory(
    *, module_name: Optional[str] = None, inventory_status: Optional[str] = None, limit: int = 500,
) -> list[Dict[str, Any]]:
    _init_if_needed()
    clauses, args = [], []
    if module_name:
        clauses.append("module_name = %s")
        args.append(module_name.strip().lower())
    if inventory_status:
        clauses.append("inventory_status = %s")
        args.append(inventory_status.strip().lower())
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    safe_limit = max(1, min(int(limit), 2000))
    with _connect() as conn:
        rows = conn.execute(
            f"SELECT * FROM {_table('native_tenant_inventory')} {where} ORDER BY last_seen_at DESC LIMIT {safe_limit}",
            tuple(args),
        ).fetchall()
    return [dict(row) for row in rows]


def mark_native_tenant_inventory_for_review(*, module_name: str, native_tenant_id: str) -> None:
    """Remove a stale trusted state when its canonical Registry record is absent."""
    _init_if_needed()
    with _connect() as conn:
        conn.execute(
            f"UPDATE {_table('native_tenant_inventory')} "
            "SET inventory_status='unclaimed' WHERE module_name=%s AND native_tenant_id=%s",
            (module_name.strip().lower(), native_tenant_id.strip()),
        )
        conn.commit()


def get_module_projection(*, canonical_tenant_id: str, module_name: str) -> Optional[Dict[str, Any]]:
    _init_if_needed()
    with _connect() as conn:
        row = conn.execute(
            f"SELECT * FROM {_table('tenant_module_projections')} WHERE canonical_tenant_id=%s AND module_name=%s",
            (canonical_tenant_id.strip(), module_name.strip().lower()),
        ).fetchone()
    return dict(row) if row else None


def upsert_module_projection(
    *, canonical_tenant_id: str, module_name: str, native_tenant_id: Optional[str],
    state: str, routing: Dict[str, Any], verified: bool = False,
) -> Dict[str, Any]:
    _init_if_needed()
    now = _utc_now()
    with _connect() as conn:
        row = conn.execute(
            f"""
            INSERT INTO {_table('tenant_module_projections')}
              (canonical_tenant_id,module_name,native_tenant_id,state,routing_json,link_version,last_verified_at,created_at,updated_at)
            VALUES (%s,%s,%s,%s,%s::jsonb,1,%s,%s,%s)
            ON CONFLICT(canonical_tenant_id,module_name) DO UPDATE SET
              native_tenant_id=excluded.native_tenant_id, state=excluded.state,
              routing_json=excluded.routing_json,
              link_version=tenant_module_projections.link_version + 1,
              last_verified_at=excluded.last_verified_at, updated_at=excluded.updated_at
            RETURNING *
            """,
            (canonical_tenant_id.strip(), module_name.strip().lower(),
             str(native_tenant_id or "").strip() or None, state.strip().lower(),
             _json(routing), now if verified else None, now, now),
        ).fetchone()
        conn.commit()
    return dict(row)


def append_tenant_link_event(
    *, event_id: str, claim_id: Optional[str], canonical_tenant_id: str,
    module_name: str, native_tenant_id: Optional[str], actor_sub: str, action: str,
    before: Dict[str, Any], after: Dict[str, Any], correlation_id: Optional[str],
) -> None:
    _init_if_needed()
    with _connect() as conn:
        conn.execute(
            f"""INSERT INTO {_table('tenant_link_events')}
            (event_id,claim_id,canonical_tenant_id,module_name,native_tenant_id,actor_sub,action,before_json,after_json,correlation_id,created_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s)""",
            (event_id, claim_id, canonical_tenant_id, module_name.lower(), native_tenant_id,
             actor_sub, action, _json(before), _json(after), correlation_id, _utc_now()),
        )
        conn.commit()


def create_tenant_link_claim(
    *, claim_id: str, canonical_tenant_id: str, module_name: str, native_tenant_id: str,
    reason: str, initiated_by: str, challenge_hash: str, expires_at: str,
    expected_link_version: Optional[int],
) -> Dict[str, Any]:
    _init_if_needed()
    now = _utc_now()
    with _connect() as conn:
        row = conn.execute(
            f"""INSERT INTO {_table('tenant_link_claims')}
            (claim_id,canonical_tenant_id,module_name,native_tenant_id,state,reason,initiated_by,
             challenge_hash,expected_link_version,expires_at,created_at,updated_at)
            VALUES (%s,%s,%s,%s,'verification_pending',%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
            (claim_id, canonical_tenant_id, module_name.lower(), native_tenant_id, reason,
             initiated_by, challenge_hash, expected_link_version, expires_at, now, now),
        ).fetchone()
        conn.commit()
    return dict(row)


def get_tenant_link_claim(*, claim_id: str) -> Optional[Dict[str, Any]]:
    _init_if_needed()
    with _connect() as conn:
        row = conn.execute(f"SELECT * FROM {_table('tenant_link_claims')} WHERE claim_id=%s", (claim_id,)).fetchone()
    return dict(row) if row else None


def list_tenant_link_claims(*, state: Optional[str] = None, limit: int = 200) -> list[Dict[str, Any]]:
    _init_if_needed()
    safe_limit = max(1, min(int(limit), 1000))
    with _connect() as conn:
        if state:
            rows = conn.execute(
                f"SELECT * FROM {_table('tenant_link_claims')} WHERE state=%s ORDER BY created_at DESC LIMIT {safe_limit}",
                (state.lower(),),
            ).fetchall()
        else:
            rows = conn.execute(f"SELECT * FROM {_table('tenant_link_claims')} ORDER BY created_at DESC LIMIT {safe_limit}").fetchall()
    return [dict(row) for row in rows]


def update_tenant_link_claim(
    *, claim_id: str, expected_state: str, new_state: str, approved_by: Optional[str] = None,
    assertion_hash: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    _init_if_needed()
    now = _utc_now()
    terminal = new_state in {"approved", "rejected", "cancelled", "expired"}
    with _connect() as conn:
        row = conn.execute(
            f"""UPDATE {_table('tenant_link_claims')} SET state=%s,
            approved_by=COALESCE(%s,approved_by), assertion_hash=COALESCE(%s,assertion_hash),
            decided_at=CASE WHEN %s THEN %s ELSE decided_at END, updated_at=%s
            WHERE claim_id=%s AND state=%s RETURNING *""",
            (new_state, approved_by, assertion_hash, terminal, now, now, claim_id, expected_state),
        ).fetchone()
        conn.commit()
    return dict(row) if row else None


def approve_tenant_link_claim(
    *, claim_id: str, approved_by: str, correlation_id: Optional[str], event_id: str,
    require_second_approver: bool = True,
) -> Dict[str, Any]:
    """Atomically approve a native-confirmed claim and activate its projection."""
    _init_if_needed()
    now = _utc_now()
    with _connect() as conn:
        with conn.transaction():
            claim = conn.execute(
                f"SELECT * FROM {_table('tenant_link_claims')} WHERE claim_id=%s FOR UPDATE",
                (claim_id,),
            ).fetchone()
            if not claim:
                raise ValueError("claim_not_found")
            if claim["state"] != "native_confirmed":
                raise ValueError("claim_not_native_confirmed")
            if require_second_approver and str(claim["initiated_by"]) == str(approved_by):
                raise ValueError("second_approver_required")
            if claim.get("expires_at") and claim["expires_at"] <= datetime.now(timezone.utc):
                raise ValueError("claim_expired")
            projection = conn.execute(
                f"SELECT * FROM {_table('tenant_module_projections')} WHERE canonical_tenant_id=%s AND module_name=%s FOR UPDATE",
                (claim["canonical_tenant_id"], claim["module_name"]),
            ).fetchone()
            expected = claim.get("expected_link_version")
            if expected is not None and int((projection or {}).get("link_version") or 0) != int(expected):
                raise ValueError("projection_version_conflict")
            conflicting = conn.execute(
                f"""SELECT canonical_tenant_id FROM {_table('tenant_module_projections')}
                WHERE module_name=%s AND native_tenant_id=%s AND canonical_tenant_id<>%s FOR UPDATE""",
                (claim["module_name"], claim["native_tenant_id"], claim["canonical_tenant_id"]),
            ).fetchone()
            if conflicting:
                raise ValueError("native_tenant_already_linked")
            routing_row = conn.execute(
                f"SELECT routing_key FROM {_table('native_tenant_inventory')} WHERE module_name=%s AND native_tenant_id=%s FOR UPDATE",
                (claim["module_name"], claim["native_tenant_id"]),
            ).fetchone()
            if not routing_row:
                raise ValueError("native_inventory_not_found")
            before = dict(projection) if projection else {}
            routing = {"routing_key": routing_row.get("routing_key")}
            updated_projection = conn.execute(
                f"""INSERT INTO {_table('tenant_module_projections')}
                (canonical_tenant_id,module_name,native_tenant_id,state,routing_json,link_version,last_verified_at,created_at,updated_at)
                VALUES (%s,%s,%s,'verified',%s::jsonb,1,%s,%s,%s)
                ON CONFLICT(canonical_tenant_id,module_name) DO UPDATE SET
                  native_tenant_id=excluded.native_tenant_id,state='verified',routing_json=excluded.routing_json,
                  link_version=tenant_module_projections.link_version+1,
                  last_verified_at=excluded.last_verified_at,updated_at=excluded.updated_at
                RETURNING *""",
                (claim["canonical_tenant_id"], claim["module_name"], claim["native_tenant_id"],
                 _json(routing), now, now, now),
            ).fetchone()
            conn.execute(
                f"UPDATE {_table('native_tenant_inventory')} SET inventory_status='claimed', last_seen_at=last_seen_at WHERE module_name=%s AND native_tenant_id=%s",
                (claim["module_name"], claim["native_tenant_id"]),
            )
            approved = conn.execute(
                f"""UPDATE {_table('tenant_link_claims')} SET state='approved',approved_by=%s,decided_at=%s,updated_at=%s
                WHERE claim_id=%s RETURNING *""",
                (approved_by, now, now, claim_id),
            ).fetchone()
            conn.execute(
                f"""INSERT INTO {_table('tenant_link_events')}
                (event_id,claim_id,canonical_tenant_id,module_name,native_tenant_id,actor_sub,action,before_json,after_json,correlation_id,created_at)
                VALUES (%s,%s,%s,%s,%s,%s,'claim.approved',%s::jsonb,%s::jsonb,%s,%s)""",
                (event_id, claim_id, claim["canonical_tenant_id"], claim["module_name"],
                 claim["native_tenant_id"], approved_by, _json(before), _json(dict(updated_projection)),
                 correlation_id, now),
            )
    return {"claim": dict(approved), "projection": dict(updated_projection)}


def upsert_tenant_membership(
    *, keycloak_issuer: str, keycloak_sub: str, canonical_tenant_id: str, status: str, source: str,
) -> None:
    _init_if_needed()
    now = _utc_now()
    with _connect() as conn:
        conn.execute(
            f"""INSERT INTO {_table('tenant_memberships')}
            (keycloak_issuer,keycloak_sub,canonical_tenant_id,status,source,created_at,updated_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT(keycloak_issuer,keycloak_sub,canonical_tenant_id) DO UPDATE SET
              status=excluded.status, source=excluded.source, updated_at=excluded.updated_at""",
            (keycloak_issuer, keycloak_sub, canonical_tenant_id, status, source, now, now),
        )
        conn.commit()


def get_tenant_membership(*, keycloak_issuer: str, keycloak_sub: str, canonical_tenant_id: str) -> Optional[Dict[str, Any]]:
    _init_if_needed()
    with _connect() as conn:
        row = conn.execute(
            f"SELECT * FROM {_table('tenant_memberships')} WHERE keycloak_issuer=%s AND keycloak_sub=%s AND canonical_tenant_id=%s",
            (keycloak_issuer, keycloak_sub, canonical_tenant_id),
        ).fetchone()
    return dict(row) if row else None


def resolve_principal_tenant(
    *, keycloak_issuer: str, keycloak_sub: str, preferred_tenant_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Resolve a canonical tenant from active membership, never profile labels."""
    _init_if_needed()
    issuer = str(keycloak_issuer or "").rstrip("/")
    subject = str(keycloak_sub or "").strip()
    if not issuer or not subject:
        return None
    with _connect() as conn:
        rows = conn.execute(
            f"""SELECT canonical_tenant_id, status, source, updated_at
            FROM {_table('tenant_memberships')}
            WHERE keycloak_issuer=%s AND keycloak_sub=%s AND status='active'
            ORDER BY updated_at DESC""",
            (issuer, subject),
        ).fetchall()
    if not rows:
        return None
    preferred = str(preferred_tenant_id or "").strip()
    if preferred:
        row = next((item for item in rows if str(item["canonical_tenant_id"]) == preferred), None)
        if row:
            return {"tenant_id": str(row["canonical_tenant_id"]), "source": "canonical_membership"}
    tenant_ids = {str(item["canonical_tenant_id"]) for item in rows}
    if len(tenant_ids) != 1:
        return None
    return {"tenant_id": next(iter(tenant_ids)), "source": "canonical_membership"}


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


def create_module_handoff_code(*, code_hash: str, payload: Dict[str, Any]) -> None:
    _init_if_needed()
    expires_at = datetime.fromtimestamp(int(payload["exp"]), timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(f"DELETE FROM {_table('module_handoff_codes')} WHERE expires_at <= NOW()")
        conn.execute(
            f"""INSERT INTO {_table('module_handoff_codes')}
                (code_hash,module_id,tenant_id,expires_at,payload_json,created_at)
                VALUES (%s,%s,%s,%s,%s,%s)""",
            (code_hash, str(payload["aud"]), str(payload["tenant_id"]), expires_at,
             json.dumps(payload), _utc_now()),
        )
        conn.commit()


def consume_module_handoff_code(*, code_hash: str) -> Optional[Dict[str, Any]]:
    """Atomically consume one unexpired opaque code; concurrent replays return no row."""
    _init_if_needed()
    with _connect() as conn:
        row = conn.execute(
            f"""UPDATE {_table('module_handoff_codes')}
                SET consumed_at=%s
                WHERE code_hash=%s AND consumed_at IS NULL AND expires_at>NOW()
                RETURNING payload_json""",
            (_utc_now(), code_hash),
        ).fetchone()
        conn.commit()
    if not row:
        return None
    payload = row.get("payload_json") if isinstance(row, dict) else row[0]
    return payload if isinstance(payload, dict) else json.loads(payload)
