from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class TenantMatchDecision:
    decision: str
    target_tenant_ref: Optional[str]
    evidence: Dict[str, Any]


def _norm_text(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _norm_country(value: Any) -> str:
    raw = _norm_text(value)
    aliases = {
        "ghana": "gh",
        "gh": "gh",
        "nigeria": "ng",
        "ng": "ng",
        "kenya": "ke",
        "ke": "ke",
    }
    return aliases.get(raw, raw)


def _norm_bool(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    raw = _norm_text(value)
    if raw in {"true", "1", "yes", "y"}:
        return "true"
    if raw in {"false", "0", "no", "n"}:
        return "false"
    return ""


def _build_fingerprint(raw: Dict[str, Any]) -> Dict[str, str]:
    return {
        "name": _norm_text(raw.get("organization_name") or raw.get("name")),
        "org_type": _norm_text(raw.get("organization_type") or raw.get("org_type")),
        "country": _norm_country(raw.get("country")),
        "has_branches": _norm_bool(raw.get("has_branches")),
        "registration_id": _norm_text(raw.get("registration_id") or raw.get("tax_id") or raw.get("registration_number")),
    }


def evaluate_strict_tenant_match(
    *,
    source_profile: Dict[str, Any],
    candidate_rows: List[Dict[str, Any]],
) -> TenantMatchDecision:
    src = _build_fingerprint(source_profile or {})
    required = ("name", "org_type", "country", "has_branches", "registration_id")
    missing_source = [f for f in required if not src.get(f)]
    if missing_source:
        return TenantMatchDecision(
            decision="create_new",
            target_tenant_ref=None,
            evidence={"reason": "missing_source_required_fields", "missing_fields": missing_source, "source": src},
        )

    for row in candidate_rows or []:
        if not isinstance(row, dict):
            continue
        tgt = _build_fingerprint(row)
        mismatches = [f for f in required if src.get(f) != tgt.get(f)]
        if not mismatches:
            target_ref = str(
                row.get("tenant_id")
                or row.get("id")
                or row.get("subdomain")
                or row.get("tenant_slug")
                or row.get("slug")
                or ""
            ).strip() or None
            return TenantMatchDecision(
                decision="reuse_existing",
                target_tenant_ref=target_ref,
                evidence={"matched_fields": list(required), "source": src, "target": tgt},
            )

    return TenantMatchDecision(
        decision="create_new",
        target_tenant_ref=None,
        evidence={"reason": "no_strict_match", "required_fields": list(required), "source": src},
    )

