import re
from typing import Dict, Optional

from pydantic import BaseModel, ConfigDict, Field


class ModuleStatus(BaseModel):
    status: str = "inactive"
    ready: bool = False
    configured: bool = False


class TenantModules(BaseModel):
    model_config = ConfigDict(extra="allow")

    srms: ModuleStatus = Field(default_factory=ModuleStatus)
    eappraisal: ModuleStatus = Field(default_factory=ModuleStatus)
    eleave: ModuleStatus = Field(default_factory=ModuleStatus)

    def get_status(self, module_name: str) -> ModuleStatus:
        raw = self.model_dump().get(module_name)
        if isinstance(raw, dict):
            try:
                return ModuleStatus(**raw)
            except Exception:
                return ModuleStatus()
        if isinstance(raw, ModuleStatus):
            return raw
        return ModuleStatus()

    def as_dict(self) -> Dict[str, ModuleStatus]:
        modules: Dict[str, ModuleStatus] = {}
        for module_name, raw in self.model_dump().items():
            if isinstance(raw, dict):
                modules[module_name] = ModuleStatus(**raw)
        return modules


class TenantMapping(BaseModel):
    tenant_id: str
    code: str
    name: str
    srms_schema: Optional[str] = None
    srms_slug: Optional[str] = None
    eappraisal_subdomain: Optional[str] = None
    eleave_subdomain: Optional[str] = None
    is_active: bool
    lifecycle_status: str = "active"
    modules: TenantModules = Field(default_factory=TenantModules)

    def is_tenant_active(self) -> bool:
        return self.is_active and self.lifecycle_status.lower() == "active"

    def module_enabled(self, module_name: str) -> bool:
        if not isinstance(module_name, str):
            return False
        normalized = module_name.strip().lower()
        if not re.fullmatch(r"[a-z][a-z0-9_-]*", normalized):
            return False
        module = self.modules.get_status(normalized)
        return module.configured and module.ready and module.status.lower() == "active"

    def enabled_module_ids(self) -> list[str]:
        enabled: list[str] = []
        for module_name, module in self.modules.as_dict().items():
            if module.configured and module.ready and module.status.lower() == "active":
                enabled.append(module_name)
        return enabled
