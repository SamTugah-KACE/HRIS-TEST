from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from app.services import automation_store


JIT_SETTING_PREFIX = "jit."


@dataclass(frozen=True)
class JitRoleMapping:
    eappraisal_role_id: Optional[str] = None
    eappraisal_role_name: Optional[str] = None
    eleave_role_name: Optional[str] = None
    eappraisal_fallback_role_name: Optional[str] = None
    eleave_fallback_role_name: Optional[str] = None


def get_jit_role_mapping(*, tenant_id: str) -> JitRoleMapping:
    """
    Tenant-scoped role mapping overrides used by JIT provisioning.
    Stored in automation store runtime settings for flexibility without code changes.
    """
    raw = automation_store.get_tenant_setting(tenant_id=tenant_id, setting_key=f"{JIT_SETTING_PREFIX}role_mapping") or {}
    if not isinstance(raw, dict):
        raw = {}
    return JitRoleMapping(
        eappraisal_role_id=str(raw.get("eappraisal_role_id") or "").strip() or None,
        eappraisal_role_name=str(raw.get("eappraisal_role_name") or "").strip() or None,
        eleave_role_name=str(raw.get("eleave_role_name") or "").strip() or None,
        eappraisal_fallback_role_name=str(raw.get("eappraisal_fallback_role_name") or "").strip() or None,
        eleave_fallback_role_name=str(raw.get("eleave_fallback_role_name") or "").strip() or None,
    )


def set_jit_role_mapping(*, tenant_id: str, value: Dict[str, Any]) -> None:
    automation_store.upsert_tenant_setting(
        tenant_id=tenant_id,
        setting_key=f"{JIT_SETTING_PREFIX}role_mapping",
        value=dict(value or {}),
    )


def get_jit_module_enable_policy(*, tenant_id: str) -> Dict[str, Any]:
    raw = automation_store.get_tenant_setting(tenant_id=tenant_id, setting_key=f"{JIT_SETTING_PREFIX}module_enable_policy") or {}
    if not isinstance(raw, dict):
        return {}
    return raw


def set_jit_module_enable_policy(*, tenant_id: str, value: Dict[str, Any]) -> None:
    automation_store.upsert_tenant_setting(
        tenant_id=tenant_id,
        setting_key=f"{JIT_SETTING_PREFIX}module_enable_policy",
        value=dict(value or {}),
    )


def get_jit_action_allowlist(*, tenant_id: str, module_name: str) -> list[str]:
    raw = automation_store.get_tenant_setting(
        tenant_id=tenant_id,
        setting_key=f"{JIT_SETTING_PREFIX}action_allowlist",
    ) or {}
    if not isinstance(raw, dict):
        return []
    module = str(module_name or "").strip().lower()
    items = raw.get(module)
    if not isinstance(items, list):
        return []
    return [str(x).strip().lower() for x in items if str(x).strip()]

