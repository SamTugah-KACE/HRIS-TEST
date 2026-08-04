from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class HrisOutboundMetadataHeaders(BaseModel):
    request_id: str = Field(..., min_length=1)
    client_app: str = Field(..., min_length=1)
    client_version: str = Field(..., min_length=1)
    integration_module: str = Field(..., min_length=1)
    user_sub: Optional[str] = None
    role: Optional[str] = None
    tenant_id: Optional[str] = None
    tenant_slug: Optional[str] = None
    tenant_code: Optional[str] = None
    employee_id: Optional[str] = None

    def as_http_headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {
            "X-Request-ID": self.request_id,
            "X-Client-App": self.client_app,
            "X-Client-Version": self.client_version,
            "X-HRIS-Integration-Module": self.integration_module,
        }
        if (self.user_sub or "").strip():
            headers["X-HRIS-User-Sub"] = str(self.user_sub).strip()
        if (self.role or "").strip():
            headers["X-HRIS-Role"] = str(self.role).strip()
        if (self.tenant_id or "").strip():
            headers["X-HRIS-Tenant-Id"] = str(self.tenant_id).strip()
        if (self.tenant_slug or "").strip():
            headers["X-HRIS-Tenant-Slug"] = str(self.tenant_slug).strip()
        if (self.tenant_code or "").strip():
            headers["X-HRIS-Tenant-Code"] = str(self.tenant_code).strip()
        if (self.employee_id or "").strip():
            headers["X-HRIS-Employee-Id"] = str(self.employee_id).strip()
        return headers


class HrisEnvelopeMeta(BaseModel):
    request_id: str
    module: str
    tenant_id: str
    resolved_tenant_id: str = ""
    resolved_user_id: str = ""
    effective_role: str
    api_version: str = "v1"
    timestamp: str


class HrisEnvelope(BaseModel):
    success: bool = True
    message: str = "ok"
    data: Any
    meta: HrisEnvelopeMeta
