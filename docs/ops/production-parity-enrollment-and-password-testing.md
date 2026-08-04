# Production-parity enrollment and password testing

This runbook exercises the same Core, Registry, Keycloak, PostgreSQL, SMTP, and Portal paths used in production. Local runs differ only in hostnames, TLS termination, and secret storage.

## Safety model

- `STARTUP_FEDERATED_ENROLLMENT_MODE=discover` is the safe first boot. It reads inventories but creates no login accounts and sends no email.
- Review discovery in **Administration → Tenant Management → Federated Keycloak User Sync** using **Dry-run**.
- Apply is an explicit super-admin action and requires typing `APPLY`.
- `STARTUP_FEDERATED_ENROLLMENT_MODE=apply` is intended only after tenant mappings have been approved.
- Email is the Keycloak username. Unknown module roles fall back to `hris:employee`; they never elevate platform access.
- Welcome delivery is recorded by tenant and email. Repeated apply/restart does not resend a successful welcome.
- eLeave user inventory currently reports `unsupported`; production activation must treat this as a visible module-contract gap.

## Docker

1. Configure `apps/backend/hris-core-api/.env`, including SMTP and Keycloak admin credentials supplied from an approved local secret source.
2. Run `python scripts/prepare_docker_dev_env.py`; never commit the generated `.env.docker.development`.
3. Use `STARTUP_FEDERATED_ENROLLMENT_MODE=discover` in the Core `.env` for the first boot, then regenerate the Docker env.
4. Run `docker compose --env-file .env.docker.development -f docker-compose.yml -f docker-compose.keycloak.yml up -d --build --wait`.
5. Open `http://localhost:5173`, sign in as the approved super-admin, and open Tenant Management.
6. Run a global dry-run. Verify tenant counts, source statuses, missing-email count, derived roles, and that eLeave is visibly unsupported.
7. Resolve ambiguous/split tenants before apply. Use an explicit alias such as `HRIS_TENANT_RECONCILIATION_ALIASES_JSON={"eappraisal:GI-KACE":"gkacoeii919"}`, restart in discovery mode, and confirm the eAppraisal routing metadata enriches the canonical SRMS tenant rather than creating another tenant.
8. Enable `ENABLE_FEDERATED_KEYCLOAK_SYNC=true` and `ENABLE_FEDERATED_KEYCLOAK_WELCOME_EMAIL=true` in the Core `.env`, regenerate the Docker env, select Apply, type `APPLY`, and run.
9. Verify a newly created user receives exactly one welcome email and logs in with the email address as username.
10. Repeat Apply and restart the stack. Verify `created_count=0` and no second welcome email.

## Non-Docker

Run PostgreSQL and Keycloak first. Configure Core `.env` with the same settings but without the `HRIS_` prefix. Start Registry, Core, and Portal with `scripts/start_local_stack.py`. The UI workflow is identical to Docker.

## Normal-user tests

### First login

1. Open the welcome email.
2. Follow the expiring Keycloak required-action link and set a password.
3. Sign in using the email address and the newly selected password.
4. Confirm the HRIS dashboard contains only capabilities derived from the user's approved tenant/module memberships.

### Forgot password

1. Sign out and select **Forgot your password?**.
2. Submit the enrolled email address.
3. Confirm the UI returns the generic accepted message.
4. Open the email within 15 minutes and set a compliant password.
5. Confirm the link cannot be reused and the new password works.
6. Submit an unknown but validly formatted email. Confirm the same UI response appears but no email is sent.
7. Submit repeated requests and confirm rate limiting activates.

### Authenticated password change

From the profile/security screen, verify that an incorrect current password is rejected and a correct current password permits a compliant replacement.

## Production gates

Do not switch startup mode to `apply` until tenant reconciliation has no ambiguous matches, SMTP/Keycloak action email is verified, source emails are clean, roles are reviewed, and a dry-run export has been approved. Production must use HTTPS, secure cookies, a confidential Keycloak admin service account, external secret storage, database backups, and centralized rate limiting when Core has multiple replicas.
