"""
Module launch URL resolution for the HRIS module catalog.

Builds optional *native application* entry URLs (Angular / React module UIs) from
tenant registry mappings and Core settings. URLs are validated before exposure in
JSON responses to reduce open-redirect and malicious-link risks in the portal.

Security model (summary):
- Only http/https schemes; credentials embedded in URLs are rejected.
- Production defaults expect https unless MODULE_LAUNCH_ALLOW_HTTP is enabled for dev.
- Optional host suffix allowlist (MODULE_LAUNCH_HOST_SUFFIX_ALLOWLIST) restricts
  which hostnames may appear in catalog payloads when non-empty.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from app.core.settings import Settings, get_settings
from app.models.tenant_mapping import TenantMapping

# Tenant slug / subdomain segments interpolated into domain templates must be conservative
# to avoid template injection or path traversal in composed URLs.
_SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def _segment_or_none(raw: Optional[str]) -> Optional[str]:
    """Return stripped segment if it matches _SAFE_SEGMENT; otherwise None."""
    if raw is None:
        return None
    text = str(raw).strip()
    if not text or not _SAFE_SEGMENT.fullmatch(text):
        return None
    return text


def _derive_native_app_url(module_id: str, mapping: TenantMapping, settings: Settings) -> Optional[str]:
    """
    Compute the browser entry URL for the module's own SPA, if configuration allows.

    SRMS: {SRMS_BASE_URL}/{slug}/dashboard (path-based tenancy in replica docs).
    eAppraisal: either a shared static SPA origin or a tenant-aware
    ``{subdomain}`` template. Tenant identity is still carried separately in
    the signed handoff payload and response.
    eLeave: domain template with {subdomain} placeholder.
    """
    normalized = str(module_id or "").strip().lower()
    if normalized == "srms":
        base = str(settings.srms_base_url or "").strip().rstrip("/")
        slug = _segment_or_none(mapping.srms_slug)
        if not base or not slug:
            return None
        return f"{base}/{slug}/dashboard"

    if normalized == "eappraisal":
        template = str(settings.eappraisal_domain_template or "").strip()
        sub = _segment_or_none(mapping.eappraisal_subdomain)
        # A mapped native tenant is required in both deployment topologies:
        # - current shared origin: https://appraisal.example.com
        # - future per-tenant origin: https://{subdomain}.appraisal.example.com
        # The handoff endpoint returns `sub` separately for the Appraisal SSO
        # bridge, so accepting a static origin does not discard tenant context.
        if not template or not sub:
            return None
        if "{subdomain}" in template:
            return template.format(subdomain=sub).rstrip("/")
        return template.rstrip("/")

    if normalized == "eleave":
        template = str(settings.eleave_domain_template or "").strip()
        sub = _segment_or_none(mapping.eleave_subdomain)
        if not template or "{subdomain}" not in template or not sub:
            return None
        base = template.format(subdomain=sub).rstrip("/")
        if settings.eleave_use_tenant_path:
            return f"{base}/{sub}/dashboard"
        return f"{base}/dashboard"

    return None


def _hostname_matches_allowlist(hostname: str, suffixes: List[str]) -> bool:
    """True if hostname equals or ends with one of the configured suffix entries."""
    host = hostname.lower().strip(".")
    if not host:
        return False
    for suffix in suffixes:
        suf = suffix.lower().strip().strip(".")
        if not suf:
            continue
        if host == suf or host.endswith(f".{suf}"):
            return True
    return False


def validate_catalog_launch_url(url: str, settings: Optional[Settings] = None) -> bool:
    """
    Return True if *url* is safe to embed in the module catalog for clients.

    Rejects:
    - non-http(s) schemes
    - missing hostname
    - userinfo in netloc (e.g. https://user:pass@host)
    - http when MODULE_LAUNCH_ALLOW_HTTP is false
    - host not matching MODULE_LAUNCH_HOST_SUFFIX_ALLOWLIST when that list is non-empty
    """
    cfg = settings or get_settings()
    text = str(url or "").strip()
    if not text:
        return False
    parsed = urlparse(text)
    scheme = (parsed.scheme or "").lower()
    if scheme not in {"http", "https"}:
        return False
    if scheme == "http" and not bool(cfg.module_launch_allow_http):
        return False
    netloc = parsed.netloc or ""
    if "@" in netloc:
        # Credentials in URL are never required for catalog links and are a common abuse vector.
        return False
    hostname = (parsed.hostname or "").strip().lower()
    if not hostname:
        return False
    raw_list = str(cfg.module_launch_host_suffix_allowlist or "").strip()
    if not raw_list:
        return True
    suffixes = [part.strip() for part in raw_list.split(",") if part.strip()]
    if not suffixes:
        return True
    return _hostname_matches_allowlist(hostname, suffixes)


def build_module_launch_descriptor(
    module_id: str,
    mapping: TenantMapping,
    *,
    settings: Optional[Settings] = None,
    expose_native_url: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    Build the `launch` object for a single catalog entry.

    When native URL cannot be derived or fails validation, returns a descriptor
    with native_app_url=None and native_entry_available=False so the portal can
    fall back to in-portal summary routes only.
    """
    cfg = settings or get_settings()
    candidate = _derive_native_app_url(module_id, mapping, cfg)
    if not candidate:
        return {
            "native_app_url": None,
            "native_entry_available": False,
            "open_mode": str(cfg.module_launch_open_mode or "new_tab"),
            "portal_summary_note": "native_url_not_configured",
        }

    if not validate_catalog_launch_url(candidate, cfg):
        return {
            "native_app_url": None,
            "native_entry_available": False,
            "open_mode": str(cfg.module_launch_open_mode or "new_tab"),
            "portal_summary_note": "native_url_failed_policy_validation",
        }

    mode = str(cfg.module_launch_open_mode or "new_tab").strip().lower()
    if mode not in {"new_tab", "same_window"}:
        mode = "new_tab"

    should_expose = bool(cfg.module_launch_expose_native_urls) if expose_native_url is None else bool(expose_native_url)
    if not should_expose:
        return {
            "native_app_url": None,
            "native_entry_available": True,
            "open_mode": mode,
            "portal_summary_note": "native_url_hidden_by_policy",
        }

    return {
        "native_app_url": candidate,
        "native_entry_available": True,
        "open_mode": mode,
        "portal_summary_note": None,
    }
