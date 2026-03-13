import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import requests


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Reset a Keycloak realm from a realm export file.")
    parser.add_argument("--base-url", default="http://localhost:8080")
    parser.add_argument("--admin-realm", default="master")
    parser.add_argument("--admin-username", default="admin")
    parser.add_argument("--admin-password", default="admin")
    parser.add_argument("--target-realm", default="hris-platform")
    parser.add_argument("--realm-file", default="identity/realm-export.json")
    parser.add_argument(
        "--exclude-users",
        action="store_true",
        help="Exclude users from imported realm payload for a clean account reset.",
    )
    return parser.parse_args()


def _token(base_url: str, admin_realm: str, username: str, password: str) -> str:
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


def main() -> None:
    args = _args()
    token = _token(
        base_url=args.base_url,
        admin_realm=args.admin_realm,
        username=args.admin_username,
        password=args.admin_password,
    )
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    # Backup current target realm before destructive delete.
    backup_dir = Path("identity/backups")
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / f"{args.target_realm}-backup-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    current = requests.get(f"{args.base_url}/admin/realms/{args.target_realm}", headers=headers, timeout=20)
    if current.status_code == 200:
        backup_path.write_text(json.dumps(current.json(), ensure_ascii=True, indent=2), encoding="utf-8")
        print(f"backup_saved={backup_path}")

    delete_response = requests.delete(f"{args.base_url}/admin/realms/{args.target_realm}", headers=headers, timeout=20)
    if delete_response.status_code not in (204, 404):
        raise RuntimeError(f"Realm delete failed ({delete_response.status_code}): {delete_response.text[:250]}")
    print(f"delete_status={delete_response.status_code}")

    payload = json.loads(Path(args.realm_file).read_text(encoding="utf-8"))
    if args.exclude_users:
        payload.pop("users", None)
        payload.pop("events", None)
        payload.pop("adminEvents", None)

    create_response = requests.post(
        f"{args.base_url}/admin/realms",
        headers=headers,
        data=json.dumps(payload),
        timeout=30,
    )
    if create_response.status_code not in (201, 409):
        raise RuntimeError(f"Realm create failed ({create_response.status_code}): {create_response.text[:250]}")
    print(f"create_status={create_response.status_code}")

    users_response = requests.get(
        f"{args.base_url}/admin/realms/{args.target_realm}/users",
        headers=headers,
        params={"max": 10},
        timeout=20,
    )
    users_response.raise_for_status()
    users = users_response.json() if isinstance(users_response.json(), list) else []
    print(f"user_count_sample={len(users)}")


if __name__ == "__main__":
    main()
