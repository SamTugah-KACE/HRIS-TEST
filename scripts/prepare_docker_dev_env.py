"""Create an ignored Docker-development env file from the working Core API env."""
from __future__ import annotations

import argparse
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "apps" / "backend" / "hris-core-api" / ".env"
TARGET = ROOT / ".env.docker.development"
COMPOSE_FILES = (ROOT / "docker-compose.yml", ROOT / "docker-compose.keycloak.yml")


def _dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        else:
            value = re.split(r"\s+#", value, maxsplit=1)[0].rstrip()
        values[key] = value
    return values


def _required_hris_keys() -> set[str]:
    text = "\n".join(path.read_text(encoding="utf-8-sig") for path in COMPOSE_FILES)
    return set(re.findall(r"\$\{(HRIS_[A-Z0-9_]+)", text))


def _safe_env_value(value: str) -> str:
    # Compose interpolates dollar signs in env-file values; doubling preserves them.
    return value.replace("$", "$$").replace("\r", "").replace("\n", "\\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--output", type=Path, default=TARGET)
    args = parser.parse_args()
    source, output = args.source.resolve(), args.output.resolve()
    if not source.is_file():
        parser.error(f"Source env file does not exist: {source}")
    if output.parent != ROOT:
        parser.error("Docker development env output must stay in the repository root")

    source_values = _dotenv(source)
    required = _required_hris_keys()
    generated: dict[str, str] = {}
    for docker_key in sorted(required):
        source_key = docker_key.removeprefix("HRIS_")
        if source_key in source_values:
            generated[docker_key] = source_values[source_key]

    # Browser-facing URLs stay on localhost; container-to-container URLs use service DNS.
    generated.update(
        {
            "HRIS_APP_ENV": "development",
            "HRIS_DATA_SOURCE_MODE": "production",
            "HRIS_AUTH_MODE": "keycloak",
            "HRIS_DEPLOYMENT_MODE": "single",
            "HRIS_ALLOW_SINGLE_NODE_PRODUCTION": "false",
            "HRIS_COMPONENT_PRIMARY_DATABASE_MODE": "required",
            "HRIS_COMPONENT_TENANT_REGISTRY_MODE": "required",
            "HRIS_COMPONENT_KEYCLOAK_MODE": "required",
            "HRIS_COMPONENT_AUDIT_LOG_MODE": "required",
            "HRIS_COMPONENT_REDIS_MODE": "optional",
            "HRIS_COMPONENT_BACKGROUND_WORKERS_MODE": "optional",
            "HRIS_COMPONENT_SCHEDULER_MODE": "optional",
            "HRIS_COMPONENT_SRMS_MODE": "optional",
            "HRIS_COMPONENT_EAPPRAISAL_MODE": "optional",
            "HRIS_COMPONENT_ELEAVE_MODE": "disabled",
            "HRIS_COMPONENT_SMS_MODE": "disabled",
            "HRIS_COMPONENT_EMAIL_MODE": "optional",
            "HRIS_COMPONENT_DATABASE_SHARDING_MODE": "disabled",
            "HRIS_COMPONENT_SHARD_ROUTER_MODE": "optional",
            "HRIS_COMPONENT_METRICS_MODE": "optional",
            "HRIS_COMPONENT_TRACING_MODE": "disabled",
            "HRIS_COMPONENT_NETWORK_MONITORING_MODE": "disabled",
            "HRIS_USE_STUB_DATA": "false",
            "HRIS_SRMS_BASE_URL": source_values.get("SRMS_BASE_URL", "https://srms.gi-kace.com.gh"),
            "HRIS_SRMS_HRIS_SHARED_SECRET": source_values.get("SRMS_HRIS_SHARED_SECRET", ""),
            "HRIS_SRMS_HRIS_SERVICE_TOKEN": source_values.get("SRMS_HRIS_SERVICE_TOKEN", ""),
            "HRIS_EAPPRAISAL_INTEGRATION_BASE_URL": source_values.get("EAPPRAISAL_INTEGRATION_BASE_URL", "https://appraisal.gi-kace.com.gh"),
            "HRIS_EAPPRAISAL_HRIS_SHARED_SECRET": source_values.get("EAPPRAISAL_HRIS_SHARED_SECRET", ""),
            "HRIS_EAPPRAISAL_HRIS_SERVICE_TOKEN": source_values.get("EAPPRAISAL_HRIS_SERVICE_TOKEN", ""),
            "HRIS_KEYCLOAK_ISSUER": "http://localhost:8080/realms/hris-platform",
            "HRIS_KEYCLOAK_INTERNAL_BASE_URL": "http://keycloak:8080",
            "HRIS_KEYCLOAK_JWKS_URL": "http://keycloak:8080/realms/hris-platform/protocol/openid-connect/certs",
            "HRIS_AUTH_SSO_CALLBACK_URL": "http://localhost:8000/auth/sso/callback",
            "HRIS_PORTAL_BASE_URL": "http://localhost:5173",
            "HRIS_CORS_ALLOWED_ORIGINS": "http://localhost:5173,http://127.0.0.1:5173",
            "HRIS_TENANT_REGISTRY_BASE_URL": "http://tenant-registry:8000",
            "HRIS_TENANT_REGISTRY_ALLOW_FALLBACK": "false",
            "HRIS_TENANT_REGISTRY_STARTUP_WAIT_FAIL_OPEN": "false",
            # These are real, idempotent module inventory reconciliations—not
            # sample-data seeding. Preserve the operator's local source policy.
            "HRIS_ENABLE_STARTUP_TENANT_INVENTORY_IMPORT": source_values.get("ENABLE_STARTUP_TENANT_INVENTORY_IMPORT", "false"),
            "HRIS_ENABLE_STARTUP_EAPPRAISAL_TENANT_INVENTORY_IMPORT": source_values.get("ENABLE_STARTUP_EAPPRAISAL_TENANT_INVENTORY_IMPORT", "false"),
            "HRIS_STARTUP_FEDERATED_ENROLLMENT_MODE": "disabled",
            "HRIS_ENABLE_AUTO_SYNC_LOOP": source_values.get("ENABLE_AUTO_SYNC_LOOP", "false"),
            "HRIS_ENABLE_POST_DEPLOY_SYNC_AUTOMATION": "false",
            "HRIS_ONBOARDING_AUTO_SYNC_NEW_TENANTS": source_values.get("ONBOARDING_AUTO_SYNC_NEW_TENANTS", "false"),
            "HRIS_ONBOARDING_AUTO_KEYCLOAK_PROVISION": "false",
            "HRIS_ONBOARDING_WELCOME_EMAIL_ENABLED": "false",
            "HRIS_TENANT_INVENTORY_AUTO_CREATE_CANONICAL": source_values.get("TENANT_INVENTORY_AUTO_CREATE_CANONICAL", "false"),
            "HRIS_ENROLLMENT_REFRESH_TENANT_INVENTORY": "true",
            "HRIS_AUTOMATION_STORE_DATABASE_URL": "postgresql://hris:hris_secret@postgres:5432/hris_tenant_registry",
            "HRIS_DB_BOOTSTRAP_ADMIN_URL": "postgresql://hris:hris_secret@postgres:5432/postgres",
            "HRIS_KEYCLOAK_EMAIL_THEME": "hris-platform",
            "HRIS_AUTH_RECOVERY_MODE": "disabled",
            "HRIS_AUTH_RECOVERY_MANUAL_ACTIVE": "false",
            "HRIS_AUTH_COOKIE_SECURE": "false",
            "HRIS_AUTH_COOKIE_SAMESITE": "lax",
            "HRIS_AUTH_CSRF_ENABLED": "true",
            "HRIS_BOOTSTRAP_ADMIN_ENABLED": "false",
            "HRIS_ENABLE_JIT_MODULE_SETUP": "false",
            "HRIS_JIT_AUTO_BOOTSTRAP_ENABLED": "false",
            "PORTAL_VITE_HRIS_CORE_API_BASE_URL": "http://localhost:8000",
            "PORTAL_VITE_AUTH_MODE": "keycloak",
            "PORTAL_HOST_PORT": "5173",
            "PGADMIN_DEFAULT_EMAIL": "admin@example.com",
            "PGADMIN_DEFAULT_PASSWORD": "admin",
        }
    )

    lines = [
        "# Generated by scripts/prepare_docker_dev_env.py; ignored by Git.",
        "# Re-run after changing apps/backend/hris-core-api/.env.",
    ]
    lines.extend(f"{key}={_safe_env_value(value)}" for key, value in sorted(generated.items()))
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Generated {output} with {len(generated)} Docker development settings.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
