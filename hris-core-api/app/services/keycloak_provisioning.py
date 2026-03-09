import secrets
import string
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

import httpx

from app.core.settings import get_settings

_SUPPORTED_HRIS_ROLES: List[str] = [
    "hris:super_admin",
    "hris:tenant_admin",
    "hris:hr_manager",
    "hris:line_manager",
    "hris:employee",
]


def _target_realm_from_issuer() -> Optional[str]:
    settings = get_settings()
    if (settings.keycloak_realm or "").strip():
        return settings.keycloak_realm.strip()
    issuer = str(settings.keycloak_issuer or "").strip()
    if not issuer:
        return None
    tail = issuer.rstrip("/").split("/")
    return tail[-1] if tail else None


def _admin_base_url() -> Optional[str]:
    settings = get_settings()
    issuer = str(settings.keycloak_issuer or "").strip()
    if not issuer:
        return None
    parsed = urlparse(issuer)
    if not parsed.scheme or not parsed.netloc:
        return None
    marker = "/realms/"
    idx = parsed.path.find(marker)
    root_path = parsed.path[:idx] if idx >= 0 else parsed.path
    return f"{parsed.scheme}://{parsed.netloc}{root_path}".rstrip("/")


def _generate_temp_password(length: int) -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%&*?"
    # Ensure complexity by forcing at least one character from each class.
    value = [
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.digits),
        secrets.choice("!@#$%&*?"),
    ]
    while len(value) < length:
        value.append(secrets.choice(alphabet))
    secrets.SystemRandom().shuffle(value)
    return "".join(value)


def _admin_access_token(client: httpx.Client) -> str:
    settings = get_settings()
    base = _admin_base_url()
    admin_realm = str(settings.keycloak_admin_realm or "master").strip() or "master"
    if not base:
        raise RuntimeError("Keycloak admin base URL/realm cannot be resolved")
    token_url = f"{base}/realms/{admin_realm}/protocol/openid-connect/token"

    if (settings.keycloak_admin_client_id or "").strip() and (settings.keycloak_admin_client_secret or "").strip():
        data = {
            "grant_type": "client_credentials",
            "client_id": settings.keycloak_admin_client_id,
            "client_secret": settings.keycloak_admin_client_secret,
        }
    else:
        data = {
            "grant_type": "password",
            "client_id": settings.keycloak_admin_client_id or "admin-cli",
            "username": settings.keycloak_admin_username or "",
            "password": settings.keycloak_admin_password or "",
        }
    resp = client.post(token_url, data=data)
    resp.raise_for_status()
    token = resp.json().get("access_token")
    if not token:
        raise RuntimeError("Failed to get Keycloak admin token")
    return str(token)


def _ensure_user_attributes(
    *,
    client: httpx.Client,
    headers: Dict[str, str],
    users_url: str,
    user_id: str,
    tenant_id: str,
    roles: Optional[List[str]],
    username: str,
    email: str,
) -> None:
    user_resp = client.get(f"{users_url}/{user_id}", headers=headers)
    user_resp.raise_for_status()
    user_payload = user_resp.json() if isinstance(user_resp.json(), dict) else {}
    attrs = user_payload.get("attributes") if isinstance(user_payload.get("attributes"), dict) else {}

    attrs["tenant_id"] = [tenant_id]
    if roles is not None:
        attrs["roles"] = roles

    fallback_name = (username or email or "hris-user").split("@", 1)[0].replace(".", " ").replace("_", " ").strip()
    if not fallback_name:
        fallback_name = "HRIS User"
    first_name = str(user_payload.get("firstName") or "").strip() or fallback_name.title()
    last_name = str(user_payload.get("lastName") or "").strip() or "User"

    update_payload = {
        "username": username,
        "email": email,
        "attributes": attrs,
        "enabled": True,
        "emailVerified": True,
        "firstName": first_name,
        "lastName": last_name,
    }
    updated = client.put(
        f"{users_url}/{user_id}",
        headers=headers,
        json=update_payload,
    )
    updated.raise_for_status()


def _normalized_roles(default_role: str, roles: Optional[List[str]]) -> List[str]:
    merged = list(roles or [])
    if default_role:
        merged.append(default_role)
    filtered: List[str] = []
    for role in _SUPPORTED_HRIS_ROLES:
        if role in merged and role not in filtered:
            filtered.append(role)
    return filtered or ["hris:employee"]


def _assign_realm_roles(
    *,
    client: httpx.Client,
    headers: Dict[str, str],
    base: str,
    realm: str,
    user_id: str,
    target_roles: List[str],
) -> None:
    role_representations: List[Dict[str, str]] = []
    for role_name in target_roles:
        role_resp = client.get(f"{base}/admin/realms/{realm}/roles/{role_name}", headers=headers)
        role_resp.raise_for_status()
        role_payload = role_resp.json() if isinstance(role_resp.json(), dict) else {}
        role_id = str(role_payload.get("id") or "").strip()
        role_name_value = str(role_payload.get("name") or role_name).strip()
        if role_id and role_name_value:
            role_representations.append({"id": role_id, "name": role_name_value})

    mapping_url = f"{base}/admin/realms/{realm}/users/{user_id}/role-mappings/realm"
    current_resp = client.get(mapping_url, headers=headers)
    current_resp.raise_for_status()
    current_roles = current_resp.json() if isinstance(current_resp.json(), list) else []
    current_role_names = {str(row.get("name") or "").strip() for row in current_roles if isinstance(row, dict)}
    target_role_names = {row["name"] for row in role_representations}
    managed_current = [row for row in current_roles if isinstance(row, dict) and str(row.get("name") or "") in _SUPPORTED_HRIS_ROLES]

    to_add = [row for row in role_representations if row["name"] not in current_role_names]
    to_remove = [row for row in managed_current if str(row.get("name") or "").strip() not in target_role_names]

    if to_add:
        add_resp = client.post(mapping_url, headers=headers, json=to_add)
        add_resp.raise_for_status()
    if to_remove:
        remove_resp = client.request("DELETE", mapping_url, headers=headers, json=to_remove)
        remove_resp.raise_for_status()


def ensure_user_and_temp_password(
    *,
    email: str,
    username: str,
    tenant_id: str,
    default_role: str = "hris:employee",
    roles: Optional[List[str]] = None,
    force_temp_password: bool = False,
) -> Dict[str, Optional[str]]:
    settings = get_settings()
    if not settings.keycloak_issuer:
        return {"status": "skipped", "reason": "keycloak_not_configured", "user_id": None, "temporary_password": None}

    base = _admin_base_url()
    realm = _target_realm_from_issuer()
    if not base or not realm:
        return {"status": "skipped", "reason": "keycloak_admin_resolution_failed", "user_id": None, "temporary_password": None}

    send_temp_password = bool(settings.onboarding_send_temp_password_email or force_temp_password)
    target_email = str(email or "").strip().lower()
    target_username = str(username or target_email).strip().lower()
    if not target_email:
        return {"status": "skipped", "reason": "missing_email", "user_id": None, "temporary_password": None}
    role_source_missing = roles == []
    resolved_roles = (
        None
        if role_source_missing
        else _normalized_roles(default_role=default_role, roles=roles)
    )

    users_url = f"{base}/admin/realms/{realm}/users"
    with httpx.Client(timeout=settings.http_client_timeout_seconds) as client:
        token = _admin_access_token(client)
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        query = client.get(users_url, headers=headers, params={"username": target_username, "exact": "true"})
        query.raise_for_status()
        rows = query.json() if isinstance(query.json(), list) else []
        user = next((row for row in rows if str(row.get("username", "")).lower() == target_username), None)
        user_id: Optional[str] = None
        status = "existing"

        if user is None:
            payload = {
                "username": target_username,
                "email": target_email,
                "enabled": True,
                "emailVerified": True,
                "attributes": {"tenant_id": [tenant_id], "roles": (resolved_roles or [default_role])},
            }
            created = client.post(users_url, headers=headers, json=payload)
            created.raise_for_status()
            status = "created"
            query2 = client.get(users_url, headers=headers, params={"username": target_username, "exact": "true"})
            query2.raise_for_status()
            rows2 = query2.json() if isinstance(query2.json(), list) else []
            user = next((row for row in rows2 if str(row.get("username", "")).lower() == target_username), None)

        if user is not None:
            user_id = str(user.get("id") or "").strip() or None

        if user_id:
            _ensure_user_attributes(
                client=client,
                headers=headers,
                users_url=users_url,
                user_id=user_id,
                tenant_id=tenant_id,
                roles=resolved_roles,
                username=target_username,
                email=target_email,
            )
            if resolved_roles is not None:
                _assign_realm_roles(
                    client=client,
                    headers=headers,
                    base=base,
                    realm=realm,
                    user_id=user_id,
                    target_roles=resolved_roles,
                )

        temporary_password = None
        if send_temp_password and user_id:
            temporary_password = _generate_temp_password(settings.onboarding_temp_password_length)
            reset_url = f"{users_url}/{user_id}/reset-password"
            reset_payload = {"type": "password", "value": temporary_password, "temporary": True}
            reset = client.put(reset_url, headers=headers, json=reset_payload)
            reset.raise_for_status()

        return {
            "status": status,
            "reason": None,
            "user_id": user_id,
            "temporary_password": temporary_password,
        }
