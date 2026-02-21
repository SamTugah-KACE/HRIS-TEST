
---

## 9. `docs/ops/env-variables.md`

```markdown
# Environment Variables

This document lists the key environment variables required by the HRIS Platform components.

## 1. Common Variables

These may apply to multiple services (HRIS Core API, Tenant Registry, SRMS, eAppraisal, eLeave).

- `KEYCLOAK_ISSUER` – Keycloak issuer URL, e.g. `https://keycloak.example.com/realms/hris-platform`
- `KEYCLOAK_JWKS_URL` – JWKS endpoint, e.g. `https://keycloak.example.com/realms/hris-platform/protocol/openid-connect/certs`

Each service has its own `KEYCLOAK_AUDIENCE_*` to validate tokens.

## 2. HRIS Core API

- `KEYCLOAK_AUDIENCE_HRIS_CORE` – Expected `aud` for tokens accepted by HRIS Core API.
- `TENANT_REGISTRY_BASE_URL` – Base URL for Tenant Registry Service.
- `TENANT_REGISTRY_TIMEOUT_SECONDS` – Default HTTP timeout for registry calls.
- `SERVICE_CLIENT_ID` – Client ID for HRIS Core API when calling Tenant Registry.
- `SERVICE_CLIENT_SECRET` – Secret for HRIS Core API when calling Tenant Registry.
- `DATABASE_URL` – PostgreSQL connection URI for HRIS Core (if used).

## 3. Tenant Registry Service

- `DATABASE_URL` – PostgreSQL connection URI for Tenant Registry DB.
- `JWT_SECRET_KEY` (if using internal JWT for internal auth).
- `API_PORT` – HTTP port.

## 4. SRMS

- `KEYCLOAK_AUDIENCE_SRMS` – Expected audience for SRMS tokens.
- `TENANT_REGISTRY_BASE_URL` – Base URL for Tenant Registry.
- `TENANT_REGISTRY_TIMEOUT_SECONDS`
- `SERVICE_CLIENT_ID` – service identity for SRMS.
- `SERVICE_CLIENT_SECRET`
- `SRMS_DATABASE_URL` – PostgreSQL URL (public + tenant schemas).
- Any existing SRMS-specific env vars (mail, RQ, facial auth endpoints).

## 5. eAppraisal

- `KEYCLOAK_AUDIENCE_EAPPRAISAL`
- `TENANT_REGISTRY_BASE_URL`
- `TENANT_REGISTRY_TIMEOUT_SECONDS`
- `SERVICE_CLIENT_ID`
- `SERVICE_CLIENT_SECRET`
- `EAPPRAISAL_DATABASE_URL`

## 6. eLeave (Laravel)

Defined in `.env`:

- `KEYCLOAK_ISSUER`
- `KEYCLOAK_AUDIENCE_ELEAVE`
- `KEYCLOAK_JWKS_URL`
- `TENANT_REGISTRY_BASE_URL`
- `TENANT_REGISTRY_TIMEOUT`
- `SERVICE_CLIENT_ID`
- `SERVICE_CLIENT_SECRET`
- Standard Laravel variables:
  - `APP_URL`, `APP_ENV`, `APP_KEY`
  - `DB_*` for central DB
  - Tenancy-specific variables in `config/tenancy.php`
