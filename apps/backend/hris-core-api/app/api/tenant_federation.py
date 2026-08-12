from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from jose import JWTError, jwt
from pydantic import BaseModel, Field

from app.core.auth import AuthenticatedUser, require_roles
from app.core.settings import get_settings
from app.services import automation_store
from app.services.persona_policy import enforce_tenant_scope
from app.services.tenant_registry_client import get_tenant_mapping

router = APIRouter(prefix="/federation", tags=["tenant-federation"])


class ClaimCreateIn(BaseModel):
    canonical_tenant_id: str
    module_name: str
    native_tenant_id: str
    reason: str = Field(min_length=8, max_length=1000)
    expected_link_version: Optional[int] = Field(default=None, ge=0)


class NativeConfirmIn(BaseModel):
    assertion: str = Field(min_length=64, max_length=8192)


class ClaimDecisionIn(BaseModel):
    reason: str = Field(min_length=8, max_length=1000)


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _module_claim_secret(module_name: str) -> str:
    settings = get_settings()
    module = module_name.strip().lower()
    if module == "srms":
        return str(settings.srms_hris_shared_secret or "").strip()
    elif module == "eappraisal":
        return str(settings.eappraisal_hris_shared_secret or "").strip()
    return ""


@router.get("/native-tenants")
def native_tenants(
    module: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    limit: int = Query(500, ge=1, le=2000),
    _: AuthenticatedUser = Depends(require_roles("hris:super_admin")),
):
    return {"items": automation_store.list_native_tenant_inventory(module_name=module, inventory_status=state, limit=limit)}


@router.get("/tenants/{tenant_id}/projections")
def tenant_projections(
    tenant_id: str,
    user: AuthenticatedUser = Depends(require_roles("hris:super_admin", "hris:tenant_admin")),
):
    enforce_tenant_scope(user, tenant_id, context="Tenant federation projections")
    items = []
    for module in ("srms", "eappraisal", "eleave"):
        row = automation_store.get_module_projection(canonical_tenant_id=tenant_id, module_name=module)
        if row:
            items.append(row)
    return {"tenant_id": tenant_id, "items": items}


@router.get("/claims")
def claims(
    state: Optional[str] = Query(None), limit: int = Query(200, ge=1, le=1000),
    _: AuthenticatedUser = Depends(require_roles("hris:super_admin")),
):
    return {"items": automation_store.list_tenant_link_claims(state=state, limit=limit)}


@router.post("/claims", status_code=status.HTTP_201_CREATED)
def create_claim(
    payload: ClaimCreateIn,
    request: Request,
    user: AuthenticatedUser = Depends(require_roles("hris:super_admin")),
):
    module = payload.module_name.strip().lower()
    if module not in {"srms", "eappraisal", "eleave"}:
        raise HTTPException(status_code=422, detail="Unsupported module")
    get_tenant_mapping(payload.canonical_tenant_id)
    inventory = automation_store.list_native_tenant_inventory(module_name=module, limit=2000)
    if not any(str(row.get("native_tenant_id")) == payload.native_tenant_id for row in inventory):
        raise HTTPException(status_code=404, detail="Native tenant inventory record not found")
    projection = automation_store.get_module_projection(
        canonical_tenant_id=payload.canonical_tenant_id, module_name=module
    )
    if projection and projection.get("state") == "verified":
        raise HTTPException(status_code=409, detail="Module projection is already verified")
    current_version = int((projection or {}).get("link_version") or 0)
    if payload.expected_link_version is not None and payload.expected_link_version != current_version:
        raise HTTPException(status_code=409, detail="Module projection version changed; refresh and retry")

    challenge = secrets.token_urlsafe(48)
    claim_id = str(uuid4())
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
    try:
        row = automation_store.create_tenant_link_claim(
            claim_id=claim_id, canonical_tenant_id=payload.canonical_tenant_id,
            module_name=module, native_tenant_id=payload.native_tenant_id,
            reason=payload.reason.strip(), initiated_by=user.sub,
            challenge_hash=_sha256(challenge), expires_at=expires_at,
            expected_link_version=current_version,
        )
    except Exception as exc:
        raise HTTPException(status_code=409, detail="An active claim already exists or the link changed") from exc
    automation_store.append_tenant_link_event(
        event_id=str(uuid4()), claim_id=claim_id, canonical_tenant_id=payload.canonical_tenant_id,
        module_name=module, native_tenant_id=payload.native_tenant_id, actor_sub=user.sub,
        action="claim.created", before={}, after={"state": "verification_pending"},
        correlation_id=getattr(request.state, "correlation_id", None),
    )
    # The challenge is returned once and is never stored in plaintext.
    return {"claim": row, "challenge": challenge, "expires_at": expires_at}


@router.post("/claims/{claim_id}/confirm-native")
def confirm_native_claim(
    claim_id: str,
    payload: NativeConfirmIn,
    request: Request,
    user: AuthenticatedUser = Depends(require_roles("hris:super_admin")),
):
    claim = automation_store.get_tenant_link_claim(claim_id=claim_id)
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")
    module = str(claim["module_name"]).strip().lower()
    secret = _module_claim_secret(module)
    if not secret:
        raise HTTPException(status_code=503, detail="Native claim verification secret is not configured")
    try:
        assertion = jwt.decode(
            payload.assertion, secret, algorithms=["HS256"],
            audience="hris-core-tenant-claim",
        )
    except JWTError as exc:
        raise HTTPException(status_code=401, detail="Native authority assertion is invalid or expired") from exc
    expected = {
        "iss": module,
        "claim_id": claim_id,
        "canonical_tenant_id": str(claim["canonical_tenant_id"]),
        "native_tenant_id": str(claim["native_tenant_id"]),
        "challenge_hash": str(claim["challenge_hash"]),
    }
    if any(str(assertion.get(key) or "") != value for key, value in expected.items()):
        raise HTTPException(status_code=403, detail="Native authority assertion is not bound to this claim")
    assertion_id = str(assertion.get("jti") or "").strip()
    authority_sub = str(assertion.get("authority_sub") or "").strip()
    if not assertion_id or not authority_sub:
        raise HTTPException(status_code=403, detail="Native authority assertion is incomplete")
    if claim["state"] != "verification_pending":
        raise HTTPException(status_code=409, detail="Claim is not awaiting native confirmation")
    if claim.get("expires_at") and claim["expires_at"] <= datetime.now(timezone.utc):
        automation_store.update_tenant_link_claim(
            claim_id=claim_id, expected_state="verification_pending", new_state="expired"
        )
        raise HTTPException(status_code=410, detail="Claim challenge expired")
    updated = automation_store.update_tenant_link_claim(
        claim_id=claim_id, expected_state="verification_pending", new_state="native_confirmed",
        assertion_hash=_sha256(assertion_id),
    )
    if not updated:
        raise HTTPException(status_code=409, detail="Claim changed concurrently")
    automation_store.append_tenant_link_event(
        event_id=str(uuid4()), claim_id=claim_id, canonical_tenant_id=str(claim["canonical_tenant_id"]),
        module_name=str(claim["module_name"]), native_tenant_id=str(claim["native_tenant_id"]),
        actor_sub=f"module:{module}:{authority_sub}", action="claim.native_confirmed",
        before={"state": "verification_pending"}, after={"state": "native_confirmed"},
        correlation_id=getattr(request.state, "correlation_id", None),
    )
    return {"claim": updated}


@router.post("/claims/{claim_id}/approve")
def approve_claim(
    claim_id: str,
    payload: ClaimDecisionIn,
    request: Request,
    user: AuthenticatedUser = Depends(require_roles("hris:super_admin")),
):
    try:
        result = automation_store.approve_tenant_link_claim(
            claim_id=claim_id, approved_by=user.sub,
            correlation_id=getattr(request.state, "correlation_id", None), event_id=str(uuid4()),
        )
    except ValueError as exc:
        messages = {
            "claim_not_found": (404, "Claim not found"),
            "claim_not_native_confirmed": (409, "Native tenant has not confirmed the claim"),
            "second_approver_required": (403, "A different superadmin must approve this claim"),
            "claim_expired": (410, "Claim expired"),
            "projection_version_conflict": (409, "Module projection changed; create a new claim"),
            "native_tenant_already_linked": (409, "Native tenant is already linked elsewhere"),
            "native_inventory_not_found": (404, "Native inventory record not found"),
        }
        code, detail = messages.get(str(exc), (409, "Claim could not be approved"))
        raise HTTPException(status_code=code, detail=detail) from exc
    # Reason is captured as a separate immutable event without exposing secrets.
    automation_store.append_tenant_link_event(
        event_id=str(uuid4()), claim_id=claim_id,
        canonical_tenant_id=str(result["claim"]["canonical_tenant_id"]),
        module_name=str(result["claim"]["module_name"]),
        native_tenant_id=str(result["claim"]["native_tenant_id"]), actor_sub=user.sub,
        action="claim.approval_reason", before={}, after={"reason": payload.reason.strip()},
        correlation_id=getattr(request.state, "correlation_id", None),
    )
    return result


@router.post("/claims/{claim_id}/reject")
def reject_claim(
    claim_id: str,
    payload: ClaimDecisionIn,
    request: Request,
    user: AuthenticatedUser = Depends(require_roles("hris:super_admin")),
):
    claim = automation_store.get_tenant_link_claim(claim_id=claim_id)
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")
    if claim["state"] not in {"verification_pending", "native_confirmed"}:
        raise HTTPException(status_code=409, detail="Claim is no longer reviewable")
    updated = automation_store.update_tenant_link_claim(
        claim_id=claim_id, expected_state=str(claim["state"]), new_state="rejected", approved_by=user.sub
    )
    if not updated:
        raise HTTPException(status_code=409, detail="Claim changed concurrently")
    automation_store.append_tenant_link_event(
        event_id=str(uuid4()), claim_id=claim_id, canonical_tenant_id=str(claim["canonical_tenant_id"]),
        module_name=str(claim["module_name"]), native_tenant_id=str(claim["native_tenant_id"]),
        actor_sub=user.sub, action="claim.rejected", before={"state": claim["state"]},
        after={"state": "rejected", "reason": payload.reason.strip()},
        correlation_id=getattr(request.state, "correlation_id", None),
    )
    return {"claim": updated}
