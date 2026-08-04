import React, { useEffect, useState } from 'react';
import {
  ClipboardList, CheckCircle, AlertTriangle, Clock, Target,
  TrendingUp, Star, ChevronRight, MessageSquare, Send, BarChart3, Eye, ExternalLink,
} from 'lucide-react';
import { useAuth } from '../../auth/AuthProvider';
import { hasMinimumRole, HRIS_ROLES, isManagerRole } from '../../auth/roles';
import { StatCard } from '../../components/StatCard';
import { ModuleNativeLaunchBanner } from '../../components/ModuleNativeLaunchBanner';
import { clsx } from 'clsx';
import {
  getAppraisalHistoryDetail,
  getAppraisalCapabilities,
  getAppraisalModuleData,
  getAppraisalTasks,
  getEappraisalDiagnostics,
  executeAppraisalAction,
  getModulesCatalog,
  type AppraisalModuleResponse,
  type ModuleCapabilitiesResponse,
  type ModuleTasksResponse,
  runJitModuleSetup,
} from '../../api/hrisCoreClient';
import { getModuleModeHint } from '../../shared/moduleMode';

export const AppraisalPage: React.FC = () => {
  const { user } = useAuth();
  const role = user?.effectiveRole ?? HRIS_ROLES.EMPLOYEE;
  const isManager = isManagerRole(role);
  const [feedback, setFeedback] = useState('');
  const [toast, setToast] = useState<string | null>(null);
  const [apiData, setApiData] = useState<AppraisalModuleResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [jitSetupRunning, setJitSetupRunning] = useState(false);
  const [selectedHistory, setSelectedHistory] = useState<AppraisalModuleResponse['employee']['past_appraisals'][number] | null>(null);
  const [historyDetail, setHistoryDetail] = useState<Record<string, unknown> | null>(null);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [dataSourceMode, setDataSourceMode] = useState<'native' | 'unavailable'>('native');
  const [readMode, setReadMode] = useState('native-readonly');
  const [capabilities, setCapabilities] = useState<ModuleCapabilitiesResponse | null>(null);
  const [tasks, setTasks] = useState<ModuleTasksResponse | null>(null);

  const showToast = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 3000);
  };

  useEffect(() => {
    let mounted = true;
    setLoading(true);
    setError(null);
    setJitSetupRunning(false);
    getAppraisalModuleData()
      .then((d) => { if (mounted) setApiData(d); })
      .catch(async (err: unknown) => {
        if (!mounted) return;
        let message = 'Failed to load appraisal module data in API mode.';
        const maybeAxios = err as { response?: { status?: number; data?: { detail?: string | { code?: string; message?: string; action?: string } } } };
        const statusCode = maybeAxios?.response?.status;
        const detailRaw = maybeAxios?.response?.data?.detail;
        const detail = typeof detailRaw === 'string' ? detailRaw.trim() : String(detailRaw?.message || '').trim();
        const detailCode = typeof detailRaw === 'object' ? String(detailRaw?.code || '').trim() : '';
        const detailAction = typeof detailRaw === 'object' ? String(detailRaw?.action || '').trim() : '';
        if (statusCode === 403 && detail.toLowerCase().includes("module 'eappraisal' is not active")) {
          // JIT enable + provision path (if enabled server-side). If it fails, we still show a clear message.
          try {
            setJitSetupRunning(true);
            await runJitModuleSetup('eappraisal');
            const d2 = await getAppraisalModuleData();
            if (mounted) {
              setApiData(d2);
              setError(null);
            }
            return;
          } catch {
            message = 'Performance Appraisal is not active for your tenant (and setup could not be completed). Contact admin or try again later.';
          } finally {
            if (mounted) setJitSetupRunning(false);
          }
        } else if (statusCode === 403 && detail) {
          message = `Appraisal access denied: ${detail}`;
        } else if (statusCode === 409 && detailCode) {
          message = `Appraisal setup blocked (${detailCode}): ${detail || 'module not ready'}`;
          if (detailAction) {
            message = `${message}. Action: ${detailAction}`;
          }
        }
        try {
          const catalog = await getModulesCatalog();
          const moduleRow = (catalog.modules || []).find((m) => String(m.id || '').toLowerCase() === 'eappraisal');
          if (moduleRow && !moduleRow.enabled) {
            message = 'Performance Appraisal is disabled for your current tenant in module catalog.';
          }
          const isSuperAdmin = String(user?.effectiveRole || '').toLowerCase() === 'hris:super_admin';
          if (isSuperAdmin) {
            const diagnostics = await getEappraisalDiagnostics();
            const probes = diagnostics.probes || {};
            const summaryProbe = probes.appraisal_summary;
            if (summaryProbe && summaryProbe.ok === false) {
              const detail = String(summaryProbe.detail || '');
              if (detail.toLowerCase().includes('authentication')) {
                message = 'Appraisal integration is reachable but authentication expired. Re-login to eAppraisal or refresh integration tokens.';
              } else {
                message = `Appraisal integration degraded: ${detail || 'upstream unavailable'}`;
              }
            }
          }
        } catch {
          // Keep generic message if diagnostics endpoint is disabled.
        }
        setError(message);
      })
      .finally(() => { if (mounted) setLoading(false); });
    getAppraisalCapabilities().then((r) => { if (mounted) setCapabilities(r); }).catch(() => undefined);
    getAppraisalTasks().then((r) => { if (mounted) setTasks(r); }).catch(() => undefined);
    getModulesCatalog()
      .then((catalog) => {
        if (!mounted) return;
        const moduleRow = (catalog.modules || []).find((m) => String(m.id || '').toLowerCase() === 'eappraisal');
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
      activeCycles: Number(apiData.manager.stats.active_cycles ?? 0),
      completed: Number(apiData.manager.stats.completed ?? 0),
      pending: Number(apiData.manager.stats.pending ?? 0),
      overdue: Number(apiData.manager.stats.overdue ?? 0),
    }
    : { activeCycles: 1, completed: 88, pending: 12, overdue: 3 };

  const teamStats = apiData?.manager.team_stats ?? [];
  const recentActivity = apiData?.manager.recent_activity ?? [];
  const sections = apiData?.employee.sections ?? [];
  const goals = apiData?.employee.goals ?? [];
  const pastAppraisals = apiData?.employee.past_appraisals ?? [];
  const cycleInfo = apiData?.employee.current_cycle ?? { title: 'Current Appraisal Cycle', due_date: '', overall_progress: 0 };
  const trendMessage = apiData?.employee.trend_message ?? '';

  const completedSectionsDynamic = sections.filter((s) => String(s.status) === 'completed').length;
  const allowedActions = new Set((capabilities?.actions || []).map((a) => String(a).toLowerCase()));
  const canDo = (action: string) => allowedActions.has(String(action).toLowerCase());
  const runAction = async (actionId: string, fallbackMessage: string) => {
    try {
      const out = await executeAppraisalAction(actionId, { source: 'portal' });
      if (String(out?.status || '') === 'native_action_required') {
        showToast('Open the module workspace to complete this appraisal action.');
        return;
      }
      showToast(fallbackMessage);
    } catch {
      showToast('Action blocked by policy or module authorization.');
    }
  };
  const overallProgressDynamic = sections.length > 0
    ? Math.round((completedSectionsDynamic / sections.length) * 100)
    : Number(cycleInfo.overall_progress ?? 0);

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
        <p className="text-sm text-red-700">{error ?? 'No appraisal data available in API mode.'}</p>
        {jitSetupRunning && (
          <p className="mt-2 text-xs text-red-700">
            Setting up Appraisal for your organization…
          </p>
        )}
        {String(user?.effectiveRole || '').toLowerCase() === 'hris:super_admin' && (
          <p className="mt-2 text-xs text-red-600">
            Check `GET /debug/integrations/eappraisal` (superadmin only) for upstream diagnostics.
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

      <ModuleNativeLaunchBanner moduleId="eappraisal" />

      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">
            {isManager ? 'Performance Appraisal' : 'My Appraisals'}
          </h1>
          <p className="mt-1 text-sm text-gray-500">
            {isManager
              ? 'Manage appraisal cycles, review submissions, and track team performance.'
              : 'Complete your self-assessment, track goals, and view your performance history.'}
          </p>
        </div>
        <div className="flex flex-col items-end gap-2">
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
      </div>

      {/* Manager View */}
      {isManager ? (
        <>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <StatCard label="Active Cycles" value={managerStats.activeCycles} icon={ClipboardList} color="purple" />
            <StatCard label="Completed" value={managerStats.completed} icon={CheckCircle} color="green" />
            <StatCard label="Pending" value={managerStats.pending} icon={Clock} color="amber" />
            <StatCard label="Overdue" value={managerStats.overdue} icon={AlertTriangle} color="red" />
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            <div className="card">
              <h2 className="mb-4 text-sm font-semibold text-gray-900">Team Progress</h2>
              <div className="space-y-3">
                {teamStats.map((member, i) => (
                  <div key={i} className="flex items-center justify-between rounded-lg border border-gray-100 p-3">
                    <div className="flex items-center gap-3">
                      <div className="flex h-8 w-8 items-center justify-center rounded-full bg-purple-100 text-xs font-bold text-purple-600">
                        {String(member.name ?? '').split(' ').map(n => n[0]).join('')}
                      </div>
                      <div>
                        <p className="text-sm font-medium text-gray-900">{String(member.name ?? 'Team Member')}</p>
                        <p className="text-xs text-gray-500">{String(member.completed ?? 0)}/5 sections completed</p>
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      {member.score ? (
                        <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-xs font-medium text-emerald-700">{String(member.score)}/5.0</span>
                      ) : (
                        <span className="rounded-full bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-700">In Progress</span>
                      )}
                      <button onClick={() => showToast(`Opening review for ${String(member.name ?? 'staff')}`)} className="text-brand-500 hover:text-brand-600">
                        <ChevronRight className="h-4 w-4" />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="card">
              <h2 className="mb-4 text-sm font-semibold text-gray-900">Recent Activity</h2>
              <div className="space-y-3">
                {recentActivity.map((item, i) => (
                  <div key={i} className="flex items-center justify-between rounded-lg border border-gray-100 p-3">
                    <div>
                      <p className="text-sm font-medium text-gray-900">{String(item.name ?? 'Staff')}</p>
                      <p className="text-xs text-gray-500">{String(item.action ?? '')} &middot; {String(item.time ?? '')}</p>
                    </div>
                    <span className={clsx('inline-flex rounded-full px-2 py-0.5 text-xs font-medium',
                      String(item.status) === 'completed' ? 'bg-emerald-50 text-emerald-700' :
                      String(item.status) === 'pending' ? 'bg-amber-50 text-amber-700' :
                      String(item.status) === 'in_progress' ? 'bg-blue-50 text-blue-700' : 'bg-purple-50 text-purple-700'
                    )}>
                      {String(item.status ?? '').replace('_', ' ')}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="card">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-semibold text-gray-900">Batch Actions</h2>
            </div>
            <div className="flex flex-wrap gap-3">
              <button
                onClick={() => runAction('assign_reviewer', 'Sending reminders to pending staff...')}
                className="btn-secondary text-sm"
                disabled={!canDo('assign_reviewer')}
              >
                <Send className="h-4 w-4" /> Send Reminders
              </button>
              <button
                onClick={() => runAction('view_reports', 'Generating appraisal report...')}
                className="btn-secondary text-sm"
                disabled={!canDo('view_reports')}
              >
                <BarChart3 className="h-4 w-4" /> Generate Report
              </button>
              <button
                onClick={() => runAction('create_cycle', 'Starting appraisal cycle setup...')}
                className="btn-secondary text-sm"
                disabled={!canDo('create_cycle')}
              >
                <ExternalLink className="h-4 w-4" /> Export Data
              </button>
            </div>
          </div>
        </>
      ) : (
        /* Employee View */
        <>
          {/* Current Cycle Overview */}
          <div className="card overflow-hidden p-0">
            <div className="bg-gradient-to-r from-purple-600 to-purple-700 px-6 py-5 text-white">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-lg font-semibold">{String(cycleInfo.title ?? 'Current Appraisal Cycle')}</h2>
                  <p className="mt-0.5 text-sm text-purple-200">Self-assessment due by {String(cycleInfo.due_date ?? 'N/A')}</p>
                </div>
                <div className="text-right">
                  <p className="text-3xl font-bold">{overallProgressDynamic}%</p>
                  <p className="text-xs text-purple-200">Overall Progress</p>
                </div>
              </div>
              <div className="mt-4 h-2 rounded-full bg-white/20">
                <div className="h-full rounded-full bg-white transition-all" style={{ width: `${overallProgressDynamic}%` }} />
              </div>
            </div>

            {/* Sections */}
            <div className="divide-y divide-gray-100">
              {sections.map((section, i) => (
                <div key={i} className="flex items-center justify-between px-6 py-4 hover:bg-gray-50">
                  <div className="flex items-center gap-3">
                    <div className={clsx('flex h-8 w-8 items-center justify-center rounded-full',
                      String(section.status) === 'completed' ? 'bg-emerald-100 text-emerald-600' :
                      String(section.status) === 'in_progress' ? 'bg-blue-100 text-blue-600' :
                      String(section.status) === 'locked' ? 'bg-gray-100 text-gray-400' : 'bg-gray-100 text-gray-500'
                    )}>
                      {String(section.status) === 'completed' ? <CheckCircle className="h-4 w-4" /> :
                       String(section.status) === 'in_progress' ? <Clock className="h-4 w-4" /> :
                       <span className="text-xs font-medium">{i + 1}</span>}
                    </div>
                    <div>
                      <p className="text-sm font-medium text-gray-900">{String(section.name ?? 'Section')}</p>
                      <p className="text-xs text-gray-500">Weight: {String(section.weight ?? 0)}%{section.score ? ` \u00b7 Score: ${String(section.score)}/${String(section.maxScore ?? 5)}` : ''}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className={clsx('rounded-full px-2.5 py-0.5 text-xs font-medium',
                      String(section.status) === 'completed' ? 'bg-emerald-50 text-emerald-700' :
                      String(section.status) === 'in_progress' ? 'bg-blue-50 text-blue-700' :
                      String(section.status) === 'locked' ? 'bg-gray-100 text-gray-400' : 'bg-gray-50 text-gray-500'
                    )}>
                      {String(section.status) === 'in_progress' ? 'In Progress' :
                       String(section.status) === 'not_started' ? 'Not Started' :
                       String(section.status) === 'locked' ? 'Locked' : 'Completed'}
                    </span>
                    {(String(section.status) === 'in_progress' || String(section.status) === 'not_started') && (
                      <button onClick={() => showToast(`Opening "${String(section.name ?? 'section')}" for editing...`)} className="text-brand-500 hover:text-brand-600">
                        <ChevronRight className="h-4 w-4" />
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Goals & Objectives */}
          <div className="card">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-sm font-semibold text-gray-900">Goals & Objectives</h2>
              <button
                onClick={() => runAction('update_goal', 'Opening goal form...')}
                className="text-xs font-medium text-brand-500 hover:text-brand-600"
                disabled={!canDo('update_goal')}
              >
                + Add Goal
              </button>
            </div>
            <div className="space-y-3">
              {goals.map((goal, i) => (
                <div key={i} className="rounded-lg border border-gray-100 p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex items-start gap-3">
                      <Target className={clsx('mt-0.5 h-4 w-4', Number(goal.progress) === 100 ? 'text-emerald-500' : 'text-gray-400')} />
                      <div>
                        <p className={clsx('text-sm font-medium', Number(goal.progress) === 100 ? 'text-gray-500 line-through' : 'text-gray-900')}>{String(goal.title ?? 'Goal')}</p>
                        <div className="mt-1 flex gap-2">
                          <span className="text-xs text-gray-400">Due: {String(goal.dueDate ?? 'N/A')}</span>
                          <span className={clsx('rounded px-1.5 py-0.5 text-xs font-medium',
                            String(goal.priority) === 'High' ? 'bg-red-50 text-red-600' : 'bg-amber-50 text-amber-600'
                          )}>{String(goal.priority ?? 'Medium')}</span>
                        </div>
                      </div>
                    </div>
                    <span className="text-sm font-semibold text-gray-900">{String(goal.progress ?? 0)}%</span>
                  </div>
                  <div className="mt-3 h-1.5 rounded-full bg-gray-100">
                    <div className={clsx('h-full rounded-full transition-all',
                      Number(goal.progress) === 100 ? 'bg-emerald-500' : Number(goal.progress) >= 60 ? 'bg-blue-500' : 'bg-amber-500'
                    )} style={{ width: `${Number(goal.progress ?? 0)}%` }} />
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            <div className="card">
              <h2 className="mb-4 text-sm font-semibold text-gray-900">My Workflow Tasks</h2>
              <div className="space-y-2">
                {(tasks?.tasks || []).slice(0, 6).map((task) => (
                  <div key={task.task_id} className="rounded-lg border border-gray-100 p-3">
                    <p className="text-sm font-medium text-gray-900">{task.title}</p>
                    <p className="text-xs text-gray-500">{task.status}</p>
                  </div>
                ))}
                {!(tasks?.tasks || []).length && (
                  <p className="text-xs text-gray-500">No pending appraisal tasks right now.</p>
                )}
              </div>
            </div>
            {/* Feedback */}
            <div className="card">
              <h2 className="mb-4 text-sm font-semibold text-gray-900">Add General Comment</h2>
              <textarea
                value={feedback}
                onChange={e => setFeedback(e.target.value)}
                rows={4}
                className="input-field"
                placeholder="Share your thoughts on this appraisal cycle, achievements, or areas for development..."
              />
              <button
                onClick={() => { runAction('add_comment', 'Comment saved'); setFeedback(''); }}
                className="btn-primary mt-3 text-sm"
                disabled={!feedback.trim() || !canDo('add_comment')}
              >
                <MessageSquare className="h-4 w-4" /> Save Comment
              </button>
            </div>

            {/* Past Appraisals */}
            <div className="card">
              <h2 className="mb-4 text-sm font-semibold text-gray-900">Past Appraisals</h2>
              <div className="space-y-3">
                {pastAppraisals.map((a, i) => (
                  <button
                    type="button"
                    key={i}
                    onClick={async () => {
                      setSelectedHistory(a);
                      const entryId = String(a.submission_id || a.appraisal_id || '');
                      if (!entryId) {
                        setHistoryDetail(null);
                        return;
                      }
                      setHistoryLoading(true);
                      try {
                        const detail = await getAppraisalHistoryDetail(entryId);
                        setHistoryDetail(detail);
                      } catch {
                        setHistoryDetail(null);
                      } finally {
                        setHistoryLoading(false);
                      }
                    }}
                    className="flex w-full items-center justify-between rounded-lg border border-gray-100 p-3 text-left transition hover:bg-gray-50"
                  >
                    <div className="flex items-center gap-3">
                      <div className="flex h-8 w-8 items-center justify-center rounded-full bg-purple-50">
                        <Star className="h-4 w-4 text-purple-600" />
                      </div>
                      <div>
                        <p className="text-sm font-medium text-gray-900">{String(a.cycle ?? 'Cycle')}</p>
                        <p className="text-xs text-gray-500">{String(a.date ?? '')}</p>
                      </div>
                    </div>
                    <div className="text-right">
                      <p className="text-sm font-semibold text-gray-900">{String(a.score ?? 'N/A')}/5.0</p>
                      <p className="text-xs text-emerald-600">{String(a.rating ?? '')}</p>
                      <p className="mt-1 inline-flex items-center gap-1 text-xs font-medium text-brand-600">
                        <Eye className="h-3 w-3" /> View
                      </p>
                    </div>
                  </button>
                ))}
              </div>
              {selectedHistory && (
                <div className="mt-3 rounded-lg border border-purple-200 bg-purple-50 p-3">
                  <p className="text-xs font-semibold uppercase tracking-wide text-purple-700">Selected Appraisal</p>
                  <p className="mt-1 text-sm font-medium text-purple-900">{String(selectedHistory.cycle ?? 'Cycle')}</p>
                  {historyLoading ? (
                    <p className="mt-1 text-xs text-purple-700">Loading details...</p>
                  ) : historyDetail ? (
                    <p className="mt-1 text-xs text-purple-700">
                      Status: {String(historyDetail.status ?? selectedHistory.status ?? 'unknown')} | Submitted:{' '}
                      {String(historyDetail.submitted ?? 'N/A')} | Reviewed: {String(historyDetail.reviewed ?? 'N/A')}
                    </p>
                  ) : (
                    <p className="mt-1 text-xs text-purple-700">Read-only detail is not available for this item yet.</p>
                  )}
                </div>
              )}
              <div className="mt-3 flex items-center gap-2 rounded-lg bg-purple-50 p-3">
                <TrendingUp className="h-4 w-4 text-purple-600" />
                <p className="text-xs text-purple-700">{trendMessage || 'Performance trend is unavailable in API mode.'}</p>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
};
