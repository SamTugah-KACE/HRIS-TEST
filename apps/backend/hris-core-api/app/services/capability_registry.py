from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional

from app.core.settings import get_settings
from app.services import automation_store


class ComponentMode(str, Enum):
    DISABLED = "disabled"
    OPTIONAL = "optional"
    REQUIRED = "required"


@dataclass(frozen=True)
class CapabilityDecision:
    name: str
    mode: ComponentMode
    enabled: bool
    tenant_enabled: bool
    source: str
    reason_code: str

    def public_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "mode": self.mode.value,
            "enabled": self.enabled,
            "tenant_enabled": self.tenant_enabled,
            "source": self.source,
            "reason_code": self.reason_code,
        }


_SETTING_FIELDS = {
    "primary_database": "component_primary_database_mode",
    "tenant_registry": "component_tenant_registry_mode",
    "keycloak": "component_keycloak_mode",
    "audit_log": "component_audit_log_mode",
    "redis": "component_redis_mode",
    "background_workers": "component_background_workers_mode",
    "scheduler": "component_scheduler_mode",
    "srms": "component_srms_mode",
    "eappraisal": "component_eappraisal_mode",
    "eleave": "component_eleave_mode",
    "sms": "component_sms_mode",
    "email": "component_email_mode",
    "database_sharding": "component_sharding_mode",
    "shard_router": "component_shard_router_mode",
    "metrics": "component_metrics_mode",
    "tracing": "component_tracing_mode",
    "network_monitoring": "component_network_monitoring_mode",
}


def known_capabilities() -> tuple[str, ...]:
    return tuple(_SETTING_FIELDS)


def component_mode(name: str) -> ComponentMode:
    normalized = str(name or "").strip().lower()
    field = _SETTING_FIELDS.get(normalized)
    if not field:
        raise KeyError(f"Unknown capability: {normalized}")
    return ComponentMode(str(getattr(get_settings(), field)).strip().lower())


def _tenant_entitlements(tenant_id: Optional[str]) -> Dict[str, bool]:
    if not tenant_id:
        return {}
    payload = automation_store.get_tenant_setting(
        tenant_id=str(tenant_id), setting_key="feature_entitlements"
    ) or {}
    features = payload.get("features") if isinstance(payload, dict) else {}
    if not isinstance(features, dict):
        return {}
    return {str(k).strip().lower(): bool(v) for k, v in features.items()}


def resolve_capability(name: str, *, tenant_id: Optional[str] = None) -> CapabilityDecision:
    normalized = str(name or "").strip().lower()
    mode = component_mode(normalized)
    if mode == ComponentMode.DISABLED:
        return CapabilityDecision(normalized, mode, False, False, "environment", "GLOBALLY_DISABLED")
    entitlements = _tenant_entitlements(tenant_id)
    tenant_enabled = entitlements.get(normalized, True)
    if not tenant_enabled:
        return CapabilityDecision(normalized, mode, False, False, "tenant", "TENANT_DISABLED")
    return CapabilityDecision(normalized, mode, True, True, "resolved", "ENABLED")


def public_capability_snapshot(*, tenant_id: Optional[str] = None) -> list[Dict[str, Any]]:
    return [resolve_capability(name, tenant_id=tenant_id).public_dict() for name in known_capabilities()]


def update_tenant_entitlements(tenant_id: str, features: Dict[str, bool]) -> Dict[str, bool]:
    unknown = sorted(set(str(k).strip().lower() for k in features) - set(known_capabilities()))
    if unknown:
        raise ValueError("Unknown capabilities: " + ", ".join(unknown))
    normalized = {str(k).strip().lower(): bool(v) for k, v in features.items()}
    automation_store.upsert_tenant_setting(
        tenant_id=str(tenant_id), setting_key="feature_entitlements", value={"features": normalized}
    )
    return normalized
