import argparse
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import httpx
from fastapi.testclient import TestClient

from module_contract_audit import run_audit

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _local_contract_checks() -> Tuple[bool, List[str]]:
    original_auth_mode = os.environ.get("AUTH_MODE")
    original_stub_mode = os.environ.get("USE_STUB_DATA")
    os.environ["AUTH_MODE"] = "dev"
    os.environ["USE_STUB_DATA"] = "true"

    # Keep local contract checks deterministic by disabling live eAppraisal auth.
    managed_keys = ("EAPPRAISAL_SERVICE_TOKEN", "EAPPRAISAL_REFRESH_TOKEN")
    original_values = {k: os.environ.get(k) for k in managed_keys}
    for key in managed_keys:
        os.environ[key] = ""

    from app.core.settings import get_settings

    get_settings.cache_clear()
    from app.main import app

    client = TestClient(app)
    errors: List[str] = []

    employee_headers = {
        "X-Debug-Roles": "hris:employee",
        "X-Debug-Username": "employee",
        "X-Debug-Employee-Id": "e001",
    }
    manager_headers = {
        "X-Debug-Roles": "hris:hr_manager",
        "X-Debug-Username": "hr.manager",
    }

    endpoint_headers: Dict[str, Dict[str, str]] = {
        "/health": {},
        "/me": employee_headers,
        "/dashboard/summary": employee_headers,
        "/employees": manager_headers,
        "/employees/e001/summary": manager_headers,
        "/profile/me": employee_headers,
        "/modules/appraisal": employee_headers,
        "/modules/leave": employee_headers,
    }

    for endpoint, headers in endpoint_headers.items():
        response = client.get(endpoint, headers=headers)
        if response.status_code != 200:
            errors.append(f"{endpoint}: expected 200, got {response.status_code}")

    me = client.get("/me", headers=employee_headers).json()
    if "employee_id" not in me:
        errors.append("/me: missing employee_id")

    profile = client.get("/profile/me", headers=employee_headers).json()
    for key in ("profile", "employment", "qualifications", "emergency_contacts", "documents", "quick_stats"):
        if key not in profile:
            errors.append(f"/profile/me: missing {key}")

    appraisal = client.get("/modules/appraisal", headers=employee_headers).json()
    if "manager" not in appraisal or "employee" not in appraisal:
        errors.append("/modules/appraisal: missing manager/employee sections")

    leave = client.get("/modules/leave", headers=employee_headers).json()
    if "manager" not in leave or "employee" not in leave:
        errors.append("/modules/leave: missing manager/employee sections")

    # Type/format checks for key contracts
    dashboard = client.get("/dashboard/summary", headers=employee_headers).json()
    for key in ("srms", "appraisal", "leave"):
        if not isinstance(dashboard.get(key), dict):
            errors.append(f"/dashboard/summary: '{key}' must be an object")

    srms = dashboard.get("srms", {}) if isinstance(dashboard.get("srms"), dict) else {}
    for key in ("total_employees", "active_employees", "inactive_employees", "branches", "departments"):
        if not isinstance(srms.get(key), int):
            errors.append(f"/dashboard/summary.srms.{key}: expected int")

    appraisal_summary = dashboard.get("appraisal", {}) if isinstance(dashboard.get("appraisal"), dict) else {}
    for key in ("active_cycles", "pending_reviews", "completed_reviews", "overdue_reviews"):
        if not isinstance(appraisal_summary.get(key), int):
            errors.append(f"/dashboard/summary.appraisal.{key}: expected int")
    for key in ("average_score", "completion_rate"):
        if not isinstance(appraisal_summary.get(key), (int, float)):
            errors.append(f"/dashboard/summary.appraisal.{key}: expected number")

    leave_summary = dashboard.get("leave", {}) if isinstance(dashboard.get("leave"), dict) else {}
    for key in ("total_leaves_this_year", "approved_leaves", "pending_leaves", "rejected_leaves", "cancelled_leaves"):
        if not isinstance(leave_summary.get(key), int):
            errors.append(f"/dashboard/summary.leave.{key}: expected int")
    if not isinstance(leave_summary.get("leave_utilization_rate"), (int, float)):
        errors.append("/dashboard/summary.leave.leave_utilization_rate: expected number")

    employees = client.get("/employees", headers=manager_headers).json()
    if not isinstance(employees.get("employees"), list):
        errors.append("/employees: employees must be a list")
    else:
        for i, row in enumerate(employees.get("employees", [])[:3]):
            if not isinstance(row, dict):
                errors.append(f"/employees: row {i} must be object")
                continue
            for key in ("employee_id", "staff_id", "full_name", "department", "status"):
                if not isinstance(row.get(key), str):
                    errors.append(f"/employees: row {i} '{key}' must be string")

    leave_mod = client.get("/modules/leave", headers=employee_headers).json()
    employee_leave = leave_mod.get("employee", {}) if isinstance(leave_mod.get("employee"), dict) else {}
    if not isinstance(employee_leave.get("history", []), list):
        errors.append("/modules/leave.employee.history: expected list")
    else:
        for i, row in enumerate(employee_leave.get("history", [])[:3]):
            if not isinstance(row, dict):
                errors.append(f"/modules/leave.employee.history[{i}]: expected object")
                continue
            if not isinstance(row.get("days"), int):
                errors.append(f"/modules/leave.employee.history[{i}].days: expected int")

    appraisal_mod = client.get("/modules/appraisal", headers=employee_headers).json()
    employee_appraisal = appraisal_mod.get("employee", {}) if isinstance(appraisal_mod.get("employee"), dict) else {}
    if not isinstance(employee_appraisal.get("past_appraisals", []), list):
        errors.append("/modules/appraisal.employee.past_appraisals: expected list")
    else:
        for i, row in enumerate(employee_appraisal.get("past_appraisals", [])[:3]):
            if not isinstance(row, dict):
                errors.append(f"/modules/appraisal.employee.past_appraisals[{i}]: expected object")
                continue
            for key in ("cycle", "status", "date"):
                if key not in row:
                    errors.append(f"/modules/appraisal.employee.past_appraisals[{i}].{key}: missing")
            if "submission_id" not in row and "appraisal_id" not in row:
                errors.append(
                    f"/modules/appraisal.employee.past_appraisals[{i}]: expected submission_id or appraisal_id for drilldown"
                )
    first_past = (employee_appraisal.get("past_appraisals") or [None])[0]
    if isinstance(first_past, dict):
        entry_id = first_past.get("submission_id") or first_past.get("appraisal_id")
        if entry_id:
            detail_resp = client.get(
                f"/modules/appraisal/history/{entry_id}",
                headers=employee_headers,
            )
            if detail_resp.status_code != 200:
                errors.append(
                    f"/modules/appraisal/history/{entry_id}: expected 200, got {detail_resp.status_code}"
                )

    ok = len(errors) == 0

    # Restore environment for any subsequent live probes in this same process.
    for key, value in original_values.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    if original_auth_mode is None:
        os.environ.pop("AUTH_MODE", None)
    else:
        os.environ["AUTH_MODE"] = original_auth_mode
    if original_stub_mode is None:
        os.environ.pop("USE_STUB_DATA", None)
    else:
        os.environ["USE_STUB_DATA"] = original_stub_mode
    get_settings.cache_clear()

    return ok, errors


def _live_module_probe() -> Tuple[bool, List[str]]:
    errors: List[str] = []

    # Optional probe only. It verifies connectivity + auth path availability
    # when running real integration mode.
    srms_base = os.getenv("SRMS_BASE_URL", "").rstrip("/")
    eapp_template = os.getenv("EAPPRAISAL_DOMAIN_TEMPLATE", "")
    eleave_template = os.getenv("ELEAVE_DOMAIN_TEMPLATE", "")
    sample_subdomain = os.getenv("SYNC_CHECK_SAMPLE_SUBDOMAIN", "devsub")
    bearer = os.getenv("SYNC_CHECK_BEARER_TOKEN", "")

    if not bearer:
        errors.append("SYNC_CHECK_BEARER_TOKEN is required for --live probe")
        return False, errors

    headers = {"Authorization": f"Bearer {bearer}"}

    try:
        with httpx.Client(timeout=10.0) as client:
            if srms_base:
                r = client.get(f"{srms_base}/api/dashboard/summary", headers=headers)
                if r.status_code >= 500:
                    errors.append(f"SRMS probe failed with status {r.status_code}")
            else:
                errors.append("SRMS_BASE_URL missing for live probe")

            if eapp_template:
                eapp_base = eapp_template.format(subdomain=sample_subdomain).rstrip("/")
                r = client.get(f"{eapp_base}/api/dashboard/counts", headers=headers)
                if r.status_code >= 500:
                    errors.append(f"eAppraisal probe failed with status {r.status_code}")
            else:
                errors.append("EAPPRAISAL_DOMAIN_TEMPLATE missing for live probe")

            if eleave_template:
                eleave_base = eleave_template.format(subdomain=sample_subdomain).rstrip("/")
                r = client.get(f"{eleave_base}/{sample_subdomain}/dashboard", headers=headers)
                if r.status_code >= 500:
                    errors.append(f"eLeave probe failed with status {r.status_code}")
            else:
                errors.append("ELEAVE_DOMAIN_TEMPLATE missing for live probe")
    except httpx.HTTPError as exc:
        errors.append(f"live probe network error: {exc}")

    return len(errors) == 0, errors


def _live_eappraisal_diagnostics_probe() -> Tuple[bool, List[str]]:
    """
    Probe the in-app diagnostics endpoint to validate eAppraisal integration path
    end-to-end without exposing secrets in script output.
    """
    errors: List[str] = []

    original_auth_mode = os.environ.get("AUTH_MODE")
    original_stub_mode = os.environ.get("USE_STUB_DATA")
    os.environ["AUTH_MODE"] = "dev"
    os.environ["USE_STUB_DATA"] = "true"

    from app.core.settings import get_settings

    get_settings.cache_clear()

    try:
        from app.main import app

        client = TestClient(app)
        headers = {
            "X-Debug-Roles": "hris:hr_manager",
            "X-Debug-Username": "hr.manager",
            "X-Debug-Employee-Id": os.getenv("DEV_DEFAULT_EMPLOYEE_ID", "e001"),
        }

        response = client.get("/debug/integrations/eappraisal", headers=headers)
        if response.status_code != 200:
            errors.append(
                "/debug/integrations/eappraisal unavailable. "
                "Set ENABLE_INTEGRATION_DEBUG_ENDPOINTS=true for this probe."
            )
            return False, errors

        payload = response.json()
        probes = payload.get("probes", {}) if isinstance(payload, dict) else {}
        if not isinstance(probes, dict):
            errors.append("eAppraisal diagnostics probe: invalid probe payload")
            return False, errors

        expected_probes = ("appraisal_summary", "my_appraisals", "employee_appraisals")
        for probe_name in expected_probes:
            probe = probes.get(probe_name, {})
            ok = isinstance(probe, dict) and probe.get("ok") is True
            if not ok:
                detail = probe.get("detail") if isinstance(probe, dict) else "probe missing"
                errors.append(f"eAppraisal diagnostics '{probe_name}' failed: {detail}")
        return len(errors) == 0, errors
    finally:
        if original_auth_mode is None:
            os.environ.pop("AUTH_MODE", None)
        else:
            os.environ["AUTH_MODE"] = original_auth_mode
        if original_stub_mode is None:
            os.environ.pop("USE_STUB_DATA", None)
        else:
            os.environ["USE_STUB_DATA"] = original_stub_mode
        get_settings.cache_clear()


def _live_core_auth_probe(tenant_id: str) -> Tuple[bool, List[str]]:
    errors: List[str] = []
    core_base = os.getenv("SYNC_CHECK_HRIS_CORE_BASE_URL", "http://localhost:8000").rstrip("/")
    bearer = os.getenv("SYNC_CHECK_BEARER_TOKEN", "")
    if not bearer:
        return False, ["SYNC_CHECK_BEARER_TOKEN is required for --live-core-auth probe"]

    headers = {"Authorization": f"Bearer {bearer}"}
    readiness_path = f"/tenants/{tenant_id}/onboarding/readiness"
    try:
        with httpx.Client(timeout=10.0) as client:
            me_response = client.get(f"{core_base}/me", headers=headers)
            if me_response.status_code >= 400:
                errors.append(f"Core /me probe failed with status {me_response.status_code}")
            else:
                payload = me_response.json()
                for key in ("tenant", "identity_map"):
                    if key not in payload:
                        errors.append(f"Core /me response missing '{key}'")

            readiness_response = client.get(f"{core_base}{readiness_path}", headers=headers)
            if readiness_response.status_code >= 400:
                errors.append(f"Core {readiness_path} probe failed with status {readiness_response.status_code}")
            else:
                readiness_payload = readiness_response.json()
                if "ready_for_activation" not in readiness_payload:
                    errors.append("Onboarding readiness payload missing 'ready_for_activation'")
    except httpx.HTTPError as exc:
        errors.append(f"live core auth probe network error: {exc}")
    return len(errors) == 0, errors


def _module_capability_scan() -> Dict[str, object]:
    checks: List[Dict[str, object]] = []
    modules_root = PROJECT_ROOT.parent / "modules"

    def _read(path: Path) -> str:
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8", errors="ignore")

    srms_main = modules_root / "staff-records" / "backend" / "main.py"
    srms_response_mw = (
        modules_root / "staff-records" / "backend" / "app" / "middleware" / "response_encryption_middleware.py"
    )
    srms_main_text = _read(srms_main)
    srms_response_text = _read(srms_response_mw)
    checks.append(
        {
            "name": "SRMS response encryption middleware detected",
            "ok": "ResponseEncryptionMiddleware" in srms_main_text and "ENCRYPT_ALL_RESPONSES" in srms_response_text,
        }
    )
    checks.append(
        {
            "name": "SRMS source validation middleware detected",
            "ok": "SourceValidationMiddleware" in srms_main_text,
        }
    )

    appraisal_main = modules_root / "performance-appraisal" / "backend" / "app" / "main.py"
    appraisal_main_text = _read(appraisal_main)
    checks.append(
        {
            "name": "eAppraisal tenant middleware detected",
            "ok": "TenantMiddleware" in appraisal_main_text,
        }
    )

    eleave_tenant_routes = modules_root / "eLeave" / "backend" / "routes" / "tenant.php"
    eleave_routes_text = _read(eleave_tenant_routes)
    checks.append(
        {
            "name": "eLeave Sanctum middleware detected",
            "ok": "auth:sanctum" in eleave_routes_text,
        }
    )
    checks.append(
        {
            "name": "eLeave approval action route detected",
            "ok": "LeaveActionController::class" in eleave_routes_text and "/{id}/{action}" in eleave_routes_text,
        }
    )

    passed = sum(1 for c in checks if bool(c["ok"]))
    return {"summary": {"total": len(checks), "passed": passed, "failed": len(checks) - passed}, "checks": checks}


def main() -> int:
    parser = argparse.ArgumentParser(description="HRIS synchronization and contract checker")
    parser.add_argument(
        "--live",
        action="store_true",
        help="Run live module connectivity probe (requires env vars and token)",
    )
    parser.add_argument(
        "--live-eappraisal",
        action="store_true",
        help=(
            "Run live eAppraisal diagnostics probe through /debug/integrations/eappraisal "
            "(requires ENABLE_INTEGRATION_DEBUG_ENDPOINTS=true and valid eAppraisal env vars)"
        ),
    )
    parser.add_argument(
        "--strict-live",
        action="store_true",
        help=(
            "Run both live probes together (--live and --live-eappraisal) and fail fast on any live sync issue"
        ),
    )
    parser.add_argument(
        "--live-core-auth",
        action="store_true",
        help="Run tenant-scoped HRIS Core auth/session + onboarding-readiness probe",
    )
    parser.add_argument(
        "--tenant-id",
        default=os.getenv("SYNC_CHECK_TENANT_ID", "11111111-1111-1111-1111-111111111111"),
        help="Tenant ID used for tenant-scoped live auth probe",
    )
    args = parser.parse_args()

    ok_local, local_errors = _local_contract_checks()
    module_audit_report = run_audit()

    result = {
        "local_contract_checks": {"ok": ok_local, "errors": local_errors},
        "module_source_audit": module_audit_report,
        "module_capability_scan": _module_capability_scan(),
        "live_probe": {"ok": None, "errors": []},
        "live_eappraisal_probe": {"ok": None, "errors": []},
        "live_core_auth_probe": {"ok": None, "errors": []},
    }

    ok_live = True
    run_live_probe = args.live or args.strict_live
    if run_live_probe:
        ok_live, live_errors = _live_module_probe()
        result["live_probe"] = {"ok": ok_live, "errors": live_errors}

    ok_live_eapp = True
    run_live_eapp_probe = args.live_eappraisal or args.strict_live
    if run_live_eapp_probe:
        ok_live_eapp, live_eapp_errors = _live_eappraisal_diagnostics_probe()
        result["live_eappraisal_probe"] = {"ok": ok_live_eapp, "errors": live_eapp_errors}

    ok_live_core_auth = True
    if args.live_core_auth or args.strict_live:
        ok_live_core_auth, live_core_auth_errors = _live_core_auth_probe(args.tenant_id)
        result["live_core_auth_probe"] = {"ok": ok_live_core_auth, "errors": live_core_auth_errors}

    print(json.dumps(result, indent=2))
    module_ok = module_audit_report.get("summary", {}).get("failed", 1) == 0
    capability_ok = result.get("module_capability_scan", {}).get("summary", {}).get("failed", 1) == 0
    return 0 if ok_local and ok_live and ok_live_eapp and ok_live_core_auth and module_ok and capability_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
