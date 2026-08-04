"""Delete and re-import one Keycloak realm with explicit destructive safeguards."""
import argparse
import json
import os
import sys
import re
from pathlib import Path
from urllib.parse import urlparse

import httpx


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8080")
    parser.add_argument("--realm", default="hris-platform")
    parser.add_argument("--admin-realm", default="master")
    parser.add_argument("--admin-username", default=os.getenv("KEYCLOAK_ADMIN_USERNAME", "admin"))
    parser.add_argument("--realm-file", default="identity/realm-export.json")
    parser.add_argument("--confirm-realm", required=True, help="Must exactly match --realm")
    parser.add_argument("--allow-remote", action="store_true", help="Permit a non-loopback Keycloak target")
    parser.add_argument("--keep-seed-users", action="store_true", help="Retain users embedded in the realm export")
    parser.add_argument("--reset-hris-enrollment-state", action="store_true", help="Also clear identity/welcome/job state using AUTOMATION_STORE_DATABASE_URL")
    args = parser.parse_args()

    if args.confirm_realm != args.realm:
        print("Refusing reset: --confirm-realm must exactly match --realm.", file=sys.stderr)
        return 2
    host = (urlparse(args.base_url).hostname or "").lower()
    if host not in {"localhost", "127.0.0.1", "::1"} and not args.allow_remote:
        print("Refusing remote reset without --allow-remote.", file=sys.stderr)
        return 2
    password = os.getenv("KEYCLOAK_ADMIN_PASSWORD", "")
    if not password:
        print("Set KEYCLOAK_ADMIN_PASSWORD in the current shell; it is intentionally not accepted on the command line.", file=sys.stderr)
        return 2
    realm_path = Path(args.realm_file).resolve()
    payload = json.loads(realm_path.read_text(encoding="utf-8-sig"))
    payload["realm"] = args.realm
    removed_users = len(payload.get("users") or [])
    if not args.keep_seed_users:
        payload["users"] = []
    base = args.base_url.rstrip("/")
    with httpx.Client(timeout=30, trust_env=False) as client:
        token_response = client.post(
            f"{base}/realms/{args.admin_realm}/protocol/openid-connect/token",
            data={"grant_type": "password", "client_id": "admin-cli", "username": args.admin_username, "password": password},
        )
        token_response.raise_for_status()
        headers = {"Authorization": f"Bearer {token_response.json()['access_token']}"}
        existing = client.get(f"{base}/admin/realms/{args.realm}", headers=headers)
        if existing.status_code == 200:
            deleted = client.delete(f"{base}/admin/realms/{args.realm}", headers=headers)
            deleted.raise_for_status()
            print(f"Deleted Keycloak realm '{args.realm}'. This cannot be undone except from a backup/export.")
        elif existing.status_code != 404:
            existing.raise_for_status()
        imported = client.post(f"{base}/admin/realms", headers=headers, json=payload)
        imported.raise_for_status()
    print(f"Imported clean realm '{args.realm}' from {realm_path}; seed users removed={0 if args.keep_seed_users else removed_users}.")
    if args.reset_hris_enrollment_state:
        database_url = os.getenv("AUTOMATION_STORE_DATABASE_URL", "")
        schema = os.getenv("AUTOMATION_STORE_SCHEMA", "hris_automation")
        if not database_url:
            print("Realm reset completed, but AUTOMATION_STORE_DATABASE_URL is required to clear HRIS enrollment state.", file=sys.stderr)
            return 3
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", schema):
            print("Invalid AUTOMATION_STORE_SCHEMA.", file=sys.stderr)
            return 3
        import psycopg
        from psycopg import sql
        table_names = ("identity_mappings", "welcome_dispatch", "enrollment_jobs", "email_delivery_audit")
        with psycopg.connect(database_url) as conn:
            with conn.cursor() as cursor:
                for table_name in table_names:
                    cursor.execute(sql.SQL("TRUNCATE TABLE {}.{} RESTART IDENTITY").format(sql.Identifier(schema), sql.Identifier(table_name)))
        print("Cleared HRIS identity, welcome, enrollment-job, and email-delivery state.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
