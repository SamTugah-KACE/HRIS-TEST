from typing import Optional, Set

from fastapi import HTTPException, status

from app.core.auth import AuthenticatedUser
from app.services.identity_resolution import resolve_canonical_identity

SUPERADMIN_ROLES: Set[str] = {"hris:super_admin"}
TENANT_ADMIN_ROLES: Set[str] = {"hris:tenant_admin", "hris:hr_manager"}
MANAGER_ROLES: Set[str] = {
    "hris:super_admin",
    "hris:tenant_admin",
    "hris:hr_manager",
    "hris:line_manager",
}
TENANT_ROSTER_ROLES: Set[str] = {
    "hris:super_admin",
    "hris:tenant_admin",
    "hris:hr_manager",
}


def has_any_role(user: AuthenticatedUser, allowed_roles: Set[str]) -> bool:
    return user.effective_role in allowed_roles


def can_view_tenant_employee_roster(user: AuthenticatedUser) -> bool:
    return has_any_role(user, TENANT_ROSTER_ROLES)


def can_view_team_employee_roster(user: AuthenticatedUser) -> bool:
    return has_any_role(user, MANAGER_ROLES)


def can_view_manager_sections(user: AuthenticatedUser) -> bool:
    return has_any_role(user, MANAGER_ROLES)


def can_override_employee_scope(user: AuthenticatedUser) -> bool:
    return can_view_tenant_employee_roster(user)


def is_self_scope(user: AuthenticatedUser, target_employee_id: Optional[str]) -> bool:
    target = (target_employee_id or "").strip().lower()
    if not target:
        return True

    canonical = resolve_canonical_identity(user)
    candidates = {
        (user.employee_id or "").strip().lower(),
        (user.sub or "").strip().lower(),
        (user.username or "").strip().lower(),
        (canonical.srms.employee_id or "").strip().lower(),
        (canonical.eappraisal.employee_id or "").strip().lower(),
        (canonical.eleave.employee_id or "").strip().lower(),
    }
    candidates.discard("")
    return target in candidates


def enforce_self_or_privileged(user: AuthenticatedUser, target_employee_id: Optional[str], *, context: str) -> None:
    if can_override_employee_scope(user):
        return
    if is_self_scope(user, target_employee_id):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=f"{context}: access is limited to your own records.",
    )


def enforce_tenant_scope(user: AuthenticatedUser, tenant_id: str, *, context: str) -> None:
    if has_any_role(user, SUPERADMIN_ROLES):
        return
    if str(user.tenant_id) == str(tenant_id):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=f"{context}: cross-tenant access is not allowed.",
    )
