from urllib.parse import urlparse

import httpx

from app.core.settings import get_settings
from app.services.keycloak_provisioning import _admin_access_token, _admin_base_url, _target_realm_from_issuer


AUDIENCE_MAPPER_NAME = "hris-core-api-audience"


def _ensure_core_api_audience_mapper(client: httpx.Client, *, base: str, realm: str,
                                     client_uuid: str, headers: dict, audience: str) -> str:
    """Idempotently ensure portal access tokens are explicitly issued for Core."""
    endpoint = f"{base}/admin/realms/{realm}/clients/{client_uuid}/protocol-mappers/models"
    response = client.get(endpoint, headers=headers)
    response.raise_for_status()
    expected_config = {
        "included.client.audience": audience,
        "id.token.claim": "false",
        "access.token.claim": "true",
        "userinfo.token.claim": "false",
        "introspection.token.claim": "true",
    }
    existing = next(
        (row for row in response.json() if row.get("name") == AUDIENCE_MAPPER_NAME),
        None,
    )
    payload = {
        "name": AUDIENCE_MAPPER_NAME,
        "protocol": "openid-connect",
        "protocolMapper": "oidc-audience-mapper",
        "consentRequired": False,
        "config": expected_config,
    }
    if existing is None:
        created = client.post(endpoint, headers=headers, json=payload)
        created.raise_for_status()
        return "created"

    mapper_id = str(existing.get("id") or "").strip()
    current_config = existing.get("config") or {}
    if (existing.get("protocolMapper") == payload["protocolMapper"] and
            all(str(current_config.get(key, "")) == value for key, value in expected_config.items())):
        return "unchanged"
    if not mapper_id:
        raise RuntimeError("Existing HRIS Core audience mapper does not expose a stable id")
    payload["id"] = mapper_id
    updated = client.put(f"{endpoint}/{mapper_id}", headers=headers, json=payload)
    updated.raise_for_status()
    return "updated"


def configure_keycloak_portal_client_if_enabled() -> dict:
    """Add canonical BFF callback/origin without deleting operator-managed URIs."""
    settings = get_settings()
    if not settings.keycloak_manage_portal_client_settings:
        return {"configured": False, "reason": "disabled"}
    callback = str(settings.auth_sso_callback_url or "").strip()
    if not callback:
        return {"configured": False, "reason": "callback_not_configured"}
    parsed_callback = urlparse(callback)
    if parsed_callback.scheme not in {"http", "https"} or not parsed_callback.netloc:
        raise RuntimeError("AUTH_SSO_CALLBACK_URL must be an absolute http(s) URL")
    base, realm = _admin_base_url(), _target_realm_from_issuer()
    if not base or not realm:
        raise RuntimeError("Keycloak admin URL/realm cannot be resolved")
    portal_origin = str(settings.portal_base_url or "").rstrip("/")
    with httpx.Client(timeout=settings.http_client_timeout_seconds, trust_env=False) as client:
        token = _admin_access_token(client)
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        lookup = client.get(
            f"{base}/admin/realms/{realm}/clients", headers=headers,
            params={"clientId": settings.keycloak_portal_client_id},
        )
        lookup.raise_for_status()
        matches = [row for row in lookup.json() if row.get("clientId") == settings.keycloak_portal_client_id]
        if len(matches) != 1:
            raise RuntimeError("Expected exactly one Keycloak portal client")
        payload = matches[0]
        client_uuid = payload.get("id")
        redirects = list(payload.get("redirectUris") or [])
        origins = list(payload.get("webOrigins") or [])
        if callback not in redirects:
            redirects.append(callback)
        if portal_origin and portal_origin not in origins:
            origins.append(portal_origin)
        payload.update({"redirectUris": redirects, "webOrigins": origins, "enabled": True})
        updated = client.put(f"{base}/admin/realms/{realm}/clients/{client_uuid}", headers=headers, json=payload)
        updated.raise_for_status()
        audience_mapper = _ensure_core_api_audience_mapper(
            client,
            base=base,
            realm=realm,
            client_uuid=client_uuid,
            headers=headers,
            audience=(str(settings.keycloak_audience or "hris-core-api").split(",")[0].strip() or "hris-core-api"),
        )
    return {
        "configured": True, "realm": realm, "client_id": settings.keycloak_portal_client_id,
        "callback": callback, "portal_origin": portal_origin, "audience_mapper": audience_mapper,
    }
