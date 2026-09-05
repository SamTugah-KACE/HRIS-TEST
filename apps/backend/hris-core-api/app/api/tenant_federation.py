from __future__ import annotations

import hashlib
import secrets
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from jose import JWTError, jwt
from pydantic import BaseModel, Field

from app.core.auth import AuthenticatedUser, require_roles
from app.core.settings import get_settings
from app.services import automation_store
from app.services.tenant_inventory_import import (
    import_missing_tenants_from_eappraisal,
    import_missing_tenants_from_srms,
)
from app.services.persona_policy import enforce_tenant_scope
from app.services.tenant_registry_client import get_tenant_mapping, import_tenant
from app.clients import eappraisal_client, srms_client

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


class InventoryRefreshIn(BaseModel):
    modules: list[str] = Field(default_factory=lambda: ["srms", "eappraisal"])
    max_records: int = Field(default=500, ge=1, le=2000)


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


@router.post("/native-tenants/refresh")
def refresh_native_tenants(
    payload: InventoryRefreshIn,
    user: AuthenticatedUser = Depends(require_roles("hris:super_admin")),
):
    """Refresh read-only native inventories without silently linking tenants."""
    requested = list(dict.fromkeys(module.strip().lower() for module in payload.modules))
    unsupported = [module for module in requested if module not in {"srms", "eappraisal"}]
    if unsupported:
        raise HTTPException(status_code=422, detail=f"Unsupported inventory modules: {', '.join(unsupported)}")
    def refresh_one(module: str):
        try:
            result = (
                import_missing_tenants_from_srms(user, max_records=payload.max_records)
                if module == "srms"
                else import_missing_tenants_from_eappraisal(user, max_records=payload.max_records)
            )
            return {"module": module, "ok": True, "result": result}
        except Exception as exc:
            # One unavailable optional module must not discard another module's
            # successful inventory. Return stable categories, not credentials.
            detail = str(getattr(exc, "detail", "") or "").lower()
            if "authentication failed" in detail or getattr(exc, "status_code", None) in {401, 403}:
                reason = "integration_authentication_rejected"
            elif "not configured" in detail:
                reason = "integration_not_configured"
            else:
                reason = "integration_unavailable"
            return {"module": module, "ok": False, "error": reason}

    # Optional modules are independent. Running discovery concurrently prevents
    # a legacy SRMS compatibility probe from delaying a healthy e-Appraisal result.
    results_by_module = {}
    with ThreadPoolExecutor(max_workers=max(1, len(requested)), thread_name_prefix="tenant-inventory") as executor:
        futures = {executor.submit(refresh_one, module): module for module in requested}
        for future in as_completed(futures):
            result = future.result()
            results_by_module[result["module"]] = result
    results = [results_by_module[module] for module in requested]
    return {
        "results": results,
        "items": automation_store.list_native_tenant_inventory(limit=2000),
    }


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
    projection_routing = (projection or {}).get("routing_json") or {}
    if isinstance(projection_routing, str):
        import json
        try:
            projection_routing = json.loads(projection_routing)
        except ValueError:
            projection_routing = {}
    if projection and projection.get("state") == "verified" and projection_routing.get("proof_type") != "compatibility_native_auto_import":
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
            require_second_approver=get_settings().tenant_federation_require_second_superadmin,
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
    claim = result["claim"]
    try:
        activation = _complete_approved_claim(claim=claim)
    except Exception as exc:
        module = str(claim["module_name"]).strip().lower()
        automation_store.upsert_module_projection(
            canonical_tenant_id=str(claim["canonical_tenant_id"]), module_name=module,
            native_tenant_id=str(claim["native_tenant_id"]), state="activation_failed",
            routing={"proof_type": "native_activation_failed", "claim_id": claim_id}, verified=False,
        )
        raise HTTPException(
            status_code=502,
            detail=(
                f"{module} federation was approved but completion failed. "
                "Use Retry completion after correcting module connectivity or credentials."
            ),
        ) from exc
    result["activation"] = activation
    return result


def _complete_approved_claim(*, claim: dict) -> dict:
    """Idempotently finish the remote and registry portions of an approved claim.

    Cross-service work cannot share a database transaction.  Keeping it in one
    resumable operation prevents an activation or Registry outage from turning
    an approved claim into a permanently unrecoverable link.
    """
    module = str(claim["module_name"]).strip().lower()
    try:
        if module == "srms":
            activation = srms_client.activate_tenant_federation(
                str(claim["native_tenant_id"]), str(claim["canonical_tenant_id"])
            )
        elif module == "eappraisal":
            activation = eappraisal_client.activate_tenant_federation(
                str(claim["native_tenant_id"]), str(claim["canonical_tenant_id"])
            )
        else:
            activation = {"status": "not_required"}
    except Exception:
        automation_store.upsert_module_projection(
            canonical_tenant_id=str(claim["canonical_tenant_id"]), module_name=module,
            native_tenant_id=str(claim["native_tenant_id"]), state="activation_failed",
            routing={"proof_type": "native_activation_failed", "claim_id": str(claim["claim_id"])}, verified=False,
        )
        raise
    mapping = get_tenant_mapping(str(claim["canonical_tenant_id"]))
    registry_payload = mapping.model_dump(exclude={"modules"})
    routing_key = str(activation.get("routing_key") or "").strip()
    if module == "srms":
        registry_payload["srms_slug"] = routing_key or mapping.srms_slug
        registry_payload["srms_schema"] = str(activation.get("schema_name") or mapping.srms_schema or "").strip() or None
    elif module == "eappraisal":
        registry_payload["eappraisal_subdomain"] = routing_key or mapping.eappraisal_subdomain
    try:
        import_tenant(registry_payload)
    except Exception:
        automation_store.upsert_module_projection(
            canonical_tenant_id=str(claim["canonical_tenant_id"]), module_name=module,
            native_tenant_id=str(claim["native_tenant_id"]), state="registry_commit_failed",
            routing={
                "proof_type": "native_activated_registry_pending",
                "claim_id": str(claim["claim_id"]),
                "routing_key": routing_key,
            }, verified=False,
        )
        raise
    automation_store.upsert_module_projection(
        canonical_tenant_id=str(claim["canonical_tenant_id"]), module_name=module,
        native_tenant_id=str(claim["native_tenant_id"]), state="verified",
        routing={
            "proof_type": "native_claim_and_activation",
            "claim_id": str(claim["claim_id"]),
            "routing_key": routing_key,
        }, verified=True,
    )
    return activation


@router.post("/claims/{claim_id}/retry-completion")
def retry_claim_completion(
    claim_id: str,
    request: Request,
    user: AuthenticatedUser = Depends(require_roles("hris:super_admin")),
):
    """Resume an approved federation saga after module or Registry failure."""
    claim = automation_store.get_tenant_link_claim(claim_id=claim_id)
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")
    if str(claim.get("state")) != "approved":
        raise HTTPException(status_code=409, detail="Only an approved claim can resume completion")
    projection = automation_store.get_module_projection(
        canonical_tenant_id=str(claim["canonical_tenant_id"]),
        module_name=str(claim["module_name"]),
    )
    if str((projection or {}).get("state")) not in {"activation_failed", "registry_commit_failed", "verified"}:
        raise HTTPException(status_code=409, detail="Claim is not in a resumable completion state")
    activation = _complete_approved_claim(claim=claim)
    automation_store.append_tenant_link_event(
        event_id=str(uuid4()), claim_id=claim_id,
        canonical_tenant_id=str(claim["canonical_tenant_id"]),
        module_name=str(claim["module_name"]), native_tenant_id=str(claim["native_tenant_id"]),
        actor_sub=user.sub, action="claim.completion_retried",
        before={"projection_state": (projection or {}).get("state")}, after={"projection_state": "verified"},
        correlation_id=getattr(request.state, "correlation_id", None),
    )
    return {"claim": claim, "activation": activation, "status": "verified"}


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
