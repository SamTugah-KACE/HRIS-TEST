from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import httpx
from fastapi import HTTPException, status

from app.adapters.base import EappraisalAdapter
from app.clients.adapter_utils import (
    build_auth_headers,
    build_hris_metadata_headers,
    ensure_dict,
    ensure_list,
    extract_json_from_network_dump,
    unwrap_payload,
    to_float,
    to_int,
    to_str,
)
from app.core.settings import get_settings
from app.models.tenant_mapping import TenantMapping


class HttpEappraisalAdapter(EappraisalAdapter):
    def __init__(self) -> None:
        self.settings = get_settings()
        self._runtime_access_token: Optional[str] = None

    def _get_http_client(self) -> httpx.Client:
        return httpx.Client(timeout=self.settings.http_client_timeout_seconds)

    def _candidate_paths(self, hris_path: str, module_path: str) -> List[str]:
        mode = self.settings.module_adapter_mode.lower()
        if mode == "hris_contract":
            return [hris_path]
        if mode == "module_native":
            return [module_path]
        return [hris_path, module_path]

    def _build_base_url(self, mapping: TenantMapping) -> str:
        if not self.settings.eappraisal_domain_template or not mapping.eappraisal_subdomain:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="eAppraisal not configured for this tenant",
            )
        return self.settings.eappraisal_domain_template.format(subdomain=mapping.eappraisal_subdomain)

    def _build_headers(
        self,
        mapping: TenantMapping,
        token: Optional[str],
        base_url: str,
        *,
        employee_id: Optional[str] = None,
    ) -> Dict[str, str]:
        active_token = token or self._runtime_access_token or self.settings.eappraisal_service_token
        headers = build_auth_headers(active_token, None)
        headers.update(
            build_hris_metadata_headers(
                module_name="eappraisal",
                user_token=active_token,
                tenant_id=mapping.tenant_id,
                tenant_code=mapping.code,
                employee_id=employee_id,
            )
        )
        configured_subdomain = (self.settings.eappraisal_subdomain_header or "").strip()
        if configured_subdomain:
            headers["subdomain"] = configured_subdomain
        elif "{subdomain}" in (self.settings.eappraisal_domain_template or "") and mapping.eappraisal_subdomain:
            headers["subdomain"] = mapping.eappraisal_subdomain
        else:
            host = (urlparse(base_url).hostname or "").strip()
            parts = host.split(".")
            if parts:
                headers["subdomain"] = parts[0]
        if self.settings.eappraisal_cookie:
            headers["cookie"] = self.settings.eappraisal_cookie
        return headers

    def _refresh_access_token(
        self,
        *,
        client: httpx.Client,
        base_url: str,
        headers: Dict[str, str],
        stale_token: Optional[str],
    ) -> Optional[str]:
        if not self.settings.eappraisal_auto_refresh:
            return None
        refresh_token = self.settings.eappraisal_refresh_token
        if not refresh_token:
            return None

        refresh_headers = dict(headers)
        if stale_token:
            refresh_headers["Authorization"] = f"Bearer {stale_token}"
        refresh_headers["Content-Type"] = "application/json"
        refresh_url = f"{base_url.rstrip('/')}/api/auth/refresh"

        try:
            response = client.post(refresh_url, headers=refresh_headers, json={"refresh_token": refresh_token})
            response.raise_for_status()
            payload = response.json()
        except Exception:
            return None

        new_token = None
        if isinstance(payload, dict):
            new_token = payload.get("access_token") or payload.get("token") or payload.get("accessToken")
            if not new_token and isinstance(payload.get("data"), dict):
                data_obj = payload["data"]
                new_token = data_obj.get("access_token") or data_obj.get("token") or data_obj.get("accessToken")

        if not new_token:
            return None
        self._runtime_access_token = str(new_token)
        return self._runtime_access_token

    def _get_json_with_candidates(
        self,
        *,
        client: httpx.Client,
        base_url: str,
        paths: List[str],
        headers: Dict[str, str],
        module_name: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Any:
        last_response: Optional[httpx.Response] = None
        last_error: Optional[Exception] = None

        for path in paths:
            url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
            try:
                response = client.get(url, headers=headers, params=params)
                last_response = response
            except httpx.HTTPError as exc:
                last_error = exc
                continue

            if response.status_code in (404, 405):
                continue

            if response.status_code == 401:
                stale = None
                auth_header = headers.get("Authorization")
                if auth_header and auth_header.lower().startswith("bearer "):
                    stale = auth_header[7:]
                refreshed = self._refresh_access_token(
                    client=client,
                    base_url=base_url,
                    headers=headers,
                    stale_token=stale,
                )
                if refreshed:
                    retry_headers = dict(headers)
                    retry_headers["Authorization"] = f"Bearer {refreshed}"
                    response = client.get(url, headers=retry_headers, params=params)
                    last_response = response
                    if response.status_code in (404, 405):
                        continue
                    if response.status_code == 401:
                        raise HTTPException(
                            status_code=status.HTTP_502_BAD_GATEWAY,
                            detail=f"{module_name} authentication failed while calling '{path}'",
                        )
                    response.raise_for_status()
                    return unwrap_payload(response.json()), path

                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"{module_name} authentication failed while calling '{path}'",
                )

            try:
                response.raise_for_status()
                return unwrap_payload(response.json()), path
            except httpx.HTTPError as exc:
                last_error = exc
                continue

        if last_response is not None:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=(
                    f"{module_name} request failed for all mapped endpoints. "
                    f"Last status: {last_response.status_code}"
                ),
            )

        if last_error is not None:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"{module_name} request failed: {last_error}",
            )

        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"{module_name} request failed: no endpoint candidates available",
        )

    def _load_fixture_cycles(self) -> List[Dict[str, Any]]:
        fixture_file = self.settings.eappraisal_fixture_file
        if not fixture_file:
            return []
        payload = extract_json_from_network_dump(fixture_file)
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            return [payload]
        return []

    def _normalize_cycle_to_appraisal(self, cycle: Dict[str, Any]) -> Dict[str, Any]:
        status = "in_progress" if bool(cycle.get("is_active", True)) else "completed"
        return {
            "cycle_name": to_str(cycle.get("name") or "Appraisal Cycle"),
            "overall_score": cycle.get("overall_score"),
            "rating": to_str(cycle.get("rating")),
            "status": status,
            "date": to_str(cycle.get("updated_date") or cycle.get("created_date")),
        }

    def _normalize_cycle_sections(self, cycle: Dict[str, Any]) -> List[Dict[str, Any]]:
        sections = cycle.get("appraisal_sections")
        if not isinstance(sections, list):
            return []
        normalized: List[Dict[str, Any]] = []
        total = max(1, len(sections))
        for section in sections:
            if not isinstance(section, dict):
                continue
            inputs = section.get("inputs")
            has_inputs = isinstance(inputs, list) and len(inputs) > 0
            normalized.append(
                {
                    "name": to_str(section.get("name") or "Section"),
                    "weight": round(100 / total),
                    "status": "completed" if has_inputs else "not_started",
                    "score": None,
                    "maxScore": 5,
                }
            )
        return normalized

    def _get_identity_from_auth_me(
        self,
        *,
        client: httpx.Client,
        base_url: str,
        headers: Dict[str, str],
        token: Optional[str],
    ) -> Dict[str, str]:
        token_to_send = token or self._runtime_access_token or self.settings.eappraisal_service_token
        if not token_to_send:
            return {}

        url = f"{base_url.rstrip('/')}/api/auth/me"
        try:
            request_headers = dict(headers)
            request_headers["Authorization"] = f"Bearer {token_to_send}"
            response = client.post(url, headers=request_headers, json={"access_token": token_to_send})
            if response.status_code == 401:
                refreshed = self._refresh_access_token(
                    client=client,
                    base_url=base_url,
                    headers=request_headers,
                    stale_token=token_to_send,
                )
                if refreshed:
                    request_headers["Authorization"] = f"Bearer {refreshed}"
                    response = client.post(url, headers=request_headers, json={"access_token": refreshed})
            response.raise_for_status()
            payload = response.json()
        except Exception:
            return {}

        user = payload.get("user") if isinstance(payload, dict) else None
        if not isinstance(user, dict):
            user = {}
        return {
            "user_id": to_str(user.get("id")),
            "email": to_str(user.get("email")).lower(),
            "staff_id": to_str(user.get("staff_id")),
            "subdomain": to_str(payload.get("subdomain")) if isinstance(payload, dict) else "",
        }

    def _submission_matches_identity(self, row: Dict[str, Any], identity: Dict[str, str], employee_id: str) -> bool:
        staff = row.get("staff")
        if not isinstance(staff, dict):
            return False

        email = to_str(staff.get("email")).lower()
        user_id = to_str(staff.get("user_id"))
        staff_id = to_str(staff.get("id"))
        requested = to_str(employee_id).lower()

        checks = [
            bool(identity.get("user_id")) and user_id == identity["user_id"],
            bool(identity.get("email")) and email == identity["email"],
            bool(identity.get("staff_id")) and staff_id == identity["staff_id"],
            bool(requested) and requested in {email, user_id, staff_id},
        ]
        return any(checks)

    def get_appraisal_summary(self, mapping: TenantMapping, token: Optional[str]) -> Dict[str, Any]:
        fixture_cycles = self._load_fixture_cycles()
        if fixture_cycles:
            active_cycles = sum(1 for c in fixture_cycles if bool(c.get("is_active", True)))
            return {
                "active_cycles": active_cycles,
                "pending_reviews": 0,
                "completed_reviews": len(fixture_cycles),
                "overdue_reviews": 0,
                "average_score": 0.0,
                "completion_rate": 100.0 if fixture_cycles else 0.0,
            }

        base_url = self._build_base_url(mapping)
        headers = self._build_headers(mapping, token, base_url)
        paths = self._candidate_paths(
            hris_path="/api/hris/appraisals/summary",
            module_path="/api/dashboard/counts",
        )

        with self._get_http_client() as client:
            payload, selected_path = self._get_json_with_candidates(
                client=client,
                base_url=base_url,
                paths=paths,
                headers=headers,
                module_name="eAppraisal",
            )

        payload = ensure_dict(payload, context="eAppraisal summary")

        if selected_path == "/api/dashboard/counts":
            pending = to_int(payload.get("pending", payload.get("pending_reviews", 0)), context="eAppraisal summary.pending")
            completed = to_int(payload.get("approved", payload.get("completed_reviews", 0)), context="eAppraisal summary.completed")
            changes_requested = to_int(payload.get("changes_requested", 0), context="eAppraisal summary.changes_requested")
            total_staff = to_int(payload.get("total_staff", payload.get("total", 0)), context="eAppraisal summary.total_staff")
            completion_rate = (completed / total_staff * 100) if total_staff > 0 else 0.0
            return {
                "active_cycles": to_int(payload.get("active_cycles", 1 if total_staff > 0 else 0), context="eAppraisal summary.active_cycles"),
                "pending_reviews": pending + changes_requested,
                "completed_reviews": completed,
                "overdue_reviews": to_int(payload.get("overdue_reviews", 0), context="eAppraisal summary.overdue_reviews"),
                "average_score": to_float(payload.get("average_score", 0.0), context="eAppraisal summary.average_score"),
                "completion_rate": round(completion_rate, 1),
            }

        return {
            "active_cycles": to_int(payload.get("active_cycles", 0), context="eAppraisal summary.active_cycles"),
            "pending_reviews": to_int(payload.get("pending_reviews", 0), context="eAppraisal summary.pending_reviews"),
            "completed_reviews": to_int(payload.get("completed_reviews", 0), context="eAppraisal summary.completed_reviews"),
            "overdue_reviews": to_int(payload.get("overdue_reviews", 0), context="eAppraisal summary.overdue_reviews"),
            "average_score": to_float(payload.get("average_score", 0.0), context="eAppraisal summary.average_score"),
            "completion_rate": to_float(payload.get("completion_rate", 0.0), context="eAppraisal summary.completion_rate"),
        }

    def get_employee_appraisals(self, mapping: TenantMapping, employee_id: str, token: Optional[str]) -> Dict[str, Any]:
        fixture_cycles = self._load_fixture_cycles()
        if fixture_cycles:
            return {
                "employee_id": employee_id,
                "appraisals": [self._normalize_cycle_to_appraisal(cycle) for cycle in fixture_cycles],
            }

        base_url = self._build_base_url(mapping)
        headers = self._build_headers(mapping, token, base_url, employee_id=employee_id)
        mode = self.settings.module_adapter_mode.lower()

        with self._get_http_client() as client:
            identity = self._get_identity_from_auth_me(
                client=client,
                base_url=base_url,
                headers=headers,
                token=token,
            )
            if mode != "module_native":
                try:
                    payload, selected_path = self._get_json_with_candidates(
                        client=client,
                        base_url=base_url,
                        paths=[f"/api/hris/employees/{employee_id}/appraisals"],
                        headers=headers,
                        module_name="eAppraisal",
                    )
                except HTTPException:
                    if mode == "hris_contract":
                        raise
                    try:
                        payload, selected_path = self._get_json_with_candidates(
                            client=client,
                            base_url=base_url,
                            paths=["/api/appraisals/submissions"],
                            headers=headers,
                            params={"staff_id": employee_id},
                            module_name="eAppraisal",
                        )
                    except HTTPException:
                        payload, selected_path = self._get_json_with_candidates(
                            client=client,
                            base_url=base_url,
                            paths=["/api/appraisals/submissions"],
                            headers=headers,
                            module_name="eAppraisal",
                        )
            else:
                try:
                    payload, selected_path = self._get_json_with_candidates(
                        client=client,
                        base_url=base_url,
                        paths=["/api/appraisals/submissions"],
                        headers=headers,
                        params={"staff_id": employee_id},
                        module_name="eAppraisal",
                    )
                except HTTPException:
                    payload, selected_path = self._get_json_with_candidates(
                        client=client,
                        base_url=base_url,
                        paths=["/api/appraisals/submissions"],
                        headers=headers,
                        module_name="eAppraisal",
                    )

        if isinstance(payload, dict) and "appraisals" in payload and isinstance(payload["appraisals"], list):
            return payload

        if selected_path == "/api/appraisals/submissions":
            rows = ensure_list(payload, context="eAppraisal submissions")
            normalized = []
            for row in rows:
                if not isinstance(row, dict):
                    continue
                if identity and not self._submission_matches_identity(row, identity, employee_id):
                    continue
                status_text = to_str(row.get("status"))
                appraisal = row.get("appraisal") if isinstance(row.get("appraisal"), dict) else {}
                reviewer = row.get("current_reviewer")
                if isinstance(reviewer, dict):
                    reviewer_text = to_str(reviewer.get("username") or reviewer.get("email") or reviewer.get("id"))
                else:
                    reviewer_text = to_str(reviewer)
                normalized.append(
                    {
                        "submission_id": to_str(row.get("id")),
                        "appraisal_id": to_str(appraisal.get("id")),
                        "cycle_name": to_str(
                            row.get("cycle")
                            or row.get("appraisal_cycle")
                            or appraisal.get("name")
                            or "Appraisal Cycle"
                        ),
                        "overall_score": row.get("overall_score") or row.get("total_score") or row.get("score"),
                        "rating": to_str(row.get("rating") or row.get("grade")),
                        "status": status_text.lower().replace(" ", "_") if status_text else "unknown",
                        "date": to_str(row.get("updated_at") or row.get("created_at")),
                        "submitted": bool(row.get("submitted", False)),
                        "reviewed": bool(row.get("reviewed_at") or row.get("is_review", False)),
                        "reviewer": reviewer_text,
                        "comments": to_str(row.get("comments")),
                    }
                )
            return {"employee_id": employee_id, "appraisals": normalized}

        return {"employee_id": employee_id, "appraisals": []}

    def get_my_appraisals(self, mapping: TenantMapping, token: Optional[str]) -> Dict[str, Any]:
        fixture_cycles = self._load_fixture_cycles()
        if fixture_cycles:
            cycle = fixture_cycles[0]
            sections = self._normalize_cycle_sections(cycle)
            completed = sum(1 for s in sections if s.get("status") == "completed")
            progress = round((completed / len(sections)) * 100) if sections else 0
            return {
                "current_cycle": {
                    "title": to_str(cycle.get("name") or "Current Appraisal Cycle"),
                    "due_date": to_str(cycle.get("year") or ""),
                    "overall_progress": progress,
                },
                "sections": sections,
                "goals": [],
            }

        base_url = self._build_base_url(mapping)
        headers = self._build_headers(mapping, token, base_url)
        paths = ["/api/appraisals/cycles/list-my-appraisals"]
        with self._get_http_client() as client:
            payload, _ = self._get_json_with_candidates(
                client=client,
                base_url=base_url,
                paths=paths,
                headers=headers,
                module_name="eAppraisal",
            )

        if isinstance(payload, list) and payload and isinstance(payload[0], dict):
            cycle = payload[0]
            sections = self._normalize_cycle_sections(cycle)
            completed = sum(1 for s in sections if s.get("status") == "completed")
            progress = round((completed / len(sections)) * 100) if sections else 0
            return {
                "current_cycle": {
                    "title": to_str(cycle.get("name") or "Current Appraisal Cycle"),
                    "due_date": to_str(cycle.get("year") or ""),
                    "overall_progress": progress,
                },
                "sections": sections,
                "goals": [],
            }

        return {"current_cycle": {"title": "Current Appraisal Cycle", "due_date": "", "overall_progress": 0}, "sections": [], "goals": []}
