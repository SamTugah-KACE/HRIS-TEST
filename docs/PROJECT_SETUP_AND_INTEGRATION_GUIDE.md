# HRIS Platform Setup, Structure, Integration, and RBAC Guide

Last updated: 2026-08-04

This is the canonical first-setup and integration guide for the current grouped
repo layout. The deployable HRIS apps now live under `apps/`; old root-level
`portal/`, `hris-core-api/`, and `tenant-registry-service/` paths should be
treated as legacy paths unless a compatibility script explicitly falls back to
them.

The platform is a multi-tenant HRIS shell that integrates these native systems:

- SRMS: Staff Records Management System
- eAppraisal: Performance Appraisal Management System
- eLeave: Leave Management System
- HRIS native features: dashboard, profile hub, employee 360, tenant admin,
  branding, storage settings, reports, module catalog, and secure handoff

## 1. Runtime Architecture

The normal request path is:

```text
Browser
  -> Portal (React/Vite)
  -> HRIS Core API (FastAPI BFF)
  -> Tenant Registry (FastAPI/Postgres)
  -> SRMS / eAppraisal / eLeave native APIs
```

Key rules:

- Portal calls Core API. Portal should not call native module APIs directly.
- Core API validates identity, resolves tenant mapping, calls modules, and
  normalizes responses for the portal.
- Tenant Registry maps the global `tenant_id` to native module identifiers:
  `srms_schema`, `srms_slug`, `eappraisal_subdomain`, and `eleave_subdomain`.
- Keycloak is the central identity provider for production-like and production
  runtime.
- Native modules keep their own tenant-specific RBAC. HRIS uses global roles for
  coarse navigation and delegates fine-grained authorization to each module.
- Product runtime must not depend on stub data. `USE_STUB_DATA=true` is test-only.

## 2. First Setup: Development Mode

The supported development path is production-like: real Keycloak, real Tenant
Registry, real module endpoints or reachable development/staging module
instances. Debug auth can still be used for isolated tests, but it is not the
normal product-development mode.

### 2.1 Prerequisites

Install:

- Git
- Python 3.11 or newer
- Node.js 18 or newer and npm
- Docker Desktop or Docker Engine with Compose v2
- PostgreSQL client tools are helpful, but Docker can supply Postgres

Recommended ports:

- Portal: `5173` locally and on the Docker host
- HRIS Core API: `8000`
- Tenant Registry: `8001` externally, `8000` inside Docker
- GraphQL Gateway: `8010`
- Keycloak: `8080`
- Postgres: `5432`
- pgAdmin: `5050`

### 2.2 Fastest Development Setup With Docker

Use this when you want the whole stack running with the least machine-specific
setup.

1. Configure the Core API environment and generate the ignored Docker-development file:

```powershell
Copy-Item apps/backend/hris-core-api/.env.example apps/backend/hris-core-api/.env
python scripts/prepare_docker_dev_env.py
```

2. Edit `apps/backend/hris-core-api/.env`, then rerun the generator:

- Set `HRIS_APP_ENV=staging` or `HRIS_APP_ENV=development`.
- Set `HRIS_AUTH_MODE=keycloak`.
- Set `HRIS_USE_STUB_DATA=false`.
- Set `HRIS_AUTH_STATE_SECRET` to a long random value.
- Set `HRIS_MODULE_TOKEN_SECRET` to a long random value for module handoff.
- Set Tenant Registry basic auth to a non-default local secret if possible.
- Set module URLs and service secrets for the environments you are integrating.

3. Start and health-gate the stack:

```powershell
docker compose --env-file .env.docker.development -f docker-compose.yml -f docker-compose.keycloak.yml up -d --build --wait
```

4. Open:

- Portal: `http://localhost:5173`
- Core API: `http://localhost:8000/docs`
- Tenant Registry: `http://localhost:8001/docs`
- GraphQL Gateway: `http://localhost:8010/graphql`
- Keycloak Admin: `http://localhost:8080/admin`
- pgAdmin: `http://localhost:5050`

5. Stop without deleting data:

```powershell
docker compose --env-file .env.docker.development -f docker-compose.yml -f docker-compose.keycloak.yml down
```

6. Stop and reset volumes:

```powershell
docker compose --env-file .env.docker.development -f docker-compose.yml -f docker-compose.keycloak.yml down -v
```

### 2.3 Local Development Setup Without Running HRIS Apps in Docker

Use this when frontend/backend teams want hot reload from the host machine.
Postgres and Keycloak can still run in Docker.

1. Start shared infrastructure:

```powershell
docker compose --env-file .env.docker.development -f docker-compose.yml -f docker-compose.keycloak.yml up -d postgres keycloak
```

2. Copy env examples:

```powershell
Copy-Item apps/backend/tenant-registry-service/.env.example apps/backend/tenant-registry-service/.env
Copy-Item apps/backend/hris-core-api/.env.example apps/backend/hris-core-api/.env
Copy-Item apps/backend/gateway/.env.example apps/backend/gateway/.env
Copy-Item apps/frontend/portal/.env.example apps/frontend/portal/.env
```

3. Edit `apps/backend/tenant-registry-service/.env`:

```text
DATABASE_URL=postgresql://hris:hris_secret@localhost:5432/hris_tenant_registry
INTERNAL_BASIC_AUTH_USERNAME=hris_internal
INTERNAL_BASIC_AUTH_PASSWORD=registry_secret
```

4. Edit `apps/backend/hris-core-api/.env` for local Keycloak and registry:

```text
APP_ENV=development
AUTH_MODE=keycloak
USE_STUB_DATA=false
KEYCLOAK_ISSUER=http://localhost:8080/realms/hris-platform
KEYCLOAK_JWKS_URL=http://localhost:8080/realms/hris-platform/protocol/openid-connect/certs
KEYCLOAK_AUDIENCE_HRIS_CORE=account,hris-core-api,hris-portal
KEYCLOAK_CLIENT_ID_PORTAL=hris-portal
PORTAL_BASE_URL=http://localhost:5173
AUTH_STATE_SECRET=replace-with-long-random-local-secret
TENANT_REGISTRY_BASE_URL=http://127.0.0.1:8001
TENANT_REGISTRY_BASIC_AUTH_USERNAME=hris_internal
TENANT_REGISTRY_BASIC_AUTH_PASSWORD=registry_secret
AUTOMATION_STORE_DATABASE_URL=postgresql://hris:hris_secret@localhost:5432/hris_tenant_registry
```

Also configure module-specific values as needed:

```text
SRMS_BASE_URL=https://srms.gi-kace.com.gh
SRMS_HRIS_SHARED_SECRET=...
SRMS_HRIS_SERVICE_TOKEN=...
EAPPRAISAL_DOMAIN_TEMPLATE=https://appraisal.{subdomain}.com.gh
EAPPRAISAL_INTEGRATION_BASE_URL=https://appraisal.gi-kace.com.gh
EAPPRAISAL_HRIS_SHARED_SECRET=...
EAPPRAISAL_HRIS_SERVICE_TOKEN=...
ELEAVE_DOMAIN_TEMPLATE=https://{subdomain}.eleave.com.gh
ELEAVE_HRIS_SHARED_SECRET=...
ELEAVE_HRIS_SERVICE_TOKEN=...
```

5. Edit `apps/frontend/portal/.env`:

```text
VITE_HRIS_CORE_API_BASE_URL=http://localhost:8000
VITE_HRIS_GATEWAY_API_BASE_URL=http://localhost:8010
VITE_USE_GRAPHQL_GATEWAY=false
VITE_AUTH_MODE=keycloak
VITE_PORTAL_DATA_MODE=api
```

6. Install dependencies:

```powershell
pip install -r apps/backend/tenant-registry-service/requirements.txt
pip install -r apps/backend/hris-core-api/requirements.txt
pip install -r apps/backend/gateway/requirements.txt
```

```powershell
Set-Location apps/frontend/portal
npm install
Set-Location ../../..
```

7. Run host services with health gates:

```powershell
python scripts/start_local_stack.py --with-gateway --registry-port 8001 --core-port 8000 --gateway-port 8010 --portal-port 5173 --timeout 300 --auto-registry-port-fallback
```

8. Open:

- Portal: `http://127.0.0.1:5173`
- Core API: `http://127.0.0.1:8000/docs`
- Tenant Registry: `http://127.0.0.1:8001/docs`
- Gateway: `http://127.0.0.1:8010/graphql`

### 2.4 Debug/Test Mode

The code still has debug headers and portal role switching, but Core API now
rejects non-Keycloak auth outside test mode. Use this only for isolated tests:

```text
APP_ENV=test
AUTH_MODE=dev
USE_STUB_DATA=false
```

Debug request headers understood by Core API:

```text
X-Debug-Roles: hris:hr_manager
X-Debug-Username: hr.manager
X-Debug-Employee-Id: e001
X-Debug-Tenant-Id: 11111111-1111-1111-1111-111111111111
```

Do not deploy debug auth or stub data.

## 3. First Setup: Production Mode

There are two production-like paths:

- Local production-like Docker: root `docker-compose.yml` plus
  `docker-compose.keycloak.yml` and generated `.env.docker.development`.
- Server production deployment: `infra/docker-compose.yml` with production
  secrets, external DNS/TLS, and hardened Keycloak settings.

### 3.1 Production Environment Requirements

Required:

- HTTPS for Portal, Core API, Keycloak, and module UI/API origins.
- `AUTH_MODE=keycloak`.
- `USE_STUB_DATA=false`.
- `AUTH_COOKIE_SECURE=true` when served over HTTPS.
- `AUTH_COOKIE_SAMESITE=none` only if `AUTH_COOKIE_SECURE=true`.
- Real Tenant Registry basic-auth password.
- `AUTOMATION_STORE_DATABASE_URL` when module handoff replay protection or
  automation is enabled.
- `ALLOW_LOW_CONFIDENCE_IDENTITY_FALLBACK=false` in production.
- Native module service secrets set for each integrated module.
- Module launch allowlist configured if exposing native launch URLs:
  `MODULE_LAUNCH_HOST_SUFFIX_ALLOWLIST`.

Recommended production Core API settings:

```text
APP_ENV=production
AUTH_MODE=keycloak
USE_STUB_DATA=false
TENANT_REGISTRY_ALLOW_FALLBACK=false
TENANT_REGISTRY_STARTUP_WAIT_FAIL_OPEN=false
AUTH_COOKIE_SECURE=true
ALLOW_LOW_CONFIDENCE_IDENTITY_FALLBACK=false
MODULE_HANDOFF_ENABLED=true
MODULE_SERVICE_AUTH_MODE=jwt_strict
ENABLE_INTEGRATION_DEBUG_ENDPOINTS=false
ONBOARDING_DEV_CREDENTIALS_EXPORT_ENABLED=false
EXPOSE_TEMPORARY_PASSWORD_IN_API=false
```

### 3.2 Production-Like Docker Run

1. Create and edit env file:

```powershell
python scripts/prepare_docker_dev_env.py
```

Set at minimum:

```text
HRIS_APP_ENV=production
HRIS_AUTH_MODE=keycloak
HRIS_USE_STUB_DATA=false
HRIS_AUTH_STATE_SECRET=<long-random-secret>
HRIS_MODULE_TOKEN_SECRET=<long-random-secret>
HRIS_TENANT_REGISTRY_BASIC_AUTH_PASSWORD=<strong-secret>
HRIS_AUTH_COOKIE_SECURE=true
HRIS_AUTH_COOKIE_SAMESITE=lax
HRIS_ALLOW_LOW_CONFIDENCE_IDENTITY_FALLBACK=false
```

2. Start:

```powershell
docker compose --env-file .env.docker.development -f docker-compose.yml -f docker-compose.keycloak.yml up -d --build --wait
```

3. Verify:

```powershell
curl http://127.0.0.1:8001/health
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8010/health
```

### 3.3 Server Production Run With `infra/docker-compose.yml`

The `infra/` compose file is closer to server deployment. It includes Nginx and
uses production-style Keycloak start settings.

1. Create an environment file outside source control, for example
   `infra/.env.production`.

2. Populate all required variables referenced by `infra/docker-compose.yml`,
   including:

```text
TENANT_REGISTRY_DB_PASSWORD=...
TENANT_REGISTRY_BASIC_AUTH_USERNAME=...
TENANT_REGISTRY_BASIC_AUTH_PASSWORD=...
KEYCLOAK_ADMIN=...
KEYCLOAK_ADMIN_PASSWORD=...
KEYCLOAK_DB_HOST=...
KEYCLOAK_DB_NAME=...
KEYCLOAK_DB_USER=...
KEYCLOAK_DB_PASSWORD=...
KEYCLOAK_EXTERNAL_HOSTNAME=...
KEYCLOAK_ISSUER=...
KEYCLOAK_JWKS_URL=...
KEYCLOAK_AUDIENCE_HRIS_CORE=...
SRMS_BASE_URL=...
EAPPRAISAL_DOMAIN_TEMPLATE=...
ELEAVE_DOMAIN_TEMPLATE=...
HRIS_GATEWAY_CORS_ALLOWED_ORIGINS=...
HRIS_CORE_API_PUBLIC_BASE_URL=...
KEYCLOAK_PUBLIC_BASE_URL=...
KEYCLOAK_REALM=hris-platform
KEYCLOAK_PORTAL_CLIENT_ID=hris-portal
```

3. Start from the repo root:

```powershell
docker compose --env-file infra/.env.production -f infra/docker-compose.yml up --build -d
```

4. Check containers:

```powershell
docker compose --env-file infra/.env.production -f infra/docker-compose.yml ps
```

5. Run release checks:

```powershell
python scripts/check_repo_policy.py
```

If backend dependencies are installed locally:

```powershell
Set-Location apps/backend/hris-core-api
python -m pytest
Set-Location ../../..
```

### 3.4 Superadmin Onboarding

Use the script only after Keycloak and Core settings are aligned:

```powershell
python scripts/onboard_keycloak_superadmin.py --show-account-identities
```

Then run the secure onboarding path:

```powershell
python scripts/onboard_keycloak_superadmin.py --username "<preferred-username>" --auth-kind local --account-auth-mode session --enforce-group-authorization
```

Audit output is written under `logs/security/`. Do not commit exported secrets
or temporary credentials.

### 3.5 Existing Tenant User Migration and Keycloak Setup

Keycloak setup is required for both development and production-like runtime.
It should be automated from reviewed configuration, not recreated by hand in
the admin console. Manual Keycloak changes are acceptable for emergency
inspection, but the durable source of truth should be `identity/realm-export.json`,
environment variables, and idempotent bootstrap/sync tooling.

Existing tenant users from SRMS, eAppraisal, eLeave, and future modules should
also be migrated through automation, but not through a blind first-boot job that
silently resets passwords or emails every employee. The safe pattern is:

1. Import/reconcile Keycloak realm, clients, roles, token mappers, SMTP, and
   security settings.
2. Import tenant inventory into Tenant Registry.
3. Run read-only user inventory and drift snapshots.
4. Review duplicate emails, missing emails, tenant mismatches, inactive users,
   and role-mapping gaps.
5. Provision or link Keycloak users in controlled batches.
6. Send welcome/reset emails only after SMTP and audit settings are verified.
7. Disable migration/debug endpoints after cutover.

Do not migrate native module password hashes into Keycloak. Create or link
Keycloak users, then use Keycloak forgot-password, action email, or temporary
password flows. Native modules remain the authority for tenant-specific RBAC;
Keycloak stores HRIS coarse roles and the `tenant_id` claim needed for HRIS
login and routing.

Full runbook: `docs/ops/tenant-identity-migration-keycloak.md`.

## 4. How To Run Each Mode

| Mode | Command | Notes |
| --- | --- | --- |
| Full Docker development | `python scripts/prepare_docker_dev_env.py`, then `docker compose --env-file .env.docker.development -f docker-compose.yml -f docker-compose.keycloak.yml up -d --build --wait` | Recommended first run. Uses Docker services. |
| Local hot-reload development | `python scripts/start_local_stack.py --with-gateway --registry-port 8001 --core-port 8000 --gateway-port 8010 --portal-port 5173 --timeout 300 --auto-registry-port-fallback` | Requires local env files and shared infra running. |
| Backend only | `python scripts/start_local_stack.py --with-gateway --no-portal --registry-port 8001 --core-port 8000 --gateway-port 8010 --timeout 300 --auto-registry-port-fallback` | Useful for API work. |
| Portal only | `cd apps/frontend/portal && npm run dev` | Requires Core API URL in portal `.env`. |
| Production-like local Docker | Use the generated `.env.docker.development` command above. | Local validation only; do not reuse development secrets in production. |
| Server production | `docker compose --env-file infra/.env.production -f infra/docker-compose.yml up --build -d` | Requires DNS/TLS/secrets and external module URLs. |
| Stop Docker stack | `docker compose --env-file .env.docker.development -f docker-compose.yml -f docker-compose.keycloak.yml down` | Keeps volumes. |
| Reset Docker stack | `docker compose --env-file .env.docker.development -f docker-compose.yml -f docker-compose.keycloak.yml down -v` | Deletes local volumes and all contained data. |

## 5. Team Ownership: Where To Work

Frontend team:

- Primary workspace: `apps/frontend/portal/`
- Routing and page composition: `apps/frontend/portal/src/router.tsx`
- Page screens: `apps/frontend/portal/src/pages/`
- Shared shell components: `apps/frontend/portal/src/components/`
- Auth state and role UI: `apps/frontend/portal/src/auth/`
- API clients: `apps/frontend/portal/src/api/`
- Module iframe host and bridge: `apps/frontend/portal/src/components/ModuleFrame.tsx`

Backend team:

- Primary workspace: `apps/backend/`
- Portal-facing REST API: `apps/backend/hris-core-api/app/api/`
- Auth, settings, JWT validation: `apps/backend/hris-core-api/app/core/`
- Module adapters: `apps/backend/hris-core-api/app/adapters/`
- Module HTTP clients: `apps/backend/hris-core-api/app/clients/`
- Identity, tenant, sync, readiness, handoff services:
  `apps/backend/hris-core-api/app/services/`
- Tenant Registry service: `apps/backend/tenant-registry-service/`
- Optional GraphQL facade: `apps/backend/gateway/`

Native module teams:

- SRMS team: `modules/Staff-Records-Management-System/`
- eAppraisal team: `modules/performance-appraisal/`
- eLeave team: `modules/eLeave/`

Platform/DevOps team:

- Compose and deployment: `docker-compose.yml`, `docker-compose.keycloak.yml`,
  `infra/`
- Identity realm export: `identity/realm-export.json`
- Startup and automation scripts: `scripts/`
- Operational docs: `docs/ops/`, `docs/security/`, `docs/qa/`

Do not make HRIS portal/backend product changes inside `modules/` unless the
task is explicitly owned by the native module team.

## 6. Project Structure and File Purposes

### 6.1 Repository Root

| Path | Purpose |
| --- | --- |
| `.github/` | GitHub workflow and repository automation configuration. |
| `.vscode/` | Local/editor workspace settings. Do not rely on this for runtime behavior. |
| `apps/` | Standardized home for deployable HRIS applications. |
| `docs/` | Architecture, operations, contracts, tasks, QA, security, and onboarding docs. |
| `identity/` | Keycloak realm export and backups. |
| `infra/` | Production-oriented infrastructure compose, Nginx configs, DB seed files. |
| `logs/` | Runtime/audit logs generated by local automation. Do not commit secrets. |
| `modules/` | Native module replicas/reference apps: SRMS, eAppraisal, eLeave. |
| `scripts/` | Cross-platform startup, onboarding, reset, API smoke, and policy scripts. |
| `.env.docker.development` | Ignored generated Docker-development values; produced by `scripts/prepare_docker_dev_env.py`. |
| `.env.superadmin-onboard` | Local operator env for superadmin onboarding. Treat as sensitive/local. |
| `.gitignore` | Ignore rules for local outputs, secrets, dependencies, and generated files. |
| `CONTRIBUTING.md` | Collaboration and contribution notes. |
| `docker-compose.yml` | Local all-in-one Docker stack: Postgres, Keycloak, Registry, Core, Gateway, Portal, pgAdmin. |
| `docker-compose.keycloak.yml` | Compose override that switches Core/Portal into Keycloak mode and passes production-like module/handoff settings. |
| `README.md` | High-level overview and common command reference. |
| `i-want-you-to-buzzing-taco.md` | Existing generated/project note; not part of runtime. |
| `production eAppraisal employee list my appriasals data.txt` | Reference data dump; not application code. |

### 6.2 `apps/`

| Path | Purpose |
| --- | --- |
| `apps/README.md` | Explains grouped app layout and team entry docs. |
| `apps/backend/README.md` | Backend setup, run commands, and backend ownership guide. |
| `apps/backend/hris-core-api/` | Main FastAPI BFF/integration layer. |
| `apps/backend/tenant-registry-service/` | FastAPI service storing global tenant-to-module mapping. |
| `apps/backend/gateway/` | Optional Strawberry GraphQL facade over Core API contracts. |
| `apps/frontend/README.md` | Frontend setup and ownership guide. |
| `apps/frontend/portal/` | React/TypeScript/Vite portal shell. |

### 6.3 `apps/backend/hris-core-api/`

| Path | Purpose |
| --- | --- |
| `.env.example` | Local Core API env template. |
| `Dockerfile` | Builds the Core API image. |
| `requirements.txt` | Python dependencies. |
| `app/main.py` | FastAPI app, CORS, request correlation, startup validation, router wiring. |
| `app/core/settings.py` | Pydantic settings and production fail-closed validation. |
| `app/core/auth.py` | Keycloak JWT validation, debug auth, role extraction, tenant conflict guard. |
| `app/api/account.py` | Account/session related endpoints. |
| `app/api/auth_sso.py` | HRIS-native SSO start/callback/session/refresh/logout endpoints. |
| `app/api/dashboard.py` | Aggregated dashboard cards and role-aware quick actions. |
| `app/api/employees.py` | Employee roster, team roster, employee 360 endpoints. |
| `app/api/federated_directory_debug.py` | Debug endpoints for federated identity sync. |
| `app/api/integrations_debug.py` | Integration readiness/debug endpoints. |
| `app/api/integration_sync.py` | Manual sync/drift/automation endpoints. |
| `app/api/jit_setup.py` | Just-in-time module setup endpoint. |
| `app/api/me.py` | Current user identity, tenant, modules, and canonical identity map. |
| `app/api/modules.py` | Module catalog, handoff, profile, appraisal, leave, capabilities, tasks, actions. |
| `app/api/tenants_onboarding.py` | Tenant onboarding, branding, storage, and related admin endpoints. |
| `app/adapters/base.py` | Adapter interfaces for SRMS/eAppraisal/eLeave. |
| `app/adapters/registry.py` | Cached adapter factory. |
| `app/adapters/srms.py` | HTTP adapter for SRMS routes, auth headers, encryption wrappers, inventory, provisioning. |
| `app/adapters/eappraisal.py` | HTTP adapter for eAppraisal summaries, appraisals, inventory, token refresh. |
| `app/adapters/eleave.py` | HTTP adapter for eLeave summary/history and tenant path handling. |
| `app/clients/adapter_utils.py` | Shared auth/header/payload decoding helpers. |
| `app/clients/srms_client.py` | Core facade over the SRMS adapter. |
| `app/clients/eappraisal_client.py` | Core facade over the eAppraisal adapter. |
| `app/clients/eleave_client.py` | Core facade over the eLeave adapter. |
| `app/models/integration_contract.py` | Shared integration header/envelope models. |
| `app/models/tenant_mapping.py` | Tenant and module status models used by Core. |
| `app/services/admin_bootstrap.py` | Optional startup admin bootstrapping. |
| `app/services/auto_provision_service.py` | Cross-module missing-user provisioning planner/executor. |
| `app/services/auto_sync_service.py` | Background tenant/user drift and identity sync loop. |
| `app/services/automation_store.py` | Postgres-backed sync, identity, handoff replay, and runtime settings store. |
| `app/services/db_health.py` | Runtime database readiness/bootstrap checks. |
| `app/services/federated_directory_sync.py` | Builds cross-module user inventory snapshots. |
| `app/services/identity_resolution.py` | Resolves canonical per-module employee identities. |
| `app/services/integration_envelope.py` | Shared integration response envelope helpers. |
| `app/services/integration_sync.py` | Sync orchestration helpers. |
| `app/services/jit_module_setup.py` | On-demand module enable/provision flow. |
| `app/services/jit_policy.py` | Tenant-scoped JIT role/action policies. |
| `app/services/keycloak_provisioning.py` | Keycloak user creation/update and temporary password support. |
| `app/services/module_handoff.py` | Short-lived signed module launch tokens and replay protection. |
| `app/services/module_launch.py` | Native module URL derivation and allowlist validation. |
| `app/services/module_readiness.py` | Per-module readiness and user-presence checks. |
| `app/services/onboarding.py` | Tenant onboarding service helpers. |
| `app/services/onboarding_automation.py` | Tenant/user sync, Keycloak provisioning, welcome email automation. |
| `app/services/persona_policy.py` | Role/persona authorization helpers for Core endpoints. |
| `app/services/rate_limiter.py` | Lightweight request rate limiting. |
| `app/services/tenant_branding_service.py` | Tenant branding config and media references. |
| `app/services/tenant_drift_sync.py` | Tenant drift snapshot generation. |
| `app/services/tenant_inventory_import.py` | Imports missing tenants from native module inventory. |
| `app/services/tenant_match_engine.py` | Strict tenant match policy for JIT integration. |
| `app/services/tenant_registry_client.py` | Core client for Tenant Registry with cache and import helpers. |
| `app/services/tenant_storage_service.py` | Tenant media/storage provider config. |
| `app/services/user_drift_sync.py` | User presence drift across modules. |
| `app/services/welcome_email_service.py` | Welcome email rendering and SMTP delivery. |
| `scripts/export_integration_contract_schema.py` | Exports integration schema artifacts. |
| `scripts/integration_sync_report.py` | Generates integration sync reports. |
| `scripts/module_contract_audit.py` | Audits module contract shape. |
| `scripts/sync_check.py` | Sync validation helper. |
| `tests/` | Pytest coverage for auth, tenant conflicts, policy, module handoff, readiness, no-stub runtime, rate limiters. |

### 6.4 `apps/backend/tenant-registry-service/`

| Path | Purpose |
| --- | --- |
| `.env.example` | Local Tenant Registry env template. |
| `Dockerfile` | Builds Tenant Registry image. |
| `requirements.txt` | Python dependencies. |
| `app/main.py` | FastAPI app and DB initialization on startup. |
| `app/api/tenants.py` | Internal basic-auth tenant list/get/import endpoints. |
| `app/core/database.py` | SQLAlchemy engine/session/base. |
| `app/core/db_bootstrap.py` | Optional database creation/readiness bootstrap. |
| `app/core/settings.py` | Registry settings. |
| `app/dependencies/db.py` | DB session dependency. |
| `app/models/tenant.py` | SQLAlchemy tenant table model. |
| `app/schemas/tenant.py` | Pydantic request/response schemas. |

### 6.5 `apps/backend/gateway/`

| Path | Purpose |
| --- | --- |
| `.env.example` | Gateway env template. |
| `Dockerfile` | Builds Gateway image. |
| `requirements.txt` | Python dependencies. |
| `app/main.py` | FastAPI app and `/graphql` mount. |
| `app/core/settings.py` | Gateway settings. |
| `app/graphql/schema.py` | Strawberry schema for module catalog, dashboard, workspace launch. |
| `app/services/core_client.py` | Forwards auth/debug/cookie headers to Core API and normalizes upstream errors. |
| `tests/test_graphql_contract.py` | Gateway contract tests. |

### 6.6 `apps/frontend/portal/`

| Path | Purpose |
| --- | --- |
| `.env.example` | Portal env template. |
| `Dockerfile` | Builds production static Portal image. |
| `package.json` | npm scripts/dependencies. |
| `package-lock.json` | Locked dependency graph. |
| `index.html` | Vite HTML entry. |
| `vite.config.ts` | Vite configuration. |
| `tsconfig.json` | TypeScript configuration. |
| `tailwind.config.js` | Tailwind design tokens and content paths. |
| `postcss.config.js` | PostCSS/Tailwind pipeline. |
| `hris_enterprise_primary_logo.png` | Portal logo asset. |
| `hris_enterprise_favicon_32.png` | Favicon PNG. |
| `hris_enterprise_favicon.ico` | Browser favicon. |
| `src/main.tsx` | React root render. |
| `src/App.tsx` | Top-level app composition. |
| `src/router.tsx` | Browser routes. |
| `src/index.css` | Global Tailwind/CSS rules. |
| `src/keycloak.ts` | Keycloak adapter wiring for legacy/direct auth helpers. |
| `src/api/httpClient.ts` | Axios client, CSRF, dev headers, refresh retry. |
| `src/api/hrisCoreClient.ts` | Typed REST/Gateway calls to Core. |
| `src/api/gatewayClient.ts` | Optional GraphQL gateway client. |
| `src/api/accountClient.ts` | Account-related client calls. |
| `src/auth/AuthProvider.tsx` | Auth session provider, SSO bootstrap, dev role switch support. |
| `src/auth/roles.ts` | HRIS role constants and role resolution. |
| `src/components/` | Shared shell components: layout, navbar, sidebar, module cards, module iframe, notifications, confirmations, loading/error UI. |
| `src/contexts/ModuleCapabilitiesContext.tsx` | Registry for module-declared profile/action capabilities. |
| `src/hooks/useModuleToken.ts` | Fetches module handoff launch and extracts token/origin/tenant slug. |
| `src/pages/` | Dashboard, profile, employee, reports, admin, and module pages. |
| `src/pages/admin/` | Tenant and role admin pages. |
| `src/pages/modules/` | Appraisal, leave, and native module workspace pages. |
| `src/config/dataMode.ts` | Portal data mode configuration. |
| `src/constants/moduleOrigins.ts` | Optional env-based native module origins. |
| `src/shared/moduleMode.ts` | Shared module mode helpers. |

### 6.7 `docs/`

| Path | Purpose |
| --- | --- |
| `docs/START_HERE.md` | Beginner entry path. |
| `docs/CODEBASE_TOUR.md` | Where-to-change-what guide. |
| `docs/GLOSSARY.md` | Shared terminology. |
| `docs/architecture/` | System overview, identity model, module integration, iframe bridge, code reading map. |
| `docs/api-contracts/` | Read/write API contracts for SRMS, eAppraisal, eLeave, module handoff, capability contracts. |
| `docs/backend/tasks/` | Backend implementation task specs. |
| `docs/frontend/tasks/` | Frontend implementation task specs. |
| `docs/collaboration/` | Collaboration and PR definition of done. |
| `docs/implementation/` | Roadmap, team distribution, migration map, readiness gates. |
| `docs/modules/` | Module-specific coherence guides. |
| `docs/ops/` | Deployment, env vars, tenant identity migration, release gates, observability, performance, reliability. |
| `docs/qa/` | Acceptance matrix. |
| `docs/security/` | Hardening and secure handoff specs. |
| `docs/ux/` | UX and accessibility docs. |
| `docs/PROJECT_SETUP_AND_INTEGRATION_GUIDE.md` | This guide. |

### 6.8 `identity/`

| Path | Purpose |
| --- | --- |
| `identity/realm-export.json` | Keycloak realm import for `hris-platform`, clients, roles, token mappers. |
| `identity/backups/` | Local Keycloak realm backups. Review before committing any backup. |

### 6.9 `infra/`

| Path | Purpose |
| --- | --- |
| `infra/docker-compose.yml` | Server-oriented production compose stack. |
| `infra/db-init/tenant_registry_dev_seed.sql` | Local seed SQL for Tenant Registry and Keycloak schema. |
| `infra/nginx/hris-portal.conf` | Nginx portal reverse proxy config. |
| `infra/nginx/hris-core-api.conf` | Nginx Core API reverse proxy config. |
| `infra/nginx/keycloak.conf` | Nginx Keycloak reverse proxy config. |

### 6.10 `scripts/`

| Path | Purpose |
| --- | --- |
| `scripts/start_docker_stack.py` | Cross-platform Docker stack launcher with health gates. |
| `scripts/start-docker-stack.ps1` | PowerShell Docker wrapper. |
| `scripts/start-docker-stack.sh` | Shell Docker wrapper. |
| `scripts/start_local_stack.py` | Cross-platform host-process launcher for Core, Registry, Portal, optional Gateway. |
| `scripts/start-local-stack.ps1` | PowerShell local wrapper. |
| `scripts/onboard_keycloak_superadmin.py` | Secure Keycloak superadmin onboarding. |
| `scripts/reset_keycloak_realm.py` | Keycloak realm reset helper. |
| `scripts/test_backend_apis.ps1` | REST/GraphQL backend smoke checks. |
| `scripts/check_repo_policy.py` | Repository policy and production-readiness checks. |

### 6.11 `modules/Staff-Records-Management-System/`

SRMS is a native, production-sized app included as a module replica/reference.
It has many historical docs and deployment scripts. Key directories/files:

| Path | Purpose |
| --- | --- |
| `.env` | Local SRMS env. Treat as sensitive. |
| `README.md` | SRMS module guide. |
| `docker-compose.production.yml` | SRMS production compose. |
| `docker-compose.secure.yml` | Hardened SRMS compose. |
| `docker-compose.unified.yml` | Unified SRMS deployment composition. |
| `Backend/` | SRMS FastAPI backend. |
| `Backend/main.py` | SRMS FastAPI entrypoint. |
| `Backend/requirements.txt` | SRMS backend dependencies. |
| `Backend/Dockerfile` | SRMS backend image. |
| `Backend/app/apis/` | SRMS API routers. |
| `Backend/app/apis/hris_integration_api.py` | HRIS-facing `/api/hris/v1/*` endpoints for dashboard, employees, tenant inventory, user inventory, provisioning. |
| `Backend/app/apis/sso_bridge_api.py` | Exchanges HRIS handoff token for SRMS session. |
| `Backend/app/dependencies/hris_auth.py` | HRIS auth dependency, shared-secret/service auth, module token support. |
| `Backend/app/models/` | SRMS public and tenant SQLAlchemy models. |
| `Backend/app/schemas/` | SRMS request/response schemas. |
| `Backend/app/services/` | SRMS business services: orgs, employees, security, storage, messaging, etc. |
| `Backend/database/` | SRMS DB session utilities. |
| `Backend/alembic/` | SRMS public/tenant migrations. |
| `Backend/tests/` | SRMS backend tests, including HRIS integration tests. |
| `frontend/` | SRMS React frontend. |
| `frontend/src/index.js` | SRMS frontend entry and HRIS bridge hook area. |
| `frontend/src/context/` | SRMS auth/org/API/WebSocket contexts. |
| `frontend/src/utils/` | SRMS URL, session, request signing, payload encryption/decryption helpers. |
| `frontend/Dockerfile` | SRMS frontend image. |
| `superadmin/` | SRMS superadmin UI/app assets. |
| `nginx/` | SRMS Nginx config/image support. |
| `scripts/` | SRMS operational scripts. |
| `*.md` at SRMS root | Historical implementation, security, deployment, and troubleshooting notes. |

### 6.12 `modules/performance-appraisal/`

eAppraisal is a native Angular + FastAPI module.

| Path | Purpose |
| --- | --- |
| `client/` | Angular frontend. |
| `client/package.json` | Angular dependencies/scripts. |
| `client/src/app/auth/` | Native authentication UI/services. |
| `client/src/app/main-app/` | Main tenant application pages: dashboard, staff, appraisal management, roles, reports. |
| `client/src/app/shared/guards/` | Auth, role, permission, appraisal guards. |
| `client/src/app/shared/interceptors/` | Token, tenant, loading, and error interceptors. |
| `client/src/app/store/` | Angular state actions/states. |
| `backend/app/` | FastAPI backend. |
| `backend/app/main.py` | eAppraisal FastAPI entrypoint and middleware wiring. |
| `backend/app/apis/routers.py` | Includes native routers and HRIS integration router. |
| `backend/app/apis/hris_integration_api.py` | HRIS service-to-service provisioning endpoint. |
| `backend/app/db/` | SQLAlchemy session, migration, schema initialization. |
| `backend/app/middleware/tenant.py` | Header-based tenant schema selection. |
| `backend/app/utils/rbac.py` | Tenant role and permission checks. |
| `backend/app/domains/` | Domain modules: auth, organization, appraisal, notification, tenancies. |

### 6.13 `modules/eLeave/`

eLeave is a native Angular + Laravel module using Stancl Tenancy.

| Path | Purpose |
| --- | --- |
| `backend/` | Laravel backend. |
| `backend/composer.json` | PHP dependencies. |
| `backend/artisan` | Laravel CLI entry. |
| `backend/config/tenancy.php` | Stancl tenancy configuration. |
| `backend/routes/api.php` | Central API routes and HRIS provisioning route. |
| `backend/routes/tenant.php` | Tenant path routes under `/{tenant}`. |
| `backend/app/Http/Controllers/HrisIntegrationController.php` | HRIS service-to-service provisioning endpoint. |
| `backend/app/Http/Controllers/` | Auth, staff, leave, roles, reports, org controllers. |
| `backend/app/Models/` | Tenant and central Eloquent models. |
| `backend/app/Jobs/` | Staff import and leave automation jobs. |
| `backend/app/Console/Commands/` | Scheduled leave, notification, and tenant commands. |
| `backend/database/migrations/` | Central migrations. |
| `backend/database/migrations/tenant/` | Tenant database migrations. |
| `backend/database/seeders/` | Tenant and RBAC seeders. |
| `backend/tests/` | Laravel tests. |
| `frontend/` | Angular frontend. |
| `frontend/package.json` | Angular dependencies/scripts. |
| `frontend/src/app/tenant-app/` | Tenant leave-management UI. |
| `frontend/src/app/tenant-app/utils/permissions.ts` | Native eLeave permission and role constants. |

## 7. HRIS and SRMS Integration Workflow

Current SRMS integration is contract-driven and non-breaking. SRMS exposes
HRIS-only routes under `/api/hris/v1/*`, while existing SRMS user routes remain
available for the native app.

### 7.1 Tenant Flow

1. User signs in through HRIS/Keycloak.
2. Core validates the token and extracts `tenant_id`.
3. Core calls Tenant Registry.
4. Tenant Registry returns `srms_schema` and `srms_slug`.
5. Core calls SRMS using:
   - Bearer user token, service token, or module token depending on endpoint.
   - HRIS metadata headers such as `X-HRIS-Tenant-Id`,
     `X-HRIS-User-Sub`, `X-HRIS-Role`, `X-Request-ID`.
6. SRMS resolves the native organization/schema and enforces native RBAC.
7. Core normalizes SRMS payloads for Portal pages.

### 7.2 SRMS APIs Used By HRIS

Core adapter currently expects or falls back across these route families:

- `GET /api/hris/v1/dashboard/summary`
- `GET /api/hris/v1/employees`
- `GET /api/hris/v1/employees/{employee_id}`
- `GET /api/hris/v1/employees/self/comprehensive`
- `GET /api/hris/v1/integration/tenants`
- `GET /api/hris/v1/integration/tenants/{tenant_id}/users`
- `POST /api/hris/v1/integration/tenants/{tenant_id}/users/provision`

Compatibility paths under `/api/hris/*` and older native paths are tried by the
adapter where safe.

### 7.3 SRMS SSO Handoff

For native SRMS workspace launch:

1. Portal requests `POST /modules/catalog/srms/handoff`.
2. Core derives the native SRMS URL from `SRMS_BASE_URL` and `srms_slug`.
3. Core signs a short-lived handoff token.
4. Portal iframe receives or launches the URL containing `hris_handoff`.
5. SRMS `/api/sso/bridge` validates the token, maps the user, creates an SRMS
   native session, and redirects to the SRMS callback.

Security properties:

- Token has TTL.
- Token audience is module-specific.
- Token includes tenant id, user identifiers, employee id, target route, `jti`.
- `automation_store.module_handoff_replay` prevents replay in production when
  `AUTOMATION_STORE_DATABASE_URL` is set.

## 8. Integrating eLeave, eAppraisal, and Other Modules

The integration pattern should be the same for every module.

### 8.1 Minimum Module Contract

Each module must provide:

- A stable module id such as `srms`, `eappraisal`, `eleave`.
- A Tenant Registry mapping field or launch resolver.
- Read APIs for summaries and user/self records needed by HRIS.
- Inventory APIs for tenants and users if the module is a source of users/RBAC.
- Provisioning APIs if HRIS may create shell accounts or JIT accounts.
- A native SSO bridge or handoff redeem endpoint for iframe/native launch.
- Native RBAC enforcement inside the module.
- Versioned HRIS-specific routes, preferably `/api/hris/v1/...`.

### 8.2 eAppraisal Integration

Current HRIS side:

- Core builds native URLs from `EAPPRAISAL_DOMAIN_TEMPLATE` and
  `eappraisal_subdomain`.
- Core can call `EAPPRAISAL_INTEGRATION_BASE_URL` for inventory.
- Core uses `eappraisal_client` and `HttpEappraisalAdapter` for appraisal
  summary, employee appraisals, my appraisals, tenant inventory, user inventory.
- eAppraisal has an HRIS provisioning endpoint in
  `modules/performance-appraisal/backend/app/apis/hris_integration_api.py`.
- eAppraisal tenant resolution is schema/subdomain based.
- Native eAppraisal RBAC uses organization roles and permissions.

Required for successful integration:

- Tenant Registry row has `eappraisal_subdomain`.
- eAppraisal exposes integration tenant inventory.
- eAppraisal exposes tenant user inventory.
- HRIS shared secret/service token are configured on both sides.
- Role mapping is defined for JIT provisioning where needed.
- eAppraisal module routes return stable payload fields or the Core adapter is
  updated when fields change.

### 8.3 eLeave Integration

Current HRIS side:

- Core builds native URLs from `ELEAVE_DOMAIN_TEMPLATE` and
  `eleave_subdomain`.
- Core calls eLeave summary/history through `HttpEleaveAdapter`.
- eLeave has central HRIS provisioning route:
  `/api/hris/v1/integration/tenants/{tenant_id}/users/provision`.
- eLeave tenant runtime uses Stancl Tenancy and tenant paths under `/{tenant}`.
- Native eLeave permissions include `viewStaff`, `applyForLeave`,
  `approveLeaves`, `recommendLeaves`, `manageRolesAndPermissions`, and others.

Required for successful integration:

- Tenant Registry row has `eleave_subdomain`.
- `ELEAVE_DOMAIN_TEMPLATE` is set in Core.
- `ELEAVE_HRIS_SHARED_SECRET` and optional service token match eLeave env.
- eLeave has tenant DB migrations and seeders run for target tenants.
- HRIS-facing read endpoints should be added for stable summary/history APIs if
  native routes change.
- To use eLeave as a source of users/RBAC, add tenant and user inventory
  endpoints. Current Core federated directory sync reads SRMS and eAppraisal
  inventory; eLeave currently has provisioning, not full inventory sync.

### 8.4 Adding A New Native HRIS Feature

For a native HRIS feature, not a federated module:

1. Add backend model/service/API under `apps/backend/hris-core-api/app/`.
2. Enforce tenant and role policy in the backend first.
3. Add typed client call in `apps/frontend/portal/src/api/hrisCoreClient.ts`.
4. Add page/component under `apps/frontend/portal/src/pages/` or
   `src/components/`.
5. Register route in `src/router.tsx` and navigation in `Sidebar.tsx`.
6. Add tests around authorization and tenant isolation.
7. Add env variables to the relevant `.env.example` files if needed.

### 8.5 Adding A New Federated Module

1. Add Tenant Registry mapping fields or a generic module configuration record.
2. Add a Core adapter interface implementation under
   `apps/backend/hris-core-api/app/adapters/`.
3. Add a client facade under `apps/backend/hris-core-api/app/clients/`.
4. Add module metadata to `MODULE_UI_METADATA` or a dynamic catalog source.
5. Add readiness checks in `module_readiness.py`.
6. Add handoff launch URL derivation in `module_launch.py`.
7. Add module-specific service auth in `modules.py` if it redeems handoff tokens.
8. Add portal route/page or use `ModuleWorkspacePage` and `ModuleFrame`.
9. Implement the iframe bridge protocol in the native app if it is embedded.
10. Add API contract docs and tests.

## 9. Multi-Tenant Authentication, Authorization, and Cross-Module Access

### 9.1 Current Identity Sources

Keycloak:

- Authenticates users.
- Issues tokens with `sub`, `preferred_username`, `email`, `tenant_id`, and
  roles.
- Holds global HRIS roles such as `hris:employee` and `hris:hr_manager`.

Tenant Registry:

- Resolves tenant-specific module routing and enablement.
- Does not store user passwords or module RBAC.

Automation Store:

- Stores canonical tenant snapshots.
- Stores `identity_mappings` by tenant, module, module user id, email,
  Keycloak subject, source, and confidence.
- Stores provisioning audit, probe history, drift snapshots, tenant links,
  handoff replay records, and tenant runtime settings.

Native modules:

- Store local users, roles, and permissions.
- Enforce tenant-specific fine-grained RBAC.

First-setup migration and Keycloak activation are documented in
`docs/ops/tenant-identity-migration-keycloak.md`. Use that runbook before
running bulk migration, welcome-email delivery, or password reset operations.

### 9.2 Effective Role Resolution In HRIS

Core role priority:

1. `hris:super_admin`
2. `hris:tenant_admin`
3. `hris:hr_manager`
4. `hris:line_manager`
5. `hris:employee`

Core extracts roles from:

- Direct `roles` claim.
- `realm_access.roles`.
- `resource_access.*.roles`.
- `attributes.roles`.

The effective role controls HRIS shell navigation and Core API coarse checks.
It is not a replacement for native module RBAC.

### 9.3 Tenant Conflict Protection

When a user logs in:

1. Core validates the Keycloak token.
2. Core resolves `tenant_id` from token claims.
3. Core also checks persisted identity links by Keycloak subject, email, or
   username.
4. If token tenant and canonical identity tenant disagree, Core rejects with a
   tenant conflict.
5. Superadmins may use platform context, but tenant actions still require
   explicit tenant selection and policy.

This prevents a valid user from Tenant A being accidentally resolved into
Tenant B.

### 9.4 Resolving A User Across Modules

Canonical resolution order per module:

1. High-confidence `automation_store.identity_mappings`.
2. Module-specific token claim, such as `srms_employee_id` or
   `eappraisal_employee_id`.
3. Generic `employee_id` from the authenticated user.
4. Low-confidence username fallback only when
   `ALLOW_LOW_CONFIDENCE_IDENTITY_FALLBACK=true`.

Production should set `ALLOW_LOW_CONFIDENCE_IDENTITY_FALLBACK=false`.

### 9.5 Recommended Cross-Module Access Policy

Use this policy for a user who exists in one module but not another:

1. Authenticate through Keycloak. If the user only exists in a native module,
   sync/provision the user into Keycloak first.
2. Resolve the user's tenant through Keycloak `tenant_id` and Tenant Registry.
3. Import native module user inventory and RBAC into a canonical identity map.
4. Map native roles/permissions to global HRIS roles for shell access.
5. Keep native permissions as module entitlements for module-specific actions.
6. If the user needs access to another module where they do not exist, use JIT
   or scheduled provisioning to create a minimal native user in that module.
7. Persist the new module identity mapping.
8. Let the target module enforce its own RBAC after handoff or API access.

Never grant cross-module feature access only because another module has a user
with the same email. Tenant id, identity confidence, role mapping, and module
readiness must all match.

### 9.6 Example: Tenant A eLeave User Logs Into HRIS

Desired behavior:

- User exists in Tenant A in eLeave.
- User logs into HRIS.
- User should see eLeave features based on eLeave role/permissions.
- User may see eAppraisal, SRMS, or HRIS native features if policy allows.
- User does not already exist in eAppraisal or SRMS.

Secure implementation:

1. Add eLeave tenant user inventory endpoint:

```text
GET /api/hris/v1/integration/tenants/{tenant_id}/users
```

It should return at least:

```json
{
  "tenant_id": "Tenant A global id",
  "users": [
    {
      "user_id": "native eLeave user id",
      "staff_id": "native staff id",
      "email": "person@example.com",
      "username": "person@example.com",
      "role_name": "HR",
      "permissions": ["applyForLeave", "approveLeaves"]
    }
  ]
}
```

2. Extend `federated_directory_sync.py` to read eLeave inventory, the same way
   it currently reads SRMS and eAppraisal.
3. Map eLeave permissions to HRIS roles:

| eLeave role/permission | HRIS role |
| --- | --- |
| `Admin`, `manageRolesAndPermissions` | `hris:tenant_admin` |
| `HR`, `viewStaff`, `generateReport` | `hris:hr_manager` |
| `Director`, `recommendLeaves`, `approveLeaves` | `hris:line_manager` |
| `Normal`, `applyForLeave`, `viewMyLeaves` | `hris:employee` |

4. Provision or update Keycloak user:

- Use deterministic tenant-scoped usernames to avoid cross-tenant collisions:
  `email__tenantcode`.
- Set `tenant_id` claim.
- Assign global HRIS roles based on mapped native role/permissions.

5. Persist mappings:

```text
tenant_id=Tenant A
module_name=eleave
module_user_id=<eLeave staff/user id>
email=person@example.com
keycloak_sub=<Keycloak subject>
source=federated_directory
confidence=high
```

6. For access to eAppraisal/SRMS where the user does not exist:

- If access is policy-approved, JIT provision a shell user into the target
  module.
- Use tenant-scoped role mapping:
  - eLeave Normal -> eAppraisal STAFF, SRMS self-service user
  - eLeave HR -> eAppraisal HUMAN RESOURCE, SRMS HR/manager role
  - eLeave Director -> eAppraisal supervisor/manager role, SRMS line manager
- Persist identity mapping for the target module after provisioning.

7. On portal render:

- `/me` returns Keycloak identity, tenant, enabled modules, and identity map.
- `/modules/catalog` returns module visibility/readiness.
- Module pages call readiness checks before showing native actions.
- Handoff only occurs when module is enabled, tenant mapping is active, and
  native launch policy passes.

Current gap:

- Core currently has SRMS and eAppraisal inventory flows. eLeave has a
  provisioning endpoint, but not a complete inventory source in Core. To fully
  support "eLeave-only user becomes HRIS user and gains policy-approved access
  elsewhere", add eLeave inventory sync and role mapping as described above.

### 9.7 Tenant-Specific RBAC Mapping

Use tenant-scoped mappings rather than one global mapping for all tenants.
Different organizations may use different role names for the same function.

Store overrides in automation store runtime settings through `jit_policy.py`:

```json
{
  "eappraisal_role_name": "STAFF",
  "eappraisal_role_id": "optional-native-role-id",
  "eleave_role_name": "Normal",
  "eappraisal_fallback_role_name": "STAFF",
  "eleave_fallback_role_name": "Normal"
}
```

Recommended rules:

- Global HRIS roles control HRIS shell and Core endpoints.
- Native module permissions control native module actions.
- Module write actions should be executed by native modules or explicit write
  adapters, not by blind HRIS-side mutation.
- HRIS may show a feature only if both HRIS role and module entitlement allow it.
- HRIS must hide or block module actions if identity is unresolved.

## 10. How Native Module Changes Affect HRIS

### 10.1 SRMS Changes That Automatically Appear In HRIS

These changes flow through without HRIS code changes:

- Data changes behind existing SRMS endpoints.
- New employees, departments, branches, or profile fields that reuse existing
  field names already normalized by `HttpSrmsAdapter`.
- Native SRMS UI changes inside the iframe/native workspace, as long as launch
  URL, handoff bridge, and postMessage bridge remain compatible.
- Additional tenant/user inventory rows returned by existing inventory contract.

### 10.2 SRMS Changes That Require HRIS Changes

Manual HRIS changes are required when SRMS changes:

- Endpoint paths outside the adapter's candidate paths.
- Authentication headers, service secrets, token format, or handoff bridge.
- Response envelope/encryption/signature format.
- Field names required by Portal pages.
- New workflow states or actions that should appear in HRIS.
- New module permissions that must map to HRIS roles or module entitlements.
- New pages that should be exposed in HRIS navigation or native workspace.
- New write capabilities that need Core API contracts or adapter calls.

The same rule applies to eAppraisal, eLeave, and future modules: changes inside
an existing stable contract flow through; contract changes require HRIS adapter,
client, or portal updates.

### 10.3 Best Practice For Module Teams

When adding native module features:

1. Keep old endpoints backward compatible.
2. Add versioned HRIS endpoints under `/api/hris/v1`.
3. Return additive fields before removing old fields.
4. Update the relevant file in `docs/api-contracts/`.
5. Add or update Core adapter tests.
6. Add module readiness checks if the feature affects launch/access.
7. Add portal UI only when the feature is intended to be visible in HRIS.

## 11. Business Logic Summary

Core HRIS business logic:

- Authenticate users through Keycloak.
- Resolve tenant and active module configuration.
- Aggregate dashboard data from SRMS, eAppraisal, and eLeave.
- Provide employee roster, team roster, employee 360, and profile views.
- Build role-aware quick actions and navigation.
- Build module catalog with visibility, readiness, launch policy, and
  capability metadata.
- Issue and redeem module handoff tokens.
- Sync tenant/user inventories and identity mappings.
- Detect drift between Tenant Registry, modules, and Keycloak.
- Provision missing users when configured and audited.
- Fail closed for production unsafe settings.

SRMS business logic exposed to HRIS:

- Organization/tenant inventory.
- Employee list/details/self profile.
- Dashboard summary.
- Tenant user inventory and RBAC enrichment.
- Provision tenant user.
- Native SSO bridge/session creation.

eAppraisal business logic exposed to HRIS:

- Appraisal summary.
- Employee appraisal history.
- My appraisal cycles/sections/goals.
- Tenant and user inventory.
- Provision tenant staff user when service auth is configured.

eLeave business logic exposed to HRIS:

- Leave summary/history through adapter-supported endpoints.
- Tenant staff, leave, roles, permissions, reports in native app.
- HRIS service provisioning endpoint.
- Native role/permission set for leave workflows.

## 12. Verification Checklist

Before handing off a setup or integration change:

```powershell
git status --short
```

Core tests:

```powershell
Set-Location apps/backend/hris-core-api
python -m pytest
Set-Location ../../..
```

Gateway tests:

```powershell
Set-Location apps/backend/gateway
python -m pytest
Set-Location ../../..
```

Portal build:

```powershell
Set-Location apps/frontend/portal
npm run build
Set-Location ../../..
```

Docker config validation:

```powershell
docker compose --env-file .env.docker.development -f docker-compose.yml -f docker-compose.keycloak.yml config -q
```

Runtime health:

```powershell
curl http://127.0.0.1:8001/health
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8010/health
```

Integration smoke:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\test_backend_apis.ps1
```

## 13. Staging And Commit Guidance

Stage only files that are intentional and production-safe.

For this documentation/update task, the production-safe files are:

```powershell
git add docs/PROJECT_SETUP_AND_INTEGRATION_GUIDE.md docker-compose.yml docker-compose.keycloak.yml scripts/prepare_docker_dev_env.py
```

For the identity migration documentation/config update, also stage:

```powershell
git add docs/ops/tenant-identity-migration-keycloak.md docker-compose.yml
```

Do not stage:

- Local `.env` files.
- `logs/`.
- Keycloak backups containing real identities/secrets.
- Generated credentials under `apps/backend/hris-core-api/data/exports/`.
- Native module historical docs unless a native module task explicitly changes them.
- Unrelated app moves or deletes already present in the working tree.
