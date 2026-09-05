-- Required database structure for the local shared PostgreSQL instance.
-- Keycloak owns and migrates the tables inside this schema.
-- This file deliberately creates no tenants, users, credentials or sample HR data.
CREATE SCHEMA IF NOT EXISTS keycloak;
