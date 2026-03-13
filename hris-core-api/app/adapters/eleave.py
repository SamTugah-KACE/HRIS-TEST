from typing import Any, Dict, List, Optional

import httpx
from fastapi import HTTPException, status

from app.adapters.base import EleaveAdapter
from app.clients.adapter_utils import (
    build_auth_headers,
    build_hris_metadata_headers,
    ensure_dict,
    get_json_from_candidate_paths,
    to_float,
    to_int,
    to_str,
)
from app.core.settings import get_settings
from app.models.tenant_mapping import TenantMapping


class HttpEleaveAdapter(EleaveAdapter):
    def __init__(self) -> None:
        self.settings = get_settings()

    def _get_http_client(self) -> httpx.Client:
        return httpx.Client(timeout=self.settings.http_client_timeout_seconds)

    def _candidate_paths(self, hris_path: str, module_path: str) -> List[str]:
        mode = self.settings.module_adapter_mode.lower()
        hris_candidates = [hris_path]
        if hris_path.startswith("/hris/"):
            hris_candidates = [
                hris_path.replace("/hris/", "/api/hris/v1/", 1),
                hris_path.replace("/hris/", "/api/hris/", 1),
                hris_path,
            ]
        if mode == "hris_contract":
            return hris_candidates
        if mode == "module_native":
            return [module_path]
        return [*hris_candidates, module_path]

    def _build_base_url(self, mapping: TenantMapping) -> str:
        if not self.settings.eleave_domain_template or not mapping.eleave_subdomain:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="eLeave not configured for this tenant")
        return self.settings.eleave_domain_template.format(subdomain=mapping.eleave_subdomain)

    def get_leave_summary(self, mapping: TenantMapping, token: Optional[str]) -> Dict[str, Any]:
        base_url = self._build_base_url(mapping)
        headers = build_auth_headers(token, self.settings.eleave_service_token)
        headers.update(
            build_hris_metadata_headers(
                module_name="eleave",
                user_token=token or self.settings.eleave_service_token,
                tenant_id=mapping.tenant_id,
                tenant_code=mapping.code,
            )
        )
        tenant_prefix = f"/{mapping.eleave_subdomain}" if self.settings.eleave_use_tenant_path and mapping.eleave_subdomain else ""
        paths = self._candidate_paths(
            hris_path="/hris/leaves/summary",
            module_path=f"{tenant_prefix}/dashboard" if tenant_prefix else "/dashboard",
        )

        with self._get_http_client() as client:
            payload, selected_path = get_json_from_candidate_paths(
                client=client,
                base_url=base_url,
                paths=paths,
                headers=headers,
                module_name="eLeave",
            )

        payload = ensure_dict(payload, context="eLeave summary")

        if selected_path.endswith("/dashboard"):
            source = payload.get("data") if isinstance(payload.get("data"), dict) else payload
            return {
                "total_leaves_this_year": to_int(source.get("total_leaves_this_year", source.get("total", 0)), context="eLeave summary.total_leaves_this_year"),
                "approved_leaves": to_int(source.get("approved_leaves", source.get("approved", 0)), context="eLeave summary.approved_leaves"),
                "pending_leaves": to_int(source.get("pending_leaves", source.get("pending", 0)), context="eLeave summary.pending_leaves"),
                "rejected_leaves": to_int(source.get("rejected_leaves", source.get("rejected", 0)), context="eLeave summary.rejected_leaves"),
                "cancelled_leaves": to_int(source.get("cancelled_leaves", source.get("cancelled", 0)), context="eLeave summary.cancelled_leaves"),
                "leave_utilization_rate": to_float(source.get("leave_utilization_rate", source.get("utilization_rate", 0.0)), context="eLeave summary.leave_utilization_rate"),
            }

        return {
            "total_leaves_this_year": to_int(payload.get("total_leaves_this_year", 0), context="eLeave summary.total_leaves_this_year"),
            "approved_leaves": to_int(payload.get("approved_leaves", 0), context="eLeave summary.approved_leaves"),
            "pending_leaves": to_int(payload.get("pending_leaves", 0), context="eLeave summary.pending_leaves"),
            "rejected_leaves": to_int(payload.get("rejected_leaves", 0), context="eLeave summary.rejected_leaves"),
            "cancelled_leaves": to_int(payload.get("cancelled_leaves", 0), context="eLeave summary.cancelled_leaves"),
            "leave_utilization_rate": to_float(payload.get("leave_utilization_rate", 0.0), context="eLeave summary.leave_utilization_rate"),
        }

    def get_employee_leave_history(self, mapping: TenantMapping, employee_id: str, token: Optional[str]) -> Dict[str, Any]:
        base_url = self._build_base_url(mapping)
        headers = build_auth_headers(token, self.settings.eleave_service_token)
        headers.update(
            build_hris_metadata_headers(
                module_name="eleave",
                user_token=token or self.settings.eleave_service_token,
                tenant_id=mapping.tenant_id,
                tenant_code=mapping.code,
                employee_id=employee_id,
            )
        )
        tenant_prefix = f"/{mapping.eleave_subdomain}" if self.settings.eleave_use_tenant_path and mapping.eleave_subdomain else ""
        paths = self._candidate_paths(
            hris_path=f"/hris/employees/{employee_id}/leaves",
            module_path=f"{tenant_prefix}/staff/{employee_id}/leaveHistory" if tenant_prefix else f"/staff/{employee_id}/leaveHistory",
        )

        with self._get_http_client() as client:
            payload, selected_path = get_json_from_candidate_paths(
                client=client,
                base_url=base_url,
                paths=paths,
                headers=headers,
                module_name="eLeave",
            )

        if isinstance(payload, dict) and "leaves" in payload and isinstance(payload["leaves"], list):
            return payload

        rows: List[Dict[str, Any]] = []
        if isinstance(payload, list):
            rows = [r for r in payload if isinstance(r, dict)]
        elif isinstance(payload, dict):
            if isinstance(payload.get("data"), list):
                rows = [r for r in payload["data"] if isinstance(r, dict)]
            elif isinstance(payload.get("history"), list):
                rows = [r for r in payload["history"] if isinstance(r, dict)]
            elif isinstance(payload.get("records"), list):
                rows = [r for r in payload["records"] if isinstance(r, dict)]

        normalized = []
        for row in rows:
            normalized.append(
                {
                    "type": to_str(row.get("leave_type") or row.get("type")),
                    "days": to_int(row.get("days") or row.get("duration") or 0, context="eLeave history.days"),
                    "status": to_str(row.get("status")).lower(),
                    "start_date": to_str(row.get("start_date") or row.get("startDate")),
                    "end_date": to_str(row.get("end_date") or row.get("endDate")),
                }
            )

        balance: Dict[str, Any] = {}
        used: Dict[str, Any] = {}
        if selected_path.endswith("leaveHistory") and tenant_prefix:
            try:
                with self._get_http_client() as client:
                    progress_payload, _ = get_json_from_candidate_paths(
                        client=client,
                        base_url=base_url,
                        paths=[f"{tenant_prefix}/staff/myLeaveProgress"],
                        headers=headers,
                        module_name="eLeave",
                    )
                if isinstance(progress_payload, dict):
                    progress_source = progress_payload.get("data") if isinstance(progress_payload.get("data"), dict) else progress_payload
                    if isinstance(progress_source.get("balance"), dict):
                        balance = progress_source["balance"]
                    if isinstance(progress_source.get("used"), dict):
                        used = progress_source["used"]
            except HTTPException:
                # Progress endpoint is optional for compatibility.
                pass

        return {"employee_id": employee_id, "balance": balance, "used": used, "leaves": normalized}
