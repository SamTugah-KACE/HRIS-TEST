from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict

import httpx

from app.core.settings import get_settings


_lock = threading.Lock()
_memory: Dict[str, Any] = {"fetched_at": 0.0, "jwks": None}


class JwksUnavailable(RuntimeError):
    pass


def _valid(payload: Any) -> bool:
    return (
        isinstance(payload, dict)
        and isinstance(payload.get("keys"), list)
        and bool(payload.get("keys"))
    )


def _load_disk() -> Dict[str, Any] | None:
    path = Path(get_settings().auth_jwks_last_good_path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    if not isinstance(payload, dict) or not _valid(payload.get("jwks")):
        return None
    return payload


def _store_disk(jwks: Dict[str, Any], fetched_at: float) -> None:
    path = Path(get_settings().auth_jwks_last_good_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps({"fetched_at": fetched_at, "jwks": jwks}, separators=(",", ":")),
        encoding="utf-8",
    )
    os.replace(temporary, path)


def get_jwks(*, force_refresh: bool = False) -> Dict[str, Any]:
    settings = get_settings()
    now = time.time()
    ttl = int(settings.auth_jwks_cache_ttl_seconds)
    max_stale = int(settings.auth_jwks_cache_max_stale_seconds)

    with _lock:
        if (
            not force_refresh
            and _valid(_memory.get("jwks"))
            and now - float(_memory.get("fetched_at") or 0) <= ttl
        ):
            return _memory["jwks"]

        fetch_error: Exception | None = None
        try:
            with httpx.Client(timeout=5.0, trust_env=False) as client:
                response = client.get(str(settings.keycloak_jwks_url))
                response.raise_for_status()
                jwks = response.json()
            if not _valid(jwks):
                raise JwksUnavailable("Identity provider returned no signing keys")
            _memory.update({"fetched_at": now, "jwks": jwks})
            try:
                _store_disk(jwks, now)
            except OSError:
                # Disk continuity is defense in depth; a valid in-memory key set
                # remains usable and no token material is stored here.
                pass
            return jwks
        except (httpx.HTTPError, ValueError, JwksUnavailable) as exc:
            fetch_error = exc

        candidates = []
        if _valid(_memory.get("jwks")):
            candidates.append(dict(_memory))
        disk = _load_disk()
        if disk:
            candidates.append(disk)
        candidates.sort(key=lambda row: float(row.get("fetched_at") or 0), reverse=True)
        if candidates:
            freshest = candidates[0]
            age = now - float(freshest.get("fetched_at") or 0)
            if age <= max_stale:
                _memory.update(freshest)
                return freshest["jwks"]
        raise JwksUnavailable("No current or permitted last-known-good signing keys are available") from fetch_error


def clear_jwks_cache() -> None:
    with _lock:
        _memory.update({"fetched_at": 0.0, "jwks": None})
