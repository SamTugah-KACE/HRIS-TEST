"""Keep platform-owned env files documented without copying or printing secret values."""
from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FILES = [
    ROOT / "apps/backend/hris-core-api/.env",
    ROOT / "apps/backend/hris-core-api/.env.example",
    ROOT / "apps/backend/tenant-registry-service/.env",
    ROOT / "apps/backend/tenant-registry-service/.env.example",
    ROOT / "apps/backend/gateway/.env",
    ROOT / "apps/backend/gateway/.env.example",
    ROOT / "apps/frontend/portal/.env",
    ROOT / "apps/frontend/portal/.env.example",
    ROOT / "infra/.env",
    ROOT / ".env.docker.prod-like.example",
]
DOCKER_FILES = [ROOT / "docker-compose.yml", ROOT / "docker-compose.keycloak.yml", ROOT / "infra/docker-compose.yml"]

SENSITIVE = re.compile(r"(PASSWORD|SECRET|TOKEN|COOKIE|ACCESS_KEY|PRIVATE|CREDENTIAL)", re.I)
ALTERNATIVES = {
    "APP_ENV": "development | staging | production | test",
    "HRIS_APP_ENV": "development | staging | production | test",
    "AUTH_MODE": "keycloak (product runtime); dev is test-only",
    "HRIS_AUTH_MODE": "keycloak (product runtime); dev is test-only",
    "STARTUP_FEDERATED_ENROLLMENT_MODE": "disabled | discover | apply",
    "HRIS_STARTUP_FEDERATED_ENROLLMENT_MODE": "disabled | discover | apply",
    "SMTP_USE_TLS": "true for STARTTLS; false when implicit SSL is used",
    "HRIS_SMTP_USE_TLS": "true for STARTTLS; false when implicit SSL is used",
    "SMTP_USE_SSL": "false for port 587 STARTTLS; true commonly uses port 465",
    "HRIS_SMTP_USE_SSL": "false for port 587 STARTTLS; true commonly uses port 465",
    "MODULE_SERVICE_AUTH_MODE": "shared_secret | jwt_optional | jwt_strict",
    "HRIS_MODULE_SERVICE_AUTH_MODE": "shared_secret | jwt_optional | jwt_strict",
    "MODULE_LAUNCH_OPEN_MODE": "same_window | new_tab",
    "HRIS_MODULE_LAUNCH_OPEN_MODE": "same_window | new_tab",
    "VITE_AUTH_MODE": "keycloak for product UI; dev only for isolated UI work",
    "PORTAL_VITE_AUTH_MODE": "keycloak for production parity",
}


def purpose(name: str) -> str:
    clean = name.removeprefix("HRIS_").removeprefix("VITE_").replace("_", " ").lower()
    if SENSITIVE.search(name):
        return f"Secret/configuration for {clean}; inject securely and never commit a real value."
    if name.endswith(("ENABLED", "ENABLE")) or name.startswith(("ENABLE_", "HRIS_ENABLE_")):
        return f"Feature flag controlling {clean}."
    if name.endswith(("URL", "URI", "BASE_URL", "HOST")):
        return f"Network location used for {clean}."
    if name.endswith(("SECONDS", "TTL")):
        return f"Time limit for {clean}, in seconds."
    if name.endswith(("PORT", "MAX", "RETRIES", "LIMIT")):
        return f"Numeric runtime limit for {clean}."
    return f"Configures {clean}."


def sync_file(path: Path) -> None:
    if not path.exists():
        return
    lines = path.read_text(encoding="utf-8").splitlines()
    output: list[str] = []
    for line in lines:
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$", line)
        if match:
            name = match.group(1)
            previous = output[-1].strip() if output else ""
            if not previous.startswith("# Purpose:"):
                output.append(f"# Purpose: {purpose(name)}")
            alternative = ALTERNATIVES.get(name)
            if alternative:
                output.append(f"# Options: {alternative}.")
        output.append(line)
    path.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")


def add_missing_core_settings(path: Path) -> None:
    sys.path.insert(0, str((ROOT / "apps/backend/hris-core-api").resolve()))
    from app.core.settings import Settings

    text = path.read_text(encoding="utf-8")
    present = set(re.findall(r"^([A-Z][A-Z0-9_]*)=", text, re.M))
    additions: list[str] = []
    for field_name, field in Settings.model_fields.items():
        name = str(field.alias or field_name)
        if not name.isupper() or name in present:
            continue
        default = field.default
        if default is None or str(default).startswith("PydanticUndefined"):
            value = ""
        elif isinstance(default, bool):
            value = str(default).lower()
        else:
            value = str(default)
        if SENSITIVE.search(name) and (default is None or isinstance(default, str)):
            value = ""
        additions.extend([f"# Purpose: {purpose(name)}"])
        if name in ALTERNATIVES:
            additions.append(f"# Options: {ALTERNATIVES[name]}.")
        additions.append(f"{name}={value}")
    if additions:
        path.write_text(text.rstrip() + "\n\n# --- Automatically synchronized settings coverage ---\n" + "\n".join(additions) + "\n", encoding="utf-8")


def sync_docker_comments(path: Path) -> None:
    if not path.exists():
        return
    output: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^(\s+)([A-Z][A-Z0-9_]+):\s*(.*)$", line)
        if match and "${" in match.group(3):
            name = match.group(2)
            previous = output[-1].strip() if output else ""
            if not previous.startswith("# Purpose:"):
                output.append(f"{match.group(1)}# Purpose: {purpose(name)}")
        output.append(line)
    path.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")


def main() -> int:
    for path in FILES:
        sync_file(path)
        if path.name in {".env", ".env.example"} and path.parent.name == "hris-core-api":
            add_missing_core_settings(path)
        print(path.relative_to(ROOT))
    for path in DOCKER_FILES:
        sync_docker_comments(path)
        print(path.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
