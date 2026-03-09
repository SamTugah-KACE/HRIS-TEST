from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.core.auth import AuthenticatedUser
from app.models.integration_contract import HrisEnvelope, HrisEnvelopeMeta


def build_hris_envelope(
    *,
    data: Any,
    module: str,
    request_id: str,
    tenant_id: str,
    actor: AuthenticatedUser,
    message: str = "ok",
    resolved_tenant_id: Optional[str] = None,
    resolved_user_id: Optional[str] = None,
) -> Dict[str, Any]:
    envelope = HrisEnvelope(
        success=True,
        message=message,
        data=data,
        meta=HrisEnvelopeMeta(
            request_id=request_id,
            module=module,
            tenant_id=tenant_id,
            resolved_tenant_id=resolved_tenant_id or "",
            resolved_user_id=resolved_user_id or "",
            effective_role=actor.effective_role,
            api_version="v1",
            timestamp=datetime.now(timezone.utc).isoformat(),
        ),
    )
    return envelope.model_dump()
