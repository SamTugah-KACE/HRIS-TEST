# Codebase tour (Where to change what)

This guide is for beginners: if you have a task, start here to find the right folder/file quickly.

---

## “I need to change the UI”

Go to `apps/frontend/portal/`.

- **Routes / navigation**: `apps/frontend/portal/src/router.tsx`, `apps/frontend/portal/src/components/Sidebar.tsx`
- **Auth UI + SSO session wiring**: `apps/frontend/portal/src/auth/AuthProvider.tsx`, `apps/frontend/portal/src/components/RoleSwitcher.tsx`
- **API calls to Core**: `apps/frontend/portal/src/api/httpClient.ts`, `apps/frontend/portal/src/api/hrisCoreClient.ts`
- **Key pages**:
  - Dashboard: `apps/frontend/portal/src/pages/DashboardPage.tsx`
  - Profile (employee self-service): `apps/frontend/portal/src/pages/ProfilePage.tsx`
  - Staff records (managers): `apps/frontend/portal/src/pages/EmployeeListPage.tsx`
  - Employee 360: `apps/frontend/portal/src/pages/EmployeeDetailPage.tsx`
  - Leave: `apps/frontend/portal/src/pages/modules/LeavePage.tsx`
  - Appraisal: `apps/frontend/portal/src/pages/modules/AppraisalPage.tsx`

Beginner tip: If the UI renders but shows empty data, check module readiness and Core API errors first. Product runtime should use real Core data, not local mock datasets.

---

## “I need to change API behavior / data sent to the portal”

Go to `apps/backend/hris-core-api/`.

- **FastAPI app entrypoint**: `apps/backend/hris-core-api/app/main.py`
- **Settings/config**: `apps/backend/hris-core-api/app/core/settings.py`
- **Auth + roles**:
  - Keycloak validation and limited test/debug helpers live under `apps/backend/hris-core-api/app/core/auth.py`
  - SSO endpoints: `apps/backend/hris-core-api/app/api/auth_sso.py`
- **Portal-facing endpoints (BFF)**:
  - Current user: `apps/backend/hris-core-api/app/api/me.py`
  - Dashboard aggregation: `apps/backend/hris-core-api/app/api/dashboard.py`
  - Employees list + 360 view: `apps/backend/hris-core-api/app/api/employees.py`
  - Module pages: `apps/backend/hris-core-api/app/api/modules.py`
- **Calling production modules**:
  - “Client” layer: `apps/backend/hris-core-api/app/clients/*_client.py`
  - Adapter layer (contract alignment / normalization): `apps/backend/hris-core-api/app/adapters/*`

Beginner tip: When debugging missing data, check Tenant Registry mapping, module readiness, adapter errors, and service credentials. Product APIs should fail closed instead of returning hardcoded data.

---

## “I need to change tenant mapping / onboarding”

There are two places depending on what you mean:

- **Tenant Registry service** (source of truth for mappings): `apps/backend/tenant-registry-service/`
  - Endpoints: `apps/backend/tenant-registry-service/app/api/tenants.py`
  - DB model: `apps/backend/tenant-registry-service/app/models/tenant.py`
  - DB bootstrap/init: `apps/backend/tenant-registry-service/app/core/db_bootstrap.py`
- **Core API behavior using the registry**: `apps/backend/hris-core-api/app/services/tenant_registry_client.py`

---

## “I need to change login/roles (Keycloak)”

- **Realm export**: `identity/realm-export.json`
- **Core API SSO proxy**: `apps/backend/hris-core-api/app/api/auth_sso.py`
- **Portal SSO/session wiring**: `apps/frontend/portal/src/auth/AuthProvider.tsx`
- `apps/frontend/portal/src/keycloak.ts` is a legacy/direct-adapter helper and
  is not the authoritative normal-runtime session flow.

Important: Keycloak is the expected mode for production-like development:

- `keycloak`: real SSO and token validation
- `dev`: limited debug mode only for isolated tests or emergency local diagnostics

---

## “I need to run or troubleshoot the stack”

Use the current launch paths:

- Local: `scripts/start_local_stack.py` (and `scripts/start-local-stack.ps1`)
- Docker: generate `.env.docker.development` with
  `scripts/prepare_docker_dev_env.py`, then run the root Compose files with
  `--wait` as shown in `docs/START_HERE.md`.

Docs:

- `README.md` (most common commands)
- `docs/ops/env-variables.md` (how env is organized)
- `docs/ops/enrollment-jobs-email-and-keycloak-reset.md` (tenant/user enrollment, email, and job diagnosis)
