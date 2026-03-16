# Codebase tour (Where to change what)

This guide is for beginners: if you have a task, start here to find the right folder/file quickly.

---

## “I need to change the UI”

Go to `portal/`.

- **Routes / navigation**: `portal/src/router.tsx`, `portal/src/components/Sidebar.tsx`
- **Auth UI + role switching (dev mode)**: `portal/src/auth/AuthProvider.tsx`, `portal/src/components/RoleSwitcher.tsx`
- **API calls to Core**: `portal/src/api/httpClient.ts`, `portal/src/api/hrisCoreClient.ts`
- **Key pages**:
  - Dashboard: `portal/src/pages/DashboardPage.tsx`
  - Profile (employee self-service): `portal/src/pages/ProfilePage.tsx`
  - Staff records (managers): `portal/src/pages/EmployeeListPage.tsx`
  - Employee 360: `portal/src/pages/EmployeeDetailPage.tsx`
  - Leave: `portal/src/pages/modules/LeavePage.tsx`
  - Appraisal: `portal/src/pages/modules/AppraisalPage.tsx`

Beginner tip: If the UI renders but shows “empty” data, check whether `VITE_PORTAL_DATA_MODE` is set to `mock` or `api` in `portal/.env` (see `portal/.env.example`).

---

## “I need to change API behavior / data sent to the portal”

Go to `hris-core-api/`.

- **FastAPI app entrypoint**: `hris-core-api/app/main.py`
- **Settings/config**: `hris-core-api/app/core/settings.py`
- **Auth + roles**:
  - Dev headers (`X-Debug-Roles`) and Keycloak validation live under `hris-core-api/app/core/auth.py`
  - SSO endpoints: `hris-core-api/app/api/auth_sso.py`
- **Portal-facing endpoints (BFF)**:
  - Current user: `hris-core-api/app/api/me.py`
  - Dashboard aggregation: `hris-core-api/app/api/dashboard.py`
  - Employees list + 360 view: `hris-core-api/app/api/employees.py`
  - Module pages: `hris-core-api/app/api/modules.py`
- **Calling production modules**:
  - “Client” layer: `hris-core-api/app/clients/*_client.py`
  - Adapter layer (contract alignment / normalization): `hris-core-api/app/adapters/*`

Beginner tip: When debugging, first decide if you’re in **stub mode** (`USE_STUB_DATA=true`) or **live mode** (`USE_STUB_DATA=false`). Stub mode bypasses real module calls by design.

---

## “I need to change tenant mapping / onboarding”

There are two places depending on what you mean:

- **Tenant Registry service** (source of truth for mappings): `tenant-registry-service/`
  - Endpoints: `tenant-registry-service/app/api/tenants.py`
  - DB model: `tenant-registry-service/app/models/tenant.py`
  - DB bootstrap/init: `tenant-registry-service/app/core/db_bootstrap.py`
- **Core API behavior using the registry**: `hris-core-api/app/services/tenant_registry_client.py`

---

## “I need to change login/roles (Keycloak)”

- **Realm export**: `identity/realm-export.json`
- **Core API SSO proxy**: `hris-core-api/app/api/auth_sso.py`
- **Portal Keycloak wiring**: `portal/src/keycloak.ts`

Important: The repo supports two auth modes:

- `dev`: fast local work, no real SSO required
- `keycloak`: real SSO and token validation

---

## “I need to run or troubleshoot the stack”

Start with the wrappers (they add health checks + clearer output):

- Local: `scripts/start_local_stack.py` (and `scripts/start-local-stack.ps1`)
- Docker: `scripts/start_docker_stack.py` (and `scripts/start-docker-stack.ps1`)

Docs:

- `README.md` (most common commands)
- `docs/ops/env-variables.md` (how env is organized)

