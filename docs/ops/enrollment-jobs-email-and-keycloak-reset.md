# Enrollment Jobs, Email Diagnostics, and Keycloak Reset

## Operational model

Federated enrollment is a durable background job. API readiness never waits for
module user discovery, Keycloak writes, or SMTP delivery. PostgreSQL atomically
claims queued jobs with `FOR UPDATE SKIP LOCKED`, allowing the same workflow in a
local process, Docker Compose, or multiple Core replicas without duplicate job
claims.

For a global job, `ENROLLMENT_REFRESH_TENANT_INVENTORY=true` makes the worker
refresh SRMS and eAppraisal tenant inventories before it reads users. The two
legacy `ENABLE_STARTUP_*_TENANT_INVENTORY_IMPORT` flags should remain `false`:
they perform remote work in the API startup hook and are retained only for
backward compatibility. Tenant-specific jobs do not refresh the global tenant
inventory.

`FEDERATED_KEYCLOAK_SYNC_MAX_USERS_PER_RUN=0` means all discovered users. A
positive value is an operator-selected canary limit. Unlimited refers only to
directory size: the worker is serial and HTTP/SMTP calls retain timeouts and
bounded retries.

Recommended production configuration:

```env
STARTUP_FEDERATED_ENROLLMENT_MODE=discover
ENABLE_FEDERATED_KEYCLOAK_SYNC=true
FEDERATED_KEYCLOAK_SYNC_MAX_USERS_PER_RUN=0
ENROLLMENT_WORKER_ENABLED=true
ENROLLMENT_REFRESH_TENANT_INVENTORY=true
ENABLE_FEDERATED_KEYCLOAK_WELCOME_EMAIL=true
ENROLLMENT_EMAIL_MAX_ATTEMPTS=3
ENROLLMENT_EMAIL_RETRY_BASE_SECONDS=30
SMTP_VALIDATE_CERTS=true
```

Use `discover` first, inspect the job, then enqueue `apply` explicitly:

```http
POST /integrations/synchronization/enrollment/preview?max_users=0
GET  /integrations/synchronization/enrollment/jobs/{job_id}
POST /integrations/synchronization/enrollment/apply?max_users=0
```

All endpoints require `hris:super_admin`. `202` means queued, not completed.
Terminal statuses are:

- `completed`: discovery and enrollment finished without reported user/source errors.
- `completed_with_errors`: useful work completed, but one or more users or sources failed.
- `failed`: the worker crashed, or no users were found while upstream discovery reported errors.

The job `result_json.tenant_inventory_refresh` shows each module's tenant import.
`result_json.tenant_discovery` shows the per-tenant user endpoint status. A run
that processed zero users is not proof that the directory is empty; check these
two fields before treating it as successful.

## Required source-module contract

HRIS cannot infer users from a module database that exposes no integration API.
Every consolidated module must implement and authorize these service-to-service
operations (the versioned singular `integration` form is preferred):

```http
GET /api/hris/v1/integration/tenants
GET /api/hris/v1/integration/tenants/{module_native_tenant_id}/users?limit=2000
```

Tenant inventory responses must include stable tenant IDs plus reconciliation
hints (`code`, `name`, and slug/subdomain where applicable). User inventory rows
must include a stable user ID, email, active state, and native roles. The same
shared-secret/service-token configuration must be present at both HRIS and the
source module. `401/403` means authentication policy mismatch, `404` means the
contract is not deployed, and `422` normally means HRIS used a tenant identifier
or query shape the module does not accept. Fix the source contract or configure
`TENANT_RECONCILIATION_ALIASES_JSON`; do not provision around an unverified
tenant mapping.

At present, eLeave user inventory is explicitly reported as `unsupported` until
that module implements this contract. Such users cannot be automatically
enrolled from eLeave alone.

## Docker development commands

```powershell
python scripts/prepare_docker_dev_env.py
docker compose --env-file .env.docker.development -f docker-compose.yml -f docker-compose.keycloak.yml config -q
docker compose --env-file .env.docker.development -f docker-compose.yml -f docker-compose.keycloak.yml up -d --build --wait
docker compose --env-file .env.docker.development -f docker-compose.yml -f docker-compose.keycloak.yml ps
docker compose --env-file .env.docker.development -f docker-compose.yml -f docker-compose.keycloak.yml logs -f hris-core-api
```

Re-run the environment generator whenever
`apps/backend/hris-core-api/.env` changes. The generated file is ignored and
must never be committed. Docker service URLs use Compose DNS internally while
browser URLs remain on localhost.

## Invitation states

Each result distinguishes `new_account`, `existing_welcome_sent`,
`existing_no_welcome_record`, and `existing_welcome_failed_retry`. Failed or
skipped delivery rows are retryable; only `status=sent` suppresses another
welcome. Results also report tenant memberships and `multi_tenant`.

Keycloak does not expose a reliable historical last-login value in its normal
user representation. The result therefore reports `login_state=unknown`
instead of making an unsafe inference. A future authoritative login-event sink
can update that field without changing invitation semantics.

Existing accounts are never assigned a new password during reconciliation.
Their invitation directs them to the organization sign-in/reset flow. Automatic
password rotation remains disabled.

## Password-reset email diagnosis

The public password-reset endpoint always returns `202` to prevent account
enumeration. Authorized operators can inspect sanitized outcomes at:

```http
GET /debug/integrations/email-delivery-audit?purpose=password_reset
GET /debug/integrations/email-readiness
```

`accepted_by_keycloak` means Keycloak accepted the action-email request; final
inbox delivery remains the SMTP provider's responsibility. `failed` includes a
sanitized Keycloak HTTP/error category. Recipient addresses are stored only as
SHA-256 prefixes in this diagnostic table.

The readiness endpoint negotiates TLS and authenticates without sending a
message or returning SMTP credentials.

For Gmail, use an application password or managed SMTP relay; ordinary account
passwords are commonly rejected. Confirm the realm SMTP `from` address is
permitted by the Gmail account/relay, STARTTLS is enabled on port 587, and check
spam/quarantine and provider logs.

## Development logging

`APP_ENV=development` enables verbose sanitized logging. Correlation IDs,
tenant/job context, outcomes, and durations are printed. HTTP wire logging is
kept at INFO and values resembling tokens, cookies, passwords, and secrets are
redacted. Staging/production stay at INFO. Never enable credential exports or
disable TLS certificate validation in production.

## Destructive clean Keycloak reset

Back up/export the realm first. Stop Core or set
`ENROLLMENT_WORKER_ENABLED=false` so it cannot write while reset is underway.
The reset script refuses non-loopback targets unless `--allow-remote` is passed,
requires the realm name twice, reads the password only from the environment,
and removes the five seed users from the import unless `--keep-seed-users` is
explicitly selected.

PowerShell, whether Keycloak runs locally or in Docker with port 8080 exposed:

```powershell
$env:KEYCLOAK_ADMIN_PASSWORD = '<local-admin-password>'
python scripts/reset_keycloak_realm.py --realm hris-platform --confirm-realm hris-platform
Remove-Item Env:KEYCLOAK_ADMIN_PASSWORD
```

For a completely fresh enrollment, clear the matching HRIS enrollment state in
the same guarded operation:

```powershell
$env:KEYCLOAK_ADMIN_PASSWORD = '<local-admin-password>'
$env:AUTOMATION_STORE_DATABASE_URL = 'postgresql://<user>:<password>@localhost:5432/hris_tenant_registry'
python scripts/reset_keycloak_realm.py --realm hris-platform --confirm-realm hris-platform --reset-hris-enrollment-state
Remove-Item Env:KEYCLOAK_ADMIN_PASSWORD
Remove-Item Env:AUTOMATION_STORE_DATABASE_URL
```

Remote production reset is intentionally not a normal workflow. Restore from a
tested realm/database backup or run the guarded script only during an approved
maintenance window with `--allow-remote` and explicit secrets from a secure
secret manager.
