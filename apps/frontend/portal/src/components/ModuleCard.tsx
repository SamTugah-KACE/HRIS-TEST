import React from 'react';
import { Link } from 'react-router-dom';
import { type LucideIcon, ArrowRight, ExternalLink } from 'lucide-react';
import { clsx } from 'clsx';

type ModuleCardProps = {
  title: string;
  description: string;
  icon: LucideIcon;
  href: string;
  stats?: Array<{ label: string; value: string | number }>;
  color: 'blue' | 'green' | 'amber' | 'purple';
  linkLabel?: string;
  nativeModuleId?: string | null;
};

const bgMap = {
  blue: 'from-blue-500 to-blue-600',
  green: 'from-emerald-500 to-emerald-600',
  amber: 'from-amber-500 to-amber-600',
  purple: 'from-purple-500 to-purple-600',
};

export const ModuleCard: React.FC<ModuleCardProps> = ({
  title,
  description,
  icon: Icon,
  href,
  stats,
  color,
  linkLabel,
  nativeModuleId,
}) => {
  return (
    <div className="card overflow-hidden p-0">
      <div className={clsx('bg-gradient-to-r px-6 py-5 text-white', bgMap[color])}>
        <div className="flex items-center gap-3">
          <div className="rounded-lg bg-white/20 p-2">
            <Icon className="h-6 w-6" />
          </div>
          <div>
            <h3 className="text-lg font-semibold">{title}</h3>
            <p className="text-sm text-white/80">{description}</p>
          </div>
        </div>
      </div>
      {stats && stats.length > 0 && (
        <div className="grid grid-cols-2 gap-px border-b border-gray-100 bg-gray-100">
          {stats.map(s => (
            <div key={s.label} className="bg-white px-4 py-3">
              <p className="text-xs text-gray-500">{s.label}</p>
              <p className="text-lg font-semibold text-gray-900">{s.value}</p>
            </div>
          ))}
        </div>
      )}
      <div className="space-y-2 px-6 py-4">
        <Link
          to={href}
          className="inline-flex items-center gap-1 text-sm font-medium text-brand-500 hover:text-brand-600"
        >
          {linkLabel ?? 'Open Module'} <ArrowRight className="h-4 w-4" />
        </Link>
        {nativeModuleId ? (
          <Link
            to={`/modules/${encodeURIComponent(nativeModuleId)}/native`}
            className="inline-flex items-center gap-1 text-xs font-medium text-gray-600 hover:text-brand-600 dark:text-gray-400"
          >
            <ExternalLink className="h-3.5 w-3.5" />
            Open module workspace
          </Link>
        ) : null}
      </div>
    </div>
  );
};
