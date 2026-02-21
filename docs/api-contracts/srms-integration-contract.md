# SRMS Integration API Contract

This document describes the SRMS APIs that the **HRIS Core API** is allowed to call.

> ⚠️ Note: SRMS already has a production UI and routing pattern for **human users**:
> - Base UI: `https://srms.gi-kace.com.gh/`
> - Tenant sign-in: `https://srms.gi-kace.com.gh/{tenant_slug}/signin`
>
> Each tenant has:
> - HR/CEO-facing UI (HR Dashboard)
> - Staff-facing UI (Staff Dashboard)
>
> This contract is **not** about those sign-in pages. It defines the **backend APIs** that HRIS Core API will call using Keycloak Bearer tokens.

---

## 1. Base URL

For HRIS integration, SRMS base API URL is:

- **Production:** `https://srms.gi-kace.com.gh`

HRIS Core API will call REST endpoints under this host, typically with a prefix such as `/api/hris/...`.  
Tenant selection is **not taken from the path or slug**, but from the `tenant_id` claim in the Keycloak token and the Tenant Registry mapping.

---

## 2. Authentication

HRIS Core API includes the Keycloak access token in the `Authorization` header:

```http
Authorization: Bearer <access_token>
