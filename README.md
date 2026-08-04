# HRIS Platform

A multi-tenant Human Resource Information System that consolidates three independent production modules -- **Staff Records (SRMS)**, **Performance Appraisal (eAppraisal)**, and **Leave Management (eLeave)** -- into a unified portal with role-based dashboards, single sign-on, and cross-module data aggregation.

New contributors should begin with `docs/START_HERE.md` for the current collaboration workflow, scope boundaries, and migration checklist.

---

## Table of Contents

- [Quick Command Cheat Sheet](#quick-command-cheat-sheet)
1. [Architecture Overview](#1-architecture-overview)
2. [Component Reference](#2-component-reference)
3. [Portal Features and Pages](#3-portal-features-and-pages)
4. [Current Startup Guide (Docker)](#4-current-startup-guide-docker)
5. [Current Startup Guide (Without Docker)](#5-current-startup-guide-without-docker)
6. [Seeded Data and Login Credentials](#6-seeded-data-and-login-credentials)
7. [Role System and Permissions](#7-role-system-and-permissions)
8. [API Reference](#8-api-reference)
9. [Production Module Integration](#9-production-module-integration)
10. [Production Deployment Guide](#10-production-deployment-guide)
11. [Environment Variables](#11-environment-variables)
12. [Project Structure](#12-project-structure)

---

## Quick Command Cheat Sheet

Use these commands as the safest defaults for first-time setup and repeat runs.

| Scenario | Command | Purpose |
|----------|---------|---------|
| Docker development env | `python scripts/prepare_docker_dev_env.py` | Generates ignored `.env.docker.development` from the local Core API `.env`. |
| Docker first run (recommended) | `docker compose --env-file .env.docker.development -f docker-compose.yml -f docker-compose.keycloak.yml up -d --build --wait` | Builds, starts, and health-gates the complete stack. |
| Docker subsequent run | `docker compose --env-file .env.docker.development -f docker-compose.yml -f docker-compose.keycloak.yml up -d --wait` | Starts without forcing an image rebuild. |
| Docker stop | `docker compose --env-file .env.docker.development -f docker-compose.yml -f docker-compose.keycloak.yml down` | Stops containers while keeping volumes/data. |
| Docker clean reset | `docker compose --env-file .env.docker.development -f docker-compose.yml -f docker-compose.keycloak.yml down -v` | Destructively removes local containers and volumes. |
| Local Keycloak start (realm import) | `KC_BOOTSTRAP_ADMIN_USERNAME=admin KC_BOOTSTRAP_ADMIN_PASSWORD=admin <kc-bin> start-dev --http-port 8080 --import-realm` | Starts local Keycloak in dev mode with admin bootstrap and realm import. |
| Local first-time backend deps | `pip install -r apps/backend/tenant-registry-service/requirements.txt && pip install -r apps/backend/hris-core-api/requirements.txt` | Installs Python dependencies for both backend services. |
| Local first-time frontend deps | `cd apps/frontend/portal && npm install && cd ../../..` | Installs portal dependencies once. |
| Local run (recommended) | `python scripts/start_local_stack.py --registry-port 8001 --core-port 8000 --portal-port 5173 --timeout 300 --auto-registry-port-fallback` | Starts core, tenant registry, and portal with health gates in one terminal. |
| Superadmin pre-check | `python scripts/onboard_keycloak_superadmin.py --show-account-identities` | Shows detected operator identity/groups before privileged write. |
| Superadmin onboarding (secure local) | `python scripts/onboard_keycloak_superadmin.py --username "<preferred-username>" --auth-kind local --account-auth-mode session --enforce-group-authorization` | Securely creates/updates Keycloak superadmin with confirmation, group authorization, and audit logs. |
| Superadmin onboarding (secure SSH) | `python scripts/onboard_keycloak_superadmin.py --username "<preferred-username>" --auth-kind ssh --account-auth-mode session --enforce-group-authorization` | Same secure onboarding flow for SSH operators. |
| Portal login target (local) | `http://localhost:5173/admin/tenants` | Recommended superadmin landing route after onboarding. |
| Portal login target (docker) | `http://localhost:5173/admin/tenants` | Recommended superadmin landing route after onboarding. |

### Backend-only commands

```bash
# install backend deps
pip install -r apps/backend/tenant-registry-service/requirements.txt
pip install -r apps/backend/hris-core-api/requirements.txt

# run backend services manually
cd apps/backend/tenant-registry-service && python -m uvicorn app.main:app --reload --port 8001
cd apps/backend/hris-core-api && python -m uvicorn app.main:app --reload --port 8000
```

### Frontend-only commands

```bash
# install frontend deps
cd apps/frontend/portal && npm install

# run frontend dev server
cd apps/frontend/portal && npm run dev
```

---

## 1. Architecture Overview

The platform follows a Backend-for-Frontend (BFF) pattern where the Portal calls the HRIS Core API, which in turn aggregates data from the three production modules.

- **Portal (React, port 5173)** authenticates the user via Keycloak and renders role-based dashboards.
- **HRIS Core API (FastAPI, port 8000)** validates the token, resolves the tenant, calls each module API, and returns consolidated data.
- **Keycloak (port 8080)** manages users, roles, and SSO across all modules.
- **Tenant Registry (FastAPI, port 8001)** maps global tenant IDs to each module's native identifiers.
- **SRMS, eAppraisal, eLeave** remain as independent production systems, called via their REST APIs.

### Design Principles

- **Explicit module contracts**: Production modules remain independently deployed, but each must expose the versioned HRIS tenant/user inventory and handoff contracts required by consolidation.
- **Unified identity**: Keycloak is the single source of truth for authentication and role assignment.
- **Tenant isolation**: A central Tenant Registry maps a global tenant_id to each module's native tenant identifier (schema name, subdomain, or database).
- **Role-based dashboards**: The portal renders completely different views based on the user's HRIS role. Managers see org-wide analytics; employees see self-service tools.

---

## 2. Component Reference

### 2.1 Portal (apps/frontend/portal/)

| Attribute | Value |
|-----------|-------|
| Technology | React 18, TypeScript, Vite 6 |
| Styling | Tailwind CSS 3 |
| Charts | Recharts |
| Icons | Lucide React |
| Auth | Core-managed OIDC authorization-code flow with HttpOnly session cookies; isolated dev bypass for tests/diagnostics |
| Port | 5173 (local and Docker host) |

The portal is the user-facing entry point. In normal runtime it uses the Core
API's `/auth/sso/*` endpoints and credentialed cookies; browser JavaScript does
not persist access tokens. Isolated dev mode retains the role switcher for
diagnostics and automated UI work.

### 2.2 HRIS Core API (apps/backend/hris-core-api/)

| Attribute | Value |
|-----------|-------|
| Technology | FastAPI (Python) |
| Auth | Keycloak JWT validation or dev mode with X-Debug headers |
| Port | 8000 |
| Role | Backend-for-Frontend (BFF) |

The integration and aggregation layer. It receives requests from the portal, resolves the tenant, calls each production module's API, and returns consolidated responses. In dev mode, the portal sends `X-Debug-Roles` and `X-Debug-Username` headers so the backend returns role-appropriate quick actions and user context.

**Key files:**

| File | Purpose |
|------|---------|
| app/main.py | FastAPI app, CORS middleware, router registration |
| app/core/auth.py | Auth dependency (dev/keycloak), role resolution, require_roles() |
| app/core/settings.py | Pydantic Settings with all config |
| app/api/me.py | /me endpoint returning current user identity and tenant info |
| app/api/dashboard.py | /dashboard/summary with role-specific quick actions |
| app/api/employees.py | /employees list and /employees/{id}/summary (360 view) |
| app/clients/srms_client.py | HTTP client calling SRMS APIs |
| app/clients/eappraisal_client.py | HTTP client calling eAppraisal APIs |
| app/clients/eleave_client.py | HTTP client calling eLeave APIs |
| app/services/tenant_registry_client.py | Resolves tenant_id to module-specific mappings |
| app/models/tenant_mapping.py | Pydantic model for tenant mapping data |

**Auth modes** (controlled by AUTH_MODE):

| Mode | Behavior |
|------|----------|
| dev | Isolated diagnostics/tests only; never expose this mode on a shared or production network. |
| keycloak | Validates Keycloak JWT using JWKS. Extracts tenant_id and roles from claims. |

`USE_STUB_DATA=true` is test-only. Normal development, Docker, staging, and production fail closed when required dependencies are unavailable.

### 2.3 Tenant Registry Service (apps/backend/tenant-registry-service/)

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
| Technology | Keycloak 26.5.4 |
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

## 3. Portal Features and Pages

### 3.1 Dev Mode Role Switcher

In dev mode, a **Role Switcher** button appears in the top navbar showing the current role as a colored badge. Clicking it opens a dropdown to instantly switch between all 5 HRIS roles. The switch:

- Updates the frontend user context and re-renders the entire UI (sidebar, dashboard, module pages)
- Sends the selected role via `X-Debug-Roles` header to the backend so API responses (quick actions, user info) also reflect the new role
- Persists the selection in localStorage across page refreshes
- Each role maps to a realistic user profile (super.admin, tenant.admin, hr.manager, line.manager, employee)

### 3.2 Interactive Notification Panel

The bell icon in the navbar opens a full notification panel with:

- Color-coded notifications by type (leave, appraisal, staff, system, message)
- Unread count badge on the bell icon
- Mark individual notifications as read or dismiss them
- "Mark All as Read" button
- Action links on notifications (e.g., "Start Assessment", "Update Now")
- 6 realistic sample notifications

### 3.3 Pages by Route

| Route | Page | Available To | Description |
|-------|------|:------------:|-------------|
| `/` | Dashboard | All roles | Role-differentiated dashboard (see below) |
| `/profile` | My Profile | All roles | Comprehensive employee self-service profile |
| `/employees` | Staff Records | Managers only | Searchable, filterable employee table with bulk actions |
| `/employees/:id` | Employee 360 | Managers only | Tabbed view: Profile, Appraisals, Leave History |
| `/modules/appraisal` | Appraisal | All roles | Manager view or Employee self-assessment view |
| `/modules/leave` | Leave | All roles | Manager approval view or Employee leave management |
| `/reports` | Reports | HR Manager+ | Cross-module report catalog with generation |
| `/admin/roles` | Roles & Permissions | Tenant Admin+ | Consolidated role mapping reference |
| `/admin/tenants` | Tenant Management | Tenant Admin+ | Tenant list with module enablement |

Employees navigating to `/employees` are automatically redirected to `/profile`.

### 3.4 Dashboard Page (/)

The dashboard is fully role-differentiated:

**Managers (Super Admin, Tenant Admin, HR Manager, Line Manager):**

- Title varies by role: "System Administration", "Organization Dashboard", "HR Dashboard", or "Team Dashboard"
- 6 org-wide KPI stat cards (Total Staff, Active Staff, Departments, Pending Reviews, Pending Leave, Avg Score)
- HR Modules section with 3 module cards showing org-wide stats (active employees, branches, appraisal completion rate, leave utilization)
- Staff Overview bar chart and Leave Distribution pie chart
- Role-specific quick actions from the backend API

**Employee:**

- Title: "My Dashboard" with subtitle "Your personal HR services at a glance"
- 4 personal KPI cards (Leave Balance, Leave Taken, Pending Requests, Appraisal Status)
- "My Services" section with 3 personalized module cards:
  - **My Profile**: department, branch, staff ID, status
  - **My Appraisals**: current cycle, score, status, due date
  - **My Leave**: annual balance, used days, pending requests, sick leave
- Upcoming events panel (appraisal deadlines, pending requests, public holidays)
- Recent activity panel (submissions, completions)
- Self-service quick actions (Apply for Leave, My Appraisal, My Profile)
- No charts or org-wide stats

### 3.5 Profile Page (/profile)

A comprehensive 5-tab employee self-service profile:

**Profile Header:**
- Gradient header with avatar initials, name, position, department
- Quick stats bar (years of service, leave balance, appraisal score, certifications)
- Edit Profile button with camera icon on avatar hover

**Personal Info tab:**
- Basic information (name, date of birth, gender, marital status, nationality)
- Contact details (work email, personal email, phone, addresses)
- Identification (Ghana Card, SSNIT, TIN)
- Inline edit mode with Save/Cancel buttons and toast notifications

**Employment tab:**
- Current position details (organization, branch, department, unit, rank, grade level)
- Service details (hire date, confirmation date, supervisor)
- Position history timeline with visual indicators

**Qualifications tab:**
- Academic qualifications displayed as cards (degree, institution, year, grade)
- Professional certifications (AWS, PMP, etc.)
- Trainings and workshops
- Add Qualification button

**Emergency Contacts tab:**
- Primary and secondary contacts with relationship, phone, email
- Edit and Add buttons for each contact

**Documents tab:**
- Uploaded documents table (employment letters, certificates, ID documents, photos)
- Category, type, size, and upload date columns
- Download and Upload Document buttons

### 3.6 Staff Records Page (/employees) -- Managers Only

- Add Employee and Export buttons in the header
- Search by name, staff ID, or email
- Department filter dropdown (IT, HR, Finance, Administration, Legal)
- Status filter (Active, Inactive, All)
- Reset Filters button
- Checkbox selection on each row with Select All in header
- Bulk actions bar appears when rows are selected (Send Email, Export Selected, Clear Selection)
- Employee rows show avatar initials, name, email, staff ID, department, branch, status badge
- Action icons per row (View 360 Profile, Send Email, More Options)
- Numbered page buttons in pagination with "Showing X-Y of Z" display
- Employees accessing this route are automatically redirected to `/profile`

### 3.7 Employee 360 Page (/employees/:id)

- Back to Staff Records link
- Employee header card with avatar, name, position, department, status badge, employee type, staff ID, branch
- 3 tabs with counts: Profile, Appraisals, Leave History
- Profile tab: Personal Information and Organization cards with icon-labeled fields
- Appraisals tab: Table with cycle name, score, rating, status, date
- Leave History tab: Table with type, days, start date, end date, status

### 3.8 Appraisal Page (/modules/appraisal)

**Manager view:**
- 4 stat cards (Active Cycles, Completed, Pending, Overdue)
- Team Progress panel: each team member with avatar, sections completed, score or "In Progress"
- Recent Activity panel: staff submissions, completions, change requests with timestamps
- Batch Actions: Send Reminders, Generate Report, Export Data buttons
- HRIS-native-first flow badges (`native`, `native-readonly`) for clear employee/manager context
- `Open legacy eAppraisal` button is fallback-only (`legacy-fallback`) for unsupported workflows

**Employee view:**
- Current Cycle card with gradient header showing cycle name, due date, and overall progress percentage with animated progress bar
- Section-by-section checklist (Key Result Areas, Core Competencies, Leadership & Initiative, Learning & Development, Supervisor Assessment) with:
  - Completion status (completed, in progress, not started, locked)
  - Weight percentage and score per section
  - Clickable arrow to open each section
- Goals & Objectives tracker with:
  - Individual progress bars per goal
  - Priority badges (High, Medium)
  - Due dates and completion percentages
  - Add Goal button
- General Comment textarea with Save Comment button
- Past Appraisals history (3 previous cycles with scores, ratings, dates)
- Past appraisal entries support read-only drilldown via Core API history endpoint
- Performance trend insight ("Your performance trend is improving")

### 3.9 Leave Page (/modules/leave)

**Manager view:**
- 4 stat cards (Total This Year, Approved, Pending, Rejected)
- Pending Leave Requests table with:
  - Employee name, department, leave type, duration, dates, relief officer, applied date
  - Approve and Reject buttons per request with visual feedback after action
  - View details button
  - Export and Remind All buttons in header
- Quick Reports section (Utilization Report, Leave Calendar, Export All Data)
- HRIS-native-first flow badges with fallback marker (`legacy-fallback`)
- Legacy eLeave button is fallback-only for missing features

**Employee view:**
- Apply for Leave button opens multi-step Leave Application Modal
- Leave Balances section: visual progress bars per leave type (Annual, Sick, Casual, Study, Compassionate) showing total, used, pending, and available days
- Leave History table: clickable rows with type, days, period, and status badges
- Export leave history button
- Upcoming Public Holidays panel (Independence Day, Good Friday, Easter Monday, May Day, Eid al-Fitr)
- Optional legacy eLeave link (fallback only)

### 3.10 Leave Application Modal

A multi-step modal dialog accessed from the employee Leave page:

**Step 1 -- Form:**
- Leave type dropdown showing available balance per type (Annual, Sick, Casual, Maternity, Paternity, Study, Compassionate)
- Start and end date pickers
- Calculated day count with remaining balance display
- Relief officer dropdown
- Reason textarea
- File attachment area (drag & drop or browse, PDF/JPG/PNG up to 5MB)
- Cancel and Submit Application buttons

**Step 2 -- Confirmation:**
- Summary card showing leave type, duration, dates, relief officer, and reason
- Back to Edit and Confirm & Submit buttons

**Step 3 -- Success:**
- Animated success icon
- Confirmation message with description that supervisor will be notified

### 3.11 Reports Page (/reports) -- HR Manager+

- Category filter pills: All Reports, Staff Records, Appraisal, Leave, Cross-Module
- 9 report types:
  - Staff Summary Report (PDF/Excel)
  - Department Headcount (Excel/CSV)
  - New Hires Report (PDF/Excel)
  - Appraisal Cycle Report (PDF)
  - Performance Trend Analysis (PDF/Excel)
  - Leave Utilization Report (PDF/Excel)
  - Leave Calendar Report (PDF)
  - Cross-Module Employee 360 (PDF)
  - Attrition Analysis (PDF/Excel)
- Format selector dropdown per report
- Generate button with loading spinner animation
- Download button appears after generation with "Ready to download" indicator
- Schedule Reports button in header

### 3.12 Roles & Permissions Page (/admin/roles) -- Tenant Admin+

Documented consolidated role mapping showing HRIS role hierarchy and how each role maps to native roles in SRMS, eAppraisal, and eLeave.

### 3.13 Tenant Management Page (/admin/tenants) -- Tenant Admin+

Lists seeded tenants with their codes, names, and module enablement status (SRMS, eAppraisal, eLeave).

---

## 4. Current Startup Guide (Docker)

Use this path when you want a production-like environment with Keycloak SSO, Postgres, and all services orchestrated by Compose.

### 4.1 Prerequisites

- Docker Desktop (Compose v2)
- Python 3.9+ (for `scripts/start_docker_stack.py`)
- free ports: `5173`, `5432`, `8000`, `8001`, `8010`, `8080`, `5050`

### 4.2 First-Time Docker Setup (one-time)

1. Configure `apps/backend/hris-core-api/.env`, then generate the ignored Docker-development environment:

```bash
python scripts/prepare_docker_dev_env.py
```

Windows PowerShell:

```powershell
python scripts/prepare_docker_dev_env.py
```

2. Update minimum required values in `apps/backend/hris-core-api/.env`, then regenerate:
- `HRIS_AUTH_STATE_SECRET`
- `HRIS_KEYCLOAK_CLIENT_ID_PORTAL` (normally `hris-portal`)
- `HRIS_TENANT_REGISTRY_BASIC_AUTH_PASSWORD`

3. Recommended enrollment settings:
- `ENABLE_STARTUP_TENANT_INVENTORY_IMPORT=false`
- `ENABLE_STARTUP_EAPPRAISAL_TENANT_INVENTORY_IMPORT=false`
- `ENROLLMENT_WORKER_ENABLED=true`
- `ENROLLMENT_REFRESH_TENANT_INVENTORY=true`
- `STARTUP_FEDERATED_ENROLLMENT_MODE=discover` for a safe first production-like run; explicitly queue `apply` after reviewing discovery
- `FEDERATED_KEYCLOAK_SYNC_MAX_USERS_PER_RUN=0` to process the complete discovered directory

4. Recommended secure credential-delivery settings:
- `HRIS_ONBOARDING_WELCOME_EMAIL_ENABLED=true`
- `HRIS_POST_DEPLOY_WELCOME_EMAILS_ENABLED=true`
- use Keycloak expiring required-action links; do not email reusable passwords in production
- `HRIS_ONBOARDING_DEV_CREDENTIALS_EXPORT_ENABLED=false`
- configure all `HRIS_SMTP_*` values

### 4.3 First Run (recommended command)

```bash
docker compose --env-file .env.docker.development -f docker-compose.yml -f docker-compose.keycloak.yml up -d --build --wait
```

Command purpose:
- validates and resolves the two Compose files and generated environment
- starts stack with wait gates (`--wait`)
- verifies HTTP readiness (`tenant-registry`, `hris-core-api`, `portal`, `keycloak`)
- prints `docker compose ps` when complete

Optional wrappers:

```bash
bash scripts/start-docker-stack.sh --keycloak-mode
```

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-docker-stack.ps1 -KeycloakMode
```

### 4.4 Subsequent Docker Runs

Fast restart (skip image rebuild):

```bash
docker compose --env-file .env.docker.development -f docker-compose.yml -f docker-compose.keycloak.yml up -d --wait
```

Stop stack:

```bash
docker compose --env-file .env.docker.development -f docker-compose.yml -f docker-compose.keycloak.yml down
```

Full clean reset (containers + volumes):

```bash
docker compose --env-file .env.docker.development -f docker-compose.yml -f docker-compose.keycloak.yml down -v
```

### 4.5 Docker URLs

| Service | URL |
|---------|-----|
| Portal | http://localhost:5173 |
| HRIS Core API Docs | http://localhost:8000/docs |
| Tenant Registry Docs | http://localhost:8001/docs |
| Keycloak Admin | http://localhost:8080/admin |
| pgAdmin | http://localhost:5050 |

### 4.6 Superadmin Onboarding While Using Docker

Run these from repo root on the host machine (the onboarding script calls Keycloak admin APIs over HTTP):

```bash
python scripts/onboard_keycloak_superadmin.py --show-account-identities
```

Purpose: display detected operator identity and groups before enforcement.

Windows recommended secure command:

```powershell
set HRIS_SUPERADMIN_ONBOARD_ALLOWED_GROUPS=HRIS-Onboarding-Admins,Administrators
python scripts/onboard_keycloak_superadmin.py --username "<preferred-username>" --auth-kind local --account-auth-mode session --enforce-group-authorization
```

Linux/macOS recommended secure command:

```bash
export HRIS_SUPERADMIN_ONBOARD_ALLOWED_GROUPS="hris-onboarding-admins,sudo"
python scripts/onboard_keycloak_superadmin.py --username "<preferred-username>" --auth-kind ssh --account-auth-mode session --enforce-group-authorization
```

Purpose: onboard a unique Keycloak user, enforce operator authorization, require interactive confirmation, assign `hris:super_admin`, and write audit records.

After onboarding, sign in at:
- `http://localhost:5173/admin/tenants` (portal)

### 4.7 Useful Docker Commands

```bash
# all service logs
docker compose logs -f

# only core logs
docker compose logs -f hris-core-api

# restart only core
docker compose restart hris-core-api
```

---

## 5. Current Startup Guide (Without Docker)

Use this path when you run services directly on your machine (uvicorn + Vite), without Docker containers.

### 5.1 Prerequisites

- Python 3.9+
- Node.js 18+
- npm 9+
- PostgreSQL 14+ (required when `USE_STUB_DATA=false`; optional for pure stub mode)

### 5.2 Install and Run Keycloak Locally (SSO Mode Prerequisite)

If you will run HRIS in `AUTH_MODE=keycloak` without Docker, start Keycloak first before launching other services.

#### 5.2.1 Install Java 17

Keycloak requires Java 17+.

Windows (PowerShell, via winget):

```powershell
winget install EclipseAdoptium.Temurin.17.JDK
java -version
```

macOS (Homebrew):

```bash
brew install openjdk@17
java -version
```

Ubuntu/Debian:

```bash
sudo apt-get update
sudo apt-get install -y openjdk-17-jdk curl tar
java -version
```

#### 5.2.2 Download and Extract Keycloak

Set a version and install path:

Windows (PowerShell):

```powershell
$KC_VERSION = "26.1.0"
$KC_ARCHIVE = "keycloak-$KC_VERSION.zip"
$KC_URL = "https://github.com/keycloak/keycloak/releases/download/$KC_VERSION/$KC_ARCHIVE"
Invoke-WebRequest -Uri $KC_URL -OutFile $KC_ARCHIVE
Expand-Archive -Path $KC_ARCHIVE -DestinationPath .
$env:KEYCLOAK_HOME = (Resolve-Path ".\keycloak-$KC_VERSION").Path
```

macOS/Linux:

```bash
KC_VERSION="26.1.0"
KC_ARCHIVE="keycloak-${KC_VERSION}.tar.gz"
KC_URL="https://github.com/keycloak/keycloak/releases/download/${KC_VERSION}/${KC_ARCHIVE}"
curl -L "$KC_URL" -o "$KC_ARCHIVE"
tar -xzf "$KC_ARCHIVE"
export KEYCLOAK_HOME="$PWD/keycloak-${KC_VERSION}"
```

#### 5.2.3 Import HRIS Realm Configuration

Copy the project realm file into Keycloak import directory:

Windows (PowerShell):

```powershell
New-Item -ItemType Directory -Force -Path "$env:KEYCLOAK_HOME\data\import" | Out-Null
Copy-Item ".\identity\realm-export.json" "$env:KEYCLOAK_HOME\data\import\hris-platform-realm.json"
```

macOS/Linux:

```bash
mkdir -p "$KEYCLOAK_HOME/data/import"
cp "./identity/realm-export.json" "$KEYCLOAK_HOME/data/import/hris-platform-realm.json"
```

#### 5.2.4 Start Keycloak

Windows (PowerShell):

```powershell
$env:KC_BOOTSTRAP_ADMIN_USERNAME = "admin"
$env:KC_BOOTSTRAP_ADMIN_PASSWORD = "admin"
& "$env:KEYCLOAK_HOME\bin\kc.bat" start-dev --http-port 8080 --import-realm
```

macOS/Linux:

```bash
export KC_BOOTSTRAP_ADMIN_USERNAME="admin"
export KC_BOOTSTRAP_ADMIN_PASSWORD="admin"
"$KEYCLOAK_HOME/bin/kc.sh" start-dev --http-port 8080 --import-realm
```

Expected checks:
- Keycloak admin console: `http://localhost:8080/admin`
- realm exists: `hris-platform`
- admin credentials: `admin` / `admin` (change for non-dev use)

#### 5.2.5 Configure HRIS for Local Keycloak

Before starting HRIS services, confirm these values:

`apps/backend/hris-core-api/.env`:
- `AUTH_MODE=keycloak`
- `KEYCLOAK_ISSUER=http://localhost:8080/realms/hris-platform`
- `KEYCLOAK_JWKS_URL=http://localhost:8080/realms/hris-platform/protocol/openid-connect/certs`
- `KEYCLOAK_CLIENT_ID_PORTAL=hris-portal`
- `AUTH_STATE_SECRET=<strong-random-value>`

`apps/frontend/portal/.env` (or your Vite env source):
- `VITE_AUTH_MODE=keycloak`
- `VITE_HRIS_CORE_API_BASE_URL=http://localhost:8000`

### 5.3 First-Time Local Setup (one-time)

Install backend dependencies:

```bash
pip install -r apps/backend/tenant-registry-service/requirements.txt
pip install -r apps/backend/hris-core-api/requirements.txt
```

Install frontend dependencies:

```bash
cd apps/frontend/portal
npm install
cd ..
```

### 5.4 First Run / Daily Run (recommended)

Cross-platform local startup:

```bash
python scripts/start_local_stack.py --registry-port 8001 --core-port 8000 --portal-port 5173 --timeout 300 --auto-registry-port-fallback
```

Windows PowerShell wrapper:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-local-stack.ps1
```

### 5.5 What the Local Startup Command Does

- starts services in controlled order:
  1. `apps/backend/hris-core-api` (`8000`)
  2. `tenant-registry` (`8001`)
  3. `portal` (`5173`)
- waits for health between stages
- supports automatic tenant-registry port fallback when requested
- streams prefixed logs in one terminal

### 5.6 Expected Results (Local)

On successful startup:
- tenant registry starts and initializes required entities
- core API starts and serves `/health` + `/docs`
- portal serves Vite UI at `http://localhost:5173`

Expected URLs:

| Service | URL |
|---------|-----|
| Tenant Registry Docs | http://127.0.0.1:8001/docs |
| HRIS Core API Docs | http://127.0.0.1:8000/docs |
| Portal | http://127.0.0.1:5173 |

### 5.7 Subsequent Local Runs

Use the same command as first run:

```bash
python scripts/start_local_stack.py --registry-port 8001 --core-port 8000 --portal-port 5173 --timeout 300 --auto-registry-port-fallback
```

Stop all services:
- press `Ctrl+C` in the terminal running `start_local_stack.py`

### 5.8 Manual Local Startup (advanced)

Use this only when debugging individual services or isolating startup failures:

```bash
# terminal 1
cd apps/backend/hris-core-api
python -m uvicorn app.main:app --reload --port 8000

# terminal 2
cd apps/backend/tenant-registry-service
python -m uvicorn app.main:app --reload --port 8001

# terminal 3
cd apps/frontend/portal
npm run dev
```

### 5.9 Superadmin Onboarding While Running Local Stack

If your local stack is running in Keycloak mode (or your Keycloak is external but reachable), onboarding command is the same:

```bash
python scripts/onboard_keycloak_superadmin.py --show-account-identities
```

Purpose: inspect detected operator account + groups before enforcement.

```bash
python scripts/onboard_keycloak_superadmin.py --username "<preferred-username>" --auth-kind local --account-auth-mode session --enforce-group-authorization
```

Purpose: securely create/update a Keycloak `hris:super_admin` user with guardrails and audit logging.

If Keycloak is not at default `http://localhost:8080`, pass:

```bash
python scripts/onboard_keycloak_superadmin.py --username "<preferred-username>" --base-url "<keycloak-base-url>" --auth-kind local --account-auth-mode session --enforce-group-authorization
```

### 5.10 UI Smoke Test Workflow (after startup)

Run this checklist for either local or Docker startup:

1. Open portal:
- local: `http://localhost:5173`
- docker: `http://localhost:5173`

2. Verify session/auth entry:
- dev mode: auto-login or local sign-in appears
- keycloak mode: HRIS-native sign-in page appears and login succeeds

3. Validate core API reachability:
- open `http://localhost:8000/docs`
- call `/health` and `/me`

4. Validate role-aware UI:
- switch roles (dev mode Role Switcher)
- confirm dashboard and navigation differ by role

5. Validate key pages:
- `/` dashboard
- `/profile`
- `/employees` (manager roles)
- `/modules/appraisal`
- `/modules/leave`
- `/reports` (HR manager+)

6. Validate interaction flows:
- submit leave application modal as employee
- test manager leave approval actions
- open appraisal page and confirm native/fallback badges

7. Validate backend integration surfaces:
- `GET /dashboard/summary`
- `GET /employees`
- `GET /employees/{id}/summary`
- `GET /modules/appraisal`
- `GET /modules/leave`

8. Optional keycloak verification (docker keycloak mode):
- open Keycloak admin (`http://localhost:8080/admin`)
- confirm realm `hris-platform` is present
- verify seeded users can authenticate

### 5.11 Startup Verification Commands

```bash
# Core health
curl http://localhost:8000/health

# Tenant registry health
curl http://localhost:8001/health

# Tenant list (dev credentials)
curl -u hris_internal:registry_secret http://localhost:8001/tenants

# Dev role simulation
curl -H "X-Debug-Roles: hris:employee" -H "X-Debug-Username: employee" http://localhost:8000/dashboard/summary
```

---

## 6. Seeded Data and Login Credentials

### Keycloak Admin Console

| Field | Value |
|-------|-------|
| URL | http://localhost:8080/admin |
| Username | admin |
| Password | admin |

### Secure Superadmin Onboarding Command

Use this workflow to create a dedicated Keycloak user with `hris:super_admin` role, with OS/account verification, group-based authorization, confirmation gates, and audit logging.

```bash
python scripts/onboard_keycloak_superadmin.py --username "<preferred-username>"
```

### Step-by-step (works with Docker or without Docker)

1. Ensure Keycloak is reachable and admin credentials are valid.
2. Inspect current operator identities/groups:

```bash
python scripts/onboard_keycloak_superadmin.py --show-account-identities
```

3. Set allowed operator groups (recommended).
4. Run secure onboarding command and complete interactive prompts.
5. Login through portal and verify `Super Admin` dashboard access.

### Recommended Commands and Purpose

| Command | Purpose |
|---------|---------|
| `python scripts/onboard_keycloak_superadmin.py --show-account-identities` | Shows detected local/SSH identities and operator groups before any write. |
| `python scripts/onboard_keycloak_superadmin.py --username "<preferred-username>" --auth-kind local --account-auth-mode session --enforce-group-authorization` | Standard secure local onboarding flow with group authorization and session trust. |
| `python scripts/onboard_keycloak_superadmin.py --username "<preferred-username>" --auth-kind ssh --account-auth-mode session --enforce-group-authorization` | Secure SSH-based onboarding for remote operators. |
| `python scripts/onboard_keycloak_superadmin.py --username "<preferred-username>" --base-url "<keycloak-base-url>" --auth-kind local --account-auth-mode session --enforce-group-authorization` | Same secure flow against non-default Keycloak endpoint. |
| `python scripts/onboard_keycloak_superadmin.py --username "<preferred-username>" --allow-existing --auth-kind local --account-auth-mode session --enforce-group-authorization` | Reconcile an existing Keycloak user and ensure superadmin role/password are updated. |

Windows example:

```powershell
set HRIS_SUPERADMIN_ONBOARD_ALLOWED_GROUPS=HRIS-Onboarding-Admins,Administrators
python scripts/onboard_keycloak_superadmin.py --username "<preferred-username>" --auth-kind local --account-auth-mode session --enforce-group-authorization
```

Linux/macOS example:

```bash
export HRIS_SUPERADMIN_ONBOARD_ALLOWED_GROUPS="hris-onboarding-admins,sudo"
python scripts/onboard_keycloak_superadmin.py --username "<preferred-username>" --auth-kind ssh --account-auth-mode session --enforce-group-authorization
```

Post-onboarding login URLs:
- local no-docker portal: `http://localhost:5173/admin/tenants`
- docker portal: `http://localhost:5173/admin/tenants`

What the command enforces by default:
- prompts for new superadmin password (not echoed)
- auto-detects execution account and validates operator authority
- requires confirmation phrase before privileged write
- checks username/email uniqueness in Keycloak before create
- assigns realm role `hris:super_admin`
- writes security audit events (without secrets)

Optional flags:
- `--email <email>`
- `--tenant-id <tenant-uuid>`
- `--allow-existing` (updates role/password for existing account)
- `--skip-os-auth` (not recommended)
- `--os-username` / `--os-domain` (override auto-detected OS identity when needed)
- `--auth-kind auto|local|ssh`
- `--ssh-auth-host` / `--ssh-auth-port` (for SSH account verification)
- `--account-auth-mode auto|session|password`
- `--show-account-identities` (prints detected local/SSH account principals and exits)
- `--allowed-group <group>` (repeatable allowlist for authorized operators)
- `--allowed-groups-env <ENV_NAME>` (default: `HRIS_SUPERADMIN_ONBOARD_ALLOWED_GROUPS`)
- `--enforce-group-authorization` (require membership in allowlisted groups)
- `--audit-log-path <path>` (JSONL audit file path)
- `--disable-audit-log` (not recommended)

Audit behavior:
- writes one JSON line per operation outcome (success/failure)
- logs operator identity, auth mode/kind, tenant, target username, stage, and error summary
- never logs passwords
- default path: `logs/security/superadmin_onboarding_audit.jsonl`
- override path via `--audit-log-path` or env `HRIS_SUPERADMIN_ONBOARD_AUDIT_LOG_PATH`

Allowed groups intent (why this exists):
- session auth confirms *who is currently logged in*, but not whether they are allowed to create superadmins
- allowed groups enforce least privilege by restricting command execution to approved operator groups
- this reduces insider-risk and accidental privileged user creation from non-admin developer accounts
- if allowed groups are configured, enforcement is fail-closed (non-members are blocked)

How to add groups:
- pass groups directly with `--allowed-group` repeatedly
- or set comma-separated groups in `HRIS_SUPERADMIN_ONBOARD_ALLOWED_GROUPS`
- on Windows, groups can be full names like `BUILTIN\Administrators` or short names like `Administrators`
- on Linux/macOS, use local/LDAP group names returned by `id -Gn`
- use `--show-account-identities` to inspect detected operator groups before enforcing
- one-time bootstrap behavior:
  - if enforcement is enabled and allowlist is missing or does not authorize current operator, the command can prompt you to select one detected operator group
  - it writes the selected group to dedicated tooling env file `.env.superadmin-onboard` (`HRIS_SUPERADMIN_ONBOARD_ALLOWED_GROUPS`) and marks bootstrap done (`HRIS_SUPERADMIN_ONBOARD_GROUP_BOOTSTRAP_DONE=true`)
  - after bootstrap is marked done, missing/mismatched allowlist fails closed with a clear message until explicitly corrected
- allowlist values are read from process env first, then fallback env files (`.env.superadmin-onboard`, `apps/backend/hris-core-api/.env`, then repo `.env`) for backward compatibility
- to persist this beyond the current shell/session, set the environment variable manually in your shell profile or deployment environment

Recommended secure usage:
- always keep `--enforce-group-authorization` enabled
- maintain allowlist in environment or dedicated onboarding env file
- avoid `--skip-os-auth` except tightly controlled break-glass workflows

### Application Users (Keycloak SSO Mode)

All users belong to the Development Tenant (tenant_id: `11111111-1111-1111-1111-111111111111`).

| Username | Password | Email | Role | Dashboard View |
|----------|----------|-------|------|----------------|
| super.admin | Admin@123 | super.admin@hris.local | hris:super_admin | System Administration: all tenants, all modules, admin panels |
| tenant.admin | Admin@123 | tenant.admin@hris.local | hris:tenant_admin | Organization Dashboard: org structure, all modules, roles, reports |
| hr.manager | Admin@123 | hr.manager@hris.local | hris:hr_manager | HR Dashboard: staff records, appraisals, leaves, reports |
| line.manager | Admin@123 | line.manager@hris.local | hris:line_manager | Team Dashboard: team members, team appraisals, leave approvals |
| employee | Admin@123 | employee@hris.local | hris:employee | My Dashboard: self-service profile, appraisals, leave |

### Optional Admin Bootstrap (Local/Non-Production)

If seeded users do not exist in your Keycloak realm, you can bootstrap admin users from environment variables during HRIS Core startup.

Set the following in `apps/backend/hris-core-api/.env` (or process env), then restart `apps/backend/hris-core-api`:

```env
BOOTSTRAP_ADMIN_ENABLED=true
BOOTSTRAP_SUPERADMIN_USERNAME=super.admin
BOOTSTRAP_SUPERADMIN_EMAIL=super.admin@hris.local
BOOTSTRAP_SUPERADMIN_PASSWORD=<strong-password>
BOOTSTRAP_SUPERADMIN_TENANT_ID=11111111-1111-1111-1111-111111111111
BOOTSTRAP_TENANTADMIN_USERNAME=tenant.admin
BOOTSTRAP_TENANTADMIN_EMAIL=tenant.admin@hris.local
BOOTSTRAP_TENANTADMIN_PASSWORD=<strong-password>
BOOTSTRAP_TENANTADMIN_TENANT_ID=11111111-1111-1111-1111-111111111111
```

Security notes:
- keep bootstrap credentials out of git-tracked files in shared environments
- use only in local/dev/staging bootstrap workflows
- rotate or disable (`BOOTSTRAP_ADMIN_ENABLED=false`) after successful sign-in

### Dev Mode Role Switcher

In dev mode, the portal provides an in-app Role Switcher in the navbar. Click the colored role badge to switch between all 5 roles instantly. Each role maps to a realistic user profile:

| Role | Dev Username | Dev Email |
|------|-------------|-----------|
| Super Admin | super.admin | super.admin@hris.local |
| Tenant Admin | tenant.admin | tenant.admin@hris.local |
| HR Manager | hr.manager | hr.manager@hris.local |
| Line Manager | line.manager | line.manager@hris.local |
| Employee | employee | employee@hris.local |

The selected role persists in localStorage across page refreshes. Both the frontend UI and backend API responses (via `X-Debug-Roles` header) update to match the selected role.

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

### Stub Profile Data (Employee View)

When viewing the Profile page (`/profile`), the following comprehensive mock data is displayed:

| Field | Value |
|-------|-------|
| Full Name | Kwame Osei Asante |
| Staff ID | STF-001 |
| Position | Senior Software Engineer |
| Department | Information Technology |
| Branch | Head Office |
| Email | kwame.asante@gi-kace.gov.gh |
| Phone | +233 24 123 4567 |
| Supervisor | Dr. Ama Mensah (Director of IT) |
| Hire Date | 2020-01-15 |
| Grade Level | Grade 14 |
| Qualifications | BSc Computer Science (UG), MSc Information Technology (KNUST), AWS Solutions Architect, PMP |
| Emergency Contact | Akua Asante (Spouse) |

---

## 7. Role System and Permissions

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
| Dashboard title | System Administration | Organization Dashboard | HR Dashboard | Team Dashboard | My Dashboard |
| KPI stats grid | 6 org-wide | 6 org-wide | 6 org-wide | 6 org-wide | 4 personal |
| Module cards section | HR Modules | HR Modules | HR Modules | HR Modules | My Services |
| Staff/Appraisal/Leave charts | Yes | Yes | Yes | Yes | No |
| Upcoming events & activity | No | No | No | No | Yes |
| Quick actions (manage) | Yes | Yes | Yes | Yes | No |
| Quick actions (self-service) | No | No | No | No | Yes |
| Staff Records (/employees) | Full list | Full list | Full list | Full list | Redirects to /profile |
| Profile page (/profile) | Yes | Yes | Yes | Yes | Yes |
| Appraisal (manager view) | Yes | Yes | Yes | Yes | No |
| Appraisal (employee view) | No | No | No | No | Yes |
| Leave (manager view) | Yes | Yes | Yes | Yes | No |
| Leave (employee view + apply) | No | No | No | No | Yes |
| Reports page | Yes | Yes | Yes | No | No |
| Roles & Permissions page | Yes | Yes | No | No | No |
| Tenant Management page | Yes | Yes | No | No | No |
| Role Switcher (dev mode) | Yes | Yes | Yes | Yes | Yes |
| Notification Panel | Yes | Yes | Yes | Yes | Yes |

### Consolidated Role Mapping to Production Modules

| HRIS Role | SRMS Native Roles | eAppraisal Native Roles | eLeave Native Roles |
|-----------|-------------------|-------------------------|---------------------|
| hris:super_admin | Super Admin | System Admin (public) | SuperAdmin (tenant mgmt) |
| hris:tenant_admin | Admin, CEO | SYSTEM ADMINISTRATOR | Admin |
| hris:hr_manager | HR Manager, Branch Manager | HUMAN RESOURCE | HR |
| hris:line_manager | Manager, Department Head, HoD | STAFF (with review perms) | DG, Director |
| hris:employee | Employee, Staff | STAFF | Normal |

### How Authorization Works

1. **Authentication**: User signs in from HRIS-native login UI. HRIS Core runs OIDC Authorization Code + PKCE with Keycloak and stores tokens in secure HttpOnly cookies. Token includes `tenant_id` and `roles` claims.
2. **HRIS Core API**: Extracts roles from token, resolves `effective_role` (highest role wins). In dev mode, reads `X-Debug-Roles` header from the portal.
3. **Tenant resolution**: `tenant_id` is used to look up module-specific identifiers from the Tenant Registry.
4. **Module calls**: The Core API forwards the Keycloak Bearer token to each production module. The module uses its own native RBAC for fine-grained authorization.
5. **Portal rendering**: Frontend reads `effective_role` and conditionally renders dashboards, navigation, module pages, and actions. Employees see completely different UI components than managers.

---

## 8. API Reference

### HRIS Core API (http://localhost:8000)

Interactive docs: http://localhost:8000/docs

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | /health | None | Health check |
| GET | /auth/sso/start | None | Start OIDC Authorization Code + PKCE flow via Keycloak |
| GET | /auth/sso/callback | None | Backend callback to exchange auth code and set secure session cookies |
| GET | /auth/sso/session | Session cookie | Returns active authenticated user session |
| POST | /auth/sso/refresh | Session cookie | Refreshes session cookies using Keycloak refresh token |
| POST | /auth/sso/logout | Session cookie | Clears HRIS session cookies |
| GET | /me | Required | Current user identity, tenant info, module enablement |
| GET | /dashboard/summary | Required | Aggregated dashboard data from all modules plus role-specific quick actions |
| GET | /employees | Required | Paginated employee list (search, department, status filters) |
| GET | /employees/{id}/summary | Required | Employee 360: profile plus appraisals plus leave history |
| GET | /modules/appraisal | Required | Appraisal manager + employee payload for HRIS-native pages |
| GET | /modules/appraisal/history/{entry_id} | Required | Read-only appraisal history drilldown detail |
| GET | /modules/leave | Required | Leave manager + employee payload for HRIS-native pages |
| GET | /debug/integrations/eappraisal | Dev-gated | eAppraisal integration diagnostics with safe actionable status |

**Query parameters for /employees:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| search | string | "" | Search by name, staff ID, or email |
| department | string | "" | Filter by department name |
| status | string | "active" | active, inactive, or all |
| page | int | 1 | Page number |
| page_size | int | 20 | Items per page (max 100) |

**Dev mode headers (sent automatically by the portal):**

| Header | Description |
|--------|-------------|
| X-Debug-Roles | Comma-separated HRIS roles (e.g., hris:employee) |
| X-Debug-Username | Username for the dev user (e.g., employee) |
| X-Debug-Tenant-Id | Tenant ID override |

### Tenant Registry API (http://localhost:8001)

Interactive docs: http://localhost:8001/docs

All endpoints require HTTP Basic Auth (`hris_internal` / `registry_secret` in dev).

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /health | Health check |
| GET | /tenants | List all tenants |
| GET | /tenants/{tenant_id} | Get tenant by global ID |

---

## 9. Production Module Integration

The HRIS platform consolidates three independent production systems. It does not modify their codebases.

### 9.1 Staff Records Management System (SRMS)

| Attribute | Value |
|-----------|-------|
| Stack | FastAPI + React + PostgreSQL |
| Multi-tenancy | Schema-per-tenant (tenant_{org_uuid}) |
| Native auth | Username/password, custom JWT, optional facial auth |
| HRIS integration | Via srms_client.py calling SRMS REST APIs with Keycloak Bearer token |

SRMS provides: Employee records, org structure (branches, departments, units, ranks), roles/permissions, messaging, dashboards, bulk enrollment, reporting.

SRMS roles (10 default): Admin, Super Admin, CEO, HR Manager, Branch Manager, Department Head, Manager, HoD, Employee, Staff.

SRMS permissions (100+): Organized by domain including employee, branches, departments, role:manage, hr:dashboard, admin:dashboard, staff:dashboard, and more.

### 9.2 Performance Appraisal (eAppraisal)

| Attribute | Value |
|-----------|-------|
| Stack | FastAPI + Angular + PostgreSQL |
| Multi-tenancy | Schema-per-tenant (subdomain-based) |
| Native auth | Email/password, OAuth2 tokens, refresh tokens |
| HRIS integration | Via eappraisal_client.py calling eAppraisal REST APIs |

eAppraisal provides: Appraisal cycles, templates, sections, submissions, feedback, department groups, organization management.

eAppraisal roles (3 org + system): SYSTEM ADMINISTRATOR, HUMAN RESOURCE, STAFF. System Admin (public schema) bypasses all checks.

eAppraisal permissions (30+): viewTotalStaff, readStaff, createStaff, approveAppraisal, readMyAppraisal, readRoles, createRolePermissions, etc.

### 9.3 Leave Management (eLeave)

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

## 10. Production Deployment Guide

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
KEYCLOAK_AUDIENCE_HRIS_CORE=hris-core-api,hris-portal
TENANT_REGISTRY_BASE_URL=http://tenant-registry:8000
SRMS_BASE_URL=https://srms.example.com
EAPPRAISAL_DOMAIN_TEMPLATE=https://appraisal.{subdomain}.example.com
ELEAVE_DOMAIN_TEMPLATE=https://{subdomain}.eleave.example.com
```

---

## 11. Environment Variables

### Portal (apps/frontend/portal/.env)

| Variable | Required | Default | Description |
|----------|:--------:|---------|-------------|
| VITE_HRIS_CORE_API_BASE_URL | Yes | - | URL of the HRIS Core API |
| VITE_AUTH_MODE | Yes | dev | `dev` (no login, with role switcher) or `keycloak` (HRIS-native sign-in with backend-managed SSO session) |
| VITE_PORTAL_DATA_MODE | No | mock | `mock` (hardcoded UI datasets) or `api` (strictly API-driven pages) |
| VITE_DEV_REQUIRE_LOGIN | No | false | In `dev` mode, show native HRIS sign-in before local role-based login when `true` |

### HRIS Core API (apps/backend/hris-core-api/.env)

| Variable | Required | Default | Description |
|----------|:--------:|---------|-------------|
| AUTH_MODE | Yes | dev | `dev` or `keycloak` |
| USE_STUB_DATA | Yes | true | true returns mock data; false calls real modules |
| DEV_DEFAULT_TENANT_ID | If dev | - | Tenant ID for dev user |
| DEV_DEFAULT_USERNAME | If dev | - | Username for dev user |
| DEV_DEFAULT_ROLES | If dev | hris:hr_manager | Comma-separated HRIS roles (overridden by X-Debug-Roles header) |
| DEV_DEFAULT_EMPLOYEE_ID | If dev | e001 | Default employee identifier for self-service endpoints in dev mode |
| KEYCLOAK_ISSUER | If keycloak | - | Keycloak issuer URL |
| KEYCLOAK_JWKS_URL | If keycloak | - | Keycloak JWKS endpoint |
| KEYCLOAK_AUDIENCE_HRIS_CORE | If keycloak | - | Expected aud claim(s), comma-separated (e.g., `hris-core-api,hris-portal`) |
| KEYCLOAK_TOKEN_URL | No | derived from issuer | Optional explicit Keycloak token endpoint for HRIS-native login proxy |
| KEYCLOAK_AUTHORIZE_URL | No | derived from issuer | Optional explicit Keycloak authorization endpoint |
| KEYCLOAK_END_SESSION_URL | No | - | Optional explicit Keycloak logout endpoint |
| KEYCLOAK_CLIENT_ID_PORTAL | No | hris-portal | Keycloak client ID used by HRIS-native login proxy |
| KEYCLOAK_CLIENT_SECRET_PORTAL | No | - | Optional secret for confidential Keycloak clients |
| PORTAL_BASE_URL | No | http://localhost:5173 | Portal URL used for post-login callback redirect |
| CORS_ALLOWED_ORIGINS | No | localhost UI origins | Comma-separated allowed origins for credentialed CORS |
| AUTH_COOKIE_SECURE | No | false | Set true in HTTPS production so auth cookies are secure-only |
| TENANT_REGISTRY_BASE_URL | Yes | http://localhost:8001 | Tenant Registry URL |
| TENANT_REGISTRY_BASIC_AUTH_USERNAME | Yes | hris_internal | Basic auth username |
| TENANT_REGISTRY_BASIC_AUTH_PASSWORD | Yes | change-me | Basic auth password |
| SRMS_BASE_URL | If not stub | - | SRMS production URL |
| SRMS_SERVICE_TOKEN | No | - | Optional SRMS service token fallback when user token passthrough is unavailable |
| SRMS_APP_TYPE | No | - | Optional `X-App-Type` header for SRMS app-context enforcement |
| SRMS_SESSION_TOKEN | No | - | Optional `X-Session-Token` for SRMS source-validation/session-token encryption flows |
| SRMS_AUTO_SESSION_TOKEN | No | true | Auto-fetch/refresh SRMS session token via `/api/auth/session-token` when needed |
| SRMS_EXTRA_HEADERS_JSON | No | - | Optional JSON object of additional SRMS request headers |
| SRMS_PAYLOAD_SECURITY_MODE | No | auto | `auto`, `plain`, `encrypted_envelope`, or `staff_records_response` for SRMS payload protection handling |
| SRMS_PAYLOAD_SIGNING_SECRET | No | - | Required for `encrypted_envelope`; validates SRMS response HMAC signature |
| SRMS_PAYLOAD_ENCRYPTION_SECRET | No | - | Required for `staff_records_response`; decrypts SRMS `encrypted/data/checksum` response wrappers |
| EAPPRAISAL_DOMAIN_TEMPLATE | If not stub | - | eAppraisal URL template |
| EAPPRAISAL_SERVICE_TOKEN | No | - | Optional eAppraisal service token fallback |
| EAPPRAISAL_REFRESH_TOKEN | No | - | Optional refresh token for auto-recovery of eAppraisal access token |
| EAPPRAISAL_AUTO_REFRESH | No | true | Auto refresh + retry on eAppraisal 401 responses |
| EAPPRAISAL_SUBDOMAIN_HEADER | No | - | Explicit eAppraisal subdomain header override |
| EAPPRAISAL_COOKIE | No | - | Optional cookie override for constrained auth flows |
| ELEAVE_DOMAIN_TEMPLATE | If not stub | - | eLeave URL template |
| ELEAVE_SERVICE_TOKEN | No | - | Optional eLeave service token fallback |
| MODULE_ADAPTER_MODE | No | auto | `auto` (try `/hris` then module-native), `hris_contract`, or `module_native` |
| ELEAVE_USE_TENANT_PATH | No | true | When true, adapter calls eLeave tenant-path endpoints like `/{tenant}/...` |
| ENABLE_INTEGRATION_DEBUG_ENDPOINTS | No | false | Enables `/debug/integrations/*` diagnostics endpoints (dev-only gate) |
| HTTP_CLIENT_TIMEOUT_SECONDS | No | 10 | Timeout for module API calls |

### Tenant Registry (apps/backend/tenant-registry-service/.env)

| Variable | Required | Default | Description |
|----------|:--------:|---------|-------------|
| DATABASE_URL | Yes | - | PostgreSQL connection URL |
| INTERNAL_BASIC_AUTH_USERNAME | Yes | - | Basic auth username |
| INTERNAL_BASIC_AUTH_PASSWORD | Yes | - | Basic auth password |

---

## 12. Project Structure

```
HRIS-Platform/
|-- docker-compose.yml                    # Full local stack (dev mode)
|-- docker-compose.keycloak.yml           # Override for Keycloak SSO mode
|-- .gitignore
|-- README.md
|
|-- apps/frontend/portal/                 # React frontend
|   |-- src/
|   |   |-- main.tsx                      # Entry point
|   |   |-- App.tsx                       # Root component
|   |   |-- router.tsx                    # Role-aware routing
|   |   |-- index.css                     # Tailwind imports + custom classes
|   |   |-- keycloak.ts                   # Legacy/direct adapter helper; normal SSO is Core-managed
|   |   |-- auth/
|   |   |   |-- AuthProvider.tsx          # Auth context with dev role switching
|   |   |   |-- roles.ts                 # Role definitions and utilities
|   |   |-- api/
|   |   |   |-- httpClient.ts            # Axios with X-Debug headers in dev
|   |   |   |-- hrisCoreClient.ts        # Typed API client
|   |   |-- components/
|   |   |   |-- Layout.tsx               # Shell: sidebar + navbar + content
|   |   |   |-- Sidebar.tsx              # Role-aware navigation
|   |   |   |-- Navbar.tsx               # Top bar with role switcher + notifications
|   |   |   |-- RoleSwitcher.tsx         # Dev mode role switching dropdown
|   |   |   |-- NotificationPanel.tsx    # Interactive notification center
|   |   |   |-- LeaveApplicationModal.tsx # Multi-step leave application form
|   |   |   |-- StatCard.tsx             # KPI metric card
|   |   |   |-- ModuleCard.tsx           # Module summary card with link label
|   |   |   |-- ProtectedRoute.tsx       # Auth guard wrapper
|   |   |   |-- LoadingSpinner.tsx
|   |   |   |-- ErrorMessage.tsx
|   |   |-- pages/
|   |       |-- DashboardPage.tsx        # Role-differentiated dashboard
|   |       |-- ProfilePage.tsx          # 5-tab employee self-service profile
|   |       |-- EmployeeListPage.tsx     # Staff records with bulk actions
|   |       |-- EmployeeDetailPage.tsx   # Employee 360 (tabbed)
|   |       |-- ReportsPage.tsx          # Report catalog with generation
|   |       |-- NotFoundPage.tsx
|   |       |-- modules/
|   |       |   |-- AppraisalPage.tsx    # Manager or employee appraisal view
|   |       |   |-- LeavePage.tsx        # Manager approvals or employee leave
|   |       |-- admin/
|   |           |-- RolesPage.tsx        # Role mapping reference
|   |           |-- TenantManagementPage.tsx
|   |-- package.json
|   |-- tailwind.config.js
|   |-- vite.config.ts
|   |-- Dockerfile
|   |-- .env
|
|-- apps/backend/hris-core-api/           # FastAPI integration layer
|   |-- app/
|   |   |-- main.py
|   |   |-- core/
|   |   |   |-- auth.py                  # Auth + role resolution + X-Debug headers
|   |   |   |-- settings.py             # Configuration
|   |   |-- api/
|   |   |   |-- me.py                    # /me endpoint
|   |   |   |-- dashboard.py            # /dashboard/summary with role-specific actions
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
|-- apps/backend/tenant-registry-service/ # Tenant mapping microservice
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
|-- staff-records/                        # Production SRMS codebase (reference only)
|-- performance-appraisal/                # Production eAppraisal codebase (reference only)
|-- eleave/                               # Production eLeave codebase (reference only)
```

---

## Core Adapter Layer Documentation

To run portal **API mode** against current production modules **without waiting for module-native `/hris/...` endpoints**, follow:

- `docs/api-contracts/core-module-adapter-implementation-guide.md`

That guide includes:

- exact Core files/directories to implement (`app/adapters/*`, `module_auth`, `module_identity_map`)
- endpoint mapping from current SRMS/eAppraisal/eLeave routes to Core DTOs
- auth strategy for non-passthrough modules (Sanctum/internal JWT cases)
- tenant + employee identity resolution pattern
- phased rollout checklist for synchronization and safe production cutover

---

## Workflow Summary

### Development Workflow

1. Clone the repo
2. Start the stack using the startup guides in Section 4 (Docker) or Section 5 (without Docker)
3. Open http://localhost:5173 (dev mode, no login required)
4. Use the **Role Switcher** in the navbar to test all 5 role dashboards instantly
5. Edit `apps/frontend/portal/src/` files (hot reload via Vite)
6. Edit `apps/backend/hris-core-api/app/` files (hot reload via uvicorn --reload)
7. Check the **Notification Panel** for sample notifications
8. Test the **Leave Application Modal** as an employee
9. Test the **Profile Page** tabs as an employee
10. Test **Staff Records** bulk actions and **Reports** generation as a manager
11. When ready for SSO testing, run `python scripts/start_docker_stack.py --keycloak-mode`
12. Log in as different users to verify role-based views

### Collaboration Branch Policy (Required)

All collaborators must follow this branch workflow before writing code:

1. Create a new feature branch from `main`.
2. Immediately sync `main` into that branch before starting work (merge latest `main`).
3. Do all changes in that branch only; do not work directly on `main`.
4. Follow the same policy in `CONTRIBUTING.md` for pull-request expectations.

Example:

```bash
git checkout main
git pull origin main
git checkout -b feat/<short-name>
git merge main
```

### Production Workflow

1. Deploy Keycloak with realm import and production clients
2. Deploy PostgreSQL and Tenant Registry with real tenant mappings
3. Configure SRMS, eAppraisal, eLeave to accept Keycloak JWTs
4. Deploy HRIS Core API with AUTH_MODE=keycloak, USE_STUB_DATA=false
5. Build Portal with production VITE env vars, serve behind Nginx with TLS
6. Verify SSO flow end-to-end: Portal -> Keycloak -> Portal -> Core API -> Modules

---

## Troubleshooting

### Common Issues

| Problem | Solution |
|---------|----------|
| Portal shows blank page | Check browser console for errors. Ensure HRIS Core API is running on port 8000. |
| Role Switcher not appearing | Verify `VITE_AUTH_MODE=dev` in `apps/frontend/portal/.env`. Role Switcher only shows in dev mode. |
| API returns 401 Unauthorized | In dev mode, ensure `AUTH_MODE=dev` in `apps/backend/hris-core-api/.env`. In keycloak mode, check token expiry. |
| Role switch doesn't change backend data | Ensure `httpClient.ts` sends `X-Debug-Roles` header and the Core API reads it in `auth.py`. |
| Docker containers fail to start | Use `python scripts/start_docker_stack.py --keycloak-mode` (or the PowerShell wrapper) so compose config and health are validated; then run `docker compose down -v` for a clean reset and check port conflicts with `netstat -an`. |
| Keycloak mode exits during startup | Update `apps/backend/hris-core-api/.env`, rerun `python scripts/prepare_docker_dev_env.py`, validate Compose with `config -q`, and inspect the failing container log. |
| Keycloak realm not imported | Wait 90+ seconds. Check Keycloak logs: `docker compose logs keycloak`; if needed, reset with `docker compose down -v` and start again. |
| Employee sees Staff Records list | Verify the redirect guard in `EmployeeListPage.tsx` is active and the role resolved correctly. |
| Profile page shows no data | This is expected in dev mode with stub data. The profile displays hardcoded mock data. |

### Verifying the Stack

```bash
# Docker: check all services are running
docker compose ps

# Test Core API health
curl http://localhost:8000/health

# Local: tenant-registry health (same endpoint in Docker)
curl http://localhost:8001/health

# Test with a specific role (dev mode)
curl -H "X-Debug-Roles: hris:employee" -H "X-Debug-Username: employee" http://localhost:8000/dashboard/summary

# View Tenant Registry data
curl -u hris_internal:registry_secret http://localhost:8001/tenants
```

### Automated Synchronization Checks

Use the built-in Core sync checker and contract tests before pushes/deploys:

```bash
cd apps/backend/hris-core-api

# Contract + endpoint checks (dev/stub mode)
python scripts/sync_check.py

# Route-mapping audit against modules/* codebases
python scripts/module_contract_audit.py

# Optional live probe (requires token + module env vars)
python scripts/sync_check.py --live

# Optional eAppraisal live diagnostics probe (requires ENABLE_INTEGRATION_DEBUG_ENDPOINTS=true)
python scripts/sync_check.py --live-eappraisal

# Strict release gate (runs both live probes)
python scripts/sync_check.py --strict-live

# Unit-style contract tests
python -m unittest tests/test_sync_contracts.py -v
```

---

## 13. System Design and Integration Delivery Docs

For the comprehensive architecture, ERD, workflows, and module sync execution guide, see:

- `docs/architecture/hris-system-design-erd-and-module-sync-playbook.md`

Module implementation guides:

- `docs/api-contracts/staff-records-integration-implementation-guide.md`
- `docs/api-contracts/performance-appraisal-integration-implementation-guide.md`
- `docs/api-contracts/eleave-integration-implementation-guide.md`
