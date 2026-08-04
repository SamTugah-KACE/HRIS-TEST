from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.core.auth import AuthenticatedUser, require_roles
from app.core.settings import get_settings
from app.services.federated_directory_sync import (
    build_federated_directory_snapshot_for_tenant,
    build_federated_directory_snapshot_global,
)

router = APIRouter(prefix="/debug/federated-directory", tags=["federated-directory-debug"])


@router.get("")
def get_federated_directory_snapshot(
    request: Request,
    tenant_id: Optional[str] = None,
    user: AuthenticatedUser = Depends(require_roles("hris:super_admin")),
):
    settings = get_settings()
    if not settings.enable_integration_debug_endpoints:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Debug integration endpoints are disabled",
        )
    target_tenant_id = str(tenant_id or user.tenant_id or "").strip()
    if not target_tenant_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="tenant_id is required")
    return build_federated_directory_snapshot_for_tenant(
        tenant_id=target_tenant_id,
        actor=user,
        limit_per_module=2000,
    )


@router.get("/global")
def get_federated_directory_snapshot_global(
    request: Request,
    user: AuthenticatedUser = Depends(require_roles("hris:super_admin")),
):
    settings = get_settings()
    if not settings.enable_integration_debug_endpoints:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Debug integration endpoints are disabled",
        )
    return build_federated_directory_snapshot_global(actor=user, max_tenants=50, limit_per_module=2000)

