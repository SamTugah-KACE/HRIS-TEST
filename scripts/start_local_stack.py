import argparse
import http.client
import os
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse
from urllib.request import ProxyHandler, build_opener


def resolve_app_dir(repo_root: Path, legacy_name: str) -> Path:
    grouped_paths = {
        "portal": repo_root / "apps" / "frontend" / "portal",
        "hris-core-api": repo_root / "apps" / "backend" / "hris-core-api",
        "tenant-registry-service": repo_root / "apps" / "backend" / "tenant-registry-service",
    }
    apps_path = grouped_paths.get(legacy_name, repo_root / "apps" / legacy_name)
    legacy_path = repo_root / legacy_name
    if apps_path.exists():
        return apps_path
    return legacy_path


def is_port_available(host: str, port: int) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind((host, port))
        return True
    except OSError:
        return False
    finally:
        try:
            sock.close()
        except Exception:
            pass


def choose_registry_port(preferred_port: int, *, max_attempts: int = 30) -> int:
    for port in range(preferred_port, preferred_port + max_attempts):
        if is_port_available("127.0.0.1", port):
            return port
    return preferred_port


def wait_http(url: str, timeout_seconds: int = 180, interval_seconds: int = 2) -> bool:
    deadline = time.time() + timeout_seconds
    # Bypass environment proxies to avoid localhost health-check stalls.
    opener = build_opener(ProxyHandler({}))
    attempts = 0
    while time.time() < deadline:
        attempts += 1
        try:
            with opener.open(url, timeout=4) as resp:
                if 200 <= int(resp.status) < 500:
                    return True
        except Exception:
            time.sleep(interval_seconds)
            continue
    return False


def wait_tcp(host: str, port: int, timeout_seconds: int = 120, interval_seconds: int = 1) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2.0)
        try:
            sock.connect((host, port))
            return True
        except Exception:
            time.sleep(interval_seconds)
            continue
        finally:
            try:
                sock.close()
            except Exception:
                pass
    return False


def quick_http_health(url: str) -> bool:
    parsed = urlparse(url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    path = parsed.path or "/"
    conn = http.client.HTTPConnection(host, port, timeout=3)
    try:
        conn.request("GET", path)
        resp = conn.getresponse()
        _ = resp.read()
        return 200 <= int(resp.status) < 500
    except Exception:
        return False
    finally:
        try:
            conn.close()
        except Exception:
            pass


def stream_output(prefix: str, proc: subprocess.Popen) -> None:
    assert proc.stdout is not None
    for line in iter(proc.stdout.readline, ""):
        if not line:
            break
        print(f"[{prefix}] {line.rstrip()}")


def start_process(prefix: str, command: list[str], cwd: Path) -> subprocess.Popen:
    return _start_process_with_env(prefix=prefix, command=command, cwd=cwd, env_overrides=None)


def _start_process_with_env(
    *,
    prefix: str,
    command: list[str],
    cwd: Path,
    env_overrides: Optional[dict[str, str]],
) -> subprocess.Popen:
    env = os.environ.copy()
    if env_overrides:
        env.update(env_overrides)
    proc = subprocess.Popen(
        command,
        cwd=str(cwd),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    thread = threading.Thread(target=stream_output, args=(prefix, proc), daemon=True)
    thread.start()
    return proc


def wait_process_alive(stage_name: str, process: subprocess.Popen, seconds: int = 5) -> bool:
    deadline = time.time() + max(1, seconds)
    while time.time() < deadline:
        code = process.poll()
        if code is not None:
            print(f"[STACK] {stage_name} exited early (exit={code}).")
            return False
        time.sleep(0.5)
    return True


def wait_stage_ready(
    *,
    stage_name: str,
    process: subprocess.Popen,
    url: str,
    timeout_seconds: int,
    interval_seconds: int = 2,
) -> bool:
    parsed = urlparse(url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    tcp_grace_used = False

    started = time.time()
    while (time.time() - started) < timeout_seconds:
        code = process.poll()
        if code is not None:
            print(f"[STACK] {stage_name} exited before readiness check passed (exit={code}).")
            return False
        if wait_http(url, timeout_seconds=interval_seconds, interval_seconds=interval_seconds):
            return True
        # Fallback to avoid false loops when local HTTP probes are flaky.
        if wait_tcp(host, port, timeout_seconds=interval_seconds, interval_seconds=1):
            if quick_http_health(url):
                return True
            if not tcp_grace_used:
                tcp_grace_used = True
                print(
                    f"[STACK] {stage_name} port is open but /health probe is slow; proceeding with TCP readiness."
                )
                return True
        elapsed = int(time.time() - started)
        print(f"[STACK] Waiting for {stage_name} health at {url}... ({elapsed}s elapsed)")
    print(f"[STACK] {stage_name} readiness timed out after {timeout_seconds}s.")
    return False


def terminate_processes(procs: list[subprocess.Popen]) -> None:
    for proc in procs:
        if proc.poll() is None:
            try:
                proc.terminate()
            except Exception:
                pass
    for proc in procs:
        if proc.poll() is None:
            try:
                proc.wait(timeout=8)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Cross-platform local HRIS stack launcher.")
    parser.add_argument("--no-portal", action="store_true", help="Skip starting the portal service.")
    parser.add_argument("--registry-port", type=int, default=8001)
    parser.add_argument("--core-port", type=int, default=8000)
    parser.add_argument("--portal-port", type=int, default=5173)
    parser.add_argument("--gateway-port", type=int, default=8010)
    parser.add_argument(
        "--with-gateway",
        action="store_true",
        help="Start GraphQL gateway service (apps/backend/gateway).",
    )
    parser.add_argument("--timeout", type=int, default=240, help="Health wait timeout per stage (seconds).")
    parser.add_argument(
        "--auto-registry-port-fallback",
        action="store_true",
        help="Auto-select next free registry port if preferred port is busy.",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    registry_dir = resolve_app_dir(repo_root, "tenant-registry-service")
    core_dir = resolve_app_dir(repo_root, "hris-core-api")
    portal_dir = resolve_app_dir(repo_root, "portal")
    gateway_dir = repo_root / "apps" / "backend" / "gateway"

    for name, path in (
        ("tenant-registry-service", registry_dir),
        ("hris-core-api", core_dir),
        ("portal", portal_dir),
    ):
        if not path.exists():
            print(f"[STACK] Required app directory is missing for '{name}': {path}")
            return 1
    if args.with_gateway and not gateway_dir.exists():
        print(f"[STACK] Required app directory is missing for 'gateway': {gateway_dir}")
        return 1

    python_exe = sys.executable
    npm_cmd = "npm.cmd" if os.name == "nt" else "npm"
    registry_port = args.registry_port
    if args.auto_registry_port_fallback:
        selected = choose_registry_port(args.registry_port)
        if selected != args.registry_port:
            print(
                f"[STACK] Preferred Tenant Registry port {args.registry_port} is busy. "
                f"Using fallback port {selected}."
            )
        registry_port = selected

    procs: list[subprocess.Popen] = []

    # The Core API performs idempotent first-install inventory reconciliation
    # during startup, so its canonical Tenant Registry dependency must be ready
    # before Core begins. Docker already enforces the same ordering by healthcheck.
    print("[STACK] Stage 1/4: starting Tenant Registry...")
    registry = start_process(
        "REGISTRY",
        [python_exe, "-m", "uvicorn", "app.main:app", "--reload", "--port", str(registry_port)],
        registry_dir,
    )
    procs.append(registry)
    if not wait_stage_ready(
        stage_name="Tenant Registry",
        process=registry,
        url=f"http://127.0.0.1:{registry_port}/health",
        timeout_seconds=args.timeout,
    ):
        terminate_processes(procs)
        return 1
    print("[STACK] Tenant Registry healthy.")

    print("[STACK] Stage 2/4: starting HRIS Core API...")
    core = _start_process_with_env(
        prefix="CORE",
        command=[python_exe, "-m", "uvicorn", "app.main:app", "--reload", "--port", str(args.core_port)],
        cwd=core_dir,
        env_overrides={
            "TENANT_REGISTRY_BASE_URL": f"http://127.0.0.1:{registry_port}",
        },
    )
    procs.append(core)
    if not wait_process_alive("HRIS Core API", core, seconds=5):
        terminate_processes(procs)
        return 1

    if not wait_stage_ready(
        stage_name="HRIS Core API",
        process=core,
        url=f"http://127.0.0.1:{args.core_port}/health",
        timeout_seconds=args.timeout,
    ):
        terminate_processes(procs)
        return 1
    print("[STACK] HRIS Core API healthy.")

    if not args.no_portal:
        print("[STACK] Stage 3/4: starting Portal...")
        portal = start_process("PORTAL", [npm_cmd, "run", "dev"], portal_dir)
        procs.append(portal)
        if not wait_stage_ready(
            stage_name="Portal",
            process=portal,
            url=f"http://127.0.0.1:{args.portal_port}",
            timeout_seconds=args.timeout,
        ):
            terminate_processes(procs)
            return 1
        print("[STACK] Portal reachable.")
    else:
        print("[STACK] Stage 3/4: skipped Portal (--no-portal).")

    if args.with_gateway:
        print("[STACK] Stage 4/4: starting GraphQL Gateway...")
        gateway = _start_process_with_env(
            prefix="GATEWAY",
            command=[python_exe, "-m", "uvicorn", "app.main:app", "--reload", "--port", str(args.gateway_port)],
            cwd=gateway_dir,
            env_overrides={
                "CORE_API_BASE_URL": f"http://127.0.0.1:{args.core_port}",
            },
        )
        procs.append(gateway)
        if not wait_stage_ready(
            stage_name="GraphQL Gateway",
            process=gateway,
            url=f"http://127.0.0.1:{args.gateway_port}/health",
            timeout_seconds=args.timeout,
        ):
            terminate_processes(procs)
            return 1
        print("[STACK] GraphQL Gateway healthy.")

    print("[STACK] Startup complete. Press Ctrl+C to stop all services.")
    try:
        while True:
            time.sleep(1)
            for proc in procs:
                code = proc.poll()
                if code is not None and code != 0:
                    print(f"[STACK] Process exited with code {code}. Stopping all services.")
                    terminate_processes(procs)
                    return code
    except KeyboardInterrupt:
        print("\n[STACK] Shutdown requested. Stopping services...")
        terminate_processes(procs)
        return 0


if __name__ == "__main__":
    if os.name != "nt":
        signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    raise SystemExit(main())
