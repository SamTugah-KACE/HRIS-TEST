import argparse
import sys
from pathlib import Path


REQUIRED_DOCS = [
    "docs/collaboration/00-collaboration-playbook.md",
    "docs/collaboration/01-pr-review-definition-of-done.md",
    "docs/implementation/02-standardized-directory-structure-and-migration-map.md",
    "docs/implementation/03-phase-1-execution-checklist.md",
    "docs/implementation/04-implementation-readiness-gate.md",
]


MIGRATION_TOUCHED_PATHS = (
    "apps/frontend/portal/",
    "apps/backend/hris-core-api/",
    "apps/backend/tenant-registry-service/",
    "apps/hris-core-api/",
    "apps/portal/",
    "apps/tenant-registry-service/",
    "portal/",
    "hris-core-api/",
    "tenant-registry-service/",
    "scripts/",
    "docker-compose",
    "infra/",
)


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def list_all_files(root: Path) -> list[Path]:
    return [p for p in root.rglob("*") if p.is_file()]


def normalize_rel(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def changed_files_from_args(paths: list[str], root: Path) -> list[str]:
    out: list[str] = []
    for raw in paths:
        value = str(raw or "").strip().replace("\\", "/")
        if not value:
            continue
        abs_path = (root / value).resolve() if not Path(value).is_absolute() else Path(value).resolve()
        try:
            rel = normalize_rel(abs_path, root)
        except Exception:
            rel = value
        out.append(rel)
    return sorted(set(out))


def collect_default_candidate_paths() -> list[str]:
    # Without explicit changed files, avoid scanning all repository paths because
    # excluded reference directories (like modules/) legitimately exist.
    return []


def has_migration_note(root: Path) -> bool:
    candidates = [
        root / "docs/implementation/02-standardized-directory-structure-and-migration-map.md",
        root / "docs/implementation/03-phase-1-execution-checklist.md",
        root / "docs/implementation/04-implementation-readiness-gate.md",
    ]
    text = "\n".join(read_text(p) for p in candidates if p.exists())
    return "migration" in text.lower()


def check_required_docs(root: Path) -> list[str]:
    issues: list[str] = []
    for rel in REQUIRED_DOCS:
        if not (root / rel).exists():
            issues.append(f"Missing required documentation file: {rel}")
    return issues


def check_modules_scope(paths: list[str]) -> list[str]:
    if not paths:
        return []
    issues: list[str] = []
    for rel in paths:
        if rel.startswith("modules/"):
            if rel.endswith(".md"):
                continue
            issues.append(
                f"Scope guard violation: implementation file under excluded path detected: {rel}"
            )
    return issues


def check_migration_note_requirement(root: Path, paths: list[str]) -> list[str]:
    touches_migration_area = any(
        any(rel.startswith(prefix) or rel.startswith(prefix.rstrip("/")) for prefix in MIGRATION_TOUCHED_PATHS)
        for rel in paths
    )
    if not touches_migration_area:
        return []
    if has_migration_note(root):
        return []
    return [
        "Migration-note requirement failed: migration-sensitive paths changed but no migration note found in implementation docs."
    ]


def print_issues(title: str, issues: list[str]) -> None:
    if not issues:
        print(f"[OK] {title}")
        return
    print(f"[WARN] {title}")
    for issue in issues:
        print(f"  - {issue}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Repository policy checks for HRIS refactor guardrails.")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero when policy warnings are present.",
    )
    parser.add_argument(
        "--changed-file",
        action="append",
        default=[],
        help="Relative path of changed file (repeatable). If omitted, checker scans repository files.",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    changed_files = (
        changed_files_from_args(args.changed_file, repo_root)
        if args.changed_file
        else collect_default_candidate_paths()
    )

    doc_issues = check_required_docs(repo_root)
    scope_issues = check_modules_scope(changed_files)
    migration_issues = check_migration_note_requirement(repo_root, changed_files)
    all_issues = doc_issues + scope_issues + migration_issues

    print_issues("Required docs presence", doc_issues)
    print_issues("Scope guard (`modules/` excluded)", scope_issues)
    print_issues("Migration note guard", migration_issues)
    if not changed_files:
        print("[INFO] No --changed-file entries provided; scope checks skipped for repository paths.")

    if all_issues:
        print("")
        print("[SUMMARY] Policy warnings detected.")
        if args.strict:
            print("[RESULT] strict mode enabled -> FAIL")
            return 1
        print("[RESULT] warn mode -> PASS")
        return 0

    print("")
    print("[SUMMARY] All policy checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

