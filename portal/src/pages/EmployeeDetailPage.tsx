import React, { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { ArrowLeft, User, Briefcase, Mail, Phone, MapPin, Calendar, ClipboardList, CalendarDays } from 'lucide-react';
import { getEmployeeSummary, type EmployeeSummaryResponse } from '../api/hrisCoreClient';
import { clsx } from 'clsx';

const isHonorific = (value: unknown): boolean => {
  const raw = String(value ?? '').trim().toLowerCase();
  const compact = raw.replace(/[^a-z0-9]/g, '');
  return ['mr', 'mrs', 'ms', 'miss', 'dr', 'prof', 'phd'].includes(compact);
};

export const EmployeeDetailPage: React.FC = () => {
  const { employeeId } = useParams<{ employeeId: string }>();
  const [data, setData] = useState<EmployeeSummaryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'profile' | 'appraisals' | 'leaves'>('profile');

  useEffect(() => {
    if (!employeeId) { setError('Missing employee ID.'); setLoading(false); return; }
    let mounted = true;
    getEmployeeSummary(employeeId)
      .then(d => { if (mounted) setData(d); })
      .catch(() => { if (mounted) setError('Failed to load employee data.'); })
      .finally(() => { if (mounted) setLoading(false); });
    return () => { mounted = false; };
  }, [employeeId]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="h-10 w-10 animate-spin rounded-full border-4 border-gray-300 border-t-brand-500" />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="space-y-4">
        <Link to="/employees" className="inline-flex items-center gap-1 text-sm text-brand-500 hover:text-brand-600">
          <ArrowLeft className="h-4 w-4" /> Back to Staff Records
        </Link>
        <div className="rounded-xl border border-red-200 bg-red-50 p-6">
          <p className="text-sm text-red-700">{error ?? 'No data available.'}</p>
        </div>
      </div>
    );
  }

  const emp = data.employee as Record<string, string>;
  const titleValue = isHonorific(emp.position) ? String(emp.position ?? '').trim() : '';
  const displayName = [titleValue, String(emp.full_name ?? '').trim()].filter(Boolean).join(' ').trim() || 'Employee';
  const displayPosition = isHonorific(emp.position) ? '' : String(emp.position ?? '').trim();
  const headerSubtitleLeft = displayPosition || String(emp.rank ?? '').trim() || String(emp.employee_type ?? '').trim() || 'Position not available';
  const headerSubtitleRight = String(emp.department ?? '').trim() || String(emp.unit ?? '').trim() || 'Department not available';
  const tabs = [
    { id: 'profile' as const, label: 'Profile', icon: User },
    { id: 'appraisals' as const, label: 'Appraisals', icon: ClipboardList, count: data.appraisals.length },
    { id: 'leaves' as const, label: 'Leave History', icon: CalendarDays, count: data.leaves.length },
  ];

  return (
    <div className="space-y-6">
      <Link to="/employees" className="inline-flex items-center gap-1 text-sm text-brand-500 hover:text-brand-600">
        <ArrowLeft className="h-4 w-4" /> Back to Staff Records
      </Link>

      {/* Employee Header */}
      <div className="card flex flex-col gap-4 sm:flex-row sm:items-center">
        <div className="flex h-16 w-16 items-center justify-center rounded-full bg-brand-500 text-xl font-bold text-white">
          {(emp.first_name?.[0] ?? emp.full_name?.[0] ?? 'E').toUpperCase()}
        </div>
        <div className="flex-1">
          <h1 className="text-xl font-bold text-gray-900">{displayName}</h1>
          <p className="text-sm text-gray-500">{headerSubtitleLeft} &middot; {headerSubtitleRight}</p>
          <div className="mt-2 flex flex-wrap gap-2">
            <span className={clsx(
              'inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium',
              emp.status === 'Active' ? 'bg-emerald-50 text-emerald-700' : 'bg-gray-100 text-gray-600'
            )}>
              {emp.status}
            </span>
            <span className="inline-flex rounded-full bg-blue-50 px-2.5 py-0.5 text-xs font-medium text-blue-700">
              {emp.employee_type}
            </span>
          </div>
        </div>
        <div className="text-right text-sm text-gray-500">
          <p className="font-mono">{emp.staff_id}</p>
          <p className="mt-1">{emp.branch}</p>
        </div>
      </div>

      {/* Tabs */}
      <div className="border-b border-gray-200">
        <div className="flex gap-6">
          {tabs.map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={clsx(
                'flex items-center gap-2 border-b-2 pb-3 text-sm font-medium transition-colors',
                activeTab === tab.id
                  ? 'border-brand-500 text-brand-500'
                  : 'border-transparent text-gray-500 hover:text-gray-700'
              )}
            >
              <tab.icon className="h-4 w-4" />
              {tab.label}
              {tab.count !== undefined && (
                <span className="rounded-full bg-gray-100 px-1.5 py-0.5 text-xs">{tab.count}</span>
              )}
            </button>
          ))}
        </div>
      </div>

      {/* Profile Tab */}
      {activeTab === 'profile' && (
        <div className="grid gap-6 lg:grid-cols-2">
          <div className="card">
            <h3 className="mb-4 text-sm font-semibold text-gray-900">Personal Information</h3>
            <dl className="space-y-3">
              {[
                { icon: User, label: 'Staff ID', value: emp.staff_id },
                { icon: Mail, label: 'Email', value: emp.email },
                { icon: Phone, label: 'Phone', value: emp.phone },
                { icon: User, label: 'Gender', value: emp.gender },
                { icon: Calendar, label: 'Hire Date', value: emp.hire_date },
              ].map(item => (
                <div key={item.label} className="flex items-start gap-3">
                  <item.icon className="mt-0.5 h-4 w-4 text-gray-400" />
                  <div>
                    <dt className="text-xs text-gray-500">{item.label}</dt>
                    <dd className="text-sm font-medium text-gray-900">{item.value ?? '—'}</dd>
                  </div>
                </div>
              ))}
            </dl>
          </div>
          <div className="card">
            <h3 className="mb-4 text-sm font-semibold text-gray-900">Organization</h3>
            <dl className="space-y-3">
              {[
                { icon: Briefcase, label: 'Organization', value: emp.organization },
                { icon: MapPin, label: 'Branch', value: emp.branch },
                { icon: Briefcase, label: 'Department', value: emp.department },
                { icon: Briefcase, label: 'Unit', value: emp.unit },
                { icon: Briefcase, label: 'Position', value: displayPosition },
                { icon: Briefcase, label: 'Rank', value: emp.rank },
                { icon: Briefcase, label: 'Employee Type', value: emp.employee_type },
                { icon: User, label: 'Status', value: emp.status },
              ].map(item => (
                <div key={item.label} className="flex items-start gap-3">
                  <item.icon className="mt-0.5 h-4 w-4 text-gray-400" />
                  <div>
                    <dt className="text-xs text-gray-500">{item.label}</dt>
                    <dd className="text-sm font-medium text-gray-900">{item.value ?? '—'}</dd>
                  </div>
                </div>
              ))}
            </dl>
          </div>
        </div>
      )}

      {/* Appraisals Tab */}
      {activeTab === 'appraisals' && (
        <div className="card overflow-hidden p-0">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-gray-200 bg-gray-50">
              <tr>
                <th className="px-4 py-3 font-medium text-gray-500">Cycle</th>
                <th className="px-4 py-3 font-medium text-gray-500">Score</th>
                <th className="px-4 py-3 font-medium text-gray-500">Rating</th>
                <th className="px-4 py-3 font-medium text-gray-500">Status</th>
                <th className="px-4 py-3 font-medium text-gray-500">Date</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {data.appraisals.length === 0 ? (
                <tr><td colSpan={5} className="px-4 py-8 text-center text-gray-400">No appraisal records.</td></tr>
              ) : data.appraisals.map((a: Record<string, unknown>, i) => (
                <tr key={i} className="hover:bg-gray-50">
                  <td className="px-4 py-3 font-medium text-gray-900">{a.cycle_name as string}</td>
                  <td className="px-4 py-3">{a.overall_score != null ? String(a.overall_score) : '—'}</td>
                  <td className="px-4 py-3">{(a.rating as string) ?? '—'}</td>
                  <td className="px-4 py-3">
                    <span className={clsx(
                      'inline-flex rounded-full px-2 py-0.5 text-xs font-medium',
                      a.status === 'completed' ? 'bg-emerald-50 text-emerald-700' : 'bg-amber-50 text-amber-700'
                    )}>
                      {a.status as string}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-gray-500">{a.date as string}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Leaves Tab */}
      {activeTab === 'leaves' && (
        <div className="card overflow-hidden p-0">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-gray-200 bg-gray-50">
              <tr>
                <th className="px-4 py-3 font-medium text-gray-500">Type</th>
                <th className="px-4 py-3 font-medium text-gray-500">Days</th>
                <th className="px-4 py-3 font-medium text-gray-500">Start</th>
                <th className="px-4 py-3 font-medium text-gray-500">End</th>
                <th className="px-4 py-3 font-medium text-gray-500">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {data.leaves.length === 0 ? (
                <tr><td colSpan={5} className="px-4 py-8 text-center text-gray-400">No leave records.</td></tr>
              ) : data.leaves.map((l: Record<string, unknown>, i) => (
                <tr key={i} className="hover:bg-gray-50">
                  <td className="px-4 py-3 font-medium text-gray-900">{l.type as string}</td>
                  <td className="px-4 py-3">{String(l.days)}</td>
                  <td className="px-4 py-3 text-gray-500">{l.start_date as string}</td>
                  <td className="px-4 py-3 text-gray-500">{l.end_date as string}</td>
                  <td className="px-4 py-3">
                    <span className={clsx(
                      'inline-flex rounded-full px-2 py-0.5 text-xs font-medium',
                      l.status === 'approved' ? 'bg-emerald-50 text-emerald-700' :
                      l.status === 'pending' ? 'bg-amber-50 text-amber-700' : 'bg-red-50 text-red-700'
                    )}>
                      {l.status as string}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};
