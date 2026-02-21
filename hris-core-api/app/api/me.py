from fastapi import APIRouter, Depends

from app.core.auth import AuthenticatedUser, get_current_user, HRIS_ROLES
from app.services.tenant_registry_client import get_tenant_mapping

router = APIRouter(prefix="/me", tags=["identity"])


@router.get("")
def get_current_identity(
    user: AuthenticatedUser = Depends(get_current_user),
):
    mapping = get_tenant_mapping(user.tenant_id)

    return {
        "sub": user.sub,
        "username": user.username,
        "email": user.email,
        "tenant_id": user.tenant_id,
        "roles": user.roles,
        "effective_role": user.effective_role,
        "tenant": {
            "code": mapping.code,
            "name": mapping.name,
            "modules": {
                "srms": mapping.srms_schema is not None or mapping.srms_slug is not None,
                "eappraisal": mapping.eappraisal_subdomain is not None,
                "eleave": mapping.eleave_subdomain is not None,
            },
        },
        "available_roles": HRIS_ROLES,
    }
