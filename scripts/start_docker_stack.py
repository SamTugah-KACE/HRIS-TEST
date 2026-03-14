#!/usr/bin/env python3
"""
Cross-platform Docker stack launcher for HRIS.

Supports Windows/macOS/Linux and mirrors the behavior of start-docker-stack.ps1:
- optional Keycloak override compose file
- optional env-file loading
- compose config validation before startup
- compose wait gates + HTTP health checks
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import ProxyHandler, build_opener


def _print_stage(message: str) -> None:
    print(f"[DOCKER-STACK] {message}")


def _require_command(name: str) -> None:
    if shutil.which(name) is None:
        raise RuntimeError(f"Required command '{name}' was not found in PATH.")


def _run(command: list[str], cwd: Path) -> None:
    subprocess.run(command, cwd=str(cwd), check=True)


def _wait_http_ready(url: str, timeout_seconds: int = 240, interval_seconds: int = 3) -> bool:
    deadline = time.time() + timeout_seconds
    opener = build_opener(ProxyHandler({}))
    while time.time() < deadline:
        try:
            with opener.open(url, timeout=5) as resp:
                status = int(getattr(resp, "status", 0))
                if 200 <= status < 500:
                    return True
        except Exception:
            time.sleep(interval_seconds)
            continue
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Cross-platform Docker stack launcher.")
    parser.add_argument("--keycloak-mode", action="store_true", help="Enable docker-compose.keycloak.yml override.")
    parser.add_argument(
        "--no-rebuild",
        action="store_true",
        help="Skip --build during docker compose up.",
    )
    parser.add_argument(
        "--env-file",
        default=".env.docker.prod-like",
        help="Compose env file to load (default: .env.docker.prod-like).",
    )
    parser.add_argument(
        "--skip-env-file",
        action="store_true",
        help="Do not load env file via --env-file.",
    )
    parser.add_argument(
        "--wait-timeout-seconds",
        type=int,
        default=300,
        help="Compose wait timeout in seconds (default: 300).",
    )
    parser.add_argument(
        "--skip-compose-wait",
        action="store_true",
        help="Skip compose-level --wait gating.",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    _require_command("docker")

    compose_base_args: list[str] = ["docker", "compose"]
    if not args.skip_env_file:
        env_path = repo_root / args.env_file
        if env_path.exists():
            _print_stage(f"Using env file: {args.env_file}")
            compose_base_args += ["--env-file", str(env_path)]
        else:
            _print_stage(f"Env file '{args.env_file}' not found. Continuing with environment defaults.")

    compose_base_args += ["-f", "docker-compose.yml"]
    if args.keycloak_mode:
        compose_base_args += ["-f", "docker-compose.keycloak.yml"]

    _print_stage("Validating compose configuration...")
    _run(compose_base_args + ["config", "-q"], cwd=repo_root)

    up_args = compose_base_args + ["up"]
    if not args.no_rebuild:
        up_args.append("--build")
    up_args.append("-d")
    if not args.skip_compose_wait:
        up_args += ["--wait", "--wait-timeout", str(max(1, int(args.wait_timeout_seconds)))]

    _print_stage("Starting docker stack...")
    _run(up_args, cwd=repo_root)

    _print_stage("Waiting for Tenant Registry health...")
    if not _wait_http_ready("http://127.0.0.1:8001/health", timeout_seconds=240):
        raise RuntimeError("Tenant Registry did not become healthy in time.")
    _print_stage("Tenant Registry healthy.")

    _print_stage("Waiting for HRIS Core API health...")
    if not _wait_http_ready("http://127.0.0.1:8000/health", timeout_seconds=240):
        raise RuntimeError("HRIS Core API did not become healthy in time.")
    _print_stage("HRIS Core API healthy.")

    _print_stage("Waiting for Portal...")
    if not _wait_http_ready("http://127.0.0.1:3000", timeout_seconds=240):
        raise RuntimeError("Portal did not become reachable in time.")
    _print_stage("Portal reachable.")

    if args.keycloak_mode:
        _print_stage("Waiting for Keycloak readiness...")
        if not _wait_http_ready("http://127.0.0.1:8080/health/ready", timeout_seconds=300):
            raise RuntimeError("Keycloak did not become ready in time.")
        _print_stage("Keycloak ready.")

    _print_stage("Docker stack startup complete.")
    _run(compose_base_args + ["ps"], cwd=repo_root)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as exc:
        print(f"[DOCKER-STACK] Command failed with exit code {exc.returncode}.", file=sys.stderr)
        raise SystemExit(exc.returncode)
    except Exception as exc:
        print(f"[DOCKER-STACK] {exc}", file=sys.stderr)
        raise SystemExit(1)

