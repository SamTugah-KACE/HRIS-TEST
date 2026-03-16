# Glossary

This glossary uses “plain language first” so new team members can follow discussions quickly.

## Core concepts

- **Tenant**: One organization/customer using HRIS (e.g., “Ministry of Finance”). Tenants must be isolated from each other.
- **`tenant_id`**: The *global* tenant identifier (UUID). It appears in Keycloak tokens and is the lookup key in Tenant Registry.
- **Tenant Registry**: Service that maps `tenant_id` → module-specific tenant identifiers (schema names, subdomains, etc.).
- **SSO (Single Sign-On)**: Login once via Keycloak, then access portal + APIs without re-authenticating.
- **RBAC (Role-Based Access Control)**: “What you can do” based on roles. HRIS uses Keycloak realm roles like `hris:employee`.
- **BFF (Backend-for-Frontend)**: A backend tailored for one frontend. Here, **HRIS Core API** is the BFF for the Portal.

## Runtime modes

- **Dev auth mode** (`AUTH_MODE=dev`): No real login required. The portal can send debug headers (like `X-Debug-Roles`) so the backend behaves as if you were logged in as a specific role.
- **Keycloak auth mode** (`AUTH_MODE=keycloak`): Real SSO. Core API validates JWTs using Keycloak JWKS.
- **Stub data** (`USE_STUB_DATA=true`): Core API returns realistic hardcoded data instead of calling production modules. Used for UI/dev without dependencies.

## Systems/modules (integration targets)

- **SRMS**: Staff Records module (employee records, org structure).
- **eAppraisal**: Performance appraisal module (cycles, reviews, scoring).
- **eLeave**: Leave management module (leave requests, approvals, balances).

## Common “where is it implemented?”

- **Auth + role resolution**: `hris-core-api/app/core/auth.py` and `portal/src/auth/*`
- **Tenant mapping lookup**: `hris-core-api/app/services/tenant_registry_client.py` and `tenant-registry-service/app/api/tenants.py`
- **Cross-module aggregation endpoints**: `hris-core-api/app/api/*`

