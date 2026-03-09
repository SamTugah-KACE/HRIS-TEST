from fastapi import APIRouter, Depends, Query, Request
from typing import Optional

from app.core.auth import AuthenticatedUser, require_roles
from app.services.auto_provision_service import provision_missing_users_for_tenant
from app.services.auto_sync_service import get_auto_sync_status, run_auto_sync_now
from app.services.integration_envelope import build_hris_envelope
from app.services.integration_sync import build_sync_snapshot
from app.services.onboarding_automation import (
    run_post_deploy_automation,
    snapshot_current_tenant_mappings,
    sync_tenant_users_identity_snapshot,
    sync_tenant_users_and_send_welcome,
)
from app.services.persona_policy import enforce_tenant_scope
from app.services.tenant_drift_sync import build_drift_snapshot, build_tenant_reconcile_plan
from app.services.user_drift_sync import build_global_user_drift, build_tenant_user_reconcile_plan
from app.services.tenant_registry_client import refresh_tenant_mapping_cache

router = APIRouter(prefix="/integrations/synchronization", tags=["integrations-synchronization"])


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
