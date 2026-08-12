import React, { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { ModuleFrame } from '../../components/ModuleFrame';

type SummaryCard = {
  id: string;
  label: string;
  value: string | number;
};

export const ModuleWorkspacePage: React.FC<{ fixedModuleId?: string }> = ({ fixedModuleId }) => {
  const { moduleId = '' } = useParams();
  const normalizedModuleId = String(fixedModuleId || moduleId || '').toLowerCase();

  // Summary cards ported from the module via MODULE_SUMMARY_UPDATE postMessage.
  const [summaryCards, setSummaryCards] = useState<SummaryCard[]>([]);

  useEffect(() => {
    const handleSummaryUpdate = (event: Event) => {
      const detail = (event as CustomEvent<{ cards: SummaryCard[] } | null>).detail;
      setSummaryCards(Array.isArray(detail?.cards) ? detail.cards : []);
    };
    window.addEventListener('hris:module-summary-update', handleSummaryUpdate);
    return () => {
      window.removeEventListener('hris:module-summary-update', handleSummaryUpdate);
      setSummaryCards([]);
    };
  }, []);

  return (
    <div className="flex flex-col">
      {/* ── Module summary stats — single-row horizontal scroll strip ──────── */}
      {summaryCards.length > 0 && (
        <div className="border-b border-gray-200/80 bg-white/80 px-4 py-2.5 dark:border-gray-800/80 dark:bg-gray-900/60">
          <div className="flex gap-2.5 overflow-x-auto pb-0.5 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
            {summaryCards.map((card) => (
              <div
                key={card.id}
                className="flex min-w-[100px] shrink-0 flex-col items-center justify-center rounded-lg border border-gray-200/70 bg-gray-50 px-4 py-2.5 shadow-sm transition-shadow hover:shadow-md dark:border-gray-700/60 dark:bg-gray-800"
              >
                <span className="text-xl font-bold leading-none text-brand-600 dark:text-brand-400">
                  {card.value}
                </span>
                <span className="mt-1 text-center text-[11px] font-medium text-gray-500 dark:text-gray-400">
                  {card.label}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Module iframe — fills all remaining body height ─────────────────── */}
      <ModuleFrame
        moduleId={normalizedModuleId}
        title={`${normalizedModuleId} workspace`}
        className="w-full border-0"
      />
    </div>
  );
};
