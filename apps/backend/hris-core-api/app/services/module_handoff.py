from __future__ import annotations

import hashlib
import secrets
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from uuid import uuid4

from fastapi import HTTPException
from app.core.auth import AuthenticatedUser
from app.core.settings import Settings, get_settings

TOKEN_QUERY_PARAM = "hris_handoff"

MODULE_ALLOWED_ROUTE_PREFIXES = {
    "eappraisal": ("/", "/dashboard", "/modules/appraisal", "/appraisal"),
    "eleave": ("/", "/dashboard", "/modules/leave", "/leave"),
    "srms": ("/", "/dashboard", "/employees", "/profile"),
}


def token_fingerprint(token: str) -> str:
    return hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()[:16]


def _normalize_target_route(raw: str, module_id: str) -> str:
    route = str(raw or "").strip()
    if not route:
        return "/"
    parsed = urlparse(route)
    if parsed.scheme or parsed.netloc:
        raise HTTPException(status_code=400, detail="Absolute target routes are not allowed")
    normalized = parsed.path or "/"
    if not normalized.startswith("/"):
        normalized = f"/{normalized}"
    if ".." in normalized.replace("\\", "/").split("/"):
        raise HTTPException(status_code=400, detail="Invalid target route")
    allowed_prefixes = MODULE_ALLOWED_ROUTE_PREFIXES.get(module_id, ("/",))
    if not any(normalized.startswith(prefix) for prefix in allowed_prefixes):
        raise HTTPException(status_code=403, detail=f"Route '{normalized}' is not allowed for module '{module_id}'")
    if parsed.query:
        return f"{normalized}?{parsed.query}"
    return normalized


def _extract_route_from_url(url: str, module_id: str) -> str:
    parsed = urlparse(str(url or ""))
    raw = parsed.path or "/"
    if parsed.query:
        raw = f"{raw}?{parsed.query}"
    return _normalize_target_route(raw, module_id)


@dataclass
class HandoffIssueResult:
    token: str
    jti: str
    expires_at: int
    target_route: str


class _CodeStore:
    """Opaque code store with shared database support and local test fallback."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._codes: Dict[str, Dict[str, Any]] = {}

    def issue(self, code: str, payload: Dict[str, Any], settings: Settings) -> None:
        code_hash = hashlib.sha256(code.encode("utf-8")).hexdigest()
        if str(settings.automation_store_database_url or "").strip():
            from app.services import automation_store
            automation_store.create_module_handoff_code(code_hash=code_hash, payload=payload)
            return
        if str(settings.app_env or "").lower() == "production":
            raise HTTPException(status_code=503, detail="Shared module handoff store is unavailable")
        with self._lock:
            self._codes[code_hash] = dict(payload)

    def consume(self, code: str, settings: Settings) -> Optional[Dict[str, Any]]:
        code_hash = hashlib.sha256(code.encode("utf-8")).hexdigest()
        if str(settings.automation_store_database_url or "").strip():
            from app.services import automation_store
            return automation_store.consume_module_handoff_code(code_hash=code_hash)
        if str(settings.app_env or "").lower() == "production":
            return None
        now_epoch = int(time.time())
        with self._lock:
            expired = [key for key, value in self._codes.items() if int(value.get("exp") or 0) <= now_epoch]
            for key in expired:
                self._codes.pop(key, None)
            return self._codes.pop(code_hash, None)


_CODE_STORE = _CodeStore()


def issue_handoff_token(
    *,
    user: AuthenticatedUser,
    module_id: str,
    tenant_id: str,
    target_route: str,
    tenant_routing_key: str = "",
    settings: Optional[Settings] = None,
) -> HandoffIssueResult:
    cfg = settings or get_settings()
    now_epoch = int(time.time())
    expires_at = now_epoch + int(cfg.module_handoff_ttl_seconds)
    jti = str(uuid4())
    code = secrets.token_urlsafe(32)
    payload: Dict[str, Any] = {
        "iss": str(cfg.module_handoff_issuer or "hris-core"),
        "sub": str(user.sub),
        "aud": str(module_id),
        "tenant_id": str(tenant_id),
        "tenant_routing_key": str(tenant_routing_key or "").strip().lower(),
        "username": str(user.username or ""),
        "email": str(user.email or ""),
        "employee_id": str(user.employee_id or ""),
        "first_name": str((user.token_claims or {}).get("given_name") or ""),
        "last_name": str((user.token_claims or {}).get("family_name") or ""),
        # These are Keycloak-derived HRIS roles. The native module uses them only
        # to initialize a missing account; its own effective permissions remain
        # authoritative for selecting and protecting native UI functionality.
        "roles": list(user.roles or []),
        "effective_role": str(user.effective_role or ""),
        "auth_context": str((user.token_claims or {}).get("auth_context") or "normal"),
        "target_route": _normalize_target_route(target_route, module_id),
        "iat": now_epoch,
        "exp": expires_at,
        "jti": jti,
    }
    _CODE_STORE.issue(code, payload, cfg)
    return HandoffIssueResult(
        token=code,
        jti=jti,
        expires_at=expires_at,
        target_route=str(payload["target_route"]),
    )


def build_handoff_launch_url(native_app_url: str, token: str) -> str:
    parsed = urlparse(str(native_app_url or "").strip())
    if not parsed.scheme or not parsed.netloc:
        raise HTTPException(status_code=400, detail="Native app URL is invalid")
    query_items = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True) if k != TOKEN_QUERY_PARAM]
    query_items.append((TOKEN_QUERY_PARAM, token))
    return urlunparse(parsed._replace(query=urlencode(query_items)))


def issue_handoff_launch(
    *,
    user: AuthenticatedUser,
    module_id: str,
    tenant_id: str,
    tenant_routing_key: str,
    native_app_url: str,
    settings: Optional[Settings] = None,
) -> Dict[str, Any]:
    route = _extract_route_from_url(native_app_url, module_id)
    issued = issue_handoff_token(
        user=user,
        module_id=module_id,
        tenant_id=tenant_id,
        tenant_routing_key=tenant_routing_key,
        target_route=route,
        settings=settings,
    )
    launch_url = build_handoff_launch_url(native_app_url, issued.token)
    return {
        "launch_url": launch_url,
        "expires_at": issued.expires_at,
        "jti": issued.jti,
        "target_route": issued.target_route,
        "token_fingerprint": token_fingerprint(issued.token),
    }


def redeem_handoff_token(
    *,
    token: str,
    module_id: str,
    tenant_id: str,
    settings: Optional[Settings] = None,
) -> Dict[str, Any]:
    cfg = settings or get_settings()
    payload = _CODE_STORE.consume(str(token or "").strip(), cfg)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid, expired, or already used handoff code")

    aud = str(payload.get("aud") or "").strip().lower()
    expected_module = str(module_id or "").strip().lower()
    if aud != expected_module:
        raise HTTPException(status_code=403, detail="Handoff audience mismatch")

    token_tenant = str(payload.get("tenant_id") or "").strip()
    if token_tenant != str(tenant_id or "").strip():
        raise HTTPException(status_code=403, detail="Handoff tenant mismatch")

    jti = str(payload.get("jti") or "").strip()
    exp = int(payload.get("exp") or 0)
    if not jti or exp <= int(time.time()):
        raise HTTPException(status_code=401, detail="Handoff code expired or missing required claims")

    route = _normalize_target_route(str(payload.get("target_route") or "/"), expected_module)
    return {
        "sub": str(payload.get("sub") or ""),
        "username": str(payload.get("username") or ""),
        "email": str(payload.get("email") or ""),
        "employee_id": str(payload.get("employee_id") or ""),
        "first_name": str(payload.get("first_name") or ""),
        "last_name": str(payload.get("last_name") or ""),
        "roles": [str(role) for role in (payload.get("roles") or [])],
        "effective_role": str(payload.get("effective_role") or ""),
        "auth_context": str(payload.get("auth_context") or "normal"),
        "tenant_id": token_tenant,
        "tenant_routing_key": str(payload.get("tenant_routing_key") or "").strip().lower(),
        "module_id": expected_module,
        "target_route": route,
        "jti": jti,
        "exp": exp,
    }
