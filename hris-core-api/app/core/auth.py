from typing import Dict, List, Optional

import httpx
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from pydantic import BaseModel

from app.core.settings import get_settings
from app.services import automation_store

bearer_scheme = HTTPBearer(auto_error=False)

HRIS_ROLES = [
    "hris:super_admin",
    "hris:tenant_admin",
    "hris:hr_manager",
    "hris:line_manager",
    "hris:employee",
]


class AuthenticatedUser(BaseModel):
    sub: str
    username: str
    email: Optional[str] = None
    tenant_id: str
    roles: List[str] = []
    effective_role: str = "hris:employee"
    employee_id: Optional[str] = None
    raw_token: Optional[str] = None
    token_claims: Dict[str, object] = {}


def resolve_effective_role(roles: List[str]) -> str:
    for role in HRIS_ROLES:
        if role in roles:
            return role
    return "hris:employee"


def require_roles(*allowed_roles: str):
    def checker(user: AuthenticatedUser = Depends(get_current_user)):
        if user.effective_role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{user.effective_role}' is not authorized for this resource",
            )
        return user
    return checker


def _decode_keycloak_token(token: str) -> dict:
    settings = get_settings()
    if not settings.keycloak_jwks_url or not settings.keycloak_issuer:
        raise RuntimeError("Keycloak is not configured but auth_mode=keycloak")

    try:
        response = httpx.get(str(settings.keycloak_jwks_url), timeout=5.0)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise RuntimeError(f"Unable to fetch JWKS from Keycloak: {exc}") from exc

    jwks = response.json()
    keys = jwks.get("keys") if isinstance(jwks, dict) else None
    if not isinstance(keys, list) or len(keys) == 0:
        raise RuntimeError("JWKS payload does not contain signing keys")

    unverified_header = jwt.get_unverified_header(token)
    token_kid = unverified_header.get("kid")
    if not token_kid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token header missing key identifier (kid)",
        )

    signing_key = next((key for key in keys if key.get("kid") == token_kid), None)
    if signing_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token signing key was not found in JWKS",
        )
    configured_audiences = [
        audience.strip()
        for audience in str(settings.keycloak_audience or "").split(",")
        if audience.strip()
    ]
    jwt_options = {"verify_iss": True, "verify_aud": False}
    try:
        payload = jwt.decode(
            token,
            signing_key,
            algorithms=["RS256"],
            audience=None,
            issuer=str(settings.keycloak_issuer),
            options=jwt_options,
        )
        if configured_audiences:
            token_aud = payload.get("aud")
            if isinstance(token_aud, str):
                token_audiences = {token_aud}
            elif isinstance(token_aud, list):
                token_audiences = {str(aud) for aud in token_aud}
            else:
                token_audiences = set()
            if not any(aud in token_audiences for aud in configured_audiences):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid token audience",
                )
        return payload
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        ) from exc


async def _get_user_dev(request: Request) -> AuthenticatedUser:
    settings = get_settings()
    tenant_id = request.headers.get("X-Debug-Tenant-Id") or settings.dev_default_tenant_id
    username = request.headers.get("X-Debug-Username") or settings.dev_default_username
    employee_id = request.headers.get("X-Debug-Employee-Id") or settings.dev_default_employee_id
    roles_header = request.headers.get("X-Debug-Roles")

    if roles_header:
        roles = [r.strip() for r in roles_header.split(",")]
    else:
        roles = [r.strip() for r in settings.dev_default_roles.split(",")]

    if not tenant_id or not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Dev mode requires DEV_DEFAULT_TENANT_ID and DEV_DEFAULT_USERNAME.",
        )

    return AuthenticatedUser(
        sub=username,
        username=username,
        email=f"{username}@dev.local",
        tenant_id=str(tenant_id),
        roles=roles,
        effective_role=resolve_effective_role(roles),
        employee_id=employee_id,
        raw_token=None,
        token_claims={},
    )


async def _get_user_keycloak(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> AuthenticatedUser:
    token: Optional[str] = None
    if credentials is not None:
        token = credentials.credentials
    else:
        token = request.cookies.get("hris_access_token")

    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token",
        )

    payload = _decode_keycloak_token(token)

    tenant_id = payload.get("tenant_id")
    preferred_username = payload.get("preferred_username") or payload.get("email")
    email = payload.get("email")
    employee_id = payload.get("employee_id")
    roles = payload.get("roles") or payload.get("realm_access", {}).get("roles", [])

    if tenant_id is None:
        default_tenant_id = str(get_settings().dev_default_tenant_id or "").strip() or None
        resolved = automation_store.resolve_identity_link(
            module_name="srms",
            keycloak_sub=str(payload.get("sub") or "").strip() or None,
            email=str(email or "").strip().lower() or None,
            username=str(preferred_username or "").strip().lower() or None,
            preferred_tenant_id=None,
            avoid_tenant_id=default_tenant_id,
        )
        if not resolved and default_tenant_id:
            # Deterministic fallback for shared usernames across multiple tenants.
            resolved = automation_store.resolve_identity_mapping(
                tenant_id=default_tenant_id,
                module_name="srms",
                keycloak_sub=str(payload.get("sub") or "").strip() or None,
                email=str(email or "").strip().lower() or None,
                username=str(preferred_username or "").strip().lower() or None,
            )
        if resolved:
            tenant_id = str(resolved.get("tenant_id") or "").strip() or None
            if employee_id is None:
                employee_id = resolved.get("module_user_id")

    if tenant_id is None or preferred_username is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token missing required claims (tenant_id or username)",
        )

    return AuthenticatedUser(
        sub=payload.get("sub", ""),
        username=preferred_username,
        email=email,
        tenant_id=str(tenant_id),
        roles=roles,
        effective_role=resolve_effective_role(roles),
        employee_id=str(employee_id) if employee_id is not None else None,
        raw_token=token,
        token_claims=payload,
    )


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> AuthenticatedUser:
    settings = get_settings()
    if settings.auth_mode == "dev":
        return await _get_user_dev(request)
    if settings.auth_mode == "keycloak":
        return await _get_user_keycloak(request, credentials)
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Invalid AUTH_MODE configuration.",
    )
