from typing import Optional

import strawberry
from strawberry.schema.config import StrawberryConfig
from fastapi import Request

from app.services.core_client import UpstreamGatewayError, call_core_json


@strawberry.type
class GatewayError:
    code: str
    message: str
    status_code: int
    correlation_id: Optional[str] = None


@strawberry.type
class JsonObjectResult:
    ok: bool
    data: strawberry.scalars.JSON
    error: Optional[GatewayError] = None


def _ok(data: dict) -> JsonObjectResult:
    return JsonObjectResult(ok=True, data=data, error=None)


def _err(exc: UpstreamGatewayError) -> JsonObjectResult:
    return JsonObjectResult(
        ok=False,
        data={},
        error=GatewayError(
            code=exc.code,
            message=exc.message,
            status_code=exc.status_code,
            correlation_id=exc.correlation_id,
        ),
    )


@strawberry.type
class Query:
    @strawberry.field(description="Tenant-aware module catalog; module RBAC/tenancy remains delegated downstream.")
    def module_catalog(self, info: strawberry.Info) -> JsonObjectResult:
        request: Request = info.context["request"]
        try:
            data = call_core_json(request, "GET", "/modules/catalog")
            return _ok(data)
        except UpstreamGatewayError as exc:
            return _err(exc)

    @strawberry.field(description="Dashboard aggregate from existing Core contracts.")
    def dashboard_summary(self, info: strawberry.Info) -> JsonObjectResult:
        request: Request = info.context["request"]
        try:
            data = call_core_json(request, "GET", "/dashboard/summary")
            return _ok(data)
        except UpstreamGatewayError as exc:
            return _err(exc)


@strawberry.type
class Mutation:
    @strawberry.mutation(description="Issue secure workspace launch/handoff token for module shell orchestration.")
    def workspace_launch(self, info: strawberry.Info, module_id: str) -> JsonObjectResult:
        request: Request = info.context["request"]
        try:
            data = call_core_json(
                request,
                "POST",
                f"/modules/catalog/{module_id}/handoff",
            )
            return _ok(data)
        except UpstreamGatewayError as exc:
            return _err(exc)


schema = strawberry.Schema(
    query=Query,
    mutation=Mutation,
    config=StrawberryConfig(auto_camel_case=False),
)

