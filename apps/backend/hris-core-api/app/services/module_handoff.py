from __future__ import annotations

import hashlib
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from uuid import uuid4

from fastapi import HTTPException
from jose import JWTError, jwt

from app.core.auth import AuthenticatedUser
from app.core.settings import Settings, get_settings

ALGORITHM = "HS256"
TOKEN_QUERY_PARAM = "hris_handoff"

MODULE_ALLOWED_ROUTE_PREFIXES = {
    "eappraisal": ("/", "/dashboard", "/modules/appraisal", "/appraisal"),
    "eleave": ("/", "/dashboard", "/modules/leave", "/leave"),
    "srms": ("/", "/dashboard", "/employees", "/profile"),
}


def _secret(settings: Settings) -> str:
    for candidate in (
        settings.module_token_secret,
        settings.auth_state_secret,
        settings.keycloak_portal_client_secret,
    ):
        value = str(candidate or "").strip()
        if value:
            return value
    raise HTTPException(status_code=500, detail="Module handoff secret is not configured")


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


class _ReplayStore:
    """Replay store with shared database support and local test fallback."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._redeemed: Dict[str, int] = {}

    def claim_once(self, jti: str, exp: int, payload: Dict[str, Any], settings: Settings) -> bool:
        if str(settings.automation_store_database_url or "").strip():
            from app.services import automation_store

            return automation_store.claim_module_handoff_jti(jti=jti, exp=exp, payload=payload)

        now_epoch = int(time.time())
        with self._lock:
            expired = [key for key, ttl in self._redeemed.items() if ttl <= now_epoch]
            for key in expired:
                self._redeemed.pop(key, None)
            if jti in self._redeemed:
                return False
            self._redeemed[jti] = max(exp, now_epoch + 1)
            return True


_REPLAY_STORE = _ReplayStore()


def issue_handoff_token(
    *,
    user: AuthenticatedUser,
    module_id: str,
    tenant_id: str,
    target_route: str,
    settings: Optional[Settings] = None,
) -> HandoffIssueResult:
    cfg = settings or get_settings()
    now_epoch = int(time.time())
    expires_at = now_epoch + int(cfg.module_handoff_ttl_seconds)
    jti = str(uuid4())
    payload: Dict[str, Any] = {
        "iss": str(cfg.module_handoff_issuer or "hris-core"),
        "sub": str(user.sub),
        "aud": str(module_id),
        "tenant_id": str(tenant_id),
        "username": str(user.username or ""),
        "email": str(user.email or ""),
        "employee_id": str(user.employee_id or ""),
        "target_route": _normalize_target_route(target_route, module_id),
        "iat": now_epoch,
        "exp": expires_at,
        "jti": jti,
    }
    token = jwt.encode(payload, _secret(cfg), algorithm=ALGORITHM)
    return HandoffIssueResult(
        token=token,
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
    native_app_url: str,
    settings: Optional[Settings] = None,
) -> Dict[str, Any]:
    route = _extract_route_from_url(native_app_url, module_id)
    issued = issue_handoff_token(
        user=user,
        module_id=module_id,
        tenant_id=tenant_id,
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
    try:
        payload = jwt.decode(
            str(token or "").strip(),
            _secret(cfg),
            algorithms=[ALGORITHM],
            options={"verify_aud": False},
        )
    except JWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired handoff token") from exc

    aud = str(payload.get("aud") or "").strip().lower()
    expected_module = str(module_id or "").strip().lower()
    if aud != expected_module:
        raise HTTPException(status_code=403, detail="Handoff audience mismatch")

    token_tenant = str(payload.get("tenant_id") or "").strip()
    if token_tenant != str(tenant_id or "").strip():
        raise HTTPException(status_code=403, detail="Handoff tenant mismatch")

    jti = str(payload.get("jti") or "").strip()
    exp = int(payload.get("exp") or 0)
    if not jti or exp <= 0:
        raise HTTPException(status_code=401, detail="Handoff token missing required claims")
    if not _REPLAY_STORE.claim_once(jti, exp, payload, cfg):
        raise HTTPException(status_code=409, detail="Handoff token replay detected")

    route = _normalize_target_route(str(payload.get("target_route") or "/"), expected_module)
    return {
        "sub": str(payload.get("sub") or ""),
        "username": str(payload.get("username") or ""),
        "email": str(payload.get("email") or ""),
        "employee_id": str(payload.get("employee_id") or ""),
        "tenant_id": token_tenant,
        "module_id": expected_module,
        "target_route": route,
        "jti": jti,
        "exp": exp,
    }
