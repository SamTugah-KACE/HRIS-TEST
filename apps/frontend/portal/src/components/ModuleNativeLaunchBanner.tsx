import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ExternalLink } from 'lucide-react';
import { getCatalogWorkspaceLaunch, getModulesCatalog } from '../api/hrisCoreClient';

type ModuleNativeLaunchBannerProps = {
  /** Registry module id, e.g. eappraisal | eleave | srms */
  moduleId: string;
};

const MODULE_LABELS: Record<string, string> = {
  eappraisal: 'eAppraisal',
  eleave: 'eLeave',
  srms: 'SRMS',
};

/**
 * Shows a dismissible strip linking to the HRIS workspace when the Core catalog marks the native module available.
 * Fetches the module catalog once on mount; failures leave the banner hidden.
 */
export const ModuleNativeLaunchBanner: React.FC<ModuleNativeLaunchBannerProps> = ({ moduleId }) => {
  const [launch, setLaunch] = useState<{ path: string; openMode: 'new_tab' | 'same_window' } | null>(null);
  const [dismissed, setDismissed] = useState(false);
  const moduleLabel = MODULE_LABELS[String(moduleId).toLowerCase()] ?? 'Module';

  useEffect(() => {
    let cancelled = false;
    getModulesCatalog()
      .then((response) => {
        if (cancelled) return;
        setLaunch(getCatalogWorkspaceLaunch(response.modules ?? [], moduleId));
      })
      .catch(() => {
        if (cancelled) return;
        setLaunch(null);
      });
    return () => {
      cancelled = true;
    };
  }, [moduleId]);

  if (dismissed || !launch) return null;

  return (
    <div className="mb-4 flex flex-wrap items-center justify-between gap-2 rounded-lg border border-brand-200 bg-brand-500/5 px-4 py-3 text-sm dark:border-brand-900/40 dark:bg-brand-500/10">
      <p className="text-gray-700 dark:text-gray-200">
        This workflow opens in the module native UI for advanced operations. Your existing roles and permissions still apply.
      </p>
      <div className="flex items-center gap-2">
        <Link
          to={launch.path}
          aria-label={`Open in ${moduleLabel}`}
          className="inline-flex items-center gap-1 rounded-lg bg-brand-500 px-3 py-1.5 text-xs font-semibold text-white hover:bg-brand-600"
        >
          <ExternalLink className="h-3.5 w-3.5" />
          Open in {moduleLabel}
        </Link>
        <button
          type="button"
          onClick={() => setDismissed(true)}
          className="text-xs text-gray-500 hover:text-gray-800 dark:text-gray-400 dark:hover:text-gray-100"
        >
          Dismiss
        </button>
      </div>
    </div>
  );
};
