# Apps Scaffold

This directory is the standardized home for deployable HRIS applications.

Team entry points:

- Backend collaborators: `apps/backend/README.md`
- Frontend collaborators: `apps/frontend/README.md`

Current status:

- Grouped app layout is active.
- Frontend and backend apps are separated for clearer team ownership.

Target app locations:

- `apps/frontend/portal/`
- `apps/backend/hris-core-api/`
- `apps/backend/tenant-registry-service/`
- `apps/backend/gateway/` (federated-style GraphQL aggregation layer)

Current layout policy:

- Do not recreate the former root-level application directories.
- Validate local and Docker startup after path/build-context changes.
- Do not implement changes under `modules/` as part of HRIS runtime refactor.
