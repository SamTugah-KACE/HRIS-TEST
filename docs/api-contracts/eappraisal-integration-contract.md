# eAppraisal Integration API Contract

This document describes the eAppraisal APIs that the **HRIS Core API** is allowed to call.

> ℹ️ Note: In production, each tenant’s eAppraisal instance is exposed as:
>
> - `https://appraisal.{tenant_subdomain}.com.gh/`
>
> e.g. `https://appraisal.gigov.com.gh/`
>
> The `{tenant_subdomain}` is resolved by the HRIS Platform using the **Tenant Registry** and the `tenant_id` claim in Keycloak tokens. The subdomain is required for routing, but **tenant trust is enforced by `tenant_id`**, not by trusting the hostname alone.

---

## 1. Base URL Pattern

For HRIS integration, the base API URL is:

- **Production:** `https://appraisal.{tenant_subdomain}.com.gh`

HRIS Core API will construct URLs like:

- `https://appraisal.{tenant_subdomain}.com.gh/api/hris/appraisals/summary`
- `https://appraisal.{tenant_subdomain}.com.gh/api/hris/employees/{employee_id}/appraisals`
- `https://appraisal.{tenant_subdomain}.com.gh/api/hris/appraisals/cycles/active`

The `{tenant_subdomain}` value is obtained by:

1. Reading `tenant_id` from the Keycloak token.
2. Calling Tenant Registry: `GET /tenants/{tenant_id}`.
3. Taking the `eappraisal_schema` / `code` / `subdomain` field and using that to construct `{tenant_subdomain}`.

No client input is used directly to decide which tenant or schema is active.

---

## 2. Authentication

HRIS Core API includes the Keycloak access token in the `Authorization` header:

```http
Authorization: Bearer <access_token>
