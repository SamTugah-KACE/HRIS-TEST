from __future__ import annotations

import hashlib
import re
import secrets
from typing import Any, Dict

import httpx

from app.core.settings import get_settings
from app.services import automation_store
from app.services.tenant_branding_service import get_tenant_branding


_HOST = re.compile(r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")
_SLUG = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_RESERVED = {"www","api","auth","admin","support","status","mail","smtp","keycloak","registry","static","assets"}


def normalize_hostname(value: str) -> str:
    host = str(value or "").strip().lower().split(":", 1)[0].rstrip(".")
    if host in {"localhost", "127.0.0.1"}:
        return host
    if not _HOST.fullmatch(host):
        raise ValueError("Hostname is invalid")
    return host


def register_platform_slug(*, tenant_id: str, slug: str) -> Dict[str, Any]:
    normalized = str(slug or "").strip().lower()
    if not _SLUG.fullmatch(normalized) or normalized in _RESERVED:
        raise ValueError("Tenant slug is invalid or reserved")
    hostname = f"{normalized}.{get_settings().platform_base_domain.strip().lower()}"
    existing = automation_store.get_tenant_domain(hostname=hostname)
    if existing and str(existing.get("tenant_id")) != tenant_id:
        raise ValueError("Tenant hostname is already assigned")
    automation_store.upsert_tenant_domain(
        hostname=hostname, tenant_id=tenant_id, domain_type="platform", status="verified", verification_hash=None
    )
    return {"hostname": hostname, "status": "verified", "domain_type": "platform"}


def request_custom_domain(*, tenant_id: str, hostname: str) -> Dict[str, Any]:
    normalized = normalize_hostname(hostname)
    existing = automation_store.get_tenant_domain(hostname=normalized)
    if existing and str(existing.get("tenant_id")) != tenant_id:
        raise ValueError("Custom domain is already assigned")
    token = secrets.token_urlsafe(32)
    verification_hash = hashlib.sha256(token.encode()).hexdigest()
    automation_store.upsert_tenant_domain(
        hostname=normalized, tenant_id=tenant_id, domain_type="custom", status="pending", verification_hash=verification_hash
    )
    return {"hostname": normalized, "status": "pending", "dns_record": {"type": "TXT", "name": f"_hris-verification.{normalized}", "value": token}}


def verify_custom_domain(*, tenant_id: str, hostname: str, verification_token: str) -> Dict[str, Any]:
    normalized = normalize_hostname(hostname)
    row = automation_store.get_tenant_domain(hostname=normalized)
    if not row or str(row.get("tenant_id")) != tenant_id or str(row.get("domain_type")) != "custom":
        raise ValueError("Custom domain request was not found")
    expected = str(row.get("verification_hash") or "")
    if hashlib.sha256(str(verification_token).encode()).hexdigest() != expected:
        raise ValueError("Domain verification token is invalid")
    record_name = f"_hris-verification.{normalized}"
    try:
        response = httpx.get(
            "https://cloudflare-dns.com/dns-query",
            params={"name": record_name, "type": "TXT"},
            headers={"accept": "application/dns-json"},
            timeout=5.0,
            follow_redirects=False,
        )
        response.raise_for_status()
        answers = response.json().get("Answer") or []
        published = {
            str(answer.get("data") or "").strip().strip('"')
            for answer in answers if int(answer.get("type") or 0) == 16
        }
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        raise ValueError("DNS ownership could not be checked; try again later") from exc
    if not any(secrets.compare_digest(value, str(verification_token)) for value in published):
        raise ValueError(f"Required TXT record is not published at {record_name}")
    automation_store.verify_tenant_domain(hostname=normalized)
    return {"hostname": normalized, "status": "verified", "tls_status": "pending_provisioning"}


def public_branding_for_host(hostname: str) -> Dict[str, Any]:
    normalized = normalize_hostname(hostname)
    row = automation_store.get_tenant_domain(hostname=normalized)
    if not row or str(row.get("status")) != "verified":
        return {"known_tenant": False, "branding": {"brand_name": "HRIS Portal", "theme": {}}}
    branding = get_tenant_branding(str(row["tenant_id"]))
    allowed = {key: branding.get(key) for key in (
        "brand_name","short_name","logo_primary_uri","logo_symbol_uri","favicon_uri","login_background_uri","theme","locale","support_email"
    )}
    return {"known_tenant": True, "hostname": normalized, "branding": allowed}
