# HRIS Consolidated Integration Readiness and Environment Matrix

This document answers two things:

1. Current completion status across HRIS + production modules.
2. What is still required, including environment variable values/expected values for dev, staging, test, and production.

Scope note:

- `modules/` in this workspace is analysis/reference only.
- Module implementation must be completed in each module's own production repository by the module team.

---

## 1) Are We Done?

Short answer: **No, not fully complete yet**.

### 1.1 Current status

- **HRIS Core (backend):** largely complete for orchestration, drift scans, sync APIs, auto-sync loop, and controlled auto-provision scaffold.
- **Portal (frontend):** integrated against HRIS Core endpoints; still requires full environment-by-environment end-to-end validation.
- **SRMS:** farthest along; HRIS-only routes and compatibility aliases are implemented in analyzed code and should be tested in SRMS production repo deployment.
- **eAppraisal:** pending module-team implementation of inventory/provision endpoints in production repo.
- **eLeave:** pending module-team implementation of inventory/provision endpoints in production repo.

### 1.2 Definition of done (for this phase)

Done means all are true:

- HRIS Core in production mode with strict env guards.
- SRMS/eAppraisal/eLeave each expose required `/api/hris/v1/*` endpoints.
- Cross-module tenant drift = no unresolved critical mismatches.
- Cross-module user drift = no unresolved create-missing gaps.
- Auto-provision dry-run reviewed and then enabled (non-dry-run) with audits.
- End-to-end tests pass in dev, staging, and pre-prod.

---

## 2) What Still Needs To Be Done

## 2.1 HRIS Core API (owner: HRIS platform team)

- Enable strict production env profile:
  - `APP_ENV=production`
  - `AUTH_MODE=keycloak`
  - `USE_STUB_DATA=false`
  - `TENANT_REGISTRY_ALLOW_FALLBACK=false`
  - `AUTH_COOKIE_SECURE=true`
- Validate all module connectivity with real credentials and production URLs.
- Run and monitor:
  - `/integrations/synchronization/drift`
  - `/integrations/synchronization/users/drift`
  - reconcile plan endpoints
- Run auto-provision in dry-run first, review JSONL audit output, then enable write mode.

## 2.2 SRMS module team

- Confirm production repo includes:
  - `/api/hris/v1/*` routes
  - compatibility aliases `/api/hris/*`
  - router registration in startup
  - required header validation + optional shared secret
- Implement/verify inventory and provisioning routes if missing:
  - `GET /api/hris/v1/integration/tenants`
  - `GET /api/hris/v1/integration/tenants/{tenant_id}/users`
  - `POST /api/hris/v1/integration/tenants/{tenant_id}/users/provision`
- Validate strict source-validation posture for protected routes.

## 2.3 eAppraisal module team

- Implement required HRIS-only integration routes in production repo:
  - `GET /api/hris/v1/integration/tenants`
  - `GET /api/hris/v1/integration/tenants/{tenant_id}/users`
  - `POST /api/hris/v1/integration/tenants/{tenant_id}/users/provision` (idempotent)
- Apply header validation and standard envelope.
- Return normalized user identifiers (`employee_id`, `staff_id`, `email`, `tenant_id`, `is_active`).

## 2.4 eLeave module team

- Implement same inventory and provision routes as eAppraisal.
- Ensure tenant-path/subdomain routing remains compatible with HRIS adapters.
- Apply header validation middleware and response envelope.

## 2.5 Shared cross-module requirement

- Idempotent provisioning with `X-Idempotency-Key`.
- Fail-closed tenant isolation.
- Correlation/audit logging (`X-Request-ID`).
- No hardcoded secrets in code.

---

## 3) Required Module Endpoints (Target)

All modules should expose these in production repos:

- `GET /api/hris/v1/integration/tenants`
- `GET /api/hris/v1/integration/tenants/{tenant_id}/users`
- `POST /api/hris/v1/integration/tenants/{tenant_id}/users/provision`

Provision endpoint behavior:

- Idempotent create-or-confirm-existing.
- Accept duplicate idempotency key safely.
- Must not perform cross-tenant writes.
- Return stable envelope and audit metadata.

---

## 4) Environment Matrix (Dev / Staging / Test / Production)

Values below are recommended baselines; replace placeholders using your secrets manager.

## 4.1 HRIS Core API (`hris-core-api/.env`)

### Profile-level values

- **Dev**
  - `APP_ENV=development`
  - `AUTH_MODE=dev` or `keycloak` (dev realm)
  - `USE_STUB_DATA=true` for early local work, then `false` for integration testing
  - `TENANT_REGISTRY_ALLOW_FALLBACK=true`
  - `ENABLE_AUTO_SYNC_LOOP=false`
  - `ENABLE_AUTO_PROVISION=false`
- **Staging**
  - `APP_ENV=staging`
  - `AUTH_MODE=keycloak`
  - `USE_STUB_DATA=false`
  - `TENANT_REGISTRY_ALLOW_FALLBACK=false`
  - `ENABLE_AUTO_SYNC_LOOP=true`
  - `ENABLE_AUTO_PROVISION=true`
  - `AUTO_PROVISION_DRY_RUN=true`
- **Test (pre-prod integration test)**
  - `APP_ENV=test`
  - Same as staging; can enable shorter sync interval for testing
  - Keep provisioning dry-run unless explicit write test window
- **Production**
  - `APP_ENV=production`
  - `AUTH_MODE=keycloak`
  - `USE_STUB_DATA=false`
  - `TENANT_REGISTRY_ALLOW_FALLBACK=false`
  - `AUTH_COOKIE_SECURE=true`
  - `ENABLE_AUTO_SYNC_LOOP=true`
  - `ENABLE_AUTO_PROVISION=true`
  - `AUTO_PROVISION_DRY_RUN=false` only after sign-off

### Core variable expectations

- `KEYCLOAK_ISSUER=https://<keycloak-host>/realms/<realm>`
- `KEYCLOAK_JWKS_URL=https://<keycloak-host>/realms/<realm>/protocol/openid-connect/certs`
- `KEYCLOAK_AUDIENCE_HRIS_CORE=hris-core-api,hris-portal`
- `PORTAL_BASE_URL=https://<portal-host>`
- `CORS_ALLOWED_ORIGINS=https://<portal-host>`
- `TENANT_REGISTRY_BASE_URL=https://<tenant-registry-host>`
- `TENANT_REGISTRY_BASIC_AUTH_USERNAME=<service-user>`
- `TENANT_REGISTRY_BASIC_AUTH_PASSWORD=<secret>`
- `SRMS_BASE_URL=https://<srms-host>`
- `EAPPRAISAL_DOMAIN_TEMPLATE=https://appraisal.{subdomain}.<domain>`
- `ELEAVE_DOMAIN_TEMPLATE=https://{subdomain}.<domain>`
- `SRMS_HRIS_SHARED_SECRET=<shared-secret-if-enabled>`
- `HTTP_CLIENT_TIMEOUT_SECONDS=5..30` (typically `10`)

### Auto-sync / auto-provision variable expectations

- `ENABLE_AUTO_SYNC_LOOP=true|false`
- `AUTO_SYNC_INTERVAL_SECONDS=300` (staging can use `60`)
- `AUTO_SYNC_MAX_TENANTS=200` (adjust per tenant count)
- `AUTO_SYNC_MAX_USERS_PER_TENANT=200` (adjust by workload)
- `ENABLE_AUTO_PROVISION=true|false`
- `AUTO_PROVISION_DRY_RUN=true|false`
- `AUTO_PROVISION_ALLOWED_MODULES=eappraisal,eleave` (add `srms` only after SRMS provisioning endpoint is live)
- `AUTO_PROVISION_MAX_ACTIONS_PER_RUN=100`
- `AUTO_PROVISION_STOP_ON_ERROR=true`
- `AUTO_PROVISION_AUDIT_LOG_PATH=logs/auto_provision_audit.jsonl`
- `EAPPRAISAL_PROVISION_USER_PATH=/api/hris/v1/integration/tenants/{tenant_id}/users/provision`
- `ELEAVE_PROVISION_USER_PATH=/api/hris/v1/integration/tenants/{tenant_id}/users/provision`

---

## 4.2 Portal (`portal/.env`)

- **Dev**
  - `VITE_HRIS_CORE_API_BASE_URL=http://localhost:8000`
  - `VITE_AUTH_MODE=dev`
  - `VITE_PORTAL_DATA_MODE=api`
- **Staging/Test/Production**
  - `VITE_HRIS_CORE_API_BASE_URL=https://<hris-core-host>`
  - `VITE_AUTH_MODE=keycloak`
  - `VITE_PORTAL_DATA_MODE=api`
  - `VITE_DEV_REQUIRE_LOGIN=false`

---

## 4.3 SRMS module env (production repo)

Use SRMS env template in its repo (`env.example`) and enforce:

- `ENVIRONMENT=production`
- `DEBUG=False`
- real `SECRET_KEY`
- secure DB/Redis credentials
- secure mail provider credentials
- strict cookie and security options
- source validation enabled and strict in production

HRIS integration related (expected):

- `SRMS_HRIS_SHARED_SECRET=<shared-secret>` (if enforcing shared secret)
- strict request validation settings enabled in production
- route registration for HRIS integration routers

---

## 4.4 eAppraisal module env (production repo)

Expected baseline (based on Python backend structure):

- `ENVIRONMENT=production`
- `DEBUG=False`
- secure `SQLALCHEMY_DATABASE_URL`
- production CORS origins for portal/core only
- mail/sms/secrets from secret manager
- dedicated HRIS integration vars (to be added if absent):
  - `EAPPRAISAL_HRIS_SHARED_SECRET=<shared-secret>`
  - `EAPPRAISAL_ENABLE_HRIS_INTEGRATION=true`

Must expose integration inventory/provision endpoints before HRIS write provisioning.

---

## 4.5 eLeave module env (production repo)

Expected Laravel production baseline:

- `APP_ENV=production`
- `APP_DEBUG=false`
- secure `APP_KEY`
- production `APP_URL`, `FRONTEND_URL`
- secure DB/Redis/mail credentials
- queue/session configured for production stability

Recommended HRIS vars to add in eLeave repo:

- `ELEAVE_HRIS_SHARED_SECRET=<shared-secret>`
- `ELEAVE_ENABLE_HRIS_INTEGRATION=true`

Must expose integration inventory/provision endpoints before HRIS write provisioning.

---

## 5) Testing Plan By Environment

## 5.1 Dev

- Validate all `/integrations/synchronization/*` endpoints return expected schema.
- Run `users/drift` and tenant reconcile plans.
- Keep provisioning in dry-run.

## 5.2 Staging

- Test with real module backends and realistic tenant data.
- Verify audit logs for provisioning actions.
- Validate idempotency by replaying same request.

## 5.3 Test / Pre-prod

- Full regression:
  - tenant drift
  - user drift
  - auto-sync loop stability
  - rollback/compensation drill

## 5.4 Production

- Enable non-dry-run provisioning only after change approval.
- Monitor audit log and alerts continuously.
- Keep stop-on-error enabled.

---

## 6) Security and Reliability Notes

- Never commit secrets or live tokens in `.env` files.
- Rotate any accidentally exposed credentials immediately.
- Use secret manager injection for staging/production.
- Keep auto-provision bounded and idempotent.
- Prefer additive provisioning, not destructive sync.

---

## 7) Related Documents

- `docs/ops/env-variables.md`
- `docs/api-contracts/srms-integration-contract.md`
- `docs/api-contracts/eappraisal-integration-contract.md`
- `docs/api-contracts/eleave-integration-contract.md`
- `docs/api-contracts/production-module-team-integration-guide.md`
