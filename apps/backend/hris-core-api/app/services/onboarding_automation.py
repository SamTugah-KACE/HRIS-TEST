from datetime import datetime, timezone
import logging
import json
from typing import Any, Dict, List, Tuple
import hashlib
from pathlib import Path

from fastapi import HTTPException
from app.clients import srms_client
from app.core.auth import AuthenticatedUser
from app.core.settings import get_settings
from app.services import automation_store
from app.services.keycloak_provisioning import ensure_user_and_temp_password
from app.services.tenant_inventory_import import import_missing_tenants_from_srms
from app.services.tenant_branding_service import get_tenant_branding
from app.services.tenant_registry_client import get_tenant_mapping, list_tenant_mappings
from app.services.welcome_email_service import send_welcome_email

logger = logging.getLogger(__name__)

_HRIS_ROLE_PRIORITY: List[str] = [
    "hris:super_admin",
    "hris:tenant_admin",
    "hris:hr_manager",
    "hris:line_manager",
    "hris:employee",
]

def _idem_key(*, tenant_id: str, email: str, purpose: str) -> str:
    raw = f"{tenant_id}|{email.lower().strip()}|{purpose}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:48]


def _keycloak_admin_is_configured() -> bool:
    settings = get_settings()
    has_client_creds = bool(
        (settings.keycloak_admin_client_id or "").strip()
        and (settings.keycloak_admin_client_secret or "").strip()
    )
    has_password_creds = bool(
        (settings.keycloak_admin_username or "").strip()
        and (settings.keycloak_admin_password or "").strip()
    )
    return has_client_creds or has_password_creds


def _normalize_slug(value: str) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return ""
    if "://" in raw:
        raw = raw.split("://", 1)[1]
    elif raw.startswith("http:/") or raw.startswith("https:/"):
        raw = raw.split(":/", 1)[1]
    raw = raw.strip("/")
    if "/" in raw:
        raw = raw.split("/", 1)[0]
    return raw


def _norm_key(value: Any) -> str:
    text = str(value or "").strip().lower()
    return "".join(ch for ch in text if ch.isalnum() or ch in {"-", "_"})


def _resolve_srms_tenant_id_by_inventory(
    *,
    actor: AuthenticatedUser,
    tenant_mapping,
) -> str:
    """
    SRMS and other modules may not share tenant UUIDs.

    When we cannot list tenant users from SRMS using the HRIS tenant_id, fall back to
    SRMS integration inventory and match by tenant name/code/slug.
    """
    settings = get_settings()
    token = actor.raw_token or settings.srms_service_token or settings.srms_integration_token
    if not token:
        return ""
    payload = srms_client.list_integration_tenants(token)
    orgs = payload.get("organizations", []) if isinstance(payload, dict) else []
    orgs = [row for row in orgs if isinstance(row, dict)]

    want_name = _norm_key(getattr(tenant_mapping, "name", "") or "")
    want_code = _norm_key(getattr(tenant_mapping, "code", "") or "")
    want_slug = _norm_key(getattr(tenant_mapping, "srms_slug", "") or "")

    def _score(row: Dict[str, Any]) -> int:
        candidate_id = str(row.get("tenant_id") or "").strip()
        if not candidate_id:
            return -1
        row_name = _norm_key(row.get("name"))
        row_code = _norm_key(row.get("code"))
        row_slug = _norm_key(row.get("tenant_slug") or row.get("slug"))
        score = 0
        if want_slug and row_slug == want_slug:
            score += 50
        if want_code and row_code == want_code:
            score += 40
        if want_name and row_name == want_name:
            score += 30
        if want_name and row_name and want_name in row_name:
            score += 10
        if want_code and row_code and want_code in row_code:
            score += 5
        return score

    ranked = sorted(orgs, key=_score, reverse=True)
    if not ranked:
        return ""
    best = ranked[0]
    if _score(best) <= 0:
        return ""
    return str(best.get("tenant_id") or "").strip()


def _tokenize_role_value(raw_value: Any) -> List[str]:
    if raw_value is None:
        return []
    if isinstance(raw_value, str):
        value = raw_value.strip()
        if not value:
            return []
        tokens: List[str] = []
        for part in value.replace("|", ",").replace(";", ",").split(","):
            piece = part.strip()
            if piece:
                tokens.append(piece)
        return tokens
    if isinstance(raw_value, list):
        tokens: List[str] = []
        for item in raw_value:
            tokens.extend(_tokenize_role_value(item))
        return tokens
    if isinstance(raw_value, dict):
        tokens: List[str] = []
        for key in ("name", "role", "role_name", "title", "code"):
            if key in raw_value:
                tokens.extend(_tokenize_role_value(raw_value.get(key)))
        return tokens
    return [str(raw_value).strip()]


def _map_source_role_to_hris(raw_role: str) -> str:
    role = str(raw_role or "").strip().lower()
    if not role:
        return ""
    if role in _HRIS_ROLE_PRIORITY:
        return role

    compact = "".join(ch for ch in role if ch.isalnum() or ch == ":")

    if "superadmin" in compact or ("super" in compact and "admin" in compact):
        return "hris:super_admin"
    if "tenantadmin" in compact or ("tenant" in compact and "admin" in compact):
        return "hris:tenant_admin"
    if compact == "admin" or compact.endswith(":admin"):
        return "hris:tenant_admin"
    if "hrmanager" in compact or ("humanresource" in compact and "manager" in compact):
        return "hris:hr_manager"
    if ("line" in compact and "manager" in compact) or "supervisor" in compact:
        return "hris:line_manager"
    if "employee" in compact or "staff" in compact or "user" in compact:
        return "hris:employee"
    return ""


def _flatten_permission_strings(raw_permissions: Any) -> List[str]:
    values: List[str] = []
    if raw_permissions is None:
        return values
    if isinstance(raw_permissions, str):
        token = raw_permissions.strip().lower()
        if token:
            values.append(token)
        return values
    if isinstance(raw_permissions, list):
        for item in raw_permissions:
            values.extend(_flatten_permission_strings(item))
        return values
    if isinstance(raw_permissions, dict):
        for key, item in raw_permissions.items():
            key_norm = str(key or "").strip().lower()
            if isinstance(item, list):
                for action in item:
                    action_norm = str(action or "").strip().lower()
                    if key_norm and action_norm:
                        values.append(f"{key_norm}:{action_norm}")
                    elif key_norm:
                        values.append(key_norm)
            elif isinstance(item, bool):
                if item and key_norm:
                    values.append(key_norm)
            else:
                item_norm = str(item or "").strip().lower()
                if key_norm and item_norm:
                    values.append(f"{key_norm}:{item_norm}")
                elif key_norm:
                    values.append(key_norm)
        return values
    raw = str(raw_permissions or "").strip().lower()
    if raw:
        values.append(raw)
    return values


def _map_permissions_to_hris_roles(raw_permissions: Any) -> List[str]:
    permissions = _flatten_permission_strings(raw_permissions)
    resolved: List[str] = []
    for perm in permissions:
        compact = "".join(ch for ch in perm if ch.isalnum() or ch == ":")
        mapped = ""
        if "admin:all" in compact or compact.endswith(":superadmin"):
            mapped = "hris:super_admin"
        elif compact.endswith(":admin") or "organization:update" in compact or "tenant:admin" in compact:
            mapped = "hris:tenant_admin"
        elif compact == "hr:dashboard":
            # SRMS has two native personas. hr:dashboard is the authoritative
            # high-authority/HR UI capability; staff:dashboard is self-service.
            mapped = "hris:hr_manager"
        elif "employee:update" in compact or "employee:write" in compact or "reports:view" in compact:
            mapped = "hris:hr_manager"
        elif "approval" in compact or "appraisal:review" in compact or "leave:approve" in compact:
            mapped = "hris:line_manager"
        elif compact == "staff:dashboard" or "employee:read" in compact or "self:" in compact or compact.endswith(":view"):
            mapped = "hris:employee"
        if mapped and mapped not in resolved:
            resolved.append(mapped)
    ordered = [role for role in _HRIS_ROLE_PRIORITY if role in resolved]
    if "hris:hr_manager" in ordered and "hris:employee" in ordered:
        ordered.remove("hris:employee")
    return ordered


def _resolve_hris_roles_from_user_row(row: Dict[str, Any]) -> List[str]:
    roles, _ = _resolve_hris_roles_with_source(row)
    return roles


def _resolve_hris_roles_with_source(row: Dict[str, Any]) -> Tuple[List[str], str]:
    # SRMS defines its two personas by dashboard permission, irrespective of
    # the tenant's editable role label/code. Honor that authoritative signal first.
    permission_roles = _map_permissions_to_hris_roles(
        row.get("permissions") if "permissions" in row else row.get("raw_permissions")
    )
    dashboard_permissions = set(_flatten_permission_strings(
        row.get("permissions") if "permissions" in row else row.get("raw_permissions")
    ))
    if "hr:dashboard" in dashboard_permissions:
        return ["hris:hr_manager"], "permissions"
    if "staff:dashboard" in dashboard_permissions:
        return ["hris:employee"], "permissions"

    # Other integrations retain the established role_code -> permission -> role label order.
    role_code_roles = []
    for code in _tokenize_role_value(row.get("role_code")):
        mapped = _map_source_role_to_hris(code)
        if mapped and mapped not in role_code_roles:
            role_code_roles.append(mapped)
    if role_code_roles:
        return [role for role in _HRIS_ROLE_PRIORITY if role in role_code_roles], "role_code"

    if permission_roles:
        return permission_roles, "permissions"

    raw_candidates: List[Any] = [
        row.get("roles"),
        row.get("role"),
        row.get("role_name"),
        row.get("roleName"),
        row.get("designation"),
        row.get("user_type"),
        row.get("userType"),
        row.get("access_level"),
        row.get("accessLevel"),
    ]
    mapped: List[str] = []
    for candidate in raw_candidates:
        for token in _tokenize_role_value(candidate):
            hris_role = _map_source_role_to_hris(token)
            if hris_role and hris_role not in mapped:
                mapped.append(hris_role)

    # Keep a deterministic role order for effective-role resolution.
    ordered = [role for role in _HRIS_ROLE_PRIORITY if role in mapped]
    if ordered:
        return ordered, "role_name_fallback"
    return [], "unresolved"


def _canonical_identity_tenant_id(tenant_id: str, tenant_mapping) -> str:
    """
    Resolve a canonical tenant id for identity writes.
    When a dev alias tenant shares the same SRMS slug with a real tenant,
    we always persist identity links to the non-dev tenant to avoid duplicates.
    """
    slug = _normalize_slug(tenant_mapping.srms_slug or tenant_mapping.code or "")
    if not slug:
        return tenant_id
    candidates = [
        row
        for row in list_tenant_mappings(limit=5000)
        if row.is_tenant_active()
        and _normalize_slug(row.srms_slug or row.code or "") == slug
    ]
    if len(candidates) <= 1:
        return tenant_id
    preferred = [
        row
        for row in candidates
        if not str(row.code or "").strip().lower().startswith("dev-")
    ]
    ranked = preferred or candidates
    ranked.sort(key=lambda row: (str(row.code or "").strip().lower(), str(row.tenant_id)))
    return str(ranked[0].tenant_id or tenant_id).strip() or tenant_id


def _maybe_export_dev_credentials(
    *,
    tenant_id: str,
    records: List[Dict[str, str]],
) -> str:
    settings = get_settings()
    env_name = (settings.app_env or "").strip().lower()
    export_enabled = bool(
        settings.onboarding_dev_credentials_export_enabled
        or (env_name in {"development", "test"} and settings.onboarding_auto_keycloak_provision)
    )
    if not records:
        return ""
    if env_name not in {"development", "test"}:
        return ""
    if not export_enabled:
        return ""
    # Security-first behavior: when welcome email automation is enabled, credentials
    # should flow through email delivery, not local plaintext exports.
    if settings.onboarding_welcome_email_enabled or settings.post_deploy_welcome_emails_enabled:
        return ""

    out_dir = Path(str(settings.onboarding_dev_credentials_export_path or "data/exports")).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_path = out_dir / f"tenant-{tenant_id}-dev-keycloak-credentials-{timestamp}.txt"
    lines = [
        "WARNING: Development-only credentials export.",
        f"tenant_id={tenant_id}",
        f"generated_at={datetime.now(timezone.utc).isoformat()}",
        f"records={len(records)}",
        "",
    ]
    for row in records:
        lines.extend(
            [
                f"requested_tenant_id={row.get('requested_tenant_id', '')}",
                f"module_user_id={row.get('module_user_id', '')}",
                f"username={row.get('username', '')}",
                f"email={row.get('email', '')}",
                f"temporary_password={row.get('temporary_password', '')}",
                f"keycloak_user_id={row.get('keycloak_user_id', '')}",
                f"status={row.get('status', '')}",
                f"hris_role={row.get('hris_role', '')}",
                f"mapping_source={row.get('mapping_source', '')}",
                "",
            ]
        )
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return str(output_path)


def snapshot_current_tenant_mappings(limit: int = 2000) -> Dict[str, Any]:
    rows = [tenant.model_dump() for tenant in list_tenant_mappings(limit=limit)]
    try:
        affected = automation_store.snapshot_tenant_mappings(rows)
    except Exception as exc:
        logger.warning("Tenant mapping snapshot persistence failed: %s", exc)
        affected = 0
    return {"captured": affected, "total": len(rows)}


def persist_identity_from_user(user: AuthenticatedUser) -> None:
    tenant_id = str(user.tenant_id or "").strip()
    if not tenant_id:
        return
    by_module = {
        # Only module-specific immutable IDs are authenticated links.  A portal
        # username/email (or an employee ID from another module) is discovery
        # evidence and must never silently become a cross-module identity.
        "srms": str(user.token_claims.get("srms_employee_id") or "").strip(),
        "eappraisal": str(user.token_claims.get("eappraisal_employee_id") or "").strip(),
        "eleave": str(user.token_claims.get("eleave_employee_id") or "").strip(),
    }
    for module_name, module_user_id in by_module.items():
        if not module_user_id:
            continue
        try:
            automation_store.record_identity_mapping(
                keycloak_issuer=str(user.token_claims.get("iss") or "").rstrip("/") or None,
                keycloak_sub=user.sub,
                tenant_id=tenant_id,
                module_name=module_name,
                module_user_id=module_user_id,
                module_username=user.username,
                email=user.email,
                source="signed_keycloak_module_claim",
                confidence="high",
            )
        except Exception as exc:
            logger.warning("Identity mapping persistence skipped for %s: %s", module_name, exc)


def sync_tenant_users_identity_snapshot(
    *,
    tenant_id: str,
    actor: AuthenticatedUser,
    limit: int,
) -> Dict[str, Any]:
    settings = get_settings()
    tenant_mapping = get_tenant_mapping(tenant_id)
    write_tenant_id = _canonical_identity_tenant_id(tenant_id, tenant_mapping)
    try:
        users_payload = srms_client.list_tenant_users(
            tenant_id,
            actor.raw_token,
            limit=limit,
            tenant_slug=tenant_mapping.srms_slug,
            tenant_code=tenant_mapping.code,
        )
    except HTTPException as exc:
        # If SRMS can't find the tenant_id, try resolving a matching SRMS tenant via inventory.
        detail_text = str(getattr(exc, "detail", "") or "")
        is_not_found_wrapped = "Last status: 404" in detail_text
        if int(exc.status_code) == 404 or (int(exc.status_code) == 502 and is_not_found_wrapped):
            fallback_srms_tenant_id = _resolve_srms_tenant_id_by_inventory(
                actor=actor, tenant_mapping=tenant_mapping
            )
            if fallback_srms_tenant_id and fallback_srms_tenant_id != tenant_id:
                users_payload = srms_client.list_tenant_users(
                    fallback_srms_tenant_id,
                    actor.raw_token,
                    limit=limit,
                    tenant_slug=tenant_mapping.srms_slug,
                    tenant_code=tenant_mapping.code,
                )
            else:
                users_payload = {"users": []}
        else:
            raise
    users = users_payload.get("users", []) if isinstance(users_payload, dict) else []
    users = [row for row in users if isinstance(row, dict)]

    persisted = 0
    keycloak_linked = 0
    keycloak_skipped = 0
    skipped = 0
    missing_role_source = 0
    mapping_source_summary: Dict[str, int] = {
        "role_code": 0,
        "permissions": 0,
        "role_name_fallback": 0,
        "unresolved": 0,
    }
    errors: List[Dict[str, str]] = []
    max_limit = max(1, min(limit, 5000))
    keycloak_provision_enabled = bool(settings.onboarding_auto_keycloak_provision and _keycloak_admin_is_configured())
    welcome_email_mode_enabled = bool(
        settings.onboarding_welcome_email_enabled or settings.post_deploy_welcome_emails_enabled
    )
    export_enabled = bool(
        settings.onboarding_dev_credentials_export_enabled
        or (
            (settings.app_env or "").strip().lower() in {"development", "test"}
            and settings.onboarding_auto_keycloak_provision
        )
    )
    if welcome_email_mode_enabled:
        export_enabled = False
    exported_credentials: List[Dict[str, str]] = []
    logger.warning(
        "Tenant identity sync starting: %s",
        json.dumps(
            {
                "tenant_id": write_tenant_id,
                "requested_tenant_id": tenant_id,
                "input_users": len(users),
                "limit": max_limit,
                "keycloak_provision_enabled": keycloak_provision_enabled,
                "dev_credentials_export_enabled": export_enabled,
            },
            ensure_ascii=True,
        ),
    )

    for row in users[:max_limit]:
        user_id = str(row.get("user_id") or row.get("id") or "").strip()
        email = str(row.get("email") or "").strip().lower()
        username = str(row.get("username") or "").strip()
        module_user_id = user_id or email or username
        resolved_hris_roles, mapping_source = _resolve_hris_roles_with_source(row)
        default_hris_role = resolved_hris_roles[0] if resolved_hris_roles else "hris:employee"
        mapping_source_summary[mapping_source] = mapping_source_summary.get(mapping_source, 0) + 1
        if not module_user_id:
            skipped += 1
            continue
        if not resolved_hris_roles:
            missing_role_source += 1

        try:
            automation_store.record_identity_mapping(
                keycloak_sub=None,
                tenant_id=write_tenant_id,
                module_name="srms",
                module_user_id=module_user_id,
                module_username=username or None,
                email=email or None,
                source="srms_inventory_sync",
                confidence="medium",
            )
            persisted += 1
            if keycloak_provision_enabled and email:
                force_dev_temp_password = bool(
                    export_enabled and settings.onboarding_dev_force_temp_password
                )
                keycloak_result = ensure_user_and_temp_password(
                    email=email,
                    username=(username or email).lower(),
                    tenant_id=write_tenant_id,
                    default_role=default_hris_role,
                    roles=resolved_hris_roles if resolved_hris_roles else [],
                    # First-run dev/test credential exports require temp passwords for newly created users.
                    # Existing users still remain protected from automatic resets by _should_issue_temp_password.
                    send_temp_password=export_enabled,
                    # Optional dev override: only force-reset when explicitly enabled.
                    force_temp_password=force_dev_temp_password,
                )
                keycloak_user_id = str(keycloak_result.get("user_id") or "").strip()
                if keycloak_user_id:
                    automation_store.record_identity_mapping(
                        keycloak_issuer=str(settings.keycloak_issuer or "").rstrip("/") or None,
                        keycloak_sub=keycloak_user_id,
                        tenant_id=write_tenant_id,
                        module_name="srms",
                        module_user_id=module_user_id,
                        module_username=(username or email).lower(),
                        email=email or None,
                        source="srms_inventory_keycloak_link",
                        confidence="high",
                    )
                    keycloak_linked += 1
                    automation_store.upsert_tenant_membership(
                        keycloak_issuer=str(settings.keycloak_issuer or "").rstrip("/"),
                        keycloak_sub=keycloak_user_id,
                        canonical_tenant_id=write_tenant_id,
                        status="active",
                        source="srms_inventory_keycloak_link",
                    )
                    temp_password = str(keycloak_result.get("temporary_password") or "").strip()
                    if export_enabled:
                        exported_credentials.append(
                            {
                                "username": (username or email).lower(),
                                "email": email,
                                "requested_tenant_id": tenant_id,
                                "module_user_id": module_user_id,
                                "temporary_password": temp_password,
                                "keycloak_user_id": keycloak_user_id,
                                "status": str(keycloak_result.get("status") or "unknown"),
                                "hris_role": default_hris_role if resolved_hris_roles else "unresolved",
                                "mapping_source": mapping_source,
                            }
                        )
                else:
                    keycloak_skipped += 1
            elif settings.onboarding_auto_keycloak_provision:
                keycloak_skipped += 1
        except Exception as exc:
            errors.append({"user_id": module_user_id, "error": str(exc)})

    credentials_export_path = _maybe_export_dev_credentials(
        tenant_id=write_tenant_id,
        records=exported_credentials,
    )
    if credentials_export_path:
        logger.info(
            "Development credential export generated for tenant sync",
            extra={
                "tenant_id": write_tenant_id,
                "requested_tenant_id": tenant_id,
                "records": len(exported_credentials),
                "export_path": credentials_export_path,
            },
        )
    result = {
        "tenant_id": write_tenant_id,
        "requested_tenant_id": tenant_id,
        "processed": len(users),
        "persisted": persisted,
        "skipped": skipped,
        "keycloak_linked": keycloak_linked,
        "keycloak_skipped": keycloak_skipped,
        "missing_role_source": missing_role_source,
        "mapping_source_summary": mapping_source_summary,
        "keycloak_provision_enabled": keycloak_provision_enabled,
        "dev_credentials_export_path": credentials_export_path or None,
        "errors": errors[:100],
    }
    logger.warning(
        "Tenant identity sync completed: %s",
        json.dumps(
            {
                "tenant_id": result["tenant_id"],
                "requested_tenant_id": result["requested_tenant_id"],
                "processed": result["processed"],
                "persisted": result["persisted"],
                "skipped": result["skipped"],
                "keycloak_linked": result["keycloak_linked"],
                "keycloak_skipped": result["keycloak_skipped"],
                "missing_role_source": result["missing_role_source"],
                "mapping_source_summary": result["mapping_source_summary"],
                "errors_count": len(errors),
                "dev_credentials_export_path": result["dev_credentials_export_path"],
            },
            ensure_ascii=True,
        ),
    )
    return result


def sync_tenant_users_and_send_welcome(
    *,
    tenant_id: str,
    actor: AuthenticatedUser,
    limit: int,
) -> Dict[str, Any]:
    settings = get_settings()
    if not settings.onboarding_welcome_email_enabled:
        return {"tenant_id": tenant_id, "processed": 0, "sent": 0, "skipped": 0, "errors": [], "enabled": False}

    users_payload = srms_client.list_tenant_users(tenant_id, actor.raw_token, limit=limit)
    users = users_payload.get("users", []) if isinstance(users_payload, dict) else []
    users = [row for row in users if isinstance(row, dict)]
    tenants = {t.tenant_id: t for t in list_tenant_mappings(limit=5000)}
    tenant = tenants.get(tenant_id)
    if tenant is not None:
        write_tenant_id = _canonical_identity_tenant_id(tenant_id, tenant)
    else:
        write_tenant_id = tenant_id
    tenant_name = tenant.name if tenant else tenant_id
    branding = get_tenant_branding(write_tenant_id)

    sent = 0
    skipped = 0
    errors: List[Dict[str, str]] = []
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")

    for row in users[: max(1, min(limit, settings.onboarding_welcome_max_users_per_tenant))]:
        email = str(row.get("email") or "").strip().lower()
        username = str(row.get("username") or email).strip().lower()
        user_id = str(row.get("user_id") or "").strip()
        resolved_hris_roles, _ = _resolve_hris_roles_with_source(row)
        default_hris_role = resolved_hris_roles[0] if resolved_hris_roles else "hris:employee"
        if not email:
            skipped += 1
            continue

        try:
            if automation_store.was_welcome_sent(tenant_id=write_tenant_id, email=email):
                skipped += 1
                continue
        except Exception as exc:
            logger.warning("Welcome idempotency check failed for %s: %s", email, exc)

        idem_key = _idem_key(tenant_id=tenant_id, email=email, purpose="welcome")
        try:
            keycloak_result = ensure_user_and_temp_password(
                email=email,
                username=username,
                tenant_id=write_tenant_id,
                default_role=default_hris_role,
                roles=resolved_hris_roles if resolved_hris_roles else [],
            )
            email_result = send_welcome_email(
                to_email=email,
                tenant_name=tenant_name,
                username=username,
                temporary_password=keycloak_result.get("temporary_password"),
                brand_name=str(branding.get("brand_name") or ""),
                support_email=str(branding.get("support_email") or ""),
                logo_primary_uri=str(branding.get("logo_primary_uri") or ""),
            )
            if not email_result.get("sent"):
                skipped += 1
                try:
                    automation_store.record_welcome_dispatch(
                        tenant_id=tenant_id,
                        email=email,
                        username=username,
                        keycloak_user_id=keycloak_result.get("user_id"),
                        status="skipped",
                        payload={"keycloak": keycloak_result, "email": email_result},
                    )
                except Exception as exc:
                    logger.warning("Welcome dispatch audit skipped for %s: %s", email, exc)
                continue

            try:
                automation_store.record_identity_mapping(
                    keycloak_sub=None,
                    tenant_id=write_tenant_id,
                    module_name="srms",
                    module_user_id=user_id or email,
                    module_username=username,
                    email=email,
                    source="srms_inventory_sync",
                    confidence="medium",
                )
            except Exception as exc:
                logger.warning("Identity audit skipped for %s: %s", email, exc)
            audit_payload = {
                "run_id": run_id,
                "tenant_id": tenant_id,
                "module": "hris-core",
                "employee_id": user_id,
                "email": email,
                "idempotency_key": idem_key,
                "status": "welcome_sent",
                "keycloak": keycloak_result,
            }
            try:
                automation_store.record_provisioning_audit(audit_payload)
                automation_store.record_welcome_dispatch(
                    tenant_id=write_tenant_id,
                    email=email,
                    username=username,
                    keycloak_user_id=keycloak_result.get("user_id"),
                    status="sent",
                    payload=audit_payload,
                )
            except Exception as exc:
                logger.warning("Welcome/provisioning audit skipped for %s: %s", email, exc)
            sent += 1
        except Exception as exc:
            errors.append({"email": email, "error": str(exc)})

    return {
        "tenant_id": write_tenant_id,
        "requested_tenant_id": tenant_id,
        "processed": len(users),
        "sent": sent,
        "skipped": skipped,
        "errors": errors[:100],
        "enabled": True,
    }


def run_post_deploy_automation(actor: AuthenticatedUser) -> Dict[str, Any]:
    settings = get_settings()
    import_result = import_missing_tenants_from_srms(
        actor,
        max_records=settings.startup_tenant_inventory_max_records,
    )
    mapping_snapshot = snapshot_current_tenant_mappings(limit=5000)
    try:
        automation_store.record_checkpoint(
            checkpoint_type="post_deploy_import",
            tenant_id=None,
            payload={"import_result": import_result, "mapping_snapshot": mapping_snapshot},
        )
    except Exception as exc:
        logger.warning("Post-deploy checkpoint persistence failed: %s", exc)

    welcome_results: List[Dict[str, Any]] = []
    if settings.post_deploy_welcome_emails_enabled:
        for tenant in list_tenant_mappings(limit=5000):
            if not tenant.is_tenant_active():
                continue
            welcome_results.append(
                sync_tenant_users_and_send_welcome(
                    tenant_id=tenant.tenant_id,
                    actor=actor,
                    limit=settings.onboarding_welcome_max_users_per_tenant,
                )
            )

    result = {
        "import_result": import_result,
        "mapping_snapshot": mapping_snapshot,
        "welcome_results": welcome_results,
    }
    try:
        automation_store.record_checkpoint(
            checkpoint_type="post_deploy_automation_completed",
            tenant_id=None,
            payload=result,
        )
    except Exception as exc:
        logger.warning("Post-deploy completion checkpoint persistence failed: %s", exc)
    return result
