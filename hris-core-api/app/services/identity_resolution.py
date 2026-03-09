from typing import Optional

from pydantic import BaseModel

from app.core.auth import AuthenticatedUser


class ModuleIdentity(BaseModel):
    employee_id: Optional[str] = None
    source: str = "unresolved"
    confidence: str = "low"


class CanonicalIdentity(BaseModel):
    person_id: str
    tenant_id: str
    srms: ModuleIdentity
    eappraisal: ModuleIdentity
    eleave: ModuleIdentity


def _resolve_for_module(
    user: AuthenticatedUser,
    claim_name: str,
) -> ModuleIdentity:
    claim_value = user.token_claims.get(claim_name)
    if claim_value:
        return ModuleIdentity(employee_id=str(claim_value), source="token_claim", confidence="high")
    if user.employee_id:
        return ModuleIdentity(employee_id=user.employee_id, source="employee_id", confidence="medium")
    return ModuleIdentity(employee_id=user.username, source="username_fallback", confidence="low")


def resolve_canonical_identity(user: AuthenticatedUser) -> CanonicalIdentity:
    person_id = user.sub or user.username
    return CanonicalIdentity(
        person_id=person_id,
        tenant_id=user.tenant_id,
        srms=_resolve_for_module(user, "srms_employee_id"),
        eappraisal=_resolve_for_module(user, "eappraisal_employee_id"),
        eleave=_resolve_for_module(user, "eleave_employee_id"),
    )
