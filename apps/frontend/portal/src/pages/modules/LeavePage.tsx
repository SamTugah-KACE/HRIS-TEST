import React, { useEffect, useState } from 'react';
import {
  CalendarDays, CalendarCheck, CalendarClock, CalendarX,
  CalendarPlus, CheckCircle, Download, Send, Filter, Eye, BarChart3,
} from 'lucide-react';
import { useAuth } from '../../auth/AuthProvider';
import { HRIS_ROLES, isManagerRole } from '../../auth/roles';
import { StatCard } from '../../components/StatCard';
import { ModuleNativeLaunchBanner } from '../../components/ModuleNativeLaunchBanner';
import { clsx } from 'clsx';
import { Link } from 'react-router-dom';
import { getLeaveModuleData, getModulesCatalog, runJitModuleSetup, type LeaveModuleResponse } from '../../api/hrisCoreClient';
import { getModuleModeHint } from '../../shared/moduleMode';

export const LeavePage: React.FC = () => {
  const { user } = useAuth();
  const role = user?.effectiveRole ?? HRIS_ROLES.EMPLOYEE;
  const isManager = isManagerRole(role);
  const [toast, setToast] = useState<string | null>(null);
  const [apiData, setApiData] = useState<LeaveModuleResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [jitSetupRunning, setJitSetupRunning] = useState(false);
  const [dataSourceMode, setDataSourceMode] = useState<'native' | 'unavailable'>('native');
  const [readMode, setReadMode] = useState('native-readonly');

  const showToast = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 3000);
  };

  const handleManagerAction = (id: string, action: 'approved' | 'rejected') => {
    showToast(`Open the eLeave workspace to mark request ${id} as ${action}.`);
  };

  useEffect(() => {
    let mounted = true;
    setLoading(true);
    setError(null);
    setJitSetupRunning(false);
    getLeaveModuleData()
      .then((d) => { if (mounted) setApiData(d); })
      .catch(async (err: unknown) => {
        if (!mounted) return;
        let message = 'Failed to load leave module data in API mode.';
        const maybeAxios = err as { response?: { status?: number; data?: { detail?: string | { code?: string; message?: string; action?: string } } } };
        const statusCode = maybeAxios?.response?.status;
        const detailRaw = maybeAxios?.response?.data?.detail;
        const detail = typeof detailRaw === 'string' ? detailRaw.trim() : String(detailRaw?.message || '').trim();
        const detailCode = typeof detailRaw === 'object' ? String(detailRaw?.code || '').trim() : '';
        const detailAction = typeof detailRaw === 'object' ? String(detailRaw?.action || '').trim() : '';
        if (statusCode === 403 && detail.toLowerCase().includes("module 'eleave' is not active")) {
          try {
            setJitSetupRunning(true);
            await runJitModuleSetup('eleave');
            const d2 = await getLeaveModuleData();
            if (mounted) {
              setApiData(d2);
              setError(null);
            }
            return;
          } catch {
            message = 'Leave is not active for your tenant (and setup could not be completed). Contact admin or try again later.';
          } finally {
            if (mounted) setJitSetupRunning(false);
          }
        } else if (statusCode === 403 && detail) {
          message = `Leave access denied: ${detail}`;
        } else if (statusCode === 409 && detailCode) {
          message = `Leave setup blocked (${detailCode}): ${detail || 'module not ready'}`;
          if (detailAction) {
            message = `${message}. Action: ${detailAction}`;
          }
        }
        setError(message);
      })
      .finally(() => { if (mounted) setLoading(false); });
    getModulesCatalog()
      .then((catalog) => {
        if (!mounted) return;
        const moduleRow = (catalog.modules || []).find((m) => String(m.id || '').toLowerCase() === 'eleave');
        const mode = String(moduleRow?.capabilities?.read_mode || 'native-readonly').trim();
        setDataSourceMode('native');
        setReadMode(mode || 'native-readonly');
      })
      .catch(() => {
        if (!mounted) return;
        setDataSourceMode('unavailable');
        setReadMode('native-readonly');
      });
    return () => { mounted = false; };
  }, []);

  const managerStats = apiData
    ? {
      total: Number(apiData.manager.stats.total_this_year ?? 0),
      approved: Number(apiData.manager.stats.approved ?? 0),
      pending: Number(apiData.manager.stats.pending ?? 0),
      rejected: Number(apiData.manager.stats.rejected ?? 0),
    }
    : { total: 0, approved: 0, pending: 0, rejected: 0 };
  const pendingRequests = apiData?.manager.pending_requests ?? [];
  const leaveBalances = apiData?.employee.balances ?? [];
  const leaveHistory = apiData?.employee.history ?? [];
  const holidays = apiData?.employee.holidays ?? [];

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="h-10 w-10 animate-spin rounded-full border-4 border-gray-300 border-t-brand-500" />
      </div>
    );
  }

  if (error || !apiData) {
    return (
      <div className="rounded-xl border border-red-200 bg-red-50 p-6">
        <p className="text-sm text-red-700">{error ?? 'No leave data available in API mode.'}</p>
        {jitSetupRunning && (
          <p className="mt-2 text-xs text-red-700">
            Setting up Leave for your organization…
          </p>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {toast && (
        <div className="fixed right-4 top-20 z-50 flex items-center gap-2 rounded-lg bg-emerald-600 px-4 py-3 text-sm font-medium text-white shadow-lg">
          <CheckCircle className="h-4 w-4" /> {toast}
        </div>
      )}

      <ModuleNativeLaunchBanner moduleId="eleave" />

      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">
            {isManager ? 'Leave Management' : 'My Leave'}
          </h1>
          <p className="mt-1 text-sm text-gray-500">
            {isManager
              ? 'Review leave requests, manage approvals, and view team leave schedules.'
              : 'View your leave balances, apply for leave, and track your leave history.'}
          </p>
        </div>
        <div className="flex flex-col items-end gap-2">
          <div className="flex flex-wrap justify-end gap-2">
            <span
              title={getModuleModeHint(dataSourceMode)}
              className="cursor-help rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-medium text-emerald-700"
            >
              {dataSourceMode}
            </span>
            <span
              title={getModuleModeHint(readMode)}
              className="cursor-help rounded-full bg-blue-50 px-2.5 py-1 text-xs font-medium text-blue-700"
            >
              {readMode}
            </span>
          </div>
          <div className="flex gap-2">
          {!isManager && (
            <Link to="/modules/eleave/native" className="btn-primary">
              <CalendarPlus className="h-4 w-4" /> Apply for Leave
            </Link>
          )}
          </div>
        </div>
      </div>

      {/* Manager View */}
      {isManager ? (
        <>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <StatCard label="Total This Year" value={managerStats.total} icon={CalendarDays} color="blue" />
            <StatCard label="Approved" value={managerStats.approved} icon={CalendarCheck} color="green" />
            <StatCard label="Pending" value={managerStats.pending} icon={CalendarClock} color="amber" />
            <StatCard label="Rejected" value={managerStats.rejected} icon={CalendarX} color="red" />
          </div>

          <div className="card">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-sm font-semibold text-gray-900">Pending Leave Requests ({pendingRequests.length})</h2>
              <div className="flex gap-2">
                <button onClick={() => showToast('Exporting leave data...')} className="btn-secondary py-1.5 text-xs">
                  <Download className="h-3.5 w-3.5" /> Export
                </button>
                <button onClick={() => showToast('Sending reminders...')} className="btn-secondary py-1.5 text-xs">
                  <Send className="h-3.5 w-3.5" /> Remind All
                </button>
              </div>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="border-b border-gray-200 bg-gray-50">
                  <tr>
                    <th className="px-4 py-3 font-medium text-gray-500">Employee</th>
                    <th className="px-4 py-3 font-medium text-gray-500">Type</th>
                    <th className="px-4 py-3 font-medium text-gray-500">Duration</th>
                    <th className="px-4 py-3 font-medium text-gray-500">Relief Officer</th>
                    <th className="px-4 py-3 font-medium text-gray-500">Applied</th>
                    <th className="px-4 py-3 font-medium text-gray-500">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {pendingRequests.map(req => (
                    <tr key={req.id} className="hover:bg-gray-50">
                      <td className="px-4 py-3">
                        <p className="font-medium text-gray-900">{String(req.name ?? 'Employee')}</p>
                        <p className="text-xs text-gray-500">{String(req.department ?? '')}</p>
                      </td>
                      <td className="px-4 py-3 text-gray-600">{String(req.type ?? '')}</td>
                      <td className="px-4 py-3">
                        <p className="text-gray-900">{String(req.days ?? 0)} day{Number(req.days ?? 0) > 1 ? 's' : ''}</p>
                        <p className="text-xs text-gray-500">{String(req.from ?? '')} to {String(req.to ?? '')}</p>
                      </td>
                      <td className="px-4 py-3 text-gray-600">{String(req.reliefOfficer ?? '')}</td>
                      <td className="px-4 py-3 text-xs text-gray-500">{String(req.appliedOn ?? '')}</td>
                      <td className="px-4 py-3">
                        <div className="flex gap-2">
                          <button onClick={() => handleManagerAction(String(req.id ?? ''), 'approved')} className="rounded-lg bg-emerald-50 px-3 py-1 text-xs font-medium text-emerald-700 hover:bg-emerald-100">
                            Approve
                          </button>
                          <button onClick={() => handleManagerAction(String(req.id ?? ''), 'rejected')} className="rounded-lg bg-red-50 px-3 py-1 text-xs font-medium text-red-700 hover:bg-red-100">
                            Reject
                          </button>
                          <button onClick={() => showToast(`Viewing ${String(req.name ?? 'employee')}'s details...`)} className="rounded-lg bg-gray-50 px-2 py-1 text-gray-500 hover:bg-gray-100">
                            <Eye className="h-3.5 w-3.5" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="card">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-semibold text-gray-900">Quick Reports</h2>
            </div>
            <div className="flex flex-wrap gap-3">
              <button onClick={() => showToast('Generating leave utilization report...')} className="btn-secondary text-sm">
                <BarChart3 className="h-4 w-4" /> Utilization Report
              </button>
              <button onClick={() => showToast('Generating leave calendar...')} className="btn-secondary text-sm">
                <CalendarDays className="h-4 w-4" /> Leave Calendar
              </button>
              <button onClick={() => showToast('Exporting all leave data...')} className="btn-secondary text-sm">
                <Download className="h-4 w-4" /> Export All Data
              </button>
            </div>
          </div>
        </>
      ) : (
        /* Employee View */
        <>
          {/* Leave Balance Breakdown */}
          <div className="card">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-sm font-semibold text-gray-900">Leave Balances</h2>
              <span className="text-xs text-gray-500">As of Feb 2026</span>
            </div>
            <div className="space-y-4">
              {leaveBalances.map((b, i) => {
                const total = Number(b.total ?? 0);
                const used = Number(b.used ?? 0);
                const pending = Number(b.pending ?? 0);
                const available = total - used - pending;
                const usedPercent = total > 0 ? (used / total) * 100 : 0;
                const pendingPercent = total > 0 ? (pending / total) * 100 : 0;
                return (
                  <div key={i}>
                    <div className="mb-1.5 flex items-center justify-between">
                      <p className="text-sm font-medium text-gray-900">{String(b.type ?? 'Leave')}</p>
                      <p className="text-sm text-gray-500">
                        <span className="font-semibold text-gray-900">{available}</span> / {total} days available
                      </p>
                    </div>
                    <div className="flex h-2.5 overflow-hidden rounded-full bg-gray-100">
                      <div className={clsx('transition-all', String(b.color ?? 'bg-gray-500'))} style={{ width: `${usedPercent}%` }} />
                      {pendingPercent > 0 && (
                        <div className="bg-amber-400" style={{ width: `${pendingPercent}%` }} />
                      )}
                    </div>
                    <div className="mt-1 flex gap-4 text-xs text-gray-500">
                      <span>Used: {used}</span>
                      {pending > 0 && <span className="text-amber-600">Pending: {pending}</span>}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          <div className="grid gap-6 lg:grid-cols-3">
            {/* Leave History */}
            <div className="lg:col-span-2">
              <div className="card overflow-hidden p-0">
                <div className="flex items-center justify-between border-b border-gray-100 px-6 py-4">
                  <h2 className="text-sm font-semibold text-gray-900">Leave History</h2>
                  <button onClick={() => showToast('Exporting leave history...')} className="flex items-center gap-1 text-xs font-medium text-brand-500 hover:text-brand-600">
                    <Download className="h-3.5 w-3.5" /> Export
                  </button>
                </div>
                <table className="w-full text-left text-sm">
                  <thead className="border-b border-gray-200 bg-gray-50">
                    <tr>
                      <th className="px-4 py-3 font-medium text-gray-500">Type</th>
                      <th className="px-4 py-3 font-medium text-gray-500">Days</th>
                      <th className="px-4 py-3 font-medium text-gray-500">Period</th>
                      <th className="px-4 py-3 font-medium text-gray-500">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {leaveHistory.map(l => (
                      <tr key={l.id} className="hover:bg-gray-50 cursor-pointer" onClick={() => showToast(`Viewing leave ${l.id} details...`)}>
                        <td className="px-4 py-3 font-medium text-gray-900">{String(l.type ?? '')}</td>
                        <td className="px-4 py-3 text-gray-600">{String(l.days ?? 0)}</td>
                        <td className="px-4 py-3 text-xs text-gray-500">{String(l.startDate ?? '')} to {String(l.endDate ?? '')}</td>
                        <td className="px-4 py-3">
                          <span className={clsx('rounded-full px-2 py-0.5 text-xs font-medium',
                            String(l.status) === 'approved' ? 'bg-emerald-50 text-emerald-700' :
                            String(l.status) === 'pending' ? 'bg-amber-50 text-amber-700' : 'bg-red-50 text-red-700'
                          )}>
                            {String(l.status ?? '')}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Upcoming Holidays */}
            <div className="card">
              <h2 className="mb-4 text-sm font-semibold text-gray-900">Upcoming Holidays</h2>
              <div className="space-y-3">
                {holidays.map((h, i) => (
                  <div key={i} className="flex items-center gap-3 rounded-lg border border-gray-100 p-3">
                    <div className="flex h-8 w-8 items-center justify-center rounded-full bg-green-50">
                      <CalendarCheck className="h-4 w-4 text-green-600" />
                    </div>
                    <div>
                      <p className="text-sm font-medium text-gray-900">{String(h.name ?? '')}</p>
                      <p className="text-xs text-gray-500">{String(h.date ?? '')}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
};
