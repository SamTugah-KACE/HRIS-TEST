import argparse
import ctypes
import csv
import getpass
import json
import os
import platform
import re
import secrets
import shutil
import socket
import subprocess
import sys
from datetime import datetime, timezone
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import requests


MIN_PASSWORD_LENGTH = 4
DEFAULT_CONFIRMATION_TEXT = "ONBOARD_SUPERADMIN"
DEFAULT_ALLOWED_GROUPS_ENV = "HRIS_SUPERADMIN_ONBOARD_ALLOWED_GROUPS"
DEFAULT_GROUP_BOOTSTRAP_DONE_ENV = "HRIS_SUPERADMIN_ONBOARD_GROUP_BOOTSTRAP_DONE"
DEFAULT_AUDIT_LOG_ENV = "HRIS_SUPERADMIN_ONBOARD_AUDIT_LOG_PATH"
DEFAULT_AUDIT_LOG_PATH = "logs/security/superadmin_onboarding_audit.jsonl"
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
TOOLING_ENV_FILE = REPO_ROOT / ".env.superadmin-onboard"
ENV_FILE_CANDIDATES = [
    TOOLING_ENV_FILE,
    REPO_ROOT / "apps" / "backend" / "hris-core-api" / ".env",
    REPO_ROOT / "apps" / "hris-core-api" / ".env",
    REPO_ROOT / "hris-core-api" / ".env",
    REPO_ROOT / ".env",
]
GENERIC_GROUP_NAMES = {
    "everyone",
    "users",
    "builtin\\users",
    "local",
    "console logon",
    "nt authority\\interactive",
    "nt authority\\authenticated users",
    "nt authority\\this organization",
    "nt authority\\local account",
    "nt authority\\ntlm authentication",
}


@dataclass
class RealmRole:
    role_id: str
    name: str


@dataclass
class OsIdentity:
    username: str
    domain: str
    principal: str


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Securely onboard a Keycloak user with the hris:super_admin realm role. "
            "Performs optional OS credential verification and uniqueness checks."
        )
    )
    parser.add_argument("--base-url", default=os.environ.get("KEYCLOAK_BASE_URL", "http://localhost:8080"))
    parser.add_argument("--admin-realm", default=os.environ.get("KEYCLOAK_ADMIN_REALM", "master"))
    parser.add_argument("--admin-username", default=os.environ.get("KEYCLOAK_ADMIN_USERNAME", "admin"))
    parser.add_argument("--admin-password", default=os.environ.get("KEYCLOAK_ADMIN_PASSWORD"))
    parser.add_argument("--target-realm", default=os.environ.get("KEYCLOAK_REALM", "hris-platform"))
    parser.add_argument("--tenant-id", default="11111111-1111-1111-1111-111111111111")
    parser.add_argument("--username", required=True, help="Preferred username for the new superadmin account.")
    parser.add_argument("--email", default="", help="Email for the new superadmin account. Defaults to username.")
    parser.add_argument(
        "--password",
        default="",
        help="Account password (discouraged on CLI; omit to be prompted securely).",
    )
    parser.add_argument(
        "--require-os-auth",
        action="store_true",
        help="Require current OS user password verification before onboarding (default on Windows).",
    )
    parser.add_argument(
        "--skip-os-auth",
        action="store_true",
        help="Skip account verification (not recommended).",
    )
    parser.add_argument(
        "--os-username",
        default="",
        help="OS account username override for identity verification. Defaults to auto-detected current user.",
    )
    parser.add_argument(
        "--os-domain",
        default="",
        help="OS account domain override for Windows identity verification. Defaults to auto-detected domain.",
    )
    parser.add_argument(
        "--auth-kind",
        choices=["auto", "local", "ssh"],
        default="auto",
        help=(
            "Account verification backend. "
            "'local' verifies local account credentials, "
            "'ssh' verifies SSH account credentials via SSH login, "
            "'auto' selects ssh when running inside an SSH session, else local."
        ),
    )
    parser.add_argument(
        "--ssh-auth-host",
        default="127.0.0.1",
        help="SSH auth host used when --auth-kind=ssh.",
    )
    parser.add_argument(
        "--ssh-auth-port",
        type=int,
        default=22,
        help="SSH auth port used when --auth-kind=ssh.",
    )
    parser.add_argument(
        "--account-auth-mode",
        choices=["auto", "session", "password"],
        default="auto",
        help=(
            "How to authenticate operator authority. "
            "'session' trusts currently authenticated OS/SSH session, "
            "'password' prompts for account password and validates it, "
            "'auto' uses session mode."
        ),
    )
    parser.add_argument(
        "--allow-existing",
        action="store_true",
        help="Allow onboarding when username/email already exists by updating role/password.",
    )
    parser.add_argument(
        "--confirmation-text",
        default=DEFAULT_CONFIRMATION_TEXT,
        help="Confirmation phrase that must be typed interactively before execution.",
    )
    parser.add_argument(
        "--show-account-identities",
        action="store_true",
        help="Print detected execution-account identities and exit.",
    )
    parser.add_argument(
        "--allowed-group",
        action="append",
        default=[],
        help=(
            "Allowed operator group. Repeat for multiple groups. "
            f"If omitted, groups can be provided via {DEFAULT_ALLOWED_GROUPS_ENV}."
        ),
    )
    parser.add_argument(
        "--allowed-groups-env",
        default=DEFAULT_ALLOWED_GROUPS_ENV,
        help="Environment variable name containing comma-separated allowed groups.",
    )
    parser.add_argument(
        "--enforce-group-authorization",
        action="store_true",
        help="Require current operator to belong to at least one allowed group.",
    )
    parser.add_argument(
        "--audit-log-path",
        default=(
            str(os.environ.get(DEFAULT_AUDIT_LOG_ENV) or "").strip()
            or DEFAULT_AUDIT_LOG_PATH
        ),
        help=(
            "Audit log file path (JSONL). "
            f"Defaults to {DEFAULT_AUDIT_LOG_PATH} or env {DEFAULT_AUDIT_LOG_ENV}."
        ),
    )
    parser.add_argument(
        "--disable-audit-log",
        action="store_true",
        help="Disable audit log writes for this run (not recommended).",
    )
    return parser.parse_args()


def _prompt_secret(label: str) -> str:
    return str(getpass.getpass(f"{label}: ")).strip()


def _validate_password_strength(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise RuntimeError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters long.")
    checks = {
        "uppercase": any(ch.isupper() for ch in password),
        "lowercase": any(ch.islower() for ch in password),
        "digit": any(ch.isdigit() for ch in password),
        "symbol": any(not ch.isalnum() for ch in password),
    }
    missing = [name for name, ok in checks.items() if not ok]
    if missing:
        raise RuntimeError(f"Password is missing required character classes: {', '.join(missing)}")


def _normalize_username(raw: str) -> str:
    value = str(raw or "").strip().lower()
    if not value:
        raise RuntimeError("username is required.")
    if not re.fullmatch(r"[a-z0-9._@-]{3,120}", value):
        raise RuntimeError(
            "username must be 3-120 chars and contain only lowercase letters, digits, '.', '_', '-', '@'."
        )
    return value


def _normalize_email(username: str, raw_email: str) -> str:
    value = str(raw_email or "").strip().lower() or username
    if "@" not in value:
        value = f"{value}@hris.local"
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
        raise RuntimeError("email is not valid.")
    return value


def _resolve_os_auth_required(args: argparse.Namespace) -> bool:
    if args.skip_os_auth:
        return False
    if args.require_os_auth:
        return True
    return True


def _resolve_auth_kind(args: argparse.Namespace) -> str:
    if args.auth_kind != "auto":
        return str(args.auth_kind)
    return "ssh" if bool(os.environ.get("SSH_CONNECTION")) else "local"


def _resolve_account_auth_mode(args: argparse.Namespace) -> str:
    if str(args.account_auth_mode) == "auto":
        return "session"
    return str(args.account_auth_mode)


def _csv_values(raw: str) -> list[str]:
    text = str(raw or "").strip()
    if not text:
        return []
    try:
        rows = list(csv.reader([text]))
    except Exception:
        rows = []
    if not rows:
        return [segment.strip() for segment in text.split(",") if segment.strip()]
    return [segment.strip() for segment in rows[0] if segment.strip()]


def _collect_allowed_groups(args: argparse.Namespace) -> list[str]:
    values: list[str] = []
    for item in list(args.allowed_group or []):
        values.extend(_csv_values(str(item)))
    env_name = str(args.allowed_groups_env or DEFAULT_ALLOWED_GROUPS_ENV).strip() or DEFAULT_ALLOWED_GROUPS_ENV
    env_value = str(os.environ.get(env_name) or "").strip()
    if not env_value:
        env_value = str(_read_env_value_from_files(env_name) or "").strip()
    values.extend(_csv_values(env_value))
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = value.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(value.strip())
    return deduped


def _read_env_value_from_files(variable_name: str) -> Optional[str]:
    target = str(variable_name or "").strip()
    if not target:
        return None
    for file_path in ENV_FILE_CANDIDATES:
        if not file_path.exists():
            continue
        try:
            lines = file_path.read_text(encoding="utf-8").splitlines()
        except Exception:
            continue
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            if key.strip() != target:
                continue
            normalized = value.strip().strip('"').strip("'")
            return normalized
    return None


def _upsert_env_value_in_file(file_path: Path, variable_name: str, variable_value: str) -> None:
    key = str(variable_name or "").strip()
    if not key:
        return
    lines = file_path.read_text(encoding="utf-8").splitlines() if file_path.exists() else []
    updated: list[str] = []
    found = False
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            existing_key, _ = stripped.split("=", 1)
            if existing_key.strip() == key:
                updated.append(f"{key}={variable_value}")
                found = True
                continue
        updated.append(line)
    if not found:
        if updated and updated[-1].strip():
            updated.append("")
        updated.append(f"{key}={variable_value}")
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_exists = file_path.exists()
    file_path.write_text("\n".join(updated) + "\n", encoding="utf-8")
    if os.name != "nt" and not file_exists:
        try:
            os.chmod(file_path, 0o600)
        except Exception:
            pass


def _select_env_target_file() -> Path:
    return TOOLING_ENV_FILE


def _bool_from_env(value: Optional[str]) -> bool:
    normalized = str(value or "").strip().lower()
    return normalized in {"1", "true", "yes", "on"}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _append_audit_event(log_path: str, event: dict) -> None:
    target = Path(str(log_path or "").strip() or DEFAULT_AUDIT_LOG_PATH)
    if not target.is_absolute():
        target = Path.cwd() / target
    target.parent.mkdir(parents=True, exist_ok=True)
    event_line = json.dumps(event, ensure_ascii=True)
    file_exists = target.exists()
    with target.open("a", encoding="utf-8") as handle:
        handle.write(event_line + "\n")
    if os.name != "nt" and not file_exists:
        try:
            os.chmod(target, 0o600)
        except Exception:
            pass


def _detect_os_identity() -> OsIdentity:
    username = str(
        os.environ.get("USERNAME")
        or os.environ.get("USER")
        or os.environ.get("LOGNAME")
        or getpass.getuser()
        or ""
    ).strip()
    if not username:
        username = "unknown-user"
    if os.name == "nt":
        domain = str(
            os.environ.get("USERDOMAIN")
            or os.environ.get("COMPUTERNAME")
            or "."
        ).strip() or "."
        principal = f"{domain}\\{username}"
        return OsIdentity(username=username, domain=domain, principal=principal)
    domain = str(socket.gethostname() or "local").strip() or "local"
    principal = f"{username}@{domain}"
    return OsIdentity(username=username, domain=domain, principal=principal)


def _detect_windows_upn() -> str:
    if os.name != "nt":
        return ""
    if not shutil.which("whoami"):
        return ""
    try:
        probe = subprocess.run(
            ["whoami", "/upn"],
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception:
        return ""
    if probe.returncode != 0:
        return ""
    value = str(probe.stdout or "").strip().lower()
    if "@" not in value:
        return ""
    return value


def _detect_windows_sam_identity() -> str:
    if os.name != "nt" or not shutil.which("whoami"):
        return ""
    try:
        probe = subprocess.run(
            ["whoami"],
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception:
        return ""
    if probe.returncode != 0:
        return ""
    return str(probe.stdout or "").strip()


def _detect_windows_user_principal_name() -> str:
    if os.name != "nt" or not shutil.which("powershell"):
        return ""
    command = (
        "[System.Security.Principal.WindowsIdentity]::GetCurrent().Name"
    )
    try:
        probe = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception:
        return ""
    if probe.returncode != 0:
        return ""
    return str(probe.stdout or "").strip()


def _detect_windows_groups() -> list[str]:
    if os.name != "nt" or not shutil.which("powershell"):
        return []
    command = (
        "[System.Security.Principal.WindowsIdentity]::GetCurrent().Groups | "
        "ForEach-Object { "
        "try { $_.Translate([System.Security.Principal.NTAccount]).Value } "
        "catch { $_.Value } "
        "} | ConvertTo-Json -Compress"
    )
    try:
        probe = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception:
        return []
    if probe.returncode != 0:
        return []
    text = str(probe.stdout or "").strip()
    if not text:
        return []
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return []
    if isinstance(payload, list):
        return [str(v).strip() for v in payload if str(v).strip()]
    if isinstance(payload, str) and payload.strip():
        return [payload.strip()]
    return []


def _detect_posix_groups() -> list[str]:
    if shutil.which("id") is None:
        return []
    try:
        probe = subprocess.run(
            ["id", "-Gn"],
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception:
        return []
    if probe.returncode != 0:
        return []
    return [value.strip() for value in str(probe.stdout or "").split() if value.strip()]


def _collect_current_operator_groups() -> list[str]:
    if os.name == "nt":
        groups = _detect_windows_groups()
    else:
        groups = _detect_posix_groups()
    deduped: list[str] = []
    seen: set[str] = set()
    for group in groups:
        key = group.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(group.strip())
    return deduped


def _group_tokens(group_name: str) -> set[str]:
    raw = str(group_name or "").strip()
    if not raw:
        return set()
    tokens = {raw.lower()}
    for sep in ("\\", "/"):
        if sep in raw:
            tokens.add(raw.split(sep)[-1].strip().lower())
    return {token for token in tokens if token}


def _is_generic_group(group_name: str) -> bool:
    return bool(_group_tokens(group_name).intersection(GENERIC_GROUP_NAMES))


def _operator_group_authorized(*, allowed_groups: list[str], operator_groups: list[str]) -> bool:
    allowed_tokens: set[str] = set()
    for value in allowed_groups:
        allowed_tokens.update(_group_tokens(value))
    operator_tokens: set[str] = set()
    for value in operator_groups:
        operator_tokens.update(_group_tokens(value))
    return bool(allowed_tokens.intersection(operator_tokens))


def _recommend_group(groups: list[str]) -> str:
    normalized = [str(group or "").strip() for group in groups if str(group or "").strip()]
    if not normalized:
        return ""
    scored: list[tuple[int, str]] = []
    for group in normalized:
        tail = group.lower().split("\\")[-1]
        score = 0
        if _is_generic_group(group):
            score -= 100
        if "hris" in group.lower():
            score += 120
        if "onboard" in group.lower():
            score += 100
        if "admin" in group.lower():
            score += 80
        if tail in {"sudo", "wheel"}:
            score += 50
        if tail == "docker-users":
            score += 25
        scored.append((score, group))
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[0][1]


def _prompt_bootstrap_group_selection(operator_groups: list[str]) -> str:
    groups = [str(group or "").strip() for group in operator_groups if str(group or "").strip()]
    if not groups:
        raise RuntimeError(
            "No operator groups detected. Configure allowed groups manually in env or via --allowed-group."
        )
    recommended = _recommend_group(groups)
    print(
        "Allowed groups are missing or do not authorize this operator.\n"
        "Select one current operator group to bootstrap allowlist (one-time):"
    )
    for idx, group in enumerate(groups, start=1):
        marker = " (recommended)" if group == recommended else ""
        print(f"  {idx}. {group}{marker}")
    default_idx = groups.index(recommended) + 1 if recommended in groups else 1
    choice = input(f"Choose group number [{default_idx}]: ").strip()
    if not choice:
        return groups[default_idx - 1]
    if not choice.isdigit():
        raise RuntimeError("Invalid bootstrap selection. Please enter a numeric index.")
    selected_idx = int(choice)
    if selected_idx < 1 or selected_idx > len(groups):
        raise RuntimeError("Selected group index is out of range.")
    return groups[selected_idx - 1]


def _enforce_group_authorization(*, required: bool, allowed_groups: list[str], operator_groups: list[str]) -> None:
    if not required:
        return
    if not allowed_groups:
        raise RuntimeError(
            "Group authorization is enabled but no allowed groups were configured. "
            "Provide --allowed-group or set the configured allowed-groups env variable."
        )
    allowed_tokens: set[str] = set()
    for value in allowed_groups:
        allowed_tokens.update(_group_tokens(value))
    operator_tokens: set[str] = set()
    for value in operator_groups:
        operator_tokens.update(_group_tokens(value))
    if not allowed_tokens.intersection(operator_tokens):
        raise RuntimeError(
            "Operator is not in any authorized group for superadmin onboarding. "
            f"allowed_groups={allowed_groups}; detected_operator_groups={operator_groups}"
        )


def _verify_windows_os_password(username: str, password: str, domain: Optional[str]) -> None:
    # Validate operator identity against current Windows account before privileged onboarding.
    logon_user = ctypes.windll.advapi32.LogonUserW  # type: ignore[attr-defined]
    close_handle = ctypes.windll.kernel32.CloseHandle  # type: ignore[attr-defined]
    token_handle = ctypes.c_void_p()
    LOGON32_LOGON_INTERACTIVE = 2
    LOGON32_PROVIDER_DEFAULT = 0

    ok = logon_user(
        ctypes.c_wchar_p(username),
        ctypes.c_wchar_p(domain) if domain is not None else None,
        ctypes.c_wchar_p(password),
        ctypes.c_uint32(LOGON32_LOGON_INTERACTIVE),
        ctypes.c_uint32(LOGON32_PROVIDER_DEFAULT),
        ctypes.byref(token_handle),
    )
    if not ok:
        error_code = ctypes.GetLastError()
        principal = f"{domain}\\{username}" if domain else username
        raise RuntimeError(f"OS authentication failed for '{principal}' (error={error_code}).")
    close_handle(token_handle)


def _verify_windows_os_identity_with_fallbacks(*, username: str, password: str, domain_hint: str) -> tuple[str, str]:
    # Candidate pairs: (username, domain). For UPN logon we pass domain=None.
    candidates: list[tuple[str, Optional[str], str]] = []
    upn = _detect_windows_upn()
    if upn:
        candidates.append((upn, None, upn))

    seen_domain: set[str] = set()

    def add_domain_candidate(domain_value: str) -> None:
        normalized_domain = str(domain_value or "").strip()
        if not normalized_domain or normalized_domain in seen_domain:
            return
        seen_domain.add(normalized_domain)
        candidates.append((username, normalized_domain, f"{normalized_domain}\\{username}"))

    if domain_hint:
        add_domain_candidate(domain_hint)
    for value in (
        os.environ.get("USERDOMAIN"),
        os.environ.get("COMPUTERNAME"),
        ".",
        "AzureAD",
    ):
        add_domain_candidate(str(value or ""))
    errors: list[str] = []
    for candidate_username, candidate_domain, candidate_principal in candidates:
        try:
            _verify_windows_os_password(candidate_username, password, candidate_domain)
            if candidate_domain is None:
                return candidate_username, ""
            return candidate_username, candidate_domain
        except Exception as exc:
            errors.append(f"{candidate_principal}:{exc}")
    raise RuntimeError(
        "OS authentication failed for all detected Windows identity candidates. "
        f"Tried={', '.join([principal for _, _, principal in candidates])}. "
        "Use your account password (not PIN) or pass explicit --os-domain/--os-username. "
        f"Details={'; '.join(errors[:3])}"
    )


def _verify_posix_os_password(username: str, password: str) -> None:
    # Prefer PAM where available because it validates user credentials directly.
    try:
        import pam  # type: ignore
        authenticator = pam.pam()
        if bool(authenticator.authenticate(username, password)):
            return
    except Exception:
        pass

    system_name = platform.system().lower()
    if system_name == "darwin" and shutil.which("dscl"):
        result = subprocess.run(
            ["dscl", "/Search", "-authonly", username, password],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            return
        raise RuntimeError("macOS OS authentication failed (dscl authonly rejected credentials).")

    raise RuntimeError(
        "Local account authentication backend unavailable on this platform. "
        "Install python-pam for local account verification, or use --auth-kind ssh, or run with --skip-os-auth."
    )


def _resolve_operator_identity(args: argparse.Namespace) -> OsIdentity:
    detected = _detect_os_identity()
    username = str(args.os_username or "").strip() or detected.username
    domain = str(args.os_domain or "").strip() or detected.domain
    if os.name == "nt":
        principal = f"{domain}\\{username}"
    else:
        principal = f"{username}@{domain}"
    return OsIdentity(username=username, domain=domain, principal=principal)


def _collect_detected_identities(args: argparse.Namespace) -> dict:
    detected = _detect_os_identity()
    resolved = _resolve_operator_identity(args)
    payload: dict = {
        "os_name": os.name,
        "platform": platform.platform(),
        "env_user": str(
            os.environ.get("USERNAME")
            or os.environ.get("USER")
            or os.environ.get("LOGNAME")
            or ""
        ).strip(),
        "getpass_user": str(getpass.getuser() or "").strip(),
        "detected_identity": {
            "username": detected.username,
            "domain": detected.domain,
            "principal": detected.principal,
        },
        "resolved_identity": {
            "username": resolved.username,
            "domain": resolved.domain,
            "principal": resolved.principal,
        },
        "ssh_connection_present": bool(os.environ.get("SSH_CONNECTION")),
        "detected_operator_groups": _collect_current_operator_groups(),
        "configured_allowed_groups": _collect_allowed_groups(args),
    }
    if os.name == "nt":
        payload["windows"] = {
            "whoami": _detect_windows_sam_identity(),
            "whoami_upn": _detect_windows_upn(),
            "windows_identity_name": _detect_windows_user_principal_name(),
            "userdomain": str(os.environ.get("USERDOMAIN") or "").strip(),
            "computername": str(os.environ.get("COMPUTERNAME") or "").strip(),
        }
    return payload


def _build_audit_context(args: argparse.Namespace) -> dict:
    return {
        "operation": "onboard_keycloak_superadmin",
        "target_username": str(args.username or "").strip().lower(),
        "target_email": str(args.email or "").strip().lower(),
        "tenant_id": str(args.tenant_id or "").strip(),
        "target_realm": str(args.target_realm or "").strip(),
        "auth_kind": str(args.auth_kind or "").strip(),
        "account_auth_mode": str(args.account_auth_mode or "").strip(),
        "group_authorization_requested": bool(args.enforce_group_authorization),
        "allowed_groups_arg_count": len(list(args.allowed_group or [])),
        "ssh_auth_host": str(args.ssh_auth_host or "").strip(),
        "ssh_auth_port": int(args.ssh_auth_port),
        "allow_existing": bool(args.allow_existing),
    }


def _verify_ssh_account_password(*, username: str, password: str, host: str, port: int) -> None:
    try:
        import paramiko  # type: ignore
    except Exception as exc:
        raise RuntimeError(
            "SSH account verification requires 'paramiko'. "
            "Install it with: pip install paramiko"
        ) from exc

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            hostname=host,
            port=int(port),
            username=username,
            password=password,
            allow_agent=False,
            look_for_keys=False,
            timeout=10,
            auth_timeout=10,
            banner_timeout=10,
        )
    except Exception as exc:
        raise RuntimeError(
            "SSH account authentication failed. "
            "Ensure username/password/host/port are correct for deployment SSH access."
        ) from exc
    finally:
        try:
            client.close()
        except Exception:
            pass


def _verify_os_user_identity(
    *,
    required: bool,
    identity: OsIdentity,
    auth_kind: str,
    ssh_host: str,
    ssh_port: int,
) -> OsIdentity:
    if not required:
        return identity
    if auth_kind == "ssh":
        prompt_principal = f"{identity.username}@{ssh_host}:{ssh_port}"
    else:
        prompt_principal = identity.principal
    os_password = _prompt_secret(f"Enter current account password for {prompt_principal}")
    if not os_password:
        raise RuntimeError("Account authentication password is required.")
    if auth_kind == "ssh":
        _verify_ssh_account_password(
            username=identity.username,
            password=os_password,
            host=str(ssh_host or "127.0.0.1").strip() or "127.0.0.1",
            port=int(ssh_port),
        )
        return OsIdentity(
            username=identity.username,
            domain=identity.domain,
            principal=f"{identity.username}@{ssh_host}:{int(ssh_port)}",
        )
    if os.name == "nt":
        username, domain = _verify_windows_os_identity_with_fallbacks(
            username=identity.username,
            password=os_password,
            domain_hint=identity.domain,
        )
        principal = f"{domain}\\{username}" if domain else username
        return OsIdentity(username=username, domain=domain, principal=principal)
    _verify_posix_os_password(identity.username, os_password)
    return identity


def _verify_session_authority(*, identity: OsIdentity, auth_kind: str) -> OsIdentity:
    current_user = str(
        os.environ.get("USERNAME")
        or os.environ.get("USER")
        or os.environ.get("LOGNAME")
        or getpass.getuser()
        or ""
    ).strip()
    if not current_user:
        raise RuntimeError("Unable to resolve current execution account from environment/session.")
    if auth_kind == "ssh":
        if not os.environ.get("SSH_CONNECTION"):
            raise RuntimeError(
                "SSH session context not detected. "
                "Run this command from an active SSH session or use --auth-kind local."
            )
    if identity.username.lower() != current_user.lower():
        raise RuntimeError(
            "Resolved operator identity does not match current execution account. "
            f"resolved='{identity.username}', current='{current_user}'. "
            "Use --os-username/--os-domain overrides if needed."
        )
    return identity


def _token(*, base_url: str, admin_realm: str, username: str, password: str) -> str:
    response = requests.post(
        f"{base_url}/realms/{admin_realm}/protocol/openid-connect/token",
        data={
            "grant_type": "password",
            "client_id": "admin-cli",
            "username": username,
            "password": password,
        },
        timeout=20,
    )
    response.raise_for_status()
    token = str((response.json() or {}).get("access_token") or "").strip()
    if not token:
        raise RuntimeError("Failed to obtain Keycloak admin access token.")
    return token


def _find_user(headers: dict, base_url: str, target_realm: str, *, username: str, email: str) -> Optional[dict]:
    users_endpoint = f"{base_url}/admin/realms/{target_realm}/users"
    for params in ({"username": username, "exact": "true"}, {"email": email, "exact": "true"}):
        response = requests.get(users_endpoint, headers=headers, params=params, timeout=20)
        response.raise_for_status()
        payload = response.json() if isinstance(response.json(), list) else []
        for row in payload:
            if not isinstance(row, dict):
                continue
            row_username = str(row.get("username") or "").strip().lower()
            row_email = str(row.get("email") or "").strip().lower()
            if row_username == username or row_email == email:
                return row
    return None


def _get_realm_role(headers: dict, base_url: str, target_realm: str, role_name: str) -> RealmRole:
    response = requests.get(
        f"{base_url}/admin/realms/{target_realm}/roles/{role_name}",
        headers=headers,
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json() if isinstance(response.json(), dict) else {}
    role_id = str(payload.get("id") or "").strip()
    normalized_name = str(payload.get("name") or role_name).strip()
    if not role_id or not normalized_name:
        raise RuntimeError(f"Failed to resolve role '{role_name}' metadata.")
    return RealmRole(role_id=role_id, name=normalized_name)


def _upsert_user(
    *,
    headers: dict,
    base_url: str,
    target_realm: str,
    tenant_id: str,
    username: str,
    email: str,
    allow_existing: bool,
) -> tuple[str, str]:
    existing = _find_user(headers, base_url, target_realm, username=username, email=email)
    if existing:
        if not allow_existing:
            raise RuntimeError("User already exists with the provided username/email.")
        user_id = str(existing.get("id") or "").strip()
        if not user_id:
            raise RuntimeError("Existing Keycloak user does not expose a stable user id.")
        return user_id, "existing"

    users_endpoint = f"{base_url}/admin/realms/{target_realm}/users"
    payload = {
        "username": username,
        "email": email,
        "enabled": True,
        "emailVerified": True,
        "attributes": {
            "tenant_id": [tenant_id],
            "roles": ["hris:super_admin"],
            "bootstrap_source": ["secure_cli"],
        },
    }
    created = requests.post(users_endpoint, headers=headers, data=json.dumps(payload), timeout=20)
    if created.status_code not in (201, 204):
        raise RuntimeError(f"Failed to create user (status={created.status_code}): {created.text[:180]}")
    # Resolve created user id deterministically.
    created_user = _find_user(headers, base_url, target_realm, username=username, email=email)
    if not created_user:
        raise RuntimeError("User created but could not be reloaded from Keycloak.")
    user_id = str(created_user.get("id") or "").strip()
    if not user_id:
        raise RuntimeError("Created Keycloak user does not expose a stable user id.")
    return user_id, "created"


def _assign_superadmin_role(*, headers: dict, base_url: str, target_realm: str, user_id: str) -> None:
    role = _get_realm_role(headers, base_url, target_realm, "hris:super_admin")
    mapping_url = f"{base_url}/admin/realms/{target_realm}/users/{user_id}/role-mappings/realm"
    current = requests.get(mapping_url, headers=headers, timeout=20)
    current.raise_for_status()
    assigned = current.json() if isinstance(current.json(), list) else []
    assigned_names = {str(row.get("name") or "").strip() for row in assigned if isinstance(row, dict)}
    if role.name in assigned_names:
        return
    add = requests.post(
        mapping_url,
        headers=headers,
        data=json.dumps([{"id": role.role_id, "name": role.name}]),
        timeout=20,
    )
    if add.status_code not in (200, 204):
        raise RuntimeError(f"Failed to assign superadmin role (status={add.status_code}): {add.text[:180]}")


def _set_password(*, headers: dict, base_url: str, target_realm: str, user_id: str, password: str) -> None:
    endpoint = f"{base_url}/admin/realms/{target_realm}/users/{user_id}/reset-password"
    response = requests.put(
        endpoint,
        headers=headers,
        data=json.dumps({"type": "password", "value": password, "temporary": False}),
        timeout=20,
    )
    if response.status_code not in (200, 204):
        raise RuntimeError(f"Failed to set user password (status={response.status_code}): {response.text[:180]}")


def _confirm_execution(expected_text: str) -> None:
    typed = input(f"Type '{expected_text}' to confirm superadmin onboarding: ").strip()
    if typed != expected_text:
        raise RuntimeError("Confirmation phrase did not match. Aborting.")


def main() -> None:
    args = _args()
    audit_enabled = not bool(args.disable_audit_log)
    audit_log_path = str(args.audit_log_path or "").strip() or DEFAULT_AUDIT_LOG_PATH
    audit_context = _build_audit_context(args)
    stage = "start"
    if bool(args.show_account_identities):
        identities_payload = _collect_detected_identities(args)
        if audit_enabled:
            try:
                _append_audit_event(
                    audit_log_path,
                    {
                        "timestamp": _utc_now_iso(),
                        "event": "show_account_identities",
                        "result": "ok",
                        **audit_context,
                        "detected_identity": identities_payload.get("resolved_identity"),
                    },
                )
            except Exception as exc:
                print(f"[WARN] Failed to write audit log: {exc}", file=sys.stderr)
        print(json.dumps(identities_payload, ensure_ascii=True, indent=2))
        return

    try:
        stage = "normalize_target_identity"
        username = _normalize_username(args.username)
        email = _normalize_email(username, args.email)

        stage = "resolve_operator_security_context"
        os_auth_required = _resolve_os_auth_required(args)
        auth_kind = _resolve_auth_kind(args)
        account_auth_mode = _resolve_account_auth_mode(args)
        operator_identity = _resolve_operator_identity(args)
        operator_groups = _collect_current_operator_groups()
        allowed_groups = _collect_allowed_groups(args)
        enforce_group_auth = bool(args.enforce_group_authorization or bool(allowed_groups))

        stage = "resolve_group_authorization"
        bootstrap_done = _bool_from_env(
            os.environ.get(DEFAULT_GROUP_BOOTSTRAP_DONE_ENV)
            or _read_env_value_from_files(DEFAULT_GROUP_BOOTSTRAP_DONE_ENV)
        )
        if enforce_group_auth:
            has_allowed = bool(allowed_groups)
            authorized = _operator_group_authorized(
                allowed_groups=allowed_groups,
                operator_groups=operator_groups,
            ) if has_allowed else False
            if (not has_allowed or not authorized) and not bootstrap_done:
                selected_group = _prompt_bootstrap_group_selection(operator_groups)
                allowed_env_name = (
                    str(args.allowed_groups_env or DEFAULT_ALLOWED_GROUPS_ENV).strip()
                    or DEFAULT_ALLOWED_GROUPS_ENV
                )
                env_target = _select_env_target_file()
                _upsert_env_value_in_file(env_target, allowed_env_name, selected_group)
                _upsert_env_value_in_file(env_target, DEFAULT_GROUP_BOOTSTRAP_DONE_ENV, "true")
                os.environ[allowed_env_name] = selected_group
                os.environ[DEFAULT_GROUP_BOOTSTRAP_DONE_ENV] = "true"
                allowed_groups = [selected_group]
                print(
                    f"[INFO] One-time group bootstrap completed. "
                    f"Set {allowed_env_name}={selected_group} in {env_target}."
                )
            elif (not has_allowed or not authorized) and bootstrap_done:
                raise RuntimeError(
                    "Allowed groups are missing or do not authorize the current operator, and one-time "
                    "bootstrap is already completed. Update env allowlist explicitly."
                )

        stage = "authorize_operator_groups"
        _enforce_group_authorization(
            required=enforce_group_auth,
            allowed_groups=allowed_groups,
            operator_groups=operator_groups,
        )

        stage = "verify_operator_authentication"
        if os_auth_required:
            if account_auth_mode == "password":
                verified_identity = _verify_os_user_identity(
                    required=True,
                    identity=operator_identity,
                    auth_kind=auth_kind,
                    ssh_host=str(args.ssh_auth_host or "127.0.0.1").strip() or "127.0.0.1",
                    ssh_port=int(args.ssh_auth_port),
                )
            else:
                verified_identity = _verify_session_authority(
                    identity=operator_identity,
                    auth_kind=auth_kind,
                )
        else:
            verified_identity = operator_identity

        stage = "confirm_sensitive_action"
        _confirm_execution(args.confirmation_text)

        stage = "collect_target_password"
        password = str(args.password or "").strip()
        if not password:
            password = _prompt_secret("Enter new superadmin password")
        if not password:
            raise RuntimeError("Password is required.")
        password_confirm = _prompt_secret("Confirm new superadmin password")
        if password != password_confirm:
            raise RuntimeError("Password confirmation does not match.")
        _validate_password_strength(password)

        stage = "collect_keycloak_admin_credentials"
        admin_password = str(args.admin_password or "").strip()
        if not admin_password:
            admin_password = _prompt_secret(f"Enter Keycloak admin password for '{args.admin_username}'")
        if not admin_password:
            raise RuntimeError("Keycloak admin password is required.")

        stage = "obtain_keycloak_admin_token"
        token = _token(
            base_url=args.base_url.rstrip("/"),
            admin_realm=args.admin_realm,
            username=args.admin_username,
            password=admin_password,
        )
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        stage = "upsert_target_user"
        user_id, status = _upsert_user(
            headers=headers,
            base_url=args.base_url.rstrip("/"),
            target_realm=args.target_realm,
            tenant_id=args.tenant_id,
            username=username,
            email=email,
            allow_existing=bool(args.allow_existing),
        )

        stage = "assign_superadmin_role"
        _assign_superadmin_role(
            headers=headers,
            base_url=args.base_url.rstrip("/"),
            target_realm=args.target_realm,
            user_id=user_id,
        )

        stage = "set_target_password"
        _set_password(
            headers=headers,
            base_url=args.base_url.rstrip("/"),
            target_realm=args.target_realm,
            user_id=user_id,
            password=password,
        )

        result = {
            "status": "ok",
            "operation": "onboard_keycloak_superadmin",
            "user_status": status,
            "username": username,
            "email": email,
            "tenant_id": args.tenant_id,
            "role_assigned": "hris:super_admin",
            "os_auth_used": os_auth_required,
            "account_auth_kind": auth_kind,
            "account_auth_mode": account_auth_mode,
            "group_authorization_enforced": enforce_group_auth,
            "operator_groups_sample": operator_groups[:20],
            "os_identity": verified_identity.principal,
            "request_id": secrets.token_hex(8),
        }
        if audit_enabled:
            try:
                _append_audit_event(
                    audit_log_path,
                    {
                        "timestamp": _utc_now_iso(),
                        "event": "superadmin_onboarding",
                        "result": "ok",
                        "stage": stage,
                        **audit_context,
                        "os_identity": verified_identity.principal,
                        "operator_groups_sample": operator_groups[:20],
                        "group_authorization_enforced": enforce_group_auth,
                        "user_status": status,
                    },
                )
            except Exception as exc:
                print(f"[WARN] Failed to write audit log: {exc}", file=sys.stderr)
        print(json.dumps(result, ensure_ascii=True))
    except Exception as exc:
        if audit_enabled:
            try:
                _append_audit_event(
                    audit_log_path,
                    {
                        "timestamp": _utc_now_iso(),
                        "event": "superadmin_onboarding",
                        "result": "failed",
                        "stage": stage,
                        **audit_context,
                        "error": str(exc),
                    },
                )
            except Exception as audit_exc:
                print(f"[WARN] Failed to write audit log: {audit_exc}", file=sys.stderr)
        raise


if __name__ == "__main__":
    main()
