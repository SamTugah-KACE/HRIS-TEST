"""Install/verify the HRIS Keycloak theme and activate it on the realm.

Docker Compose is detected automatically. For a standalone Keycloak, pass
--keycloak-home. Re-running the script is safe and idempotent.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

import httpx


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "identity" / "themes" / "hris-platform"
DEFAULT_ENV = ROOT / "apps" / "backend" / "hris-core-api" / ".env"


def _read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key.strip()] = value
    return values


def _run(command: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command, cwd=ROOT, check=check, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )


def _docker_container_id() -> str:
    try:
        result = _run(["docker", "compose", "ps", "-q", "keycloak"], check=False)
    except FileNotFoundError:
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def _is_keycloak_home(path: Path) -> bool:
    return (path / "bin" / "kc.bat").is_file() or (path / "bin" / "kc.sh").is_file()


def _discover_keycloak_home(env: dict[str, str]) -> Optional[Path]:
    explicit = os.getenv("KEYCLOAK_HOME") or env.get("KEYCLOAK_HOME", "")
    if explicit and _is_keycloak_home(Path(explicit)):
        return Path(explicit)
    candidates = [Path("/opt/keycloak"), Path("/usr/local/keycloak")]
    if os.name == "nt":
        candidates.extend(sorted(Path("C:/").glob("keycloak-*"), reverse=True))
    return next((path for path in candidates if _is_keycloak_home(path)), None)


def _validate_source(source: Path) -> None:
    required = (
        source / "email" / "theme.properties",
        source / "email" / "messages" / "messages_en.properties",
    )
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError("Theme is incomplete; missing: " + ", ".join(missing))


def _install_local(source: Path, keycloak_home: Path, theme_name: str) -> Path:
    home = keycloak_home.resolve()
    if not (home / "bin" / "kc.bat").is_file() and not (home / "bin" / "kc.sh").is_file():
        raise ValueError(f"Not a Keycloak installation: {home}")
    destination = home / "themes" / theme_name
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, destination, dirs_exist_ok=True)
    return destination


def _verify_docker_theme(container_id: str, theme_name: str) -> str:
    target = f"/opt/keycloak/themes/{theme_name}/email/theme.properties"
    result = _run(["docker", "exec", container_id, "test", "-f", target], check=False)
    if result.returncode != 0:
        raise RuntimeError(
            f"Theme is not mounted at {target}. Start Keycloak with docker-compose.yml, "
            "which mounts identity/themes/hris-platform into the container."
        )
    return target


def _configure_realm(
    *, base_url: str, realm: str, admin_realm: str, username: str,
    password: str, theme_name: str,
) -> None:
    if not password:
        raise ValueError("KEYCLOAK_ADMIN_PASSWORD is required to activate the theme")
    base = base_url.rstrip("/")
    with httpx.Client(timeout=30, trust_env=False) as client:
        token_response = client.post(
            f"{base}/realms/{admin_realm}/protocol/openid-connect/token",
            data={
                "grant_type": "password", "client_id": "admin-cli",
                "username": username, "password": password,
            },
        )
        token_response.raise_for_status()
        headers = {"Authorization": f"Bearer {token_response.json()['access_token']}"}
        realm_url = f"{base}/admin/realms/{realm}"
        response = client.get(realm_url, headers=headers)
        response.raise_for_status()
        payload = response.json()
        if payload.get("emailTheme") == theme_name:
            return
        payload["emailTheme"] = theme_name
        updated = client.put(realm_url, headers=headers, json=payload)
        updated.raise_for_status()


def _restart(container_id: str, keycloak_home: Optional[Path]) -> None:
    if container_id:
        _run(["docker", "compose", "restart", "keycloak"])
        return
    if keycloak_home:
        print("Standalone theme installed. Restart the Keycloak service/process to reload it.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keycloak-home", type=Path, help="Standalone Keycloak installation directory")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--theme-name", default="hris-platform")
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV)
    parser.add_argument("--base-url", default="http://localhost:8080")
    parser.add_argument("--realm", default="hris-platform")
    parser.add_argument("--admin-realm", default="master")
    parser.add_argument("--restart", action="store_true", help="Restart Docker Keycloak after verification")
    parser.add_argument("--skip-realm-config", action="store_true")
    args = parser.parse_args()

    try:
        source = args.source.resolve()
        _validate_source(source)
        env = _read_env(args.env_file.resolve())
        container_id = "" if args.keycloak_home else _docker_container_id()
        keycloak_home = args.keycloak_home or (None if container_id else _discover_keycloak_home(env))
        if container_id:
            installed_at = _verify_docker_theme(container_id, args.theme_name)
            deployment = "docker-mounted"
        elif keycloak_home:
            installed_at = str(_install_local(source, keycloak_home, args.theme_name))
            deployment = "standalone"
        else:
            raise RuntimeError(
                "No running Docker Compose Keycloak detected. Start it first or pass --keycloak-home."
            )

        if args.restart:
            _restart(container_id, keycloak_home)

        realm_configured = False
        if not args.skip_realm_config:
            _configure_realm(
                base_url=args.base_url,
                realm=args.realm,
                admin_realm=args.admin_realm,
                username=os.getenv("KEYCLOAK_ADMIN_USERNAME") or env.get("KEYCLOAK_ADMIN_USERNAME", "admin"),
                password=os.getenv("KEYCLOAK_ADMIN_PASSWORD") or env.get("KEYCLOAK_ADMIN_PASSWORD", ""),
                theme_name=args.theme_name,
            )
            realm_configured = True

        print(json.dumps({
            "installed": True, "deployment": deployment, "location": installed_at,
            "theme": args.theme_name, "realm": args.realm,
            "realm_configured": realm_configured,
        }, indent=2))
        return 0
    except Exception as exc:
        print(f"Theme installation failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
