# START HERE (Beginner Guide)

This repo contains a **multi-tenant HRIS platform** composed of:

- **Portal** (`apps/frontend/portal/`): React + TypeScript (Vite) UI.
- **HRIS Core API** (`apps/backend/hris-core-api/`): FastAPI “Backend-for-Frontend” that the Portal calls.
- **Tenant Registry** (`apps/backend/tenant-registry-service/`): FastAPI service that maps a global `tenant_id` to each module’s native identifiers.
- **Identity** (`identity/`): Keycloak realm export used for SSO and RBAC.

Team-specific app entry docs:

- Backend collaborators: `apps/backend/README.md`
- Frontend collaborators: `apps/frontend/README.md`

If you’re new to the codebase, read this in order:

1. `README.md` (high-level tour + run commands)
2. `docs/GLOSSARY.md` (key terms like tenant_id, BFF, SSO, module handoff)
3. `docs/CODEBASE_TOUR.md` (where to change what)
4. Saved implementation package:
   - `docs/implementation/00-current-state-and-master-roadmap.md`
   - `docs/implementation/01-team-distribution-and-delivery-board.md`
   - `docs/implementation/02-standardized-directory-structure-and-migration-map.md`
   - `docs/implementation/03-phase-1-execution-checklist.md`
   - `docs/implementation/04-implementation-readiness-gate.md`
   - `docs/implementation/05-portal-migration-pilot-plan.md`
   - `docs/implementation/06-top-level-ownership-map.md`
   - `docs/security/production-hardening-no-stubs.md`
   - `docs/api-contracts/write/common-hris-write-contract.md`
5. Collaboration standards:
   - `docs/collaboration/00-collaboration-playbook.md`
   - `docs/collaboration/01-pr-review-definition-of-done.md`
6. Deep dives:
   - `docs/architecture/hris-system-design-erd-and-module-sync-playbook.md`
   - `docs/architecture/01-identity-and-tenant-model.md`
7. **iFrame integration** (read this if you touch ModuleFrame, Sidebar, Navbar, or any module's index.js):
   - `docs/architecture/iframe-bridge-protocol.md` — complete postMessage protocol reference
   - `docs/ops/module-integration-deployment.md` — step-by-step deployment guide for all environments

---

## Daily development: production-like path

Development should use real local services and fail closed when a dependency is unavailable. Runtime stub data is no longer a normal development path; use test mocks only inside automated tests.

### Option A: run everything locally

- Install dependencies:
  - Python: `pip install -r apps/backend/tenant-registry-service/requirements.txt && pip install -r apps/backend/hris-core-api/requirements.txt`
  - Portal: `cd apps/frontend/portal && npm install`
- Start all 3 services with health gates:
  - `python scripts/start_local_stack.py --registry-port 8001 --core-port 8000 --portal-port 5173 --timeout 300 --auto-registry-port-fallback`

Open:

- Portal: `http://127.0.0.1:5173`
- Core API docs: `http://127.0.0.1:8000/docs`
- Registry docs: `http://127.0.0.1:8001/docs`

### Option B: run via Docker

- Generate the ignored Docker environment from the working Core API `.env`:
  - `python scripts/prepare_docker_dev_env.py`
- Start and wait for the complete stack:
  - `docker compose --env-file .env.docker.development -f docker-compose.yml -f docker-compose.keycloak.yml up -d --build --wait`

Open:

- Portal: `http://localhost:5173`
- Core API docs: `http://localhost:8000/docs`
- Registry docs: `http://localhost:8001/docs`
- GraphQL Gateway: `http://localhost:8010/graphql`
- Keycloak: `http://localhost:8080/admin`

Docker startup makes the APIs ready first and then runs tenant discovery, user
discovery, Keycloak enrollment, and invitations as a durable background job.
Watch it with `docker compose logs -f hris-core-api`; inspect the authoritative
job result through the enrollment job APIs described in
`docs/ops/enrollment-jobs-email-and-keycloak-reset.md`.

---

## Understanding the request flow (one picture in words)

1. **Portal** sends requests to **Core API**.
2. **Core API** authenticates user through Keycloak-backed SSO.
3. **Core API** resolves `tenant_id` via **Tenant Registry**.
4. **Core API** calls SRMS / eAppraisal / eLeave and aggregates results.

If you only remember one thing: **Portal talks to Core; Core talks to everything else.**
