from __future__ import annotations

import time
from typing import Any, Dict, Optional

import httpx

from app.core.auth import AuthenticatedUser
from app.core.settings import get_settings
from app.services.identity_resolution import resolve_canonical_identity
from app.services import automation_store
from app.services.jit_policy import get_jit_role_mapping
from app.services.tenant_match_engine import TenantMatchDecision
from app.services.tenant_registry_client import get_tenant_mapping, import_tenant, refresh_tenant_mapping_cache


def _norm_module(name: str) -> str:
    return str(name or "").strip().lower()


def _http() -> httpx.Client:
    settings = get_settings()
    return httpx.Client(timeout=settings.http_client_timeout_seconds)


def _cooldown_key(tenant_id: str, module_name: str, user_sub: str) -> str:
    return f"jit.cooldown.{tenant_id}.{module_name}.{user_sub}".lower()


def _check_cooldown(*, tenant_id: str, module_name: str, user_sub: str) -> Optional[float]:
    settings = get_settings()
    row = automation_store.get_tenant_setting(tenant_id=tenant_id, setting_key=_cooldown_key(tenant_id, module_name, user_sub))
    if not row:
        return None
    try:
        until = float(row.get("until_ts") or 0.0)
    except Exception:
        return None
    if until <= time.time():
        return None
    return until


def _set_cooldown(*, tenant_id: str, module_name: str, user_sub: str, seconds: int) -> None:
    until = time.time() + max(1, int(seconds or 1))
    automation_store.upsert_tenant_setting(
        tenant_id=tenant_id,
        setting_key=_cooldown_key(tenant_id, module_name, user_sub),
        value={"until_ts": until},
    )


def _auto_enable_module_if_needed(*, tenant_id: str, module_name: str) -> Dict[str, Any]:
    mapping = get_tenant_mapping(tenant_id)
    module = _norm_module(module_name)
    if mapping.module_enabled(module):
        return {"enabled": True, "changed": False, "module": module}

    settings = get_settings()
    allowed = {x.strip().lower() for x in str(settings.jit_auto_enable_modules or "").split(",") if x.strip()}
    if module not in allowed:
        return {"enabled": False, "changed": False, "module": module, "reason": "module_not_allowed"}

    # Auto-enable by writing routing hints into Tenant Registry (control-plane).
    # Strict isolation mode: never infer an existing target tenant by loose matching.
    patch: Dict[str, Any] = {"tenant_id": mapping.tenant_id, "code": mapping.code, "name": mapping.name, "is_active": True}
    if module == "eappraisal":
        if not str(mapping.eappraisal_subdomain or "").strip():
            return {
                "enabled": False,
                "changed": False,
                "module": module,
                "reason": "missing_verified_tenant_projection",
            }
        patch["eappraisal_subdomain"] = mapping.eappraisal_subdomain
    if module == "eleave":
        if not str(mapping.eleave_subdomain or "").strip():
            return {
                "enabled": False,
                "changed": False,
                "module": module,
                "reason": "missing_verified_tenant_projection",
            }
        patch["eleave_subdomain"] = mapping.eleave_subdomain
    import_tenant(patch)
    refresh_tenant_mapping_cache()
    mapping2 = get_tenant_mapping(tenant_id)
    return {"enabled": bool(mapping2.module_enabled(module)), "changed": True, "module": module}


def _source_org_profile(mapping: Any) -> Dict[str, Any]:
    saved = automation_store.get_tenant_setting(tenant_id=mapping.tenant_id, setting_key="org_profile") or {}
    if not isinstance(saved, dict):
        saved = {}
    name = str(saved.get("organization_name") or mapping.name or "").strip()
    org_type = str(saved.get("organization_type") or "").strip()
    country = str(saved.get("country") or "").strip()
    has_branches = saved.get("has_branches")
    registration_id = str(saved.get("registration_id") or "").strip()
    return {
        "organization_name": name,
        "organization_type": org_type,
        "country": country,
        "has_branches": has_branches,
        "registration_id": registration_id,
    }


def _resolve_target_tenant_decision(*, module_name: str, mapping: Any, run_id: Optional[str]) -> TenantMatchDecision:
    module = _norm_module(module_name)
    existing_link = automation_store.get_tenant_link(source_tenant_id=mapping.tenant_id, target_module=module)
    if isinstance(existing_link, dict):
        return TenantMatchDecision(
            decision=str(existing_link.get("decision") or "create_new"),
            target_tenant_ref=str(existing_link.get("target_tenant_ref") or "").strip() or None,
            evidence={"source": "tenant_link_ledger", "ledger_id": existing_link.get("id")},
        )

    source_profile = _source_org_profile(mapping)
    if module == "eappraisal":
        # HRIS does not discover Appraisal tenants through module APIs. The
        # registry supplies only the iframe routing slug; native identity and
        # authorization are resolved by Appraisal during handoff redemption.
        target_ref = str(mapping.eappraisal_subdomain or "").strip() or None
        decision = TenantMatchDecision(
            decision="reuse_existing" if target_ref else "create_new",
            target_tenant_ref=target_ref,
            evidence={"source": "tenant_registry_iframe_route"},
        )
    else:
        # eLeave provisioning endpoint can create tenant when absent.
        decision = TenantMatchDecision(
            decision="create_new",
            target_tenant_ref=None,
            evidence={"reason": "no_target_inventory_contract", "source": source_profile},
        )
    automation_store.upsert_tenant_link(
        source_tenant_id=mapping.tenant_id,
        target_module=module,
        target_tenant_ref=decision.target_tenant_ref,
        decision=decision.decision,
        evidence=decision.evidence,
        run_id=run_id,
    )
    return decision


def _call_provision_user(
    *,
    module_name: str,
    mapping: Any,
    actor: AuthenticatedUser,
    dry_run: bool,
    tenant_decision: TenantMatchDecision,
) -> Dict[str, Any]:
    settings = get_settings()
    module = _norm_module(module_name)
    canonical = resolve_canonical_identity(actor)
    canonical_email = str(actor.email or "").strip().lower()
    canonical_username = str(actor.username or "").strip().lower()
    canonical_emp = str(canonical.srms.employee_id or actor.employee_id or "").strip().lower()
    source_profile = _source_org_profile(mapping)
    seed_payload: Dict[str, Any] = {}
    if settings.jit_auto_bootstrap_enabled:
        seed_payload = {
            "seed_profile_shell": True,
            "seed_origin": "hris_jit",
            "seed_request_id": actor.request_id or "",
            "seed_actor_sub": actor.sub or "",
        }
    contract_payload = {
        "organization_name": source_profile.get("organization_name"),
        "organization_type": source_profile.get("organization_type"),
        "country": source_profile.get("country"),
        "has_branches": source_profile.get("has_branches"),
        "registration_id": source_profile.get("registration_id"),
        "source_tenant_id": mapping.tenant_id,
        "match_decision": tenant_decision.decision,
    }

    def _request_with_retries(*, method: str, url: str, headers: Dict[str, str], json_body: Dict[str, Any]) -> httpx.Response:
        retryable = {429, 502, 503, 504}
        last: Optional[httpx.Response] = None
        for attempt in range(2):
            with _http() as client:
                resp = client.request(method, url, headers=headers, json=json_body)
            last = resp
            if resp.status_code not in retryable:
                return resp
            # small backoff
            time.sleep(0.4 * (attempt + 1))
        return last  # type: ignore[return-value]

    if module == "eappraisal":
        return {
            "ok": True,
            "status": "iframe_handoff_only",
            "http_status": 200,
            "payload": {
                "status": "iframe_handoff_only",
                "detail": "Appraisal identity and native session initialization occur inside the iframe handoff.",
            },
        }

    if module == "eleave":
        base = str(settings.eleave_domain_template or "").strip()
        if not base:
            return {"ok": False, "status": "misconfigured", "detail": "ELEAVE_DOMAIN_TEMPLATE not set"}
        if not str(settings.eleave_hris_shared_secret or "").strip():
            return {"ok": False, "status": "misconfigured", "detail": "ELEAVE_HRIS_SHARED_SECRET not set"}
        url = f"{base}{settings.eleave_provision_user_path}".format(tenant_id=mapping.tenant_id)
        headers = {
            "X-Request-ID": actor.request_id or "",
            "X-Client-App": "hris-core",
            "X-Client-Version": "jit",
            "X-HRIS-Tenant-Id": mapping.tenant_id,
            "X-HRIS-User-Sub": actor.sub or "",
            "X-HRIS-Role": (actor.roles[0] if actor.roles else "hris:employee"),
            "X-HRIS-Shared-Secret": str(settings.eleave_hris_shared_secret or ""),
        }
        if settings.eleave_hris_service_token:
            headers["X-HRIS-Service-Token"] = str(settings.eleave_hris_service_token)
        rm = get_jit_role_mapping(tenant_id=mapping.tenant_id)
        payload = {
            "email": canonical_email or "",
            "first_name": actor.first_name or "",
            "last_name": actor.last_name or "",
            "username": canonical_username or "",
            "tenant_code": mapping.code,
            "tenant_name": mapping.name,
            "tenant_slug": mapping.eleave_subdomain or mapping.code,
            "role_name": rm.eleave_role_name or "Normal",
            "employee_id": canonical_emp or "",
            "dry_run": bool(dry_run),
            **contract_payload,
            **seed_payload,
        }
        resp = _request_with_retries(method="POST", url=url, headers=headers, json_body=payload)
        return {"ok": resp.status_code < 400, "http_status": resp.status_code, "payload": resp.json() if resp.content else {}}

    return {"ok": False, "status": "unsupported", "detail": f"Unsupported module '{module}'"}


def _upsert_identity_link_after_jit(
    *,
    tenant_id: str,
    module_name: str,
    actor: AuthenticatedUser,
    canonical_employee_id: str,
    provision_out: Dict[str, Any],
) -> None:
    if not provision_out.get("ok"):
        return
    payload = provision_out.get("payload")
    payload = payload if isinstance(payload, dict) else {}
    candidate_ids = [
        payload.get("module_user_id"),
        payload.get("employee_id"),
        payload.get("staff_id"),
        payload.get("user_id"),
        canonical_employee_id,
        actor.employee_id,
        actor.sub,
    ]
    module_user_id = next((str(v).strip() for v in candidate_ids if str(v or "").strip()), "")
    if not module_user_id:
        return
    try:
        automation_store.record_identity_mapping(
            keycloak_issuer=str(actor.token_claims.get("iss") or "").rstrip("/") or None,
            keycloak_sub=str(actor.sub or "").strip() or None,
            tenant_id=tenant_id,
            module_name=str(module_name or "").strip().lower(),
            module_user_id=module_user_id,
            module_username=str(actor.username or "").strip() or None,
            email=str(actor.email or "").strip().lower() or None,
            source="jit_setup",
            confidence="high" if canonical_employee_id and module_user_id == canonical_employee_id else "medium",
        )
    except Exception:
        pass


def jit_setup_module_for_user(
    *,
    tenant_id: str,
    module_name: str,
    actor: AuthenticatedUser,
    dry_run: Optional[bool] = None,
) -> Dict[str, Any]:
    settings = get_settings()
    if not settings.enable_jit_module_setup:
        return {"ok": False, "status": "disabled", "detail": "ENABLE_JIT_MODULE_SETUP=false"}

    module = _norm_module(module_name)
    mapping = get_tenant_mapping(tenant_id)

    if not actor.sub:
        return {"ok": False, "status": "unauthorized", "detail": "missing_user_sub"}

    cooldown_until = _check_cooldown(tenant_id=mapping.tenant_id, module_name=module, user_sub=actor.sub)
    if cooldown_until:
        return {"ok": False, "status": "cooldown", "detail": "retry_later", "cooldown_until_ts": cooldown_until}

    _set_cooldown(tenant_id=mapping.tenant_id, module_name=module, user_sub=actor.sub, seconds=settings.jit_cooldown_seconds)

    effective_dry_run = bool(dry_run) if dry_run is not None else False
    canonical = resolve_canonical_identity(actor)
    tenant_decision = _resolve_target_tenant_decision(module_name=module, mapping=mapping, run_id=actor.request_id)

    enable_out = _auto_enable_module_if_needed(tenant_id=mapping.tenant_id, module_name=module)

    provision_out = _call_provision_user(
        module_name=module,
        mapping=mapping,
        actor=actor,
        dry_run=effective_dry_run,
        tenant_decision=tenant_decision,
    )
    _upsert_identity_link_after_jit(
        tenant_id=mapping.tenant_id,
        module_name=module,
        actor=actor,
        canonical_employee_id=str(canonical.srms.employee_id or "").strip(),
        provision_out=provision_out,
    )

    audit = {
        "run_id": actor.request_id,
        "tenant_id": mapping.tenant_id,
        "module": module,
        "email": actor.email,
        "employee_id": actor.employee_id,
        "status": "ok" if provision_out.get("ok") else "failed",
        "enable": enable_out,
        "tenant_decision": {
            "decision": tenant_decision.decision,
            "target_tenant_ref": tenant_decision.target_tenant_ref,
            "evidence": tenant_decision.evidence,
        },
        "provision": {"http_status": provision_out.get("http_status"), "payload": provision_out.get("payload")},
        "dry_run": effective_dry_run,
    }
    try:
        automation_store.record_provisioning_audit(audit)
    except Exception:
        pass

    return {
        "ok": bool(provision_out.get("ok")),
        "status": "ok" if provision_out.get("ok") else "failed",
        "enable": enable_out,
        "tenant_decision": {
            "decision": tenant_decision.decision,
            "target_tenant_ref": tenant_decision.target_tenant_ref,
            "evidence": tenant_decision.evidence,
        },
        "provision": provision_out,
        "dry_run": effective_dry_run,
    }
