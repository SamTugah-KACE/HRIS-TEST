from typing import Any, Dict, Optional

import httpx
from fastapi import Request

from app.core.settings import get_settings


class UpstreamGatewayError(Exception):
    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        message: str,
        correlation_id: Optional[str] = None,
        upstream_detail: Any = None,
    ) -> None:
        self.status_code = int(status_code)
        self.code = code
        self.message = message
        self.correlation_id = correlation_id
        self.upstream_detail = upstream_detail
        super().__init__(message)


def _forward_headers(request: Request) -> Dict[str, str]:
    forwarded: Dict[str, str] = {}
    for key in (
        "authorization",
        "x-csrf-token",
        "x-debug-roles",
        "x-debug-username",
        "x-debug-employee-id",
        "x-debug-tenant-id",
        "x-correlation-id",
    ):
        value = request.headers.get(key)
        if value:
            forwarded[key] = value
    cookie = request.headers.get("cookie")
    if cookie:
        forwarded["cookie"] = cookie
    return forwarded


def call_core_json(
    request: Request,
    method: str,
    path: str,
    payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    settings = get_settings()
    base = str(settings.core_api_base_url).rstrip("/")
    url = f"{base}{path}"
    headers = _forward_headers(request)
    try:
        with httpx.Client(timeout=max(3, int(settings.core_api_timeout_seconds))) as client:
            response = client.request(method.upper(), url, json=payload, headers=headers)
    except httpx.HTTPError as exc:
        raise UpstreamGatewayError(
            status_code=502,
            code="UPSTREAM_UNREACHABLE",
            message=f"Failed to reach upstream core API: {exc}",
        ) from exc

    if response.status_code >= 400:
        detail: Any = None
        try:
            detail = response.json()
        except Exception:
            detail = response.text or f"HTTP {response.status_code}"
        if isinstance(detail, dict):
            err_code = str(detail.get("code") or f"UPSTREAM_HTTP_{response.status_code}")
            err_message = str(detail.get("message") or detail.get("detail") or "Upstream request failed")
            err_correlation_id = str(detail.get("correlation_id") or "").strip() or None
        else:
            err_code = f"UPSTREAM_HTTP_{response.status_code}"
            err_message = str(detail)
            err_correlation_id = None
        raise UpstreamGatewayError(
            status_code=response.status_code,
            code=err_code,
            message=err_message,
            correlation_id=err_correlation_id,
            upstream_detail=detail,
        )
    try:
        data = response.json()
        if isinstance(data, dict):
            return data
        return {"data": data}
    except Exception as exc:
        raise UpstreamGatewayError(
            status_code=502,
            code="UPSTREAM_INVALID_PAYLOAD",
            message=f"Upstream returned non-JSON payload: {exc}",
        ) from exc

