import base64
import hashlib
import secrets
import time
from typing import Dict, Optional
from urllib.parse import quote, urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from jose import JWTError, jwt
from pydantic import BaseModel

from app.core.auth import AuthenticatedUser, get_current_user
from app.core.settings import get_settings

router = APIRouter(prefix="/auth/sso", tags=["auth-sso"])

ACCESS_COOKIE_NAME = "hris_access_token"
REFRESH_COOKIE_NAME = "hris_refresh_token"
ID_TOKEN_COOKIE_NAME = "hris_id_token"


class _SignedStatePayload(BaseModel):
    code_verifier: str
    iat: int
    exp: int
    ui_redirect_path: str
    ui_origin: Optional[str] = None


class LogoutResponse(BaseModel):
    logout_url: Optional[str] = None


def _resolve_authorize_url() -> str:
    settings = get_settings()
    if settings.keycloak_authorize_url:
        return str(settings.keycloak_authorize_url)
    if settings.keycloak_issuer:
        return f"{str(settings.keycloak_issuer).rstrip('/')}/protocol/openid-connect/auth"
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Keycloak authorize URL is not configured")


def _resolve_token_url() -> str:
    settings = get_settings()
    if settings.keycloak_token_url:
        return str(settings.keycloak_token_url)
    if settings.keycloak_issuer:
        return f"{str(settings.keycloak_issuer).rstrip('/')}/protocol/openid-connect/token"
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Keycloak token URL is not configured")


def _resolve_callback_url(request: Request) -> str:
    return str(request.url_for("sso_callback"))


def _resolve_state_signing_secret() -> str:
    settings = get_settings()
    secret = (settings.auth_state_secret or "").strip()
    if secret:
        return secret
    fallback = (settings.keycloak_portal_client_secret or "").strip()
    if fallback:
        return fallback
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="State signing secret is not configured",
    )


def _base64_url_sha256(raw_text: str) -> str:
    digest = hashlib.sha256(raw_text.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")


def _normalize_next_path(next_path: Optional[str]) -> str:
    if next_path and next_path.startswith("/"):
        return next_path
    return "/"


def _resolve_ui_origin_for_state(request: Request) -> Optional[str]:
    settings = get_settings()
    allowed = {
        origin.strip().rstrip("/")
        for origin in str(settings.cors_allowed_origins or "").split(",")
        if origin.strip()
    }
    if settings.portal_base_url:
        allowed.add(str(settings.portal_base_url).rstrip("/"))

    candidates = [
        (request.headers.get("origin") or "").strip(),
        (request.headers.get("referer") or "").strip(),
    ]
    for raw in candidates:
        if not raw:
            continue
        candidate = raw.rstrip("/")
        if candidate in allowed:
            return candidate
        # Referer may include path/query; match by origin part.
        if "://" in candidate and "/" in candidate.split("://", 1)[1]:
            origin_only = candidate.split("://", 1)[0] + "://" + candidate.split("://", 1)[1].split("/", 1)[0]
            if origin_only.rstrip("/") in allowed:
                return origin_only.rstrip("/")
    return None


def _sign_state(code_verifier: str, ui_redirect_path: str, ui_origin: Optional[str]) -> str:
    settings = get_settings()
    now_epoch = int(time.time())
    payload = _SignedStatePayload(
        code_verifier=code_verifier,
        iat=now_epoch,
        exp=now_epoch + settings.auth_state_ttl_seconds,
        ui_redirect_path=ui_redirect_path,
        ui_origin=ui_origin,
    )
    return jwt.encode(
        payload.model_dump(),
        _resolve_state_signing_secret(),
        algorithm="HS256",
    )


def _verify_state(state_token: str) -> _SignedStatePayload:
    try:
        payload = jwt.decode(
            state_token,
            _resolve_state_signing_secret(),
            algorithms=["HS256"],
            options={"verify_aud": False, "verify_iss": False},
        )
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired SSO state",
        ) from exc
    state_payload = _SignedStatePayload(**payload)
    state_payload.ui_redirect_path = _normalize_next_path(state_payload.ui_redirect_path)
    return state_payload


def _build_cookie_settings(request: Request) -> Dict[str, object]:
    settings = get_settings()
    cookie_secure = bool(settings.auth_cookie_secure or request.url.scheme == "https")
    cookie_samesite = settings.auth_cookie_samesite.lower()
    return {
        "httponly": True,
        "secure": cookie_secure,
        "samesite": cookie_samesite,
        "path": "/",
        "domain": settings.auth_cookie_domain,
    }


def _set_csrf_cookie(request: Request, response: Response, csrf_token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=settings.auth_csrf_cookie_name,
        value=csrf_token,
        max_age=settings.auth_cookie_refresh_max_age_seconds,
        httponly=False,
        secure=bool(settings.auth_cookie_secure or request.url.scheme == "https"),
        samesite=settings.auth_cookie_samesite.lower(),
        path="/",
        domain=settings.auth_cookie_domain,
    )


def _require_csrf(request: Request) -> None:
    settings = get_settings()
    if not settings.auth_csrf_enabled:
        return
    header_value = request.headers.get(settings.auth_csrf_header_name)
    cookie_value = request.cookies.get(settings.auth_csrf_cookie_name)
    if not header_value or not cookie_value or header_value != cookie_value:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF validation failed")


def _set_auth_cookies(
    request: Request,
    response: Response,
    access_token: str,
    refresh_token: Optional[str],
    id_token: Optional[str],
    access_expires_in: Optional[int],
    refresh_expires_in: Optional[int],
) -> None:
    settings = get_settings()
    cookie_settings = _build_cookie_settings(request)
    access_max_age = access_expires_in or settings.auth_cookie_access_max_age_seconds
    response.set_cookie(
        key=ACCESS_COOKIE_NAME,
        value=access_token,
        max_age=max(60, int(access_max_age)),
        **cookie_settings,
    )
    if refresh_token:
        refresh_max_age = refresh_expires_in or settings.auth_cookie_refresh_max_age_seconds
        response.set_cookie(
            key=REFRESH_COOKIE_NAME,
            value=refresh_token,
            max_age=max(60, int(refresh_max_age)),
            **cookie_settings,
        )
    if id_token:
        response.set_cookie(
            key=ID_TOKEN_COOKIE_NAME,
            value=id_token,
            max_age=max(60, int(access_max_age)),
            **cookie_settings,
        )
    _set_csrf_cookie(request, response, csrf_token=secrets.token_urlsafe(32))


def _clear_auth_cookies(response: Response) -> None:
    settings = get_settings()
    delete_kwargs = {"path": "/", "domain": settings.auth_cookie_domain}
    response.delete_cookie(ACCESS_COOKIE_NAME, **delete_kwargs)
    response.delete_cookie(REFRESH_COOKIE_NAME, **delete_kwargs)
    response.delete_cookie(ID_TOKEN_COOKIE_NAME, **delete_kwargs)
    response.delete_cookie(settings.auth_csrf_cookie_name, **delete_kwargs)


def _exchange_token(data: Dict[str, str]) -> Dict[str, object]:
    settings = get_settings()
    token_url = _resolve_token_url()
    payload = {"client_id": settings.keycloak_portal_client_id, **data}
    if settings.keycloak_portal_client_secret:
        payload["client_secret"] = settings.keycloak_portal_client_secret
    try:
        with httpx.Client(timeout=settings.http_client_timeout_seconds) as client:
            response = client.post(
                token_url,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                data=payload,
            )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Failed to reach Keycloak token endpoint: {exc}") from exc

    if response.status_code >= 400:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Keycloak token exchange failed")
    data_json = response.json()
    if "access_token" not in data_json:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Keycloak did not return an access token")
    return data_json


@router.get("/start")
def sso_start(request: Request, next_path: Optional[str] = Query(None, alias="next")):
    settings = get_settings()
    if settings.auth_mode != "keycloak":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="SSO is available only when AUTH_MODE=keycloak")

    code_verifier = secrets.token_urlsafe(64)
    code_challenge = _base64_url_sha256(code_verifier)
    callback_url = _resolve_callback_url(request)
    authorize_url = _resolve_authorize_url()

    state = _sign_state(
        code_verifier=code_verifier,
        ui_redirect_path=_normalize_next_path(next_path),
        ui_origin=_resolve_ui_origin_for_state(request),
    )

    query = urlencode(
        {
            "client_id": settings.keycloak_portal_client_id,
            "response_type": "code",
            "scope": "openid profile email",
            "redirect_uri": callback_url,
            "state": state,
            "code_challenge_method": "S256",
            "code_challenge": code_challenge,
        }
    )
    return RedirectResponse(url=f"{authorize_url}?{query}", status_code=status.HTTP_302_FOUND)


@router.get("/callback", name="sso_callback")
def sso_callback(
    request: Request,
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
):
    if not code or not state:
        return RedirectResponse(
            url=_build_portal_error_redirect("missing_code_or_state"),
            status_code=status.HTTP_302_FOUND,
        )

    settings = get_settings()
    callback_url = _resolve_callback_url(request)
    try:
        state_payload = _verify_state(state)
        token_payload = _exchange_token(
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": callback_url,
                "code_verifier": state_payload.code_verifier,
            }
        )
    except HTTPException as exc:
        reason = str(exc.detail) if exc.detail else "sso_callback_failed"
        return RedirectResponse(
            url=_build_portal_error_redirect(reason),
            status_code=status.HTTP_302_FOUND,
        )

    base_ui = (state_payload.ui_origin or settings.portal_base_url).rstrip("/")
    redirect_target = f"{base_ui}{state_payload.ui_redirect_path}"
    response = RedirectResponse(url=redirect_target, status_code=status.HTTP_302_FOUND)
    _set_auth_cookies(
        request=request,
        response=response,
        access_token=str(token_payload.get("access_token")),
        refresh_token=token_payload.get("refresh_token"),
        id_token=token_payload.get("id_token"),
        access_expires_in=token_payload.get("expires_in"),
        refresh_expires_in=token_payload.get("refresh_expires_in"),
    )
    return response


@router.get("/session")
def sso_session(user: AuthenticatedUser = Depends(get_current_user)):
    return {
        "authenticated": True,
        "sub": user.sub,
        "username": user.username,
        "email": user.email,
        "tenant_id": user.tenant_id,
        "roles": user.roles,
        "effective_role": user.effective_role,
        "employee_id": user.employee_id,
    }


@router.post("/refresh")
def sso_refresh(request: Request):
    _require_csrf(request)
    refresh_token = request.cookies.get(REFRESH_COOKIE_NAME)
    if not refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing refresh session")

    token_payload = _exchange_token(
        {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }
    )
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    _set_auth_cookies(
        request=request,
        response=response,
        access_token=str(token_payload.get("access_token")),
        refresh_token=token_payload.get("refresh_token"),
        id_token=token_payload.get("id_token"),
        access_expires_in=token_payload.get("expires_in"),
        refresh_expires_in=token_payload.get("refresh_expires_in"),
    )
    return response


def _build_end_session_url(id_token_hint: Optional[str]) -> Optional[str]:
    settings = get_settings()
    if not settings.keycloak_end_session_url:
        return None
    post_logout_path = settings.auth_post_logout_redirect_path
    if not post_logout_path.startswith("/"):
        post_logout_path = f"/{post_logout_path}"
    post_logout_redirect_uri = f"{settings.portal_base_url.rstrip('/')}{post_logout_path}"
    query: Dict[str, str] = {
        "post_logout_redirect_uri": post_logout_redirect_uri,
        "client_id": settings.keycloak_portal_client_id,
    }
    if id_token_hint:
        query["id_token_hint"] = id_token_hint
    return f"{str(settings.keycloak_end_session_url)}?{urlencode(query)}"


def _build_portal_error_redirect(reason: str) -> str:
    settings = get_settings()
    safe_reason = quote(reason[:120], safe="")
    return f"{settings.portal_base_url.rstrip('/')}/?auth_error={safe_reason}"


@router.post("/logout")
def sso_logout(request: Request):
    _require_csrf(request)
    logout_url = _build_end_session_url(
        id_token_hint=request.cookies.get(ID_TOKEN_COOKIE_NAME),
    )
    response = Response(
        status_code=status.HTTP_200_OK,
        media_type="application/json",
        content=LogoutResponse(logout_url=logout_url).model_dump_json(),
    )
    _clear_auth_cookies(response)
    return response
