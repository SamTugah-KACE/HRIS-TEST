# Code reading map (Architecture for beginners)

This document complements the deep technical playbooks by answering: **“What happens when I click a button in the Portal?”**

If you’re new, start with `docs/START_HERE.md` first.

---

## The “happy path” request flow

Example: you open the dashboard in the Portal.

1. **Browser loads the Portal** (`portal/`).
2. Portal decides **who you are** (dev mode role switcher, or Keycloak SSO).
3. Portal calls Core API endpoints like:
   - `GET /me`
   - `GET /dashboard/summary`
4. **Core API** (`hris-core-api/`) does 3 big jobs:
   - **Authenticate** the request (dev headers or Keycloak token validation).
   - **Resolve tenant** (use `tenant_id` → Tenant Registry mapping).
   - **Aggregate module data** (call SRMS/eAppraisal/eLeave, normalize, and combine).
5. Core returns a single response shaped for the Portal’s UI.

---

## Where each responsibility lives

### Portal (React UI)

- **Auth context + role selection (dev mode)**: `portal/src/auth/AuthProvider.tsx`
- **Sending dev headers**: `portal/src/api/httpClient.ts`
- **Routes and guards**: `portal/src/router.tsx`, `portal/src/components/ProtectedRoute.tsx`
- **Pages**: `portal/src/pages/*`

### Core API (FastAPI BFF)

- **FastAPI app**: `hris-core-api/app/main.py`
- **Auth and roles**: `hris-core-api/app/core/auth.py`
- **Portal-facing endpoints**: `hris-core-api/app/api/*`
- **Module calling**: `hris-core-api/app/clients/*_client.py`
- **Normalization/adapters**: `hris-core-api/app/adapters/*`
- **Tenant resolution**: `hris-core-api/app/services/tenant_registry_client.py`

### Tenant Registry (tenant mapping)

- **API**: `tenant-registry-service/app/api/tenants.py`
- **Model**: `tenant-registry-service/app/models/tenant.py`

### Keycloak (identity)

- **Realm config**: `identity/realm-export.json`
- **Core API SSO endpoints**: `hris-core-api/app/api/auth_sso.py`

---

## How to debug quickly (beginner workflow)

When something “doesn’t work”, answer these in order:

1. **Is the Portal reaching Core?**
   - open Core docs: `http://localhost:8000/docs`
2. **Which auth mode are you in?**
   - Portal: `VITE_AUTH_MODE` in `portal/.env`
   - Core: `AUTH_MODE` in `hris-core-api/.env`
3. **Are you in stub mode?**
   - Core: `USE_STUB_DATA`
4. **If live mode, is tenant mapping present?**
   - Tenant Registry: `GET /tenants/{tenant_id}`

---

## Pointers to deeper docs

- Full system design + ERD + module sync playbook:
  - `docs/architecture/hris-system-design-erd-and-module-sync-playbook.md`
- Identity and tenant model:
  - `docs/architecture/01-identity-and-tenant-model.md`

