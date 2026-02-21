# Deployment Guide

This guide describes how to deploy the HRIS Platform in a production-like environment.

## 1. Prerequisites

- Docker and Docker Compose (for container-based deployment).
- A PostgreSQL cluster (for Tenant Registry and optionally Keycloak).
- A domain or subdomains for:
  - HRIS Portal
  - SRMS API
  - eAppraisal API
  - eLeave API
  - Keycloak
- TLS certificates (via Let’s Encrypt or corporate CA).
- Access to existing SRMS, eAppraisal, and eLeave deployments or to their new containers.

## 2. Components

The deployment consists of:

- **Keycloak** – Identity Provider (IdP).
- **Tenant Registry Service** – Tenant mapping microservice.
- **HRIS Core API** – FastAPI BFF.
- **HRIS Portal** – React frontend.
- **Reverse Proxy (Nginx)** – Routing and TLS termination.
- **Existing Modules** – SRMS, eAppraisal, eLeave.

## 3. High-Level Steps

1. **Provision Infrastructure**
   - Create VMs or Kubernetes cluster.
   - Configure networking, DNS, and firewall rules.

2. **Deploy Keycloak**
   - Run Keycloak container behind Nginx or a load balancer.
   - Create realm `hris-platform`.
   - Configure clients: `hris-portal`, `hris-core-api`, `srms-api`, `eappraisal-api`, `eleave-api`.
   - Export `realm-export.json` and store it under `identity/`.

3. **Deploy Tenant Registry Service**
   - Deploy PostgreSQL database for tenant registry.
   - Run Tenant Registry container (FastAPI).
   - Run database migrations.
   - Seed initial tenant records for known organizations.

4. **Configure SRMS, eAppraisal, and eLeave**
   - Update their environment variables:
     - Point to Keycloak issuer and JWKS.
     - Configure expected audience.
     - Configure `TENANT_REGISTRY_BASE_URL` and service credentials.
   - Deploy or restart services with new configuration.
   - Verify that each module can validate Keycloak tokens and resolve tenants.

5. **Deploy HRIS Core API**
   - Build and run FastAPI application.
   - Configure it with Keycloak and Tenant Registry settings.
   - Expose it internally behind Nginx.

6. **Deploy HRIS Portal**
   - Build React app (production build).
   - Serve static files using Nginx.
   - Configure Keycloak client settings in the portal (realm, client ID, redirect URIs).

7. **Configure Nginx**
   - Create server blocks for:
     - `portal.example.com` → HRIS Portal
     - `srms-api.example.com` → SRMS backend
     - `eappraisal-api.example.com` → eAppraisal backend
     - `eleave-api.example.com` → eLeave backend
     - `keycloak.example.com` → Keycloak
   - Enable HTTPS for all endpoints.

8. **Smoke Testing**
   - Verify:
     - User can login via HRIS Portal (Keycloak).
     - HRIS Portal can call HRIS Core API with Keycloak tokens.
     - HRIS Core API can call SRMS, eAppraisal, eLeave with Keycloak tokens.
     - Tenant switching and isolation work as expected per module.

## 4. Observability

- Configure centralized logging (e.g., ELK, Loki).
- Configure metrics (e.g., Prometheus + Grafana):
  - Request rates, latencies, error rates for:
    - HRIS Core API
    - Tenant Registry
    - SRMS, eAppraisal, eLeave
- Configure alerts for:
  - Token validation failures.
  - Tenant registry lookup failures.
  - Elevated 5xx rates.

## 5. Security Considerations

- Use HTTPS everywhere, including internal calls where possible.
- Store secrets (client secrets, DB passwords) securely (e.g., Vault, Kubernetes secrets).
- Use least-privilege for service accounts and DB credentials.
- Restrict direct public access to module APIs; prefer routing via Nginx and Keycloak.
