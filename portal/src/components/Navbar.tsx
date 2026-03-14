import React from 'react';
import { Menu, LogOut, Moon, PanelLeftClose, PanelLeftOpen, Sun } from 'lucide-react';
import { useAuth } from '../auth/AuthProvider';
import { getRoleLabel } from '../auth/roles';
import { RoleSwitcher } from './RoleSwitcher';
import { NotificationPanel } from './NotificationPanel';

type NavbarProps = {
  onMenuToggle: () => void;
  sidebarCollapsed: boolean;
  onToggleSidebarCollapse: () => void;
};

export const Navbar: React.FC<NavbarProps> = ({ onMenuToggle, sidebarCollapsed, onToggleSidebarCollapse }) => {
  const { user, logout } = useAuth();
  const [darkMode, setDarkMode] = React.useState<boolean>(() => {
    if (typeof window === 'undefined') return false;
    const stored = window.localStorage.getItem('hris_theme');
    if (stored === 'dark') return true;
    if (stored === 'light') return false;
    return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
  });

  React.useEffect(() => {
    if (typeof document === 'undefined') return;
    document.documentElement.classList.toggle('dark', darkMode);
    window.localStorage.setItem('hris_theme', darkMode ? 'dark' : 'light');
  }, [darkMode]);

  return (
    <header className="sticky top-0 z-30 flex h-16 items-center justify-between border-b border-gray-200 bg-white px-4 transition-colors lg:px-6 dark:border-gray-800 dark:bg-gray-900">
      <div className="flex items-center gap-3">
        <button
          onClick={onMenuToggle}
          className="rounded-lg p-2 text-gray-500 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-800 lg:hidden"
        >
          <Menu className="h-5 w-5" />
        </button>
        <button
          type="button"
          onClick={onToggleSidebarCollapse}
          className="hidden rounded-lg p-2 text-gray-500 hover:bg-gray-100 hover:text-gray-800 dark:text-gray-300 dark:hover:bg-gray-800 dark:hover:text-gray-100 lg:inline-flex"
          title={sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          {sidebarCollapsed ? <PanelLeftOpen className="h-5 w-5" /> : <PanelLeftClose className="h-5 w-5" />}
        </button>
        <div className="hidden text-sm text-gray-500 dark:text-gray-400 lg:block">
          {user?.email && <span>{user.email}</span>}
        </div>
      </div>

      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={() => setDarkMode((v) => !v)}
          title={darkMode ? 'Switch to light mode' : 'Switch to dark mode'}
          className="rounded-lg p-2 text-gray-500 hover:bg-gray-100 hover:text-gray-800 dark:text-gray-300 dark:hover:bg-gray-800 dark:hover:text-gray-100"
        >
          {darkMode ? <Sun className="h-5 w-5" /> : <Moon className="h-5 w-5" />}
        </button>
        <RoleSwitcher />

        <NotificationPanel />

        <div className="mx-2 h-6 w-px bg-gray-200 dark:bg-gray-700" />

        <div className="hidden items-center gap-2 sm:flex">
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-brand-500 text-xs font-bold text-white">
            {user?.username?.charAt(0)?.toUpperCase() ?? 'U'}
          </div>
          <div className="text-right">
            <p className="text-sm font-medium text-gray-900 dark:text-gray-100">{user?.username}</p>
            <p className="text-xs text-gray-500 dark:text-gray-400">{getRoleLabel(user?.effectiveRole ?? 'hris:employee')}</p>
          </div>
        </div>

        <button
          onClick={logout}
          className="ml-2 rounded-lg p-2 text-gray-500 hover:bg-red-50 hover:text-red-600"
          title="Sign out"
        >
          <LogOut className="h-5 w-5" />
        </button>
      </div>
    </header>
  );
};
