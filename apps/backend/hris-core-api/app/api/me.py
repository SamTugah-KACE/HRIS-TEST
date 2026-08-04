from fastapi import APIRouter, Depends

from app.core.auth import AuthenticatedUser, get_current_user, HRIS_ROLES
from app.services.identity_resolution import resolve_canonical_identity
from app.services.onboarding_automation import persist_identity_from_user
from app.services.tenant_registry_client import get_tenant_mapping

router = APIRouter(prefix="/me", tags=["identity"])


@router.get("")
def get_current_identity(
    user: AuthenticatedUser = Depends(get_current_user),
):
    persist_identity_from_user(user)

    if user.effective_role == "hris:super_admin":
        return {
            "sub": user.sub,
            "username": user.username,
            "email": user.email,
            "tenant_id": user.tenant_id,
            "employee_id": user.employee_id,
            "roles": user.roles,
            "effective_role": user.effective_role,
            "tenant": {
                "code": "PLATFORM",
                "name": "HRIS Platform",
                "status": "active",
                "modules": {},
                "enabled_module_ids": [],
            },
            "identity_map": {},
            "available_roles": HRIS_ROLES,
        }

    mapping = get_tenant_mapping(user.tenant_id)
    canonical_identity = resolve_canonical_identity(user)

    return {
        "sub": user.sub,
        "username": user.username,
        "email": user.email,
        "tenant_id": user.tenant_id,
        "employee_id": canonical_identity.srms.employee_id or user.employee_id,
        "roles": user.roles,
        "effective_role": user.effective_role,
        "tenant": {
            "code": mapping.code,
            "name": mapping.name,
            "status": mapping.lifecycle_status,
            "modules": mapping.modules.model_dump(),
            "enabled_module_ids": mapping.enabled_module_ids(),
        },
        "identity_map": canonical_identity.model_dump(),
        "available_roles": HRIS_ROLES,
    }
