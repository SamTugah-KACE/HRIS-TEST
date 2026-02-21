import React, { useState } from 'react';
import {
  ClipboardList, ExternalLink, CheckCircle, AlertTriangle, Clock, Target,
  TrendingUp, Star, ChevronRight, MessageSquare, Send, BarChart3,
} from 'lucide-react';
import { useAuth } from '../../auth/AuthProvider';
import { hasMinimumRole, HRIS_ROLES, isManagerRole } from '../../auth/roles';
import { StatCard } from '../../components/StatCard';
import { clsx } from 'clsx';

const APPRAISAL_SECTIONS = [
  { name: 'Key Result Areas (KRA)', weight: 40, status: 'completed', score: 4.1, maxScore: 5 },
  { name: 'Core Competencies', weight: 25, status: 'completed', score: 3.8, maxScore: 5 },
  { name: 'Leadership & Initiative', weight: 15, status: 'in_progress', score: null, maxScore: 5 },
  { name: 'Learning & Development', weight: 10, status: 'not_started', score: null, maxScore: 5 },
  { name: 'Supervisor Assessment', weight: 10, status: 'locked', score: null, maxScore: 5 },
];

const GOALS = [
  { title: 'Complete AWS migration for 3 services', progress: 80, dueDate: 'Mar 2026', priority: 'High' },
  { title: 'Mentor 2 junior developers', progress: 60, dueDate: 'Jun 2026', priority: 'Medium' },
  { title: 'Achieve PMP certification', progress: 100, dueDate: 'Jan 2026', priority: 'High' },
  { title: 'Reduce API response time by 30%', progress: 45, dueDate: 'Apr 2026', priority: 'Medium' },
];

const PAST_APPRAISALS = [
  { cycle: '2024/2025', score: 4.2, rating: 'Excellent', status: 'completed', date: '2025-06-15' },
  { cycle: '2023/2024', score: 3.8, rating: 'Very Good', status: 'completed', date: '2024-06-20' },
  { cycle: '2022/2023', score: 3.5, rating: 'Good', status: 'completed', date: '2023-07-01' },
];

const RECENT_ACTIVITY_MANAGER = [
  { name: 'Ama Mensah', action: 'Submitted self-assessment', time: '2 hours ago', status: 'pending' },
  { name: 'Kofi Osei', action: 'Appraisal completed', time: '1 day ago', status: 'completed' },
  { name: 'Abena Boateng', action: 'Changes requested', time: '2 days ago', status: 'changes_requested' },
  { name: 'Yaw Adjei', action: 'Awaiting supervisor review', time: '3 days ago', status: 'pending' },
  { name: 'Nana Appiah', action: 'Self-assessment in progress', time: '4 days ago', status: 'in_progress' },
];

const TEAM_STATS = [
  { name: 'Kwame Asante', score: 4.1, completed: 2, pending: 3 },
  { name: 'Ama Mensah', score: null, completed: 5, pending: 0 },
  { name: 'Kofi Osei', score: 3.9, completed: 5, pending: 0 },
  { name: 'Abena Boateng', score: null, completed: 3, pending: 2 },
];

export const AppraisalPage: React.FC = () => {
  const { user } = useAuth();
  const role = user?.effectiveRole ?? HRIS_ROLES.EMPLOYEE;
  const isManager = isManagerRole(role);
  const [feedback, setFeedback] = useState('');
  const [toast, setToast] = useState<string | null>(null);

  const showToast = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 3000);
  };

  const completedSections = APPRAISAL_SECTIONS.filter(s => s.status === 'completed').length;
  const overallProgress = Math.round((completedSections / APPRAISAL_SECTIONS.length) * 100);

  return (
    <div className="space-y-6">
      {toast && (
        <div className="fixed right-4 top-20 z-50 flex items-center gap-2 rounded-lg bg-emerald-600 px-4 py-3 text-sm font-medium text-white shadow-lg">
          <CheckCircle className="h-4 w-4" /> {toast}
        </div>
      )}

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
        <a href="#" target="_blank" rel="noopener noreferrer" className="btn-primary">
          <ExternalLink className="h-4 w-4" /> Open eAppraisal
        </a>
      </div>

      {/* Manager View */}
      {isManager ? (
        <>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <StatCard label="Active Cycles" value={1} icon={ClipboardList} color="purple" />
            <StatCard label="Completed" value={88} icon={CheckCircle} color="green" />
            <StatCard label="Pending" value={12} icon={Clock} color="amber" />
            <StatCard label="Overdue" value={3} icon={AlertTriangle} color="red" />
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            <div className="card">
              <h2 className="mb-4 text-sm font-semibold text-gray-900">Team Progress</h2>
              <div className="space-y-3">
                {TEAM_STATS.map((member, i) => (
                  <div key={i} className="flex items-center justify-between rounded-lg border border-gray-100 p-3">
                    <div className="flex items-center gap-3">
                      <div className="flex h-8 w-8 items-center justify-center rounded-full bg-purple-100 text-xs font-bold text-purple-600">
                        {member.name.split(' ').map(n => n[0]).join('')}
                      </div>
                      <div>
                        <p className="text-sm font-medium text-gray-900">{member.name}</p>
                        <p className="text-xs text-gray-500">{member.completed}/5 sections completed</p>
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      {member.score ? (
                        <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-xs font-medium text-emerald-700">{member.score}/5.0</span>
                      ) : (
                        <span className="rounded-full bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-700">In Progress</span>
                      )}
                      <button onClick={() => showToast(`Opening review for ${member.name}`)} className="text-brand-500 hover:text-brand-600">
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
                {RECENT_ACTIVITY_MANAGER.map((item, i) => (
                  <div key={i} className="flex items-center justify-between rounded-lg border border-gray-100 p-3">
                    <div>
                      <p className="text-sm font-medium text-gray-900">{item.name}</p>
                      <p className="text-xs text-gray-500">{item.action} &middot; {item.time}</p>
                    </div>
                    <span className={clsx('inline-flex rounded-full px-2 py-0.5 text-xs font-medium',
                      item.status === 'completed' ? 'bg-emerald-50 text-emerald-700' :
                      item.status === 'pending' ? 'bg-amber-50 text-amber-700' :
                      item.status === 'in_progress' ? 'bg-blue-50 text-blue-700' : 'bg-purple-50 text-purple-700'
                    )}>
                      {item.status.replace('_', ' ')}
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
              <button onClick={() => showToast('Sending reminders to 12 pending staff...')} className="btn-secondary text-sm">
                <Send className="h-4 w-4" /> Send Reminders
              </button>
              <button onClick={() => showToast('Generating appraisal report...')} className="btn-secondary text-sm">
                <BarChart3 className="h-4 w-4" /> Generate Report
              </button>
              <button onClick={() => showToast('Exporting appraisal data...')} className="btn-secondary text-sm">
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
                  <h2 className="text-lg font-semibold">2025/2026 Appraisal Cycle</h2>
                  <p className="mt-0.5 text-sm text-purple-200">Self-assessment due by March 30, 2026</p>
                </div>
                <div className="text-right">
                  <p className="text-3xl font-bold">{overallProgress}%</p>
                  <p className="text-xs text-purple-200">Overall Progress</p>
                </div>
              </div>
              <div className="mt-4 h-2 rounded-full bg-white/20">
                <div className="h-full rounded-full bg-white transition-all" style={{ width: `${overallProgress}%` }} />
              </div>
            </div>

            {/* Sections */}
            <div className="divide-y divide-gray-100">
              {APPRAISAL_SECTIONS.map((section, i) => (
                <div key={i} className="flex items-center justify-between px-6 py-4 hover:bg-gray-50">
                  <div className="flex items-center gap-3">
                    <div className={clsx('flex h-8 w-8 items-center justify-center rounded-full',
                      section.status === 'completed' ? 'bg-emerald-100 text-emerald-600' :
                      section.status === 'in_progress' ? 'bg-blue-100 text-blue-600' :
                      section.status === 'locked' ? 'bg-gray-100 text-gray-400' : 'bg-gray-100 text-gray-500'
                    )}>
                      {section.status === 'completed' ? <CheckCircle className="h-4 w-4" /> :
                       section.status === 'in_progress' ? <Clock className="h-4 w-4" /> :
                       <span className="text-xs font-medium">{i + 1}</span>}
                    </div>
                    <div>
                      <p className="text-sm font-medium text-gray-900">{section.name}</p>
                      <p className="text-xs text-gray-500">Weight: {section.weight}%{section.score ? ` \u00b7 Score: ${section.score}/${section.maxScore}` : ''}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className={clsx('rounded-full px-2.5 py-0.5 text-xs font-medium',
                      section.status === 'completed' ? 'bg-emerald-50 text-emerald-700' :
                      section.status === 'in_progress' ? 'bg-blue-50 text-blue-700' :
                      section.status === 'locked' ? 'bg-gray-100 text-gray-400' : 'bg-gray-50 text-gray-500'
                    )}>
                      {section.status === 'in_progress' ? 'In Progress' :
                       section.status === 'not_started' ? 'Not Started' :
                       section.status === 'locked' ? 'Locked' : 'Completed'}
                    </span>
                    {(section.status === 'in_progress' || section.status === 'not_started') && (
                      <button onClick={() => showToast(`Opening "${section.name}" for editing...`)} className="text-brand-500 hover:text-brand-600">
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
              <button onClick={() => showToast('Add goal form would open here')} className="text-xs font-medium text-brand-500 hover:text-brand-600">+ Add Goal</button>
            </div>
            <div className="space-y-3">
              {GOALS.map((goal, i) => (
                <div key={i} className="rounded-lg border border-gray-100 p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex items-start gap-3">
                      <Target className={clsx('mt-0.5 h-4 w-4', goal.progress === 100 ? 'text-emerald-500' : 'text-gray-400')} />
                      <div>
                        <p className={clsx('text-sm font-medium', goal.progress === 100 ? 'text-gray-500 line-through' : 'text-gray-900')}>{goal.title}</p>
                        <div className="mt-1 flex gap-2">
                          <span className="text-xs text-gray-400">Due: {goal.dueDate}</span>
                          <span className={clsx('rounded px-1.5 py-0.5 text-xs font-medium',
                            goal.priority === 'High' ? 'bg-red-50 text-red-600' : 'bg-amber-50 text-amber-600'
                          )}>{goal.priority}</span>
                        </div>
                      </div>
                    </div>
                    <span className="text-sm font-semibold text-gray-900">{goal.progress}%</span>
                  </div>
                  <div className="mt-3 h-1.5 rounded-full bg-gray-100">
                    <div className={clsx('h-full rounded-full transition-all',
                      goal.progress === 100 ? 'bg-emerald-500' : goal.progress >= 60 ? 'bg-blue-500' : 'bg-amber-500'
                    )} style={{ width: `${goal.progress}%` }} />
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
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
              <button onClick={() => { showToast('Comment saved'); setFeedback(''); }} className="btn-primary mt-3 text-sm" disabled={!feedback.trim()}>
                <MessageSquare className="h-4 w-4" /> Save Comment
              </button>
            </div>

            {/* Past Appraisals */}
            <div className="card">
              <h2 className="mb-4 text-sm font-semibold text-gray-900">Past Appraisals</h2>
              <div className="space-y-3">
                {PAST_APPRAISALS.map((a, i) => (
                  <div key={i} className="flex items-center justify-between rounded-lg border border-gray-100 p-3">
                    <div className="flex items-center gap-3">
                      <div className="flex h-8 w-8 items-center justify-center rounded-full bg-purple-50">
                        <Star className="h-4 w-4 text-purple-600" />
                      </div>
                      <div>
                        <p className="text-sm font-medium text-gray-900">{a.cycle}</p>
                        <p className="text-xs text-gray-500">{a.date}</p>
                      </div>
                    </div>
                    <div className="text-right">
                      <p className="text-sm font-semibold text-gray-900">{a.score}/5.0</p>
                      <p className="text-xs text-emerald-600">{a.rating}</p>
                    </div>
                  </div>
                ))}
              </div>
              <div className="mt-3 flex items-center gap-2 rounded-lg bg-purple-50 p-3">
                <TrendingUp className="h-4 w-4 text-purple-600" />
                <p className="text-xs text-purple-700">Your performance trend is <span className="font-semibold">improving</span> over the last 3 cycles.</p>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
};
