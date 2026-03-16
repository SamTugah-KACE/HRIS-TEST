# Environment variables (Beginner-friendly)

The **canonical source of truth** for “what env vars exist” is the example file next to each component:

- Portal: `portal/.env.example`
- HRIS Core API: `hris-core-api/.env.example`
- Tenant Registry: `tenant-registry-service/.env.example`

This doc explains how to think about those variables without needing to already know the system.

---

## Safety rules (important)

- **Never commit real secrets** (passwords, client secrets, SMTP credentials).
- Prefer setting secrets in **CI/CD secret stores** or your **deployment environment**, not in repo files.
- For local work: copy the example file to a real `.env` and edit locally.

---

## Portal (`portal/`)

See `portal/.env.example`.

The Portal runs in your browser. It needs to know where the Core API is and which auth mode to use.

- **`VITE_HRIS_CORE_API_BASE_URL`**: Core API base URL (typical local: `http://localhost:8000`)
- **`VITE_AUTH_MODE`**: `dev` (no SSO) or `keycloak` (SSO)
- **`VITE_PORTAL_DATA_MODE`**: `mock` (UI uses local datasets) or `api` (UI is driven by Core API)
- **`VITE_DEV_DEFAULT_TENANT_ID`** / **`VITE_DEV_DEFAULT_EMPLOYEE_ID`**: defaults used in dev mode

---

## HRIS Core API (`hris-core-api/`)

See `hris-core-api/.env.example`.

Think of Core API as a “translator and aggregator” for the Portal.

### Mode switches (first things to check)

- **`AUTH_MODE`**:
  - `dev`: trusts debug headers (fast local iteration)
  - `keycloak`: validates Keycloak JWTs using JWKS (real SSO)
- **`USE_STUB_DATA`**:
  - `true`: return realistic stub payloads (no module dependencies)
  - `false`: call SRMS / eAppraisal / eLeave live

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

### Module integration targets (only when `USE_STUB_DATA=false`)

- **`SRMS_BASE_URL`**
- **`EAPPRAISAL_DOMAIN_TEMPLATE`** (example: `https://appraisal.{subdomain}.com.gh`)
- **`ELEAVE_DOMAIN_TEMPLATE`** (example: `https://{subdomain}.eleave.com.gh`)

---

## Tenant Registry (`tenant-registry-service/`)

See `tenant-registry-service/.env.example`.

Tenant Registry is the mapping store: `tenant_id` → “how to reach this tenant in each module”.

- **`DATABASE_URL`**: Postgres connection
- **`INTERNAL_BASIC_AUTH_USERNAME`** / **`INTERNAL_BASIC_AUTH_PASSWORD`**: protects internal service endpoints

---

## Docker vs local: why the names differ

In Docker, `docker-compose.yml` passes values using `HRIS_*`-prefixed variables and then maps them into the container env.

If you’re confused about “what is actually set at runtime”, check:

- `docker-compose.yml` (what containers receive)
- the component’s `.env.example` (what local runs expect)

