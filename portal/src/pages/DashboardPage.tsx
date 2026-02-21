import React, { useEffect, useState } from 'react';
import {
  Users,
  UserCheck,
  User,
  Layers,
  ClipboardCheck,
  ClipboardList,
  CalendarDays,
  CalendarCheck,
  CalendarClock,
  CalendarPlus,
  TrendingUp,
  Briefcase,
  Star,
} from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts';
import { useAuth } from '../auth/AuthProvider';
import { getDashboardSummary, type DashboardSummary } from '../api/hrisCoreClient';
import { hasMinimumRole, HRIS_ROLES, getRoleLabel, isManagerRole } from '../auth/roles';
import { StatCard } from '../components/StatCard';
import { ModuleCard } from '../components/ModuleCard';
import { Link } from 'react-router-dom';

const PIE_COLORS = ['#10b981', '#f59e0b', '#ef4444', '#6b7280'];

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
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const role = user?.effectiveRole ?? HRIS_ROLES.EMPLOYEE;
  const isManager = isManagerRole(role);

  useEffect(() => {
    let mounted = true;
    setLoading(true);
    setError(null);
    getDashboardSummary()
      .then(d => { if (mounted) setData(d); })
      .catch(() => { if (mounted) setError('Failed to load dashboard data.'); })
      .finally(() => { if (mounted) setLoading(false); });
    return () => { mounted = false; };
  }, [role]);

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
      {isManager && (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6">
          <StatCard label="Total Staff" value={data.srms.total_employees} icon={Users} color="blue" />
          <StatCard label="Active Staff" value={data.srms.active_employees} icon={UserCheck} color="green" />
          <StatCard label="Departments" value={data.srms.departments} icon={Layers} color="purple" />
          <StatCard label="Pending Reviews" value={data.appraisal.pending_reviews} icon={ClipboardList} color="amber" />
          <StatCard label="Pending Leave" value={data.leave.pending_leaves} icon={CalendarClock} color="amber" />
          <StatCard label="Avg Score" value={data.appraisal.average_score.toFixed(1)} icon={TrendingUp} color="indigo" />
        </div>
      )}

      {/* Employee self-service stats */}
      {!isManager && (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <StatCard label="Leave Balance" value="15 days" icon={CalendarDays} color="blue" />
          <StatCard label="Leave Taken" value="8 days" icon={CalendarCheck} color="green" />
          <StatCard label="Pending Requests" value="1" icon={CalendarClock} color="amber" />
          <StatCard label="Appraisal Status" value="In Progress" icon={ClipboardCheck} color="purple" />
        </div>
      )}

      {/* Module Cards -- role-differentiated */}
      <div>
        <h2 className="mb-4 text-lg font-semibold text-gray-900">
          {isManager ? 'HR Modules' : 'My Services'}
        </h2>
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {isManager ? (
            <>
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
                  { label: 'Department', value: 'Information Technology' },
                  { label: 'Branch', value: 'Head Office' },
                  { label: 'Staff ID', value: 'STF-001' },
                  { label: 'Status', value: 'Active' },
                ]}
              />
              <ModuleCard
                title="My Appraisals"
                description="View your performance reviews and feedback"
                icon={Star}
                href="/modules/appraisal"
                color="purple"
                linkLabel="View Appraisals"
                stats={[
                  { label: 'Current Cycle', value: '2025/2026' },
                  { label: 'My Score', value: '3.9 / 5.0' },
                  { label: 'Status', value: 'In Progress' },
                  { label: 'Due Date', value: 'Mar 30' },
                ]}
              />
              <ModuleCard
                title="My Leave"
                description="Apply for leave and track your leave history"
                icon={CalendarPlus}
                href="/modules/leave"
                color="green"
                linkLabel="Manage Leave"
                stats={[
                  { label: 'Annual Balance', value: '15 days' },
                  { label: 'Used This Year', value: '8 days' },
                  { label: 'Pending', value: '1 request' },
                  { label: 'Sick Leave', value: '10 days' },
                ]}
              />
            </>
          )}
        </div>
      </div>

      {/* Charts -- managers and above */}
      {isManager && (
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
                  <Pie data={leaveChartData} cx="50%" cy="50%" outerRadius={90} innerRadius={50} dataKey="value" label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}>
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
              {[
                { label: 'Appraisal self-assessment due', date: 'Mar 30, 2026', color: 'text-purple-600 bg-purple-50' },
                { label: 'Annual leave request (pending)', date: 'Feb 25 - Feb 27', color: 'text-amber-600 bg-amber-50' },
                { label: 'Public holiday - Independence Day', date: 'Mar 6, 2026', color: 'text-green-600 bg-green-50' },
              ].map((item, i) => (
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
              {[
                { action: 'Leave request submitted', detail: 'Annual Leave - 3 days', time: '2 hours ago' },
                { action: 'Appraisal section completed', detail: 'Key Competencies', time: '1 day ago' },
                { action: 'Leave approved', detail: 'Sick Leave - Dec 15', time: '2 weeks ago' },
              ].map((item, i) => (
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
