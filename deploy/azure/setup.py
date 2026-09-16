"""Create a NEW Azure pilot configuration; never overwrite deployment secrets.

Run interactively on the Ubuntu VM. Uses only the Python standard library.
Does not contact Azure, GitHub, Google, Keycloak or native modules.
"""
import base64
import copy
import getpass
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import sys

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_HOST = "gi-kace-hris-test.eastus.cloudapp.azure.com"


def validate_inputs(host, email, admin_cidr, core_password, keycloak_password):
    if len(host) > 253 or not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", host):
        raise ValueError("Enter a DNS hostname only, without https://, spaces or paths")
    if "." not in host or any(not label or len(label) > 63 or label.startswith("-") or label.endswith("-") for label in host.split(".")):
        raise ValueError("Invalid DNS hostname")
    if not re.fullmatch(r"[A-Za-z0-9._+%-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", email):
        raise ValueError("Enter the full Google sending mailbox address")
    network = ipaddress.ip_network(admin_cidr, strict=False)
    if network.prefixlen != network.max_prefixlen:
        raise ValueError("Use your administrator's single public IP (/32 IPv4 or /128 IPv6)")
    if not network.network_address.is_global:
        raise ValueError("Administration allowlist requires your public client IP, not the VM/private IP")
    for password in (core_password, keycloak_password):
        if not re.fullmatch(r"[A-Za-z0-9]{16}", password):
            raise ValueError("Use a 16-character Google app password, not the account password")
    return str(network)


def make_config(host, email, admin_cidr, core_password, keycloak_password):
    admin_cidr = validate_inputs(host, email, admin_cidr, core_password, keycloak_password)
    return {
        "AZURE_HOSTNAME": host,
        "AZURE_ADMIN_CIDR": admin_cidr,
        "ACME_EMAIL": email,
        "SMTP_USERNAME": email,
        "CORE_SMTP_PASSWORD": core_password,
        "KEYCLOAK_SMTP_PASSWORD": keycloak_password,
        "POSTGRES_PASSWORD": secrets.token_hex(32),
        "REGISTRY_PASSWORD": secrets.token_hex(32),
        "AUTH_STATE_SECRET": secrets.token_urlsafe(48),
        "AUTH_SESSION_ENCRYPTION_KEY": base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
        "PROVIDER_SECRET_ENCRYPTION_KEY": base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
        "HRIS_KC_PORTAL_SECRET": secrets.token_urlsafe(48),
        "HRIS_KC_SERVICE_SECRET": secrets.token_urlsafe(48),
        "KEYCLOAK_BOOTSTRAP_PASSWORD": secrets.token_urlsafe(32),
    }


def make_realm(source, host, email):
    realm = copy.deepcopy(source)
    origin = "https://" + host
    realm.update({
        "sslRequired": "external", "registrationAllowed": False,
        "resetPasswordAllowed": True, "verifyEmail": True,
        "bruteForceProtected": True, "loginTheme": "hris-platform",
        "emailTheme": "hris-platform",
        "smtpServer": {
            "host": "smtp.gmail.com", "port": "587", "from": email,
            "fromDisplayName": "GI-KACE HRIS", "auth": "true", "user": email,
            "password": "${HRIS_KC_SMTP_PASSWORD}", "starttls": "true", "ssl": "false",
        },
    })
    realm.pop("users", None)  # Never import exported human users or development passwords.
    realm.get("attributes", {}).pop("frontendUrl", None)
    portal = next(c for c in realm["clients"] if c["clientId"] == "hris-portal")
    portal.update({
        "publicClient": False, "secret": "${HRIS_KC_PORTAL_SECRET}",
        "directAccessGrantsEnabled": False, "serviceAccountsEnabled": False,
        "redirectUris": [origin + "/api/auth/sso/callback"], "webOrigins": [origin],
        "rootUrl": origin, "baseUrl": origin,
    })
    portal.setdefault("attributes", {}).update({
        "pkce.code.challenge.method": "S256",
        "post.logout.redirect.uris": origin + "/",
    })
    realm["clients"] = [c for c in realm["clients"] if c["clientId"] != "hris-core-admin"]
    realm["clients"].append({
        "clientId": "hris-core-admin", "name": "HRIS account provisioning service",
        "protocol": "openid-connect", "enabled": True, "publicClient": False,
        "secret": "${HRIS_KC_SERVICE_SECRET}", "serviceAccountsEnabled": True,
        "standardFlowEnabled": False, "directAccessGrantsEnabled": False,
    })
    # A machine identity, not a second human HRIS superadmin. Realm-local user
    # management only: no master-realm or realm-configuration administration.
    realm["users"] = [{
        "username": "service-account-hris-core-admin", "enabled": True,
        "serviceAccountClientId": "hris-core-admin",
        "clientRoles": {"realm-management": ["manage-users", "view-users", "query-users", "view-realm"]},
    }]
    return realm


def write_configuration(root, config, source):
    env_path, generated = root / ".env.azure.local", root / ".azure"
    # Treat either existing output as a stop condition; changing imported realm
    # files later does NOT update the realm already stored in PostgreSQL.
    if env_path.exists() or generated.exists():
        raise FileExistsError("Azure configuration already exists. Edit it deliberately; do not regenerate secrets.")
    generated.mkdir(mode=0o755)
    realm = make_realm(source, config["AZURE_HOSTNAME"], config["SMTP_USERNAME"])
    realm_path = generated / "realm.json"
    with realm_path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(realm, stream, indent=2)
        stream.write("\n")
    # Contains placeholders, not actual keys; must be readable by Keycloak UID1000.
    realm_path.chmod(0o644)
    fd = os.open(str(env_path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
        stream.write("# Private Azure pilot secrets. Never commit, share, or regenerate against existing volumes.\n")
        for name, value in config.items():
            stream.write(f"{name}='{value}'\n")
    return env_path


def main():
    if not sys.stdin.isatty():
        raise SystemExit("Run interactively in your VM SSH terminal; password input must not be echoed.")
    if (ROOT / ".env.azure.local").exists() or (ROOT / ".azure").exists():
        raise SystemExit("Configuration already exists; refusing to overwrite it.")
    print("NEW Azure pilot only. This does not migrate existing Render identities/data.")
    host = input(f"Azure hostname [{DEFAULT_HOST}]: ").strip().lower() or DEFAULT_HOST
    email = input("Google sending mailbox (full address): ").strip()
    client_ip = os.environ.get("SSH_CONNECTION", "").split(" ")[0]
    admin_cidr = input(f"Your administrator public IP [{client_ip}]: ").strip() or client_ip
    core_password = getpass.getpass("Google app password for HRIS Core (hidden): ").replace(" ", "")
    keycloak_password = getpass.getpass("Google app password for Keycloak (hidden): ").replace(" ", "")
    try:
        config = make_config(host, email, admin_cidr, core_password, keycloak_password)
        source = json.loads((ROOT / "identity/realm-export.json").read_text(encoding="utf-8"))
        path = write_configuration(ROOT, config, source)
    except (ValueError, FileExistsError) as exc:
        raise SystemExit(str(exc)) from None
    print(f"Created {path.name} (private) and .azure/realm.json (secret placeholders).")
    print("Infrastructure secrets were generated without printing them. No services were started.")


if __name__ == "__main__":
    main()
