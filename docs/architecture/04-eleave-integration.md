# 04 – eLeave Integration Architecture

## 1. Overview

The **eLeave** system is an Angular + Laravel multi-tenant application using **Stancl Tenancy (database-per-tenant)**.

The HRIS Platform integrates eLeave by:

- Validating Keycloak JWTs in Laravel via middleware.
- Mapping global `tenant_id` to Stancl tenants using the Tenant Registry.
- Exposing REST APIs that are consumable by the HRIS Core API using Keycloak Bearer tokens.

## 2. Existing eLeave Architecture (Summary)

- **Backend:** Laravel with:
  - Central DB holding organizations (tenants).
  - Tenant DBs, each containing:
    - `users`, `staff`, leave types/levels, `staff_leave`, leave actions, holidays, etc.
- **Frontends:**
  - Angular `tenant-app` – leave management UI for staff and managers.
  - Angular `core-app` – tenant management UI.
- **Routing:**
  - Tenant routes are defined in `routes/tenant.php` with prefix `/{tenant}`.
  - Central routes in `routes/api.php` (e.g., for tenant info).
- **Multi-Tenancy:**
  - Powered by Stancl Tenancy with `Organization` as tenant model.
  - Tenant DBs or schemas prefixed using configuration in `config/tenancy.php`.

## 3. Authentication Integration

### 3.1 Legacy Authentication

Existing flow:

1. `POST /{tenant}/auth/login` with email and password.
2. Laravel runs in tenant context (Stancl).
3. Backend:
   - Looks up user in tenant DB.
   - Verifies password using `Hash::check`.
   - Deletes old tokens.
   - Issues a Sanctum API token and a custom JWT representing the user.
4. Angular stores the Sanctum token and custom user JWT and uses them for API access.

### 3.2 Keycloak-Based Authentication

For HRIS integration:

- eLeave exposes **HRIS-facing APIs** that are secured by a `keycloak.jwt` middleware.
- Middleware:
  - Validates Keycloak JWT using Keycloak JWKS.
  - Checks issuer and audience (`eleave-api`).
  - Extracts `tenant_id` from token claim.
  - Resolves tenant via Tenant Registry.
  - Initializes Stancl tenancy with resolved tenant key.
- The HRIS Core API uses **Keycloak Bearer tokens** to call these APIs.

This allows HRIS integration without modifying existing Sanctum-based authentication for the Angular frontend.

## 4. Tenant Resolution (Database-per-Tenant)

Flow:

1. Laravel middleware reads Keycloak JWT from `Authorization` header.
2. Decodes and verifies token.
3. Extracts `tenant_id`.
4. Calls Tenant Registry:
   - `GET /tenants/{tenant_id}`
5. Receives mapping containing `eleave_db_name`.
6. Calls `tenancy()->initialize(eleave_db_name)` to set tenant context.

If tenant is not found or inactive:

- Return `403 Forbidden` with a clear error message.

## 5. eLeave APIs Used by HRIS Core

Example HRIS-facing APIs:

- `GET /{tenant}/hris/leaves/summary` – aggregated leave stats for a tenant.
- `GET /{tenant}/hris/employees/{employee_id}/leaves` – leave history for a specific employee.
- `GET /{tenant}/hris/leave-types` – list of leave types for configuration UIs.

These APIs:

- Are protected with `keycloak.jwt` middleware.
- Expect Keycloak Bearer tokens with valid `tenant_id` claim.
- Never rely on client-provided schema or DB names.

The detailed contracts are defined in `docs/api-contracts/eleave-integration-contract.md`.
