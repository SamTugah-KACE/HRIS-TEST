from typing import Optional

from pydantic import BaseModel

from app.core.auth import AuthenticatedUser
from app.clients import srms_client
from app.services import automation_store
from app.services.tenant_registry_client import get_tenant_mapping


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
    module_name: str,
    claim_name: str,
) -> ModuleIdentity:
    mapping = automation_store.resolve_identity_mapping(
        tenant_id=user.tenant_id,
        module_name=module_name,
        keycloak_sub=str(user.sub or "").strip() or None,
        email=str(user.email or "").strip().lower() or None,
        username=str(user.username or "").strip().lower() or None,
    )
    if isinstance(mapping, dict):
        mapped_employee_id = str(mapping.get("module_user_id") or "").strip()
        if mapped_employee_id:
            return ModuleIdentity(employee_id=mapped_employee_id, source="identity_mapping", confidence="high")
    claim_value = user.token_claims.get(claim_name)
    if claim_value:
        return ModuleIdentity(employee_id=str(claim_value), source="token_claim", confidence="high")
    if user.employee_id:
        return ModuleIdentity(employee_id=user.employee_id, source="employee_id", confidence="medium")
    return ModuleIdentity(employee_id=user.username, source="username_fallback", confidence="low")


def _resolve_srms_self_employee_id(user: AuthenticatedUser) -> Optional[str]:
    if not user.raw_token:
        return None
    try:
        mapping = get_tenant_mapping(user.tenant_id)
    except Exception:
        return None
    if not mapping.module_enabled("srms"):
        return None
    try:
        self_payload = srms_client.get_self_employee_comprehensive(mapping, user.raw_token)
    except Exception:
        return None
    if not isinstance(self_payload, dict):
        return None
    profile = self_payload.get("profile") if isinstance(self_payload.get("profile"), dict) else {}
    resolved = str(self_payload.get("id") or profile.get("employee_id") or "").strip()
    return resolved or None


def _prefer_srms_identity(module_identity: ModuleIdentity, srms_employee_id: Optional[str]) -> ModuleIdentity:
    srms_id = str(srms_employee_id or "").strip()
    if not srms_id:
        return module_identity
    if module_identity.source in {"employee_id", "username_fallback"}:
        return ModuleIdentity(employee_id=srms_id, source="srms_derived", confidence="medium")
    return module_identity


def resolve_canonical_identity(user: AuthenticatedUser) -> CanonicalIdentity:
    person_id = user.sub or user.username
    srms_identity = _resolve_for_module(user, "srms", "srms_employee_id")
    srms_self_employee_id = _resolve_srms_self_employee_id(user)
    if srms_self_employee_id and str(srms_identity.employee_id or "").strip() != srms_self_employee_id:
        srms_identity = ModuleIdentity(
            employee_id=srms_self_employee_id,
            source="srms_self_comprehensive",
            confidence="high",
        )
    eappraisal_identity = _prefer_srms_identity(
        _resolve_for_module(user, "eappraisal", "eappraisal_employee_id"),
        srms_identity.employee_id,
    )
    eleave_identity = _prefer_srms_identity(
        _resolve_for_module(user, "eleave", "eleave_employee_id"),
        srms_identity.employee_id,
    )
    return CanonicalIdentity(
        person_id=person_id,
        tenant_id=user.tenant_id,
        srms=srms_identity,
        eappraisal=eappraisal_identity,
        eleave=eleave_identity,
    )
