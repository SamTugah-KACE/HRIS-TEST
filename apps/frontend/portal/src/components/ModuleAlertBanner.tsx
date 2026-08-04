import React, { useEffect, useRef, useState } from 'react';
import { AlertCircle, CheckCircle, Info, TriangleAlert, X } from 'lucide-react';
import { clsx } from 'clsx';

type AlertLevel = 'info' | 'success' | 'warning' | 'error';

type AlertItem = {
  id: number;
  message: string;
  level: AlertLevel;
};

const ICON: Record<AlertLevel, React.FC<{ className?: string }>> = {
  info:    Info,
  success: CheckCircle,
  warning: TriangleAlert,
  error:   AlertCircle,
};

const STYLE: Record<AlertLevel, string> = {
  info:    'bg-blue-50 border-blue-200 text-blue-800 dark:bg-blue-950/50 dark:border-blue-800/60 dark:text-blue-200',
  success: 'bg-green-50 border-green-200 text-green-800 dark:bg-green-950/50 dark:border-green-800/60 dark:text-green-200',
  warning: 'bg-yellow-50 border-yellow-200 text-yellow-800 dark:bg-yellow-950/50 dark:border-yellow-800/60 dark:text-yellow-200',
  error:   'bg-red-50 border-red-200 text-red-800 dark:bg-red-950/50 dark:border-red-800/60 dark:text-red-200',
};

let _nextId = 1;

// Receives hris:module-alert custom events dispatched by ModuleFrame when the
// active federated module sends a MODULE_ALERT postMessage (relayed from its
// own toast library). Renders the alerts in a sticky banner at the top of the
// main content area and auto-dismisses after 5 seconds.
export const ModuleAlertBanner: React.FC = () => {
  const [alerts, setAlerts] = useState<AlertItem[]>([]);
  const timersRef = useRef<Map<number, ReturnType<typeof setTimeout>>>(new Map());

  useEffect(() => {
    const handleAlert = (event: Event) => {
      const detail = (event as CustomEvent<{ message: string; level: AlertLevel } | null>).detail;
      if (!detail?.message) return;

      const id = _nextId++;
      const item: AlertItem = {
        id,
        message: detail.message,
        level: (detail.level as AlertLevel) || 'info',
      };

      setAlerts((prev) => [...prev.slice(-4), item]); // cap at 5 visible

      // Auto-dismiss after 5 s
      const timer = setTimeout(() => {
        setAlerts((prev) => prev.filter((a) => a.id !== id));
        timersRef.current.delete(id);
      }, 5000);
      timersRef.current.set(id, timer);
    };

    window.addEventListener('hris:module-alert', handleAlert);
    return () => {
      window.removeEventListener('hris:module-alert', handleAlert);
      timersRef.current.forEach((t) => clearTimeout(t));
    };
  }, []);

  const dismiss = (id: number) => {
    const t = timersRef.current.get(id);
    if (t) { clearTimeout(t); timersRef.current.delete(id); }
    setAlerts((prev) => prev.filter((a) => a.id !== id));
  };

  if (!alerts.length) return null;

  return (
    <div className="pointer-events-none fixed right-4 top-16 z-50 flex flex-col gap-2 sm:right-6" aria-live="polite">
      {alerts.map((alert) => {
        const Icon = ICON[alert.level];
        return (
          <div
            key={alert.id}
            className={clsx(
              'pointer-events-auto flex max-w-sm items-start gap-3 rounded-lg border px-4 py-3 shadow-lg transition-all',
              STYLE[alert.level],
            )}
          >
            <Icon className="mt-0.5 h-4 w-4 shrink-0" />
            <p className="flex-1 text-sm font-medium leading-snug">{alert.message}</p>
            <button
              type="button"
              onClick={() => dismiss(alert.id)}
              className="shrink-0 rounded p-0.5 opacity-60 hover:opacity-100"
              aria-label="Dismiss"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
        );
      })}
    </div>
  );
};
