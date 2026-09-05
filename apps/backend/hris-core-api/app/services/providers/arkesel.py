from __future__ import annotations

import re
import time
from typing import Any, Dict, Optional

import httpx

from app.core.settings import get_settings
from app.services.providers.contracts import DeliveryResult


_E164 = re.compile(r"^\+[1-9][0-9]{7,14}$")


def normalize_phone(value: str, default_country_code: str = "233") -> str:
    digits = re.sub(r"[^0-9+]", "", str(value or "").strip())
    if digits.startswith("00"):
        digits = "+" + digits[2:]
    elif digits.startswith("0"):
        digits = "+" + default_country_code + digits[1:]
    elif not digits.startswith("+"):
        digits = "+" + digits
    if not _E164.fullmatch(digits):
        raise ValueError("Registered phone number is not valid E.164")
    return digits


class ArkeselVerificationProvider:
    name = "arkesel"

    def __init__(self, *, api_key: Optional[str] = None, sender_id: Optional[str] = None):
        settings = get_settings()
        self.api_key = str(api_key or settings.arkesel_api_key or "").strip()
        self.sender_id = str(sender_id or settings.arkesel_sender_id or "HRIS").strip()
        self.base_url = str(settings.arkesel_api_base_url).rstrip("/")
        self.timeout = max(2, int(settings.arkesel_timeout_seconds))
        if len(self.sender_id) > 11:
            raise ValueError("Arkesel sender ID must not exceed 11 characters")

    def _post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not self.api_key:
            raise RuntimeError("Arkesel provider is not configured")
        with httpx.Client(timeout=self.timeout, trust_env=False) as client:
            response = client.post(
                f"{self.base_url}{path}",
                headers={"api-key": self.api_key, "Content-Type": "application/json"},
                json=payload,
            )
            response.raise_for_status()
            body = response.json()
        return body if isinstance(body, dict) else {}

    def start_verification(self, *, destination: str, length: int, ttl_seconds: int) -> DeliveryResult:
        phone = normalize_phone(destination)
        payload = {
            "expiry": max(1, min(10, (int(ttl_seconds) + 59) // 60)),
            "length": max(6, min(15, int(length))),
            "medium": "sms",
            "message": "Your HRIS recovery code is %otp_code%. Do not share this code.",
            "number": phone.lstrip("+"),
            "sender_id": self.sender_id,
            "type": "numeric",
        }
        started = time.perf_counter()
        try:
            body = self._post("/api/otp/generate", payload)
        except (httpx.HTTPError, RuntimeError, ValueError):
            return DeliveryResult(False, self.name, code="PROVIDER_UNAVAILABLE", retryable=True)
        accepted = str(body.get("code") or "") == "1000"
        reference = str(body.get("ussd_code") or "").strip() or None
        _ = time.perf_counter() - started
        return DeliveryResult(accepted, self.name, reference, "ACCEPTED" if accepted else "REJECTED", not accepted)

    def check_verification(self, *, destination: str, code: str, reference: Optional[str]) -> DeliveryResult:
        phone = normalize_phone(destination)
        try:
            body = self._post(
                "/api/otp/verify",
                {"number": phone.lstrip("+"), "code": str(code).strip()},
            )
        except (httpx.HTTPError, RuntimeError, ValueError):
            return DeliveryResult(False, self.name, reference, "PROVIDER_UNAVAILABLE", True)
        accepted = str(body.get("code") or "") == "1100"
        return DeliveryResult(accepted, self.name, reference, "VERIFIED" if accepted else "INVALID", False)

    def cancel_verification(self, *, reference: Optional[str]) -> None:
        return None

    def health_check(self) -> bool:
        return bool(self.api_key and self.base_url.startswith("https://"))
