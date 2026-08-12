"""Reset a Keycloak realm and, optionally, HRIS enrollment persistence.

This utility is intentionally operating-system independent: it uses the
Keycloak Admin API and psycopg rather than shell-specific commands or psql.
"""

import argparse
import getpass
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

import httpx


LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}
ENROLLMENT_TABLES = (
    "identity_mappings",
    "welcome_dispatch",
    "enrollment_jobs",
    "email_delivery_audit",
)


def _read_env_value(path: Path, name: str) -> str:
    """Read one unquoted or quoted value without importing the whole env file."""
    if not path.is_file():
        return ""
    prefix = f"{name}="
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or not line.startswith(prefix):
            continue
        value = line[len(prefix):].strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        return value
    return ""


def _database_url(env_file: Path) -> str:
    return os.getenv("AUTOMATION_STORE_DATABASE_URL", "").strip() or _read_env_value(
        env_file, "AUTOMATION_STORE_DATABASE_URL"
    )


def _validate_local_target(url: str, *, label: str, allow_remote: bool) -> None:
    host = (urlparse(url).hostname or "").lower()
    if host not in LOOPBACK_HOSTS and not allow_remote:
        raise ValueError(f"Refusing remote {label} target without --allow-remote.")


def _load_realm_payload(realm_file: Path, realm: str, keep_seed_users: bool) -> tuple[dict, int]:
    payload = json.loads(realm_file.read_text(encoding="utf-8-sig"))
    payload["realm"] = realm
    embedded_users = len(payload.get("users") or [])
    if not keep_seed_users:
        payload["users"] = []
    return payload, embedded_users


def _reset_realm(args: argparse.Namespace, payload: dict, password: str) -> None:
    base = args.base_url.rstrip("/")
    with httpx.Client(timeout=30, trust_env=False) as client:
        token_response = client.post(
            f"{base}/realms/{args.admin_realm}/protocol/openid-connect/token",
            data={
                "grant_type": "password",
                "client_id": "admin-cli",
                "username": args.admin_username,
                "password": password,
            },
        )
        token_response.raise_for_status()
        headers = {"Authorization": f"Bearer {token_response.json()['access_token']}"}
        existing = client.get(f"{base}/admin/realms/{args.realm}", headers=headers)
        if existing.status_code == 200:
            deleted = client.delete(f"{base}/admin/realms/{args.realm}", headers=headers)
            deleted.raise_for_status()
            print(f"Deleted Keycloak realm '{args.realm}'.")
        elif existing.status_code != 404:
            existing.raise_for_status()
        imported = client.post(f"{base}/admin/realms", headers=headers, json=payload)
        imported.raise_for_status()


def _clear_enrollment_state(database_url: str, schema: str) -> None:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", schema):
        raise ValueError("Invalid AUTOMATION_STORE_SCHEMA.")
    import psycopg
    from psycopg import sql

    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cursor:
            for table_name in ENROLLMENT_TABLES:
                cursor.execute(
                    sql.SQL("TRUNCATE TABLE {}.{} RESTART IDENTITY").format(
                        sql.Identifier(schema), sql.Identifier(table_name)
                    )
                )


def _drop_database(database_url: str, confirmed_database: str, allow_remote: bool) -> str:
    """Drop the URL's database through a maintenance connection."""
    import psycopg
    from psycopg import sql

    parsed = urlparse(database_url)
    database_name = parsed.path.lstrip("/")
    if not database_name:
        raise ValueError("AUTOMATION_STORE_DATABASE_URL does not name a database.")
    if database_name in {"postgres", "template0", "template1"}:
        raise ValueError(f"Refusing to drop protected database '{database_name}'.")
    if confirmed_database != database_name:
        raise ValueError("--confirm-database must exactly match the database in AUTOMATION_STORE_DATABASE_URL.")
    _validate_local_target(database_url, label="PostgreSQL", allow_remote=allow_remote)

    maintenance_url = parsed._replace(path="/postgres").geturl()
    with psycopg.connect(maintenance_url, autocommit=True) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()",
                (database_name,),
            )
            cursor.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(database_name)))
    return database_name


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8080")
    parser.add_argument("--realm", default="hris-platform")
    parser.add_argument("--admin-realm", default="master")
    parser.add_argument("--admin-username", default=os.getenv("KEYCLOAK_ADMIN_USERNAME", "admin"))
    parser.add_argument("--realm-file", default="identity/realm-export.json")
    parser.add_argument("--env-file", default="apps/backend/hris-core-api/.env")
    parser.add_argument("--confirm-realm", required=True, help="Must exactly match --realm")
    parser.add_argument("--allow-remote", action="store_true", help="Permit non-loopback Keycloak/PostgreSQL targets")
    parser.add_argument("--keep-seed-users", action="store_true", help="Retain users embedded in the realm export")
    persistence = parser.add_mutually_exclusive_group()
    persistence.add_argument(
        "--reset-hris-enrollment-state",
        action="store_true",
        help="Truncate identity/welcome/job/email state while retaining the database",
    )
    persistence.add_argument(
        "--drop-automation-database",
        action="store_true",
        help="Drop the complete automation/tenant-registry database for a fresh first start",
    )
    parser.add_argument(
        "--confirm-database",
        default="",
        help="Required with --drop-automation-database; must exactly match the target database",
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    try:
        if args.confirm_realm != args.realm:
            raise ValueError("--confirm-realm must exactly match --realm.")
        _validate_local_target(args.base_url, label="Keycloak", allow_remote=args.allow_remote)

        realm_path = Path(args.realm_file).resolve()
        payload, embedded_users = _load_realm_payload(realm_path, args.realm, args.keep_seed_users)

        database_url = ""
        if args.reset_hris_enrollment_state or args.drop_automation_database:
            database_url = _database_url(Path(args.env_file).resolve())
            if not database_url:
                raise ValueError(
                    "AUTOMATION_STORE_DATABASE_URL is required in the environment or --env-file."
                )
        if args.drop_automation_database:
            parsed_database = urlparse(database_url).path.lstrip("/")
            if args.confirm_database != parsed_database:
                raise ValueError(
                    "--confirm-database must exactly match the database in AUTOMATION_STORE_DATABASE_URL."
                )

        password = os.getenv("KEYCLOAK_ADMIN_PASSWORD", "")
        if not password:
            password = getpass.getpass("Keycloak admin password: ")
        if not password:
            raise ValueError("A Keycloak admin password is required.")

        # Authenticate before making either destructive change.
        _reset_realm(args, payload, password)
        removed_users = 0 if args.keep_seed_users else embedded_users
        print(f"Imported clean realm '{args.realm}' from {realm_path}; seed users removed={removed_users}.")

        if args.reset_hris_enrollment_state:
            schema = os.getenv("AUTOMATION_STORE_SCHEMA", "").strip() or _read_env_value(
                Path(args.env_file).resolve(), "AUTOMATION_STORE_SCHEMA"
            ) or "hris_automation"
            _clear_enrollment_state(database_url, schema)
            print("Cleared HRIS identity, welcome, enrollment-job, and email-delivery state.")
        elif args.drop_automation_database:
            dropped = _drop_database(database_url, args.confirm_database, args.allow_remote)
            print(f"Dropped PostgreSQL database '{dropped}'. It will be recreated on the next Core startup.")
        return 0
    except (ValueError, FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"Refusing reset: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"Reset failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
