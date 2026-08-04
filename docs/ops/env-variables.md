# Environment variables (Beginner-friendly)

The **canonical source of truth** for “what env vars exist” is the example file next to each component:

- Portal: `apps/frontend/portal/.env.example`
- HRIS Core API: `apps/backend/hris-core-api/.env.example`
- Tenant Registry: `apps/backend/tenant-registry-service/.env.example`

This doc explains how to think about those variables without needing to already know the system.

---

## Safety rules (important)

- **Never commit real secrets** (passwords, client secrets, SMTP credentials).
- Prefer setting secrets in **CI/CD secret stores** or your **deployment environment**, not in repo files.
- For local work: copy the example file to a real `.env` and edit locally.

---

## Portal (`apps/frontend/portal/`)

See `apps/frontend/portal/.env.example`.

The Portal runs in your browser. It needs to know where the Core API is and which auth mode to use.

- **`VITE_HRIS_CORE_API_BASE_URL`**: Core API base URL (typical local: `http://localhost:8000`)
- **`VITE_AUTH_MODE`**: use `keycloak` for production-like development and deployed environments.
- **`VITE_PORTAL_DATA_MODE`**: use `api`; local mock datasets are not a product runtime path.
- **`VITE_DEV_DEFAULT_TENANT_ID`** / **`VITE_DEV_DEFAULT_EMPLOYEE_ID`**: legacy debug defaults only.

---

## HRIS Core API (`apps/backend/hris-core-api/`)

See `apps/backend/hris-core-api/.env.example`.

For Docker development, run `python scripts/prepare_docker_dev_env.py`. It maps
the local Core `.env` into the ignored root `.env.docker.development` file and
replaces localhost-only service addresses with Docker DNS names. Re-run it
after changing the Core `.env`; never commit the generated file.

Enrollment controls:

- `STARTUP_FEDERATED_ENROLLMENT_MODE`: `disabled`, `discover`, or `apply`;
  startup only queues the durable job.
- `ENROLLMENT_WORKER_ENABLED`: enables the durable enrollment worker.
- `ENROLLMENT_REFRESH_TENANT_INVENTORY`: refreshes SRMS/eAppraisal tenants
  inside global enrollment jobs before user discovery.
- `FEDERATED_KEYCLOAK_SYNC_MAX_USERS_PER_RUN`: `0` means all discovered users;
  a positive value is an explicit canary limit.
- Keep both `ENABLE_STARTUP_*_TENANT_INVENTORY_IMPORT` flags false in the normal
  workflow so remote module discovery never gates API readiness.

Think of Core API as a “translator and aggregator” for the Portal.

### Mode switches (first things to check)

- **`AUTH_MODE`**:
  - `keycloak`: validates Keycloak JWTs using JWKS (expected mode)
  - `dev`: limited debug mode for isolated diagnostics only
- **`USE_STUB_DATA`**:
  - `false`: required. Core calls Tenant Registry and real module integrations.
  - `true`: deprecated for product runtime; do not use for normal development.

### Keycloak (only when `AUTH_MODE=keycloak`)

- **`KEYCLOAK_ISSUER`**
- **`KEYCLOAK_JWKS_URL`**
- **`KEYCLOAK_AUDIENCE_HRIS_CORE`**
- **`KEYCLOAK_CLIENT_ID_PORTAL`** (used by the HRIS-native SSO flow)
- **`KEYCLOAK_CLIENT_SECRET_PORTAL`** (only if your Keycloak client is confidential)

### Tenant Registry (Core → Registry)

- **`TENANT_REGISTRY_BASE_URL`**
- **`TENANT_REGISTRY_BASIC_AUTH_USERNAME`**
- **`TENANT_REGISTRY_BASIC_AUTH_PASSWORD`**

### Module integration targets

- **`SRMS_BASE_URL`**
- **`EAPPRAISAL_DOMAIN_TEMPLATE`** (example: `https://appraisal.{subdomain}.com.gh`)
- **`ELEAVE_DOMAIN_TEMPLATE`** (example: `https://{subdomain}.eleave.com.gh`)
- **`MODULE_HANDOFF_ENABLED`**: should be `true`.
- **`MODULE_LAUNCH_EXPOSE_NATIVE_URLS`**: should be `false`; Portal launches native UIs through handoff.

---

## Tenant Registry (`apps/backend/tenant-registry-service/`)

See `apps/backend/tenant-registry-service/.env.example`.

Tenant Registry is the mapping store: `tenant_id` → “how to reach this tenant in each module”.

- **`DATABASE_URL`**: Postgres connection
- **`INTERNAL_BASIC_AUTH_USERNAME`** / **`INTERNAL_BASIC_AUTH_PASSWORD`**: protects internal service endpoints

---

## Docker vs local: why the names differ

In Docker, `docker-compose.yml` passes values using `HRIS_*`-prefixed variables and then maps them into the container env.

If you’re confused about “what is actually set at runtime”, check:

- `docker-compose.yml` (what containers receive)
- the component’s `.env.example` (what local runs expect)
