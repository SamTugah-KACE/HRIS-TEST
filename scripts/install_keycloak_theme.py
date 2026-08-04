"""Install the repository's HRIS email theme into a local Keycloak distribution."""
import argparse
import shutil
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keycloak-home", required=True, help="Keycloak installation directory")
    args = parser.parse_args()
    source = Path(__file__).resolve().parents[1] / "identity" / "themes" / "hris-platform"
    home = Path(args.keycloak_home).resolve()
    if not (home / "bin" / "kc.bat").is_file() and not (home / "bin" / "kc.sh").is_file():
        parser.error(f"Not a Keycloak installation: {home}")
    destination = home / "themes" / "hris-platform"
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, destination, dirs_exist_ok=True)
    print(f"Installed HRIS email theme at {destination}")
    print("Restart Keycloak, set KEYCLOAK_EMAIL_THEME=hris-platform, and restart HRIS Core API.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
