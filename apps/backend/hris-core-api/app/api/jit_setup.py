from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.auth import AuthenticatedUser, get_current_user
from app.services.jit_module_setup import jit_setup_module_for_user


router = APIRouter(prefix="/jit", tags=["jit"])


@router.post("/modules/{module_name}/setup", response_model=Dict[str, Any])
def jit_setup_module(
    module_name: str,
    tenant_id: Optional[str] = Query(None, description="Tenant to setup. Defaults to current user tenant."),
    dry_run: Optional[bool] = Query(None, description="Preview only; no upstream writes."),
    user: AuthenticatedUser = Depends(get_current_user),
) -> Dict[str, Any]:
    if not user.tenant_id and not tenant_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="tenant_id is required")
    target_tenant_id = str(tenant_id or user.tenant_id or "").strip()
    return jit_setup_module_for_user(tenant_id=target_tenant_id, module_name=module_name, actor=user, dry_run=dry_run)

