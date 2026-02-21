
---

## 2️⃣ Updated `docs/api-contracts/eleave-integration-contract.md`

Now reflecting the actual **tenant-subdomain** pattern:

```markdown
# eLeave Integration API Contract

This document describes the eLeave APIs that the **HRIS Core API** is allowed to call.

> ⚠️ Note: eLeave is deployed as:
> - `https://{tenant_subdomain}.eleave.com.gh/`
>
> For example:
> - `https://gigov.eleave.com.gh/`
>
> The `{tenant_subdomain}` is required in the URL structure for routing, but **tenant identity is enforced using `tenant_id` from the Keycloak token + Tenant Registry**, not by trusting the subdomain alone.

---

## 1. Base URL Pattern

For HRIS integration, the base URL is:

- **Production:** `https://{tenant_subdomain}.eleave.com.gh`

HRIS Core API will construct URLs like:

- `https://{tenant_subdomain}.eleave.com.gh/hris/leaves/summary`
- `https://{tenant_subdomain}.eleave.com.gh/hris/employees/{employee_id}/leaves`

The actual subdomain (`{tenant_subdomain}`) is obtained by HRIS Core API from the Tenant Registry entry for the given `tenant_id`.

---

## 2. Authentication

HRIS Core API includes the Keycloak access token in the `Authorization` header:

```http
Authorization: Bearer <access_token>
