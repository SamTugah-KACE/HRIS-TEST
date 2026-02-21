import React, { useState, useRef, useEffect } from 'react';
import { Bell, Check, CheckCheck, CalendarDays, ClipboardList, Users, MessageSquare, Info, Trash2 } from 'lucide-react';
import { clsx } from 'clsx';

type Notification = {
  id: string;
  title: string;
  message: string;
  time: string;
  read: boolean;
  type: 'leave' | 'appraisal' | 'staff' | 'system' | 'message';
  actionLabel?: string;
  actionHref?: string;
};

const ICON_MAP = {
  leave: CalendarDays,
  appraisal: ClipboardList,
  staff: Users,
  system: Info,
  message: MessageSquare,
};

const COLOR_MAP = {
  leave: 'bg-green-100 text-green-600',
  appraisal: 'bg-purple-100 text-purple-600',
  staff: 'bg-blue-100 text-blue-600',
  system: 'bg-gray-100 text-gray-600',
  message: 'bg-amber-100 text-amber-600',
};

const INITIAL_NOTIFICATIONS: Notification[] = [
  { id: '1', title: 'Leave Approved', message: 'Your annual leave request (Dec 20-22) has been approved by Dr. Ama Mensah.', time: '5 min ago', read: false, type: 'leave', actionLabel: 'View Details', actionHref: '/modules/leave' },
  { id: '2', title: 'Appraisal Reminder', message: 'Self-assessment for 2025/2026 cycle is due in 14 days. Please complete all sections.', time: '1 hour ago', read: false, type: 'appraisal', actionLabel: 'Start Assessment', actionHref: '/modules/appraisal' },
  { id: '3', title: 'New Team Member', message: 'Kojo Frimpong has joined the Information Technology department.', time: '2 hours ago', read: false, type: 'staff' },
  { id: '4', title: 'System Maintenance', message: 'Scheduled maintenance on Saturday, Feb 28 from 10:00 PM to 2:00 AM GMT.', time: '5 hours ago', read: true, type: 'system' },
  { id: '5', title: 'Message from HR', message: 'Please update your emergency contact information before end of month.', time: '1 day ago', read: true, type: 'message', actionLabel: 'Update Now', actionHref: '/profile' },
  { id: '6', title: 'Leave Request Submitted', message: 'Your leave request for Feb 25-27 (3 days) is pending supervisor approval.', time: '2 days ago', read: true, type: 'leave' },
];

export const NotificationPanel: React.FC = () => {
  const [open, setOpen] = useState(false);
  const [notifications, setNotifications] = useState(INITIAL_NOTIFICATIONS);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const unreadCount = notifications.filter(n => !n.read).length;

  const markRead = (id: string) => {
    setNotifications(prev => prev.map(n => n.id === id ? { ...n, read: true } : n));
  };

  const markAllRead = () => {
    setNotifications(prev => prev.map(n => ({ ...n, read: true })));
  };

  const removeNotification = (id: string) => {
    setNotifications(prev => prev.filter(n => n.id !== id));
  };

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="relative rounded-lg p-2 text-gray-500 hover:bg-gray-100"
      >
        <Bell className="h-5 w-5" />
        {unreadCount > 0 && (
          <span className="absolute right-0.5 top-0.5 flex h-4 w-4 items-center justify-center rounded-full bg-red-500 text-[10px] font-bold text-white">
            {unreadCount}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 top-full z-50 mt-2 w-96 rounded-xl border border-gray-200 bg-white shadow-xl">
          <div className="flex items-center justify-between border-b border-gray-100 px-4 py-3">
            <h3 className="text-sm font-semibold text-gray-900">Notifications</h3>
            {unreadCount > 0 && (
              <button onClick={markAllRead} className="flex items-center gap-1 text-xs font-medium text-brand-500 hover:text-brand-600">
                <CheckCheck className="h-3.5 w-3.5" /> Mark all read
              </button>
            )}
          </div>

          <div className="max-h-96 overflow-y-auto">
            {notifications.length === 0 ? (
              <div className="px-4 py-10 text-center">
                <Bell className="mx-auto h-8 w-8 text-gray-300" />
                <p className="mt-2 text-sm text-gray-400">No notifications</p>
              </div>
            ) : (
              notifications.map(n => {
                const Icon = ICON_MAP[n.type];
                return (
                  <div
                    key={n.id}
                    className={clsx(
                      'group flex gap-3 border-b border-gray-50 px-4 py-3 transition-colors hover:bg-gray-50',
                      !n.read && 'bg-brand-500/5'
                    )}
                  >
                    <div className={clsx('mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full', COLOR_MAP[n.type])}>
                      <Icon className="h-4 w-4" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-start justify-between gap-2">
                        <p className={clsx('text-sm', n.read ? 'text-gray-700' : 'font-medium text-gray-900')}>{n.title}</p>
                        <div className="flex shrink-0 items-center gap-1">
                          {!n.read && (
                            <button onClick={() => markRead(n.id)} className="rounded p-0.5 text-gray-400 opacity-0 transition-opacity hover:text-brand-500 group-hover:opacity-100" title="Mark as read">
                              <Check className="h-3.5 w-3.5" />
                            </button>
                          )}
                          <button onClick={() => removeNotification(n.id)} className="rounded p-0.5 text-gray-400 opacity-0 transition-opacity hover:text-red-500 group-hover:opacity-100" title="Dismiss">
                            <Trash2 className="h-3.5 w-3.5" />
                          </button>
                        </div>
                      </div>
                      <p className="mt-0.5 text-xs text-gray-500 line-clamp-2">{n.message}</p>
                      <div className="mt-1.5 flex items-center gap-3">
                        <span className="text-[10px] text-gray-400">{n.time}</span>
                        {n.actionLabel && (
                          <a href={n.actionHref ?? '#'} className="text-[11px] font-medium text-brand-500 hover:text-brand-600">
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

          <div className="border-t border-gray-100 px-4 py-2.5 text-center">
            <button className="text-xs font-medium text-brand-500 hover:text-brand-600">View All Notifications</button>
          </div>
        </div>
      )}
    </div>
  );
};
