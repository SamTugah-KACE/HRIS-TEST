from typing import List, Optional

import httpx
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from pydantic import BaseModel

from app.core.settings import get_settings

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
    raw_token: Optional[str] = None


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
    if not settings.keycloak_jwks_url or not settings.keycloak_issuer or not settings.keycloak_audience:
        raise RuntimeError("Keycloak is not configured but auth_mode=keycloak")

    try:
        response = httpx.get(str(settings.keycloak_jwks_url), timeout=5.0)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise RuntimeError(f"Unable to fetch JWKS from Keycloak: {exc}") from exc

    jwks = response.json()
    try:
        payload = jwt.decode(
            token,
            jwks,
            algorithms=["RS256"],
            audience=settings.keycloak_audience,
            issuer=str(settings.keycloak_issuer),
            options={"verify_aud": True, "verify_iss": True},
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
        raw_token=None,
    )


async def _get_user_keycloak(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> AuthenticatedUser:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
        )

    token = credentials.credentials
    payload = _decode_keycloak_token(token)

    tenant_id = payload.get("tenant_id")
    preferred_username = payload.get("preferred_username") or payload.get("email")
    email = payload.get("email")
    roles = payload.get("roles") or payload.get("realm_access", {}).get("roles", [])

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
        raw_token=token,
    )


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> AuthenticatedUser:
    settings = get_settings()
    if settings.auth_mode == "dev":
        return await _get_user_dev(request)
    if settings.auth_mode == "keycloak":
        return await _get_user_keycloak(credentials)
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Invalid AUTH_MODE configuration.",
    )
