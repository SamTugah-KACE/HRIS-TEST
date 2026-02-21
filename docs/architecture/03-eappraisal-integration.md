# 03 – eAppraisal Integration Architecture

## 1. Overview

The **Performance Appraisal Management System (eAppraisal)** is a multi-tenant Angular + FastAPI application using **PostgreSQL schema-per-tenant (subdomain-based)**.

The HRIS Platform integrates eAppraisal by:

- Using Keycloak for SSO and token validation.
- Using `tenant_id` and Tenant Registry to resolve eAppraisal tenant schema.
- Consuming eAppraisal APIs from HRIS Core API for cross-module features.

## 2. Existing eAppraisal Architecture (Summary)

- **Backend:** FastAPI with a domain-driven structure:
  - `domains/auth`, `domains/organization`, `domains/appraisal`, `domains/tenancies`, `domains/notification`.
- **Client:** Angular, with modules for:
  - Authentication (login, forgot/reset password)
  - Main app
  - Tenant management
- **Database:**
  - Public schema:
    - `organizations`, `users`, `refresh_tokens`, system admin roles.
  - Tenant schema (named by org subdomain) for:
    - Staff, roles, permissions, appraisal cycles, templates, sections, submissions, feedback, etc.

## 3. Authentication Integration

### 3.1 Legacy Authentication

Existing flow:

1. `POST auth/token` with email (`username`) and `password`.
2. Backend:
   - Looks up user in public `users`.
   - Verifies password (Argon2).
   - Creates access and refresh tokens.
   - Stores refresh tokens in `refresh_tokens`.
   - Sets `AccessToken` and `RefreshToken` cookies.

### 3.2 Keycloak-Based Authentication

For HRIS integration:

- eAppraisal backend accepts Keycloak JWTs.
- It validates tokens using Keycloak JWKS and expected audience (`eappraisal-api`).
- Uses the following claims:
  - `sub`, `email`
  - `tenant_id`
  - `roles` / `realm_access.roles`

Access tokens issued by Keycloak are used for:

- Authentication of HRIS Portal and HRIS Core API.
- Potential future SSO integration for Angular frontend.

## 4. Tenant Resolution (Schema-per-Tenant)

Originally, eAppraisal uses subdomains to determine schemas.

In the integrated HRIS model:

1. Extract `tenant_id` from Keycloak token.
2. Call Tenant Registry: `GET /tenants/{tenant_id}`.
3. Retrieve `eappraisal_schema` (subdomain-based schema name).
4. Execute `SET search_path` to the resolved schema for the duration of the DB session.

If no schema or inactive tenant:

- Reject the request with `403 Forbidden`.

## 5. RBAC & Permissions

- Keycloak roles define high-level access (e.g., tenant admin, HR manager).
- Tenant schema contains `OrganizationRole` and `OrganizationPermission` entities for detailed access control.
- eAppraisal uses its own `rbac` utilities to enforce access within a tenant.

## 6. eAppraisal APIs Used by HRIS Core

Examples:

- `GET /appraisals/summary` – overall appraisal statistics per tenant.
- `GET /appraisals/employees/{employee_id}` – appraisal history for specific employee.
- `GET /appraisals/cycles/active` – list of active appraisal cycles.

The specific contracts for these endpoints are defined in `docs/api-contracts/srms-integration-contract.md` and related files, and may be extended with additional appraisal-specific contracts if needed.
