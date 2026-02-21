# CI/CD Pipeline

This document describes recommended CI/CD practices for the HRIS Platform.

## 1. Objectives

- Ensure consistent, repeatable builds.
- Run automated tests and linters.
- Enforce security checks.
- Support zero-downtime deployments wherever possible.

## 2. Pipeline Overview

Each component has its own pipeline:

- **HRIS Portal** (React)
- **HRIS Core API** (FastAPI)
- **Tenant Registry Service** (FastAPI)
- **Infrastructure** (Docker, Nginx, Kubernetes manifests)
- Module repos (SRMS, eAppraisal, eLeave) maintain their **own** pipelines, but the platform pipeline ensures compatibility.

Typical stages:

1. **Checkout**
2. **Static Analysis & Linting**
3. **Unit Tests**
4. **Integration Tests** (where applicable)
5. **Build Artifacts** (Docker images, static bundles)
6. **Security Scans**
7. **Deploy to Staging**
8. **Smoke Tests**
9. **Manual or Automated Promotion to Production**

## 3. Example: HRIS Core API Pipeline

### 3.1 Linting & Static Analysis

- Tools: `ruff`, `mypy`, `black`.
- Run on every push and merge request.

### 3.2 Unit Tests

- Framework: `pytest`.
- Coverage reports must meet a minimum threshold (e.g., 80%).

### 3.3 Docker Image Build

- Build using a multi-stage Dockerfile:
  - Builder stage (install deps, run tests).
  - Runtime stage (minimal image).

### 3.4 Security

- Use `pip-audit` or equivalent to check for vulnerable Python packages.
- Optionally run container image scanning (e.g. Trivy).

### 3.5 Deployment

- Push image to container registry.
- Trigger deployment in Kubernetes or via Docker Compose.

## 4. Example: HRIS Portal Pipeline

- Install Node.js dependencies.
- Run TypeScript checks and ESLint.
- Run unit tests (e.g., Jest, React Testing Library).
- Build optimized production bundle.
- Package as Docker image or artifact for Nginx.

## 5. Promotion Strategy

- **Git branching model:**
  - `main` – production.
  - `develop` – integration / staging.
  - feature branches.

- **Promotion:**
  - Merge to `develop` → deploy to staging.
  - Run automated smoke tests.
  - Tag release version (e.g. `v1.2.0`).
  - Merge to `main` → deploy to production.

## 6. Rollback

- Maintain versioned Docker images.
- Keep last known good configuration.
- Rolling back involves:
  - Reverting to previous image tag.
  - Applying previous configuration manifest.

## 7. Integration with Module Pipelines

- SRMS, eAppraisal, and eLeave repositories retain their own CI/CD.
- Platform pipeline:
  - Tests compatibility using pinned versions of module APIs.
  - May consume contract tests (e.g., API schemas) to fail early if breaking changes are introduced.
