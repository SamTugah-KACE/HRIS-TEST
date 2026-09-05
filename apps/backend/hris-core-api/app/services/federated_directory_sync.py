import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path

import time
from fastapi import HTTPException

from app.clients import eappraisal_client, srms_client
from app.core.auth import AuthenticatedUser
from app.core.settings import get_settings
from app.services.keycloak_provisioning import ensure_user_and_temp_password, set_user_enabled_by_username
from app.services import automation_store
from app.services.tenant_registry_client import get_tenant_mapping, list_tenant_mappings

logger = logging.getLogger(__name__)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_probable_throttle_error(message: str) -> bool:
    text = str(message or "")
    return "Last status: 429" in text or "status: 429" in text or " 429" in text


def _is_probable_not_present_error(message: str) -> bool:
    text = str(message or "").lower()
    return "could not be resolved" in text or "inventory is empty" in text


def _norm_email(value: Any) -> str:
    return str(value or "").strip().lower()


def _norm_key(value: Any) -> str:
    text = str(value or "").strip().lower()
    return "".join(ch for ch in text if ch.isalnum() or ch in {"-", "_", "@", "."})


def _tenant_scoped_username(email: str, tenant_code: str) -> str:
    # Product identity policy: verified email is the global Keycloak username.
    # Tenant membership remains an attribute/mapping concern, not part of the login name.
    return _norm_email(email)


def _roles_from_federated_user(user: Dict[str, Any]) -> List[str]:
    """Map only well-known source roles; unknown/module-specific roles never elevate HRIS access."""
    role_values: List[str] = []
    sources = user.get("sources") if isinstance(user.get("sources"), dict) else {}
    for source in sources.values():
        claims = source.get("claims") if isinstance(source, dict) and isinstance(source.get("claims"), dict) else {}
        role_values.append(str(claims.get("role_name") or "").strip().lower())
        permissions = claims.get("permissions") if isinstance(claims.get("permissions"), list) else []
        normalized_permissions = {str(value or "").strip().lower() for value in permissions}
        if "hr:dashboard" in normalized_permissions:
            role_values.append("hr manager")
        elif "staff:dashboard" in normalized_permissions:
            role_values.append("staff")
    aliases = {
        "hr manager": "hris:hr_manager",
        "hr_manager": "hris:hr_manager",
        "tenant admin": "hris:tenant_admin",
        "tenant_admin": "hris:tenant_admin",
        "line manager": "hris:line_manager",
        "line_manager": "hris:line_manager",
        "manager": "hris:line_manager",
        "employee": "hris:employee",
        "staff": "hris:employee",
    }
    precedence = ["hris:tenant_admin", "hris:hr_manager", "hris:line_manager", "hris:employee"]
    mapped = {aliases[value] for value in role_values if value in aliases}
    return [role for role in precedence if role in mapped] or ["hris:employee"]


def _federated_user_is_active(user: Dict[str, Any]) -> bool:
    """Fail closed when any linked native account explicitly says it is inactive."""
    sources = user.get("sources") if isinstance(user.get("sources"), dict) else {}
    claims = [
        source.get("claims")
        for source in sources.values()
        if isinstance(source, dict) and isinstance(source.get("claims"), dict)
    ]
    return bool(claims) and all(bool(claim.get("is_active", True)) for claim in claims)


def _srms_effective_token(actor: AuthenticatedUser) -> Optional[str]:
    settings = get_settings()
    return actor.raw_token or settings.srms_service_token or settings.srms_integration_token


def _eappraisal_effective_token(actor: AuthenticatedUser) -> Optional[str]:
    settings = get_settings()
    return actor.raw_token or settings.eappraisal_hris_service_token or settings.eappraisal_service_token


def _safe_user_claims_from_srms(row: Dict[str, Any]) -> Dict[str, Any]:
    # Store as claims (not authoritative). Keep intentionally small.
    return {
        "email": _norm_email(row.get("email")),
        "username": str(row.get("username") or row.get("user_name") or "").strip(),
        "employee_id": str(row.get("employee_id") or row.get("staff_id") or "").strip(),
        "name": str(row.get("name") or row.get("full_name") or "").strip(),
        "is_active": bool(row.get("is_active", True)),
        "role_name": str(row.get("role") or row.get("role_name") or "").strip(),
        "permissions": list(row.get("permissions") or []) if isinstance(row.get("permissions"), list) else [],
    }


def _safe_user_claims_from_eappraisal(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "email": _norm_email(row.get("email")),
        "username": str(row.get("username") or "").strip(),
        "employee_id": str(row.get("employee_id") or row.get("staff_id") or "").strip(),
        "is_active": bool(row.get("is_active", True)),
        "role_name": str(row.get("role_name") or "").strip(),
        "permissions": list(row.get("permissions") or []) if isinstance(row.get("permissions"), list) else [],
        "is_admin": bool(row.get("is_admin", False)),
        "is_manager": bool(row.get("is_manager", False)),
    }


def _merge_user_union(
    union: Dict[str, Dict[str, Any]],
    *,
    tenant_id: str,
    module_name: str,
    module_user_id: str,
    claims: Dict[str, Any],
) -> None:
    email = _norm_email(claims.get("email"))
    employee_id = str(claims.get("employee_id") or "").strip()
    username = str(claims.get("username") or "").strip()

    # Deterministic identity key:
    # - email if present
    # - else employee_id
    # - else username
    # - else module_user_id
    primary = _norm_key(email) or _norm_key(employee_id) or _norm_key(username) or _norm_key(module_user_id)
    if not primary:
        return

    row = union.get(primary)
    if not row:
        row = {
            "tenant_id": tenant_id,
            "primary_key": primary,
            "email": email,
            "employee_id": employee_id,
            "username": username,
            "sources": {},
        }
        union[primary] = row

    sources = row.get("sources")
    if not isinstance(sources, dict):
        sources = {}
        row["sources"] = sources

    sources[module_name] = {
        "module_user_id": str(module_user_id or "").strip(),
        "claims": claims,
    }

    # Backfill stable fields if empty.
    if not row.get("email") and email:
        row["email"] = email
    if not row.get("employee_id") and employee_id:
        row["employee_id"] = employee_id
    if not row.get("username") and username:
        row["username"] = username


def build_federated_directory_snapshot_for_tenant(
    *,
    tenant_id: str,
    actor: AuthenticatedUser,
    limit_per_module: int = 2000,
    _srms_state: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    mapping = get_tenant_mapping(tenant_id)
    settings = get_settings()

    union: Dict[str, Dict[str, Any]] = {}
    source_modules: List[str] = []
    errors: List[Dict[str, str]] = []
    module_status: Dict[str, Any] = {
        "srms": {"status": "skipped", "detail": "not_attempted"},
        "eappraisal": {"status": "skipped", "detail": "not_attempted"},
        "eleave": {"status": "unsupported", "detail": "tenant_user_inventory_contract_not_implemented"},
    }
    srms_projection = automation_store.get_module_projection(
        canonical_tenant_id=tenant_id, module_name="srms"
    )
    has_srms = bool(mapping.srms_slug or mapping.srms_schema or srms_projection)

    # SRMS inventory (best-effort, may 404/429/etc).
    srms_token = _srms_effective_token(actor)
    srms_state = _srms_state or {}
    srms_throttled_until = float(srms_state.get("throttled_until_ts") or 0.0)
    srms_processed = int(srms_state.get("tenants_processed") or 0)
    if not has_srms:
        module_status["srms"] = {
            "status": "not_present", "detail": "no_native_module_projection"
        }
    elif srms_token and time.time() < srms_throttled_until:
        module_status["srms"] = {"status": "throttled", "detail": "cooldown_active"}
    elif srms_token and srms_processed >= int(settings.federated_directory_srms_max_tenants_per_run):
        module_status["srms"] = {"status": "limited", "detail": "max_tenants_per_run_reached"}
    elif srms_token:
        try:
            module_status["srms"] = {"status": "attempted", "detail": "calling_inventory"}
            payload = srms_client.list_tenant_users(
                tenant_id,
                srms_token,
                limit=max(0, int(limit_per_module)),
                tenant_slug=mapping.srms_slug,
                tenant_code=mapping.code,
            )
            users = payload.get("users", []) if isinstance(payload, dict) else []
            users = [u for u in users if isinstance(u, dict)]
            source_modules.append("srms")
            source_total = int(payload.get("total") or len(users)) if isinstance(payload, dict) else len(users)
            incomplete = source_total > len(users)
            module_status["srms"] = {
                "status": "incomplete" if incomplete else "ok",
                "detail": f"users={len(users)} total={source_total}",
            }
            if incomplete:
                errors.append({"module": "srms", "error": "upstream inventory is paginated but did not return a continuation contract"})
            srms_state["tenants_processed"] = srms_processed + 1
            for u in users:
                module_user_id = str(u.get("user_id") or u.get("employee_id") or u.get("staff_id") or u.get("id") or "").strip()
                if not module_user_id:
                    continue
                _merge_user_union(
                    union,
                    tenant_id=tenant_id,
                    module_name="srms",
                    module_user_id=module_user_id,
                    claims=_safe_user_claims_from_srms(u),
                )
        except Exception as exc:
            msg = str(exc)
            if _is_probable_throttle_error(msg):
                module_status["srms"] = {"status": "throttled", "detail": "upstream_429"}
                cooldown = max(0, int(settings.federated_directory_srms_cooldown_on_429_seconds))
                srms_state["throttled_until_ts"] = float(time.time() + cooldown)
            else:
                module_status["srms"] = {"status": "error", "detail": "upstream_error"}
                errors.append({"module": "srms", "error": msg})
    srms_state.setdefault("tenants_processed", srms_processed)

    # eAppraisal inventory (best-effort).
    eapp_token = _eappraisal_effective_token(actor)
    try:
        module_status["eappraisal"] = {"status": "attempted", "detail": "calling_inventory"}
        payload = eappraisal_client.list_integration_tenant_users(
            mapping,
            eapp_token,
            limit=max(0, int(limit_per_module)),
        )
        users = payload.get("users", []) if isinstance(payload, dict) else []
        users = [u for u in users if isinstance(u, dict)]
        source_modules.append("eappraisal")
        source_total = int(payload.get("total") or len(users)) if isinstance(payload, dict) else len(users)
        incomplete = source_total > len(users)
        module_status["eappraisal"] = {
            "status": "incomplete" if incomplete else "ok",
            "detail": f"users={len(users)} total={source_total}",
        }
        if incomplete:
            errors.append({"module": "eappraisal", "error": "upstream inventory is paginated but did not return a continuation contract"})
        for u in users:
            module_user_id = str(u.get("user_id") or u.get("id") or "").strip()
            if not module_user_id:
                continue
            _merge_user_union(
                union,
                tenant_id=tenant_id,
                module_name="eappraisal",
                module_user_id=module_user_id,
                claims=_safe_user_claims_from_eappraisal(u),
            )
    except HTTPException as exc:
        msg = str(exc.detail)
        if _is_probable_not_present_error(msg):
            module_status["eappraisal"] = {"status": "not_present", "detail": "tenant_not_in_module_inventory"}
        else:
            module_status["eappraisal"] = {"status": "error", "detail": "upstream_error"}
            errors.append({"module": "eappraisal", "error": msg})
    except Exception as exc:
        msg = str(exc)
        if _is_probable_not_present_error(msg):
            module_status["eappraisal"] = {"status": "not_present", "detail": "tenant_not_in_module_inventory"}
        else:
            module_status["eappraisal"] = {"status": "error", "detail": "upstream_error"}
            errors.append({"module": "eappraisal", "error": msg})

    # Minimal safe snapshot.
    users_list = list(union.values())
    users_total = len(users_list)
    # This field is consumed by the enrollment coordinator; truncating it to a UI-sized
    # sample silently skipped valid users. Bound it by the explicit per-module run limit.
    users_sample = users_list if int(limit_per_module or 0) <= 0 else users_list[: int(limit_per_module)]

    snapshot = {
        "scope": "federated_directory",
        "generated_at": _utc_now(),
        "tenant": {
            "tenant_id": tenant_id,
            "code": mapping.code,
            "name": mapping.name,
        },
        "module_status": module_status,
        "sources": {
            "modules": sorted(set(source_modules)),
            "limits": {"per_module": int(limit_per_module)},
        },
        "summary": {
            "users_total": users_total,
            "users_sample_count": len(users_sample),
            "errors_count": len(errors),
        },
        "errors": errors[:20],
        "users_sample": users_sample,
        "notes": {
            "read_only": True,
            "claims_are_not_authoritative": True,
            "primary_key_precedence": ["email", "employee_id", "username", "module_user_id"],
        },
    }

    if settings.enable_post_deploy_sync_automation or settings.enable_auto_sync_loop:
        # Only persist when automation features are active (keeps dev lightweight).
        try:
            automation_store.record_federated_directory_snapshot(
                scope="federated_directory",
                tenant_id=tenant_id,
                source_modules=sorted(set(source_modules)),
                users_total=users_total,
                payload=snapshot,
            )
        except Exception as exc:
            logger.warning("Federated directory snapshot persistence skipped: %s", exc)

    return snapshot


def build_federated_directory_snapshot_global(
    *,
    actor: AuthenticatedUser,
    max_tenants: int = 200,
    limit_per_module: int = 2000,
) -> Dict[str, Any]:
    settings = get_settings()
    tenants = list_tenant_mappings(limit=max(1, int(max_tenants)))
    outputs: List[Dict[str, Any]] = []
    srms_state: Dict[str, Any] = {"tenants_processed": 0, "throttled_until_ts": 0.0}
    for t in tenants:
        try:
            outputs.append(
                build_federated_directory_snapshot_for_tenant(
                    tenant_id=t.tenant_id,
                    actor=actor,
                    limit_per_module=limit_per_module,
                    _srms_state=srms_state,
                )
            )
        except Exception as exc:
            outputs.append(
                {
                    "scope": "federated_directory",
                    "generated_at": _utc_now(),
                    "tenant": {"tenant_id": t.tenant_id, "code": t.code, "name": t.name},
                    "summary": {"users_total": 0, "errors_count": 1},
                    "errors": [{"error": str(exc)}],
                    "users_sample": [],
                }
            )
    total_users = sum(int((o.get("summary") or {}).get("users_total") or 0) for o in outputs)
    return {
        "scope": "federated_directory_global",
        "generated_at": _utc_now(),
        "run_controls": {
            "srms_max_tenants_per_run": int(settings.federated_directory_srms_max_tenants_per_run),
            "srms_cooldown_on_429_seconds": int(settings.federated_directory_srms_cooldown_on_429_seconds),
        },
        "tenants_processed": len(outputs),
        "total_users_union_estimate": total_users,
        "tenants": outputs,
    }


def sync_keycloak_from_federated_directory(
    *,
    actor: AuthenticatedUser,
    tenant_id: Optional[str] = None,
    max_tenants: int = 50,
    limit_per_module: int = 2000,
    max_users: Optional[int] = None,
    dry_run_override: Optional[bool] = None,
) -> Dict[str, Any]:
    settings = get_settings()
    effective_dry_run = (
        settings.federated_keycloak_sync_dry_run if dry_run_override is None else bool(dry_run_override)
    )
    configured_limit = settings.federated_keycloak_sync_max_users_per_run if max_users is None else int(max_users)
    max_users_allowed = max(0, int(configured_limit))  # 0 means the complete discovered directory.

    if tenant_id:
        snapshot_global = {
            "scope": "federated_directory_global",
            "generated_at": _utc_now(),
            "tenants": [
                build_federated_directory_snapshot_for_tenant(
                    tenant_id=tenant_id,
                    actor=actor,
                    limit_per_module=limit_per_module,
                )
            ],
        }
    else:
        snapshot_global = build_federated_directory_snapshot_global(
            actor=actor,
            max_tenants=max_tenants,
            limit_per_module=limit_per_module,
        )

    tenants = snapshot_global.get("tenants", []) if isinstance(snapshot_global, dict) else []
    tenants = [row for row in tenants if isinstance(row, dict)]
    # Keycloak accounts are global by email. Never disable a shared account when
    # the same principal is still active in another canonical tenant; tenant-level
    # denial is handled by canonical membership enforcement.
    globally_active_usernames = {
        _norm_email(user.get("email"))
        for tenant_row in tenants
        for user in (tenant_row.get("users_sample", []) if isinstance(tenant_row.get("users_sample"), list) else [])
        if isinstance(user, dict) and _federated_user_is_active(user) and _norm_email(user.get("email"))
    }

    processed_users = 0
    created_count = 0
    existing_count = 0
    native_inactive_count = 0
    keycloak_disabled_count = 0
    skipped_missing_email = 0
    skipped_no_temporary_password = 0
    failed_count = 0
    welcome_emails_sent = 0
    welcome_emails_queued = 0
    welcome_emails_skipped = 0
    welcome_emails_failed = 0
    results: List[Dict[str, Any]] = []
    export_rows_by_tenant: Dict[str, List[Dict[str, str]]] = {}
    env_name = (settings.app_env or "").strip().lower()
    dev_credentials_export_enabled = bool(
        not effective_dry_run
        and env_name in {"development", "test"}
        and settings.onboarding_dev_credentials_export_enabled
    )
    welcome_email_enabled = bool(
        not effective_dry_run
        and settings.enable_federated_keycloak_welcome_email
    )
    email_readiness = {
        "ok": welcome_email_enabled,
        "stage": "durable_queue" if welcome_email_enabled else "disabled",
        "reason": "keycloak_action_email_dispatcher" if welcome_email_enabled else "disabled",
    }

    for tenant_row in tenants:
        t = tenant_row.get("tenant", {}) if isinstance(tenant_row.get("tenant"), dict) else {}
        t_id = str(t.get("tenant_id") or "").strip()
        t_code = str(t.get("code") or "").strip()
        users = tenant_row.get("users_sample", []) if isinstance(tenant_row, dict) else []
        users = [u for u in users if isinstance(u, dict)]
        for user in users:
            if max_users_allowed and processed_users >= max_users_allowed:
                break
            email = _norm_email(user.get("email"))
            # Email is the product username; identity mappings retain tenant/module scope.
            username = _tenant_scoped_username(email, t_code)
            if not email:
                skipped_missing_email += 1
                results.append(
                    {"tenant_id": t_id, "status": "skipped_missing_email", "email": "", "username": username}
                )
                continue
            if not _federated_user_is_active(user):
                native_inactive_count += 1
                if (username or email) in globally_active_usernames:
                    results.append({
                        "tenant_id": t_id,
                        "status": "native_inactive_shared_account",
                        "email": email,
                        "username": username,
                        "reason": "account remains active in another canonical tenant",
                    })
                    continue
                if effective_dry_run:
                    results.append({"tenant_id": t_id, "status": "would_disable_native_inactive", "email": email, "username": username})
                    continue
                try:
                    disabled = set_user_enabled_by_username(username=username or email, enabled=False)
                    if str(disabled.get("status") or "") in {"disabled", "unchanged"}:
                        keycloak_disabled_count += 1
                    results.append({
                        "tenant_id": t_id,
                        "status": "native_inactive",
                        "email": email,
                        "username": username,
                        "keycloak_status": disabled.get("status"),
                    })
                except Exception as exc:
                    failed_count += 1
                    results.append({
                        "tenant_id": t_id,
                        "status": "native_inactive_disable_failed",
                        "email": email,
                        "username": username,
                        "error": str(exc),
                    })
                continue
            # Count each valid source user exactly once, regardless of whether
            # provisioning or a later email-delivery step fails.
            processed_users += 1
            if effective_dry_run:
                results.append(
                    {"tenant_id": t_id, "status": "dry_run", "email": email, "username": username}
                )
                continue
            try:
                roles = _roles_from_federated_user(user)
                welcome_status_for_user = "not_applicable_or_already_sent"
                out = ensure_user_and_temp_password(
                    email=email,
                    username=username or email,
                    tenant_id=t_id,
                    default_role=roles[0],
                    roles=roles,
                    # Production invitations use Keycloak's expiring action link.
                    # Temporary passwords are generated only for an explicitly
                    # enabled development credential export.
                    send_temp_password=bool(dev_credentials_export_enabled),
                    # Reconciliation must never rotate an existing account's
                    # password. Existing users use the verified reset flow.
                    allow_existing_user_password_reset=False,
                )
                status_text = str(out.get("status") or "unknown")
                if status_text == "created":
                    created_count += 1
                elif status_text == "existing":
                    existing_count += 1
                user_id = str(out.get("user_id") or "").strip()
                if user_id:
                    automation_store.record_identity_mapping(
                        keycloak_issuer=str(settings.keycloak_issuer or "").rstrip("/") or None,
                        keycloak_sub=user_id,
                        tenant_id=t_id,
                        module_name="keycloak",
                        module_user_id=user_id,
                        module_username=username or email,
                        email=email,
                        source="federated_directory_sync",
                        confidence="high",
                    )
                temp_password = str(out.get("temporary_password") or "").strip()
                if dev_credentials_export_enabled:
                    if not temp_password:
                        skipped_no_temporary_password += 1
                    else:
                        export_rows_by_tenant.setdefault(t_id, []).append(
                            {
                                "tenant_id": t_id,
                                "email": email,
                                "username": username or email,
                                "temporary_password": temp_password,
                                "keycloak_user_id": user_id or "",
                                "status": status_text,
                            }
                        )
                dispatch = None
                welcome_already_sent = False
                if welcome_email_enabled:
                    try:
                        dispatch = automation_store.get_welcome_dispatch(tenant_id=t_id, email=email)
                        welcome_already_sent = bool(dispatch and dispatch.get("status") == "sent")
                    except Exception as exc:
                        logger.warning("Welcome idempotency lookup failed for %s: %s", email, exc)
                # Account existence and delivery state are separate. Legacy/imported
                # Keycloak accounts with no successful dispatch still need an invitation.
                invitation_state = (
                    "new_account" if status_text == "created" else
                    "existing_welcome_sent" if welcome_already_sent else
                    "existing_welcome_failed_retry" if dispatch else
                    "existing_no_welcome_record"
                )
                if welcome_email_enabled and not welcome_already_sent:
                    if not user_id:
                        welcome_emails_failed += 1
                        automation_store.record_welcome_dispatch(
                            tenant_id=t_id, email=email, username=username or email,
                            keycloak_user_id=user_id or None, status="failed",
                            payload={
                                "source": "federated_directory_sync",
                                "reason": "missing_keycloak_user_id",
                            },
                        )
                        results.append({
                            "tenant_id": t_id, "status": status_text, "email": email,
                            "username": username, "keycloak_user_id": user_id or None,
                            "roles": roles, "invitation_state": invitation_state,
                            "login_state": str(out.get("login_state") or "unknown"),
                            "tenant_memberships": out.get("tenant_memberships") or [t_id],
                            "multi_tenant": len(out.get("tenant_memberships") or [t_id]) > 1,
                            "welcome_status": "failed_missing_keycloak_user_id",
                        })
                        continue
                    try:
                        queued = automation_store.enqueue_keycloak_invitation(
                            tenant_id=t_id, email=email, username=username or email,
                            keycloak_user_id=user_id,
                        )
                        if str(queued.get("status")) == "sent":
                            welcome_emails_skipped += 1
                            welcome_status_for_user = "already_sent"
                        elif str(queued.get("status")) == "failed":
                            welcome_emails_failed += 1
                            welcome_status_for_user = "terminal_failure"
                        else:
                            welcome_emails_queued += 1
                            welcome_status_for_user = "queued"
                    except Exception as email_exc:
                        welcome_emails_failed += 1
                        automation_store.record_welcome_dispatch(
                            tenant_id=t_id, email=email, username=username or email,
                            keycloak_user_id=user_id or None, status="failed",
                            payload={"source": "federated_directory_sync", "error_type": type(email_exc).__name__},
                        )
                        logger.warning(
                            "Welcome email delivery failed for tenant=%s email=%s error_type=%s",
                            t_id,
                            email,
                            type(email_exc).__name__,
                        )
                elif welcome_email_enabled:
                    welcome_emails_skipped += 1
                results.append(
                    {
                        "tenant_id": t_id,
                        "status": status_text,
                        "email": email,
                        "username": username,
                        "keycloak_user_id": user_id or None,
                        "roles": roles,
                        "invitation_state": invitation_state,
                        "login_state": str(out.get("login_state") or "unknown"),
                        "tenant_memberships": out.get("tenant_memberships") or [t_id],
                        "multi_tenant": len(out.get("tenant_memberships") or [t_id]) > 1,
                        "welcome_status": welcome_status_for_user,
                    }
                )
            except Exception as exc:
                failed_count += 1
                results.append(
                    {
                        "tenant_id": t_id,
                        "status": "failed",
                        "email": email,
                        "username": username,
                        "error": str(exc),
                    }
                )
        if max_users_allowed and processed_users >= max_users_allowed:
            break

    export_paths: List[str] = []
    if dev_credentials_export_enabled and export_rows_by_tenant:
        out_dir = Path(str(settings.onboarding_dev_credentials_export_path or "data/exports")).resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        for t_id, rows in export_rows_by_tenant.items():
            if not rows:
                continue
            output_path = out_dir / f"tenant-{t_id}-dev-keycloak-credentials-{ts}.txt"
            lines = [
                "WARNING: Development-only credentials export.",
                f"tenant_id={t_id}",
                f"generated_at={datetime.now(timezone.utc).isoformat()}",
                f"records={len(rows)}",
                "",
            ]
            for row in rows:
                lines.extend(
                    [
                        f"username={row.get('username', '')}",
                        f"email={row.get('email', '')}",
                        f"temporary_password={row.get('temporary_password', '')}",
                        f"keycloak_user_id={row.get('keycloak_user_id', '')}",
                        f"status={row.get('status', '')}",
                        "",
                    ]
                )
            output_path.write_text("\n".join(lines), encoding="utf-8")
            export_paths.append(str(output_path))

    return {
        "enabled": bool(settings.enable_federated_keycloak_sync),
        "dry_run": bool(effective_dry_run),
        "max_users": max_users_allowed,
        "unlimited": max_users_allowed == 0,
        "processed_users": processed_users,
        "created_count": created_count,
        "existing_count": existing_count,
        "skipped_missing_email": skipped_missing_email,
        "native_inactive": native_inactive_count,
        "keycloak_disabled": keycloak_disabled_count,
        "skipped_no_temporary_password": skipped_no_temporary_password,
        "failed_count": failed_count,
        "welcome_emails_sent": welcome_emails_sent,
        "welcome_emails_queued": welcome_emails_queued,
        "welcome_emails_skipped": welcome_emails_skipped,
        "welcome_emails_failed": welcome_emails_failed,
        "email_readiness": email_readiness,
        "dev_credentials_exports": export_paths,
        "tenant_discovery": [
            {
                "tenant": row.get("tenant", {}),
                "summary": row.get("summary", {}),
                "module_status": row.get("module_status", {}),
                "errors": row.get("errors", []),
            }
            for row in tenants
        ],
        "results": results[:500],
    }

