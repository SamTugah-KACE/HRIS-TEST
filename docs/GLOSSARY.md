# Glossary

This glossary uses “plain language first” so new team members can follow discussions quickly.

## Core concepts

- **Tenant**: One organization/customer using HRIS (e.g., “Ministry of Finance”). Tenants must be isolated from each other.
- **`tenant_id`**: The *global* tenant identifier (UUID). It appears in Keycloak tokens and is the lookup key in Tenant Registry.
- **Tenant Registry**: Service that maps `tenant_id` → module-specific tenant identifiers (schema names, subdomains, etc.).
- **SSO (Single Sign-On)**: Login once via Keycloak, then access Portal, Core APIs, and native module workspaces without re-authenticating.
- **RBAC (Role-Based Access Control)**: “What you can do” based on roles. HRIS uses Keycloak realm roles like `hris:employee`.
- **BFF (Backend-for-Frontend)**: A backend tailored for one frontend. Here, **HRIS Core API** is the BFF for the Portal.

## Runtime expectations

- **Keycloak auth mode** (`AUTH_MODE=keycloak`): Real SSO. Core API validates JWTs using Keycloak JWKS. This is the expected development, staging, and production mode.
- **Production-like development**: Local development uses real local services, real Tenant Registry records, and real module readiness checks.
- **No-stub runtime**: Product APIs must not return hardcoded employee, tenant, appraisal, leave, profile, or dashboard data. Tests may still use mocks and fixtures inside test code.
- **Handoff**: Short-lived, one-time launch flow used when HRIS opens a native module UI.

## Systems/modules (integration targets)

- **SRMS**: Staff Records module (employee records, org structure).
- **eAppraisal**: Performance appraisal module (cycles, reviews, scoring).
- **eLeave**: Leave management module (leave requests, approvals, balances).

## Common “where is it implemented?”

- **Auth + role resolution**: `apps/backend/hris-core-api/app/core/auth.py` and `apps/frontend/portal/src/auth/*`
- **Tenant mapping lookup**: `apps/backend/hris-core-api/app/services/tenant_registry_client.py` and `apps/backend/tenant-registry-service/app/api/tenants.py`
- **Cross-module aggregation endpoints**: `apps/backend/hris-core-api/app/api/*`
- **Saved implementation package**: `docs/implementation/`, `docs/backend/tasks/`, `docs/frontend/tasks/`, and `docs/api-contracts/write/`
