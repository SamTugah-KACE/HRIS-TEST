import json
import hmac
import hashlib
import base64
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

import httpx
from fastapi import HTTPException, status
from cryptography.fernet import Fernet, InvalidToken

from app.models.integration_contract import HrisOutboundMetadataHeaders

_HRIS_ROLE_PRIORITY = [
    "hris:super_admin",
    "hris:tenant_admin",
    "hris:hr_manager",
    "hris:line_manager",
    "hris:employee",
]


def _decode_jwt_payload_unverified(token: Optional[str]) -> Dict[str, Any]:
    raw = (token or "").strip()
    if not raw:
        return {}
    parts = raw.split(".")
    if len(parts) < 2:
        return {}
    payload_b64 = parts[1]
    padded = payload_b64 + "=" * (-len(payload_b64) % 4)
    try:
        decoded = base64.urlsafe_b64decode(padded.encode("utf-8")).decode("utf-8")
        parsed = json.loads(decoded)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _resolve_effective_hris_role(claims: Dict[str, Any]) -> str:
    roles: List[str] = []
    raw_roles = claims.get("roles")
    if isinstance(raw_roles, list):
        roles.extend([str(role) for role in raw_roles])
    realm_access = claims.get("realm_access")
    if isinstance(realm_access, dict) and isinstance(realm_access.get("roles"), list):
        roles.extend([str(role) for role in realm_access["roles"]])
    for role in _HRIS_ROLE_PRIORITY:
        if role in roles:
            return role
    return "hris:system"


def resolve_user_context_from_token(token: Optional[str]) -> Tuple[str, str]:
    claims = _decode_jwt_payload_unverified(token)
    sub = (
        str(
            claims.get("sub")
            or claims.get("preferred_username")
            or claims.get("email")
            or "hris-core-service"
        )
    ).strip()
    role = _resolve_effective_hris_role(claims)
    return sub or "hris-core-service", role or "hris:system"


def build_auth_headers(user_token: Optional[str], service_token: Optional[str]) -> Dict[str, str]:
    token = user_token or service_token
    if not token:
        return {}
    return {"Authorization": f"Bearer {token}"}


def build_hris_metadata_headers(
    *,
    module_name: str,
    user_token: Optional[str] = None,
    tenant_id: Optional[str] = None,
    tenant_slug: Optional[str] = None,
    tenant_code: Optional[str] = None,
    employee_id: Optional[str] = None,
) -> Dict[str, str]:
    user_sub, role = resolve_user_context_from_token(user_token)
    model = HrisOutboundMetadataHeaders(
        request_id=str(uuid.uuid4()),
        client_app="hris-core",
        client_version="1.0.0",
        integration_module=module_name,
        user_sub=user_sub,
        role=role,
        tenant_id=tenant_id,
        tenant_slug=tenant_slug,
        tenant_code=tenant_code,
        employee_id=employee_id,
    )
    return model.as_http_headers()


def unwrap_payload(payload: Any) -> Any:
    if isinstance(payload, dict):
        # Common wrappers used by existing modules.
        if "data" in payload and isinstance(payload["data"], (dict, list)):
            return payload["data"]
        if "result" in payload and isinstance(payload["result"], (dict, list)):
            return payload["result"]
    return payload


def _decode_encrypted_envelope(
    payload: Any,
    *,
    module_name: str,
    signing_secret: Optional[str],
) -> Any:
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"{module_name} encrypted envelope: expected object payload",
        )
    ciphertext = payload.get("ciphertext")
    signature = payload.get("signature")
    if not isinstance(ciphertext, str) or not ciphertext:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"{module_name} encrypted envelope: missing ciphertext",
        )
    if signing_secret:
        if not isinstance(signature, str) or not signature:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"{module_name} encrypted envelope: missing signature",
            )
        expected_signature = hmac.new(
            signing_secret.encode("utf-8"),
            ciphertext.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected_signature, signature):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"{module_name} encrypted envelope: signature validation failed",
            )
    try:
        decoded_bytes = base64.b64decode(ciphertext.encode("utf-8"), validate=True)
        decoded_text = decoded_bytes.decode("utf-8")
        return json.loads(decoded_text)
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"{module_name} encrypted envelope: ciphertext decode failed",
        ) from exc


def _derive_staff_records_fernet_key(encryption_secret: str) -> bytes:
    salt = b"response_encryption_salt_v1"
    key_material = hashlib.sha256(encryption_secret.encode("utf-8") + salt).digest()
    return base64.urlsafe_b64encode(key_material)


def _derive_session_token_fernet_key(session_token: str) -> bytes:
    key_material = hashlib.sha256(session_token.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(key_material)


def _decode_staff_records_response_wrapper(
    payload: Any,
    *,
    module_name: str,
    encryption_secret: Optional[str],
    session_token: Optional[str] = None,
) -> Any:
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"{module_name} response wrapper: expected object payload",
        )

    encrypted = bool(payload.get("encrypted"))
    wrapped_data = payload.get("data")
    if wrapped_data is None:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"{module_name} response wrapper: missing data field",
        )

    if not encrypted:
        return wrapped_data

    if not isinstance(wrapped_data, str):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"{module_name} response wrapper: encrypted data must be string",
        )
    wrapper_method = str(payload.get("method") or "").strip().lower()

    checksum = payload.get("checksum")
    encrypted_bytes = wrapped_data.encode("utf-8")
    if isinstance(checksum, str) and checksum:
        expected_checksum = hashlib.sha256(encrypted_bytes).hexdigest()[:16]
        if checksum != expected_checksum:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"{module_name} response wrapper: checksum validation failed",
            )

    # Some deployed modules omit `method` but still encrypt with session-token key.
    candidate_fernets: List[Fernet] = []
    if wrapper_method == "session_token":
        if not (session_token or "").strip():
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"{module_name} response wrapper: session token is not configured",
            )
        candidate_fernets.append(Fernet(_derive_session_token_fernet_key(session_token.strip())))
    else:
        if (session_token or "").strip():
            candidate_fernets.append(Fernet(_derive_session_token_fernet_key(session_token.strip())))
        if (encryption_secret or "").strip():
            candidate_fernets.append(Fernet(_derive_staff_records_fernet_key(encryption_secret.strip())))
        if not candidate_fernets:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"{module_name} response wrapper: neither session token nor encryption secret is configured",
            )

    last_exc: Optional[Exception] = None
    for fernet in candidate_fernets:
        try:
            decrypted_bytes = fernet.decrypt(encrypted_bytes)
            return json.loads(decrypted_bytes.decode("utf-8"))
        except (InvalidToken, ValueError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            last_exc = exc
            continue
    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=f"{module_name} response wrapper: decryption failed",
    ) from last_exc


def decode_module_payload(
    payload: Any,
    *,
    module_name: str,
    security_mode: str = "plain",
    signing_secret: Optional[str] = None,
    encryption_secret: Optional[str] = None,
    session_token: Optional[str] = None,
) -> Any:
    normalized_mode = security_mode.lower().strip()
    if normalized_mode == "auto":
        if isinstance(payload, dict) and "ciphertext" in payload:
            return unwrap_payload(
                _decode_encrypted_envelope(
                    payload,
                    module_name=module_name,
                    signing_secret=signing_secret,
                )
            )
        if isinstance(payload, dict) and payload.get("encrypted") is True and "data" in payload:
            return unwrap_payload(
                _decode_staff_records_response_wrapper(
                    payload,
                    module_name=module_name,
                    encryption_secret=encryption_secret,
                    session_token=session_token,
                )
            )
        if isinstance(payload, dict) and payload.get("encrypted") is False and "data" in payload:
            return unwrap_payload(payload.get("data"))
        return unwrap_payload(payload)
    if normalized_mode == "plain":
        if isinstance(payload, dict) and payload.get("encrypted") is True and "data" in payload:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"{module_name} payload is encrypted but SRMS_PAYLOAD_SECURITY_MODE=plain",
            )
        return unwrap_payload(payload)
    if normalized_mode == "encrypted_envelope":
        return unwrap_payload(
            _decode_encrypted_envelope(
                payload,
                module_name=module_name,
                signing_secret=signing_secret,
            )
        )
    if normalized_mode == "staff_records_response":
        return unwrap_payload(
            _decode_staff_records_response_wrapper(
                payload,
                module_name=module_name,
                encryption_secret=encryption_secret,
                session_token=session_token,
            )
        )
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=f"{module_name} payload security mode '{security_mode}' is not supported",
    )


def ensure_dict(value: Any, *, context: str) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"{context}: expected object payload, got {type(value).__name__}",
        )
    return value


def ensure_list(value: Any, *, context: str) -> List[Any]:
    if not isinstance(value, list):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"{context}: expected list payload, got {type(value).__name__}",
        )
    return value


def to_int(value: Any, *, default: int = 0, context: str = "field") -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"{context}: expected integer-compatible value, got '{value}'",
        ) from exc


def to_float(value: Any, *, default: float = 0.0, context: str = "field") -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"{context}: expected float-compatible value, got '{value}'",
        ) from exc


def to_str(value: Any, *, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def extract_json_from_network_dump(file_path: str) -> Any:
    path = Path(file_path)
    if not path.exists():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Fixture file not found: {file_path}",
        )

    text = path.read_text(encoding="utf-8", errors="ignore")
    marker = "****network response"
    marker_index = text.find(marker)
    if marker_index != -1:
        text = text[marker_index + len(marker):]

    # Find first JSON object/array in remaining payload.
    start_obj = text.find("{")
    start_arr = text.find("[")
    candidates = [i for i in (start_obj, start_arr) if i != -1]
    if not candidates:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Fixture parse error: no JSON content found",
        )
    start = min(candidates)
    candidate_text = text[start:].strip()

    try:
        decoder = json.JSONDecoder()
        data, _ = decoder.raw_decode(candidate_text)
        return data
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Fixture parse error: invalid JSON ({exc})",
        ) from exc


def get_json_from_candidate_paths(
    *,
    client: httpx.Client,
    base_url: str,
    paths: Iterable[str],
    headers: Dict[str, str],
    params: Optional[Dict[str, Any]] = None,
    module_name: str,
    payload_security_mode: str = "plain",
    payload_signing_secret: Optional[str] = None,
    payload_encryption_secret: Optional[str] = None,
    payload_session_token: Optional[str] = None,
    prepare_headers: Optional[Callable[[str, Dict[str, str]], Dict[str, str]]] = None,
) -> Tuple[Any, str]:
    last_response: Optional[httpx.Response] = None
    last_error: Optional[Exception] = None
    last_redirect_location: str = ""
    last_auth_status: int = 0
    last_auth_path: str = ""
    path_statuses: Dict[str, int] = {}

    for path in paths:
        url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
        request_headers = dict(headers)
        if prepare_headers is not None:
            request_headers = prepare_headers(path, request_headers)
        try:
            response = client.get(url, headers=request_headers, params=params)
            last_response = response
            path_statuses[path] = int(response.status_code)
        except httpx.HTTPError as exc:
            last_error = exc
            continue

        if response.status_code in (404, 405):
            # Candidate route absent, try the next mapping.
            continue

        if response.status_code in (301, 302, 307, 308):
            last_redirect_location = str(response.headers.get("location") or "").strip()
            # Try other candidates first; caller can inspect the final error detail.
            continue

        if response.status_code in (401, 403):
            last_auth_status = response.status_code
            last_auth_path = path
            # Candidate route may enforce a different auth contract; keep trying.
            continue

        try:
            response.raise_for_status()
            raw_payload = response.json()
            decoded_payload = decode_module_payload(
                raw_payload,
                module_name=module_name,
                security_mode=payload_security_mode,
                signing_secret=payload_signing_secret,
                encryption_secret=payload_encryption_secret,
                session_token=payload_session_token,
            )
            return decoded_payload, path
        except ValueError as exc:
            last_error = exc
            continue
        except httpx.HTTPError as exc:
            last_error = exc
            continue

    if last_response is not None:
        status_summary = ", ".join([f"{k}:{v}" for k, v in path_statuses.items()]) if path_statuses else ""
        if last_auth_status in (401, 403):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=(
                    f"{module_name} authentication failed while calling "
                    f"'{last_auth_path}' (status {last_auth_status})"
                    + (f"; attempted={status_summary}" if status_summary else "")
                ),
            )
        redirect_hint = (
            f", redirect_location={last_redirect_location}" if last_redirect_location else ""
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                f"{module_name} request failed for all mapped endpoints. "
                f"Last status: {last_response.status_code}{redirect_hint}"
                + (f"; attempted={status_summary}" if status_summary else "")
            ),
        )

    if last_error is not None:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"{module_name} request failed: {last_error}",
        )

    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=f"{module_name} request failed: no endpoint candidates available",
    )
