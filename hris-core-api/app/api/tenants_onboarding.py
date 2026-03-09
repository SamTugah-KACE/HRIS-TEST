from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from app.core.auth import AuthenticatedUser, require_roles
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

router = APIRouter(prefix="/tenants", tags=["tenants"])


class TenantBrandingUpdate(BaseModel):
    brand_name: Optional[str] = None
    support_email: Optional[str] = None
    theme: Optional[Dict[str, Any]] = None


class TenantStorageStackUpdate(BaseModel):
    providers: list[Dict[str, Any]]


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
    user: AuthenticatedUser = Depends(require_roles("hris:super_admin", "hris:tenant_admin", "hris:employee")),
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
