# HRIS Platform

A multi-tenant Human Resource Information System that consolidates three independent production modules -- **Staff Records (SRMS)**, **Performance Appraisal (eAppraisal)**, and **Leave Management (eLeave)** -- into a unified portal with role-based dashboards, single sign-on, and cross-module data aggregation.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Component Reference](#2-component-reference)
3. [Portal Features and Pages](#3-portal-features-and-pages)
4. [Quick Start with Docker](#4-quick-start-with-docker)
5. [Development Setup without Docker](#5-development-setup-without-docker)
6. [Seeded Data and Login Credentials](#6-seeded-data-and-login-credentials)
7. [Role System and Permissions](#7-role-system-and-permissions)
8. [API Reference](#8-api-reference)
9. [Production Module Integration](#9-production-module-integration)
10. [Production Deployment Guide](#10-production-deployment-guide)
11. [Environment Variables](#11-environment-variables)
12. [Project Structure](#12-project-structure)

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
- **Role-based dashboards**: The portal renders completely different views based on the user's HRIS role. Managers see org-wide analytics; employees see self-service tools.

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

The portal is the user-facing entry point. It authenticates users via Keycloak (or dev mode), determines their role, and renders role-appropriate dashboards by calling the HRIS Core API. In dev mode, a **Role Switcher** component in the navbar lets you instantly switch between all 5 roles without restarting.

### 2.2 HRIS Core API (hris-core-api/)

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
| app/clients/srms_client.py | HTTP client calling SRMS APIs (with stub fallback) |
| app/clients/eappraisal_client.py | HTTP client calling eAppraisal APIs (with stub fallback) |
| app/clients/eleave_client.py | HTTP client calling eLeave APIs (with stub fallback) |
| app/services/tenant_registry_client.py | Resolves tenant_id to module-specific mappings |
| app/models/tenant_mapping.py | Pydantic model for tenant mapping data |

**Auth modes** (controlled by AUTH_MODE):

| Mode | Behavior |
|------|----------|
| dev | Trusts `X-Debug-Roles` and `X-Debug-Username` headers, or falls back to DEV_DEFAULT env vars. No token required. |
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
- Open eAppraisal deep-link button

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
- Open eLeave deep-link button

**Employee view:**
- Apply for Leave button opens multi-step Leave Application Modal
- Leave Balances section: visual progress bars per leave type (Annual, Sick, Casual, Study, Compassionate) showing total, used, pending, and available days
- Leave History table: clickable rows with type, days, period, and status badges
- Export leave history button
- Upcoming Public Holidays panel (Independence Day, Good Friday, Easter Monday, May Day, Eid al-Fitr)
- Open eLeave deep-link button

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

## 4. Quick Start with Docker

### Prerequisites

- Docker Desktop (with Docker Compose v2)
- Ports 3000, 5432, 8000, 8001, 8080 available

### Option A: Dev Mode (fastest, no login screen)

```bash
docker compose up --build -d
```

Wait about 60 seconds for all services to start, then open:

| Service | URL |
|---------|-----|
| Portal | http://localhost:3000 |
| HRIS Core API Docs | http://localhost:8000/docs |
| Tenant Registry Docs | http://localhost:8001/docs |
| Keycloak Admin | http://localhost:8080/admin |

In dev mode, the portal auto-authenticates as hr.manager. Use the **Role Switcher** in the navbar to switch between all 5 roles instantly -- no restarts needed.

### Option B: Keycloak SSO Mode (full authentication)

```bash
docker compose -f docker-compose.yml -f docker-compose.keycloak.yml up --build -d
```

Wait about 90 seconds (Keycloak takes longer to import the realm), then open:

| Service | URL |
|---------|-----|
| Portal | http://localhost:3000 (redirects to Keycloak login) |
| Keycloak Admin | http://localhost:8080/admin (admin / admin) |

Log in with any of the seeded credentials listed in Section 6.

### Useful Docker Commands

```bash
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

---

## 5. Development Setup without Docker

### Prerequisites

- Node.js 18+
- Python 3.9+
- PostgreSQL 14+ (only needed if USE_STUB_DATA=false)

### Backend: HRIS Core API

```bash
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

```bash
curl http://localhost:8000/health
curl http://localhost:8000/me
curl http://localhost:8000/dashboard/summary
curl http://localhost:8000/employees
curl http://localhost:8000/employees/e001/summary
```

### Backend: Tenant Registry Service (optional in dev)

Only needed when USE_STUB_DATA=false. The Core API returns stub tenant data in dev mode.

```bash
cd tenant-registry-service

python -m venv venv
venv\Scripts\activate

pip install -r requirements.txt

# Requires PostgreSQL running with database hris_tenant_registry
# Edit .env with your DATABASE_URL

python -m uvicorn app.main:app --reload --port 8001
```

### Frontend: Portal

```bash
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
| 1 | `cd hris-core-api && python -m uvicorn app.main:app --reload --port 8000` | http://localhost:8000 |
| 2 | `cd portal && npm run dev` | http://localhost:5173 |

---

## 6. Seeded Data and Login Credentials

### Keycloak Admin Console

| Field | Value |
|-------|-------|
| URL | http://localhost:8080/admin |
| Username | admin |
| Password | admin |

### Application Users (Keycloak SSO Mode)

All users belong to the Development Tenant (tenant_id: `11111111-1111-1111-1111-111111111111`).

| Username | Password | Email | Role | Dashboard View |
|----------|----------|-------|------|----------------|
| super.admin | Admin@123 | super.admin@hris.local | hris:super_admin | System Administration: all tenants, all modules, admin panels |
| tenant.admin | Admin@123 | tenant.admin@hris.local | hris:tenant_admin | Organization Dashboard: org structure, all modules, roles, reports |
| hr.manager | Admin@123 | hr.manager@hris.local | hris:hr_manager | HR Dashboard: staff records, appraisals, leaves, reports |
| line.manager | Admin@123 | line.manager@hris.local | hris:line_manager | Team Dashboard: team members, team appraisals, leave approvals |
| employee | Admin@123 | employee@hris.local | hris:employee | My Dashboard: self-service profile, appraisals, leave |

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

1. **Authentication**: User logs in via Keycloak. Token includes `tenant_id` and `roles` claims.
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
| GET | /me | Required | Current user identity, tenant info, module enablement |
| GET | /dashboard/summary | Required | Aggregated dashboard data from all modules plus role-specific quick actions |
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
KEYCLOAK_AUDIENCE_HRIS_CORE=hris-core-api
TENANT_REGISTRY_BASE_URL=http://tenant-registry:8000
SRMS_BASE_URL=https://srms.example.com
EAPPRAISAL_DOMAIN_TEMPLATE=https://appraisal.{subdomain}.example.com
ELEAVE_DOMAIN_TEMPLATE=https://{subdomain}.eleave.example.com
```

---

## 11. Environment Variables

### Portal (portal/.env)

| Variable | Required | Default | Description |
|----------|:--------:|---------|-------------|
| VITE_HRIS_CORE_API_BASE_URL | Yes | - | URL of the HRIS Core API |
| VITE_AUTH_MODE | Yes | dev | `dev` (no login, with role switcher) or `keycloak` (SSO) |
| VITE_KEYCLOAK_URL | If keycloak | - | Keycloak server URL |
| VITE_KEYCLOAK_REALM | If keycloak | - | Keycloak realm name |
| VITE_KEYCLOAK_CLIENT_ID | If keycloak | - | Keycloak client ID |

### HRIS Core API (hris-core-api/.env)

| Variable | Required | Default | Description |
|----------|:--------:|---------|-------------|
| AUTH_MODE | Yes | dev | `dev` or `keycloak` |
| USE_STUB_DATA | Yes | true | true returns mock data; false calls real modules |
| DEV_DEFAULT_TENANT_ID | If dev | - | Tenant ID for dev user |
| DEV_DEFAULT_USERNAME | If dev | - | Username for dev user |
| DEV_DEFAULT_ROLES | If dev | hris:hr_manager | Comma-separated HRIS roles (overridden by X-Debug-Roles header) |
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

## 12. Project Structure

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
|   |   |-- index.css                     # Tailwind imports + custom classes
|   |   |-- keycloak.ts                   # Keycloak client init
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
|-- hris-core-api/                        # FastAPI integration layer
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
|-- staff-records/                        # Production SRMS codebase (reference only)
|-- performance-appraisal/                # Production eAppraisal codebase (reference only)
|-- eleave/                               # Production eLeave codebase (reference only)
```

---

## Workflow Summary

### Development Workflow

1. Clone the repo
2. Start both servers: backend (port 8000) and frontend (port 5173)
3. Open http://localhost:5173 (dev mode, no login required)
4. Use the **Role Switcher** in the navbar to test all 5 role dashboards instantly
5. Edit `portal/src/` files (hot reload via Vite)
6. Edit `hris-core-api/app/` files (hot reload via uvicorn --reload)
7. Check the **Notification Panel** for sample notifications
8. Test the **Leave Application Modal** as an employee
9. Test the **Profile Page** tabs as an employee
10. Test **Staff Records** bulk actions and **Reports** generation as a manager
11. When ready for SSO testing, use Docker with the keycloak override
12. Log in as different users to verify role-based views

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
| Role Switcher not appearing | Verify `VITE_AUTH_MODE=dev` in `portal/.env`. Role Switcher only shows in dev mode. |
| API returns 401 Unauthorized | In dev mode, ensure `AUTH_MODE=dev` in `hris-core-api/.env`. In keycloak mode, check token expiry. |
| Role switch doesn't change backend data | Ensure `httpClient.ts` sends `X-Debug-Roles` header and the Core API reads it in `auth.py`. |
| Docker containers fail to start | Run `docker compose down -v` for a clean start. Check port conflicts with `netstat -an`. |
| Keycloak realm not imported | Wait 90+ seconds. Check Keycloak logs: `docker compose logs keycloak`. |
| Employee sees Staff Records list | Verify the redirect guard in `EmployeeListPage.tsx` is active and the role resolved correctly. |
| Profile page shows no data | This is expected in dev mode with stub data. The profile displays hardcoded mock data. |

### Verifying the Stack

```bash
# Check all services are running
docker compose ps

# Test Core API health
curl http://localhost:8000/health

# Test with a specific role (dev mode)
curl -H "X-Debug-Roles: hris:employee" -H "X-Debug-Username: employee" http://localhost:8000/dashboard/summary

# View Tenant Registry data
curl -u hris_internal:registry_secret http://localhost:8001/tenants
```
