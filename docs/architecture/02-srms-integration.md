# 02 – SRMS Integration Architecture

## 1. Overview

The **Staff Records Management System (SRMS)** is a multi-tenant React + FastAPI application using **PostgreSQL schema-per-tenant**.

The HRIS Platform integrates SRMS by:

- Delegating authentication to Keycloak.
- Using `tenant_id` from Keycloak tokens and Tenant Registry to select the correct schema.
- Exposing a well-defined API contract for HRIS Core API to consume.

## 2. Existing SRMS Architecture (Summary)

- **Backend:** FastAPI (async), with:
  - RQ workers (email, facial sync)
  - WebSockets (real-time summaries and dashboards)
- **Frontend:** React app under `frontend/`
- **Database:**
  - Public schema:
    - `organizations`, `user_mappings`, `super_admins`, `tenancies`, `system_settings`, `terms_and_conditions`, audit tables.
  - Tenant schema (`tenant_<org_uuid>`):
    - `users`, `employees`, `roles`, `tokens`, `branches`, `departments`, `units`, `ranks`, messaging, etc.

## 3. Authentication Integration

### 3.1 Legacy Authentication

Existing flow:

1. `POST /api/auth/login` with:
   - Username (or email)
   - Password (or facial image)
2. Backend:
   - Uses `public.user_mappings` to find `organization_id`.
   - Loads user from tenant schema.
   - Verifies password or facial auth.
   - Issues **custom JWT** and stores token in `tenant.tokens`.
3. Frontend stores token in HttpOnly cookie `token`.

This flow continues to exist for backward compatibility.

### 3.2 Keycloak-Based Authentication

For HRIS integration:

- SRMS backend validates **Keycloak JWT** instead of issuing its own.
- SRMS relies on the following token claims:
  - `sub` – user id
  - `preferred_username`
  - `tenant_id`
  - `realm_access.roles` or `roles`

SRMS uses:

- Keycloak token for **authentication**
- Local `roles` / `permissions` tables for **fine-grained authorization**

### 3.3 Mixed Mode

The SRMS backend supports both:

- Legacy SRMS tokens (for existing frontend)
- Keycloak tokens (for HRIS Portal and Core API)

Endpoints accessed via HRIS Portal and HRIS Core API **must** use Keycloak tokens.

## 4. Tenant Resolution (Schema-per-Tenant)

SRMS uses the Tenant Registry to determine the schema for the current request.

Flow:

1. Extract `tenant_id` from validated Keycloak token.
2. Call Tenant Registry: `GET /tenants/{tenant_id}`.
3. Retrieve `srms_schema` (e.g., `tenant_944cce18_bf10_4d46_b7e0_93b42aba6c2d`).
4. Set `search_path` to `srms_schema, public` for the duration of the DB session.

If `srms_schema` is `null` or tenant is inactive:

- Reject the request (`403 Forbidden`).

## 5. RBAC & Permissions

- Keycloak roles are used for coarse-grained checks (e.g., only `hris:tenant_admin` can manage tenants).
- SRMS `roles` and `permissions` tables provide detailed access control inside a tenant.
- Typical helper functions:
  - `require_permission("employee:read")`
  - `require_role("HR Manager")`

In an HRIS context, these helper functions are used **after** token and tenant resolution.

## 6. SRMS APIs Used by HRIS Core

Typical endpoints consumed by HRIS Core API include:

- `GET /api/employees/{employee_id}` – core employee record
- `GET /api/employees` – list employees (with filters)
- `GET /api/dashboard/summary` – SRMS-specific dashboard cards
- `GET /api/branches` – org structures for navigation

The detailed API contract is defined in `docs/api-contracts/srms-integration-contract.md`.
