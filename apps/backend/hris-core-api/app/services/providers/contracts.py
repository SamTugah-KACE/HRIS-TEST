from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol


@dataclass(frozen=True)
class DeliveryResult:
    accepted: bool
    provider: str
    reference: Optional[str] = None
    code: str = "UNKNOWN"
    retryable: bool = False


class NotificationProvider(Protocol):
    name: str

    def send_message(self, *, destination: str, message: str, purpose: str) -> DeliveryResult: ...
    def health_check(self) -> bool: ...


class VerificationProvider(Protocol):
    name: str

    def start_verification(self, *, destination: str, length: int, ttl_seconds: int) -> DeliveryResult: ...
    def check_verification(self, *, destination: str, code: str, reference: Optional[str]) -> DeliveryResult: ...
    def cancel_verification(self, *, reference: Optional[str]) -> None: ...
    def health_check(self) -> bool: ...
