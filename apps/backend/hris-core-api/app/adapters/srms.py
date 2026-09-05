from typing import Any, Dict, List, Optional
import json
import time
import hmac
import hashlib
import base64
import secrets
import logging
from uuid import uuid4
from urllib.parse import urlparse

import httpx
from fastapi import HTTPException, status
from jose import jwt as jose_jwt

from app.adapters.base import SrmsAdapter
from app.clients.adapter_utils import (
    build_auth_headers,
    build_hris_metadata_headers,
    ensure_dict,
    get_json_from_candidate_paths,
    to_int,
    to_str,
)
from app.core.settings import get_settings
from app.models.tenant_mapping import TenantMapping
from app.services import automation_store

logger = logging.getLogger(__name__)


class HttpSrmsAdapter(SrmsAdapter):
    def __init__(self) -> None:
        self.settings = get_settings()
        self._runtime_session_token: Optional[str] = None
        self._runtime_session_token_expiry_epoch: float = 0.0
        self._runtime_session_token_retry_after_epoch: float = 0.0

    @staticmethod
    def _canonicalize_path(path: str) -> str:
        if not path:
            return path
        if path == "/":
            return path
        return path[:-1] if path.endswith("/") else path

    def _build_signed_headers_for_path(
        self,
        *,
        path: str,
        session_token: Optional[str],
        method: str = "GET",
        base_headers: Dict[str, str],
    ) -> Dict[str, str]:
        headers = dict(base_headers)
        token = (session_token or "").strip()
        if not token:
            return headers

        canonical_path = self._canonicalize_path(path)
        timestamp = str(int(time.time() * 1000))
        payload_hash = ""
        challenge = secrets.token_urlsafe(24)

        challenge_response = hmac.new(
            token.encode("utf-8"),
            challenge.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        signature_payload = f"{method.upper()}:{canonical_path}:{timestamp}:{payload_hash}:{challenge}"
        request_signature = hmac.new(
            token.encode("utf-8"),
            signature_payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        headers["X-Session-Token"] = token
        headers["X-Request-Timestamp"] = timestamp
        headers["X-Payload-Hash"] = payload_hash
        headers["X-Challenge"] = challenge
        headers["X-Challenge-Response"] = challenge_response
        headers["X-Request-Signature"] = request_signature
        return headers

    def _get_http_client(self) -> httpx.Client:
        return httpx.Client(timeout=self.settings.http_client_timeout_seconds)

    def _candidate_paths(self, hris_path: str, module_path: str) -> List[str]:
        hris_candidates = [hris_path]
        if hris_path.startswith("/api/hris/") and not hris_path.startswith("/api/hris/v1/"):
            versioned = hris_path.replace("/api/hris/", "/api/hris/v1/", 1)
            hris_candidates = [versioned, hris_path]

        mode = self.settings.module_adapter_mode.lower()
        # When MODULE_TOKEN_SECRET is configured, user-context SRMS auth is expected via
        # HRIS-contract routes. Avoid fallback to module-native endpoints that require SRMS JWT.
        if (self.settings.module_token_secret or "").strip() and hris_path.startswith("/api/hris/"):
            return hris_candidates
        if mode == "hris_contract":
            return hris_candidates
        if mode == "module_native":
            return [module_path]
        return [*hris_candidates, module_path]

    def _build_srms_headers(
        self,
        *,
        user_token: Optional[str],
        prefer_service_token: bool = False,
        tenant_id: Optional[str] = None,
        tenant_slug: Optional[str] = None,
        tenant_code: Optional[str] = None,
        employee_id: Optional[str] = None,
    ) -> Dict[str, str]:
        integration_token = (self.settings.srms_integration_token or "").strip() or None
        service_token = (self.settings.srms_service_token or "").strip() or None
        module_token = self._mint_srms_module_token(user_token, tenant_id=tenant_id)
        normalized_tenant_slug = self._normalize_tenant_slug(tenant_slug or tenant_code)
        if prefer_service_token:
            # Prefer the dedicated service token for machine-to-machine integration endpoints.
            token = service_token or integration_token or module_token or user_token
            fallback_token = None
        else:
            # Prefer SRMS module token for user-context routes; it matches SRMS replica auth contract.
            token = module_token or user_token or integration_token
            fallback_token = service_token
        headers = build_auth_headers(token, fallback_token)
        headers.update(
            build_hris_metadata_headers(
                module_name="srms",
                user_token=token,
                tenant_id=tenant_id,
                tenant_slug=normalized_tenant_slug,
                tenant_code=tenant_code,
                employee_id=employee_id,
            )
        )
        if (self.settings.srms_app_type or "").strip():
            headers["X-App-Type"] = self.settings.srms_app_type.strip()
        if (self.settings.srms_hris_shared_secret or "").strip():
            headers["X-HRIS-Shared-Secret"] = self.settings.srms_hris_shared_secret.strip()
        if (self.settings.srms_hris_service_token or "").strip():
            headers["X-HRIS-Service-Token"] = self.settings.srms_hris_service_token.strip()
        if (self.settings.srms_session_token or "").strip():
            headers["X-Session-Token"] = self.settings.srms_session_token.strip()
        raw_extra = (self.settings.srms_extra_headers_json or "").strip()
        if raw_extra:
            try:
                parsed = json.loads(raw_extra)
                if isinstance(parsed, dict):
                    for key, value in parsed.items():
                        if isinstance(key, str) and value is not None:
                            headers[key] = str(value)
            except json.JSONDecodeError:
                # Runtime validation already guards this; keep resilient.
                pass
        return headers

    @staticmethod
    def _decode_unverified_claims(token: Optional[str]) -> Dict[str, Any]:
        raw = (token or "").strip()
        if not raw:
            return {}
        parts = raw.split(".")
        if len(parts) < 2:
            return {}
        payload_b64 = parts[1]
        padded = payload_b64 + "=" * (-len(payload_b64) % 4)
        try:
            decoded = base64.urlsafe_b64decode(padded.encode("utf-8")).decode("utf-8")
            parsed = json.loads(decoded)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}

    def _mint_srms_module_token(self, user_token: Optional[str], *, tenant_id: Optional[str] = None) -> Optional[str]:
        secret = (self.settings.module_token_secret or "").strip()
        if not secret:
            return None
        claims = self._decode_unverified_claims(user_token)
        token_sub = str(claims.get("sub") or "").strip()
        token_email = str(claims.get("email") or "").strip().lower()
        token_username = str(claims.get("preferred_username") or "").strip().lower()
        preferred_username = str(token_username or token_email or token_sub or "").strip()
        resolved_module_user_id = ""

        tenant_id_value = str(tenant_id or "").strip()
        if tenant_id_value:
            try:
                resolved = automation_store.resolve_identity_mapping(
                    tenant_id=tenant_id_value,
                    module_name="srms",
                    keycloak_sub=token_sub or None,
                    email=token_email or None,
                    username=token_username or None,
                )
            except Exception:
                resolved = None
            if isinstance(resolved, dict):
                mapped_username = str(resolved.get("module_username") or "").strip()
                resolved_module_user_id = str(resolved.get("module_user_id") or "").strip()
                if mapped_username:
                    preferred_username = mapped_username
        if not preferred_username:
            return None
        subject = str(claims.get("sub") or preferred_username).strip()
        email = str(claims.get("email") or "").strip()

        roles = claims.get("roles")
        if not isinstance(roles, list):
            realm_access = claims.get("realm_access")
            if isinstance(realm_access, dict) and isinstance(realm_access.get("roles"), list):
                roles = realm_access.get("roles")
            else:
                roles = []

        now_epoch = int(time.time())
        payload = {
            "sub": subject,
            "preferred_username": preferred_username,
            "email": email,
            "module": "srms",
            "module_user_id": resolved_module_user_id,
            "roles": [str(role) for role in roles],
            "iat": now_epoch,
            "exp": now_epoch + 900,
        }
        try:
            return jose_jwt.encode(payload, secret, algorithm="HS256")
        except Exception:
            return None

    @staticmethod
    def _normalize_tenant_slug(value: Optional[str]) -> Optional[str]:
        raw = str(value or "").strip()
        if not raw:
            return None
        if "://" in raw:
            raw = raw.split("://", 1)[1]
        elif raw.startswith("http:/") or raw.startswith("https:/"):
            raw = raw.split(":/", 1)[1]
        raw = raw.strip("/")
        if "/" in raw:
            raw = raw.split("/", 1)[0]
        return raw or None

    def _auth_header_candidates(
        self,
        user_token: Optional[str],
        *,
        tenant_id: Optional[str] = None,
        tenant_slug: Optional[str] = None,
        tenant_code: Optional[str] = None,
        employee_id: Optional[str] = None,
    ) -> List[Dict[str, str]]:
        candidates: List[Dict[str, str]] = []
        minted_module_token = self._mint_srms_module_token(user_token, tenant_id=tenant_id)

        primary = self._build_srms_headers(
            user_token=user_token,
            tenant_id=tenant_id,
            tenant_slug=tenant_slug,
            tenant_code=tenant_code,
            employee_id=employee_id,
        )
        candidates.append(primary)

        # Adaptive fallback: if user token is rejected by module-native auth, retry with
        # configured SRMS bridge token when available.
        if (self.settings.srms_service_token or "").strip() and not minted_module_token:
            service_first = self._build_srms_headers(
                user_token=user_token,
                prefer_service_token=True,
                tenant_id=tenant_id,
                tenant_slug=tenant_slug,
                tenant_code=tenant_code,
                employee_id=employee_id,
            )
            if service_first.get("Authorization") != primary.get("Authorization"):
                candidates.append(service_first)

        return candidates

    @staticmethod
    def _append_authless_fallbacks(candidates: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """Add no-Authorization variants while preserving candidate order."""
        expanded: List[Dict[str, str]] = list(candidates)
        for headers in candidates:
            if "Authorization" not in headers:
                continue
            authless = dict(headers)
            authless.pop("Authorization", None)
            # Avoid duplicates while preserving original order.
            if not any(existing == authless for existing in expanded):
                expanded.insert(0, authless)
        return expanded

    def _integration_header_candidates(
        self,
        token: Optional[str],
        *,
        tenant_id: Optional[str] = None,
        tenant_slug: Optional[str] = None,
        tenant_code: Optional[str] = None,
    ) -> List[Dict[str, str]]:
        """
        Prefer secret-based service auth for integration inventory routes.

        Some SRMS deployments enforce bearer-token validation in middleware before route
        dependencies run. When shared-secret integration is enabled, trying an authless
        variant first avoids hard failure on stale bearer tokens while keeping bearer
        fallback for environments that still require Authorization.
        """
        base_candidates = self._auth_header_candidates(
            token,
            tenant_id=tenant_id,
            tenant_slug=tenant_slug,
            tenant_code=tenant_code,
        )
        if not (self.settings.srms_hris_shared_secret or "").strip():
            return base_candidates
        return self._append_authless_fallbacks(base_candidates)

    def _session_token_from_config_or_cache(self) -> Optional[str]:
        now = time.time()
        configured = (self.settings.srms_session_token or "").strip()
        if configured:
            return configured
        if self._runtime_session_token:
            # Accept cached token while valid and during a short grace window when SRMS
            # throttles token refresh calls.
            if self._runtime_session_token_expiry_epoch > now:
                return self._runtime_session_token
            if now <= self._runtime_session_token_expiry_epoch + 900:
                return self._runtime_session_token
        return None

    def _refresh_runtime_session_token(self, client: httpx.Client) -> Optional[str]:
        if not self.settings.srms_auto_session_token:
            return None
        if not self.settings.srms_base_url:
            return None
        if self._runtime_session_token_retry_after_epoch > time.time():
            return self._session_token_from_config_or_cache()

        headers: Dict[str, str] = {}
        app_type = (self.settings.srms_app_type or "superadmin").strip()
        if app_type:
            headers["X-App-Type"] = app_type
        bootstrap_token = (
            (self.settings.srms_integration_token or "").strip()
            or (self.settings.srms_service_token or "").strip()
        )
        if bootstrap_token:
            headers["Authorization"] = f"Bearer {bootstrap_token}"
        if (self.settings.srms_hris_shared_secret or "").strip():
            headers["X-HRIS-Shared-Secret"] = self.settings.srms_hris_shared_secret.strip()
        if (self.settings.srms_hris_service_token or "").strip():
            headers["X-HRIS-Service-Token"] = self.settings.srms_hris_service_token.strip()
        # Keep the session-token bootstrap call traceable as HRIS integration traffic.
        headers.update(
            build_hris_metadata_headers(
                module_name="srms",
                user_token=bootstrap_token or None,
            )
        )

        url = f"{str(self.settings.srms_base_url).rstrip('/')}/api/auth/session-token"
        try:
            response = client.get(url, headers=headers)
            response.raise_for_status()
            payload = response.json()
            token = str(payload.get("session_token") or "").strip()
            if not token:
                return self._session_token_from_config_or_cache()
            expires_in = int(payload.get("expires_in") or 3600)
            self._runtime_session_token = token
            self._runtime_session_token_expiry_epoch = time.time() + max(60, expires_in - 30)
            self._runtime_session_token_retry_after_epoch = 0.0
            return token
        except (httpx.HTTPError, ValueError):
            # Handle SRMS auth/session-token throttling or transient failures gracefully.
            # Keep using the last known token (if any) and back off refresh attempts briefly.
            self._runtime_session_token_retry_after_epoch = time.time() + 30
            return self._session_token_from_config_or_cache()

    def _normalize_employee(self, raw: Dict[str, Any], mapping: TenantMapping, employee_id: str) -> Dict[str, Any]:
        first_name = to_str(raw.get("first_name") or raw.get("firstname")).strip()
        last_name = to_str(raw.get("last_name") or raw.get("lastname")).strip()
        full_name = to_str(raw.get("full_name")).strip() or " ".join([p for p in [first_name, last_name] if p]).strip()
        if not full_name:
            full_name = to_str(raw.get("name") or "Unknown Employee")
        return {
            "employee_id": to_str(raw.get("employee_id") or raw.get("id") or employee_id),
            "staff_id": to_str(raw.get("staff_id") or raw.get("staffId")),
            "full_name": full_name,
            "first_name": first_name or full_name.split(" ")[0],
            "last_name": last_name,
            "email": to_str(raw.get("email")),
            "organization": to_str(raw.get("organization") or mapping.name),
            "branch": to_str(raw.get("branch")),
            "department": to_str(raw.get("department")),
            "unit": to_str(raw.get("unit")),
            "rank": to_str(raw.get("rank")),
            "position": to_str(raw.get("position") or raw.get("title")),
            "employee_type": to_str(raw.get("employee_type") or raw.get("employeeType")),
            "status": to_str(raw.get("status") or ("Active" if raw.get("is_active", True) else "Inactive")),
            "hire_date": to_str(raw.get("hire_date")),
            "phone": to_str(raw.get("phone") or raw.get("phone_number")),
            "gender": to_str(raw.get("gender")),
        }

    @staticmethod
    def _name_or_value(value: Any) -> str:
        if isinstance(value, dict):
            return to_str(value.get("name") or value.get("label") or value.get("title"))
        return to_str(value)

    def _list_native_employee_context(
        self,
        *,
        mapping: TenantMapping,
        token: Optional[str],
        skip: int,
        limit: int,
    ) -> Dict[str, Dict[str, str]]:
        """
        Best-effort enrichment from module-native employee list that includes
        department/unit/branch relational names.
        """
        context_by_employee_id: Dict[str, Dict[str, str]] = {}
        if not self.settings.srms_base_url:
            return context_by_employee_id

        payload: Any = None
        with self._get_http_client() as client:
            session_token = self._session_token_from_config_or_cache()
            if not session_token:
                session_token = self._refresh_runtime_session_token(client)
            header_candidates = self._auth_header_candidates(
                token,
                tenant_id=mapping.tenant_id,
                tenant_slug=mapping.srms_slug,
                tenant_code=mapping.code,
            )
            paths = ["/api/employees", "/api/employees/"]
            params = {
                "organization_id": mapping.tenant_id,
                "skip": max(0, int(skip)),
                "limit": max(1, min(int(limit), 1000)),
            }
            for headers in header_candidates:
                if session_token:
                    headers["X-Session-Token"] = session_token
                try:
                    payload, _ = get_json_from_candidate_paths(
                        client=client,
                        base_url=str(self.settings.srms_base_url),
                        paths=paths,
                        headers=headers,
                        params=params,
                        module_name="SRMS",
                        payload_security_mode=self.settings.srms_payload_security_mode,
                        payload_signing_secret=self.settings.srms_payload_signing_secret,
                        payload_encryption_secret=self.settings.srms_payload_encryption_secret,
                        payload_session_token=session_token,
                        prepare_headers=lambda path, base_headers: self._build_signed_headers_for_path(
                            path=path,
                            session_token=session_token,
                            method="GET",
                            base_headers=base_headers,
                        ),
                    )
                    break
                except HTTPException:
                    continue

        records: List[Dict[str, Any]] = []
        if isinstance(payload, dict):
            if isinstance(payload.get("employees"), list):
                records = [r for r in payload.get("employees", []) if isinstance(r, dict)]
            elif isinstance(payload.get("data"), list):
                records = [r for r in payload.get("data", []) if isinstance(r, dict)]
        elif isinstance(payload, list):
            records = [r for r in payload if isinstance(r, dict)]

        for row in records:
            employee_id = to_str(row.get("id") or row.get("employee_id")).strip()
            if not employee_id:
                continue
            context_by_employee_id[employee_id] = {
                "department": self._name_or_value(row.get("department")).strip(),
                "branch": self._name_or_value(row.get("branch")).strip(),
                "unit": self._name_or_value(row.get("unit")).strip(),
            }
        return context_by_employee_id

    def _extract_records(self, payload: Any) -> List[Dict[str, Any]]:
        if isinstance(payload, list):
            return [row for row in payload if isinstance(row, dict)]
        if isinstance(payload, dict):
            for key in ("organizations", "tenants", "items", "results", "data"):
                value = payload.get(key)
                if isinstance(value, list):
                    return [row for row in value if isinstance(row, dict)]
        return []

    def _normalize_organization(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        access_url = self._normalize_organization_domain(
            to_str(raw.get("tenant_url") or raw.get("access_url") or raw.get("accessUrl")).strip()
        )
        org_type = to_str(raw.get("type")).strip()
        org_nature = to_str(raw.get("nature")).strip()
        organization_type = " - ".join([value for value in [org_type, org_nature] if value]).strip()
        code = to_str(
            raw.get("code")
            or raw.get("organization_code")
            or raw.get("org_code")
            or raw.get("tenant_slug")
            or raw.get("slug")
            or access_url
            or raw.get("name")
        ).strip()
        status_raw = to_str(raw.get("status") or raw.get("lifecycle_status") or "").strip().lower()
        if not status_raw:
            is_active = raw.get("is_active")
            status_raw = "active" if is_active is not False else "inactive"
        return {
            "tenant_id": to_str(raw.get("tenant_id") or raw.get("organization_id") or raw.get("id")),
            # Preserve the native module's explicit federation identity and
            # routing metadata.  Dropping these fields made an otherwise valid
            # SRMS tenant look unprojected when the catalog evaluated it.
            "canonical_tenant_id": to_str(
                raw.get("canonical_tenant_id") or raw.get("hris_canonical_tenant_id")
            ).strip() or None,
            "srms_schema": to_str(
                raw.get("srms_schema") or raw.get("schema_name") or raw.get("schema")
            ).strip() or None,
            "name": to_str(raw.get("name") or raw.get("organization_name") or code),
            "code": code,
            "slug": to_str(raw.get("tenant_slug") or raw.get("slug")),
            "organization_type": organization_type or "N/A",
            "access_url": access_url,
            "type": org_type,
            "nature": org_nature,
            "status": "active" if status_raw == "active" else status_raw or "inactive",
            "modules": {
                "srms": True,
                "eappraisal": bool(raw.get("eappraisal_enabled", True)),
                "eleave": bool(raw.get("eleave_enabled", True)),
            },
        }

    def _normalize_organization_domain(self, value: str) -> str:
        raw = (value or "").strip()
        if not raw:
            return ""

        # Keep already valid absolute URLs unchanged.
        parsed = urlparse(raw)
        if parsed.scheme in ("http", "https") and parsed.netloc:
            return raw

        base = (self.settings.srms_base_url or "").strip().rstrip("/")
        if not base:
            return raw

        # Recover path-like values from malformed URLs such as:
        # - https:/tenant123
        # - tenant123
        # - /tenant123
        suffix = raw
        if "://" in raw:
            suffix = raw.split("://", 1)[1]
        elif raw.startswith("http:/") or raw.startswith("https:/"):
            suffix = raw.split(":/", 1)[1]

        suffix = suffix.lstrip("/")
        if not suffix:
            return base
        return f"{base}/{suffix}"

    def get_employee(self, mapping: TenantMapping, employee_id: str, token: Optional[str]) -> Dict[str, Any]:
        if not self.settings.srms_base_url:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SRMS base URL is not configured")

        headers = self._build_srms_headers(
            user_token=token,
            tenant_id=mapping.tenant_id,
            tenant_slug=mapping.srms_slug,
            tenant_code=mapping.code,
            employee_id=employee_id,
        )
        paths = self._candidate_paths(
            hris_path=f"/api/hris/employees/{employee_id}",
            module_path=f"/api/employees/{employee_id}",
        )

        with self._get_http_client() as client:
            session_token = self._session_token_from_config_or_cache()
            if not session_token:
                session_token = self._refresh_runtime_session_token(client)
                if session_token:
                    headers["X-Session-Token"] = session_token
            try:
                payload, _ = get_json_from_candidate_paths(
                    client=client,
                    base_url=str(self.settings.srms_base_url),
                    paths=paths,
                    headers=headers,
                    module_name="SRMS",
                    payload_security_mode=self.settings.srms_payload_security_mode,
                    payload_signing_secret=self.settings.srms_payload_signing_secret,
                    payload_encryption_secret=self.settings.srms_payload_encryption_secret,
                    payload_session_token=session_token,
                    prepare_headers=lambda path, base_headers: self._build_signed_headers_for_path(
                        path=path,
                        session_token=session_token,
                        method="GET",
                        base_headers=base_headers,
                    ),
                )
            except HTTPException as exc:
                if exc.status_code != status.HTTP_502_BAD_GATEWAY or not self.settings.srms_auto_session_token:
                    raise
                refreshed = self._refresh_runtime_session_token(client)
                if not refreshed:
                    raise
                headers["X-Session-Token"] = refreshed
                payload, _ = get_json_from_candidate_paths(
                    client=client,
                    base_url=str(self.settings.srms_base_url),
                    paths=paths,
                    headers=headers,
                    module_name="SRMS",
                    payload_security_mode=self.settings.srms_payload_security_mode,
                    payload_signing_secret=self.settings.srms_payload_signing_secret,
                    payload_encryption_secret=self.settings.srms_payload_encryption_secret,
                    payload_session_token=refreshed,
                    prepare_headers=lambda path, base_headers: self._build_signed_headers_for_path(
                        path=path,
                        session_token=refreshed,
                        method="GET",
                        base_headers=base_headers,
                    ),
                )

        source = ensure_dict(payload, context="SRMS employee")
        return self._normalize_employee(source, mapping, employee_id)

    def list_employees(
        self,
        mapping: TenantMapping,
        token: Optional[str],
        search: str = "",
        department: str = "",
        emp_status: str = "active",
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        if not self.settings.srms_base_url:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SRMS base URL is not configured")

        params = {"search": search, "department": department, "status": emp_status, "page": page, "page_size": page_size}
        headers = self._build_srms_headers(
            user_token=token,
            tenant_id=mapping.tenant_id,
            tenant_slug=mapping.srms_slug,
            tenant_code=mapping.code,
        )
        paths = self._candidate_paths(
            hris_path="/api/hris/employees",
            module_path="/api/employees",
        )

        with self._get_http_client() as client:
            session_token = self._session_token_from_config_or_cache()
            if not session_token:
                session_token = self._refresh_runtime_session_token(client)
                if session_token:
                    headers["X-Session-Token"] = session_token
            payload, _ = get_json_from_candidate_paths(
                client=client,
                base_url=str(self.settings.srms_base_url),
                paths=paths,
                headers=headers,
                params=params,
                module_name="SRMS",
                payload_security_mode=self.settings.srms_payload_security_mode,
                payload_signing_secret=self.settings.srms_payload_signing_secret,
                payload_encryption_secret=self.settings.srms_payload_encryption_secret,
                payload_session_token=session_token,
                prepare_headers=lambda path, base_headers: self._build_signed_headers_for_path(
                    path=path,
                    session_token=session_token,
                    method="GET",
                    base_headers=base_headers,
                ),
            )

        if isinstance(payload, dict):
            records = payload.get("employees")
            if records is None:
                records = payload.get("items")
            if records is None and isinstance(payload.get("results"), list):
                records = payload.get("results")
            if records is None and isinstance(payload.get("data"), list):
                records = payload.get("data")
            if isinstance(records, list):
                employees = [
                    self._normalize_employee(
                        r if isinstance(r, dict) else {},
                        mapping,
                        str(r.get("id", "")) if isinstance(r, dict) else "",
                    )
                    for r in records
                ]
                if employees and any(
                    not str(emp.get("department") or "").strip() and not str(emp.get("branch") or "").strip()
                    for emp in employees
                ):
                    native_context = self._list_native_employee_context(
                        mapping=mapping,
                        token=token,
                        skip=(page - 1) * page_size,
                        limit=page_size,
                    )
                    if native_context:
                        for employee in employees:
                            emp_id = str(employee.get("employee_id") or "").strip()
                            context_row = native_context.get(emp_id)
                            if not context_row:
                                continue
                            if not str(employee.get("department") or "").strip():
                                employee["department"] = context_row.get("department", "")
                            if not str(employee.get("branch") or "").strip():
                                employee["branch"] = context_row.get("branch", "")
                            if not str(employee.get("unit") or "").strip():
                                employee["unit"] = context_row.get("unit", "")
                total = to_int(payload.get("total", len(employees)), context="SRMS employees.total")
                return {
                    "employees": employees,
                    "total": total,
                    "page": to_int(payload.get("page", page), context="SRMS employees.page"),
                    "page_size": to_int(payload.get("page_size", page_size), context="SRMS employees.page_size"),
                    "total_pages": to_int(
                        payload.get("total_pages", max(1, (total + page_size - 1) // page_size)),
                        context="SRMS employees.total_pages",
                    ),
                }

        if isinstance(payload, list):
            employees = [
                self._normalize_employee(
                    r if isinstance(r, dict) else {},
                    mapping,
                    str(r.get("id", "")) if isinstance(r, dict) else "",
                )
                for r in payload
            ]
            if employees and any(
                not str(emp.get("department") or "").strip() and not str(emp.get("branch") or "").strip()
                for emp in employees
            ):
                native_context = self._list_native_employee_context(
                    mapping=mapping,
                    token=token,
                    skip=(page - 1) * page_size,
                    limit=page_size,
                )
                if native_context:
                    for employee in employees:
                        emp_id = str(employee.get("employee_id") or "").strip()
                        context_row = native_context.get(emp_id)
                        if not context_row:
                            continue
                        if not str(employee.get("department") or "").strip():
                            employee["department"] = context_row.get("department", "")
                        if not str(employee.get("branch") or "").strip():
                            employee["branch"] = context_row.get("branch", "")
                        if not str(employee.get("unit") or "").strip():
                            employee["unit"] = context_row.get("unit", "")
            total = len(employees)
            return {
                "employees": employees,
                "total": total,
                "page": page,
                "page_size": page_size,
                "total_pages": max(1, (total + page_size - 1) // page_size),
            }

        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="SRMS employee list payload is invalid")

    def get_self_employee_comprehensive(self, mapping: TenantMapping, token: Optional[str]) -> Dict[str, Any]:
        if not self.settings.srms_base_url:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SRMS base URL is not configured")

        paths = [
            "/api/hris/v1/employees/self/comprehensive",
            "/api/hris/v1/employees/self/comprehensive/",
            "/api/hris/employees/self/comprehensive",
            "/api/hris/employees/self/comprehensive/",
            "/api/employees/self/comprehensive",
            "/api/employees/self/comprehensive/",
        ]

        payload: Any = None
        last_exception: Optional[HTTPException] = None
        attempts: List[Dict[str, Any]] = []
        trace_id = uuid4().hex
        logger.info(
            "SRMS self-comprehensive request started",
            extra={
                "trace_id": trace_id,
                "tenant_id": mapping.tenant_id,
                "tenant_code": mapping.code,
            },
        )
        with self._get_http_client() as client:
            session_token = self._session_token_from_config_or_cache()
            if not session_token:
                session_token = self._refresh_runtime_session_token(client)
            for headers in self._auth_header_candidates(
                token,
                tenant_id=mapping.tenant_id,
                tenant_slug=mapping.srms_slug,
                tenant_code=mapping.code,
            ):
                if session_token:
                    headers["X-Session-Token"] = session_token
                try:
                    payload, selected_path = get_json_from_candidate_paths(
                        client=client,
                        base_url=str(self.settings.srms_base_url),
                        paths=paths,
                        headers=headers,
                        module_name="SRMS",
                        payload_security_mode=self.settings.srms_payload_security_mode,
                        payload_signing_secret=self.settings.srms_payload_signing_secret,
                        payload_encryption_secret=self.settings.srms_payload_encryption_secret,
                        payload_session_token=session_token,
                        prepare_headers=lambda path, base_headers: self._build_signed_headers_for_path(
                            path=path,
                            session_token=session_token,
                            method="GET",
                            base_headers=base_headers,
                        ),
                    )
                    logger.info(
                        "SRMS self-comprehensive request succeeded",
                        extra={
                            "trace_id": trace_id,
                            "tenant_id": mapping.tenant_id,
                            "tenant_code": mapping.code,
                            "selected_path": selected_path,
                            "session_token_used": bool(session_token),
                            "authorization_header_used": bool(headers.get("Authorization")),
                            "attempts_before_success": len(attempts),
                        },
                    )
                    break
                except HTTPException as exc:
                    last_exception = exc
                    attempts.append(
                        {
                            "trace_id": trace_id,
                            "attempt_number": len(attempts) + 1,
                            "status_code": exc.status_code,
                            "detail": str(exc.detail),
                            "authorization_header_used": bool(headers.get("Authorization")),
                            "session_token_used": bool(session_token),
                        }
                    )
                    if exc.status_code == status.HTTP_502_BAD_GATEWAY and self.settings.srms_auto_session_token:
                        refreshed = self._refresh_runtime_session_token(client)
                        if refreshed:
                            headers["X-Session-Token"] = refreshed
                            try:
                                payload, selected_path = get_json_from_candidate_paths(
                                    client=client,
                                    base_url=str(self.settings.srms_base_url),
                                    paths=paths,
                                    headers=headers,
                                    module_name="SRMS",
                                    payload_security_mode=self.settings.srms_payload_security_mode,
                                    payload_signing_secret=self.settings.srms_payload_signing_secret,
                                    payload_encryption_secret=self.settings.srms_payload_encryption_secret,
                                    payload_session_token=refreshed,
                                    prepare_headers=lambda path, base_headers: self._build_signed_headers_for_path(
                                        path=path,
                                        session_token=refreshed,
                                        method="GET",
                                        base_headers=base_headers,
                                    ),
                                )
                                session_token = refreshed
                                logger.info(
                                    "SRMS self-comprehensive request succeeded after session refresh",
                                    extra={
                                        "trace_id": trace_id,
                                        "tenant_id": mapping.tenant_id,
                                        "tenant_code": mapping.code,
                                        "selected_path": selected_path,
                                        "session_token_used": True,
                                        "authorization_header_used": bool(headers.get("Authorization")),
                                        "attempts_before_success": len(attempts),
                                    },
                                )
                                break
                            except HTTPException as refreshed_exc:
                                last_exception = refreshed_exc
                                attempts.append(
                                    {
                                        "trace_id": trace_id,
                                        "attempt_number": len(attempts) + 1,
                                        "status_code": refreshed_exc.status_code,
                                        "detail": str(refreshed_exc.detail),
                                        "authorization_header_used": bool(headers.get("Authorization")),
                                        "session_token_used": True,
                                    }
                                )
                    continue

        if payload is None and last_exception is not None:
            logger.warning(
                "SRMS self-comprehensive request failed; profile fallback path will be used",
                extra={
                    "trace_id": trace_id,
                    "tenant_id": mapping.tenant_id,
                    "tenant_code": mapping.code,
                    "attempt_count": len(attempts),
                    "attempts": attempts[-5:],
                    "last_status_code": last_exception.status_code,
                    "last_detail": str(last_exception.detail),
                },
            )
            raise last_exception

        source = ensure_dict(payload, context="SRMS self comprehensive")
        if isinstance(source.get("data"), dict):
            return ensure_dict(source.get("data"), context="SRMS self comprehensive.data")
        return source

    def get_dashboard_summary(self, mapping: TenantMapping, token: Optional[str]) -> Dict[str, Any]:
        if not self.settings.srms_base_url:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SRMS base URL is not configured")

        paths = self._candidate_paths(
            hris_path="/api/hris/dashboard/summary",
            module_path="/api/dashboard/summary",
        )

        payload: Any = None
        last_exception: Optional[HTTPException] = None

        with self._get_http_client() as client:
            session_token = self._session_token_from_config_or_cache()
            if not session_token:
                session_token = self._refresh_runtime_session_token(client)
            for headers in self._auth_header_candidates(
                token,
                tenant_id=mapping.tenant_id,
                tenant_slug=mapping.srms_slug,
                tenant_code=mapping.code,
            ):
                if session_token:
                    headers["X-Session-Token"] = session_token
                try:
                    payload, _ = get_json_from_candidate_paths(
                        client=client,
                        base_url=str(self.settings.srms_base_url),
                        paths=paths,
                        headers=headers,
                        module_name="SRMS",
                        payload_security_mode=self.settings.srms_payload_security_mode,
                        payload_signing_secret=self.settings.srms_payload_signing_secret,
                        payload_encryption_secret=self.settings.srms_payload_encryption_secret,
                        payload_session_token=session_token,
                        prepare_headers=lambda path, base_headers: self._build_signed_headers_for_path(
                            path=path,
                            session_token=session_token,
                            method="GET",
                            base_headers=base_headers,
                        ),
                    )
                    break
                except HTTPException as exc:
                    last_exception = exc
                    if exc.status_code != status.HTTP_502_BAD_GATEWAY or not self.settings.srms_auto_session_token:
                        continue
                    refreshed = self._refresh_runtime_session_token(client)
                    if not refreshed:
                        continue
                    headers["X-Session-Token"] = refreshed
                    try:
                        payload, _ = get_json_from_candidate_paths(
                            client=client,
                            base_url=str(self.settings.srms_base_url),
                            paths=paths,
                            headers=headers,
                            module_name="SRMS",
                            payload_security_mode=self.settings.srms_payload_security_mode,
                            payload_signing_secret=self.settings.srms_payload_signing_secret,
                            payload_encryption_secret=self.settings.srms_payload_encryption_secret,
                            payload_session_token=refreshed,
                            prepare_headers=lambda path, base_headers: self._build_signed_headers_for_path(
                                path=path,
                                session_token=refreshed,
                                method="GET",
                                base_headers=base_headers,
                            ),
                        )
                        session_token = refreshed
                        break
                    except HTTPException as refreshed_exc:
                        last_exception = refreshed_exc
                        continue

        if payload is None and last_exception is not None:
            raise last_exception

        if isinstance(payload, dict):
            source = payload.get("data") if isinstance(payload.get("data"), dict) else payload
            return {
                "total_employees": to_int(source.get("total_employees", source.get("totalEmployees", 0)), context="SRMS summary.total_employees"),
                "active_employees": to_int(source.get("active_employees", source.get("activeEmployees", 0)), context="SRMS summary.active_employees"),
                "inactive_employees": to_int(source.get("inactive_employees", source.get("inactiveEmployees", 0)), context="SRMS summary.inactive_employees"),
                "branches": to_int(source.get("branches", 0), context="SRMS summary.branches"),
                "departments": to_int(source.get("departments", 0), context="SRMS summary.departments"),
                "new_hires_this_month": to_int(source.get("new_hires_this_month", source.get("newHiresThisMonth", 0)), context="SRMS summary.new_hires_this_month"),
                "pending_enlistments": to_int(source.get("pending_enlistments", source.get("pendingApprovals", 0)), context="SRMS summary.pending_enlistments"),
            }

        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="SRMS dashboard payload is invalid")

    def list_organizations(self, token: Optional[str]) -> Dict[str, Any]:
        if not self.settings.srms_base_url:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SRMS base URL is not configured")

        integration_paths = [
            "/api/hris/v1/integration/tenants",
            "/api/hris/v1/integration/tenants/",
            "/api/hris/integration/tenants",
            "/api/hris/integration/tenants/",
            "/api/hris/v1/integrations/tenants",
            "/api/hris/v1/integrations/tenants/",
            "/api/hris/integrations/tenants",
            "/api/hris/integrations/tenants/",
        ]
        legacy_paths = self._candidate_paths(
            hris_path="/api/hris/organizations",
            module_path="/api/organizations/",
        )
        legacy_paths.append("/api/organizations")

        payload: Any = None
        last_exception: Optional[HTTPException] = None

        with self._get_http_client() as client:
            session_token = self._session_token_from_config_or_cache()
            if not session_token:
                session_token = self._refresh_runtime_session_token(client)
            header_candidates = self._integration_header_candidates(token)
            for headers in header_candidates:
                if session_token:
                    headers["X-Session-Token"] = session_token
                for paths in (integration_paths, legacy_paths):
                    try:
                        payload, _ = get_json_from_candidate_paths(
                            client=client,
                            base_url=str(self.settings.srms_base_url),
                            paths=paths,
                            headers=headers,
                            module_name="SRMS",
                            payload_security_mode=self.settings.srms_payload_security_mode,
                            payload_signing_secret=self.settings.srms_payload_signing_secret,
                            payload_encryption_secret=self.settings.srms_payload_encryption_secret,
                            payload_session_token=session_token,
                            prepare_headers=lambda path, base_headers: self._build_signed_headers_for_path(
                                path=path,
                                session_token=session_token,
                                method="GET",
                                base_headers=base_headers,
                            ),
                        )
                        break
                    except HTTPException as exc:
                        last_exception = exc
                        if exc.status_code == status.HTTP_502_BAD_GATEWAY and self.settings.srms_auto_session_token:
                            refreshed = self._refresh_runtime_session_token(client)
                            if refreshed:
                                headers["X-Session-Token"] = refreshed
                                try:
                                    payload, _ = get_json_from_candidate_paths(
                                        client=client,
                                        base_url=str(self.settings.srms_base_url),
                                        paths=paths,
                                        headers=headers,
                                        module_name="SRMS",
                                        payload_security_mode=self.settings.srms_payload_security_mode,
                                        payload_signing_secret=self.settings.srms_payload_signing_secret,
                                        payload_encryption_secret=self.settings.srms_payload_encryption_secret,
                                        payload_session_token=refreshed,
                                        prepare_headers=lambda path, base_headers: self._build_signed_headers_for_path(
                                            path=path,
                                            session_token=refreshed,
                                            method="GET",
                                            base_headers=base_headers,
                                        ),
                                    )
                                    session_token = refreshed
                                    break
                                except HTTPException as refreshed_exc:
                                    last_exception = refreshed_exc
                        continue
                if payload is not None:
                    break

        if payload is None and last_exception is not None:
            raise last_exception

        records: List[Dict[str, Any]] = []
        if isinstance(payload, dict):
            if isinstance(payload.get("tenants"), list):
                records = [row for row in payload["tenants"] if isinstance(row, dict)]
            data_block = payload.get("data")
            if not records and isinstance(data_block, dict) and isinstance(data_block.get("tenants"), list):
                records = [row for row in data_block["tenants"] if isinstance(row, dict)]
        if not records:
            records = self._extract_records(payload)
        organizations = [self._normalize_organization(row) for row in records]
        total = len(organizations)
        active = sum(1 for row in organizations if row.get("status") == "active")
        inactive = total - active
        return {
            "organizations": organizations,
            "summary": {
                "total": total,
                "active": active,
                "inactive": inactive,
            },
        }

    def list_integration_tenants(self, token: Optional[str]) -> Dict[str, Any]:
        if not self.settings.srms_base_url:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SRMS base URL is not configured")

        integration_paths = [
            "/api/hris/v1/integration/tenants",
            "/api/hris/v1/integration/tenants/",
            "/api/hris/integration/tenants",
            "/api/hris/integration/tenants/",
            "/api/hris/v1/integrations/tenants",
            "/api/hris/v1/integrations/tenants/",
            "/api/hris/integrations/tenants",
            "/api/hris/integrations/tenants/",
        ]

        payload: Any = None
        last_exception: Optional[HTTPException] = None
        with self._get_http_client() as client:
            session_token = self._session_token_from_config_or_cache()
            if not session_token:
                session_token = self._refresh_runtime_session_token(client)
            header_candidates = self._integration_header_candidates(token)
            for headers in header_candidates:
                if session_token:
                    headers["X-Session-Token"] = session_token
                try:
                    payload, _ = get_json_from_candidate_paths(
                        client=client,
                        base_url=str(self.settings.srms_base_url),
                        paths=integration_paths,
                        headers=headers,
                        module_name="SRMS",
                        payload_security_mode=self.settings.srms_payload_security_mode,
                        payload_signing_secret=self.settings.srms_payload_signing_secret,
                        payload_encryption_secret=self.settings.srms_payload_encryption_secret,
                        payload_session_token=session_token,
                        prepare_headers=lambda path, base_headers: self._build_signed_headers_for_path(
                            path=path,
                            session_token=session_token,
                            method="GET",
                            base_headers=base_headers,
                        ),
                    )
                    break
                except HTTPException as exc:
                    last_exception = exc
                    if exc.status_code == status.HTTP_502_BAD_GATEWAY and self.settings.srms_auto_session_token:
                        refreshed = self._refresh_runtime_session_token(client)
                        if refreshed:
                            headers["X-Session-Token"] = refreshed
                            try:
                                payload, _ = get_json_from_candidate_paths(
                                    client=client,
                                    base_url=str(self.settings.srms_base_url),
                                    paths=integration_paths,
                                    headers=headers,
                                    module_name="SRMS",
                                    payload_security_mode=self.settings.srms_payload_security_mode,
                                    payload_signing_secret=self.settings.srms_payload_signing_secret,
                                    payload_encryption_secret=self.settings.srms_payload_encryption_secret,
                                    payload_session_token=refreshed,
                                    prepare_headers=lambda path, base_headers: self._build_signed_headers_for_path(
                                        path=path,
                                        session_token=refreshed,
                                        method="GET",
                                        base_headers=base_headers,
                                    ),
                                )
                                session_token = refreshed
                                break
                            except HTTPException as refreshed_exc:
                                last_exception = refreshed_exc
                    continue
                if payload is not None:
                    break

        if payload is None and last_exception is not None:
            raise last_exception

        records: List[Dict[str, Any]] = []
        if isinstance(payload, dict):
            if isinstance(payload.get("tenants"), list):
                records = [row for row in payload["tenants"] if isinstance(row, dict)]
            data_block = payload.get("data")
            if not records and isinstance(data_block, dict) and isinstance(data_block.get("tenants"), list):
                records = [row for row in data_block["tenants"] if isinstance(row, dict)]
        if not records:
            records = self._extract_records(payload)

        organizations = [self._normalize_organization(row) for row in records]
        total = len(organizations)
        active = sum(1 for row in organizations if row.get("status") == "active")
        inactive = total - active
        return {
            "organizations": organizations,
            "summary": {
                "total": total,
                "active": active,
                "inactive": inactive,
            },
        }

    def provision_tenant(self, payload_body: Dict[str, Any]) -> Dict[str, Any]:
        """Create or retrieve an SRMS tenant projection by canonical UUID."""
        if not self.settings.srms_base_url:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SRMS base URL is not configured")
        paths = ["/api/hris/v1/integration/tenants"]
        response_payload: Any = None
        last_exception: Optional[HTTPException] = None
        with self._get_http_client() as client:
            session_token = self._session_token_from_config_or_cache() or self._refresh_runtime_session_token(client)
            for headers in self._integration_header_candidates(None):
                headers["Content-Type"] = "application/json"
                if session_token:
                    headers["X-Session-Token"] = session_token
                try:
                    response_payload, _ = get_json_from_candidate_paths(
                        client=client,
                        base_url=str(self.settings.srms_base_url),
                        paths=paths,
                        headers=headers,
                        method="POST",
                        json_body=payload_body,
                        module_name="SRMS",
                        payload_security_mode=self.settings.srms_payload_security_mode,
                        payload_signing_secret=self.settings.srms_payload_signing_secret,
                        payload_encryption_secret=self.settings.srms_payload_encryption_secret,
                        payload_session_token=session_token,
                        prepare_headers=lambda path, base_headers: self._build_signed_headers_for_path(
                            path=path,
                            session_token=session_token,
                            method="POST",
                            base_headers=base_headers,
                        ),
                    )
                    break
                except HTTPException as exc:
                    last_exception = exc
        if response_payload is None:
            if last_exception is not None:
                raise last_exception
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="SRMS tenant provisioning returned no payload")
        envelope = ensure_dict(response_payload, context="SRMS tenant provisioning response")
        data = ensure_dict(envelope.get("data"), context="SRMS tenant provisioning response.data") or envelope
        return data

    def activate_tenant_federation(self, native_tenant_id: str, canonical_tenant_id: str) -> Dict[str, Any]:
        if not self.settings.srms_base_url:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SRMS base URL is not configured")
        path = f"/api/hris/v1/integration/tenants/{native_tenant_id}/federation/activate"
        last_exception: Optional[HTTPException] = None
        with self._get_http_client() as client:
            session_token = self._session_token_from_config_or_cache() or self._refresh_runtime_session_token(client)
            for headers in self._integration_header_candidates(None):
                headers["Content-Type"] = "application/json"
                if session_token:
                    headers["X-Session-Token"] = session_token
                try:
                    payload, _ = get_json_from_candidate_paths(
                        client=client, base_url=str(self.settings.srms_base_url), paths=[path], headers=headers,
                        method="POST", json_body={"canonical_tenant_id": canonical_tenant_id}, module_name="SRMS",
                        payload_security_mode=self.settings.srms_payload_security_mode,
                        payload_signing_secret=self.settings.srms_payload_signing_secret,
                        payload_encryption_secret=self.settings.srms_payload_encryption_secret,
                        payload_session_token=session_token,
                        prepare_headers=lambda candidate, base_headers: self._build_signed_headers_for_path(
                            path=candidate, session_token=session_token, method="POST", base_headers=base_headers,
                        ),
                    )
                    envelope = ensure_dict(payload, context="SRMS federation activation response")
                    return ensure_dict(envelope.get("data"), context="SRMS federation activation response.data") or envelope
                except HTTPException as exc:
                    last_exception = exc
        if last_exception:
            raise last_exception
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="SRMS federation activation returned no payload")

    def list_tenant_users(
        self,
        tenant_id: str,
        token: Optional[str],
        *,
        limit: int = 2000,
        tenant_slug: Optional[str] = None,
        tenant_code: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not self.settings.srms_base_url:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SRMS base URL is not configured")
        tenant_id_str = str(tenant_id or "").strip()
        if not tenant_id_str:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="tenant_id is required")

        effective_limit = max(0, int(limit))
        def users_paths_for(target_tenant_id: str) -> List[str]:
            return [
                f"/api/hris/v1/integration/tenants/{target_tenant_id}/users",
                f"/api/hris/integration/tenants/{target_tenant_id}/users",
                f"/api/hris/v1/integrations/tenants/{target_tenant_id}/users",
                f"/api/hris/integrations/tenants/{target_tenant_id}/users",
            ]

        resolved_tenant_id = tenant_id_str
        slug_hint = self._normalize_tenant_slug(tenant_slug)
        code_hint = str(tenant_code or "").strip().lower()
        if slug_hint or code_hint:
            try:
                index_payload = self.list_integration_tenants(token)
                organizations = index_payload.get("organizations", []) if isinstance(index_payload, dict) else []
                if isinstance(organizations, list):
                    for org in organizations:
                        if not isinstance(org, dict):
                            continue
                        org_id = to_str(org.get("tenant_id")).strip()
                        if not org_id:
                            continue
                        org_slug = self._normalize_tenant_slug(
                            to_str(org.get("slug") or org.get("access_url") or org.get("code"))
                        )
                        org_code = to_str(org.get("code")).strip().lower()
                        if slug_hint and org_slug and slug_hint == org_slug:
                            resolved_tenant_id = org_id
                            break
                        if code_hint and org_code and code_hint == org_code:
                            resolved_tenant_id = org_id
                            break
            except Exception:
                # Best-effort optimization only; fall back to original tenant_id when resolution fails.
                pass

        payload: Any = None
        last_exception: Optional[HTTPException] = None
        tenant_id_attempts: List[str] = [tenant_id_str]
        if resolved_tenant_id and resolved_tenant_id != tenant_id_str:
            tenant_id_attempts.append(resolved_tenant_id)
        with self._get_http_client() as client:
            session_token = self._session_token_from_config_or_cache()
            if not session_token:
                session_token = self._refresh_runtime_session_token(client)
            for tenant_id_candidate in tenant_id_attempts:
                users_paths = users_paths_for(tenant_id_candidate)
                header_candidates = self._integration_header_candidates(
                    token,
                    tenant_id=tenant_id_str,
                    tenant_slug=tenant_slug,
                    tenant_code=tenant_code,
                )
                for headers in header_candidates:
                    if session_token:
                        headers["X-Session-Token"] = session_token
                    try:
                        payload, _ = get_json_from_candidate_paths(
                            client=client,
                            base_url=str(self.settings.srms_base_url),
                            paths=users_paths,
                            headers=headers,
                            params=({"limit": effective_limit} if effective_limit else {}),
                            module_name="SRMS",
                            payload_security_mode=self.settings.srms_payload_security_mode,
                            payload_signing_secret=self.settings.srms_payload_signing_secret,
                            payload_encryption_secret=self.settings.srms_payload_encryption_secret,
                            payload_session_token=session_token,
                            prepare_headers=lambda path, base_headers: self._build_signed_headers_for_path(
                                path=path,
                                session_token=session_token,
                                method="GET",
                                base_headers=base_headers,
                            ),
                        )
                        break
                    except HTTPException as exc:
                        last_exception = exc
                        if exc.status_code == status.HTTP_502_BAD_GATEWAY and self.settings.srms_auto_session_token:
                            refreshed = self._refresh_runtime_session_token(client)
                            if refreshed:
                                headers["X-Session-Token"] = refreshed
                                try:
                                    payload, _ = get_json_from_candidate_paths(
                                        client=client,
                                        base_url=str(self.settings.srms_base_url),
                                        paths=users_paths,
                                        headers=headers,
                                        params={"limit": effective_limit},
                                        module_name="SRMS",
                                        payload_security_mode=self.settings.srms_payload_security_mode,
                                        payload_signing_secret=self.settings.srms_payload_signing_secret,
                                        payload_encryption_secret=self.settings.srms_payload_encryption_secret,
                                        payload_session_token=refreshed,
                                        prepare_headers=lambda path, base_headers: self._build_signed_headers_for_path(
                                            path=path,
                                            session_token=refreshed,
                                            method="GET",
                                            base_headers=base_headers,
                                        ),
                                    )
                                    session_token = refreshed
                                    break
                                except HTTPException as refreshed_exc:
                                    last_exception = refreshed_exc
                        continue
                if payload is not None:
                    break

        if payload is None and last_exception is not None:
            raise last_exception

        users: List[Dict[str, Any]] = []
        if isinstance(payload, dict):
            if isinstance(payload.get("users"), list):
                users = [row for row in payload["users"] if isinstance(row, dict)]
            data_block = payload.get("data")
            if not users and isinstance(data_block, dict) and isinstance(data_block.get("users"), list):
                users = [row for row in data_block["users"] if isinstance(row, dict)]

        payload_data = payload.get("data") if isinstance(payload, dict) and isinstance(payload.get("data"), dict) else {}

        normalized_users = []
        for row in users:
            email = to_str(row.get("email")).lower()
            raw_roles = row.get("roles")
            primary_role = to_str(
                row.get("role")
                or row.get("role_name")
                or row.get("roleName")
                or row.get("designation")
                or row.get("user_type")
                or row.get("userType")
            )
            normalized_users.append(
                {
                    "user_id": to_str(row.get("user_id") or row.get("id")),
                    "username": to_str(row.get("username")) or email,
                    "email": email,
                    "is_active": bool(row.get("is_active", True)),
                    "roles": raw_roles if isinstance(raw_roles, (list, str)) else ([] if raw_roles is None else [to_str(raw_roles)]),
                    "role": primary_role,
                    "role_code": to_str(row.get("role_code")),
                    "role_name": to_str(row.get("role_name") or row.get("roleName")),
                    "designation": to_str(row.get("designation")),
                    "user_type": to_str(row.get("user_type") or row.get("userType")),
                    "access_level": to_str(row.get("access_level") or row.get("accessLevel")),
                    "permissions": row.get("permissions") if isinstance(row.get("permissions"), (list, dict, str)) else [],
                    "raw_permissions": row.get("raw_permissions") if row.get("raw_permissions") is not None else row.get("permissions"),
                    "is_admin": bool(row.get("is_admin", False)),
                    "is_manager": bool(row.get("is_manager", False)),
                }
            )

        return {
            "tenant_id": tenant_id_str,
            "tenant_slug": to_str(payload_data.get("tenant_slug") or payload.get("tenant_slug") if isinstance(payload, dict) else ""),
            "tenant_url": to_str(payload_data.get("tenant_url") or payload.get("tenant_url") if isinstance(payload, dict) else ""),
            "users": normalized_users,
            "total": len(normalized_users),
        }

    def provision_tenant_user(
        self,
        tenant_id: str,
        token: Optional[str],
        *,
        email: str,
        username: str,
        first_name: str = "",
        last_name: str = "",
        user_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        tenant_slug: Optional[str] = None,
        tenant_code: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not self.settings.srms_base_url:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SRMS base URL is not configured")
        tenant_id_str = str(tenant_id or "").strip()
        if not tenant_id_str:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="tenant_id is required")

        email_value = str(email or "").strip().lower()
        username_value = str(username or "").strip().lower()
        if not email_value and not username_value:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="email or username is required",
            )

        payload_body: Dict[str, Any] = {
            "email": email_value,
            "username": username_value or email_value,
            "first_name": str(first_name or "").strip(),
            "last_name": str(last_name or "").strip(),
        }
        if str(user_id or "").strip():
            payload_body["user_id"] = str(user_id).strip()
        if str(idempotency_key or "").strip():
            payload_body["idempotency_key"] = str(idempotency_key).strip()

        provision_paths = [
            f"/api/hris/v1/integration/tenants/{tenant_id_str}/users/provision",
            f"/api/hris/integration/tenants/{tenant_id_str}/users/provision",
            f"/api/hris/v1/integrations/tenants/{tenant_id_str}/users/provision",
            f"/api/hris/integrations/tenants/{tenant_id_str}/users/provision",
        ]

        response_payload: Any = None
        last_exception: Optional[HTTPException] = None
        with self._get_http_client() as client:
            session_token = self._session_token_from_config_or_cache()
            if not session_token:
                session_token = self._refresh_runtime_session_token(client)
            header_candidates = self._integration_header_candidates(
                token,
                tenant_id=tenant_id_str,
                tenant_slug=tenant_slug,
                tenant_code=tenant_code,
            )
            for headers in header_candidates:
                headers["Content-Type"] = "application/json"
                if str(idempotency_key or "").strip():
                    headers["X-Idempotency-Key"] = str(idempotency_key).strip()
                if session_token:
                    headers["X-Session-Token"] = session_token
                try:
                    response_payload, _ = get_json_from_candidate_paths(
                        client=client,
                        base_url=str(self.settings.srms_base_url),
                        paths=provision_paths,
                        headers=headers,
                        method="POST",
                        json_body=payload_body,
                        module_name="SRMS",
                        payload_security_mode=self.settings.srms_payload_security_mode,
                        payload_signing_secret=self.settings.srms_payload_signing_secret,
                        payload_encryption_secret=self.settings.srms_payload_encryption_secret,
                        payload_session_token=session_token,
                        prepare_headers=lambda path, base_headers: self._build_signed_headers_for_path(
                            path=path,
                            session_token=session_token,
                            method="POST",
                            base_headers=base_headers,
                        ),
                    )
                    break
                except HTTPException as exc:
                    last_exception = exc
                    if exc.status_code == status.HTTP_502_BAD_GATEWAY and self.settings.srms_auto_session_token:
                        refreshed = self._refresh_runtime_session_token(client)
                        if refreshed:
                            headers["X-Session-Token"] = refreshed
                            try:
                                response_payload, _ = get_json_from_candidate_paths(
                                    client=client,
                                    base_url=str(self.settings.srms_base_url),
                                    paths=provision_paths,
                                    headers=headers,
                                    method="POST",
                                    json_body=payload_body,
                                    module_name="SRMS",
                                    payload_security_mode=self.settings.srms_payload_security_mode,
                                    payload_signing_secret=self.settings.srms_payload_signing_secret,
                                    payload_encryption_secret=self.settings.srms_payload_encryption_secret,
                                    payload_session_token=refreshed,
                                    prepare_headers=lambda path, base_headers: self._build_signed_headers_for_path(
                                        path=path,
                                        session_token=refreshed,
                                        method="POST",
                                        base_headers=base_headers,
                                    ),
                                )
                                session_token = refreshed
                                break
                            except HTTPException as refreshed_exc:
                                last_exception = refreshed_exc
                    continue

        if response_payload is None and last_exception is not None:
            raise last_exception

        if not isinstance(response_payload, dict):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="SRMS tenant user provision payload is invalid",
            )

        source = response_payload.get("data") if isinstance(response_payload.get("data"), dict) else response_payload
        source = source if isinstance(source, dict) else {}
        user_block = source.get("user") if isinstance(source.get("user"), dict) else {}
        provisioned_value = source.get("provisioned")
        provisioned = bool(provisioned_value) if isinstance(provisioned_value, bool) else False
        if not isinstance(provisioned_value, bool):
            status_text = str(source.get("status") or response_payload.get("message") or "").strip().lower()
            provisioned = status_text in {"created", "provisioned", "success", "ok"}

        return {
            "tenant_id": tenant_id_str,
            "provisioned": provisioned,
            "idempotency_key": to_str(source.get("idempotency_key")),
            "user_id": to_str(
                source.get("user_id")
                or source.get("id")
                or user_block.get("user_id")
                or user_block.get("id")
            ),
            "email": to_str(source.get("email") or user_block.get("email") or email_value),
            "username": to_str(source.get("username") or user_block.get("username") or username_value or email_value),
            "message": to_str(response_payload.get("message") or source.get("message") or "ok"),
            "raw": source,
        }
