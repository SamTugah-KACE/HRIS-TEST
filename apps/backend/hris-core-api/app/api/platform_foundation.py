from typing import Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.core.auth import AuthenticatedUser, get_current_user, require_roles
from app.core.settings import get_settings
from app.services.capability_registry import (
    public_capability_snapshot,
    update_tenant_entitlements,
)
from app.services.persona_policy import enforce_tenant_scope
from app.services import automation_store
from app.services.tenant_domain_service import (
    public_branding_for_host,
    register_platform_slug,
    request_custom_domain,
    verify_custom_domain,
)
from app.services.provider_config_service import get_sms_provider, upsert_sms_provider, verify_sms_provider


router = APIRouter(prefix="/api/hris/v1", tags=["platform-foundation"])


def _audit(user: AuthenticatedUser, tenant_id: str, action: str, resource_type: str, resource_id: str) -> None:
    automation_store.append_tenant_audit(row={
        "tenant_id": tenant_id, "actor_id": user.sub, "actor_role": user.effective_role,
        "action": action, "resource_type": resource_type, "resource_id": resource_id,
        "outcome": "success", "detail": {},
    })


class TenantEntitlementsUpdate(BaseModel):
    features: Dict[str, bool]


class PlatformSlugIn(BaseModel):
    slug: str


class CustomDomainIn(BaseModel):
    hostname: str


class CustomDomainVerifyIn(BaseModel):
    verification_token: str


class SmsProviderIn(BaseModel):
    provider: str = "arkesel"
    api_key: Optional[str] = None
    sender_id: str
    enabled: bool = False
    allow_platform_fallback: bool = True
    purpose: str = "both"


@router.get("/capabilities")
def get_capabilities(user: AuthenticatedUser = Depends(get_current_user)):
    return {
        "tenant_id": user.tenant_id,
        "capabilities": public_capability_snapshot(tenant_id=user.tenant_id),
    }


@router.get("/platform/deployment")
def get_deployment_status(
    user: AuthenticatedUser = Depends(require_roles("hris:super_admin")),
):
    settings = get_settings()
    return {
        "deployment_mode": settings.deployment_mode,
        "single_node_production_allowed": settings.allow_single_node_production,
        "capabilities": public_capability_snapshot(),
    }


@router.get("/tenants/{tenant_id}/entitlements")
def get_tenant_entitlements(
    tenant_id: str,
    user: AuthenticatedUser = Depends(
        require_roles("hris:super_admin", "hris:tenant_admin")
    ),
):
    enforce_tenant_scope(user, tenant_id, context="Tenant entitlements read")
    return {"tenant_id": tenant_id, "capabilities": public_capability_snapshot(tenant_id=tenant_id)}


@router.put("/tenants/{tenant_id}/entitlements")
def put_tenant_entitlements(
    tenant_id: str,
    payload: TenantEntitlementsUpdate,
    user: AuthenticatedUser = Depends(
        require_roles("hris:super_admin", "hris:tenant_admin")
    ),
):
    enforce_tenant_scope(user, tenant_id, context="Tenant entitlements update")
    try:
        features = update_tenant_entitlements(tenant_id, payload.features)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    _audit(user, tenant_id, "tenant.entitlements.updated", "tenant", tenant_id)
    return {
        "tenant_id": tenant_id,
        "features": features,
        "capabilities": public_capability_snapshot(tenant_id=tenant_id),
    }


@router.get("/public/branding")
def get_public_branding(request: Request):
    # The edge proxy must replace Host with the validated public hostname.
    # Trusting a client-supplied X-Forwarded-Host here would permit branding
    # confusion when the API is reached without that proxy.
    hostname = str(request.url.hostname or "localhost")
    try:
        return public_branding_for_host(hostname)
    except ValueError:
        return {"known_tenant": False, "branding": {"brand_name": "HRIS Portal", "theme": {}}}


@router.post("/tenants/{tenant_id}/domains/platform")
def create_platform_domain(
    tenant_id: str, payload: PlatformSlugIn,
    user: AuthenticatedUser = Depends(require_roles("hris:super_admin", "hris:tenant_admin")),
):
    enforce_tenant_scope(user, tenant_id, context="Tenant platform domain create")
    try:
        result = register_platform_slug(tenant_id=tenant_id, slug=payload.slug)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    _audit(user, tenant_id, "tenant.domain.platform_created", "domain", str(result.get("hostname")))
    return {"tenant_id": tenant_id, **result}


@router.post("/tenants/{tenant_id}/domains/custom")
def create_custom_domain(
    tenant_id: str, payload: CustomDomainIn,
    user: AuthenticatedUser = Depends(require_roles("hris:super_admin", "hris:tenant_admin")),
):
    enforce_tenant_scope(user, tenant_id, context="Tenant custom domain create")
    try:
        result = request_custom_domain(tenant_id=tenant_id, hostname=payload.hostname)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    _audit(user, tenant_id, "tenant.domain.custom_requested", "domain", str(result.get("hostname")))
    return {"tenant_id": tenant_id, **result}


@router.post("/tenants/{tenant_id}/domains/{hostname}/verify")
def verify_domain(
    tenant_id: str, hostname: str, payload: CustomDomainVerifyIn,
    user: AuthenticatedUser = Depends(require_roles("hris:super_admin", "hris:tenant_admin")),
):
    enforce_tenant_scope(user, tenant_id, context="Tenant custom domain verify")
    try:
        result = verify_custom_domain(tenant_id=tenant_id, hostname=hostname, verification_token=payload.verification_token)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    _audit(user, tenant_id, "tenant.domain.verified", "domain", hostname)
    return {"tenant_id": tenant_id, **result}


@router.get("/tenants/{tenant_id}/domains")
def get_domains(
    tenant_id: str,
    user: AuthenticatedUser = Depends(require_roles("hris:super_admin", "hris:tenant_admin")),
):
    enforce_tenant_scope(user, tenant_id, context="Tenant domains list")
    return {"tenant_id": tenant_id, "domains": automation_store.list_tenant_domains(tenant_id=tenant_id)}


@router.get("/tenants/{tenant_id}/activity")
def get_tenant_activity(
    tenant_id: str, limit: int = 100,
    user: AuthenticatedUser = Depends(require_roles("hris:super_admin", "hris:tenant_admin")),
):
    enforce_tenant_scope(user, tenant_id, context="Tenant activity audit")
    return {"tenant_id": tenant_id, "events": automation_store.list_tenant_audit(tenant_id=tenant_id, limit=limit)}


@router.get("/tenants/{tenant_id}/providers/sms")
def read_sms_provider(
    tenant_id: str,
    user: AuthenticatedUser = Depends(require_roles("hris:super_admin", "hris:tenant_admin")),
):
    enforce_tenant_scope(user, tenant_id, context="Tenant SMS provider read")
    return {"tenant_id": tenant_id, "provider": get_sms_provider(tenant_id=tenant_id)}


@router.put("/tenants/{tenant_id}/providers/sms")
def write_sms_provider(
    tenant_id: str, payload: SmsProviderIn,
    user: AuthenticatedUser = Depends(require_roles("hris:super_admin", "hris:tenant_admin")),
):
    enforce_tenant_scope(user, tenant_id, context="Tenant SMS provider update")
    try:
        provider = upsert_sms_provider(
            tenant_id=tenant_id, provider=payload.provider, api_key=payload.api_key,
            sender_id=payload.sender_id, enabled=payload.enabled,
            allow_platform_fallback=payload.allow_platform_fallback, purpose=payload.purpose,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    _audit(user, tenant_id, "tenant.sms_provider.updated", "provider", payload.provider)
    return {"tenant_id": tenant_id, "provider": provider}


@router.post("/tenants/{tenant_id}/providers/sms/verify")
def verify_sms_configuration(
    tenant_id: str,
    user: AuthenticatedUser = Depends(require_roles("hris:super_admin", "hris:tenant_admin")),
):
    enforce_tenant_scope(user, tenant_id, context="Tenant SMS provider verify")
    try:
        provider = verify_sms_provider(tenant_id=tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    _audit(user, tenant_id, "tenant.sms_provider.verified", "provider", str(provider.get("provider")))
    return {"tenant_id": tenant_id, "provider": provider}
