import json
import re
from pathlib import Path
from typing import Dict, List


def _read(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")


def _has(pattern: str, text: str) -> bool:
    return re.search(pattern, text, flags=re.MULTILINE) is not None


def run_audit() -> Dict[str, object]:
    root = Path(__file__).resolve().parents[2]
    modules_root = root / "modules"

    checks: List[Dict[str, object]] = []

    # SRMS checks
    srms_variants = [
        modules_root / "staff-records" / "backend" / "app" / "apis",
        modules_root / "Staff-Records-Management-System" / "Backend" / "app" / "apis",
    ]
    srms_dashboard = None
    srms_employee = None
    for base in srms_variants:
        dashboard_candidate = base / "dashboard_summary_api.py"
        employee_candidate = base / "individual_employee_api.py"
        if dashboard_candidate.exists() and employee_candidate.exists():
            srms_dashboard = dashboard_candidate
            srms_employee = employee_candidate
            break
    if srms_dashboard is None:
        srms_dashboard = srms_variants[0] / "dashboard_summary_api.py"
    if srms_employee is None:
        srms_employee = srms_variants[0] / "individual_employee_api.py"
    srms_adapter = root / "hris-core-api" / "app" / "adapters" / "srms.py"

    srms_dashboard_text = _read(srms_dashboard)
    srms_employee_text = _read(srms_employee)
    srms_adapter_text = _read(srms_adapter)

    checks.extend(
        [
            {
                "name": "SRMS module exposes /api/dashboard/summary",
                "ok": _has(r'prefix="/api/dashboard"', srms_dashboard_text)
                and _has(r'@router\.get\(\s*"/summary"', srms_dashboard_text),
            },
            {
                "name": "SRMS module exposes /api/employees and /api/employees/{id}",
                "ok": _has(r'prefix="/api/employees"', srms_employee_text)
                and _has(r'@router\.get\(\s*"/\{employee_id\}"', srms_employee_text),
            },
            {
                "name": "SRMS adapter has module-native mappings",
                "ok": _has(r'module_path="/api/dashboard/summary"', srms_adapter_text)
                and _has(r'module_path="/api/employees"', srms_adapter_text),
            },
        ]
    )

    # eAppraisal checks
    eapp_main = modules_root / "performance-appraisal" / "backend" / "app" / "main.py"
    eapp_dashboard = modules_root / "performance-appraisal" / "backend" / "app" / "domains" / "organization" / "apis" / "dashboard.py"
    eapp_submission = modules_root / "performance-appraisal" / "backend" / "app" / "domains" / "appraisal" / "apis" / "appraisal_submission.py"
    eapp_bundle = modules_root / "performance-appraisal" / "backend" / "app" / "domains" / "appraisal" / "apis" / "__init__.py"
    eapp_adapter = root / "hris-core-api" / "app" / "adapters" / "eappraisal.py"

    eapp_main_text = _read(eapp_main)
    eapp_dashboard_text = _read(eapp_dashboard)
    eapp_submission_text = _read(eapp_submission)
    eapp_bundle_text = _read(eapp_bundle)
    eapp_adapter_text = _read(eapp_adapter)

    checks.extend(
        [
            {
                "name": "eAppraisal uses /api prefix",
                "ok": _has(r'include_router\(api_router,\s*prefix="/api"\)', eapp_main_text),
            },
            {
                "name": "eAppraisal exposes /api/dashboard/counts",
                "ok": _has(r'@dashboard\.get\(\s*"/dashboard/counts"', eapp_dashboard_text),
            },
            {
                "name": "eAppraisal exposes /api/appraisals/submissions",
                "ok": _has(r"prefix='/appraisals'", eapp_bundle_text)
                and _has(r"prefix='/submissions'", eapp_submission_text),
            },
            {
                "name": "eAppraisal adapter has module-native mappings",
                "ok": _has(r'module_path="/api/dashboard/counts"', eapp_adapter_text)
                and _has(r'paths=\["/api/appraisals/submissions"\]', eapp_adapter_text),
            },
        ]
    )

    # eLeave checks
    eleave_routes = modules_root / "eLeave" / "backend" / "routes" / "tenant.php"
    eleave_adapter = root / "hris-core-api" / "app" / "adapters" / "eleave.py"

    eleave_routes_text = _read(eleave_routes)
    eleave_adapter_text = _read(eleave_adapter)

    checks.extend(
        [
            {
                "name": "eLeave uses tenant path prefix /{tenant}",
                "ok": _has(r"Route::prefix\('/\{tenant\}'\)", eleave_routes_text),
            },
            {
                "name": "eLeave exposes dashboard and leaveHistory routes",
                "ok": _has(r"Route::get\('/dashboard'", eleave_routes_text)
                and _has(r"Route::get\('/\{id\}/leaveHistory'", eleave_routes_text),
            },
            {
                "name": "eLeave adapter has tenant-path module-native mappings",
                "ok": _has(r'module_path=f"\{tenant_prefix\}/dashboard"', eleave_adapter_text)
                and _has(r'leaveHistory', eleave_adapter_text),
            },
        ]
    )

    passed = [c for c in checks if c["ok"]]
    failed = [c for c in checks if not c["ok"]]
    return {
        "summary": {"total": len(checks), "passed": len(passed), "failed": len(failed)},
        "checks": checks,
    }


def main() -> int:
    report = run_audit()
    print(json.dumps(report, indent=2))
    return 0 if report["summary"]["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
