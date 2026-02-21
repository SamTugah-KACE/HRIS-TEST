import React from 'react';
import { type LucideIcon } from 'lucide-react';
import { clsx } from 'clsx';

type StatCardProps = {
  label: string;
  value: string | number;
  icon: LucideIcon;
  trend?: string;
  trendUp?: boolean;
  color?: 'blue' | 'green' | 'amber' | 'red' | 'purple' | 'indigo';
};

const colorMap = {
  blue: 'bg-blue-50 text-blue-600',
  green: 'bg-emerald-50 text-emerald-600',
  amber: 'bg-amber-50 text-amber-600',
  red: 'bg-red-50 text-red-600',
  purple: 'bg-purple-50 text-purple-600',
  indigo: 'bg-indigo-50 text-indigo-600',
};

export const StatCard: React.FC<StatCardProps> = ({ label, value, icon: Icon, trend, trendUp, color = 'blue' }) => {
  return (
    <div className="stat-card">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-gray-500">{label}</span>
        <div className={clsx('rounded-lg p-2', colorMap[color])}>
          <Icon className="h-5 w-5" />
        </div>
      </div>
      <p className="mt-1 text-2xl font-bold text-gray-900">{value}</p>
      {trend && (
        <p className={clsx('text-xs font-medium', trendUp ? 'text-emerald-600' : 'text-red-600')}>
          {trendUp ? '↑' : '↓'} {trend}
        </p>
      )}
    </div>
  );
};
