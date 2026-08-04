import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  Bell, CalendarDays, Check, CheckCheck, ClipboardList,
  Info, MessageSquare, Trash2, Users,
} from 'lucide-react';
import { clsx } from 'clsx';

type NotificationType = 'leave' | 'appraisal' | 'staff' | 'system' | 'message';

type Notification = {
  id: string;
  title: string;
  message: string;
  time: string;
  timestamp: number;
  read: boolean;
  type: NotificationType;
  actionLabel?: string;
  actionHref?: string;
  // When set, clicking the action button fires a trigger to the module instead
  // of navigating to a URL — used for opening messaging modals, etc.
  actionTrigger?: { moduleId: string; actionId: string };
};

const ICON_MAP: Record<NotificationType, React.ElementType> = {
  leave: CalendarDays,
  appraisal: ClipboardList,
  staff: Users,
  system: Info,
  message: MessageSquare,
};

const COLOR_MAP: Record<NotificationType, string> = {
  leave: 'bg-green-100 text-green-600',
  appraisal: 'bg-purple-100 text-purple-600',
  staff: 'bg-blue-100 text-blue-600',
  system: 'bg-gray-100 text-gray-600',
  message: 'bg-amber-100 text-amber-600',
};

// Map MODULE_ALERT level → notification type
const LEVEL_TYPE_MAP: Record<string, NotificationType> = {
  error: 'system',
  warning: 'system',
  success: 'message',
  info: 'staff',
};

// Map module ID → notification type
const MODULE_TYPE_MAP: Record<string, NotificationType> = {
  eleave: 'leave',
  eappraisal: 'appraisal',
  srms: 'staff',
};

const STORAGE_KEY = 'hris_notifications';
const MAX_STORED = 80;

function loadNotifications(): Notification[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function saveNotifications(notifications: Notification[]): void {
  try {
    // Keep only the most recent MAX_STORED to avoid unbounded growth
    const trimmed = notifications.slice(0, MAX_STORED);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(trimmed));
  } catch {
    // storage full or private mode — not critical
  }
}

function formatRelativeTime(timestamp: number): string {
  const diffMs = Date.now() - timestamp;
  const diffMin = Math.floor(diffMs / 60_000);
  if (diffMin < 1) return 'Just now';
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHour = Math.floor(diffMin / 60);
  if (diffHour < 24) return `${diffHour}h ago`;
  const diffDay = Math.floor(diffHour / 24);
  return `${diffDay}d ago`;
}

function makeId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

export const NotificationPanel: React.FC = () => {
  const [open, setOpen] = useState(false);
  const [notifications, setNotifications] = useState<Notification[]>(loadNotifications);
  const ref = useRef<HTMLDivElement>(null);

  // Persist to localStorage whenever notifications change
  useEffect(() => {
    saveNotifications(notifications);
  }, [notifications]);

  // Close panel when clicking outside
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  // Receive MODULE_ALERT events from any embedded federated module and
  // convert them into persistent notifications in this panel.
  const addModuleNotification = useCallback(
    (detail: { moduleId: string; message: string; level: string }) => {
      const { moduleId, message, level } = detail;
      if (!message) return;

      const type: NotificationType =
        MODULE_TYPE_MAP[moduleId?.toLowerCase()] ??
        LEVEL_TYPE_MAP[level?.toLowerCase()] ??
        'system';

      const moduleLabel =
        moduleId === 'srms' ? 'Staff Records'
        : moduleId === 'eappraisal' ? 'Performance Appraisal'
        : moduleId === 'eleave' ? 'Leave Management'
        : moduleId ?? 'Module';

      const notification: Notification = {
        id: makeId(),
        title: moduleLabel,
        message,
        time: formatRelativeTime(Date.now()),
        timestamp: Date.now(),
        read: false,
        type,
      };

      setNotifications((prev) => {
        // Deduplicate: skip if same message from same module in last 5 seconds
        const recent = prev[0];
        if (
          recent &&
          recent.title === notification.title &&
          recent.message === notification.message &&
          Date.now() - recent.timestamp < 5_000
        ) {
          return prev;
        }
        return [notification, ...prev];
      });
    },
    [],
  );

  useEffect(() => {
    const handle = (event: Event) => {
      const detail = (event as CustomEvent<{ moduleId: string; message: string; level: string }>).detail;
      if (detail) addModuleNotification(detail);
    };
    window.addEventListener('hris:module-alert', handle);
    return () => window.removeEventListener('hris:module-alert', handle);
  }, [addModuleNotification]);

  // Receive rich MODULE_NOTIFICATION events from embedded modules.
  // These carry structured data (sender, preview, conversationId) and produce
  // notification entries with an action button that opens the module's UI.
  useEffect(() => {
    const handle = (event: Event) => {
      const detail = (event as CustomEvent<{
        moduleId: string;
        notificationType: string;
        senderName: string;
        preview: string;
        conversationId: string;
      }>).detail;
      if (!detail) return;

      const { moduleId, senderName, preview, conversationId } = detail;
      const moduleLabel =
        moduleId === 'srms' ? 'Staff Records'
        : moduleId === 'eappraisal' ? 'Performance Appraisal'
        : moduleId === 'eleave' ? 'Leave Management'
        : moduleId ?? 'Module';

      const notification: Notification = {
        id: conversationId ? `msg-${conversationId}-${Date.now()}` : makeId(),
        title: senderName ? `Message from ${senderName}` : 'New Message',
        message: preview || `New message in ${moduleLabel}`,
        time: formatRelativeTime(Date.now()),
        timestamp: Date.now(),
        read: false,
        type: 'message',
        actionLabel: 'Open Messages',
        actionTrigger: { moduleId, actionId: 'messages:open' },
      };

      setNotifications((prev) => {
        // Skip if an identical conversation notification arrived within 15 seconds
        if (
          conversationId &&
          prev.some(
            (n) =>
              n.id.startsWith(`msg-${conversationId}`) &&
              Date.now() - n.timestamp < 15_000,
          )
        ) {
          return prev;
        }
        return [notification, ...prev];
      });
    };
    window.addEventListener('hris:module-notification', handle);
    return () => window.removeEventListener('hris:module-notification', handle);
  }, []);

  // Refresh relative timestamps every minute so "2m ago" stays accurate
  useEffect(() => {
    const timer = window.setInterval(() => {
      setNotifications((prev) =>
        prev.map((n) => ({ ...n, time: formatRelativeTime(n.timestamp) })),
      );
    }, 60_000);
    return () => window.clearInterval(timer);
  }, []);

  const unreadCount = notifications.filter((n) => !n.read).length;

  const markRead = (id: string) => {
    setNotifications((prev) => prev.map((n) => (n.id === id ? { ...n, read: true } : n)));
  };

  const markAllRead = () => {
    setNotifications((prev) => prev.map((n) => ({ ...n, read: true })));
  };

  const removeNotification = (id: string) => {
    setNotifications((prev) => prev.filter((n) => n.id !== id));
  };

  const clearAll = () => {
    setNotifications([]);
  };

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className="relative rounded-lg p-2 text-gray-500 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-800"
        title="Notifications"
        aria-label={`Notifications${unreadCount > 0 ? ` (${unreadCount} unread)` : ''}`}
      >
        <Bell className="h-5 w-5" />
        {unreadCount > 0 && (
          <span className="absolute right-0.5 top-0.5 flex h-4 w-4 items-center justify-center rounded-full bg-red-500 text-[10px] font-bold text-white">
            {unreadCount > 9 ? '9+' : unreadCount}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 top-full z-50 mt-2 w-96 rounded-xl border border-gray-200 bg-white shadow-xl dark:border-gray-700 dark:bg-gray-900">
          {/* Header */}
          <div className="flex items-center justify-between border-b border-gray-100 px-4 py-3 dark:border-gray-800">
            <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
              Notifications
            </h3>
            <div className="flex items-center gap-2">
              {unreadCount > 0 && (
                <button
                  onClick={markAllRead}
                  className="flex items-center gap-1 text-xs font-medium text-brand-500 hover:text-brand-600"
                >
                  <CheckCheck className="h-3.5 w-3.5" /> Mark all read
                </button>
              )}
              {notifications.length > 0 && (
                <button
                  onClick={clearAll}
                  className="flex items-center gap-1 text-xs font-medium text-gray-400 hover:text-red-500"
                  title="Clear all"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              )}
            </div>
          </div>

          {/* List */}
          <div className="max-h-96 overflow-y-auto">
            {notifications.length === 0 ? (
              <div className="px-4 py-10 text-center">
                <Bell className="mx-auto h-8 w-8 text-gray-300 dark:text-gray-600" />
                <p className="mt-2 text-sm text-gray-400 dark:text-gray-500">No notifications</p>
                <p className="mt-1 text-xs text-gray-300 dark:text-gray-600">
                  Activity from connected modules will appear here
                </p>
              </div>
            ) : (
              notifications.map((n) => {
                const Icon = ICON_MAP[n.type];
                return (
                  <div
                    key={n.id}
                    className={clsx(
                      'group flex gap-3 border-b border-gray-50 px-4 py-3 transition-colors hover:bg-gray-50 dark:border-gray-800 dark:hover:bg-gray-800/50',
                      !n.read && 'bg-brand-500/5 dark:bg-brand-400/5',
                    )}
                  >
                    <div
                      className={clsx(
                        'mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full',
                        COLOR_MAP[n.type],
                      )}
                    >
                      <Icon className="h-4 w-4" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-start justify-between gap-2">
                        <p
                          className={clsx(
                            'text-sm',
                            n.read
                              ? 'text-gray-700 dark:text-gray-300'
                              : 'font-medium text-gray-900 dark:text-gray-100',
                          )}
                        >
                          {n.title}
                        </p>
                        <div className="flex shrink-0 items-center gap-1">
                          {!n.read && (
                            <button
                              onClick={() => markRead(n.id)}
                              className="rounded p-0.5 text-gray-400 opacity-0 transition-opacity hover:text-brand-500 group-hover:opacity-100"
                              title="Mark as read"
                            >
                              <Check className="h-3.5 w-3.5" />
                            </button>
                          )}
                          <button
                            onClick={() => removeNotification(n.id)}
                            className="rounded p-0.5 text-gray-400 opacity-0 transition-opacity hover:text-red-500 group-hover:opacity-100"
                            title="Dismiss"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </button>
                        </div>
                      </div>
                      <p className="mt-0.5 text-xs text-gray-500 line-clamp-2 dark:text-gray-400">
                        {n.message}
                      </p>
                      <div className="mt-1.5 flex items-center gap-3">
                        <span className="text-[10px] text-gray-400 dark:text-gray-500">{n.time}</span>
                        {n.actionLabel && n.actionTrigger && (
                          <button
                            type="button"
                            className="text-[11px] font-medium text-brand-500 hover:text-brand-600"
                            onClick={() => {
                              markRead(n.id);
                              window.dispatchEvent(
                                new CustomEvent(
                                  `hris:module-trigger-action-${n.actionTrigger!.moduleId}`,
                                  { detail: { actionId: n.actionTrigger!.actionId } },
                                ),
                              );
                              setOpen(false);
                            }}
                          >
                            {n.actionLabel} &rarr;
                          </button>
                        )}
                        {n.actionLabel && n.actionHref && !n.actionTrigger && (
                          <a
                            href={n.actionHref}
                            className="text-[11px] font-medium text-brand-500 hover:text-brand-600"
                            onClick={() => markRead(n.id)}
                          >
                            {n.actionLabel} &rarr;
                          </a>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })
            )}
          </div>

          {/* Footer */}
          <div className="border-t border-gray-100 px-4 py-2.5 text-center dark:border-gray-800">
            <span className="text-xs text-gray-400 dark:text-gray-500">
              Notifications from all connected modules
            </span>
          </div>
        </div>
      )}
    </div>
  );
};
