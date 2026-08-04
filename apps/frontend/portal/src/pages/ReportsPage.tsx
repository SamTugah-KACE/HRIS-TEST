import React, { useState } from 'react';
import { FileText, Download, BarChart3, Calendar, Users, ClipboardList, CalendarDays, CheckCircle, Clock, Filter } from 'lucide-react';
import { clsx } from 'clsx';

const REPORTS = [
  { id: 'staff-summary', name: 'Staff Summary Report', module: 'SRMS', icon: Users, description: 'Overview of all employees by department, branch, status, and demographics', format: ['PDF', 'Excel'], category: 'staff' },
  { id: 'headcount', name: 'Department Headcount', module: 'SRMS', icon: Users, description: 'Employee distribution across departments and branches with trend data', format: ['Excel', 'CSV'], category: 'staff' },
  { id: 'new-hires', name: 'New Hires Report', module: 'SRMS', icon: Users, description: 'Recently onboarded employees with their joining dates and departments', format: ['PDF', 'Excel'], category: 'staff' },
  { id: 'appraisal-cycle', name: 'Appraisal Cycle Report', module: 'eAppraisal', icon: ClipboardList, description: 'Summary of completion rates, scores, and pending reviews for the current cycle', format: ['PDF'], category: 'appraisal' },
  { id: 'performance-trend', name: 'Performance Trend Analysis', module: 'eAppraisal', icon: BarChart3, description: 'Year-over-year performance trends by department and individual', format: ['PDF', 'Excel'], category: 'appraisal' },
  { id: 'leave-utilization', name: 'Leave Utilization Report', module: 'eLeave', icon: CalendarDays, description: 'Leave balance consumption across all leave types and departments', format: ['PDF', 'Excel'], category: 'leave' },
  { id: 'leave-calendar', name: 'Leave Calendar Report', module: 'eLeave', icon: Calendar, description: 'Monthly/quarterly leave calendar for workforce planning', format: ['PDF'], category: 'leave' },
  { id: 'employee-360', name: 'Cross-Module Employee 360', module: 'All Modules', icon: Users, description: 'Combined profile, appraisal history, and leave data for any employee', format: ['PDF'], category: 'cross' },
  { id: 'attrition', name: 'Attrition Analysis', module: 'SRMS', icon: BarChart3, description: 'Employee turnover rates, exit reasons, and retention metrics', format: ['PDF', 'Excel'], category: 'staff' },
];

export const ReportsPage: React.FC = () => {
  const [categoryFilter, setCategoryFilter] = useState('all');
  const [generating, setGenerating] = useState<string | null>(null);
  const [generated, setGenerated] = useState<Set<string>>(new Set());
  const [selectedFormat, setSelectedFormat] = useState<Record<string, string>>({});
  const [toast, setToast] = useState<string | null>(null);

  const showToast = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 3000);
  };

  const handleGenerate = (reportId: string, reportName: string) => {
    setGenerating(reportId);
    setTimeout(() => {
      setGenerating(null);
      setGenerated(prev => new Set(prev).add(reportId));
      showToast(`${reportName} generated successfully`);
    }, 2000);
  };

  const filtered = categoryFilter === 'all' ? REPORTS : REPORTS.filter(r => r.category === categoryFilter);

  return (
    <div className="space-y-6">
      {toast && (
        <div className="fixed right-4 top-20 z-50 flex items-center gap-2 rounded-lg bg-emerald-600 px-4 py-3 text-sm font-medium text-white shadow-lg">
          <CheckCircle className="h-4 w-4" /> {toast}
        </div>
      )}

      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Reports</h1>
          <p className="mt-1 text-sm text-gray-500">Generate and download cross-module reports</p>
        </div>
        <button onClick={() => showToast('Scheduling report delivery...')} className="btn-secondary">
          <Calendar className="h-4 w-4" /> Schedule Reports
        </button>
      </div>

      {/* Category Filter */}
      <div className="flex gap-2 overflow-x-auto">
        {[
          { value: 'all', label: 'All Reports' },
          { value: 'staff', label: 'Staff Records' },
          { value: 'appraisal', label: 'Appraisal' },
          { value: 'leave', label: 'Leave' },
          { value: 'cross', label: 'Cross-Module' },
        ].map(cat => (
          <button
            key={cat.value}
            onClick={() => setCategoryFilter(cat.value)}
            className={clsx(
              'shrink-0 rounded-full px-4 py-2 text-sm font-medium transition-colors',
              categoryFilter === cat.value
                ? 'bg-brand-500 text-white'
                : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
            )}
          >
            {cat.label}
          </button>
        ))}
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {filtered.map(r => {
          const Icon = r.icon;
          const isGenerating = generating === r.id;
          const isGenerated = generated.has(r.id);
          const format = selectedFormat[r.id] || r.format[0];

          return (
            <div key={r.id} className="card flex flex-col justify-between">
              <div>
                <div className="flex items-center gap-3">
                  <div className="rounded-lg bg-brand-500/10 p-2">
                    <Icon className="h-5 w-5 text-brand-500" />
                  </div>
                  <div>
                    <h3 className="text-sm font-semibold text-gray-900">{r.name}</h3>
                    <span className="text-xs text-gray-400">{r.module}</span>
                  </div>
                </div>
                <p className="mt-3 text-xs text-gray-500">{r.description}</p>
              </div>
              <div className="mt-4 space-y-3">
                <div className="flex items-center gap-2">
                  <select
                    value={format}
                    onChange={e => setSelectedFormat(prev => ({ ...prev, [r.id]: e.target.value }))}
                    className="input-field py-1.5 text-xs"
                  >
                    {r.format.map(f => (
                      <option key={f} value={f}>{f}</option>
                    ))}
                  </select>
                  <button
                    onClick={() => handleGenerate(r.id, r.name)}
                    disabled={isGenerating}
                    className={clsx('btn-secondary flex-1 py-1.5 text-xs', isGenerating && 'opacity-50')}
                  >
                    {isGenerating ? (
                      <><Clock className="h-3.5 w-3.5 animate-spin" /> Generating...</>
                    ) : isGenerated ? (
                      <><Download className="h-3.5 w-3.5" /> Download {format}</>
                    ) : (
                      <><BarChart3 className="h-3.5 w-3.5" /> Generate</>
                    )}
                  </button>
                </div>
                {isGenerated && (
                  <p className="text-center text-[10px] text-emerald-600">Ready to download</p>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
