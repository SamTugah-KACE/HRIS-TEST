# Frontend Entry Guide

This is the primary entry point for frontend collaborators.

## Scope

- `apps/frontend/portal/`: React + TypeScript HRIS shell UI

## Quick Start

### Install frontend dependencies

```bash
cd apps/frontend/portal
npm install
```

### Run frontend only

```bash
cd apps/frontend/portal
npm run dev
```

Optional federated gateway mode:

```bash
# in apps/frontend/portal/.env (or .env.local)
VITE_USE_GRAPHQL_GATEWAY=true
VITE_HRIS_GATEWAY_API_BASE_URL=http://localhost:8010
```

### Run full local stack (recommended)

```bash
python scripts/start_local_stack.py --registry-port 8001 --core-port 8000 --portal-port 5173 --timeout 300 --auto-registry-port-fallback
```

## Where to Work

- Routing: `apps/frontend/portal/src/router.tsx`
- Auth and role state: `apps/frontend/portal/src/auth/`
- API integration: `apps/frontend/portal/src/api/`
- Shared UI: `apps/frontend/portal/src/components/`
- Pages: `apps/frontend/portal/src/pages/`

## Guardrails

- Do not hardcode module-native links as final behavior; use Core handoff flow.
- Keep role-aware UI behavior consistent with backend authorization.
- Handle loading/empty/error states explicitly on critical screens.
