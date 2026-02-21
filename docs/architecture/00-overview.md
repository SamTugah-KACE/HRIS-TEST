
---

## 2. `docs/architecture/00-overview.md`

```markdown
# 00 – Platform Overview

## 1. Purpose

This document describes the **high-level architecture** of the HRIS Platform, which unifies:

- Staff Records Management System (SRMS)
- Performance Appraisal Management System (eAppraisal)
- Leave Management System (eLeave)

into a single **Human Resource Information System (HRIS)** experience, while preserving independent deployments and heterogeneous technology stacks.

## 2. High-Level Architecture

The platform is organized into the following layers:

1. **User Experience Layer**
   - **HRIS Portal (React)** – primary entry point, SSO-based.
   - Provides unified navigation, dashboards, and cross-module experiences.

2. **Identity & Access Layer**
   - **Keycloak** as the central Identity Provider (IdP).
   - Single realm (`hris-platform`) with:
     - Shared users and RBAC.
     - Tenant-aware claims (`tenant_id`, roles).
   - All modules (SRMS, eAppraisal, eLeave, HRIS Core API) are Keycloak clients.

3. **Tenant & Configuration Layer**
   - **Tenant Registry Service** (FastAPI) stores:
     - Global `tenant_id`
     - SRMS schema
     - eAppraisal schema
     - eLeave tenant database / tenant key
     - Tenant status, branding settings, etc.

4. **Module Layer (Existing Systems)**
   - **SRMS** (React + FastAPI, schema-per-tenant).
   - **eAppraisal** (Angular + FastAPI, schema-per-tenant via subdomain).
   - **eLeave** (Angular + Laravel, database-per-tenant using Stancl Tenancy).
   - Each module:
     - Validates Keycloak JWTs.
     - Uses `tenant_id` to resolve the correct schema / database via Tenant Registry.

5. **Integration Layer**
   - **HRIS Core API** (FastAPI Backend-for-Frontend).
   - Provides cross-module aggregation endpoints, e.g.:
     - Employee 360 view.
     - Cross-module dashboards.
   - Uses Keycloak tokens and Tenant Registry to securely call each module’s API.

6. **Infrastructure Layer**
   - Docker / Kubernetes orchestrating:
     - HRIS Portal
     - HRIS Core API
     - Tenant Registry
     - Keycloak
     - Nginx / reverse proxies
   - Supports gradual rollout and independent scaling of each module.

## 3. Data & Multi-Tenancy Overview

- **Global tenant_id** is managed by the Tenant Registry Service.
- SRMS and eAppraisal use **schema-per-tenant** in shared PostgreSQL instances.
- eLeave uses **database-per-tenant** via Stancl Tenancy.
- The Tenant Registry defines a **canonical mapping**:

```text
tenant_id → {
  srms_schema,
  eappraisal_schema,
  eleave_db_name,
  branding,
  is_active,
  ...
}
