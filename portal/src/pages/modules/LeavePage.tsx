import React, { useEffect, useState } from 'react';
import {
  CalendarDays, CalendarCheck, CalendarClock, CalendarX,
  CalendarPlus, CheckCircle, Download, Send, Filter, Eye, BarChart3,
} from 'lucide-react';
import { useAuth } from '../../auth/AuthProvider';
import { HRIS_ROLES, isManagerRole } from '../../auth/roles';
import { StatCard } from '../../components/StatCard';
import { LeaveApplicationModal } from '../../components/LeaveApplicationModal';
import { clsx } from 'clsx';
import { getLeaveModuleData, type LeaveModuleResponse } from '../../api/hrisCoreClient';
import { isApiDataMode } from '../../config/dataMode';

const LEAVE_BALANCES = [
  { type: 'Annual Leave', total: 23, used: 8, pending: 3, color: 'bg-blue-500' },
  { type: 'Sick Leave', total: 10, used: 0, pending: 0, color: 'bg-red-500' },
  { type: 'Casual Leave', total: 5, used: 2, pending: 0, color: 'bg-amber-500' },
  { type: 'Study Leave', total: 30, used: 0, pending: 0, color: 'bg-purple-500' },
  { type: 'Compassionate', total: 5, used: 0, pending: 0, color: 'bg-green-500' },
];

const MY_LEAVE_HISTORY = [
  { id: 'L001', type: 'Annual Leave', days: 5, startDate: '2025-12-20', endDate: '2025-12-24', status: 'approved', appliedOn: '2025-12-01', approvedBy: 'Dr. Ama Mensah' },
  { id: 'L002', type: 'Sick Leave', days: 2, startDate: '2025-11-10', endDate: '2025-11-11', status: 'approved', appliedOn: '2025-11-10', approvedBy: 'Dr. Ama Mensah' },
  { id: 'L003', type: 'Annual Leave', days: 3, startDate: '2026-02-25', endDate: '2026-02-27', status: 'pending', appliedOn: '2026-02-10', approvedBy: null },
  { id: 'L004', type: 'Casual Leave', days: 1, startDate: '2025-08-15', endDate: '2025-08-15', status: 'approved', appliedOn: '2025-08-10', approvedBy: 'Dr. Ama Mensah' },
  { id: 'L005', type: 'Casual Leave', days: 1, startDate: '2025-06-02', endDate: '2025-06-02', status: 'rejected', appliedOn: '2025-05-28', approvedBy: 'Dr. Ama Mensah' },
];

const PENDING_REQUESTS_MANAGER = [
  { id: 'P001', name: 'Kwame Asante', type: 'Annual Leave', days: 3, from: '2026-02-25', to: '2026-02-27', appliedOn: '2026-02-10', department: 'IT', reliefOfficer: 'Kofi Osei' },
  { id: 'P002', name: 'Efua Owusu', type: 'Sick Leave', days: 2, from: '2026-02-18', to: '2026-02-19', appliedOn: '2026-02-18', department: 'Legal', reliefOfficer: 'Nana Appiah' },
  { id: 'P003', name: 'Akua Darko', type: 'Annual Leave', days: 5, from: '2026-03-10', to: '2026-03-14', appliedOn: '2026-02-08', department: 'Finance', reliefOfficer: 'Yaw Adjei' },
  { id: 'P004', name: 'Nana Appiah', type: 'Study Leave', days: 10, from: '2026-04-01', to: '2026-04-10', appliedOn: '2026-02-05', department: 'HR', reliefOfficer: 'Ama Mensah' },
];

const HOLIDAYS = [
  { name: 'Independence Day', date: 'Mar 6, 2026' },
  { name: 'Good Friday', date: 'Apr 3, 2026' },
  { name: 'Easter Monday', date: 'Apr 6, 2026' },
  { name: 'May Day', date: 'May 1, 2026' },
  { name: 'Eid al-Fitr', date: 'Mar 30, 2026' },
];

export const LeavePage: React.FC = () => {
  const { user } = useAuth();
  const role = user?.effectiveRole ?? HRIS_ROLES.EMPLOYEE;
  const isManager = isManagerRole(role);
  const [leaveModalOpen, setLeaveModalOpen] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [managerActions, setManagerActions] = useState<Record<string, string>>({});
  const [apiData, setApiData] = useState<LeaveModuleResponse | null>(null);
  const [loading, setLoading] = useState(isApiDataMode);
  const [error, setError] = useState<string | null>(null);

  const showToast = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 3000);
  };

  const handleManagerAction = (id: string, action: 'approved' | 'rejected') => {
    setManagerActions(prev => ({ ...prev, [id]: action }));
    showToast(`Leave request ${action}`);
  };

  useEffect(() => {
    if (!isApiDataMode) return;
    let mounted = true;
    setLoading(true);
    setError(null);
    getLeaveModuleData()
      .then((d) => { if (mounted) setApiData(d); })
      .catch(() => { if (mounted) setError('Failed to load leave module data in API mode.'); })
      .finally(() => { if (mounted) setLoading(false); });
    return () => { mounted = false; };
  }, []);

  const managerStats = isApiDataMode && apiData
    ? {
      total: Number(apiData.manager.stats.total_this_year ?? 0),
      approved: Number(apiData.manager.stats.approved ?? 0),
      pending: Number(apiData.manager.stats.pending ?? 0),
      rejected: Number(apiData.manager.stats.rejected ?? 0),
    }
    : { total: 320, approved: 280, pending: 25, rejected: 10 };
  const pendingRequests = isApiDataMode ? (apiData?.manager.pending_requests ?? []) : PENDING_REQUESTS_MANAGER;
  const leaveBalances = isApiDataMode ? (apiData?.employee.balances ?? []) : LEAVE_BALANCES;
  const leaveHistory = isApiDataMode ? (apiData?.employee.history ?? []) : MY_LEAVE_HISTORY;
  const holidays = isApiDataMode ? (apiData?.employee.holidays ?? []) : HOLIDAYS;

  if (isApiDataMode && loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="h-10 w-10 animate-spin rounded-full border-4 border-gray-300 border-t-brand-500" />
      </div>
    );
  }

  if (isApiDataMode && (error || !apiData)) {
    return (
      <div className="rounded-xl border border-red-200 bg-red-50 p-6">
        <p className="text-sm text-red-700">{error ?? 'No leave data available in API mode.'}</p>
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

      <LeaveApplicationModal open={leaveModalOpen} onClose={() => setLeaveModalOpen(false)} onSuccess={() => showToast('Leave application submitted!')} />

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
            <span className="rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-medium text-emerald-700">native</span>
            <span className="rounded-full bg-blue-50 px-2.5 py-1 text-xs font-medium text-blue-700">native-readonly</span>
          </div>
          <div className="flex gap-2">
          {!isManager && (
            <button onClick={() => setLeaveModalOpen(true)} className="btn-primary">
              <CalendarPlus className="h-4 w-4" /> Apply for Leave
            </button>
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
                        {managerActions[req.id] ? (
                          <span className={clsx('rounded-full px-2.5 py-0.5 text-xs font-medium',
                            managerActions[req.id] === 'approved' ? 'bg-emerald-50 text-emerald-700' : 'bg-red-50 text-red-700'
                          )}>
                            {managerActions[req.id]}
                          </span>
                        ) : (
                          <div className="flex gap-2">
                            <button onClick={() => handleManagerAction(req.id, 'approved')} className="rounded-lg bg-emerald-50 px-3 py-1 text-xs font-medium text-emerald-700 hover:bg-emerald-100">
                              Approve
                            </button>
                            <button onClick={() => handleManagerAction(req.id, 'rejected')} className="rounded-lg bg-red-50 px-3 py-1 text-xs font-medium text-red-700 hover:bg-red-100">
                              Reject
                            </button>
                            <button onClick={() => showToast(`Viewing ${String(req.name ?? 'employee')}'s details...`)} className="rounded-lg bg-gray-50 px-2 py-1 text-gray-500 hover:bg-gray-100">
                              <Eye className="h-3.5 w-3.5" />
                            </button>
                          </div>
                        )}
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
