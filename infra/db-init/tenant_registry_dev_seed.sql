-- Create the Keycloak schema (Keycloak manages its own tables)
CREATE SCHEMA IF NOT EXISTS keycloak;

-- Explicit test fixture only.
-- Normal development and production Compose files do not mount or execute this file.
-- Run it manually only inside a disposable test database after Registry migrations.

INSERT INTO tenants (
    id, tenant_id, code, name,
    srms_schema, srms_slug,
    eappraisal_subdomain, eleave_subdomain,
    is_active, created_at, updated_at
) VALUES
(
    gen_random_uuid(),
    '11111111-1111-1111-1111-111111111111',
    'DEV-TENANT',
    'Development Tenant',
    'tenant_dev',
    'dev-org',
    'devsub',
    'devsub',
    TRUE, NOW(), NOW()
),
(
    gen_random_uuid(),
    '22222222-2222-2222-2222-222222222222',
    'GI-KACE',
    'Ghana-India Kofi Annan Centre of Excellence in ICT',
    'tenant_gikace',
    'gi-kace',
    'gigov',
    'gigov',
    TRUE, NOW(), NOW()
),
(
    gen_random_uuid(),
    '33333333-3333-3333-3333-333333333333',
    'MOF',
    'Ministry of Finance',
    'tenant_mof',
    'mof',
    'mof',
    'mof',
    TRUE, NOW(), NOW()
)
ON CONFLICT DO NOTHING;
