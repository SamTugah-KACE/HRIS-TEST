from fastapi import APIRouter, Depends, Query, Request
from typing import Optional
from pydantic import BaseModel
import hashlib

from app.clients import srms_client
from app.core.auth import AuthenticatedUser, require_roles
from app.core.settings import get_settings
from app.services import automation_store
from app.services.auto_provision_service import provision_missing_users_for_tenant
from app.services.auto_sync_service import get_auto_sync_status, run_auto_sync_now
from app.services.integration_envelope import build_hris_envelope
from app.services.integration_sync import build_sync_snapshot
from app.services.keycloak_provisioning import ensure_user_and_temp_password
from app.services.onboarding_automation import (
    run_post_deploy_automation,
    snapshot_current_tenant_mappings,
    sync_tenant_users_identity_snapshot,
    sync_tenant_users_and_send_welcome,
)
from app.services.persona_policy import enforce_tenant_scope
from app.services.tenant_drift_sync import build_drift_snapshot, build_tenant_reconcile_plan
from app.services.user_drift_sync import build_global_user_drift, build_tenant_user_reconcile_plan
from app.services.tenant_registry_client import get_tenant_mapping, refresh_tenant_mapping_cache

router = APIRouter(prefix="/integrations/synchronization", tags=["integrations-synchronization"])


class TenantUserProvisionRequest(BaseModel):
    email: str
    username: Optional[str] = None
    first_name: str = ""
    last_name: str = ""
    user_id: Optional[str] = None
    idempotency_key: Optional[str] = None


class TenantUserPasswordResetRequest(BaseModel):
    email: Optional[str] = None
    username: Optional[str] = None
    idempotency_key: Optional[str] = None
    reason: str = "manual_admin_reset"


def _password_reset_idempotency_key(*, tenant_id: str, identity: str, idempotency_key: str) -> str:
    raw = f"{tenant_id}:{identity.lower().strip()}:{idempotency_key.strip()}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:48]
    return f"password_reset:{digest}"


@router.get("/tenant/{tenant_id}")
def get_tenant_sync_status(
    tenant_id: str,
    request: Request,
    include_live_probes: bool = Query(True),
    user: AuthenticatedUser = Depends(require_roles("hris:super_admin", "hris:tenant_admin")),
):
    enforce_tenant_scope(user, tenant_id, context="Integrations synchronization")
    snapshot = build_sync_snapshot(
        tenant_id=tenant_id,
        actor=user,
        include_live_probes=include_live_probes,
    )
    return build_hris_envelope(
        data=snapshot,
        module="hris-core",
        request_id=getattr(request.state, "correlation_id", ""),
        tenant_id=tenant_id,
        actor=user,
        message="Synchronization status retrieved",
        resolved_tenant_id=tenant_id,
        resolved_user_id=user.sub,
    )


@router.post("/tenant/{tenant_id}/reconcile")
def reconcile_tenant_sync_status(
    tenant_id: str,
    request: Request,
    include_live_probes: bool = Query(True),
    user: AuthenticatedUser = Depends(require_roles("hris:super_admin", "hris:tenant_admin")),
):
    enforce_tenant_scope(user, tenant_id, context="Integrations synchronization reconcile")
    refresh_tenant_mapping_cache()
    snapshot = build_sync_snapshot(
        tenant_id=tenant_id,
        actor=user,
        include_live_probes=include_live_probes,
    )
    return build_hris_envelope(
        data={"tenant_id": tenant_id, "reconciled": True, "synchronization": snapshot},
        module="hris-core",
        request_id=getattr(request.state, "correlation_id", ""),
        tenant_id=tenant_id,
        actor=user,
        message="Synchronization reconciled",
        resolved_tenant_id=tenant_id,
        resolved_user_id=user.sub,
    )


@router.get("/drift")
def get_cross_system_drift(
    request: Request,
    max_registry_tenants: int = Query(500, ge=1, le=2000),
    user: AuthenticatedUser = Depends(require_roles("hris:super_admin")),
):
    drift = build_drift_snapshot(user, max_registry_tenants=max_registry_tenants)
    return build_hris_envelope(
        data=drift,
        module="hris-core",
        request_id=getattr(request.state, "correlation_id", ""),
        tenant_id=user.tenant_id,
        actor=user,
        message="Cross-system tenant drift snapshot",
        resolved_tenant_id=user.tenant_id,
        resolved_user_id=user.sub,
    )


@router.post("/tenant/{tenant_id}/reconcile-plan")
def get_tenant_reconcile_plan(
    tenant_id: str,
    request: Request,
    user: AuthenticatedUser = Depends(require_roles("hris:super_admin", "hris:tenant_admin")),
):
    enforce_tenant_scope(user, tenant_id, context="Tenant synchronization reconcile plan")
    plan = build_tenant_reconcile_plan(tenant_id=tenant_id, actor=user)
    return build_hris_envelope(
        data=plan,
        module="hris-core",
        request_id=getattr(request.state, "correlation_id", ""),
        tenant_id=tenant_id,
        actor=user,
        message="Tenant reconcile plan generated",
        resolved_tenant_id=tenant_id,
        resolved_user_id=user.sub,
    )


@router.get("/users/drift")
def get_cross_module_user_drift(
    request: Request,
    max_tenants: int = Query(200, ge=1, le=2000),
    max_users_per_tenant: int = Query(200, ge=1, le=500),
    user: AuthenticatedUser = Depends(require_roles("hris:super_admin")),
):
    drift = build_global_user_drift(
        actor=user,
        max_tenants=max_tenants,
        max_users_per_tenant=max_users_per_tenant,
    )
    return build_hris_envelope(
        data=drift,
        module="hris-core",
        request_id=getattr(request.state, "correlation_id", ""),
        tenant_id=user.tenant_id,
        actor=user,
        message="Cross-module user drift snapshot",
        resolved_tenant_id=user.tenant_id,
        resolved_user_id=user.sub,
    )


@router.post("/tenant/{tenant_id}/users/reconcile-plan")
def get_tenant_user_reconcile_plan(
    tenant_id: str,
    request: Request,
    max_users: int = Query(200, ge=1, le=500),
    user: AuthenticatedUser = Depends(require_roles("hris:super_admin", "hris:tenant_admin")),
):
    enforce_tenant_scope(user, tenant_id, context="Tenant user synchronization reconcile plan")
    plan = build_tenant_user_reconcile_plan(
        tenant_id=tenant_id,
        actor=user,
        max_users=max_users,
    )
    return build_hris_envelope(
        data=plan,
        module="hris-core",
        request_id=getattr(request.state, "correlation_id", ""),
        tenant_id=tenant_id,
        actor=user,
        message="Tenant user reconcile plan generated",
        resolved_tenant_id=tenant_id,
        resolved_user_id=user.sub,
    )


@router.get("/auto/status")
def get_auto_sync_runtime_status(
    request: Request,
    user: AuthenticatedUser = Depends(require_roles("hris:super_admin")),
):
    status_payload = get_auto_sync_status()
    return build_hris_envelope(
        data=status_payload,
        module="hris-core",
        request_id=getattr(request.state, "correlation_id", ""),
        tenant_id=user.tenant_id,
        actor=user,
        message="Automatic sync runtime status",
        resolved_tenant_id=user.tenant_id,
        resolved_user_id=user.sub,
    )


@router.post("/auto/run-now")
def run_auto_sync_cycle_now(
    request: Request,
    user: AuthenticatedUser = Depends(require_roles("hris:super_admin")),
):
    result = run_auto_sync_now()
    return build_hris_envelope(
        data=result,
        module="hris-core",
        request_id=getattr(request.state, "correlation_id", ""),
        tenant_id=user.tenant_id,
        actor=user,
        message="Automatic synchronization cycle completed",
        resolved_tenant_id=user.tenant_id,
        resolved_user_id=user.sub,
    )


@router.post("/tenant/{tenant_id}/users/provision-missing")
def provision_tenant_missing_users(
    tenant_id: str,
    request: Request,
    dry_run: Optional[bool] = Query(None),
    max_users: int = Query(200, ge=1, le=500),
    user: AuthenticatedUser = Depends(require_roles("hris:super_admin", "hris:tenant_admin")),
):
    enforce_tenant_scope(user, tenant_id, context="Tenant auto-provision users")
    result = provision_missing_users_for_tenant(
        tenant_id=tenant_id,
        actor=user,
        dry_run_override=dry_run,
        max_users=max_users,
    )
    return build_hris_envelope(
        data=result,
        module="hris-core",
        request_id=getattr(request.state, "correlation_id", ""),
        tenant_id=tenant_id,
        actor=user,
        message="Tenant user auto-provision cycle completed",
        resolved_tenant_id=tenant_id,
        resolved_user_id=user.sub,
    )


@router.post("/tenant/{tenant_id}/users/provision")
def provision_tenant_user(
    tenant_id: str,
    payload: TenantUserProvisionRequest,
    request: Request,
    user: AuthenticatedUser = Depends(require_roles("hris:super_admin", "hris:tenant_admin")),
):
    enforce_tenant_scope(user, tenant_id, context="Tenant user provision")
    mapping = get_tenant_mapping(tenant_id)
    derived_username = (
        (payload.username or "").strip().lower()
        or (payload.email or "").strip().lower()
    )
    result = srms_client.provision_tenant_user(
        tenant_id=tenant_id,
        token=user.raw_token,
        email=(payload.email or "").strip(),
        username=derived_username,
        first_name=(payload.first_name or "").strip(),
        last_name=(payload.last_name or "").strip(),
        user_id=(payload.user_id or "").strip() or None,
        idempotency_key=(payload.idempotency_key or "").strip() or None,
        tenant_slug=mapping.srms_slug,
        tenant_code=mapping.code,
    )
    return build_hris_envelope(
        data=result,
        module="hris-core",
        request_id=getattr(request.state, "correlation_id", ""),
        tenant_id=tenant_id,
        actor=user,
        message="Tenant user provisioned" if bool(result.get("provisioned")) else "Tenant user already existed",
        resolved_tenant_id=tenant_id,
        resolved_user_id=user.sub,
    )


@router.post("/tenant/{tenant_id}/users/password-reset")
def reset_tenant_user_password(
    tenant_id: str,
    payload: TenantUserPasswordResetRequest,
    request: Request,
    user: AuthenticatedUser = Depends(require_roles("hris:super_admin", "hris:tenant_admin")),
):
    settings = get_settings()
    enforce_tenant_scope(user, tenant_id, context="Tenant user manual password reset")
    mapping = get_tenant_mapping(tenant_id)

    email_value = str(payload.email or "").strip().lower()
    username_value = str(payload.username or "").strip().lower()
    if not email_value and not username_value:
        return build_hris_envelope(
            data={"reset_applied": False, "reason": "email_or_username_required"},
            module="hris-core",
            request_id=getattr(request.state, "correlation_id", ""),
            tenant_id=tenant_id,
            actor=user,
            message="Email or username is required",
            resolved_tenant_id=tenant_id,
            resolved_user_id=user.sub,
        )

    users_payload = srms_client.list_tenant_users(
        tenant_id=tenant_id,
        token=user.raw_token,
        limit=5000,
        tenant_slug=mapping.srms_slug,
        tenant_code=mapping.code,
    )
    users = users_payload.get("users", []) if isinstance(users_payload, dict) else []
    users = users if isinstance(users, list) else []
    matched_user = None
    for row in users:
        if not isinstance(row, dict):
            continue
        row_email = str(row.get("email") or "").strip().lower()
        row_username = str(row.get("username") or "").strip().lower()
        if email_value and row_email == email_value:
            matched_user = row
            break
        if username_value and row_username == username_value:
            matched_user = row
            break

    if not matched_user:
        return build_hris_envelope(
            data={"reset_applied": False, "reason": "user_not_found_in_tenant"},
            module="hris-core",
            request_id=getattr(request.state, "correlation_id", ""),
            tenant_id=tenant_id,
            actor=user,
            message="Target user was not found in tenant inventory",
            resolved_tenant_id=tenant_id,
            resolved_user_id=user.sub,
        )

    target_email = str(matched_user.get("email") or email_value).strip().lower()
    target_username = str(matched_user.get("username") or username_value or target_email).strip().lower()
    provided_idem = str(payload.idempotency_key or "").strip()

    if provided_idem:
        identity_key = target_email or target_username
        store_key = _password_reset_idempotency_key(
            tenant_id=tenant_id,
            identity=identity_key,
            idempotency_key=provided_idem,
        )
        existing = automation_store.get_tenant_setting(tenant_id=tenant_id, setting_key=store_key)
        if isinstance(existing, dict) and bool(existing.get("reset_applied")):
            return build_hris_envelope(
                data={
                    "reset_applied": False,
                    "idempotency_key": provided_idem,
                    "idempotent_replay": True,
                    "target_email": target_email,
                    "target_username": target_username,
                },
                module="hris-core",
                request_id=getattr(request.state, "correlation_id", ""),
                tenant_id=tenant_id,
                actor=user,
                message="Password reset already applied for idempotency key",
                resolved_tenant_id=tenant_id,
                resolved_user_id=user.sub,
            )

    keycloak_result = ensure_user_and_temp_password(
        email=target_email,
        username=target_username,
        tenant_id=tenant_id,
        default_role="hris:employee",
        roles=[],
        force_temp_password=True,
        allow_existing_user_password_reset=True,
    )
    temporary_password = str(keycloak_result.get("temporary_password") or "").strip()
    reset_applied = bool(temporary_password)

    audit_payload = {
        "run_id": getattr(request.state, "correlation_id", ""),
        "tenant_id": tenant_id,
        "module": "hris-core",
        "employee_id": str(matched_user.get("user_id") or ""),
        "email": target_email,
        "idempotency_key": provided_idem or None,
        "status": "password_reset_applied" if reset_applied else "password_reset_skipped",
        "reason": str(payload.reason or "manual_admin_reset"),
        "requested_by_sub": user.sub,
        "requested_by_role": user.effective_role,
    }
    automation_store.record_provisioning_audit(audit_payload)

    if provided_idem:
        identity_key = target_email or target_username
        store_key = _password_reset_idempotency_key(
            tenant_id=tenant_id,
            identity=identity_key,
            idempotency_key=provided_idem,
        )
        automation_store.upsert_tenant_setting(
            tenant_id=tenant_id,
            setting_key=store_key,
            value={
                "reset_applied": reset_applied,
                "target_email": target_email,
                "target_username": target_username,
                "requested_by_sub": user.sub,
                "reason": str(payload.reason or "manual_admin_reset"),
            },
        )

    return build_hris_envelope(
        data={
            "reset_applied": reset_applied,
            "idempotency_key": provided_idem or None,
            "target_email": target_email,
            "target_username": target_username,
            "temporary_password": temporary_password if settings.expose_temporary_password_in_api else None,
            "password_reset_applied": keycloak_result.get("password_reset_applied"),
            "temporary_password_delivery": (
                "api_response"
                if settings.expose_temporary_password_in_api
                else "out_of_band_only"
            ),
        },
        module="hris-core",
        request_id=getattr(request.state, "correlation_id", ""),
        tenant_id=tenant_id,
        actor=user,
        message="Manual password reset completed" if reset_applied else "Manual password reset not applied",
        resolved_tenant_id=tenant_id,
        resolved_user_id=user.sub,
    )


@router.post("/automation/post-deploy-run")
def run_post_deploy_sync_automation(
    request: Request,
    user: AuthenticatedUser = Depends(require_roles("hris:super_admin")),
):
    result = run_post_deploy_automation(user)
    return build_hris_envelope(
        data=result,
        module="hris-core",
        request_id=getattr(request.state, "correlation_id", ""),
        tenant_id=user.tenant_id,
        actor=user,
        message="Post-deploy automation run completed",
        resolved_tenant_id=user.tenant_id,
        resolved_user_id=user.sub,
    )


@router.post("/automation/tenant/{tenant_id}/welcome-sync")
def run_tenant_welcome_sync(
    tenant_id: str,
    request: Request,
    max_users: int = Query(2000, ge=1, le=5000),
    user: AuthenticatedUser = Depends(require_roles("hris:super_admin", "hris:tenant_admin")),
):
    enforce_tenant_scope(user, tenant_id, context="Tenant onboarding welcome sync")
    result = sync_tenant_users_and_send_welcome(
        tenant_id=tenant_id,
        actor=user,
        limit=max_users,
    )
    return build_hris_envelope(
        data=result,
        module="hris-core",
        request_id=getattr(request.state, "correlation_id", ""),
        tenant_id=tenant_id,
        actor=user,
        message="Tenant welcome synchronization completed",
        resolved_tenant_id=tenant_id,
        resolved_user_id=user.sub,
    )


@router.post("/automation/tenant/{tenant_id}/identity-sync")
def run_tenant_identity_sync(
    tenant_id: str,
    request: Request,
    max_users: int = Query(2000, ge=1, le=5000),
    user: AuthenticatedUser = Depends(require_roles("hris:super_admin", "hris:tenant_admin")),
):
    enforce_tenant_scope(user, tenant_id, context="Tenant onboarding identity sync")
    result = sync_tenant_users_identity_snapshot(
        tenant_id=tenant_id,
        actor=user,
        limit=max_users,
    )
    return build_hris_envelope(
        data=result,
        module="hris-core",
        request_id=getattr(request.state, "correlation_id", ""),
        tenant_id=tenant_id,
        actor=user,
        message="Tenant identity synchronization completed",
        resolved_tenant_id=tenant_id,
        resolved_user_id=user.sub,
    )


@router.post("/automation/tenant-mapping/snapshot")
def run_tenant_mapping_snapshot(
    request: Request,
    limit: int = Query(2000, ge=1, le=10000),
    user: AuthenticatedUser = Depends(require_roles("hris:super_admin")),
):
    result = snapshot_current_tenant_mappings(limit=limit)
    return build_hris_envelope(
        data=result,
        module="hris-core",
        request_id=getattr(request.state, "correlation_id", ""),
        tenant_id=user.tenant_id,
        actor=user,
        message="Canonical tenant mapping snapshot captured",
        resolved_tenant_id=user.tenant_id,
        resolved_user_id=user.sub,
    )
