# HRIS Platform Setup, Structure, Integration, and RBAC Guide

Last updated: 2026-08-12

Code audit baseline: working tree inspected on 2026-08-12. Statements marked
**Implemented** are backed by the current source and, where applicable, tests.
**Partial** means useful code exists but one or more production controls or
module contracts are missing. **Planned** describes the recommended target and
must not be treated as a currently available feature.

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

Plain-language terms used in this guide:

| Term | Simple meaning |
| --- | --- |
| Tenant | One organization's protected HR workspace. |
| Canonical tenant ID | The main HRIS UUID for that workspace. |
| Native tenant ID | The ID used by SRMS, eAppraisal, or eLeave for the same workspace. |
| Projection or tenant link | A checked link between the HRIS tenant and a native module tenant. |
| Principal | One signed-in person, identified by the identity provider's issuer and subject. |
| Membership | Permission for a principal to use one tenant. |
| Federation | Trusting an identity provider to sign users in to HRIS. |
| Provisioning | Creating, updating, disabling, or linking user accounts. |
| SCIM | A standard format and API for exchanging users and groups. |
| Idempotent | Safe to retry without creating the same tenant or user twice. |
| RLS | Database rules that block one tenant from reading another tenant's rows. |
| Handoff | A short-lived, one-time way to open a native module for a signed-in user. |

## 1. Runtime Architecture

The normal request path is:

```text
Browser
  -> Portal (React/Vite)
  -> HRIS Core API (FastAPI BFF)
  -> Tenant Registry (FastAPI/Postgres)
  -> SRMS / eAppraisal / eLeave native APIs
```

Simple rules:

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

4. Provision or update the Keycloak user:

- Identify the person by the immutable `(issuer, subject)` pair and store each
  tenant relationship as a separate membership. Do not derive identity from an
  email address or encode tenant identity into a mutable email-based username.
- If the current realm configuration requires a unique username, generate an
  opaque, stable login name and keep native usernames/emails as aliases or
  profile attributes. A user with multiple tenant memberships remains one
  principal and selects an authorized, signed tenant context.
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

## 13. What Works Today (2026-08-12)

This table shows what works now and what still needs work. A route in the code
does not prove that every live module supports it.

| Area | Status | Current behavior and evidence | Production limitation |
| --- | --- | --- | --- |
| Keycloak browser SSO | Implemented | Core exposes `/auth/sso/start`, callback, session, refresh, and logout; tokens are validated in `app/core/auth.py`; secure-cookie and environment validation settings exist. | Production realm, SMTP, key rotation, client policy, MFA/AAL, and recovery procedures are deployment responsibilities. |
| Canonical tenant registry | Implemented | Registry stores opaque tenant UUIDs and module routing fields; Core resolves mappings through `tenant_registry_client.py`. | Registry uses internal Basic authentication and its shared tenant table is not protected by database RLS. Replace Basic auth for production service trust. |
| Native module integration | Partial | SRMS and eAppraisal adapters support inventory/read/provisioning paths; eLeave supports summary/history and a provisioning path. | Availability and payload compatibility still depend on each deployed native module; eLeave lacks complete inventory federation. |
| Portal module workspace | Implemented | Catalog, readiness, handoff, iframe workspace, capability context, and native routes are wired. | Native apps must enforce their own authorization and iframe/message-origin controls. |
| Tenant inventory | Partial | Automation Store has `native_tenant_inventory`; SRMS/eAppraisal imports and manual/global enrollment flows exist. | No standard SCIM endpoint, durable module outbox consumer, or complete eLeave inventory. Current import paths must not be allowed to auto-link on descriptive similarity. |
| Tenant claim/linking | Implemented first tranche | `/federation` supports inventory, projections, claims, five-minute challenge, native confirmation, rejection, different-superadmin approval, optimistic link versions, uniqueness, and append-only link events. | Native authority assertion is HS256 with a module shared secret; migrate to asymmetric signatures or mTLS-bound proof and add key rotation/revocation. No portal claim UI is present. |
| Canonical user directory | Partial | Federated snapshots, `(issuer, subject)` fields, module user mappings, confidence, enrollment jobs, drift, and Keycloak provisioning exist. | Current schema/workflows are not a complete SCIM 2.0 lifecycle; eLeave is not a full source; deprovisioning and group lifecycle need stronger contracts. |
| Enrollment jobs | Implemented first tranche | Preview/apply, status, retry, stale-job recovery, reconcile plans, provision-missing, password reset, welcome and identity sync endpoints exist. | Production queue isolation, bounded concurrency, dead-letter handling, idempotency across every module, and operator approval gates require validation. |
| Module handoff | Implemented | Short-lived, audience-bound JWTs, target-route constraints, host allowlist, `jti`, and Postgres replay claims are present. | HS256 expands secret exposure; use per-module asymmetric keys, strict single audience, sender constraints where feasible, and fail closed if replay storage is unavailable. |
| Tenant isolation | Partial | Token tenant-conflict checks, tenant-scoped API policy, native module tenant models, and explicit mappings exist. | No consistent request-wide tenant context middleware plus PostgreSQL `ENABLE/FORCE ROW LEVEL SECURITY` on every shared tenant table. Cache/object-store/search/queue isolation must be audited. |
| RBAC | Partial | HRIS coarse roles and native module fine-grained roles are separated; persona checks protect privileged endpoints. | Tenant-specific entitlement mapping, access reviews, separation of duties, and negative cross-tenant tests must be completed across all modules. |
| Observability/audit | Partial | Correlation IDs, link events, provisioning/email audit, probe history, drift snapshots, and operational docs exist. | Central immutable audit retention, tenant-scoped security alerts, SIEM export, redaction validation, and federation SLOs need deployment and testing. |
| SCIM 2.0 | Planned | Existing inventories and provisioning services are useful implementation inputs. | RFC 7643 schema discovery, `/Users`, `/Groups`, enterprise extension, lifecycle semantics, and RFC 7644 protocol behavior are not implemented. |

Verified on this audit:

```powershell
Set-Location apps/backend/hris-core-api
python -m pytest -q
# 76 passed
Set-Location ../../..
```

Run each Python service's tests from its own directory. Running the Core and
Gateway suites together from the repository root creates an import collision
because both services use a top-level package named `app`.

## 14. Production Federation and Onboarding Plan

### 14.1 Research used for this plan

This plan uses three main sources:

- [RFC 7643: SCIM Core Schema](https://www.rfc-editor.org/rfc/rfc7643.html),
  which defines portable `User`, `Group`, enterprise-user, schema discovery,
  attribute mutability, returned/uniqueness behavior, `externalId`, and privacy
  handling. RFC 7643 is a schema specification; implement the HTTP lifecycle
  with [RFC 7644](https://www.rfc-editor.org/rfc/rfc7644.html).
- [NIST SP 800-63C-4 federation requirements](https://pages.nist.gov/800-63-4/sp800-63c/Federation/),
  which require an RP to validate the expected issuer and assertion, associate
  it with an RP account, restrict/check audience, protect against injection and
  replay, securely link accounts, notify users of link changes, and define
  disable/termination behavior. The organization must select and document its
  target Federation Assurance Level (FAL); this guide does not claim a FAL.
- [OWASP Multi-Tenant Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Multi_Tenant_Security_Cheat_Sheet.html),
  which recommends deriving tenant context from verified identity, validating
  it early, propagating it through all layers, never trusting a raw client
  tenant ID, using defense-in-depth isolation such as PostgreSQL RLS, and
  tenant-aware caches, files, logs, rate limits, and tests.

Rules for this platform:

1. Authentication federation (OIDC/Keycloak), user provisioning (SCIM), tenant
   federation, and authorization are separate concerns. Success in one never
   implicitly grants another.
2. The stable person key is `(issuer, subject)`. Email, username, employee
   number, name, domain, and phone are attributes, not linking authority.
3. The stable tenant key is the HRIS canonical UUID. Every native module keeps
   its immutable native tenant ID; the verified projection joins the two.
4. SCIM `externalId` is assigned by the provisioning client and scoped to that
   client. Use an opaque HRIS user/membership identifier, not email. A module's
   own resource `id` remains module-owned.
5. Tenant membership is explicit and many-to-many. A person may belong to more
   than one tenant and must select an authorized tenant context; a token or
   server session binds that context for each request.
6. Descriptive tenant/user matching produces review candidates only. It never
   creates an active link or membership.
7. Provisioning is a durable, idempotent saga. Each external write uses an
   operation ID/idempotency key; retries resume instead of duplicating tenants
   or users.
8. Federation assertions and module handoffs have one intended audience,
   issuer/key validation, short expiry, nonce/state or `jti`, replay rejection,
   and an allowlisted destination. Prefer asymmetric signatures with keys per
   issuer and automated rotation over shared HS256 secrets.

### 14.2 Main records and who owns them

Use these main records. Each record has one clear job:

| Record | Required identity and security fields |
| --- | --- |
| `canonical_tenant` | UUID, normalized unique label/code, status, workforce-boundary description, residency/tier, created/approved metadata. |
| `native_tenant_inventory` | Module, immutable native ID, reported canonical UUID, routing key, display metadata, source version, last seen, status; never authoritative merely because names match. |
| `tenant_module_projection` | Canonical UUID, module, native ID, state, link version, proof/audit reference, last verified; unique on both `(tenant,module)` and `(module,native_id)`. |
| `principal` | Internal opaque ID plus unique `(issuer, subject)`; no tenant embedded in the principal key. |
| `tenant_membership` | Principal, canonical tenant, lifecycle state, source, start/end time, assurance/proof, version. |
| `module_identity` | Membership/principal, module, immutable module user ID, SCIM resource ID/external ID, version, sync state. |
| `entitlement` | Tenant, module, native role/permission, mapped HRIS capability, provenance, approver, effective/expiry times. |
| `federation_connection` | Tenant/IdP, issuer, discovery/JWKS metadata, client IDs, allowed algorithms, audiences, FAL/AAL policy, claim mapping, key state. Secrets belong in a secrets manager. |
| `onboarding_operation` | Operation/idempotency ID, desired state, per-step result, retry count, next attempt, actor, correlation ID, timestamps. |
| `audit_event` | Actor, tenant, subject, action, before/after references, result, source IP/client, correlation ID, tamper-evident timestamp; secrets and raw tokens excluded. |

Place all shared-table tenant records behind PostgreSQL RLS. Application code
must set a transaction-local tenant value after validating membership, and
database roles used by the application must not have `BYPASSRLS`; apply
`FORCE ROW LEVEL SECURITY` so table owners do not silently bypass policies.
Platform-wide jobs use a separate, tightly controlled service role and must
explicitly enumerate tenants.

### 14.3 New tenant onboarding

1. A superadmin creates a draft workforce boundary and selects modules,
   identity source, regions, retention, data classification, and tenant admins.
2. Core normalizes the label, enforces database uniqueness, generates the
   canonical UUID and onboarding operation ID, and records an audit event.
3. A second authorized operator approves high-impact production onboarding.
4. Core creates each native tenant with the canonical UUID, a per-module
   idempotency key, authenticated service identity, and explicit contract
   version. Each module persists the UUID and returns its immutable native ID.
5. Core verifies the returned identity, writes the projection, and exposes only
   `verified` modules. Partial failures remain retryable without undoing valid
   projections.
6. Configure the tenant's IdP through reviewed OIDC/SAML metadata. Pin expected
   issuer, client, redirect URIs, algorithms, keys, audience and claim mapping;
   test signed login, logout, key rollover and break-glass recovery.
7. Create the SCIM connection using a tenant-scoped OAuth client or mTLS
   identity with least-privilege scopes. Discover `/ServiceProviderConfig`,
   `/ResourceTypes`, and `/Schemas`; refuse unsupported mandatory features.
8. Run SCIM import in preview: validate schemas, unique `externalId`, duplicate
   candidates, manager/group references, required attributes and tenant scope.
9. Approve and run bounded batches. Upsert principals, memberships, module
   identities and groups idempotently; no password import. New accounts start
   with minimum access until entitlement policy approves more.
10. Reconcile counts and hashes, sample users, run negative tenant-isolation
    tests, verify login/handoff and disable flows, then activate the tenant.
11. Notify tenant administrators and users of account/link activation as policy
    requires. Store evidence, not credentials, in the audit trail.

### 14.4 Existing tenant and user migration

1. Inventory native tenants and users read-only with immutable IDs, versions,
   status, roles and source timestamps.
2. Put unlinked native tenants in `unclaimed`. Candidate scores may assist
   review but never authorize a link.
3. Claim the exact native tenant using a short-lived proof bound to claim ID,
   canonical UUID, module, native ID, action, audience, issuer, nonce/`jti`, and
   expiry. A different superadmin approves it.
4. Resolve users first by an existing verified `(issuer, subject)` or approved
   immutable module mapping. If resolution depends on attributes, require a
   reviewed, uniquely resolving attribute set and do not auto-merge ambiguous
   records.
5. Create memberships independently per tenant. Never move a person between
   tenants because their email/domain changed.
6. Preview role mapping and privileged grants. Require explicit approval for
   tenant admin, HR, payroll, security, and bulk-export privileges.
7. Apply in resumable batches and preserve native permission provenance. Do not
   overwrite module-specific direct permissions with coarse Keycloak roles.
8. Reconcile active, disabled, suspended, and terminated users. A SCIM
   `active=false` disables access promptly; deletion follows legal retention
   policy rather than immediately erasing regulated HR records.
9. Notify subscribers when federated identifiers are linked/unlinked and when
   accounts are disabled or terminated, subject to incident-safety policy.
10. Complete dual-run monitoring, then remove legacy authentication and broad
    migration credentials.

### 14.5 Developer case scenarios

These examples show how the rules should work in code.

#### Scenario A: a new customer needs all three modules

Company A has no HRIS, SRMS, eAppraisal, or eLeave records.

1. A superadmin creates Company A in HRIS.
2. HRIS creates canonical tenant UUID `C1` and operation ID `O1`.
3. HRIS calls each module with `C1` and a separate idempotency key.
4. The modules return native tenant IDs `S1`, `A1`, and `L1`.
5. HRIS stores three verified links: `C1 -> S1`, `C1 -> A1`, and `C1 -> L1`.
6. The portal shows a module only after its link is verified.

If eLeave fails, HRIS keeps the successful SRMS and eAppraisal links. A retry
uses the same operation and idempotency key, so it does not create duplicates.

#### Scenario B: two modules contain tenants with the same name

SRMS and eAppraisal both contain a tenant named `Central Services`, but neither
record has a canonical HRIS UUID.

1. Inventory adds both records as `unclaimed`.
2. HRIS may show them as possible matches.
3. HRIS must not link them by name, email domain, logo, or contact person.
4. An administrator proves control of the exact native tenant.
5. A different superadmin approves the link.

The key lesson is simple: similar data helps people search; it does not prove
that two tenant records are the same customer.

#### Scenario C: an existing SRMS user is added to HRIS

Ama already has SRMS user ID `U77` in verified tenant `C1`.

1. The sync job reads `U77` from the SRMS inventory.
2. HRIS looks for a verified module mapping or Keycloak `(issuer, subject)`.
3. It does not merge Ama with another user only because the emails match.
4. HRIS creates or links the Keycloak principal and creates membership in `C1`.
5. The module identity record links the membership to SRMS user `U77`.
6. Ama receives only the approved starting access.

#### Scenario D: one person works for two tenants

Kojo works for Company A and Company B.

1. Kojo keeps one principal identified by `(issuer, subject)`.
2. HRIS stores two memberships: one for `C1` and one for `C2`.
3. Kojo chooses a tenant after login.
4. The server checks that membership and creates a signed tenant context.
5. Switching tenants clears cached page data and creates a new context.

The browser must never change tenant context by sending an unchecked
`X-Tenant-Id` header or query parameter.

#### Scenario E: a user leaves the organization

Efua leaves Company A but HR records must be retained.

1. The source directory sends `active=false`, or an approved administrator
   starts the disable action.
2. HRIS disables the `C1` membership and revokes active sessions.
3. Module access is removed through an idempotent job.
4. Audit and required HR records remain under the retention policy.
5. An older replayed event cannot reactivate the account because version and
   tombstone checks reject it.

#### Scenario F: a module is unavailable during onboarding

SRMS is down while a tenant is being created.

1. The onboarding operation records SRMS as `failed_retryable`.
2. The portal shows the failed step and the operation ID.
3. A worker retries with backoff and the original idempotency key.
4. Other verified modules remain available.
5. After the retry limit, the item moves to a dead-letter/manual-review state.

#### Scenario G: a forged tenant request

A valid Company A user changes a URL to contain Company B's tenant UUID.

1. Core derives the active tenant from the verified session, not the URL.
2. The membership check fails for Company B.
3. Database RLS also blocks Company B rows as a second layer.
4. Core returns a general `403` or `404` without confirming that the record
   exists and writes a tenant-security audit event.

#### Scenario H: SCIM sends the same request twice

An identity provider retries a user creation request after a timeout.

1. HRIS uses the tenant-scoped `externalId` and operation/idempotency data.
2. It finds the first result and returns that resource instead of creating a
   second user.
3. A conflicting payload is rejected and sent for review.
4. The audit log connects both requests with their correlation IDs.

### 14.6 SCIM profile for HRIS

Implement `/scim/v2` per RFC 7643 and RFC 7644:

- `/ServiceProviderConfig`, `/ResourceTypes`, and `/Schemas`.
- `/Users` with core attributes: `id`, client-scoped `externalId`, `userName`,
  `name`, `displayName`, `emails`, `phoneNumbers`, `active`, `groups`, and
  `meta` including `resourceType`, timestamps, version and location.
- Enterprise extension
  `urn:ietf:params:scim:schemas:extension:enterprise:2.0:User` for
  `employeeNumber`, organization/division/department/costCenter and manager.
- `/Groups` for membership/entitlement inputs. Group names do not directly
  become privileged roles; policy maps approved groups to capabilities.
- HRIS extension, versioned under an owned URN, for canonical membership ID and
  workforce metadata that cannot be represented by standard fields. Keep
  canonical tenant scope in the connection/server context and immutable server
  data; do not trust a caller-supplied tenant extension by itself.
- Strong ETags/`meta.version` and conditional updates to avoid lost writes;
  stable pagination/sorting; PATCH, filtering and bulk behavior only when
  advertised by service configuration.
- Attribute allowlists, mutability enforcement, canonical email handling,
  maximum sizes/counts, reference validation, and generic error responses that
  do not leak cross-tenant existence.

SCIM security baseline:

- TLS everywhere; tenant-scoped OAuth 2.0 client credentials with short-lived
  access tokens or mTLS; no long-lived Basic tokens in source or UI.
- Scope every query, cache key, idempotency key, rate-limit bucket, object path,
  queue message and audit event by canonical tenant.
- Never return passwords, password hashes, recovery answers, raw tokens, client
  secrets, or unrelated tenant attributes. Treat credentials as write-only if
  supported at all; prefer IdP-managed activation/reset.
- Rate limit per tenant and client, cap bulk payloads, validate content type and
  schema, protect against filter/query abuse, and use transactional outbox plus
  dead-letter/reconciliation for downstream propagation.
- Maintain tombstones/version watermarks sufficient to prevent deleted users
  from being resurrected by an older replayed event.

### 14.7 Login, tenant switch, and module handoff

For every federation response, Core/RP validates signature, allowed algorithm,
issuer, single intended audience, expiry/not-before, nonce/state and transaction
binding. It then looks up the unique `(issuer, subject)` principal and verifies
an active membership before creating a session.

The tenant switch endpoint must accept only a membership ID already authorized
for the principal, rotate the session/CSRF token, and issue a new signed context.
Raw `tenant_id` headers, query parameters, subdomains, origins, emails and
module-returned tenant fields cannot override it. Downstream calls include the
canonical tenant and exact native projection derived server-side.

Module handoffs should use authorization-code-style, single-use redemption
where modules can support it. If a JWT remains necessary, use asymmetric
module-specific signing keys, one audience, five minutes or less, `jti`, exact
tenant/native projection, subject, target route and purpose. Redeem server to
server, reject replay atomically, and never place reusable bearer credentials
in URLs, browser storage, referrers or logs.

### 14.8 Security and operations checklist

- Validate tenant context immediately after authentication and membership
  resolution; make missing context a hard failure for tenant data paths.
- Apply RLS and composite `(tenant_id, id)` keys/foreign keys to shared tables.
- Prefix cache keys, object storage paths, search indexes and queue topics with
  a validated tenant ID; prevent tenant-controlled path traversal.
- Use least-privilege database/service identities per workload and separate
  privileged platform jobs from tenant requests.
- Encrypt in transit and at rest; keep tenant/client secrets in a managed secret
  store; rotate keys with overlapping verification windows and revocation.
- Redact HR data, tokens and secrets from logs; include tenant, actor, subject,
  decision, correlation ID and source in security audit events.
- Monitor cross-tenant authorization failures, claim/link changes, privileged
  grants, bulk export, SCIM spikes, replay, key failures and reconciliation drift.
- Back up and restore with tenant-aware access controls. Test full recovery and,
  where promised, individual-tenant export/deletion/restoration.
- Pen-test IDOR/BOLA, forged tenant context, confused deputy, cache bleed,
  cross-tenant search, object-store paths, bulk SCIM, stale events, iframe
  origins, token replay and administrator separation of duties.

## 15. Backend Implementation Tasks

Priorities: P0 blocks production federation; P1 is required before broad tenant
rollout; P2 improves scale and operability. “Done” means code, migrations,
negative tests, metrics, runbooks and rollback behavior are present.

### P0 — trust boundary and tenant isolation

- **BE-P0-01: request tenant context.** Add middleware/dependency that derives
  principal and active membership from verified token/session, establishes one
  immutable request tenant context, and rejects attempts to override it.
- **BE-P0-02: database isolation.** Add `tenant_id` to all shared tenant data,
  composite constraints/foreign keys, PostgreSQL `ENABLE` and `FORCE RLS`,
  transaction-local context, non-bypass application roles, and migration tests.
- **BE-P0-03: service authentication.** Replace Registry Basic auth and module
  shared secrets with workload identity using mTLS or short-lived OAuth JWTs;
  pin issuer/audience/algorithm and implement key rotation/revocation.
- **BE-P0-04: harden claim proof.** Replace HS256 native confirmation with a
  module-specific asymmetric signature or mTLS-bound assertion; store key ID,
  proof version and replay record; expire abandoned claims automatically.
- **BE-P0-05: authoritative projection gate.** Make all catalog, API proxy,
  JIT, handoff and sync paths require a `verified` projection. Remove any
  auto-link behavior based on names/domains and quarantine conflicts.
- **BE-P0-06: canonical principal/membership schema.** Enforce unique
  `(issuer,subject)`, unique `(principal,tenant)` membership, versioned lifecycle
  states, module identities and explicit tenant selection. Migrate existing
  identity mappings without email-based merges.
- **BE-P0-07: federation validation policy.** Centralize issuer, key, algorithm,
  audience, nonce/state, time-skew, replay and RP-account association checks;
  add negative tests for injection and cross-client replay.
- **BE-P0-08: secrets and logs.** Remove/rotate any generated credentials or
  identity exports from deployable artifacts, prevent token/PII logging, and
  integrate a production secret manager.

### P0 — lifecycle correctness

- **BE-P0-09: durable onboarding saga.** Persist state before external calls;
  use idempotency keys, optimistic versions, bounded retry/backoff, dead-letter
  state, compensation/manual recovery, and per-step audit evidence.
- **BE-P0-10: deprovisioning.** Define disable, suspend, reactivate, unlink and
  terminate semantics across Keycloak and modules. Revoke sessions promptly,
  preserve records per retention policy, notify users, and block stale replay.
- **BE-P0-11: eLeave parity.** Implement tenant and user inventory, immutable
  identifiers, version/cursor, canonical UUID persistence, provisioning
  idempotency, and native authority proof for eLeave.
- **BE-P0-12: privileged entitlement governance.** Make native-to-HRIS mappings
  tenant-scoped and versioned; require approval for privileged roles; never
  manufacture native authority from a coarse HRIS role.

### P1 — SCIM and reliable synchronization

- **BE-P1-01: SCIM discovery/schema.** Implement service configuration,
  resource types, schemas, Core User, Group and Enterprise User extension plus
  a minimal versioned HRIS extension.
- **BE-P1-02: SCIM protocol.** Implement tenant-scoped `/Users` and `/Groups`
  GET/POST/PUT/PATCH/delete-or-deactivate, filtering, pagination, ETags,
  conditional writes and RFC-compliant errors; advertise only supported
  features.
- **BE-P1-03: SCIM authorization.** Issue one least-privilege client per tenant
  connection, support credential rotation/revocation, enforce attribute/scope
  allowlists, and add per-client/tenant rate and bulk limits.
- **BE-P1-04: event delivery.** Add transactional outbox at each module,
  authenticated consumers, idempotent event inbox, ordered version handling,
  tombstones and a dead-letter workflow.
- **BE-P1-05: reconciliation.** Support incremental cursor scans every 5–15
  minutes and daily full reconciliation as operational defaults, with manual
  scan, lag/drift metrics and no automatic identity/link approval.
- **BE-P1-06: migration tooling.** Provide preview/diff, duplicate quarantine,
  resumable bounded batches, dry-run export, approvals, checksums/counts and
  rollback/disable procedures. Never migrate password hashes.

### P1/P2 — platform hardening and scale

- **BE-P1-07:** Tenant-scope caches, rate limits, search, files, media, queues,
  metrics and error messages; add automated cross-tenant bleed tests.
- **BE-P1-08:** Move handoff to single-use server-side code redemption or
  asymmetric JWTs; require replay-store health and verify iframe origins/CSP.
- **BE-P1-09:** Centralize tamper-evident audit events and SIEM export with
  retention, redaction, alerting and tenant/admin access policy.
- **BE-P1-10:** Add onboarding/federation SLOs: queue age, completion latency,
  failure/retry/dead-letter rate, reconciliation lag, drift, replay and auth
  failure metrics.
- **BE-P2-01:** Replace module-specific tenant columns with a versioned generic
  module projection/configuration model while maintaining compatible APIs.
- **BE-P2-02:** Add pairwise pseudonymous subject support per RP where privacy
  risk warrants it; protect the correlation map as subscriber information.
- **BE-P2-03:** Add chaos/recovery tests for IdP/module outage, lost events,
  duplicate delivery, key rollover, partial onboarding and database restore.

## 16. Frontend Implementation Tasks

The frontend displays server decisions; it must never become an authorization
or tenant-routing authority.

### P0 — safe administrator and subscriber flows

- **FE-P0-01: onboarding wizard.** Build draft → review → approve → provision →
  verify → activate steps with module/IdP/SCIM readiness, per-step status,
  idempotent retry and no exposure of client secrets or temporary passwords.
- **FE-P0-02: inventory and claim console.** Show immutable native IDs, module,
  routing data, last seen, conflicts and candidate evidence distinctly. Require
  exact-record confirmation, reason, fresh authentication and a different
  approver; never label a similarity candidate “matched”.
- **FE-P0-03: tenant switcher.** List only server-returned active memberships;
  switch through a protected endpoint, rotate session state, clear tenant
  caches, reload capabilities, and show the active tenant persistently.
- **FE-P0-04: lifecycle UI.** Provide preview and confirmation for suspend,
  deactivate, unlink, reactivate and terminate; explain module impact,
  retention and notification behavior; require step-up auth for destructive or
  privileged actions.
- **FE-P0-05: secure error states.** Use generic unauthorized/not-found messages
  that do not reveal another tenant's resources. Correlation IDs may be shown
  for support; tokens, proofs and secrets must never be rendered or logged.
- **FE-P0-06: projection gating.** Render module links only from server catalog
  state; visually distinguish provisioning, unclaimed, verification pending,
  verified, conflict, suspended and failed-retryable states.

### P1 — SCIM, migration and governance UX

- **FE-P1-01: identity connection setup.** Accept metadata/connection details,
  display issuer/audience/redirect/scopes and key expiry, send secrets directly
  to the secure backend endpoint, and never read them back.
- **FE-P1-02: SCIM preview.** Present counts and actionable categories:
  create/update/disable/no-op, duplicate/ambiguous, invalid required fields,
  missing manager/group, privileged grants and cross-tenant conflicts.
- **FE-P1-03: batch operations.** Show operation ID, progress, bounded failures,
  retries, dead letters and downloadable redacted reports. A refresh must resume
  observation rather than resubmit the job.
- **FE-P1-04: entitlement mapping.** Provide tenant-specific group/role mapping,
  least-privilege defaults, privileged warnings, effective/expiry dates,
  approval and change diff.
- **FE-P1-05: user identity view.** Show principal, tenant memberships, linked
  federated identifiers, module identities, lifecycle and provenance without
  implying that matching emails are the same person. Support secure link/unlink
  notices and recovery guidance.
- **FE-P1-06: audit and operations.** Add filterable tenant-scoped audit,
  onboarding health, reconciliation lag/drift and key-expiry views; enforce
  pagination and redaction server-side.

### P1/P2 — browser security, accessibility and testing

- **FE-P1-07:** Use BFF HttpOnly/Secure/SameSite cookies, CSRF tokens, strict CSP,
  frame ancestors and exact `postMessage` origin/source checks. Do not store
  bearer/SCIM/module tokens in local/session storage or URL state.
- **FE-P1-08:** Clear React Query/client caches and cancel in-flight requests on
  tenant change/logout; include tenant only as a cache partition label derived
  from authenticated server state, never as authorization evidence.
- **FE-P1-09:** Add unit/E2E negative tests for forged tenant IDs, stale tabs,
  back-button after switch, cross-tenant deep links, claim self-approval,
  duplicate submit, iframe message spoofing and expired sessions.
- **FE-P1-10:** Make wizard/status/error/approval experiences keyboard and screen
  reader accessible, with focus management, live progress and non-color-only
  state labels.
- **FE-P2-01:** Add just-in-time support diagnostics that export only redacted
  connection and correlation metadata, never identity payloads or secrets.

## 17. Production Acceptance Gates

Do not activate production federation until all applicable gates pass:

1. **Identity:** expected issuer/key/algorithm/audience/nonce/state/replay tests,
   unique `(issuer,subject)`, documented FAL/AAL and account recovery policy.
2. **Tenant:** verified immutable projections only, explicit memberships,
   request context validation, RLS, and negative cross-tenant API/database tests.
3. **Provisioning:** SCIM contract/conformance tests, idempotency, ETags,
   deactivate/reactivate/delete policy, group and manager cycle handling.
4. **Security:** least-privilege clients, key rotation/revocation, secret scan,
   CSP/CSRF/cookie/origin tests, BOLA/IDOR and confused-deputy penetration tests.
5. **Reliability:** retry/dead-letter/reconciliation, partial saga recovery,
   module/IdP outage, duplicate/out-of-order event and restore exercises.
6. **Privacy:** data minimization, attribute purpose/trust agreement, retention,
   user notices, redacted logs/exports and access review.
7. **Operations:** dashboards/alerts/runbooks/on-call ownership, support tooling,
   rollback, break glass, audit/SIEM retention and signed production approval.

## 18. Documentation Maintenance Rule

When federation code changes, update this guide's status matrix and the relevant
contract/runbook in the same pull request. Label future designs **Planned** and
do not move them to **Implemented** until migrations, production-safe defaults,
authorization, negative tenant-isolation tests and operational recovery are all
verified. Re-run Core, Gateway, Portal build, policy checks and module contract
audits separately and record exact results; never infer production readiness
from a single service's unit suite.
