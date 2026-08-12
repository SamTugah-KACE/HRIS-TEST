from typing import Any, Dict, Optional
from uuid import uuid4
import hashlib
import logging

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from app.core.auth import AuthenticatedUser, require_roles, get_current_user
from app.services import automation_store
from app.services.integration_sync import build_sync_snapshot
from app.services.onboarding import build_onboarding_readiness
from app.services.persona_policy import enforce_tenant_scope
from app.services.tenant_branding_service import (
    get_tenant_branding,
    upload_tenant_logo,
    upsert_tenant_branding,
)
from app.services.tenant_storage_service import TenantStorageService
from app.services.tenant_registry_client import get_tenant_mapping, refresh_tenant_mapping_cache
from app.services.tenant_registry_client import list_tenant_mappings
from app.services.tenant_registry_client import import_tenant
from app.clients import eappraisal_client, srms_client

router = APIRouter(prefix="/tenants", tags=["tenants"])
logger = logging.getLogger(__name__)


def _module_provision_failure(module_name: str, exc: Exception, tenant_id: str) -> Dict[str, str]:
    logger.exception(
        "Native tenant provisioning failed",
        extra={"module_name": module_name, "tenant_id": tenant_id},
    )
    if isinstance(exc, HTTPException) and isinstance(exc.detail, str) and exc.status_code < 500:
        detail = exc.detail
    else:
        detail = f"{module_name} provisioning failed; retry from the canonical tenant record"
    return {"status": "failed", "detail": detail}


class TenantBrandingUpdate(BaseModel):
    brand_name: Optional[str] = None
    support_email: Optional[str] = None
    theme: Optional[Dict[str, Any]] = None


class TenantStorageStackUpdate(BaseModel):
    providers: list[Dict[str, Any]]

class TenantOnboardImportIn(BaseModel):
    tenant_id: Optional[str] = None
    code: str
    name: str
    srms_schema: Optional[str] = None
    srms_slug: Optional[str] = None
    eappraisal_subdomain: Optional[str] = None
    eleave_subdomain: Optional[str] = None
    is_active: bool = True
    enabled_modules: list[str] = []
    primary_admin_email: Optional[str] = None
    organization_email: Optional[str] = None
    country: str = "GH"
    organization_type: str = "PRIVATE"
    employee_range: str = "0-10"
    contact_person: Optional[str] = None
    phone_number: Optional[str] = None
    organization_nature: str = "single_managed"
    subscription_plan: str = "Basic"

@router.post("/onboarding/import")
def import_tenant_onboarding(
    payload: TenantOnboardImportIn,
    user: AuthenticatedUser = Depends(require_roles("hris:super_admin")),
):
    body = payload.model_dump()
    # New HRIS tenants always receive an opaque canonical identifier. Never let
    # the registry infer identity from a human-readable tenant code.
    if payload.tenant_id:
        try:
            canonical = get_tenant_mapping(str(payload.tenant_id))
        except Exception as exc:
            raise HTTPException(status_code=404, detail="Canonical tenant_id was not found") from exc
        body["tenant_id"] = str(canonical.tenant_id)
        body["code"] = canonical.code
        body["name"] = canonical.name
    else:
        incoming_code = str(payload.code or "").strip().casefold()
        incoming_name = str(payload.name or "").strip().casefold()
        existing_tenants = list_tenant_mappings(limit=5000)
        if any(str(row.code or "").strip().casefold() == incoming_code for row in existing_tenants):
            raise HTTPException(status_code=409, detail="Tenant code already exists in HRIS")
        if any(str(row.name or "").strip().casefold() == incoming_name for row in existing_tenants):
            raise HTTPException(status_code=409, detail="Tenant name already exists in HRIS")
        body["tenant_id"] = str(uuid4())
    enabled_modules = {
        str(value or "").strip().lower()
        for value in body.pop("enabled_modules", [])
        if str(value or "").strip()
    }
    admin_email = str(body.pop("primary_admin_email", "") or "").strip().lower()
    organization_email = str(body.pop("organization_email", "") or admin_email).strip().lower()
    country = str(body.pop("country", "GH") or "GH").strip()
    organization_type = str(body.pop("organization_type", "PRIVATE") or "PRIVATE").strip().upper()
    employee_range = str(body.pop("employee_range", "0-10") or "0-10").strip()
    contact_person = str(body.pop("contact_person", "") or body["name"]).strip()
    phone_number = str(body.pop("phone_number", "") or "").strip()
    organization_nature = str(body.pop("organization_nature", "single_managed") or "single_managed").strip()
    subscription_plan = str(body.pop("subscription_plan", "Basic") or "Basic").strip()
    module_results: Dict[str, Any] = {}
    # Routing metadata is generated only by a native module provisioning result.
    body["eappraisal_subdomain"] = None
    body["eleave_subdomain"] = None

    if enabled_modules & {"srms", "eappraisal"} and not admin_email:
        raise HTTPException(status_code=422, detail="primary_admin_email is required for native module provisioning")
    if "srms" in enabled_modules and not phone_number:
        raise HTTPException(status_code=422, detail="phone_number is required when provisioning Staff Records")

    if "srms" in enabled_modules:
        try:
            provisioned = srms_client.provision_tenant({
                "canonical_tenant_id": str(body["tenant_id"]), "name": str(body["name"]),
                "admin_email": admin_email, "organization_email": organization_email,
                "country": country, "organization_type": organization_type.title(),
                "organization_nature": organization_nature, "employee_range": employee_range,
                "contact_person": contact_person, "phone_number": phone_number,
                "subscription_plan": subscription_plan,
            })
            routing_key = str(provisioned.get("routing_key") or "").strip()
            native_tenant_id = str(provisioned.get("native_tenant_id") or "").strip()
            schema_name = str(provisioned.get("schema_name") or "").strip()
            if not routing_key or not native_tenant_id or not schema_name:
                raise RuntimeError("SRMS provisioning did not return native tenant identity")
            body["srms_slug"], body["srms_schema"] = routing_key, schema_name
            module_results["srms"] = provisioned
        except Exception as exc:
            module_results["srms"] = _module_provision_failure("srms", exc, str(body["tenant_id"]))

    if "eappraisal" in enabled_modules:
        digest = hashlib.sha256(str(body["tenant_id"]).encode("utf-8")).hexdigest()[:24]
        try:
            provisioned = eappraisal_client.provision_tenant({
                "canonical_tenant_id": str(body["tenant_id"]), "name": str(body["name"]),
                "routing_key": f"t-{digest}", "admin_email": admin_email,
                "organization_email": organization_email, "country": country,
                "organization_type": organization_type, "employee_range": employee_range,
            })
            routing_key = str(provisioned.get("routing_key") or "").strip()
            native_tenant_id = str(provisioned.get("native_tenant_id") or "").strip()
            if not routing_key or not native_tenant_id:
                raise RuntimeError("eAppraisal provisioning did not return native tenant identity")
            body["eappraisal_subdomain"] = routing_key
            module_results["eappraisal"] = provisioned
        except Exception as exc:
            module_results["eappraisal"] = _module_provision_failure("eappraisal", exc, str(body["tenant_id"]))

    # Persist the canonical identity even after a partial native failure. This
    # makes retries use the same UUID and turns onboarding into an idempotent
    # saga instead of leaking an unreachable native tenant projection.
    result = import_tenant(body)
    registry_payload = result.get("payload") or {}

    for module_name in ("srms", "eappraisal"):
        if module_name not in module_results or not module_results[module_name].get("native_tenant_id"):
            continue
        provisioned = module_results[module_name]
        routing_key = str(provisioned.get("routing_key") or "").strip()
        native_tenant_id = str(provisioned.get("native_tenant_id") or "").strip()
        automation_store.upsert_tenant_link(
            source_tenant_id=str(body["tenant_id"]),
            target_module=module_name,
            target_tenant_ref=native_tenant_id,
            decision="created",
            evidence={"source": "trusted_provisioning_contract", "routing_key": routing_key},
            run_id=user.request_id,
        )
        automation_store.upsert_module_projection(
            canonical_tenant_id=str(body["tenant_id"]),
            module_name=module_name,
            native_tenant_id=native_tenant_id,
            state="verified",
            routing={"routing_key": routing_key, "proof_type": "trusted_provisioning_contract",
                     "proof_reference": user.request_id, "provisioning": provisioned},
            verified=True,
        )
        automation_store.upsert_native_tenant_inventory(
            module_name=module_name,
            native_tenant_id=native_tenant_id,
            reported_canonical_tenant_id=str(body["tenant_id"]),
            display_name=str(body["name"]),
            normalized_name=str(body["name"]).strip().casefold(),
            routing_key=routing_key or native_tenant_id,
            source_version=str(provisioned.get("identity_version") or "provisioned-v1"),
            source_updated_at=None,
            metadata=provisioned,
            inventory_status="claimed",
        )

    for module_name in sorted(enabled_modules - {"srms", "eappraisal"}):
        module_results[module_name] = {"status": "pending", "detail": "native tenant provisioning contract not yet available"}
    refresh_tenant_mapping_cache()
    return {"imported": True, "result": registry_payload, "modules": module_results}


@router.get("")
def list_tenants(
    limit: int = Query(200, ge=1, le=2000),
    user: AuthenticatedUser = Depends(require_roles("hris:super_admin", "hris:tenant_admin")),
):
    rows = list_tenant_mappings(limit=limit)
    if user.effective_role != "hris:super_admin":
        rows = [row for row in rows if str(row.tenant_id) == str(user.tenant_id)]
    tenants = [row.model_dump() for row in rows]
    return {"tenants": tenants, "total": len(tenants)}


@router.get("/{tenant_id}/onboarding/readiness")
def get_tenant_onboarding_readiness(
    tenant_id: str,
    user: AuthenticatedUser = Depends(require_roles("hris:super_admin", "hris:tenant_admin")),
):
    enforce_tenant_scope(user, tenant_id, context="Tenant onboarding readiness")
    mapping = get_tenant_mapping(tenant_id)
    return build_onboarding_readiness(mapping)


@router.post("/{tenant_id}/onboarding/reconcile")
def reconcile_tenant_onboarding(
    tenant_id: str,
    user: AuthenticatedUser = Depends(require_roles("hris:super_admin", "hris:tenant_admin")),
):
    enforce_tenant_scope(user, tenant_id, context="Tenant onboarding reconcile")
    # This endpoint is idempotent and safe: it refreshes tenant context and recalculates readiness.
    refresh_tenant_mapping_cache()
    mapping = get_tenant_mapping(tenant_id)
    readiness = build_onboarding_readiness(mapping)
    return {
        "tenant_id": tenant_id,
        "reconciled": True,
        "readiness": readiness,
    }


@router.get("/{tenant_id}/synchronization/status")
def get_tenant_synchronization_status(
    tenant_id: str,
    user: AuthenticatedUser = Depends(require_roles("hris:super_admin", "hris:tenant_admin")),
):
    enforce_tenant_scope(user, tenant_id, context="Tenant synchronization status")
    return build_sync_snapshot(tenant_id=tenant_id, actor=user, include_live_probes=True)


@router.post("/{tenant_id}/synchronization/reconcile")
def reconcile_tenant_synchronization(
    tenant_id: str,
    user: AuthenticatedUser = Depends(require_roles("hris:super_admin", "hris:tenant_admin")),
):
    enforce_tenant_scope(user, tenant_id, context="Tenant synchronization reconcile")
    refresh_tenant_mapping_cache()
    snapshot = build_sync_snapshot(tenant_id=tenant_id, actor=user, include_live_probes=True)
    return {"tenant_id": tenant_id, "reconciled": True, "synchronization": snapshot}


@router.get("/{tenant_id}/branding")
def get_branding(
    tenant_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
):
    enforce_tenant_scope(user, tenant_id, context="Tenant branding get")
    return {"tenant_id": tenant_id, "branding": get_tenant_branding(tenant_id)}


@router.put("/{tenant_id}/branding")
def update_branding(
    tenant_id: str,
    payload: TenantBrandingUpdate,
    user: AuthenticatedUser = Depends(require_roles("hris:super_admin", "hris:tenant_admin")),
):
    enforce_tenant_scope(user, tenant_id, context="Tenant branding update")
    branding = upsert_tenant_branding(
        tenant_id,
        brand_name=payload.brand_name,
        support_email=payload.support_email,
        theme=payload.theme,
    )
    return {"tenant_id": tenant_id, "branding": branding, "updated": True}


@router.post("/{tenant_id}/branding/logo")
async def upload_branding_logo(
    tenant_id: str,
    logo_kind: str,
    file: UploadFile = File(...),
    user: AuthenticatedUser = Depends(require_roles("hris:super_admin", "hris:tenant_admin")),
):
    enforce_tenant_scope(user, tenant_id, context="Tenant branding logo upload")
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=422, detail="Uploaded file is empty")
    outcome = upload_tenant_logo(
        tenant_id,
        logo_kind=logo_kind,
        file_name=file.filename or f"{logo_kind}.bin",
        content=raw,
        content_type=file.content_type,
    )
    return {"tenant_id": tenant_id, "updated": True, **outcome}


@router.put("/{tenant_id}/storage/providers")
def upsert_tenant_storage_stack(
    tenant_id: str,
    payload: TenantStorageStackUpdate,
    user: AuthenticatedUser = Depends(require_roles("hris:super_admin", "hris:tenant_admin")),
):
    enforce_tenant_scope(user, tenant_id, context="Tenant storage provider stack update")
    if not payload.providers:
        raise HTTPException(status_code=422, detail="providers list is required")
    normalized = []
    for row in payload.providers:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "").strip().lower()
        config = row.get("config") if isinstance(row.get("config"), dict) else {}
        if not name:
            continue
        normalized.append({"name": name, "config": config})
    if not normalized:
        raise HTTPException(status_code=422, detail="No valid providers found")
    automation_store.upsert_tenant_setting(
        tenant_id=tenant_id,
        setting_key="storage_stack",
        value={"providers": normalized},
    )
    return {"tenant_id": tenant_id, "updated": True, "providers": normalized}


@router.get("/{tenant_id}/storage/providers")
def get_tenant_storage_stack(
    tenant_id: str,
    user: AuthenticatedUser = Depends(require_roles("hris:super_admin", "hris:tenant_admin")),
):
    enforce_tenant_scope(user, tenant_id, context="Tenant storage provider stack read")
    payload = automation_store.get_tenant_setting(tenant_id=tenant_id, setting_key="storage_stack") or {"providers": []}
    providers = payload.get("providers") if isinstance(payload, dict) else []
    return {"tenant_id": tenant_id, "providers": providers if isinstance(providers, list) else []}


@router.get("/{tenant_id}/media/{owner_type}/{owner_id}/{document_key}")
def get_tenant_media_document(
    tenant_id: str,
    owner_type: str,
    owner_id: str,
    document_key: str,
    user: AuthenticatedUser = Depends(require_roles("hris:super_admin", "hris:tenant_admin", "hris:hr_manager", "hris:line_manager", "hris:employee")),
):
    enforce_tenant_scope(user, tenant_id, context="Tenant media document read")
    storage = TenantStorageService()
    payload = storage.load_document(
        tenant_id=tenant_id,
        owner_type=owner_type,
        owner_id=owner_id,
        document_key=document_key,
    )
    if payload is None:
        raise HTTPException(status_code=404, detail="Media document not found")
    return Response(
        content=payload["content"],  # type: ignore[index]
        media_type=str(payload.get("content_type") or "application/octet-stream"),
        headers={"Cache-Control": "private, max-age=300"},
    )
