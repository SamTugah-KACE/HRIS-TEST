from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import hashlib
import ipaddress
import threading
import time
from typing import Deque, Dict, Optional, Tuple

from fastapi import HTTPException, Request, status

from app.core.settings import get_settings


def _hash_text(value: str) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()[:16]


def _normalized_client_ip(request: Request) -> str:
    forwarded_for = str(request.headers.get("x-forwarded-for") or "").strip()
    if forwarded_for:
        ip = forwarded_for.split(",")[0].strip()
    else:
        ip = str((request.client.host if request.client else "") or "").strip()
    if not ip:
        return "unknown"
    try:
        parsed = ipaddress.ip_address(ip)
    except ValueError:
        return ip
    if isinstance(parsed, ipaddress.IPv4Address):
        network = ipaddress.ip_network(f"{parsed}/24", strict=False)
    else:
        network = ipaddress.ip_network(f"{parsed}/64", strict=False)
    return str(network.network_address)


def _principal_hint(request: Request) -> str:
    access_cookie = str(request.cookies.get("hris_access_token") or "").strip()
    refresh_cookie = str(request.cookies.get("hris_refresh_token") or "").strip()
    auth_header = str(request.headers.get("authorization") or "").strip()
    if access_cookie:
        return f"acc:{_hash_text(access_cookie)}"
    if refresh_cookie:
        return f"ref:{_hash_text(refresh_cookie)}"
    if auth_header:
        return f"auth:{_hash_text(auth_header)}"
    return ""


def build_rate_limit_key(request: Request, *, scope: str, user_key: Optional[str] = None) -> str:
    ip_scope = _normalized_client_ip(request)
    ua = str(request.headers.get("user-agent") or "").strip().lower()
    lang = str(request.headers.get("accept-language") or "").strip().lower()
    principal = str(user_key or "").strip() or _principal_hint(request)
    if principal:
        return f"{scope}|principal:{principal}"
    return f"{scope}|ip:{ip_scope}|ua:{_hash_text(ua)}|lang:{_hash_text(lang)}"


@dataclass
class _Bucket:
    events: Deque[float]
    touched_at: float


class SlidingWindowRateLimiter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._buckets: Dict[str, _Bucket] = {}

    def allow(self, *, key: str, limit: int, window_seconds: int) -> Tuple[bool, int]:
        now = time.time()
        min_ts = now - max(1, int(window_seconds))
        with self._lock:
            stale_cutoff = now - max(5, int(window_seconds) * 4)
            for bucket_key in list(self._buckets.keys()):
                bucket = self._buckets.get(bucket_key)
                if not bucket:
                    continue
                if bucket.touched_at < stale_cutoff:
                    self._buckets.pop(bucket_key, None)

            bucket = self._buckets.get(key)
            if not bucket:
                bucket = _Bucket(events=deque(), touched_at=now)
                self._buckets[key] = bucket

            while bucket.events and bucket.events[0] <= min_ts:
                bucket.events.popleft()
            bucket.touched_at = now
            if len(bucket.events) >= max(1, int(limit)):
                oldest = bucket.events[0] if bucket.events else now
                retry_after = max(1, int(window_seconds - (now - oldest)))
                return False, retry_after
            bucket.events.append(now)
            return True, 0


_LIMITER = SlidingWindowRateLimiter()


def enforce_rate_limit(
    request: Request,
    *,
    scope: str,
    limit: int,
    window_seconds: Optional[int] = None,
    user_key: Optional[str] = None,
) -> None:
    settings = get_settings()
    if not settings.rate_limit_enabled:
        return
    effective_window = int(window_seconds or settings.rate_limit_window_seconds)
    key = build_rate_limit_key(request, scope=scope, user_key=user_key)
    allowed, retry_after = _LIMITER.allow(key=key, limit=limit, window_seconds=effective_window)
    if allowed:
        return
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail={
            "code": "RATE_LIMITED",
            "message": "Too many requests for this operation. Please retry shortly.",
            "scope": scope,
            "retry_after_seconds": retry_after,
        },
    )

