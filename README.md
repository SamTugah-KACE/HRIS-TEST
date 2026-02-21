# HRIS Platform

A multi-tenant Human Resource Information System that consolidates three independent production modules -- **Staff Records (SRMS)**, **Performance Appraisal (eAppraisal)**, and **Leave Management (eLeave)** -- into a unified portal with role-based dashboards, single sign-on, and cross-module data aggregation.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Component Reference](#2-component-reference)
3. [Quick Start with Docker](#3-quick-start-with-docker)
4. [Development Setup without Docker](#4-development-setup-without-docker)
5. [Seeded Data and Login Credentials](#5-seeded-data-and-login-credentials)
6. [Role System and Permissions](#6-role-system-and-permissions)
7. [API Reference](#7-api-reference)
8. [Production Module Integration](#8-production-module-integration)
9. [Production Deployment Guide](#9-production-deployment-guide)
10. [Environment Variables](#10-environment-variables)
11. [Project Structure](#11-project-structure)

---

## 1. Architecture Overview

The platform follows a Backend-for-Frontend (BFF) pattern where the Portal calls the HRIS Core API, which in turn aggregates data from the three production modules.

- **Portal (React, port 3000)** authenticates the user via Keycloak and renders role-based dashboards.
- **HRIS Core API (FastAPI, port 8000)** validates the token, resolves the tenant, calls each module API, and returns consolidated data.
- **Keycloak (port 8080)** manages users, roles, and SSO across all modules.
- **Tenant Registry (FastAPI, port 8001)** maps global tenant IDs to each module's native identifiers.
- **SRMS, eAppraisal, eLeave** remain as independent production systems, called via their REST APIs.

### Design Principles

- **No module modification**: Production modules remain untouched. The HRIS platform integrates via their existing APIs.
- **Unified identity**: Keycloak is the single source of truth for authentication and role assignment.
- **Tenant isolation**: A central Tenant Registry maps a global tenant_id to each module's native tenant identifier (schema name, subdomain, or database).
- **Role-based dashboards**: The portal renders different views based on the user's HRIS role.

---

## 2. Component Reference

### 2.1 Portal (portal/)

| Attribute | Value |
|-----------|-------|
| Technology | React 18, TypeScript, Vite 6 |
| Styling | Tailwind CSS 3 |
| Charts | Recharts |
| Icons | Lucide React |
| Auth | Keycloak JS adapter (SSO) or dev bypass mode |
| Port | 5173 (dev) or 3000 (Docker) |

The portal is the user-facing entry point. It authenticates users via Keycloak (or dev mode), determines their role, and renders role-appropriate dashboards by calling the HRIS Core API.

**Key pages:**

| Page | Route | Description |
|------|-------|-------------|
| Dashboard | / | Role-differentiated KPI cards, charts, module summaries, quick actions |
| Staff Records | /employees | Searchable, filterable, paginated employee table from SRMS |
| Employee 360 | /employees/:id | Tabbed view with Profile, Appraisals, and Leave History |
| Performance Appraisal | /modules/appraisal | Module overview, stats, recent activity, deep-link to eAppraisal |
| Leave Management | /modules/leave | Module overview, pending requests, balances, deep-link to eLeave |
| Reports | /reports | Cross-module report catalog |
| Roles and Permissions | /admin/roles | Consolidated role mapping across all modules |
| Tenant Management | /admin/tenants | Tenant list with module enablement (admin only) |

**Auth modes** (controlled by VITE_AUTH_MODE):

| Mode | Behavior |
|------|----------|
| dev | No Keycloak required. Auto-authenticates as a dev user. Instant startup. |
| keycloak | Redirects to Keycloak login. Full SSO with PKCE. Token refresh every 30s. |

### 2.2 HRIS Core API (hris-core-api/)

| Attribute | Value |
|-----------|-------|
| Technology | FastAPI (Python) |
| Auth | Keycloak JWT validation or dev mode |
| Port | 8000 |
| Role | Backend-for-Frontend (BFF) |

The integration and aggregation layer. It receives requests from the portal, resolves the tenant, calls each production module's API, and returns consolidated responses.

**Key files:**

| File | Purpose |
|------|---------|
| app/main.py | FastAPI app, CORS middleware, router registration |
| app/core/auth.py | Auth dependency (dev/keycloak), role resolution, require_roles() |
| app/core/settings.py | Pydantic Settings with all config |
| app/api/me.py | /me endpoint returning current user identity and tenant info |
| app/api/dashboard.py | /dashboard/summary returning aggregated stats from all modules |
| app/api/employees.py | /employees list and /employees/{id}/summary (360 view) |
| app/clients/srms_client.py | HTTP client calling SRMS APIs (with stub fallback) |
| app/clients/eappraisal_client.py | HTTP client calling eAppraisal APIs (with stub fallback) |
| app/clients/eleave_client.py | HTTP client calling eLeave APIs (with stub fallback) |
| app/services/tenant_registry_client.py | Resolves tenant_id to module-specific mappings |
| app/models/tenant_mapping.py | Pydantic model for tenant mapping data |

**Auth modes** (controlled by AUTH_MODE):

| Mode | Behavior |
|------|----------|
| dev | Trusts X-Debug headers or uses DEV_DEFAULT env vars. No token required. |
| keycloak | Validates Keycloak JWT using JWKS. Extracts tenant_id and roles from claims. |

**Stub data** (controlled by USE_STUB_DATA): When true, module clients return realistic hardcoded data instead of calling production APIs. This allows the portal to function without any production module running.

### 2.3 Tenant Registry Service (tenant-registry-service/)

| Attribute | Value |
|-----------|-------|
| Technology | FastAPI, SQLAlchemy, PostgreSQL |
| Auth | HTTP Basic Auth (service-to-service) |
| Port | 8001 |

Maintains the canonical mapping between global tenant IDs and each module's native tenant identifier.

**Database model (tenants table):**

| Column | Type | Description |
|--------|------|-------------|
| tenant_id | UUID | Global tenant identifier (in Keycloak tokens) |
| code | String | Short org code (e.g. GI-KACE) |
| name | String | Organization display name |
| srms_schema | String | SRMS PostgreSQL schema name |
| srms_slug | String | SRMS UI slug |
| eappraisal_subdomain | String | eAppraisal subdomain |
| eleave_subdomain | String | eLeave subdomain |
| is_active | Boolean | Tenant status |

**Endpoints:**

| Method | Path | Description |
|--------|------|-------------|
| GET | /tenants | List all tenants (with optional is_active and search filters) |
| GET | /tenants/{tenant_id} | Get a single tenant mapping |
| GET | /health | Health check |

### 2.4 Identity with Keycloak (identity/)

| Attribute | Value |
|-----------|-------|
| Technology | Keycloak 24.0 |
| Port | 8080 |
| Admin Console | http://localhost:8080/admin |
| Realm | hris-platform |

Centralized identity provider. Manages users, roles, and SSO across the portal and all modules.

**Configuration (identity/realm-export.json):**

| Element | Details |
|---------|---------|
| Realm | hris-platform |
| Clients | hris-portal (public), hris-core-api (bearer-only), srms-api, eappraisal-api, eleave-api |
| Realm roles | hris:super_admin, hris:tenant_admin, hris:hr_manager, hris:line_manager, hris:employee |
| Token mappers | tenant_id (user attribute to token claim), roles (realm roles to token claim) |
| Default role | hris:employee |

The realm is auto-imported when Keycloak starts via the --import-realm flag.

### 2.5 Infrastructure (infra/, docker-compose.yml)

| File | Purpose |
|------|---------|
| docker-compose.yml | Full local stack (Postgres, Keycloak, Tenant Registry, Core API, Portal) |
| docker-compose.keycloak.yml | Override to switch from dev auth to Keycloak SSO |
| infra/db-init/tenant_registry_dev_seed.sql | Seeds 3 tenants and creates Keycloak schema |
| infra/nginx/ | Nginx reverse proxy configs (for production) |

---

## 3. Quick Start with Docker

### Prerequisites

- Docker Desktop (with Docker Compose v2)
- Ports 3000, 5432, 8000, 8001, 8080 available

### Option A: Dev Mode (fastest, no login screen)

```
docker compose up --build -d
```

Wait about 60 seconds for all services to start, then open:

| Service | URL |
|---------|-----|
| Portal | http://localhost:3000 |
| HRIS Core API Docs | http://localhost:8000/docs |
| Tenant Registry Docs | http://localhost:8001/docs |
| Keycloak Admin | http://localhost:8080/admin |

In dev mode, the portal auto-authenticates as dev.admin with the hris:hr_manager role. No login is required.

### Option B: Keycloak SSO Mode (full authentication)

```
docker compose -f docker-compose.yml -f docker-compose.keycloak.yml up --build -d
```

Wait about 90 seconds (Keycloak takes longer to import the realm), then open:

| Service | URL |
|---------|-----|
| Portal | http://localhost:3000 (redirects to Keycloak) |
| Keycloak Admin | http://localhost:8080/admin (admin / admin) |

Log in with any of the seeded credentials listed in Section 5.

### Useful Docker Commands

```
# View logs for all services
docker compose logs -f

# View logs for a specific service
docker compose logs -f hris-core-api

# Restart a single service
docker compose restart hris-core-api

# Stop everything
docker compose down

# Stop and remove all data (fresh start)
docker compose down -v

# Rebuild a single service
docker compose up --build -d portal
```

### Switching Roles in Dev Mode

To see different dashboards, change the DEV_DEFAULT_ROLES env var for the Core API:

```
docker compose down
# Edit docker-compose.yml -> hris-core-api -> DEV_DEFAULT_ROLES to one of:
#   hris:super_admin
#   hris:tenant_admin
#   hris:hr_manager
#   hris:line_manager
#   hris:employee
docker compose up --build -d
```

---

## 4. Development Setup without Docker

### Prerequisites

- Node.js 18+
- Python 3.9+
- PostgreSQL 14+ (only needed if USE_STUB_DATA=false)

### Backend: HRIS Core API

```
cd hris-core-api

# Create virtual environment (recommended)
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS/Linux

# Install dependencies
pip install -r requirements.txt

# The .env file is already configured for dev mode
# AUTH_MODE=dev, USE_STUB_DATA=true

# Start the server
python -m uvicorn app.main:app --reload --port 8000
```

Verify by opening http://localhost:8000/docs for the Swagger UI.

Test endpoints:

```
curl http://localhost:8000/health
curl http://localhost:8000/me
curl http://localhost:8000/dashboard/summary
curl http://localhost:8000/employees
curl http://localhost:8000/employees/e001/summary
```

### Backend: Tenant Registry Service (optional in dev)

Only needed when USE_STUB_DATA=false. The Core API returns stub tenant data in dev mode.

```
cd tenant-registry-service

python -m venv venv
venv\Scripts\activate

pip install -r requirements.txt

# Requires PostgreSQL running with database hris_tenant_registry
# Edit .env with your DATABASE_URL

python -m uvicorn app.main:app --reload --port 8001
```

### Frontend: Portal

```
cd portal

# Install dependencies
npm install

# The .env file is already configured for dev mode
# VITE_AUTH_MODE=dev, VITE_HRIS_CORE_API_BASE_URL=http://localhost:8000

# Start dev server with hot reload
npm run dev
```

Open http://localhost:5173 in your browser.

### Running Both Together

Open two terminals:

| Terminal | Command | URL |
|----------|---------|-----|
| 1 | cd hris-core-api && python -m uvicorn app.main:app --reload --port 8000 | http://localhost:8000 |
| 2 | cd portal && npm run dev | http://localhost:5173 |

---

## 5. Seeded Data and Login Credentials

### Keycloak Admin Console

| Field | Value |
|-------|-------|
| URL | http://localhost:8080/admin |
| Username | admin |
| Password | admin |

### Application Users (Keycloak SSO Mode)

All users belong to the Development Tenant (tenant_id: 11111111-1111-1111-1111-111111111111).

| Username | Password | Email | Role | Dashboard View |
|----------|----------|-------|------|----------------|
| super.admin | Admin@123 | super.admin@hris.local | hris:super_admin | Full system: all tenants, all modules, admin panels |
| tenant.admin | Admin@123 | tenant.admin@hris.local | hris:tenant_admin | Full tenant: org structure, all modules, roles, reports |
| hr.manager | Admin@123 | hr.manager@hris.local | hris:hr_manager | HR dashboard: staff records, appraisals, leaves, reports |
| line.manager | Admin@123 | line.manager@hris.local | hris:line_manager | Team view: team members, team appraisals, leave approvals |
| employee | Admin@123 | employee@hris.local | hris:employee | Self-service: my profile, my appraisals, my leave |

### Dev Mode Default User

When running with AUTH_MODE=dev or VITE_AUTH_MODE=dev, the system auto-authenticates as:

| Field | Value |
|-------|-------|
| Username | dev.admin |
| Role | hris:hr_manager (configurable via DEV_DEFAULT_ROLES) |
| Tenant | Development Tenant |

### Seeded Tenants (Tenant Registry)

| Tenant ID | Code | Name | SRMS | eAppraisal | eLeave |
|-----------|------|------|------|------------|--------|
| 11111111-... | DEV-TENANT | Development Tenant | Yes | Yes | Yes |
| 22222222-... | GI-KACE | Ghana-India Kofi Annan Centre of Excellence in ICT | Yes | Yes | Yes |
| 33333333-... | MOF | Ministry of Finance | Yes | Yes | Yes |

### Stub Employee Data (when USE_STUB_DATA=true)

| Employee ID | Staff ID | Name | Department | Branch |
|-------------|----------|------|------------|--------|
| e001 | STF-001 | Kwame Asante | Information Technology | Head Office |
| e002 | STF-002 | Ama Mensah | Human Resources | Head Office |
| e003 | STF-003 | Kofi Osei | Finance | Head Office |
| e004 | STF-004 | Abena Boateng | Information Technology | Kumasi Branch |
| e005 | STF-005 | Yaw Adjei | Administration | Head Office |
| e006 | STF-006 | Akua Darko | Finance | Tamale Branch |
| e007 | STF-007 | Nana Appiah | Human Resources | Head Office |
| e008 | STF-008 | Efua Owusu | Legal | Head Office |
| e009 | STF-009 | Kojo Frimpong | Information Technology | Head Office |
| e010 | STF-010 | Adwoa Poku | Administration | Kumasi Branch |

---

## 6. Role System and Permissions

### HRIS Role Hierarchy

The hierarchy from highest to lowest privilege:

1. **hris:super_admin** -- System-wide access, all tenants
2. **hris:tenant_admin** -- Full access within one tenant
3. **hris:hr_manager** -- HR functions: staff, appraisals, leaves, reports
4. **hris:line_manager** -- Team scope: direct reports, approvals
5. **hris:employee** -- Self-service only

Higher roles inherit all views available to lower roles.

### What Each Role Sees in the Portal

| Feature | Super Admin | Tenant Admin | HR Manager | Line Manager | Employee |
|---------|:-----------:|:------------:|:----------:|:------------:|:--------:|
| KPI stats grid | 6 cards | 6 cards | 6 cards | 6 cards | 4 cards |
| Staff/Appraisal/Leave charts | Yes | Yes | Yes | Yes | No |
| Module summary cards | Yes | Yes | Yes | Yes | Yes |
| Quick actions (manage) | Yes | Yes | Yes | Yes | No |
| Quick actions (self-service) | No | No | No | No | Yes |
| Employee list and search | Yes | Yes | Yes | Yes | My Profile |
| Appraisal module (manager view) | Yes | Yes | Yes | Yes | No |
| Appraisal module (my view) | No | No | No | No | Yes |
| Leave module (manager view) | Yes | Yes | Yes | Yes | No |
| Leave module (my view) | No | No | No | No | Yes |
| Reports page | Yes | Yes | Yes | No | No |
| Roles and Permissions page | Yes | Yes | No | No | No |
| Tenant Management page | Yes | Yes | No | No | No |

### Consolidated Role Mapping to Production Modules

Each HRIS role maps to native roles in each production module:

| HRIS Role | SRMS Native Roles | eAppraisal Native Roles | eLeave Native Roles |
|-----------|-------------------|-------------------------|---------------------|
| hris:super_admin | Super Admin | System Admin (public) | SuperAdmin (tenant mgmt) |
| hris:tenant_admin | Admin, CEO | SYSTEM ADMINISTRATOR | Admin |
| hris:hr_manager | HR Manager, Branch Manager | HUMAN RESOURCE | HR |
| hris:line_manager | Manager, Department Head, HoD | STAFF (with review perms) | DG, Director |
| hris:employee | Employee, Staff | STAFF | Normal |

### How Authorization Works

1. **Authentication**: User logs in via Keycloak. Token includes tenant_id and roles claims.
2. **HRIS Core API**: Extracts roles from token, resolves effective_role (highest role wins).
3. **Tenant resolution**: tenant_id is used to look up module-specific identifiers from the Tenant Registry.
4. **Module calls**: The Core API forwards the Keycloak Bearer token to each production module. The module uses its own native RBAC for fine-grained authorization.
5. **Portal rendering**: Frontend reads effective_role and conditionally renders dashboards, navigation, and actions.

---

## 7. API Reference

### HRIS Core API (http://localhost:8000)

Interactive docs: http://localhost:8000/docs

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | /health | None | Health check |
| GET | /me | Required | Current user identity, tenant info, module enablement |
| GET | /dashboard/summary | Required | Aggregated dashboard data from all modules plus quick actions |
| GET | /employees | Required | Paginated employee list (search, department, status filters) |
| GET | /employees/{id}/summary | Required | Employee 360: profile plus appraisals plus leave history |

**Query parameters for /employees:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| search | string | "" | Search by name, staff ID, or email |
| department | string | "" | Filter by department name |
| status | string | "active" | active, inactive, or all |
| page | int | 1 | Page number |
| page_size | int | 20 | Items per page (max 100) |

### Tenant Registry API (http://localhost:8001)

Interactive docs: http://localhost:8001/docs

All endpoints require HTTP Basic Auth (hris_internal / registry_secret in dev).

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /health | Health check |
| GET | /tenants | List all tenants |
| GET | /tenants/{tenant_id} | Get tenant by global ID |

---

## 8. Production Module Integration

The HRIS platform consolidates three independent production systems. It does not modify their codebases.

### 8.1 Staff Records Management System (SRMS)

| Attribute | Value |
|-----------|-------|
| Stack | FastAPI + React + PostgreSQL |
| Multi-tenancy | Schema-per-tenant (tenant_{org_uuid}) |
| Native auth | Username/password, custom JWT, optional facial auth |
| HRIS integration | Via srms_client.py calling SRMS REST APIs with Keycloak Bearer token |

SRMS provides: Employee records, org structure (branches, departments, units, ranks), roles/permissions, messaging, dashboards, bulk enrollment, reporting.

SRMS roles (10 default): Admin, Super Admin, CEO, HR Manager, Branch Manager, Department Head, Manager, HoD, Employee, Staff.

SRMS permissions (100+): Organized by domain including employee, branches, departments, role:manage, hr:dashboard, admin:dashboard, staff:dashboard, and more.

### 8.2 Performance Appraisal (eAppraisal)

| Attribute | Value |
|-----------|-------|
| Stack | FastAPI + Angular + PostgreSQL |
| Multi-tenancy | Schema-per-tenant (subdomain-based) |
| Native auth | Email/password, OAuth2 tokens, refresh tokens |
| HRIS integration | Via eappraisal_client.py calling eAppraisal REST APIs |

eAppraisal provides: Appraisal cycles, templates, sections, submissions, feedback, department groups, organization management.

eAppraisal roles (3 org + system): SYSTEM ADMINISTRATOR, HUMAN RESOURCE, STAFF. System Admin (public schema) bypasses all checks.

eAppraisal permissions (30+): viewTotalStaff, readStaff, createStaff, approveAppraisal, readMyAppraisal, readRoles, createRolePermissions, etc.

### 8.3 Leave Management (eLeave)

| Attribute | Value |
|-----------|-------|
| Stack | Laravel + Angular + PostgreSQL |
| Multi-tenancy | Database-per-tenant (Stancl Tenancy) |
| Native auth | Email/password, Laravel Sanctum tokens |
| HRIS integration | Via eleave_client.py calling eLeave REST APIs |

eLeave provides: Leave types/levels, leave application, multi-level approval, leave scheduling, holidays, reports, staff management.

eLeave roles (6 tenant + 3 management): Admin, HR, DG, Director, Normal, ThirdParty. Management: SuperAdmin, Admin, Officer.

eLeave permissions (46): applyForLeave, recommendLeaves, approveLeaves, viewMyLeaves, generateReport, manageRolesAndPermissions, etc.

---

## 9. Production Deployment Guide

### Key Steps

1. **Provision infrastructure** -- VMs or Kubernetes cluster with PostgreSQL, DNS, TLS.
2. **Deploy Keycloak** -- Import realm, configure clients with production redirect URIs, enable HTTPS.
3. **Deploy Tenant Registry** -- Run migrations, seed production tenants.
4. **Configure production modules** -- Add Keycloak JWT validation middleware to SRMS, eAppraisal, eLeave (see docs/architecture/).
5. **Deploy HRIS Core API** -- Set AUTH_MODE=keycloak, USE_STUB_DATA=false, configure real module URLs.
6. **Deploy Portal** -- Build with production VITE env vars, deploy behind Nginx with TLS.
7. **Smoke test** -- Verify SSO login, dashboard loading, cross-module data aggregation.

### Production Environment Variables

Set AUTH_MODE=keycloak and USE_STUB_DATA=false, then configure:

```
KEYCLOAK_ISSUER=https://auth.hris.example.com/realms/hris-platform
KEYCLOAK_JWKS_URL=https://auth.hris.example.com/realms/hris-platform/protocol/openid-connect/certs
KEYCLOAK_AUDIENCE_HRIS_CORE=hris-core-api
TENANT_REGISTRY_BASE_URL=http://tenant-registry:8000
SRMS_BASE_URL=https://srms.example.com
EAPPRAISAL_DOMAIN_TEMPLATE=https://appraisal.{subdomain}.example.com
ELEAVE_DOMAIN_TEMPLATE=https://{subdomain}.eleave.example.com
```

---

## 10. Environment Variables

### Portal (portal/.env)

| Variable | Required | Default | Description |
|----------|:--------:|---------|-------------|
| VITE_HRIS_CORE_API_BASE_URL | Yes | - | URL of the HRIS Core API |
| VITE_AUTH_MODE | Yes | dev | dev (no login) or keycloak (SSO) |
| VITE_KEYCLOAK_URL | If keycloak | - | Keycloak server URL |
| VITE_KEYCLOAK_REALM | If keycloak | - | Keycloak realm name |
| VITE_KEYCLOAK_CLIENT_ID | If keycloak | - | Keycloak client ID |

### HRIS Core API (hris-core-api/.env)

| Variable | Required | Default | Description |
|----------|:--------:|---------|-------------|
| AUTH_MODE | Yes | dev | dev or keycloak |
| USE_STUB_DATA | Yes | true | true returns mock data; false calls real modules |
| DEV_DEFAULT_TENANT_ID | If dev | - | Tenant ID for dev user |
| DEV_DEFAULT_USERNAME | If dev | - | Username for dev user |
| DEV_DEFAULT_ROLES | If dev | hris:hr_manager | Comma-separated HRIS roles |
| KEYCLOAK_ISSUER | If keycloak | - | Keycloak issuer URL |
| KEYCLOAK_JWKS_URL | If keycloak | - | Keycloak JWKS endpoint |
| KEYCLOAK_AUDIENCE_HRIS_CORE | If keycloak | - | Expected aud claim |
| TENANT_REGISTRY_BASE_URL | Yes | http://localhost:8001 | Tenant Registry URL |
| TENANT_REGISTRY_BASIC_AUTH_USERNAME | Yes | hris_internal | Basic auth username |
| TENANT_REGISTRY_BASIC_AUTH_PASSWORD | Yes | change-me | Basic auth password |
| SRMS_BASE_URL | If not stub | - | SRMS production URL |
| EAPPRAISAL_DOMAIN_TEMPLATE | If not stub | - | eAppraisal URL template |
| ELEAVE_DOMAIN_TEMPLATE | If not stub | - | eLeave URL template |
| HTTP_CLIENT_TIMEOUT_SECONDS | No | 10 | Timeout for module API calls |

### Tenant Registry (tenant-registry-service/.env)

| Variable | Required | Default | Description |
|----------|:--------:|---------|-------------|
| DATABASE_URL | Yes | - | PostgreSQL connection URL |
| INTERNAL_BASIC_AUTH_USERNAME | Yes | - | Basic auth username |
| INTERNAL_BASIC_AUTH_PASSWORD | Yes | - | Basic auth password |

---

## 11. Project Structure

```
HRIS-Platform/
|-- docker-compose.yml                    # Full local stack (dev mode)
|-- docker-compose.keycloak.yml           # Override for Keycloak SSO mode
|-- .gitignore
|-- README.md
|
|-- portal/                               # React frontend
|   |-- src/
|   |   |-- main.tsx                      # Entry point
|   |   |-- App.tsx                       # Root component
|   |   |-- router.tsx                    # Role-aware routing
|   |   |-- index.css                     # Tailwind imports
|   |   |-- keycloak.ts                   # Keycloak client init
|   |   |-- auth/
|   |   |   |-- AuthProvider.tsx          # Auth context (dev + keycloak)
|   |   |   |-- roles.ts                 # Role definitions and utilities
|   |   |-- api/
|   |   |   |-- httpClient.ts            # Axios instance + auth interceptor
|   |   |   |-- hrisCoreClient.ts        # Typed API client
|   |   |-- components/
|   |   |   |-- Layout.tsx               # Shell: sidebar + navbar + content
|   |   |   |-- Sidebar.tsx              # Role-aware navigation
|   |   |   |-- Navbar.tsx               # Top bar with user info
|   |   |   |-- StatCard.tsx             # KPI metric card
|   |   |   |-- ModuleCard.tsx           # Module summary card
|   |   |   |-- ProtectedRoute.tsx       # Auth guard wrapper
|   |   |   |-- LoadingSpinner.tsx
|   |   |   |-- ErrorMessage.tsx
|   |   |-- pages/
|   |       |-- DashboardPage.tsx        # Main dashboard (role-differentiated)
|   |       |-- EmployeeListPage.tsx     # Staff records table
|   |       |-- EmployeeDetailPage.tsx   # Employee 360 (tabbed)
|   |       |-- ReportsPage.tsx          # Report catalog
|   |       |-- NotFoundPage.tsx
|   |       |-- modules/
|   |       |   |-- AppraisalPage.tsx    # eAppraisal module view
|   |       |   |-- LeavePage.tsx        # eLeave module view
|   |       |-- admin/
|   |           |-- RolesPage.tsx        # Role mapping reference
|   |           |-- TenantManagementPage.tsx
|   |-- package.json
|   |-- tailwind.config.js
|   |-- vite.config.ts
|   |-- Dockerfile
|   |-- .env
|
|-- hris-core-api/                        # FastAPI integration layer
|   |-- app/
|   |   |-- main.py
|   |   |-- core/
|   |   |   |-- auth.py                  # Auth + role resolution
|   |   |   |-- settings.py             # Configuration
|   |   |-- api/
|   |   |   |-- me.py                    # /me endpoint
|   |   |   |-- dashboard.py            # /dashboard/summary
|   |   |   |-- employees.py            # /employees + /employees/{id}/summary
|   |   |-- clients/
|   |   |   |-- srms_client.py           # SRMS API client
|   |   |   |-- eappraisal_client.py     # eAppraisal API client
|   |   |   |-- eleave_client.py         # eLeave API client
|   |   |-- services/
|   |   |   |-- tenant_registry_client.py
|   |   |-- models/
|   |       |-- tenant_mapping.py
|   |-- requirements.txt
|   |-- Dockerfile
|   |-- .env
|
|-- tenant-registry-service/              # Tenant mapping microservice
|   |-- app/
|   |   |-- main.py
|   |   |-- core/
|   |   |   |-- database.py
|   |   |   |-- settings.py
|   |   |-- api/
|   |   |   |-- tenants.py
|   |   |-- models/
|   |   |   |-- tenant.py
|   |   |-- schemas/
|   |   |   |-- tenant.py
|   |   |-- dependencies/
|   |       |-- db.py
|   |-- requirements.txt
|   |-- Dockerfile
|   |-- .env
|
|-- identity/                             # Keycloak configuration
|   |-- realm-export.json                 # Realm with clients, roles, users
|
|-- infra/                                # Infrastructure configs
|   |-- db-init/
|   |   |-- tenant_registry_dev_seed.sql
|   |-- nginx/
|       |-- hris-core-api.conf
|       |-- hris-portal.conf
|       |-- keycloak.conf
|
|-- docs/                                 # Architecture and API documentation
|   |-- architecture/
|   |-- api-contracts/
|   |-- ops/
|
|-- staff-records/                        # Production SRMS codebase (reference)
|-- performance-appraisal/                # Production eAppraisal codebase (reference)
|-- eleave/                               # Production eLeave codebase (reference)
```

---

## Workflow Summary

### Development Workflow

1. Clone repo
2. Run: docker compose up --build -d (or run backend + frontend manually)
3. Open http://localhost:3000 (dev mode, no login required)
4. Edit portal/src/ files (hot reload via Vite)
5. Edit hris-core-api/app/ files (hot reload via uvicorn --reload)
6. Test different roles by changing DEV_DEFAULT_ROLES
7. When ready for SSO testing, use docker compose with the keycloak override
8. Log in as different users to verify role-based views

### Production Workflow

1. Deploy Keycloak with realm import and production clients
2. Deploy PostgreSQL and Tenant Registry with real tenant mappings
3. Configure SRMS, eAppraisal, eLeave to accept Keycloak JWTs
4. Deploy HRIS Core API with AUTH_MODE=keycloak, USE_STUB_DATA=false
5. Build Portal with production VITE env vars, serve behind Nginx with TLS
6. Verify SSO flow end-to-end: Portal to Keycloak to Portal to Core API to Modules