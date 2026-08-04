import React, { useRef } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { ChevronLeft, LogOut, Menu, Moon, PanelLeftClose, PanelLeftOpen, Search, Sun, X } from 'lucide-react';
import { useAuth } from '../auth/AuthProvider';
import { getRoleLabel } from '../auth/roles';
import { RoleSwitcher } from './RoleSwitcher';
import { NotificationPanel } from './NotificationPanel';

type NavbarProps = {
  onMenuToggle: () => void;
  sidebarCollapsed: boolean;
  onToggleSidebarCollapse: () => void;
};

type ModuleSearchConfig = {
  moduleId: string;
  placeholder: string;
};

const MODULE_LABELS: Record<string, string> = {
  srms: 'Staff Records',
  eappraisal: 'Performance Appraisal',
  eleave: 'Leave Management',
};

const MODULE_SUMMARY_PATH: Record<string, string> = {
  srms: '/employees',
  eappraisal: '/modules/appraisal',
  eleave: '/modules/leave',
};

export const Navbar: React.FC<NavbarProps> = ({ onMenuToggle, sidebarCollapsed, onToggleSidebarCollapse }) => {
  const { user, logout } = useAuth();
  const location = useLocation();

  const [darkMode, setDarkMode] = React.useState<boolean>(() => {
    if (typeof window === 'undefined') return false;
    const stored = window.localStorage.getItem('hris_theme');
    if (stored === 'dark') return true;
    if (stored === 'light') return false;
    return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
  });

  // Search bar shown in the Navbar when the active module declares one.
  const [moduleSearch, setModuleSearch] = React.useState<ModuleSearchConfig | null>(null);
  const [searchQuery, setSearchQuery] = React.useState('');

  // Real avatar URL supplied by the active module (MODULE_USER_PROFILE).
  const [moduleAvatarUrl, setModuleAvatarUrl] = React.useState<string | null>(null);

  const searchInputRef = useRef<HTMLInputElement>(null);

  // Detect active module workspace from current URL.
  const workspaceMatch = location.pathname.match(/^\/modules\/([^/]+)\/native/);
  const activeModuleId = workspaceMatch ? workspaceMatch[1].toLowerCase() : null;
  const activeModuleLabel = activeModuleId ? (MODULE_LABELS[activeModuleId] ?? 'Module') : null;
  const activeModuleSummaryPath = activeModuleId ? (MODULE_SUMMARY_PATH[activeModuleId] ?? '/') : null;

  React.useEffect(() => {
    if (typeof document === 'undefined') return;
    document.documentElement.classList.toggle('dark', darkMode);
    window.localStorage.setItem('hris_theme', darkMode ? 'dark' : 'light');
    // Relay the theme choice to any active module iframe so it can adapt.
    window.dispatchEvent(new CustomEvent('hris:theme-change', { detail: { darkMode } }));
  }, [darkMode]);

  // Listen for module search config — show / hide the contextual search bar.
  React.useEffect(() => {
    const handleSearchConfig = (event: Event) => {
      const detail = (event as CustomEvent<ModuleSearchConfig | null>).detail;
      setModuleSearch(detail ?? null);
      if (!detail) setSearchQuery('');
    };
    window.addEventListener('hris:module-search-config', handleSearchConfig);
    return () => window.removeEventListener('hris:module-search-config', handleSearchConfig);
  }, []);

  // Cmd/Ctrl+K — focus the module search bar from anywhere on the page.
  React.useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k' && moduleSearch) {
        e.preventDefault();
        searchInputRef.current?.focus();
        searchInputRef.current?.select();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [moduleSearch]);

  // Listen for real user avatar from the active module.
  React.useEffect(() => {
    const handleUserProfile = (event: Event) => {
      const detail = (event as CustomEvent<{ avatarUrl: string | null } | null>).detail;
      setModuleAvatarUrl(detail?.avatarUrl ?? null);
    };
    window.addEventListener('hris:module-user-profile', handleUserProfile);
    return () => window.removeEventListener('hris:module-user-profile', handleUserProfile);
  }, []);

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!moduleSearch) return;
    window.dispatchEvent(
      new CustomEvent(`hris:module-search-query-${moduleSearch.moduleId}`, {
        detail: { query: searchQuery },
      }),
    );
  };

  const clearSearch = () => {
    setSearchQuery('');
    if (moduleSearch) {
      window.dispatchEvent(
        new CustomEvent(`hris:module-search-query-${moduleSearch.moduleId}`, {
          detail: { query: '' },
        }),
      );
    }
    searchInputRef.current?.focus();
  };

  // Clicking the user avatar/name when a module is active opens the module's
  // profile editor (TRIGGER_ACTION → SRMS ProfileCard → HRProfileEditorModal).
  const handleAvatarClick = () => {
    if (activeModuleId) {
      window.dispatchEvent(
        new CustomEvent(`hris:module-trigger-action-${activeModuleId}`, {
          detail: { actionId: 'profile:view' },
        }),
      );
    }
  };

  const avatarImage = moduleAvatarUrl ? (
    <img
      src={moduleAvatarUrl}
      alt={user?.username ?? 'User'}
      className="h-8 w-8 rounded-full object-cover"
    />
  ) : (
    <div className="flex h-8 w-8 items-center justify-center rounded-full bg-brand-500 text-xs font-bold text-white">
      {user?.username?.charAt(0)?.toUpperCase() ?? 'U'}
    </div>
  );

  return (
    <header className="sticky top-0 z-30 flex h-14 items-center justify-between border-b border-gray-200 bg-white px-3 transition-colors lg:px-4 dark:border-gray-800 dark:bg-gray-900">
      {/* ── Left: sidebar controls + module back link or email ──────────────── */}
      <div className="flex items-center gap-2">
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

        {/* Back-to-summary link shown when inside a module workspace */}
        {activeModuleId && activeModuleSummaryPath && !moduleSearch && (
          <Link
            to={activeModuleSummaryPath}
            className="hidden items-center gap-1.5 rounded-lg px-2 py-1.5 text-sm font-medium text-brand-600 transition-colors hover:bg-brand-50 hover:text-brand-700 dark:text-brand-400 dark:hover:bg-brand-900/30 dark:hover:text-brand-300 lg:flex"
          >
            <ChevronLeft className="h-4 w-4" />
            <span>{activeModuleLabel}</span>
          </Link>
        )}

        {/* Email shown only when NOT in a module workspace and no search active */}
        {!activeModuleId && !moduleSearch && (
          <div className="hidden text-sm text-gray-500 dark:text-gray-400 lg:block">
            {user?.email && <span>{user.email}</span>}
          </div>
        )}
      </div>

      {/* ── Centre: contextual module search bar ────────────────────────────── */}
      {moduleSearch && (
        <form
          onSubmit={handleSearchSubmit}
          className="mx-3 flex flex-1 items-center gap-2 lg:mx-6"
        >
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
            <input
              ref={searchInputRef}
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder={`${moduleSearch.placeholder} (⌘K)`}
              className="h-9 w-full rounded-lg border border-gray-200 bg-gray-50 pl-9 pr-8 text-sm text-gray-900 placeholder-gray-400 focus:border-brand-500 focus:bg-white focus:outline-none focus:ring-1 focus:ring-brand-500 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100 dark:placeholder-gray-500 dark:focus:border-brand-400"
            />
            {searchQuery && (
              <button
                type="button"
                onClick={clearSearch}
                className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-0.5 text-gray-400 hover:text-gray-600"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            )}
          </div>
          <button
            type="submit"
            className="rounded-lg bg-brand-500 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-600 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:ring-offset-1"
          >
            Search
          </button>
          {/* Back link placed beside search when search is active */}
          {activeModuleId && activeModuleSummaryPath && (
            <Link
              to={activeModuleSummaryPath}
              className="hidden shrink-0 items-center gap-1 rounded-lg border border-gray-200 px-2.5 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-50 dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-800 lg:flex"
            >
              <ChevronLeft className="h-3.5 w-3.5" />
              Summary
            </Link>
          )}
        </form>
      )}

      {/* ── Right: actions + user identity ──────────────────────────────────── */}
      <div className="flex items-center gap-1.5">
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

        <div className="mx-1.5 h-6 w-px bg-gray-200 dark:bg-gray-700" />

        {/* Avatar + name — clickable to open profile editor when in a module */}
        <button
          type="button"
          onClick={handleAvatarClick}
          className={`hidden items-center gap-2 rounded-lg px-2 py-1 transition-colors sm:flex ${
            activeModuleId
              ? 'cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-800'
              : 'cursor-default'
          }`}
          title={activeModuleId ? `View my profile in ${activeModuleLabel}` : undefined}
        >
          {avatarImage}
          <div className="text-right">
            <p className="text-sm font-medium text-gray-900 dark:text-gray-100">{user?.username}</p>
            <p className="text-xs text-gray-500 dark:text-gray-400">{getRoleLabel(user?.effectiveRole ?? 'hris:employee')}</p>
          </div>
        </button>

        <button
          onClick={logout}
          className="ml-1 rounded-lg p-2 text-gray-500 hover:bg-red-50 hover:text-red-600"
          title="Sign out"
        >
          <LogOut className="h-5 w-5" />
        </button>
      </div>
    </header>
  );
};
