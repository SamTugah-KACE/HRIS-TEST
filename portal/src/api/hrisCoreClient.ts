import { httpClient } from './httpClient';

export type UserIdentity = {
  sub: string;
  username: string;
  email?: string;
  tenant_id: string;
  roles: string[];
  effective_role: string;
  tenant: {
    code: string;
    name: string;
    modules: { srms: boolean; eappraisal: boolean; eleave: boolean };
  };
  available_roles: string[];
};

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

export const getIdentity = async (): Promise<UserIdentity> => {
  const r = await httpClient.get<UserIdentity>('/me');
  return r.data;
};

export const getDashboardSummary = async (): Promise<DashboardSummary> => {
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

export const getEmployeeSummary = async (employeeId: string): Promise<EmployeeSummaryResponse> => {
  const r = await httpClient.get<EmployeeSummaryResponse>(`/employees/${encodeURIComponent(employeeId)}/summary`);
  return r.data;
};
