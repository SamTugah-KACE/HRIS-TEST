import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.auth import AuthenticatedUser
from app.services.integration_sync import build_sync_snapshot


def _actor_for_tenant(tenant_id: str) -> AuthenticatedUser:
    return AuthenticatedUser(
        sub="sync.reporter",
        username="sync.reporter",
        email="sync.reporter@hris.local",
        tenant_id=tenant_id,
        roles=["hris:tenant_admin"],
        effective_role="hris:tenant_admin",
        employee_id=None,
        raw_token=None,
        token_claims={"tenant_id": tenant_id},
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate tenant integration synchronization report.")
    parser.add_argument("--tenant-id", required=True, help="Global tenant identifier")
    parser.add_argument(
        "--skip-live-probes",
        action="store_true",
        help="Skip upstream module probe calls and return mapping-only snapshot.",
    )
    args = parser.parse_args()

    actor = _actor_for_tenant(args.tenant_id)
    snapshot = build_sync_snapshot(
        tenant_id=args.tenant_id,
        actor=actor,
        include_live_probes=not args.skip_live_probes,
    )
    print(json.dumps(snapshot, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
