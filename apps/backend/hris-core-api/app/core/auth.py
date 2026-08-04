from typing import Dict, List, Optional

import httpx
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from pydantic import BaseModel

from app.core.settings import get_settings
from app.services import automation_store
from app.services.tenant_registry_client import list_tenant_mappings

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


def _http_conflict(code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={"code": code, "message": message},
    )


def _resolve_tenant_id_with_conflict_guard(
    payload: Dict[str, object],
    token_tenant_id: Optional[str],
    preferred_tenant_hint: Optional[str],
    email: Optional[str],
    preferred_username: Optional[str],
) -> tuple[Optional[str], Optional[Dict[str, object]]]:
    """
    Deterministic precedence:
    1) token tenant claim (authoritative when present),
    2) canonical identity link resolution,
    3) no fallback (caller may apply super-admin default tenant policy).
    """
    settings = get_settings()
    resolved_link: Optional[Dict[str, object]] = None
    tenant_id = str(token_tenant_id or "").strip() or None
    default_tenant_id = str(settings.dev_default_tenant_id or "").strip() or None

    resolved = automation_store.resolve_identity_link(
        module_name="srms",
        keycloak_sub=str(payload.get("sub") or "").strip() or None,
        email=str(email or "").strip().lower() or None,
        username=str(preferred_username or "").strip().lower() or None,
        preferred_tenant_id=preferred_tenant_hint,
        avoid_tenant_id=default_tenant_id,
    )
    if not resolved:
        resolved = automation_store.resolve_identity_link(
            module_name="keycloak",
            keycloak_sub=str(payload.get("sub") or "").strip() or None,
            email=str(email or "").strip().lower() or None,
            username=str(preferred_username or "").strip().lower() or None,
            preferred_tenant_id=preferred_tenant_hint,
            avoid_tenant_id=default_tenant_id,
        )
    if isinstance(resolved, dict):
        resolved_link = resolved

    resolved_tenant_id = (
        str((resolved_link or {}).get("tenant_id") or "").strip() or None
    )
    if tenant_id and resolved_tenant_id and tenant_id != resolved_tenant_id:
        raise _http_conflict(
            "AUTH_TENANT_CONFLICT",
            "Token tenant does not match canonical identity mapping tenant.",
        )
    if not tenant_id and resolved_tenant_id:
        tenant_id = resolved_tenant_id
    return tenant_id, resolved_link


def _extract_str_claim(payload: Dict[str, object], *keys: str) -> Optional[str]:
    for key in keys:
        raw = payload.get(key)
        if isinstance(raw, str):
            value = raw.strip()
            if value:
                return value
        elif isinstance(raw, list):
            for item in raw:
                if isinstance(item, str):
                    value = item.strip()
                    if value:
                        return value

    attributes = payload.get("attributes")
    if isinstance(attributes, dict):
        for key in keys:
            attr_value = attributes.get(key)
            if isinstance(attr_value, str):
                value = attr_value.strip()
                if value:
                    return value
            elif isinstance(attr_value, list):
                for item in attr_value:
                    if isinstance(item, str):
                        value = item.strip()
                        if value:
                            return value
    return None


def _normalize_role_value(role: str) -> str:
    raw = str(role or "").strip()
    if not raw:
        return ""
    alias_map = {
        "super_admin": "hris:super_admin",
        "tenant_admin": "hris:tenant_admin",
        "hr_manager": "hris:hr_manager",
        "line_manager": "hris:line_manager",
        "employee": "hris:employee",
    }
    return alias_map.get(raw, raw)


def _extract_roles(payload: Dict[str, object]) -> List[str]:
    collected: List[str] = []

    direct_roles = payload.get("roles")
    if isinstance(direct_roles, list):
        collected.extend([str(role).strip() for role in direct_roles if str(role).strip()])
    elif isinstance(direct_roles, str):
        collected.extend([part.strip() for part in direct_roles.split(",") if part.strip()])

    realm_access = payload.get("realm_access")
    if isinstance(realm_access, dict):
        realm_roles = realm_access.get("roles")
        if isinstance(realm_roles, list):
            collected.extend([str(role).strip() for role in realm_roles if str(role).strip()])

    resource_access = payload.get("resource_access")
    if isinstance(resource_access, dict):
        for client_claim in resource_access.values():
            if not isinstance(client_claim, dict):
                continue
            client_roles = client_claim.get("roles")
            if isinstance(client_roles, list):
                collected.extend([str(role).strip() for role in client_roles if str(role).strip()])

    attributes = payload.get("attributes")
    if isinstance(attributes, dict):
        attr_roles = attributes.get("roles")
        if isinstance(attr_roles, list):
            collected.extend([str(role).strip() for role in attr_roles if str(role).strip()])
        elif isinstance(attr_roles, str):
            collected.extend([part.strip() for part in attr_roles.split(",") if part.strip()])

    normalized: List[str] = []
    seen = set()
    for role in collected:
        normalized_role = _normalize_role_value(role)
        if normalized_role and normalized_role not in seen:
            seen.add(normalized_role)
            normalized.append(normalized_role)
    return normalized


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


def _preferred_tenant_id_from_scoped_username(username: Optional[str]) -> Optional[str]:
    raw = str(username or "").strip().lower()
    if "__" not in raw:
        return None
    suffix = raw.rsplit("__", 1)[-1].strip()
    if not suffix:
        return None
    try:
        for t in list_tenant_mappings(limit=1000):
            if str(t.code or "").strip().lower() == suffix:
                return str(t.tenant_id or "").strip() or None
    except Exception:
        return None
    return None


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

    tenant_id = _extract_str_claim(payload, "tenant_id", "tenantId")
    preferred_username = _extract_str_claim(payload, "preferred_username", "username", "upn", "email")
    email = _extract_str_claim(payload, "email")
    employee_id = payload.get("employee_id")
    roles = _extract_roles(payload)
    is_platform_superadmin = "hris:super_admin" in roles
    preferred_tenant_hint = _preferred_tenant_id_from_scoped_username(preferred_username)

    tenant_id, resolved_link = _resolve_tenant_id_with_conflict_guard(
        payload=payload,
        token_tenant_id=tenant_id,
        preferred_tenant_hint=preferred_tenant_hint,
        email=email,
        preferred_username=preferred_username,
    )
    if isinstance(resolved_link, dict) and employee_id is None:
        employee_id = resolved_link.get("module_user_id")

    # Permit platform-level superadmin tokens that do not include tenant_id.
    if tenant_id is None and is_platform_superadmin:
        tenant_id = str(get_settings().dev_default_tenant_id or "").strip() or None

    if tenant_id is None or preferred_username is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token missing required claims (tenant_id or username)",
        )

    # Reconcile SRMS employee identity from persisted identity mappings to avoid
    # stale token employee_id drift after user migrations or upstream rekeys.
    resolved_srms_identity = automation_store.resolve_identity_mapping(
        tenant_id=str(tenant_id),
        module_name="srms",
        keycloak_sub=str(payload.get("sub") or "").strip() or None,
        email=str(email or "").strip().lower() or None,
        username=str(preferred_username or "").strip().lower() or None,
    )
    if not isinstance(resolved_srms_identity, dict):
        resolved_srms_identity = automation_store.resolve_identity_mapping(
            tenant_id=str(tenant_id),
            module_name="keycloak",
            keycloak_sub=str(payload.get("sub") or "").strip() or None,
            email=str(email or "").strip().lower() or None,
            username=str(preferred_username or "").strip().lower() or None,
        )
    if isinstance(resolved_srms_identity, dict):
        resolved_srms_tenant = str(resolved_srms_identity.get("tenant_id") or "").strip() or None
        if resolved_srms_tenant and resolved_srms_tenant != str(tenant_id):
            raise _http_conflict(
                "AUTH_IDENTITY_TENANT_MISMATCH",
                "Resolved SRMS identity mapping tenant does not match authenticated tenant.",
            )
        mapped_employee_id = str(resolved_srms_identity.get("module_user_id") or "").strip()
        if mapped_employee_id:
            employee_id = mapped_employee_id

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
