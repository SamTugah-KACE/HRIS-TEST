import React, { useEffect, useState } from 'react';
import {
  Users,
  UserCheck,
  User,
  Building2,
  Layers,
  ClipboardCheck,
  ClipboardList,
  CalendarDays,
  CalendarCheck,
  CalendarClock,
  CalendarPlus,
  TrendingUp,
  Star,
} from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts';
import { useAuth } from '../auth/AuthProvider';
import { getDashboardSummary, type DashboardSummary } from '../api/hrisCoreClient';
import { getMyProfile, getAppraisalModuleData, getLeaveModuleData, type ProfileDataResponse, type AppraisalModuleResponse, type LeaveModuleResponse } from '../api/hrisCoreClient';
import { getIntegrationsSummary, type IntegrationsSummaryResponse } from '../api/hrisCoreClient';
import { getModulesCatalog, type ModuleCatalogItem } from '../api/hrisCoreClient';
import { HRIS_ROLES, getRoleLabel, isManagerRole } from '../auth/roles';
import { StatCard } from '../components/StatCard';
import { ModuleCard } from '../components/ModuleCard';
import { Link } from 'react-router-dom';
import { isApiDataMode } from '../config/dataMode';

const PIE_COLORS = ['#10b981', '#f59e0b', '#ef4444', '#6b7280'];

function parseLooseDate(input: unknown): Date | null {
  const raw = String(input ?? '').trim();
  if (!raw) return null;
  const parsed = new Date(raw);
  if (!Number.isNaN(parsed.getTime())) return parsed;
  const normalized = raw.replace(/\s+/g, ' ');
  const parsedNormalized = new Date(normalized);
  return Number.isNaN(parsedNormalized.getTime()) ? null : parsedNormalized;
}

function isOnOrAfterToday(input: unknown): boolean {
  const value = parseLooseDate(input);
  if (!value) return false;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const target = new Date(value);
  target.setHours(0, 0, 0, 0);
  return target.getTime() >= today.getTime();
}

function normalizeDateLabel(input: unknown): string {
  const parsed = parseLooseDate(input);
  if (!parsed) return '';
  return parsed.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
}

function toSafeHttpUrl(raw: string): string | null {
  const value = (raw || '').trim();
  if (!value) return null;
  try {
    const parsed = new URL(value);
    if (parsed.protocol === 'http:' || parsed.protocol === 'https:') return parsed.toString();
    return null;
  } catch {
    return null;
  }
}

function getDashboardTitle(role: string): string {
  switch (role) {
    case HRIS_ROLES.SUPER_ADMIN: return 'System Administration';
    case HRIS_ROLES.TENANT_ADMIN: return 'Organization Dashboard';
    case HRIS_ROLES.HR_MANAGER: return 'HR Dashboard';
    case HRIS_ROLES.LINE_MANAGER: return 'Team Dashboard';
    default: return 'My Dashboard';
  }
}

function getDashboardSubtitle(role: string): string {
  switch (role) {
    case HRIS_ROLES.SUPER_ADMIN: return 'System-wide overview across all tenants and modules';
    case HRIS_ROLES.TENANT_ADMIN: return 'Full organization overview with all HR modules';
    case HRIS_ROLES.HR_MANAGER: return 'Staff records, performance appraisals, and leave management';
    case HRIS_ROLES.LINE_MANAGER: return 'Your team members, pending approvals, and reviews';
    default: return 'Your personal HR services at a glance';
  }
}

export const DashboardPage: React.FC = () => {
  const { user } = useAuth();
  const [data, setData] = useState<DashboardSummary | null>(null);
  const [profileData, setProfileData] = useState<ProfileDataResponse | null>(null);
  const [appraisalData, setAppraisalData] = useState<AppraisalModuleResponse | null>(null);
  const [leaveData, setLeaveData] = useState<LeaveModuleResponse | null>(null);
  const [integrationSummary, setIntegrationSummary] = useState<IntegrationsSummaryResponse | null>(null);
  const [catalogModules, setCatalogModules] = useState<ModuleCatalogItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const role = user?.effectiveRole ?? HRIS_ROLES.EMPLOYEE;
  const tenantId = user?.tenantId ?? '';
  const userSub = user?.sub ?? '';
  const isManager = isManagerRole(role);
  const isSuperAdmin = role === HRIS_ROLES.SUPER_ADMIN;
  const isTenantManager = isManager && !isSuperAdmin;

  useEffect(() => {
    let mounted = true;
    setLoading(true);
    setError(null);
    getDashboardSummary()
      .then(d => { if (mounted) setData(d); })
      .catch(() => { if (mounted) setError('Failed to load dashboard data.'); })
      .finally(() => { if (mounted) setLoading(false); });
    return () => { mounted = false; };
  }, [role, tenantId, userSub]);

  useEffect(() => {
    if (!isApiDataMode || isManager) return;
    let mounted = true;
    Promise.allSettled([getMyProfile(), getAppraisalModuleData(), getLeaveModuleData()])
      .then((results) => {
        if (!mounted) return;
        const [profileResult, appraisalResult, leaveResult] = results;
        if (profileResult.status === 'fulfilled') {
          setProfileData(profileResult.value);
        }
        if (appraisalResult.status === 'fulfilled') {
          setAppraisalData(appraisalResult.value);
        }
        if (leaveResult.status === 'fulfilled') {
          setLeaveData(leaveResult.value);
        }
      })
      .catch(() => {
        // Keep page resilient; top-level summary still loads and drives navigation/actions.
      });
    return () => {
      mounted = false;
    };
  }, [isManager, role]);

  useEffect(() => {
    let mounted = true;
    getModulesCatalog()
      .then((result) => {
        if (!mounted) return;
        setCatalogModules(Array.isArray(result.modules) ? result.modules : []);
      })
      .catch(() => {
        if (!mounted) return;
        setCatalogModules([]);
      });
    return () => { mounted = false; };
  }, [role, tenantId, userSub]);

  useEffect(() => {
    if (!isTenantManager) {
      setIntegrationSummary(null);
      return;
    }
    let mounted = true;
    getIntegrationsSummary()
      .then((result) => { if (mounted) setIntegrationSummary(result); })
      .catch(() => { if (mounted) setIntegrationSummary(null); });
    return () => { mounted = false; };
  }, [isTenantManager, role, tenantId, userSub]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="h-10 w-10 animate-spin rounded-full border-4 border-gray-300 border-t-brand-500" />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="rounded-xl border border-red-200 bg-red-50 p-6">
        <p className="text-sm text-red-700">{error ?? 'No data available.'}</p>
      </div>
    );
  }

  const leaveChartData = [
    { name: 'Approved', value: data.leave.approved_leaves, color: '#10b981' },
    { name: 'Pending', value: data.leave.pending_leaves, color: '#f59e0b' },
    { name: 'Rejected', value: data.leave.rejected_leaves, color: '#ef4444' },
    { name: 'Cancelled', value: data.leave.cancelled_leaves, color: '#6b7280' },
  ];

  const staffChartData = [
    { name: 'Active', count: data.srms.active_employees },
    { name: 'Inactive', count: data.srms.inactive_employees },
    { name: 'New Hires', count: data.srms.new_hires_this_month },
    { name: 'Pending', count: data.srms.pending_enlistments },
  ];

  const employeeBalances = leaveData?.employee.balances ?? [];
  const annualBalance = employeeBalances.find((b) => String(b.type).toLowerCase().includes('annual'));
  const appraisalSections = appraisalData?.employee.sections ?? [];
  const appraisalCompleted = appraisalSections.filter((s) => String(s.status) === 'completed').length;
  const appraisalProgress = appraisalSections.length > 0 ? Math.round((appraisalCompleted / appraisalSections.length) * 100) : 0;
  const valueOr = (value: unknown, fallback: string): string => {
    const text = String(value ?? '').trim();
    return text ? text : fallback;
  };
  const employeeStatus = valueOr(profileData?.employment.status, 'Active');
  const employeeDepartment = valueOr(profileData?.employment.department, 'Not set');
  const employeeBranch = valueOr(profileData?.employment.branch, data.tenant.name);
  const employeeStaffId = valueOr(profileData?.profile.staffId, valueOr(profileData?.profile.email, data.user.username));
  const annualTotal = Number(annualBalance?.total ?? 0);
  const annualUsed = Number(annualBalance?.used ?? 0);
  const annualPending = Number(annualBalance?.pending ?? 0);
  const annualAvailable = Math.max(0, annualTotal - annualUsed - annualPending);
  const pendingLeaveEntry = (leaveData?.employee.history ?? [])
    .find((h) => String(h.status ?? '').toLowerCase() === 'pending' && isOnOrAfterToday(h.endDate ?? h.startDate));
  const upcomingItems = isApiDataMode ? [
    ...(appraisalData?.employee.current_cycle?.due_date && isOnOrAfterToday(appraisalData?.employee.current_cycle?.due_date) ? [{
      label: 'Appraisal self-assessment due',
      date: normalizeDateLabel(appraisalData.employee.current_cycle.due_date),
      color: 'text-purple-600 bg-purple-50 dark:text-purple-300 dark:bg-purple-900/30',
      sortDate: parseLooseDate(appraisalData.employee.current_cycle.due_date),
    }] : []),
    ...(pendingLeaveEntry ? [{
      label: `${String(pendingLeaveEntry.type ?? 'Leave')} request (pending)`,
      date: `${normalizeDateLabel(pendingLeaveEntry.startDate)} - ${normalizeDateLabel(pendingLeaveEntry.endDate || pendingLeaveEntry.startDate)}`.trim(),
      color: 'text-amber-600 bg-amber-50 dark:text-amber-300 dark:bg-amber-900/30',
      sortDate: parseLooseDate(pendingLeaveEntry.startDate),
    }] : []),
    ...((leaveData?.employee.holidays ?? [])
      .filter((entry) => isOnOrAfterToday(entry.date))
      .map((entry) => ({
        label: String(entry.name ?? 'Holiday'),
        date: normalizeDateLabel(entry.date),
        color: 'text-green-600 bg-green-50 dark:text-green-300 dark:bg-green-900/30',
        sortDate: parseLooseDate(entry.date),
      }))),
  ]
    .filter((item) => String(item.date ?? '').trim())
    .sort((a, b) => {
      const at = a.sortDate instanceof Date ? a.sortDate.getTime() : Number.MAX_SAFE_INTEGER;
      const bt = b.sortDate instanceof Date ? b.sortDate.getTime() : Number.MAX_SAFE_INTEGER;
      return at - bt;
    })
    .slice(0, 3)
    : [];
  const recentItems = isApiDataMode ? [
    ...((leaveData?.employee.history ?? []).slice(0, 2).map((entry) => ({
      action: `${String(entry.type ?? 'Leave')} ${String(entry.status ?? 'updated')}`.trim(),
      detail: `${String(entry.startDate ?? '')} - ${String(entry.endDate ?? '')}`.trim(),
      time: String(entry.appliedOn ?? 'recently'),
    }))),
    ...(appraisalSections.filter((s) => String(s.status ?? '').toLowerCase() === 'completed').slice(0, 1).map((section) => ({
      action: 'Appraisal section completed',
      detail: String(section.name ?? 'Section'),
      time: 'recently',
    }))),
  ] : [];
  const enabledModuleIds = new Set(
    catalogModules
      .filter((module) => module.enabled && module.visible)
      .map((module) => String(module.id).toLowerCase())
  );
  const hasSrms = enabledModuleIds.size === 0 || enabledModuleIds.has('srms');
  const hasEappraisal = enabledModuleIds.size === 0 || enabledModuleIds.has('eappraisal');
  const hasEleave = enabledModuleIds.size === 0 || enabledModuleIds.has('eleave');

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">{getDashboardTitle(role)}</h1>
        <p className="mt-1 text-sm text-gray-500">
          Welcome back, <span className="font-medium">{data.user.username}</span>.{' '}
          {getDashboardSubtitle(role)}
        </p>
        <div className="mt-2 flex items-center gap-2">
          <span className="inline-flex items-center rounded-full bg-brand-500/10 px-2.5 py-0.5 text-xs font-medium text-brand-500">
            {getRoleLabel(role)}
          </span>
          <span className="text-xs text-gray-400">&middot;</span>
          <span className="text-xs text-gray-500">{data.tenant.name}</span>
        </div>
      </div>

      {/* KPI Stats Grid -- managers and above see org-wide stats */}
      {isTenantManager && (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6">
          <StatCard label="Total Staff" value={data.srms.total_employees} icon={Users} color="blue" />
          <StatCard label="Active Staff" value={data.srms.active_employees} icon={UserCheck} color="green" />
          <StatCard label="Departments" value={data.srms.departments} icon={Layers} color="purple" />
          <StatCard label="Pending Reviews" value={data.appraisal.pending_reviews} icon={ClipboardList} color="amber" />
          <StatCard label="Pending Leave" value={data.leave.pending_leaves} icon={CalendarClock} color="amber" />
          <StatCard label="Avg Score" value={data.appraisal.average_score.toFixed(1)} icon={TrendingUp} color="indigo" />
        </div>
      )}

      {isTenantManager && integrationSummary && (
        <div className="card">
          <div className="mb-3 flex items-center justify-between">
            <h3 className="text-sm font-semibold text-gray-900">Integration Health</h3>
            <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${integrationSummary.overall_ok ? 'bg-emerald-50 text-emerald-700' : 'bg-amber-50 text-amber-700'}`}>
              {integrationSummary.overall_ok ? 'Healthy' : 'Attention Needed'}
            </span>
          </div>
          <div className="grid gap-2 md:grid-cols-3">
            {([...enabledModuleIds].length > 0 ? [...enabledModuleIds] : ['srms', 'eappraisal', 'eleave']).map((moduleName) => {
              const moduleInfo = integrationSummary.modules[moduleName];
              if (!moduleInfo) return null;
              return (
                <div key={moduleName} className="rounded-lg border border-gray-200 px-3 py-2">
                  <div className="flex items-center justify-between">
                    <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">{moduleName}</p>
                    <span className={`inline-flex rounded-full px-2 py-0.5 text-[11px] font-medium ${moduleInfo.ok ? 'bg-emerald-50 text-emerald-700' : 'bg-red-50 text-red-700'}`}>
                      {moduleInfo.ok ? 'ok' : 'issue'}
                    </span>
                  </div>
                  <p className="mt-1 text-xs text-gray-600">{moduleInfo.detail || 'n/a'}</p>
                </div>
              );
            })}
          </div>
          {(integrationSummary.recommended_actions || []).length > 0 && (
            <p className="mt-3 text-xs text-amber-700">
              {integrationSummary.recommended_actions?.[0]}
            </p>
          )}
        </div>
      )}

      {isSuperAdmin && data.superadmin && (
        <div className="card">
          <div className="mb-4 flex items-center justify-between">
            <div>
              <h3 className="text-sm font-semibold text-gray-900">SRMS Tenant Organizations</h3>
            </div>
            <div className="flex items-center gap-2 text-xs text-gray-600">
              <span className="rounded-full bg-gray-100 px-2 py-0.5">Total {data.superadmin.tenant_summary.total}</span>
              <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-emerald-700">Active {data.superadmin.tenant_summary.active}</span>
              <span className="rounded-full bg-gray-100 px-2 py-0.5">Inactive {data.superadmin.tenant_summary.inactive}</span>
            </div>
          </div>
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead className="border-b border-gray-200 bg-gray-50">
                <tr>
                  <th className="px-3 py-2 font-medium text-gray-500">Organization</th>
                  <th className="px-3 py-2 font-medium text-gray-500">Organization Type</th>
                  <th className="px-3 py-2 font-medium text-gray-500">Domain</th>
                  <th className="px-3 py-2 font-medium text-gray-500">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {data.superadmin.tenants.map((tenant) => {
                  const rowOrganizationType = tenant.organization_type || (tenant.type && tenant.nature ? `${tenant.type} - ${tenant.nature}` : '') || 'N/A';
                  const rowDomain = tenant.access_url || tenant.slug || 'N/A';
                  const safeDomainUrl = toSafeHttpUrl(rowDomain === 'N/A' ? '' : rowDomain);
                  return (
                  <tr key={tenant.tenant_id || `${tenant.name}-${rowDomain}`} className="hover:bg-gray-50">
                    <td className="px-3 py-2">
                      <div className="flex items-center gap-2">
                        <Building2 className="h-4 w-4 text-gray-400" />
                        <span className="font-medium text-gray-900">{tenant.name}</span>
                      </div>
                    </td>
                    <td className="px-3 py-2 font-mono text-xs text-gray-600">{rowOrganizationType}</td>
                    <td className="px-3 py-2 text-xs text-gray-600">
                      {safeDomainUrl ? (
                        <a
                          className="text-brand-600 hover:underline"
                          href={safeDomainUrl}
                          rel="noreferrer"
                          target="_blank"
                        >
                          {safeDomainUrl}
                        </a>
                      ) : rowDomain}
                    </td>
                    <td className="px-3 py-2">
                      <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${tenant.status === 'active' ? 'bg-emerald-50 text-emerald-700' : 'bg-gray-100 text-gray-600'}`}>
                        {tenant.status}
                      </span>
                    </td>
                  </tr>
                )})}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Employee self-service stats */}
      {!isManager && (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <StatCard label="Leave Balance" value={isApiDataMode ? `${annualAvailable} days` : '15 days'} icon={CalendarDays} color="blue" />
          <StatCard label="Leave Taken" value={isApiDataMode ? `${annualUsed} days` : '8 days'} icon={CalendarCheck} color="green" />
          <StatCard label="Pending Requests" value={isApiDataMode ? String(annualPending) : '1'} icon={CalendarClock} color="amber" />
          <StatCard label="Appraisal Status" value={isApiDataMode ? `${appraisalProgress}% Complete` : 'In Progress'} icon={ClipboardCheck} color="purple" />
        </div>
      )}

      {/* Module Cards -- role-differentiated */}
      {!isSuperAdmin && (
      <div>
        <h2 className="mb-4 text-lg font-semibold text-gray-900">
          {isTenantManager ? 'HR Modules' : 'My Services'}
        </h2>
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {isTenantManager ? (
            <>
              {hasSrms && (
                <ModuleCard
                  title="Staff Records"
                  description="Central employee records and org structure"
                  icon={Users}
                  href="/employees"
                  color="blue"
                  stats={[
                    { label: 'Active Employees', value: data.srms.active_employees },
                    { label: 'Branches', value: data.srms.branches },
                    { label: 'Departments', value: data.srms.departments },
                    { label: 'New This Month', value: data.srms.new_hires_this_month },
                  ]}
                />
              )}
              {hasEappraisal && (
                <ModuleCard
                  title="Performance Appraisal"
                  description="Appraisal cycles, reviews, and feedback"
                  icon={ClipboardList}
                  href="/modules/appraisal"
                  color="purple"
                  stats={[
                    { label: 'Active Cycles', value: data.appraisal.active_cycles },
                    { label: 'Completion Rate', value: `${data.appraisal.completion_rate}%` },
                    { label: 'Pending Reviews', value: data.appraisal.pending_reviews },
                    { label: 'Overdue', value: data.appraisal.overdue_reviews },
                  ]}
                />
              )}
              {hasEleave && (
                <ModuleCard
                  title="Leave Management"
                  description="Leave requests, approvals, and schedules"
                  icon={CalendarDays}
                  href="/modules/leave"
                  color="green"
                  stats={[
                    { label: 'Total This Year', value: data.leave.total_leaves_this_year },
                    { label: 'Approved', value: data.leave.approved_leaves },
                    { label: 'Pending', value: data.leave.pending_leaves },
                    { label: 'Utilization', value: `${data.leave.leave_utilization_rate}%` },
                  ]}
                />
              )}
            </>
          ) : (
            <>
              <ModuleCard
                title="My Profile"
                description="View and update your personal information"
                icon={User}
                href="/profile"
                color="blue"
                linkLabel="View Profile"
                stats={[
                  { label: 'Department', value: isApiDataMode ? employeeDepartment : 'Information Technology' },
                  { label: 'Branch', value: isApiDataMode ? employeeBranch : 'Head Office' },
                  { label: 'Staff ID', value: isApiDataMode ? employeeStaffId : 'STF-001' },
                  { label: 'Status', value: isApiDataMode ? employeeStatus : 'Active' },
                ]}
              />
              {hasEappraisal && (
                <ModuleCard
                  title="My Appraisals"
                  description="View your performance reviews and feedback"
                  icon={Star}
                  href="/modules/appraisal"
                  color="purple"
                  linkLabel="View Appraisals"
                  stats={[
                    { label: 'Current Cycle', value: isApiDataMode ? String(appraisalData?.employee.current_cycle.title ?? 'Current Cycle') : '2025/2026' },
                    { label: 'My Score', value: isApiDataMode ? String(appraisalData?.employee.past_appraisals?.[0]?.score ?? 'N/A') : '3.9 / 5.0' },
                    { label: 'Status', value: isApiDataMode ? `${appraisalProgress}% Complete` : 'In Progress' },
                    { label: 'Due Date', value: isApiDataMode ? String(appraisalData?.employee.current_cycle.due_date ?? 'N/A') : 'Mar 30' },
                  ]}
                />
              )}
              {hasEleave && (
                <ModuleCard
                  title="My Leave"
                  description="Apply for leave and track your leave history"
                  icon={CalendarPlus}
                  href="/modules/leave"
                  color="green"
                  linkLabel="Manage Leave"
                  stats={[
                    { label: 'Annual Balance', value: isApiDataMode ? `${annualAvailable} days` : '15 days' },
                    { label: 'Used This Year', value: isApiDataMode ? `${annualUsed} days` : '8 days' },
                    { label: 'Pending', value: isApiDataMode ? `${annualPending} request(s)` : '1 request' },
                    { label: 'Sick Leave', value: isApiDataMode ? `${Number(employeeBalances.find((b) => String(b.type).toLowerCase().includes('sick'))?.total ?? 0)} days` : '10 days' },
                  ]}
                />
              )}
            </>
          )}
        </div>
      </div>
      )}

      {/* Charts -- managers and above */}
      {isTenantManager && (
        <div className="grid gap-6 lg:grid-cols-2">
          <div className="card">
            <h3 className="mb-4 text-sm font-semibold text-gray-900">Staff Overview</h3>
            <ResponsiveContainer width="100%" height={250}>
              <BarChart data={staffChartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis dataKey="name" tick={{ fontSize: 12 }} />
                <YAxis tick={{ fontSize: 12 }} />
                <Tooltip />
                <Bar dataKey="count" fill="#003366" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="card">
            <h3 className="mb-4 text-sm font-semibold text-gray-900">Leave Distribution</h3>
            <div className="flex items-center justify-center">
              <ResponsiveContainer width="100%" height={250}>
                <PieChart>
                  <Pie
                    data={leaveChartData}
                    cx="50%"
                    cy="50%"
                    outerRadius={90}
                    innerRadius={50}
                    dataKey="value"
                    label={({ name, percent }) => `${name} ${(((percent ?? 0) * 100)).toFixed(0)}%`}
                  >
                    {leaveChartData.map((entry, i) => (
                      <Cell key={entry.name} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip />
                </PieChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      )}

      {/* Employee upcoming events / recent activity */}
      {!isManager && (
        <div className="grid gap-6 lg:grid-cols-2">
          <div className="card">
            <h3 className="mb-4 text-sm font-semibold text-gray-900">Upcoming</h3>
            <div className="space-y-3">
              {(upcomingItems.length > 0 ? upcomingItems : [
                { label: 'No upcoming events', date: 'You are up to date', color: 'text-gray-600 bg-gray-100 dark:text-gray-300 dark:bg-gray-800' },
              ]).map((item, i) => (
                <div key={i} className="flex items-center justify-between rounded-lg border border-gray-100 p-3">
                  <p className="text-sm text-gray-900">{item.label}</p>
                  <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${item.color}`}>{item.date}</span>
                </div>
              ))}
            </div>
          </div>
          <div className="card">
            <h3 className="mb-4 text-sm font-semibold text-gray-900">Recent Activity</h3>
            <div className="space-y-3">
              {(recentItems.length > 0 ? recentItems : [
                { action: 'Leave request submitted', detail: 'Annual Leave - 3 days', time: '2 hours ago' },
                { action: 'Appraisal section completed', detail: 'Key Competencies', time: '1 day ago' },
                { action: 'Leave approved', detail: 'Sick Leave - Dec 15', time: '2 weeks ago' },
              ]).map((item, i) => (
                <div key={i} className="rounded-lg border border-gray-100 p-3">
                  <p className="text-sm font-medium text-gray-900">{item.action}</p>
                  <p className="text-xs text-gray-500">{item.detail} &middot; {item.time}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Quick Actions */}
      {data.quick_actions.length > 0 && (
        <div className="card">
          <h3 className="mb-4 text-sm font-semibold text-gray-900">Quick Actions</h3>
          <div className="flex flex-wrap gap-3">
            {data.quick_actions.map(action => (
              <Link
                key={action.id}
                to={action.href}
                className="btn-secondary text-sm"
              >
                {action.label}
              </Link>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
