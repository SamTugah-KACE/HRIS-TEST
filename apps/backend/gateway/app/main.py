from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from strawberry.fastapi import GraphQLRouter

from app.core.settings import get_settings
from app.graphql.schema import schema

settings = get_settings()
allowed_origins = [o.strip() for o in settings.cors_allowed_origins.split(",") if o.strip()]

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Federated-style GraphQL gateway over existing HRIS Core contracts.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def get_context(request: Request):
    return {"request": request}


graphql_app = GraphQLRouter(schema, context_getter=get_context)
app.include_router(graphql_app, prefix="/graphql", tags=["graphql"])


@app.get("/health", tags=["health"])
def health():
    return {"status": "ok"}

