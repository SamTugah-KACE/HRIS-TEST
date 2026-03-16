
---

## 3. `docs/architecture/01-identity-and-tenant-model.md`
  
```markdown
# 01 – Identity and Tenant Model

## 1. Identity Provider: Keycloak

The HRIS Platform uses **Keycloak** as the centralized Identity Provider (IdP).

### 1.1 Realm

- Realm name: `hris-platform`
- Purpose: Centralizes:
  - Users
  - Roles (RBAC)
  - Client configurations (HRIS Portal, SRMS, eAppraisal, eLeave, HRIS Core API)

### 1.2 Clients

Configured OIDC clients include:

- `hris-portal` – public/browser client (React Portal)
- `hris-core-api` – confidential client (FastAPI BFF)
- `srms-api` – confidential client (SRMS backend)
- `eappraisal-api` – confidential client (eAppraisal backend)
- `eleave-api` – confidential client (eLeave backend)

Each module validates tokens issued by this realm using JWKS.

### 1.3 Roles

Roles are modeled as **realm roles** and/or **client roles**:

Examples:

- Realm roles:
  - `hris:super_admin`
  - `hris:tenant_admin`
  - `hris:hr_manager`
  - `hris:line_manager`
  - `hris:employee`

Modules may maintain **local RBAC** but should map or interpret these global roles for coarse-grained access control.

### 1.4 Token Claims

Access tokens and ID tokens include the following relevant claims:

- `sub` – global user identifier
- `preferred_username` – login username
- `email` – user email (optional, but recommended)
- `realm_access.roles` – global roles
- `tenant_id` – **global tenant identifier**

The `tenant_id` claim is required for module access. If absent, modules reject the token with `403 Forbidden`.

---

## 2. Tenant Model

The platform defines a single canonical tenant model, backed by the **Tenant Registry Service**.

### 2.1 Global Tenant Identifier

- `tenant_id` is a UUID-like string.
- It represents one logical organization, regardless of the module or database model used.

### 2.2 Tenant Registry

A central service (or component of `hris-core-api`) maintains:

- `tenant_id`
- `code` – short code for organization (e.g. GI-KACE)
- `name`
- `srms_schema` – SRMS PostgreSQL schema name, or `null` if SRMS not enabled for the tenant
- `eappraisal_schema` – eAppraisal PostgreSQL schema name
- `eleave_db_name` – eLeave tenant database key
- `base_domain` – optional base domain or subdomain
- `is_active` – active/inactive flag
- Additional configuration (branding, feature flags, etc.)

### 2.3 Tenant Resolution Flow (Backend)

1. Backend receives a request with `Authorization: Bearer <token>`.
2. Token is validated against Keycloak JWKS.
3. `tenant_id` is extracted from token claims.
4. Backend calls Tenant Registry Service:
   - `GET /tenants/{tenant_id}`
5. Tenant Registry responds with schema / DB mapping.
6. Backend initializes tenant context based on module:
   - SRMS / eAppraisal: `SET search_path` to relevant schema.
   - eLeave: initialize Stancl tenancy with the resolved tenant DB name.

If the tenant is inactive or mapping is missing, the request is rejected (typically `403 Forbidden`).

---

## 3. Relationship Between Keycloak and Tenant Registry

- Keycloak holds user and role information.
- Tenant Registry holds tenant mapping and configuration.
- `tenant_id` appears in both:
  - As a claim in Keycloak tokens.
  - As a primary key in the Tenant Registry.
- Keycloak does not store schema names or DB names. Those remain in the Tenant Registry.

---

This identity and tenant model ensures:

- **Single Sign-On** across all modules.
- **Consistent tenant isolation**, even across different multi-tenancy strategies.
- **Future-proofing** for additional modules and integrations.
