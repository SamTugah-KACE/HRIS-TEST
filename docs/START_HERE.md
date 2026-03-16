# START HERE (Beginner Guide)

This repo contains a **multi-tenant HRIS platform** composed of:

- **Portal** (`portal/`): React + TypeScript (Vite) UI.
- **HRIS Core API** (`hris-core-api/`): FastAPI “Backend-for-Frontend” that the Portal calls.
- **Tenant Registry** (`tenant-registry-service/`): FastAPI service that maps a global `tenant_id` to each module’s native identifiers.
- **Identity** (`identity/`): Keycloak realm export used for SSO and RBAC.

If you’re new to the codebase, read this in order:

1. `README.md` (high-level tour + run commands)
2. `docs/GLOSSARY.md` (key terms like tenant_id, BFF, stub mode)
3. `docs/CODEBASE_TOUR.md` (where to change what)
4. Deep dives:
   - `docs/architecture/hris-system-design-erd-and-module-sync-playbook.md`
   - `docs/architecture/01-identity-and-tenant-model.md`

---

## Daily development: simplest path

### Option A: run everything locally (fast iteration)

- Install dependencies:
  - Python: `pip install -r tenant-registry-service/requirements.txt && pip install -r hris-core-api/requirements.txt`
  - Portal: `cd portal && npm install`
- Start all 3 services with health gates:
  - `python scripts/start_local_stack.py --registry-port 8001 --core-port 8000 --portal-port 5173 --timeout 300 --auto-registry-port-fallback`

Open:

- Portal: `http://127.0.0.1:5173`
- Core API docs: `http://127.0.0.1:8000/docs`
- Registry docs: `http://127.0.0.1:8001/docs`

### Option B: run via Docker (more production-like)

- `python scripts/start_docker_stack.py --keycloak-mode`

Open:

- Portal: `http://localhost:3000`
- Keycloak: `http://localhost:8080/admin`

---

## Understanding the request flow (one picture in words)

1. **Portal** sends requests to **Core API**.
2. **Core API** authenticates user (dev headers or Keycloak).
3. **Core API** resolves `tenant_id` via **Tenant Registry**.
4. **Core API** calls SRMS / eAppraisal / eLeave and aggregates results.

If you only remember one thing: **Portal talks to Core; Core talks to everything else.**

