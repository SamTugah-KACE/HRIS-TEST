from functools import lru_cache
import json
from typing import Optional

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = Field("HRIS Core API", alias="APP_NAME")
    app_env: str = Field("development", alias="APP_ENV")

    auth_mode: str = Field("keycloak", alias="AUTH_MODE")

    dev_default_tenant_id: Optional[str] = Field(
        "11111111-1111-1111-1111-111111111111", alias="DEV_DEFAULT_TENANT_ID"
    )
    dev_default_username: Optional[str] = Field("dev.admin", alias="DEV_DEFAULT_USERNAME")
    dev_default_roles: str = Field("hris:hr_manager", alias="DEV_DEFAULT_ROLES")
    dev_default_employee_id: str = Field("e001", alias="DEV_DEFAULT_EMPLOYEE_ID")

    keycloak_issuer: Optional[str] = Field(None, alias="KEYCLOAK_ISSUER")
    keycloak_internal_base_url: Optional[str] = Field(None, alias="KEYCLOAK_INTERNAL_BASE_URL")
    keycloak_jwks_url: Optional[str] = Field(None, alias="KEYCLOAK_JWKS_URL")
    keycloak_audience: Optional[str] = Field(None, alias="KEYCLOAK_AUDIENCE_HRIS_CORE")
    canonical_membership_enforcement: bool = Field(
        False, alias="CANONICAL_MEMBERSHIP_ENFORCEMENT"
    )
    verified_projection_enforcement: bool = Field(
        False, alias="VERIFIED_PROJECTION_ENFORCEMENT"
    )
    keycloak_token_url: Optional[str] = Field(None, alias="KEYCLOAK_TOKEN_URL")
    keycloak_authorize_url: Optional[str] = Field(None, alias="KEYCLOAK_AUTHORIZE_URL")
    keycloak_end_session_url: Optional[str] = Field(None, alias="KEYCLOAK_END_SESSION_URL")
    keycloak_portal_client_id: str = Field("hris-portal", alias="KEYCLOAK_CLIENT_ID_PORTAL")
    keycloak_portal_client_secret: Optional[str] = Field(None, alias="KEYCLOAK_CLIENT_SECRET_PORTAL")
    auth_sso_callback_url: Optional[str] = Field(None, alias="AUTH_SSO_CALLBACK_URL")
    keycloak_manage_portal_client_settings: bool = Field(False, alias="KEYCLOAK_MANAGE_PORTAL_CLIENT_SETTINGS")
    portal_base_url: str = Field("http://localhost:5173", alias="PORTAL_BASE_URL")
    cors_allowed_origins: str = Field(
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000,http://127.0.0.1:3000",
        alias="CORS_ALLOWED_ORIGINS",
    )
    auth_cookie_secure: bool = Field(False, alias="AUTH_COOKIE_SECURE")
    auth_cookie_samesite: str = Field("lax", alias="AUTH_COOKIE_SAMESITE")
    auth_cookie_domain: Optional[str] = Field(None, alias="AUTH_COOKIE_DOMAIN")
    auth_cookie_access_max_age_seconds: int = Field(300, alias="AUTH_COOKIE_ACCESS_MAX_AGE_SECONDS")
    auth_cookie_refresh_max_age_seconds: int = Field(60 * 60 * 8, alias="AUTH_COOKIE_REFRESH_MAX_AGE_SECONDS")
    auth_state_secret: Optional[str] = Field(None, alias="AUTH_STATE_SECRET")
    auth_state_ttl_seconds: int = Field(300, alias="AUTH_STATE_TTL_SECONDS")
    auth_csrf_enabled: bool = Field(True, alias="AUTH_CSRF_ENABLED")
    auth_csrf_cookie_name: str = Field("hris_csrf_token", alias="AUTH_CSRF_COOKIE_NAME")
    auth_csrf_header_name: str = Field("X-CSRF-Token", alias="AUTH_CSRF_HEADER_NAME")
    auth_post_logout_redirect_path: str = Field("/", alias="AUTH_POST_LOGOUT_REDIRECT_PATH")

    tenant_registry_base_url: str = Field(
        "http://localhost:8001", alias="TENANT_REGISTRY_BASE_URL"
    )
    tenant_registry_allow_fallback: bool = Field(False, alias="TENANT_REGISTRY_ALLOW_FALLBACK")
    tenant_registry_timeout_seconds: int = Field(5, alias="TENANT_REGISTRY_TIMEOUT_SECONDS")
    tenant_registry_startup_wait_retries: int = Field(60, alias="TENANT_REGISTRY_STARTUP_WAIT_RETRIES")
    tenant_registry_startup_retry_delay_seconds: int = Field(
        5, alias="TENANT_REGISTRY_STARTUP_RETRY_DELAY_SECONDS"
    )
    tenant_registry_startup_wait_fail_open: bool = Field(
        False, alias="TENANT_REGISTRY_STARTUP_WAIT_FAIL_OPEN"
    )
    tenant_registry_basic_auth_username: str = Field(
        "hris_internal", alias="TENANT_REGISTRY_BASIC_AUTH_USERNAME"
    )
    tenant_registry_basic_auth_password: str = Field(
        "change-me", alias="TENANT_REGISTRY_BASIC_AUTH_PASSWORD"
    )

    srms_base_url: Optional[str] = Field(None, alias="SRMS_BASE_URL")
    srms_integration_token: Optional[str] = Field(None, alias="SRMS_INTEGRATION_TOKEN")
    srms_service_token: Optional[str] = Field(None, alias="SRMS_SERVICE_TOKEN")
    srms_app_type: Optional[str] = Field(None, alias="SRMS_APP_TYPE")
    srms_session_token: Optional[str] = Field(None, alias="SRMS_SESSION_TOKEN")
    srms_auto_session_token: bool = Field(True, alias="SRMS_AUTO_SESSION_TOKEN")
    srms_extra_headers_json: Optional[str] = Field(None, alias="SRMS_EXTRA_HEADERS_JSON")
    srms_payload_security_mode: str = Field("auto", alias="SRMS_PAYLOAD_SECURITY_MODE")
    srms_payload_signing_secret: Optional[str] = Field(None, alias="SRMS_PAYLOAD_SIGNING_SECRET")
    srms_payload_encryption_secret: Optional[str] = Field(None, alias="SRMS_PAYLOAD_ENCRYPTION_SECRET")
    srms_hris_shared_secret: Optional[str] = Field(None, alias="SRMS_HRIS_SHARED_SECRET")
    srms_hris_service_token: Optional[str] = Field(None, alias="SRMS_HRIS_SERVICE_TOKEN")
    module_token_secret: Optional[str] = Field(None, alias="MODULE_TOKEN_SECRET")

    eappraisal_domain_template: Optional[str] = Field(
        None, alias="EAPPRAISAL_DOMAIN_TEMPLATE"
    )
    eappraisal_service_token: Optional[str] = Field(None, alias="EAPPRAISAL_SERVICE_TOKEN")
    eappraisal_refresh_token: Optional[str] = Field(None, alias="EAPPRAISAL_REFRESH_TOKEN")
    eappraisal_auto_refresh: bool = Field(True, alias="EAPPRAISAL_AUTO_REFRESH")
    eappraisal_fixture_file: Optional[str] = Field(None, alias="EAPPRAISAL_FIXTURE_FILE")
    eappraisal_fixture_employee_id: str = Field("e001", alias="EAPPRAISAL_FIXTURE_EMPLOYEE_ID")
    eappraisal_subdomain_header: Optional[str] = Field(None, alias="EAPPRAISAL_SUBDOMAIN_HEADER")
    eappraisal_cookie: Optional[str] = Field(None, alias="EAPPRAISAL_COOKIE")
    eappraisal_integration_base_url: Optional[str] = Field(
        None, alias="EAPPRAISAL_INTEGRATION_BASE_URL"
    )
    eappraisal_hris_shared_secret: Optional[str] = Field(
        None, alias="EAPPRAISAL_HRIS_SHARED_SECRET"
    )
    eappraisal_hris_service_token: Optional[str] = Field(
        None, alias="EAPPRAISAL_HRIS_SERVICE_TOKEN"
    )
    eappraisal_tenant_id_mode: str = Field(
        "resolve_native", alias="EAPPRAISAL_TENANT_ID_MODE"
    )

    eleave_domain_template: Optional[str] = Field(
        None, alias="ELEAVE_DOMAIN_TEMPLATE"
    )
    eleave_service_token: Optional[str] = Field(None, alias="ELEAVE_SERVICE_TOKEN")
    eleave_hris_shared_secret: Optional[str] = Field(
        None, alias="ELEAVE_HRIS_SHARED_SECRET"
    )
    eleave_hris_service_token: Optional[str] = Field(
        None, alias="ELEAVE_HRIS_SERVICE_TOKEN"
    )

    module_adapter_mode: str = Field("auto", alias="MODULE_ADAPTER_MODE")
    eleave_use_tenant_path: bool = Field(True, alias="ELEAVE_USE_TENANT_PATH")

    # Native module UI links in GET /modules/catalog (derived URLs; validated before exposure).
    module_launch_expose_native_urls: bool = Field(False, alias="MODULE_LAUNCH_EXPOSE_NATIVE_URLS")
    module_launch_allow_http: bool = Field(False, alias="MODULE_LAUNCH_ALLOW_HTTP")
    module_launch_host_suffix_allowlist: str = Field("", alias="MODULE_LAUNCH_HOST_SUFFIX_ALLOWLIST")
    module_launch_open_mode: str = Field("same_window", alias="MODULE_LAUNCH_OPEN_MODE")
    module_handoff_enabled: bool = Field(True, alias="MODULE_HANDOFF_ENABLED")
    module_handoff_ttl_seconds: int = Field(60, alias="MODULE_HANDOFF_TTL_SECONDS")
    module_handoff_issuer: str = Field("hris-core", alias="MODULE_HANDOFF_ISSUER")
    module_service_auth_mode: str = Field("shared_secret", alias="MODULE_SERVICE_AUTH_MODE")
    module_service_jwt_issuer: Optional[str] = Field(None, alias="MODULE_SERVICE_JWT_ISSUER")
    module_service_jwt_audience: Optional[str] = Field("hris-core-modules", alias="MODULE_SERVICE_JWT_AUDIENCE")
    module_service_jwt_shared_secret: Optional[str] = Field(None, alias="MODULE_SERVICE_JWT_SHARED_SECRET")
    module_service_jwt_algorithms: str = Field("HS256", alias="MODULE_SERVICE_JWT_ALGORITHMS")
    allow_low_confidence_identity_fallback: bool = Field(
        True, alias="ALLOW_LOW_CONFIDENCE_IDENTITY_FALLBACK"
    )
    rate_limit_enabled: bool = Field(True, alias="RATE_LIMIT_ENABLED")
    rate_limit_window_seconds: int = Field(60, alias="RATE_LIMIT_WINDOW_SECONDS")
    rate_limit_auth_start_max: int = Field(240, alias="RATE_LIMIT_AUTH_START_MAX")
    rate_limit_auth_callback_max: int = Field(240, alias="RATE_LIMIT_AUTH_CALLBACK_MAX")
    rate_limit_auth_refresh_max: int = Field(90, alias="RATE_LIMIT_AUTH_REFRESH_MAX")
    rate_limit_auth_logout_max: int = Field(90, alias="RATE_LIMIT_AUTH_LOGOUT_MAX")
    rate_limit_module_redeem_max: int = Field(240, alias="RATE_LIMIT_MODULE_REDEEM_MAX")

    use_stub_data: bool = Field(False, alias="USE_STUB_DATA")
    enable_all_modules_by_default: bool = Field(
        False, alias="ENABLE_ALL_MODULES_BY_DEFAULT"
    )
    enable_integration_debug_endpoints: bool = Field(
        False, alias="ENABLE_INTEGRATION_DEBUG_ENDPOINTS"
    )
    enable_auto_sync_loop: bool = Field(False, alias="ENABLE_AUTO_SYNC_LOOP")
    auto_sync_interval_seconds: int = Field(300, alias="AUTO_SYNC_INTERVAL_SECONDS")
    auto_sync_max_tenants: int = Field(200, alias="AUTO_SYNC_MAX_TENANTS")
    auto_sync_max_users_per_tenant: int = Field(200, alias="AUTO_SYNC_MAX_USERS_PER_TENANT")
    enable_startup_tenant_inventory_import: bool = Field(
        False, alias="ENABLE_STARTUP_TENANT_INVENTORY_IMPORT"
    )
    enable_startup_eappraisal_tenant_inventory_import: bool = Field(
        False, alias="ENABLE_STARTUP_EAPPRAISAL_TENANT_INVENTORY_IMPORT"
    )
    startup_tenant_inventory_max_records: int = Field(
        500, alias="STARTUP_TENANT_INVENTORY_MAX_RECORDS"
    )
    tenant_reconciliation_aliases_json: str = Field("{}", alias="TENANT_RECONCILIATION_ALIASES_JSON")
    enable_auto_provision: bool = Field(False, alias="ENABLE_AUTO_PROVISION")
    auto_provision_dry_run: bool = Field(True, alias="AUTO_PROVISION_DRY_RUN")
    auto_provision_allowed_modules: str = Field(
        "eappraisal,eleave", alias="AUTO_PROVISION_ALLOWED_MODULES"
    )
    auto_provision_max_actions_per_run: int = Field(100, alias="AUTO_PROVISION_MAX_ACTIONS_PER_RUN")
    auto_provision_stop_on_error: bool = Field(True, alias="AUTO_PROVISION_STOP_ON_ERROR")
    auto_provision_audit_log_path: str = Field(
        "logs/auto_provision_audit.jsonl", alias="AUTO_PROVISION_AUDIT_LOG_PATH"
    )
    eappraisal_provision_user_path: str = Field(
        "/api/hris/v1/integration/tenants/{tenant_id}/users/provision",
        alias="EAPPRAISAL_PROVISION_USER_PATH",
    )
    eleave_provision_user_path: str = Field(
        "/api/hris/v1/integration/tenants/{tenant_id}/users/provision",
        alias="ELEAVE_PROVISION_USER_PATH",
    )
    http_client_timeout_seconds: int = Field(10, alias="HTTP_CLIENT_TIMEOUT_SECONDS")

    enable_jit_module_setup: bool = Field(False, alias="ENABLE_JIT_MODULE_SETUP")
    jit_auto_enable_modules: str = Field("eappraisal,eleave", alias="JIT_AUTO_ENABLE_MODULES")
    jit_auto_bootstrap_enabled: bool = Field(True, alias="JIT_AUTO_BOOTSTRAP_ENABLED")
    jit_max_actions_per_request: int = Field(10, alias="JIT_MAX_ACTIONS_PER_REQUEST")
    jit_cooldown_seconds: int = Field(30, alias="JIT_COOLDOWN_SECONDS")

    federated_directory_srms_max_tenants_per_run: int = Field(
        25, alias="FEDERATED_DIRECTORY_SRMS_MAX_TENANTS_PER_RUN"
    )
    federated_directory_srms_cooldown_on_429_seconds: int = Field(
        120, alias="FEDERATED_DIRECTORY_SRMS_COOLDOWN_ON_429_SECONDS"
    )
    enable_federated_keycloak_sync: bool = Field(
        False, alias="ENABLE_FEDERATED_KEYCLOAK_SYNC"
    )
    startup_federated_enrollment_mode: str = Field(
        "disabled", alias="STARTUP_FEDERATED_ENROLLMENT_MODE"
    )
    federated_keycloak_sync_dry_run: bool = Field(
        True, alias="FEDERATED_KEYCLOAK_SYNC_DRY_RUN"
    )
    # 0 means process the complete discovered directory. Throughput is still
    # bounded by the single-worker job queue and downstream timeouts.
    federated_keycloak_sync_max_users_per_run: int = Field(
        0, alias="FEDERATED_KEYCLOAK_SYNC_MAX_USERS_PER_RUN"
    )
    enrollment_worker_enabled: bool = Field(True, alias="ENROLLMENT_WORKER_ENABLED")
    enrollment_refresh_tenant_inventory: bool = Field(
        True, alias="ENROLLMENT_REFRESH_TENANT_INVENTORY"
    )
    enrollment_email_max_attempts: int = Field(3, alias="ENROLLMENT_EMAIL_MAX_ATTEMPTS")
    enrollment_email_retry_base_seconds: int = Field(30, alias="ENROLLMENT_EMAIL_RETRY_BASE_SECONDS")
    enable_federated_keycloak_welcome_email: bool = Field(
        False, alias="ENABLE_FEDERATED_KEYCLOAK_WELCOME_EMAIL"
    )
    federated_keycloak_allow_existing_user_password_reset: bool = Field(
        False, alias="FEDERATED_KEYCLOAK_ALLOW_EXISTING_USER_PASSWORD_RESET"
    )
    automation_store_database_url: Optional[str] = Field(
        None, alias="AUTOMATION_STORE_DATABASE_URL"
    )
    automation_store_schema: str = Field("hris_automation", alias="AUTOMATION_STORE_SCHEMA")
    db_auto_create_on_startup: bool = Field(True, alias="DB_AUTO_CREATE_ON_STARTUP")
    db_bootstrap_admin_url: Optional[str] = Field(None, alias="DB_BOOTSTRAP_ADMIN_URL")
    db_bootstrap_admin_database: str = Field("postgres", alias="DB_BOOTSTRAP_ADMIN_DATABASE")
    db_bootstrap_connect_retries: int = Field(5, alias="DB_BOOTSTRAP_CONNECT_RETRIES")
    db_bootstrap_retry_delay_seconds: int = Field(2, alias="DB_BOOTSTRAP_RETRY_DELAY_SECONDS")
    db_bootstrap_timeout_seconds: int = Field(5, alias="DB_BOOTSTRAP_TIMEOUT_SECONDS")
    startup_pause_after_db_create_seconds: int = Field(
        0, alias="STARTUP_PAUSE_AFTER_DB_CREATE_SECONDS"
    )
    enable_post_deploy_sync_automation: bool = Field(False, alias="ENABLE_POST_DEPLOY_SYNC_AUTOMATION")
    post_deploy_welcome_emails_enabled: bool = Field(False, alias="POST_DEPLOY_WELCOME_EMAILS_ENABLED")
    onboarding_auto_sync_new_tenants: bool = Field(True, alias="ONBOARDING_AUTO_SYNC_NEW_TENANTS")
    onboarding_auto_keycloak_provision: bool = Field(False, alias="ONBOARDING_AUTO_KEYCLOAK_PROVISION")
    onboarding_welcome_email_enabled: bool = Field(False, alias="ONBOARDING_WELCOME_EMAIL_ENABLED")
    onboarding_welcome_max_users_per_tenant: int = Field(2000, alias="ONBOARDING_WELCOME_MAX_USERS_PER_TENANT")
    mail_provider: str = Field("smtp", validation_alias=AliasChoices("PROVIDER", "MAIL_PROVIDER"))
    smtp_host: Optional[str] = Field(None, validation_alias=AliasChoices("SMTP_HOST", "MAIL_SERVER"))
    smtp_port: int = Field(587, validation_alias=AliasChoices("SMTP_PORT", "MAIL_PORT"))
    smtp_username: Optional[str] = Field(None, validation_alias=AliasChoices("SMTP_USERNAME", "MAIL_USERNAME"))
    smtp_password: Optional[str] = Field(None, validation_alias=AliasChoices("SMTP_PASSWORD", "MAIL_PASSWORD"))
    smtp_use_tls: bool = Field(True, validation_alias=AliasChoices("SMTP_USE_TLS", "MAIL_STARTTLS"))
    smtp_use_ssl: bool = Field(False, validation_alias=AliasChoices("SMTP_USE_SSL", "MAIL_SSL_TLS"))
    smtp_use_credentials: bool = Field(True, validation_alias=AliasChoices("SMTP_USE_CREDENTIALS", "USE_CREDENTIALS"))
    smtp_validate_certs: bool = Field(True, validation_alias=AliasChoices("SMTP_VALIDATE_CERTS", "VALIDATE_CERTS"))
    smtp_from_email: str = Field("noreply@hris.local", validation_alias=AliasChoices("SMTP_FROM_EMAIL", "MAIL_FROM"))
    password_reset_action_lifespan_seconds: int = Field(
        900, alias="PASSWORD_RESET_ACTION_LIFESPAN_SECONDS"
    )
    password_reset_rate_limit_max: int = Field(5, alias="PASSWORD_RESET_RATE_LIMIT_MAX")
    keycloak_manage_realm_email_settings: bool = Field(
        False, alias="KEYCLOAK_MANAGE_REALM_EMAIL_SETTINGS"
    )
    keycloak_email_theme: Optional[str] = Field(None, alias="KEYCLOAK_EMAIL_THEME")
    welcome_email_subject_template: str = Field(
        "Welcome to {brand_name} - {tenant_name}", alias="WELCOME_EMAIL_SUBJECT_TEMPLATE"
    )
    welcome_email_body_template: str = Field(
        (
            "Welcome to {brand_name} for {tenant_name}.\n\n"
            "Portal URL: {portal_url}\n"
            "Username: {username}\n"
            "{password_line}\n"
            "Support: {support_email}\n"
        ),
        alias="WELCOME_EMAIL_BODY_TEMPLATE",
    )
    tenant_brand_name_default: str = Field("HRIS", alias="TENANT_BRAND_NAME_DEFAULT")
    tenant_support_email_default: str = Field("support@hris.local", alias="TENANT_SUPPORT_EMAIL_DEFAULT")
    storage_provider_stack: str = Field("s3,local", alias="STORAGE_PROVIDER_STACK")
    storage_healthcheck_ttl_seconds: int = Field(300, alias="STORAGE_HEALTHCHECK_TTL_SECONDS")
    media_local_base_path: str = Field("data/media", alias="MEDIA_LOCAL_BASE_PATH")
    s3_bucket: Optional[str] = Field(None, alias="S3_BUCKET")
    s3_region: Optional[str] = Field(None, alias="S3_REGION")
    s3_access_key_id: Optional[str] = Field(None, alias="S3_ACCESS_KEY_ID")
    s3_secret_access_key: Optional[str] = Field(None, alias="S3_SECRET_ACCESS_KEY")
    s3_endpoint_url: Optional[str] = Field(None, alias="S3_ENDPOINT_URL")
    s3_prefix: str = Field("", alias="S3_PREFIX")
    keycloak_realm: Optional[str] = Field(None, alias="KEYCLOAK_REALM")
    keycloak_admin_client_id: Optional[str] = Field(None, alias="KEYCLOAK_ADMIN_CLIENT_ID")
    keycloak_admin_client_secret: Optional[str] = Field(None, alias="KEYCLOAK_ADMIN_CLIENT_SECRET")
    keycloak_admin_username: Optional[str] = Field(None, alias="KEYCLOAK_ADMIN_USERNAME")
    keycloak_admin_password: Optional[str] = Field(None, alias="KEYCLOAK_ADMIN_PASSWORD")
    keycloak_admin_realm: str = Field("master", alias="KEYCLOAK_ADMIN_REALM")
    hris_superadmin_onboard_allowed_groups: Optional[str] = Field(
        None, alias="HRIS_SUPERADMIN_ONBOARD_ALLOWED_GROUPS"
    )
    hris_superadmin_onboard_group_bootstrap_done: Optional[bool] = Field(
        None, alias="HRIS_SUPERADMIN_ONBOARD_GROUP_BOOTSTRAP_DONE"
    )
    bootstrap_admin_enabled: bool = Field(False, alias="BOOTSTRAP_ADMIN_ENABLED")
    bootstrap_superadmin_username: Optional[str] = Field(None, alias="BOOTSTRAP_SUPERADMIN_USERNAME")
    bootstrap_superadmin_email: Optional[str] = Field(None, alias="BOOTSTRAP_SUPERADMIN_EMAIL")
    bootstrap_superadmin_password: Optional[str] = Field(None, alias="BOOTSTRAP_SUPERADMIN_PASSWORD")
    bootstrap_superadmin_tenant_id: Optional[str] = Field(None, alias="BOOTSTRAP_SUPERADMIN_TENANT_ID")
    bootstrap_tenantadmin_username: Optional[str] = Field(None, alias="BOOTSTRAP_TENANTADMIN_USERNAME")
    bootstrap_tenantadmin_email: Optional[str] = Field(None, alias="BOOTSTRAP_TENANTADMIN_EMAIL")
    bootstrap_tenantadmin_password: Optional[str] = Field(None, alias="BOOTSTRAP_TENANTADMIN_PASSWORD")
    bootstrap_tenantadmin_tenant_id: Optional[str] = Field(None, alias="BOOTSTRAP_TENANTADMIN_TENANT_ID")
    onboarding_send_temp_password_email: bool = Field(False, alias="ONBOARDING_SEND_TEMP_PASSWORD_EMAIL")
    onboarding_temp_password_length: int = Field(14, alias="ONBOARDING_TEMP_PASSWORD_LENGTH")
    onboarding_dev_credentials_export_enabled: bool = Field(
        False, alias="ONBOARDING_DEV_CREDENTIALS_EXPORT_ENABLED"
    )
    onboarding_dev_credentials_export_path: str = Field(
        "data/exports", alias="ONBOARDING_DEV_CREDENTIALS_EXPORT_PATH"
    )
    onboarding_dev_force_temp_password: bool = Field(
        False, alias="ONBOARDING_DEV_FORCE_TEMP_PASSWORD"
    )
    expose_temporary_password_in_api: bool = Field(
        False, alias="EXPOSE_TEMPORARY_PASSWORD_IN_API"
    )

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "env_ignore_empty": True,
        "populate_by_name": True,
    }

    def validate_runtime(self) -> None:
        allowed_envs = {"development", "staging", "production", "test"}
        normalized_env = (self.app_env or "development").strip().lower()
        if normalized_env not in allowed_envs:
            raise ValueError("APP_ENV must be one of: development, staging, production, test")
        if normalized_env != "test" and self.use_stub_data:
            raise ValueError("USE_STUB_DATA=true is no longer supported for product runtime")
        if normalized_env != "test" and self.auth_mode != "keycloak":
            raise ValueError("AUTH_MODE must be keycloak for production-like runtime")
        if normalized_env != "test" and (self.eappraisal_fixture_file or "").strip():
            raise ValueError("EAPPRAISAL_FIXTURE_FILE is test-only and cannot be used in product runtime")

        allowed_samesite = {"lax", "strict", "none"}
        normalized_samesite = self.auth_cookie_samesite.lower().strip()
        if normalized_samesite not in allowed_samesite:
            raise ValueError("AUTH_COOKIE_SAMESITE must be one of: lax, strict, none")
        if normalized_samesite == "none" and not self.auth_cookie_secure:
            raise ValueError("AUTH_COOKIE_SECURE must be true when AUTH_COOKIE_SAMESITE=none")
        if self.auth_state_ttl_seconds <= 0:
            raise ValueError("AUTH_STATE_TTL_SECONDS must be greater than 0")
        if self.smtp_use_tls and self.smtp_use_ssl:
            raise ValueError("SMTP_USE_TLS and SMTP_USE_SSL cannot both be true")
        if self.mail_provider.strip().lower() != "smtp":
            raise ValueError("Only PROVIDER=smtp is currently supported")
        if self.password_reset_action_lifespan_seconds < 300:
            raise ValueError("PASSWORD_RESET_ACTION_LIFESPAN_SECONDS must be at least 300")
        enrollment_mode = self.startup_federated_enrollment_mode.strip().lower()
        if enrollment_mode not in {"disabled", "discover", "apply"}:
            raise ValueError("STARTUP_FEDERATED_ENROLLMENT_MODE must be disabled, discover, or apply")
        if enrollment_mode == "apply" and not self.enable_federated_keycloak_sync:
            raise ValueError("ENABLE_FEDERATED_KEYCLOAK_SYNC=true is required for startup apply mode")
        if self.federated_keycloak_sync_max_users_per_run < 0:
            raise ValueError("FEDERATED_KEYCLOAK_SYNC_MAX_USERS_PER_RUN must be 0 (unlimited) or greater")
        if self.enrollment_email_max_attempts < 1:
            raise ValueError("ENROLLMENT_EMAIL_MAX_ATTEMPTS must be at least 1")
        if self.enrollment_email_retry_base_seconds < 1:
            raise ValueError("ENROLLMENT_EMAIL_RETRY_BASE_SECONDS must be at least 1")
        if self.auth_csrf_enabled and not str(self.auth_csrf_cookie_name or "").strip():
            raise ValueError("AUTH_CSRF_COOKIE_NAME cannot be empty when AUTH_CSRF_ENABLED=true")
        allowed_srms_modes = {"auto", "plain", "encrypted_envelope", "staff_records_response"}
        normalized_srms_mode = self.srms_payload_security_mode.lower().strip()
        if normalized_srms_mode not in allowed_srms_modes:
            raise ValueError(
                "SRMS_PAYLOAD_SECURITY_MODE must be one of: auto, plain, encrypted_envelope, staff_records_response"
            )
        if normalized_srms_mode == "encrypted_envelope" and not (self.srms_payload_signing_secret or "").strip():
            raise ValueError("SRMS_PAYLOAD_SIGNING_SECRET is required when SRMS_PAYLOAD_SECURITY_MODE=encrypted_envelope")
        if normalized_srms_mode == "staff_records_response" and not (self.srms_payload_encryption_secret or "").strip():
            raise ValueError(
                "SRMS_PAYLOAD_ENCRYPTION_SECRET is required when SRMS_PAYLOAD_SECURITY_MODE=staff_records_response"
            )
        if (self.srms_extra_headers_json or "").strip():
            try:
                value = json.loads(self.srms_extra_headers_json or "{}")
            except json.JSONDecodeError as exc:
                raise ValueError("SRMS_EXTRA_HEADERS_JSON must be valid JSON object") from exc
            if not isinstance(value, dict):
                raise ValueError("SRMS_EXTRA_HEADERS_JSON must decode to a JSON object")
        try:
            tenant_aliases = json.loads(self.tenant_reconciliation_aliases_json or "{}")
        except json.JSONDecodeError as exc:
            raise ValueError("TENANT_RECONCILIATION_ALIASES_JSON must be valid JSON") from exc
        if not isinstance(tenant_aliases, dict):
            raise ValueError("TENANT_RECONCILIATION_ALIASES_JSON must decode to a JSON object")
        if self.auth_mode == "keycloak":
            if not self.keycloak_issuer:
                raise ValueError("KEYCLOAK_ISSUER is required when AUTH_MODE=keycloak")
            if not self.portal_base_url:
                raise ValueError("PORTAL_BASE_URL is required when AUTH_MODE=keycloak")
            if normalized_env == "production" and self.auth_sso_callback_url and not self.auth_sso_callback_url.lower().startswith("https://"):
                raise ValueError("AUTH_SSO_CALLBACK_URL must use https:// in production")
            if not self.keycloak_portal_client_id:
                raise ValueError("KEYCLOAK_CLIENT_ID_PORTAL is required when AUTH_MODE=keycloak")
            has_state_secret = bool((self.auth_state_secret or "").strip())
            has_client_secret = bool((self.keycloak_portal_client_secret or "").strip())
            if not (has_state_secret or has_client_secret):
                raise ValueError(
                    "Set AUTH_STATE_SECRET (preferred) or KEYCLOAK_CLIENT_SECRET_PORTAL "
                    "for signed SSO state in AUTH_MODE=keycloak"
                )
        allowed_launch_modes = {"new_tab", "same_window"}
        if str(self.module_launch_open_mode or "").strip().lower() not in allowed_launch_modes:
            raise ValueError("MODULE_LAUNCH_OPEN_MODE must be one of: new_tab, same_window")
        if self.module_handoff_ttl_seconds <= 0:
            raise ValueError("MODULE_HANDOFF_TTL_SECONDS must be greater than 0")
        allowed_module_auth_modes = {"shared_secret", "jwt_optional", "jwt_strict"}
        if str(self.module_service_auth_mode or "").strip().lower() not in allowed_module_auth_modes:
            raise ValueError("MODULE_SERVICE_AUTH_MODE must be one of: shared_secret, jwt_optional, jwt_strict")
        if self.rate_limit_window_seconds <= 0:
            raise ValueError("RATE_LIMIT_WINDOW_SECONDS must be greater than 0")
        if min(
            self.rate_limit_auth_start_max,
            self.rate_limit_auth_callback_max,
            self.rate_limit_auth_refresh_max,
            self.rate_limit_auth_logout_max,
            self.rate_limit_module_redeem_max,
        ) <= 0:
            raise ValueError("Rate limit max values must all be greater than 0")
        if self.auto_sync_interval_seconds <= 0:
            raise ValueError("AUTO_SYNC_INTERVAL_SECONDS must be greater than 0")
        if self.auto_sync_max_tenants <= 0:
            raise ValueError("AUTO_SYNC_MAX_TENANTS must be greater than 0")
        if self.auto_sync_max_users_per_tenant <= 0:
            raise ValueError("AUTO_SYNC_MAX_USERS_PER_TENANT must be greater than 0")
        if self.startup_tenant_inventory_max_records <= 0:
            raise ValueError("STARTUP_TENANT_INVENTORY_MAX_RECORDS must be greater than 0")
        if (
            self.enable_startup_tenant_inventory_import
            and not (
                (self.srms_hris_shared_secret or "").strip()
                or (self.srms_hris_service_token or "").strip()
                or (self.srms_service_token or "").strip()
                or (self.srms_integration_token or "").strip()
            )
        ):
            raise ValueError(
                "SRMS_HRIS_SHARED_SECRET, SRMS_HRIS_SERVICE_TOKEN, SRMS_SERVICE_TOKEN, or "
                "SRMS_INTEGRATION_TOKEN is required when "
                "ENABLE_STARTUP_TENANT_INVENTORY_IMPORT=true"
            )
        if self.auto_provision_max_actions_per_run <= 0:
            raise ValueError("AUTO_PROVISION_MAX_ACTIONS_PER_RUN must be greater than 0")
        if self.onboarding_welcome_max_users_per_tenant <= 0:
            raise ValueError("ONBOARDING_WELCOME_MAX_USERS_PER_TENANT must be greater than 0")
        if self.tenant_registry_startup_wait_retries <= 0:
            raise ValueError("TENANT_REGISTRY_STARTUP_WAIT_RETRIES must be greater than 0")
        if self.tenant_registry_startup_retry_delay_seconds < 0:
            raise ValueError("TENANT_REGISTRY_STARTUP_RETRY_DELAY_SECONDS must be >= 0")
        if normalized_env == "production" and self.tenant_registry_startup_wait_fail_open:
            raise ValueError("TENANT_REGISTRY_STARTUP_WAIT_FAIL_OPEN must be false in production")
        if self.onboarding_auto_keycloak_provision and self.auth_mode != "keycloak":
            raise ValueError("ONBOARDING_AUTO_KEYCLOAK_PROVISION requires AUTH_MODE=keycloak")
        if self.bootstrap_admin_enabled and self.auth_mode != "keycloak":
            raise ValueError("BOOTSTRAP_ADMIN_ENABLED requires AUTH_MODE=keycloak")
        if self.onboarding_temp_password_length < 10:
            raise ValueError("ONBOARDING_TEMP_PASSWORD_LENGTH must be at least 10")
        if self.storage_healthcheck_ttl_seconds <= 0:
            raise ValueError("STORAGE_HEALTHCHECK_TTL_SECONDS must be greater than 0")
        if self.db_bootstrap_connect_retries <= 0:
            raise ValueError("DB_BOOTSTRAP_CONNECT_RETRIES must be greater than 0")
        if self.db_bootstrap_retry_delay_seconds < 0:
            raise ValueError("DB_BOOTSTRAP_RETRY_DELAY_SECONDS must be >= 0")
        if self.db_bootstrap_timeout_seconds <= 0:
            raise ValueError("DB_BOOTSTRAP_TIMEOUT_SECONDS must be greater than 0")
        if self.startup_pause_after_db_create_seconds < 0:
            raise ValueError("STARTUP_PAUSE_AFTER_DB_CREATE_SECONDS must be >= 0")
        if (
            self.enable_post_deploy_sync_automation
            or self.enable_auto_sync_loop
            or self.onboarding_welcome_email_enabled
            or self.enable_federated_keycloak_sync
            or enrollment_mode in {"discover", "apply"}
        ) and not (self.automation_store_database_url or "").strip():
            raise ValueError(
                "AUTOMATION_STORE_DATABASE_URL is required when automation persistence features are enabled"
            )
        if self.enable_federated_keycloak_welcome_email and not (self.smtp_host or "").strip():
            raise ValueError("SMTP_HOST/MAIL_SERVER is required when federated welcome email is enabled")
        if self.federated_keycloak_allow_existing_user_password_reset:
            raise ValueError(
                "FEDERATED_KEYCLOAK_ALLOW_EXISTING_USER_PASSWORD_RESET must be false; "
                "directory reconciliation cannot rotate existing-user passwords"
            )
        if enrollment_mode == "apply" and not (
            ((self.keycloak_admin_client_id or "").strip() and (self.keycloak_admin_client_secret or "").strip())
            or ((self.keycloak_admin_username or "").strip() and (self.keycloak_admin_password or "").strip())
        ):
            raise ValueError("Keycloak admin credentials are required for startup apply mode")
        allowed_modules = {
            module.strip().lower()
            for module in str(self.auto_provision_allowed_modules or "").split(",")
            if module.strip()
        }
        invalid_module_ids = [
            module for module in allowed_modules
            if not module
            or not module[0].isalpha()
            or any(ch not in "abcdefghijklmnopqrstuvwxyz0123456789-_" for ch in module)
        ]
        if invalid_module_ids:
            raise ValueError(
                "AUTO_PROVISION_ALLOWED_MODULES contains invalid module ids: "
                + ", ".join(sorted(invalid_module_ids))
            )
        if normalized_env == "production":
            if self.use_stub_data:
                raise ValueError("USE_STUB_DATA must be false in production")
            if self.auth_mode != "keycloak":
                raise ValueError("AUTH_MODE must be keycloak in production")
            if self.tenant_registry_allow_fallback:
                raise ValueError("TENANT_REGISTRY_ALLOW_FALLBACK must be false in production")
            if not self.auth_cookie_secure:
                raise ValueError("AUTH_COOKIE_SECURE must be true in production")
            if self.module_handoff_enabled and not (self.automation_store_database_url or "").strip():
                raise ValueError(
                    "AUTOMATION_STORE_DATABASE_URL is required for production module handoff replay protection"
                )
            if (self.tenant_registry_basic_auth_password or "").strip() in {"", "change-me"}:
                raise ValueError(
                    "TENANT_REGISTRY_BASIC_AUTH_PASSWORD must be set to a real secret in production"
                )
            if self.allow_low_confidence_identity_fallback:
                raise ValueError("ALLOW_LOW_CONFIDENCE_IDENTITY_FALLBACK must be false in production")
            if self.enable_auto_provision and self.auto_provision_dry_run:
                raise ValueError(
                    "AUTO_PROVISION_DRY_RUN must be false when ENABLE_AUTO_PROVISION=true in production"
                )
            if self.onboarding_dev_credentials_export_enabled:
                raise ValueError(
                    "ONBOARDING_DEV_CREDENTIALS_EXPORT_ENABLED must be false in production"
                )
            if str(self.module_service_auth_mode or "").strip().lower() == "jwt_strict":
                if not (self.module_service_jwt_issuer or "").strip():
                    raise ValueError("MODULE_SERVICE_JWT_ISSUER is required when MODULE_SERVICE_AUTH_MODE=jwt_strict")
                if not (
                    (self.module_service_jwt_shared_secret or "").strip()
                    or (self.module_token_secret or "").strip()
                    or (self.auth_state_secret or "").strip()
                ):
                    raise ValueError(
                        "Set MODULE_SERVICE_JWT_SHARED_SECRET (or MODULE_TOKEN_SECRET/AUTH_STATE_SECRET) "
                        "when MODULE_SERVICE_AUTH_MODE=jwt_strict"
                    )


@lru_cache()
def get_settings() -> Settings:
    return Settings()
