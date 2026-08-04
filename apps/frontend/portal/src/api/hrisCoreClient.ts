import { httpClient } from './httpClient';
import { gatewayRequest, useGraphqlGateway } from './gatewayClient';

export type UserIdentity = {
  sub: string;
  username: string;
  email?: string;
  tenant_id: string;
  employee_id?: string;
  roles: string[];
  effective_role: string;
  tenant: {
    code: string;
    name: string;
    status?: string;
    modules: Record<string, { status?: string; ready?: boolean; configured?: boolean }>;
    enabled_module_ids?: string[];
  };
  available_roles: string[];
};

/** Server-validated link to the module's own SPA (Angular/React); may be absent if policy blocks exposure. */
export type ModuleCatalogLaunch = {
  native_app_url?: string | null;
  native_entry_available?: boolean;
  open_mode?: 'new_tab' | 'same_window';
  portal_summary_note?: string | null;
};

export type ModuleHandoffLaunchResponse = {
  module_id: string;
  tenant_id: string;
  launch_url: string;
  expires_at: number;
  target_route?: string;
  open_mode?: 'new_tab' | 'same_window';
  embeddable?: boolean;
  module_label?: string;
};

export type ModuleCatalogItem = {
  id: string;
  label: string;
  description?: string;
  status: { status?: string; ready?: boolean; configured?: boolean };
  enabled: boolean;
  visible: boolean;
  ui: {
    icon?: string;
    path: string;
    manager_path?: string;
    self_path?: string;
    launch?: ModuleCatalogLaunch;
  };
  capabilities?: {
    manager_view?: boolean;
    self_service_view?: boolean;
    read_mode?: string;
    [key: string]: unknown;
  };
};

export type ModuleCatalogResponse = {
  tenant: {
    tenant_id: string;
    code: string;
    name: string;
    status?: string;
  };
  workflow_standard?: {
    version?: string;
    shape?: string;
    rbac_driven?: boolean;
    data_access?: string;
    [key: string]: unknown;
  };
  modules: ModuleCatalogItem[];
};

export function getCatalogWorkspaceLaunch(
  modules: ModuleCatalogItem[],
  moduleId: string,
): { path: string; openMode: 'new_tab' | 'same_window' } | null {
  const row = modules.find((m) => String(m.id).toLowerCase() === String(moduleId).toLowerCase());
  const launch = row?.ui?.launch;
  if (!launch?.native_entry_available) return null;
  const openMode = launch.open_mode === 'same_window' ? 'same_window' : 'new_tab';
  return { path: `/modules/${encodeURIComponent(moduleId)}/native`, openMode };
}

export type DashboardSummary = {
  user: { username: string; effective_role: string; roles: string[] };
  tenant: { code: string; name: string };
  srms: {
    total_employees: number;
    active_employees: number;
    inactive_employees: number;
    branches: number;
    departments: number;
    new_hires_this_month: number;
    pending_enlistments: number;
  };
  appraisal: {
    active_cycles: number;
    pending_reviews: number;
    completed_reviews: number;
    overdue_reviews: number;
    average_score: number;
    completion_rate: number;
  };
  leave: {
    total_leaves_this_year: number;
    approved_leaves: number;
    pending_leaves: number;
    rejected_leaves: number;
    cancelled_leaves: number;
    leave_utilization_rate: number;
  };
  superadmin?: {
    tenants: Array<{
      tenant_id?: string;
      name: string;
      code: string;
      slug?: string;
      organization_type?: string;
      access_url?: string;
      type?: string;
      nature?: string;
      status: string;
      modules?: { srms?: boolean; eappraisal?: boolean; eleave?: boolean };
    }>;
    tenant_summary: {
      total: number;
      active: number;
      inactive: number;
    };
  } | null;
  quick_actions: Array<{ id: string; label: string; icon: string; href: string }>;
};

export type Employee = {
  employee_id: string;
  staff_id: string;
  full_name: string;
  email: string;
  department: string;
  branch: string;
  rank: string;
  status: string;
  hire_date: string;
};

export type EmployeeListResponse = {
  employees: Employee[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
};

export type EmployeeSummaryResponse = {
  employee: Record<string, unknown>;
  appraisals: Array<Record<string, unknown>>;
  leaves: Array<Record<string, unknown>>;
};

export type ProfileDataResponse = {
  profile: {
    firstName?: string;
    lastName?: string;
    otherNames?: string;
    staffId?: string;
    email?: string;
    phone?: string;
    gender?: string;
    [key: string]: unknown;
  };
  employment: {
    organization?: string;
    branch?: string;
    department?: string;
    position?: string;
    rank?: string;
    status?: string;
    [key: string]: unknown;
  };
  qualifications: Array<{ title?: string; institution?: string; [key: string]: unknown }>;
  emergency_contacts: Array<{ name?: string; relationship?: string; phone?: string; [key: string]: unknown }>;
  documents: Array<{ name?: string; category?: string; type?: string; [key: string]: unknown }>;
  quick_stats: {
    years_of_service?: string;
    leave_balance?: string;
    appraisal_score?: string;
    certifications?: string;
    [key: string]: unknown;
  };
};

export type AppraisalModuleResponse = {
  manager: {
    stats: {
      active_cycles?: number;
      completed?: number;
      pending?: number;
      overdue?: number;
      [key: string]: number | undefined;
    };
    team_stats: Array<{ name?: string; score?: number | null; completed?: number; pending?: number; [key: string]: unknown }>;
    recent_activity: Array<{ name?: string; action?: string; time?: string; status?: string; [key: string]: unknown }>;
  };
  employee: {
    current_cycle: { title?: string; due_date?: string; overall_progress?: number; [key: string]: unknown };
    sections: Array<{ name?: string; weight?: number; status?: string; score?: number | null; maxScore?: number; [key: string]: unknown }>;
    goals: Array<{ title?: string; progress?: number; dueDate?: string; priority?: string; [key: string]: unknown }>;
    past_appraisals: Array<{
      submission_id?: string;
      appraisal_id?: string;
      cycle?: string;
      score?: number | null;
      rating?: string;
      status?: string;
      date?: string;
      submitted?: boolean;
      reviewed?: boolean;
      reviewer?: string;
      comments?: string;
      [key: string]: unknown;
    }>;
    trend_message: string;
  };
};

export type AppraisalHistoryDetailResponse = {
  entry_id: string;
  cycle?: string;
  status?: string;
  score?: number | null;
  rating?: string;
  submitted?: boolean;
  reviewed?: boolean;
  reviewer?: string;
  comments?: string;
  date?: string;
  [key: string]: unknown;
};

export type ModuleCapabilitiesResponse = {
  module: string;
  version: string;
  features: string[];
  actions: string[];
  workflow: { state?: string; stage?: string; [key: string]: unknown };
};

export type ModuleTasksResponse = {
  module: string;
  workflow?: { state?: string; stage?: string; [key: string]: unknown };
  tasks: Array<{ task_id: string; module: string; title: string; status: string; action_id?: string }>;
};

export type EappraisalDiagnosticsResponse = {
  enabled: boolean;
  probes: {
    appraisal_summary?: { ok: boolean; detail?: string; [key: string]: unknown };
    my_appraisals?: { ok: boolean; detail?: string; [key: string]: unknown };
    employee_appraisals?: { ok: boolean; detail?: string; [key: string]: unknown };
    [key: string]: { ok?: boolean; detail?: string; [key: string]: unknown } | undefined;
  };
  [key: string]: unknown;
};

export type IntegrationsSummaryResponse = {
  enabled: boolean;
  overall_ok: boolean;
  tenant: {
    tenant_id: string;
    code: string;
    name: string;
    employee_probe_id: string;
  };
  modules: {
    srms?: { enabled: boolean; configured: boolean; ready: boolean; status?: string; ok: boolean; detail?: string; status_code?: number };
    eappraisal?: { enabled: boolean; configured: boolean; ready: boolean; status?: string; ok: boolean; detail?: string; status_code?: number };
    eleave?: { enabled: boolean; configured: boolean; ready: boolean; status?: string; ok: boolean; detail?: string; status_code?: number };
    [key: string]: { enabled?: boolean; configured?: boolean; ready?: boolean; status?: string; ok?: boolean; detail?: string; status_code?: number } | undefined;
  };
  recommended_actions?: string[];
};

export type ModuleReadinessSnapshotResponse = {
  tenant: { tenant_id: string; code: string; name: string };
  identity: { email?: string | null; username?: string | null; employee_id?: string | null };
  modules: Record<string, { ready: boolean; code: string; detail: string }>;
};

export type JitAuditSnapshotResponse = {
  tenant_id: string;
  module_name?: string | null;
  rows_count: number;
  rows: Array<{
    id?: number;
    run_id?: string;
    tenant_id: string;
    module_name: string;
    employee_id?: string | null;
    email?: string | null;
    idempotency_key?: string | null;
    status: string;
    created_at?: string;
    payload_json?: Record<string, unknown>;
  }>;
  cooldown_settings: Array<{
    tenant_id: string;
    setting_key: string;
    value_json: Record<string, unknown>;
    updated_at?: string;
  }>;
  tenant_links?: Array<{
    source_tenant_id: string;
    target_module: string;
    target_tenant_ref?: string | null;
    decision: string;
    updated_at?: string;
    evidence_json?: Record<string, unknown>;
  }>;
};

export type LeaveModuleResponse = {
  manager: {
    stats: {
      total_this_year?: number;
      approved?: number;
      pending?: number;
      rejected?: number;
      [key: string]: number | undefined;
    };
    pending_requests: Array<{
      id?: string;
      name?: string;
      type?: string;
      days?: number;
      from?: string;
      to?: string;
      appliedOn?: string;
      department?: string;
      reliefOfficer?: string;
      [key: string]: unknown;
    }>;
  };
  employee: {
    balances: Array<{ type?: string; total?: number; used?: number; pending?: number; color?: string; [key: string]: unknown }>;
    history: Array<{ id?: string; type?: string; days?: number; startDate?: string; endDate?: string; status?: string; appliedOn?: string; approvedBy?: string | null; [key: string]: unknown }>;
    holidays: Array<{ name?: string; date?: string; [key: string]: unknown }>;
  };
};

export type TenantBrandingResponse = {
  tenant_id: string;
  branding: {
    brand_name: string;
    support_email: string;
    logo_primary_uri?: string;
    logo_symbol_uri?: string;
    favicon_uri?: string;
    theme?: Record<string, unknown>;
  };
};

export type TenantRow = {
  tenant_id: string;
  code: string;
  name: string;
  srms_schema?: string | null;
  srms_slug?: string | null;
  eappraisal_subdomain?: string | null;
  eleave_subdomain?: string | null;
  is_active: boolean;
  lifecycle_status?: string;
};

export type TenantListResponse = {
  tenants: TenantRow[];
  total: number;
};

export type TenantStorageProvidersResponse = {
  tenant_id: string;
  providers: Array<{ name: string; config?: Record<string, unknown> }>;
};

export type TenantUserPasswordResetResponse = {
  reset_applied: boolean;
  idempotency_key?: string | null;
  idempotent_replay?: boolean;
  target_email?: string;
  target_username?: string;
  temporary_password?: string | null;
  password_reset_applied?: string;
  reason?: string;
};

export type FederatedKeycloakSyncResultRow = {
  tenant_id: string;
  status: string;
  email: string;
  username: string;
  keycloak_user_id?: string | null;
  error?: string;
};

export type FederatedKeycloakSyncResponse = {
  enabled: boolean;
  dry_run: boolean;
  max_users: number;
  processed_users: number;
  created_count: number;
  existing_count: number;
  skipped_missing_email: number;
  skipped_no_temporary_password?: number;
  failed_count: number;
  welcome_emails_sent?: number;
  welcome_emails_skipped?: number;
  dev_credentials_exports?: string[];
  tenant_discovery?: Array<{
    tenant: { tenant_id?: string; code?: string; name?: string };
    summary: { users_total?: number; errors_count?: number };
    module_status: Record<string, { status?: string; detail?: string }>;
    errors?: Array<{ module?: string; error?: string }>;
  }>;
  results: FederatedKeycloakSyncResultRow[];
};

function unwrapEnvelopeData<T>(payload: unknown): T {
  const maybeEnvelope = payload as { data?: T } | null;
  if (maybeEnvelope && typeof maybeEnvelope === 'object' && 'data' in maybeEnvelope && maybeEnvelope.data) {
    return maybeEnvelope.data;
  }
  return payload as T;
}

export const getIdentity = async (): Promise<UserIdentity> => {
  const r = await httpClient.get<UserIdentity>('/me');
  return r.data;
};

export const getDashboardSummary = async (): Promise<DashboardSummary> => {
  if (useGraphqlGateway) {
    type GatewayPayload = {
      dashboard_summary: {
        ok: boolean;
        data: DashboardSummary;
        error?: { code?: string; message?: string } | null;
      };
    };
    const data = await gatewayRequest<GatewayPayload>(`
      query DashboardSummary {
        dashboard_summary {
          ok
          data
          error {
            code
            message
          }
        }
      }
    `);
    if (!data.dashboard_summary.ok) {
      throw new Error(data.dashboard_summary.error?.message || 'Gateway dashboard_summary failed');
    }
    return data.dashboard_summary.data;
  }
  const r = await httpClient.get<DashboardSummary>('/dashboard/summary');
  return r.data;
};

export const getEmployees = async (params: {
  search?: string;
  department?: string;
  status?: string;
  page?: number;
  page_size?: number;
}): Promise<EmployeeListResponse> => {
  const r = await httpClient.get<EmployeeListResponse>('/employees', { params });
  return r.data;
};

export const getTeamEmployees = async (params: {
  search?: string;
  department?: string;
  status?: string;
  page?: number;
  page_size?: number;
}): Promise<EmployeeListResponse & { scope?: string; source?: string; message?: string }> => {
  const r = await httpClient.get<EmployeeListResponse & { scope?: string; source?: string; message?: string }>('/employees/team', { params });
  return r.data;
};

export const getEmployeeSummary = async (employeeId: string): Promise<EmployeeSummaryResponse> => {
  const r = await httpClient.get<EmployeeSummaryResponse>(`/employees/${encodeURIComponent(employeeId)}/summary`);
  return r.data;
};

export const getMyProfile = async (): Promise<ProfileDataResponse> => {
  const r = await httpClient.get<ProfileDataResponse>('/profile/me');
  return r.data;
};

export const getAppraisalModuleData = async (): Promise<AppraisalModuleResponse> => {
  const r = await httpClient.get<AppraisalModuleResponse>('/modules/appraisal');
  return r.data;
};

export const getAppraisalHistoryDetail = async (entryId: string): Promise<AppraisalHistoryDetailResponse> => {
  const r = await httpClient.get<AppraisalHistoryDetailResponse>(`/modules/appraisal/history/${encodeURIComponent(entryId)}`);
  return r.data;
};

export const getAppraisalCapabilities = async (): Promise<ModuleCapabilitiesResponse> => {
  const r = await httpClient.get<ModuleCapabilitiesResponse>('/modules/appraisal/capabilities');
  return r.data;
};

export const getAppraisalTasks = async (): Promise<ModuleTasksResponse> => {
  const r = await httpClient.get<ModuleTasksResponse>('/modules/appraisal/tasks');
  return r.data;
};

export const executeAppraisalAction = async (
  actionId: string,
  payload?: Record<string, unknown>
): Promise<Record<string, unknown>> => {
  const r = await httpClient.post<Record<string, unknown>>(`/modules/appraisal/actions/${encodeURIComponent(actionId)}`, payload ?? {});
  return r.data;
};

export const getEappraisalDiagnostics = async (): Promise<EappraisalDiagnosticsResponse> => {
  const r = await httpClient.get<EappraisalDiagnosticsResponse>('/debug/integrations/eappraisal');
  return r.data;
};

export const getIntegrationsSummary = async (): Promise<IntegrationsSummaryResponse> => {
  const r = await httpClient.get<IntegrationsSummaryResponse>('/debug/integrations/summary');
  return r.data;
};

export const getModuleReadinessSnapshot = async (params?: {
  tenant_id?: string;
  email?: string;
  username?: string;
  employee_id?: string;
}): Promise<ModuleReadinessSnapshotResponse> => {
  const r = await httpClient.get<ModuleReadinessSnapshotResponse>('/debug/integrations/module-readiness', { params });
  return r.data;
};

export const getJitAuditSnapshot = async (params?: {
  tenant_id?: string;
  module_name?: string;
  limit?: number;
}): Promise<JitAuditSnapshotResponse> => {
  const r = await httpClient.get<JitAuditSnapshotResponse>('/debug/integrations/jit/audit', { params });
  return r.data;
};

export const getLeaveModuleData = async (): Promise<LeaveModuleResponse> => {
  const r = await httpClient.get<LeaveModuleResponse>('/modules/leave');
  return r.data;
};

export const getModulesCatalog = async (): Promise<ModuleCatalogResponse> => {
  if (useGraphqlGateway) {
    type GatewayPayload = {
      module_catalog: {
        ok: boolean;
        data: ModuleCatalogResponse;
        error?: { code?: string; message?: string } | null;
      };
    };
    const data = await gatewayRequest<GatewayPayload>(`
      query ModuleCatalog {
        module_catalog {
          ok
          data
          error {
            code
            message
          }
        }
      }
    `);
    if (!data.module_catalog.ok) {
      throw new Error(data.module_catalog.error?.message || 'Gateway module_catalog failed');
    }
    return data.module_catalog.data;
  }
  const r = await httpClient.get<ModuleCatalogResponse>('/modules/catalog');
  return r.data;
};

export const createModuleHandoffLaunch = async (moduleId: string): Promise<ModuleHandoffLaunchResponse> => {
  if (useGraphqlGateway) {
    type GatewayPayload = {
      workspace_launch: {
        ok: boolean;
        data: ModuleHandoffLaunchResponse;
        error?: { code?: string; message?: string } | null;
      };
    };
    const data = await gatewayRequest<GatewayPayload>(
      `
      mutation WorkspaceLaunch($moduleId: String!) {
        workspace_launch(module_id: $moduleId) {
          ok
          data
          error {
            code
            message
          }
        }
      }
      `,
      { moduleId }
    );
    if (!data.workspace_launch.ok) {
      throw new Error(data.workspace_launch.error?.message || 'Gateway workspace_launch failed');
    }
    return data.workspace_launch.data;
  }
  const r = await httpClient.post<ModuleHandoffLaunchResponse>(`/modules/catalog/${encodeURIComponent(moduleId)}/handoff`);
  return r.data;
};

export type JitSetupResponse = {
  ok: boolean;
  status: string;
  dry_run?: boolean;
  enable?: unknown;
  provision?: unknown;
  detail?: string;
};

export const runJitModuleSetup = async (
  moduleName: string,
  params?: { tenant_id?: string; dry_run?: boolean }
): Promise<JitSetupResponse> => {
  const r = await httpClient.post<JitSetupResponse>(`/jit/modules/${encodeURIComponent(moduleName)}/setup`, undefined, {
    params,
  });
  return r.data;
};

export const getTenantBranding = async (tenantId: string): Promise<TenantBrandingResponse> => {
  const r = await httpClient.get<TenantBrandingResponse>(`/tenants/${encodeURIComponent(tenantId)}/branding`);
  return r.data;
};

export const listTenants = async (limit = 200): Promise<TenantListResponse> => {
  const r = await httpClient.get<TenantListResponse>('/tenants', { params: { limit } });
  return r.data;
};

export const updateTenantBranding = async (
  tenantId: string,
  payload: { brand_name?: string; support_email?: string; theme?: Record<string, unknown> }
): Promise<TenantBrandingResponse> => {
  const r = await httpClient.put<TenantBrandingResponse>(`/tenants/${encodeURIComponent(tenantId)}/branding`, payload);
  return r.data;
};

export const uploadTenantLogo = async (
  tenantId: string,
  logoKind: 'primary' | 'symbol' | 'favicon',
  file: File
): Promise<TenantBrandingResponse> => {
  const form = new FormData();
  form.append('file', file);
  const r = await httpClient.post<TenantBrandingResponse>(
    `/tenants/${encodeURIComponent(tenantId)}/branding/logo`,
    form,
    { params: { logo_kind: logoKind }, headers: { 'Content-Type': 'multipart/form-data' } }
  );
  return r.data;
};

export type TenantOnboardingImportResponse = {
  imported: boolean;
  result: unknown;
};

export const importTenantOnboarding = async (
  payload: {
    tenant_id?: string;
    code: string;
    name: string;
    srms_schema?: string;
    srms_slug?: string;
    eappraisal_subdomain?: string;
    eleave_subdomain?: string;
    is_active: boolean;
  }
): Promise<TenantOnboardingImportResponse> => {
  const r = await httpClient.post<TenantOnboardingImportResponse>('/tenants/onboarding/import', payload);
  return r.data;
};

export const getTenantStorageProviders = async (tenantId: string): Promise<TenantStorageProvidersResponse> => {
  const r = await httpClient.get<TenantStorageProvidersResponse>(`/tenants/${encodeURIComponent(tenantId)}/storage/providers`);
  return r.data;
};

export const updateTenantStorageProviders = async (
  tenantId: string,
  providers: Array<{ name: string; config?: Record<string, unknown> }>
): Promise<TenantStorageProvidersResponse> => {
  const r = await httpClient.put<TenantStorageProvidersResponse>(`/tenants/${encodeURIComponent(tenantId)}/storage/providers`, { providers });
  return r.data;
};

export const resetTenantUserPassword = async (
  tenantId: string,
  payload: { email?: string; username?: string; idempotency_key?: string; reason?: string }
): Promise<TenantUserPasswordResetResponse> => {
  const r = await httpClient.post(
    `/integrations/synchronization/tenant/${encodeURIComponent(tenantId)}/users/password-reset`,
    payload
  );
  return unwrapEnvelopeData<TenantUserPasswordResetResponse>(r.data);
};

export const runFederatedKeycloakSync = async (params?: {
  tenant_id?: string;
  dry_run?: boolean;
  max_users?: number;
}): Promise<FederatedKeycloakSyncResponse> => {
  const r = await httpClient.post<FederatedKeycloakSyncResponse>(
    params?.dry_run === false
      ? '/integrations/synchronization/enrollment/apply'
      : '/integrations/synchronization/enrollment/preview',
    null,
    { params: { tenant_id: params?.tenant_id, max_users: params?.max_users } }
  );
  return r.data;
};
