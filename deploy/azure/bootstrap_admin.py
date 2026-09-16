"""Interactive, one-shot first HRIS administrator creation. No emailed passwords."""
import getpass
import sys

import httpx

from app.core.settings import get_settings
from app.services.keycloak_provisioning import (
    _admin_access_token, _admin_base_url, _target_realm_from_issuer,
    ensure_user_and_temp_password,
)


def main():
    if not sys.stdin.isatty():
        raise SystemExit("Use an interactive terminal for hidden password entry.")
    settings = get_settings()
    settings.validate_runtime()
    base, realm = _admin_base_url(), _target_realm_from_issuer()
    with httpx.Client(timeout=30, trust_env=False) as client:
        headers = {"Authorization": "Bearer " + _admin_access_token(client)}
        existing = client.get(f"{base}/admin/realms/{realm}/roles/hris:super_admin/users", headers=headers, params={"max": 1})
        existing.raise_for_status()
        if existing.json():
            raise SystemExit("An HRIS superadmin already exists. No account/password was changed. Use normal sign-in or password recovery.")
        username = input("First HRIS superadmin username: ").strip().lower()
        email = input("Superadmin email (an address you control): ").strip().lower()
        if not username or "@" not in email:
            raise SystemExit("A username and valid email are required.")
        # Do not let ensure_user_and_temp_password reset/promote an existing user.
        for field, value in (("username", username), ("email", email)):
            found = client.get(f"{base}/admin/realms/{realm}/users", headers=headers, params={field: value, "exact": "true"})
            found.raise_for_status()
            if found.json():
                raise SystemExit("This username/email already exists. Stopping without changing it; inspect the existing account.")
    password = getpass.getpass("New HRIS password (at least 16 characters; hidden): ")
    confirmation = getpass.getpass("Repeat HRIS password: ")
    if len(password) < 16 or password != confirmation:
        raise SystemExit("Passwords must match and contain at least 16 characters.")
    result = ensure_user_and_temp_password(
        email=email, username=username, tenant_id="platform",
        default_role="hris:super_admin", roles=["hris:super_admin"],
        allow_existing_user_password_reset=False, send_temp_password=False,
        fixed_password=password, fixed_password_temporary=False,
    )
    if not result.get("user_id") or result.get("status") != "created":
        raise SystemExit("Account creation was not confirmed. Inspect Keycloak before retrying.")
    print("Created the first HRIS superadmin. Sign in at " + settings.portal_base_url)
    print("No password email was sent: you chose the password privately here. Test reset email separately.")


if __name__ == "__main__":
    try:
        main()
    except httpx.HTTPError as exc:
        # Do not dump credential-bearing request/response bodies.
        code = getattr(getattr(exc, "response", None), "status_code", None)
        raise SystemExit(f"Keycloak administration request failed ({type(exc).__name__}, HTTP {code}). No success is implied.") from None
