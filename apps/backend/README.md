# Backend Entry Guide

This is the primary entry point for backend collaborators.

## Scope

- `apps/backend/hris-core-api/`: HRIS aggregation API (FastAPI)
- `apps/backend/tenant-registry-service/`: tenant mapping service (FastAPI + SQLAlchemy)
- `apps/backend/gateway/`: federated-style GraphQL gateway over Core contracts

## Quick Start

### Install backend dependencies

```bash
pip install -r apps/backend/tenant-registry-service/requirements.txt
pip install -r apps/backend/hris-core-api/requirements.txt
```

### Run backend services manually

```bash
# terminal 1
cd apps/backend/tenant-registry-service
python -m uvicorn app.main:app --reload --port 8001

# terminal 2
cd apps/backend/hris-core-api
python -m uvicorn app.main:app --reload --port 8000

# terminal 3 (optional GraphQL gateway)
cd apps/backend/gateway
python -m uvicorn app.main:app --reload --port 8010
```

### Run full local stack (recommended)

```bash
python scripts/start_local_stack.py --registry-port 8001 --core-port 8000 --portal-port 5173 --timeout 300 --auto-registry-port-fallback
```

With gateway:

```bash
python scripts/start_local_stack.py --with-gateway --registry-port 8001 --core-port 8000 --portal-port 5173 --gateway-port 8010 --timeout 300 --auto-registry-port-fallback
```

## Where to Work

- Core auth and session: `apps/backend/hris-core-api/app/core/`
- Core APIs: `apps/backend/hris-core-api/app/api/`
- Adapters and clients: `apps/backend/hris-core-api/app/adapters/`, `apps/backend/hris-core-api/app/clients/`
- Tenant resolution: `apps/backend/hris-core-api/app/services/tenant_registry_client.py`
- Registry API/model: `apps/backend/tenant-registry-service/app/api/`, `apps/backend/tenant-registry-service/app/models/`

## Guardrails

- Do not implement product changes inside `modules/` (reference-only replicas).
- Preserve tenant boundaries and delegated RBAC behavior.
- Prefer structured errors and fail-closed behavior over silent fallback responses.

## Backend Start and API Test Guide

### 1) Prepare environment files

Copy sample env files first.

```bash
cp apps/backend/tenant-registry-service/.env.example apps/backend/tenant-registry-service/.env
cp apps/backend/hris-core-api/.env.example apps/backend/hris-core-api/.env
cp apps/backend/gateway/.env.example apps/backend/gateway/.env
```

### 2) Install dependencies

```bash
pip install -r apps/backend/tenant-registry-service/requirements.txt
pip install -r apps/backend/hris-core-api/requirements.txt
pip install -r apps/backend/gateway/requirements.txt
```

### 3) Start the whole backend stack (recommended)

```bash
python scripts/start_local_stack.py --with-gateway --no-portal --registry-port 8001 --core-port 8000 --gateway-port 8010 --timeout 300 --auto-registry-port-fallback
```

PowerShell wrapper:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-local-stack.ps1 -IncludePortal:$false -WithGateway:$true
```

### 4) Verify backend health

```bash
curl http://127.0.0.1:8001/health
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8010/health
```

### 5) Test REST endpoints directly (dev headers)

```bash
curl -H "X-Debug-Roles: hris:hr_manager" -H "X-Debug-Username: hr.manager" -H "X-Debug-Employee-Id: e001" http://127.0.0.1:8000/me
curl -H "X-Debug-Roles: hris:hr_manager" -H "X-Debug-Username: hr.manager" -H "X-Debug-Employee-Id: e001" http://127.0.0.1:8000/dashboard/summary
curl -H "X-Debug-Roles: hris:employee" -H "X-Debug-Username: employee" -H "X-Debug-Employee-Id: e001" http://127.0.0.1:8000/modules/catalog
curl -H "X-Debug-Roles: hris:employee" -H "X-Debug-Username: employee" -H "X-Debug-Employee-Id: e001" -X POST http://127.0.0.1:8000/modules/catalog/srms/handoff
```

### 6) Test GraphQL gateway endpoints directly

Module catalog:

```bash
curl -X POST http://127.0.0.1:8010/graphql -H "Content-Type: application/json" -H "X-Debug-Roles: hris:employee" -H "X-Debug-Username: employee" -H "X-Debug-Employee-Id: e001" --data-raw "{\"query\":\"query { module_catalog { ok data error { code message status_code correlation_id } } }\"}"
```

Dashboard summary:

```bash
curl -X POST http://127.0.0.1:8010/graphql -H "Content-Type: application/json" -H "X-Debug-Roles: hris:hr_manager" -H "X-Debug-Username: hr.manager" -H "X-Debug-Employee-Id: e001" --data-raw "{\"query\":\"query { dashboard_summary { ok data error { code message status_code correlation_id } } }\"}"
```

Workspace launch mutation:

```bash
curl -X POST http://127.0.0.1:8010/graphql -H "Content-Type: application/json" -H "X-Debug-Roles: hris:employee" -H "X-Debug-Username: employee" -H "X-Debug-Employee-Id: e001" --data-raw "{\"query\":\"mutation Launch($moduleId: String!) { workspace_launch(module_id: $moduleId) { ok data error { code message status_code correlation_id } } }\",\"variables\":{\"moduleId\":\"srms\"}}"
```

### 7) Optional backend-only automated checks

```bash
cd apps/backend/hris-core-api
python -m pytest tests/test_rate_limiter.py tests/test_module_service_auth.py tests/test_identity_resolution_policy.py tests/test_no_stub_runtime.py
```

### 8) One-command backend API smoke test (REST + GraphQL)

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\test_backend_apis.ps1
```

If your Tenant Registry basic-auth password is different:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\test_backend_apis.ps1 -RegistryPassword "<your-password>"
```

If Core is running in Keycloak mode, pass an access token:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\test_backend_apis.ps1 -RegistryPassword "<your-password>" -AccessToken "<keycloak-access-token>"
```

### 9) Stop backend services

If started with `start_local_stack.py`, press `Ctrl+C` in that terminal.
