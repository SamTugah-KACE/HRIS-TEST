import React, { useEffect, useState } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import {
  LayoutDashboard,
  Users,
  ClipboardList,
  CalendarDays,
  Layers,
  FileText,
  Shield,
  Building2,
  X,
  ChevronDown,
  ChevronRight,
} from 'lucide-react';
import { useAuth } from '../auth/AuthProvider';
import { hasMinimumRole, HRIS_ROLES, getRoleLabel } from '../auth/roles';
import { clsx } from 'clsx';
import { getCatalogWorkspaceLaunch, getModulesCatalog, getTenantBranding, type ModuleCatalogItem } from '../api/hrisCoreClient';
import { httpClient } from '../api/httpClient';

type SidebarProps = {
  open: boolean;
  onClose: () => void;
  collapsed: boolean;
  onToggleCollapse: () => void;
};

// Nav item sent by a module via MODULE_NAV_UPDATE.
// type:'submenu' = collapsible group; type:'action' = leaf that triggers a modal/action in the module.
type ModuleNavItem = {
  id: string;
  label: string;
  icon?: string;
  type: 'submenu' | 'action';
  children?: ModuleNavItem[];
};

const navLinkClass = ({ isActive, collapsed }: { isActive: boolean; collapsed: boolean }) =>
  clsx(
    'flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors',
    collapsed && 'justify-center',
    isActive
      ? 'bg-brand-500/10 text-brand-600 dark:text-brand-400'
      : 'text-gray-700 hover:bg-gray-100 hover:text-gray-900 dark:text-gray-200 dark:hover:bg-gray-800 dark:hover:text-white'
  );

export const Sidebar: React.FC<SidebarProps> = ({ open, onClose, collapsed, onToggleCollapse }) => {
  const { user } = useAuth();
  const location = useLocation();
  const role = user?.effectiveRole ?? HRIS_ROLES.EMPLOYEE;
  const [brandName, setBrandName] = useState('HRIS Portal');
  const [logoPrimaryUri, setLogoPrimaryUri] = useState<string>('');
  const [catalogModules, setCatalogModules] = useState<ModuleCatalogItem[]>([]);

  // Nav items sent by active module — keyed by moduleId.
  const [moduleNavItems, setModuleNavItems] = useState<Record<string, ModuleNavItem[]>>({});
  // Tracks which level-1 submenu group is open within the module sub-nav.
  // Key: `${moduleId}:${itemId}` — allows independent state per module.
  const [openSubmenuId, setOpenSubmenuId] = useState<string | null>(null);

  // Real avatar URL relayed from the active module.
  const [moduleAvatarUrl, setModuleAvatarUrl] = useState<string | null>(null);

  const toAbsoluteLogoUrl = (value: string): string => {
    const raw = (value || '').trim();
    if (!raw) return '';
    if (raw.startsWith('http://') || raw.startsWith('https://')) return raw;
    if (raw.startsWith('/')) {
      const base = String(httpClient.defaults.baseURL || '').replace(/\/+$/, '');
      return `${base}${raw}`;
    }
    return raw;
  };

  useEffect(() => {
    let mounted = true;
    if (!user?.tenantId) return () => { mounted = false; };
    getTenantBranding(user.tenantId)
      .then((response) => {
        if (!mounted) return;
        setBrandName(response.branding?.brand_name || 'HRIS Portal');
        setLogoPrimaryUri(toAbsoluteLogoUrl(response.branding?.logo_primary_uri || ''));
      })
      .catch(() => {
        if (!mounted) return;
        setBrandName('HRIS Portal');
        setLogoPrimaryUri('');
      });
    return () => { mounted = false; };
  }, [user?.tenantId]);

  useEffect(() => {
    let mounted = true;
    getModulesCatalog()
      .then((response) => {
        if (!mounted) return;
        setCatalogModules(Array.isArray(response.modules) ? response.modules : []);
      })
      .catch(() => {
        if (!mounted) return;
        setCatalogModules([]);
      });
    return () => { mounted = false; };
  }, [user?.tenantId, role]);

  // Listen for module nav tree from ModuleFrame (relayed from MODULE_NAV_UPDATE).
  useEffect(() => {
    const handleNavUpdate = (event: Event) => {
      const detail = (event as CustomEvent<{ moduleId: string; navItems: ModuleNavItem[] } | null>).detail;
      if (!detail) {
        setModuleNavItems({});
        setOpenSubmenuId(null);
        return;
      }
      const { moduleId, navItems } = detail;
      if (!moduleId) return;
      setModuleNavItems((prev) => ({
        ...prev,
        [moduleId]: Array.isArray(navItems) ? navItems : [],
      }));
    };
    window.addEventListener('hris:module-nav-update', handleNavUpdate);
    return () => window.removeEventListener('hris:module-nav-update', handleNavUpdate);
  }, []);

  // Listen for real profile avatar from the active module.
  useEffect(() => {
    const handleUserProfile = (event: Event) => {
      const detail = (event as CustomEvent<{ avatarUrl: string | null } | null>).detail;
      setModuleAvatarUrl(detail?.avatarUrl ?? null);
    };
    window.addEventListener('hris:module-user-profile', handleUserProfile);
    return () => window.removeEventListener('hris:module-user-profile', handleUserProfile);
  }, []);

  const isEmployee = !hasMinimumRole(role, HRIS_ROLES.LINE_MANAGER);

  const iconForModule = (moduleId: string) => {
    const n = moduleId.toLowerCase();
    if (n === 'srms') return Users;
    if (n === 'eappraisal') return ClipboardList;
    if (n === 'eleave') return CalendarDays;
    return Layers;
  };

  // Employee-facing labels for each module — shown in the Self Service section.
  // SRMS is labelled "My Profile" because it IS the employee profile experience;
  // the static HRIS /profile route is hidden for employees in favour of this.
  const EMPLOYEE_LABELS: Record<string, string> = {
    srms: 'My Profile',
    eleave: 'My Leave',
    eappraisal: 'My Appraisal',
  };

  const getModuleLabelForRole = (m: ModuleCatalogItem): string => {
    const id = m.id.toLowerCase();
    if (isEmployee) return EMPLOYEE_LABELS[id] ?? `My ${m.label}`;
    if (role === HRIS_ROLES.LINE_MANAGER && id === 'srms') return 'Team Directory';
    return m.label;
  };

  // Derive the path for a module that is appropriate for the current role.
  // Priority order for employees:
  //   1. ui.self_path — a dedicated employee self-service route configured in the catalog
  //   2. The module's native workspace iframe (/modules/:id/native)
  //   3. ui.path — the general path (last resort, may be HR-facing)
  const getModulePathForRole = (m: ModuleCatalogItem): string => {
    const id = m.id.toLowerCase();
    if (isEmployee) {
      if (m.ui?.self_path) return String(m.ui.self_path);
      // Default employees to the module workspace so they see the module iframed.
      // Each module renders a role-appropriate view based on the auth relay claims.
      return `/modules/${encodeURIComponent(id)}/native`;
    }
    if (role === HRIS_ROLES.LINE_MANAGER && id === 'srms') return '/employees/team';
    return String(m.ui?.path ?? `/modules/${encodeURIComponent(id)}/native`);
  };

  // Modules to show in the sidebar.
  // For employees: show all enabled modules that declare self-service capability
  //   OR are simply enabled — the module itself controls what employees see after auth.
  //   We do NOT gate on m.visible here for employees because `visible` is typically a
  //   signal for the HR-level sidebar view, not the employee self-service view.
  // For managers / admins: existing behaviour (enabled + visible + ui.path).
  const visibleModules = catalogModules
    .filter((m) => {
      if (!m.enabled) return false;
      if (isEmployee) {
        // Include if the module explicitly declares self-service capability,
        // OR if it is visible (catalog explicitly says employees can see it).
        const hasSelfService = m.capabilities?.self_service_view !== false;
        return hasSelfService || m.visible;
      }
      return m.visible && Boolean(m.ui?.path);
    })
    .map((m) => ({
      ...m,
      label: getModuleLabelForRole(m),
      path: getModulePathForRole(m),
      icon: iconForModule(m.id),
      workspaceLaunch: getCatalogWorkspaceLaunch([m], m.id),
    }));

  // Detect which module workspace is currently open (/modules/:id/native).
  const workspaceMatch = location.pathname.match(/^\/modules\/([^/]+)\/native/);
  const activeWorkspaceModuleId = workspaceMatch ? workspaceMatch[1].toLowerCase() : null;

  // Send TRIGGER_ACTION to the target module iframe, then shift keyboard focus
  // into the iframe so that modal interactions (Tab, Escape, etc.) work immediately
  // without the user having to click inside the iframe first.
  const triggerModuleAction = (moduleId: string, actionId: string) => {
    window.dispatchEvent(
      new CustomEvent(`hris:module-trigger-action-${moduleId}`, {
        detail: { actionId },
      }),
    );
    // Small delay so the postMessage is processed and the modal is rendered before focus.
    setTimeout(() => {
      const iframe = document.querySelector<HTMLIFrameElement>('iframe[title]');
      iframe?.focus();
    }, 150);
  };

  const toggleSubmenu = (key: string) =>
    setOpenSubmenuId((prev) => (prev === key ? null : key));

  // ── Module sub-nav renderer ──────────────────────────────────────────────────
  // Renders the SRMS (or other module) nav tree inside the HRIS sidebar.
  // Level-1 items with children are collapsible groups; leaf action items are buttons.
  const renderModuleSubNav = (moduleId: string) => {
    const items = moduleNavItems[moduleId];
    if (!items || !items.length || collapsed) return null;

    return (
      <div className="mt-1 overflow-hidden rounded-lg border border-gray-200/60 bg-gray-50/80 dark:border-gray-700/60 dark:bg-gray-800/60">
        {items.map((item) => {
          const submenuKey = `${moduleId}:${item.id}`;
          const isGroupOpen = openSubmenuId === submenuKey;

          if (item.type === 'submenu' && item.children?.length) {
            return (
              <div key={item.id}>
                {/* Group header */}
                <button
                  type="button"
                  onClick={() => toggleSubmenu(submenuKey)}
                  className={clsx(
                    'flex w-full items-center gap-2 px-3 py-2 text-left text-sm font-semibold transition-colors',
                    'text-gray-800 dark:text-gray-100',
                    'hover:bg-brand-500/10 hover:text-brand-700 dark:hover:text-brand-300',
                    isGroupOpen && 'text-brand-700 dark:text-brand-300',
                  )}
                >
                  {item.icon && <span className="text-base leading-none">{item.icon}</span>}
                  <span className="flex-1 truncate">{item.label}</span>
                  <ChevronDown
                    className={clsx(
                      'h-3.5 w-3.5 shrink-0 transition-transform duration-200',
                      isGroupOpen && 'rotate-180',
                    )}
                  />
                </button>

                {/* Children — shown when group is open */}
                {isGroupOpen && (
                  <div className="border-t border-gray-200/60 bg-white/60 pb-1 dark:border-gray-700/60 dark:bg-gray-900/40">
                    {item.children.map((child) => (
                      <button
                        key={child.id}
                        type="button"
                        onClick={() => {
                          triggerModuleAction(moduleId, child.id);
                          onClose();
                        }}
                        className={clsx(
                          'flex w-full items-center gap-2 pl-8 pr-3 py-1.5 text-left text-xs font-medium transition-colors',
                          'text-gray-700 dark:text-gray-200',
                          'hover:bg-brand-500/10 hover:text-brand-700 dark:hover:bg-brand-500/10 dark:hover:text-brand-300',
                          'focus:outline-none focus-visible:ring-1 focus-visible:ring-brand-500',
                        )}
                      >
                        <ChevronRight className="h-2.5 w-2.5 shrink-0 text-gray-400 dark:text-gray-500" />
                        {child.label}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            );
          }

          // Direct action item (no children)
          return (
            <button
              key={item.id}
              type="button"
              onClick={() => {
                triggerModuleAction(moduleId, item.id);
                onClose();
              }}
              className={clsx(
                'flex w-full items-center gap-2 px-3 py-2 text-left text-sm font-semibold transition-colors',
                'text-gray-800 dark:text-gray-100',
                'hover:bg-brand-500/10 hover:text-brand-700 dark:hover:text-brand-300',
              )}
            >
              {item.icon && <span className="text-base leading-none">{item.icon}</span>}
              <span className="truncate">{item.label}</span>
            </button>
          );
        })}
      </div>
    );
  };

  const renderModuleEntry = (module: typeof visibleModules[0]) => {
    const isWorkspaceActive = activeWorkspaceModuleId === module.id;
    const hasSubNav = (moduleNavItems[module.id] ?? []).length > 0;

    return (
      <div key={module.id} className="space-y-1">
        <div className={clsx('flex items-center gap-0.5', collapsed && 'justify-center')}>
          <NavLink
            to={module.path}
            className={({ isActive }) =>
              clsx(navLinkClass({ isActive: isActive || isWorkspaceActive, collapsed }), !collapsed && 'flex-1 min-w-0')
            }
            onClick={onClose}
            title={module.label}
          >
            <module.icon className="h-4 w-4 shrink-0" />
            {!collapsed && <span className="truncate">{module.label}</span>}
          </NavLink>

          {/* Workspace launch icon — only when there's no sub-nav to expand */}
          {!collapsed && !hasSubNav && module.workspaceLaunch && (
            <NavLink
              to={module.workspaceLaunch.path}
              onClick={(e) => e.stopPropagation()}
              className="shrink-0 rounded-lg p-2 text-gray-400 hover:bg-gray-100 hover:text-brand-600 dark:hover:bg-gray-800"
              title={`Open ${module.label} workspace`}
              aria-label={`Open ${module.label} workspace`}
            >
              <Layers className="h-4 w-4" />
            </NavLink>
          )}
        </div>

        {/* Module sub-nav tree — shown only when sidebar is expanded and module is active */}
        {!collapsed && isWorkspaceActive && renderModuleSubNav(module.id)}
      </div>
    );
  };

  return (
    <>
      {open && (
        <div className="fixed inset-0 z-40 bg-black/30 lg:hidden" onClick={onClose} />
      )}
      <aside
        className={clsx(
          'fixed inset-y-0 left-0 z-50 flex flex-col border-r border-gray-200 bg-white transition-all lg:static lg:translate-x-0 dark:border-gray-800 dark:bg-gray-900',
          collapsed ? 'w-20' : 'w-72',
          open ? 'translate-x-0' : '-translate-x-full'
        )}
      >
        {/* Brand header */}
        <div className="flex h-16 items-center justify-between border-b border-gray-200 px-4 dark:border-gray-800">
          <div className="flex items-center gap-2">
            {logoPrimaryUri ? (
              <img alt={brandName} className="h-8 w-8 rounded object-contain" src={logoPrimaryUri} />
            ) : (
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-500 text-xs font-bold text-white">
                HR
              </div>
            )}
            {!collapsed && (
              <span className="text-base font-semibold text-gray-900 dark:text-gray-100">{brandName}</span>
            )}
          </div>
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={onToggleCollapse}
              title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
              className="hidden rounded-lg p-1.5 text-gray-400 hover:bg-gray-100 hover:text-gray-700 dark:hover:bg-gray-800 dark:hover:text-gray-200 lg:inline-flex"
            >
              {collapsed
                ? <ChevronRight className="h-4 w-4" />
                : <X className="h-4 w-4 rotate-45" />}
            </button>
            <button
              onClick={onClose}
              className="rounded-lg p-1.5 text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 lg:hidden"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>

        {/* Nav */}
        <nav className="flex-1 space-y-0.5 overflow-y-auto px-3 py-4">
          {!collapsed && (
            <p className="mb-2 px-3 text-xs font-semibold uppercase tracking-wider text-gray-400 dark:text-gray-500">
              Overview
            </p>
          )}
          <NavLink
            to="/"
            end
            className={({ isActive }) => navLinkClass({ isActive, collapsed })}
            onClick={onClose}
            title="Dashboard"
          >
            <LayoutDashboard className="h-4 w-4 shrink-0" />
            {!collapsed && 'Dashboard'}
          </NavLink>

          {hasMinimumRole(role, HRIS_ROLES.LINE_MANAGER) && (
            <>
              {!collapsed && (
                <p className="mb-2 mt-6 px-3 text-xs font-semibold uppercase tracking-wider text-gray-400 dark:text-gray-500">
                  HR Modules
                </p>
              )}
              {visibleModules.map(renderModuleEntry)}
            </>
          )}

          {!hasMinimumRole(role, HRIS_ROLES.LINE_MANAGER) && (
            <>
              {!collapsed && (
                <p className="mb-2 mt-6 px-3 text-xs font-semibold uppercase tracking-wider text-gray-400 dark:text-gray-500">
                  Self Service
                </p>
              )}
              {visibleModules.map(renderModuleEntry)}
            </>
          )}

          {hasMinimumRole(role, HRIS_ROLES.HR_MANAGER) && (
            <>
              {!collapsed && (
                <p className="mb-2 mt-6 px-3 text-xs font-semibold uppercase tracking-wider text-gray-400 dark:text-gray-500">
                  Reports
                </p>
              )}
              <NavLink
                to="/reports"
                className={({ isActive }) => navLinkClass({ isActive, collapsed })}
                onClick={onClose}
                title="Reports"
              >
                <FileText className="h-4 w-4 shrink-0" />
                {!collapsed && 'Reports'}
              </NavLink>
            </>
          )}

          {hasMinimumRole(role, HRIS_ROLES.TENANT_ADMIN) && (
            <>
              {!collapsed && (
                <p className="mb-2 mt-6 px-3 text-xs font-semibold uppercase tracking-wider text-gray-400 dark:text-gray-500">
                  Administration
                </p>
              )}
              <NavLink
                to="/admin/roles"
                className={({ isActive }) => navLinkClass({ isActive, collapsed })}
                onClick={onClose}
                title="Roles & Permissions"
              >
                <Shield className="h-4 w-4 shrink-0" />
                {!collapsed && 'Roles & Permissions'}
              </NavLink>
              <NavLink
                to="/admin/tenants"
                className={({ isActive }) => navLinkClass({ isActive, collapsed })}
                onClick={onClose}
                title="Tenant Management"
              >
                <Building2 className="h-4 w-4 shrink-0" />
                {!collapsed && 'Tenant Management'}
              </NavLink>
            </>
          )}
        </nav>

        {/* User card at bottom — clickable to view profile when a module is active */}
        <div className="border-t border-gray-200 p-4 dark:border-gray-800">
          <div
            role={activeWorkspaceModuleId ? 'button' : undefined}
            tabIndex={activeWorkspaceModuleId ? 0 : undefined}
            title={activeWorkspaceModuleId ? 'View my profile' : undefined}
            onClick={() => {
              if (activeWorkspaceModuleId) {
                window.dispatchEvent(
                  new CustomEvent(`hris:module-trigger-action-${activeWorkspaceModuleId}`, {
                    detail: { actionId: 'profile:view' },
                  }),
                );
              }
            }}
            onKeyDown={(e) => {
              if (activeWorkspaceModuleId && (e.key === 'Enter' || e.key === ' ')) {
                window.dispatchEvent(
                  new CustomEvent(`hris:module-trigger-action-${activeWorkspaceModuleId}`, {
                    detail: { actionId: 'profile:view' },
                  }),
                );
              }
            }}
            className={clsx(
              'rounded-lg bg-gray-50 p-3 dark:bg-gray-800',
              activeWorkspaceModuleId && 'cursor-pointer transition-colors hover:bg-gray-100 dark:hover:bg-gray-700',
            )}
          >
            {!collapsed ? (
              <div className="flex items-center gap-3">
                {moduleAvatarUrl ? (
                  <img
                    src={moduleAvatarUrl}
                    alt={user?.username ?? 'User'}
                    className="h-9 w-9 shrink-0 rounded-full object-cover ring-2 ring-brand-500/30"
                  />
                ) : (
                  <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-brand-500 text-sm font-bold text-white">
                    {user?.username?.charAt(0)?.toUpperCase() ?? 'U'}
                  </div>
                )}
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-semibold text-gray-900 dark:text-gray-100">
                    {user?.username}
                  </p>
                  <p className="text-xs text-gray-500 dark:text-gray-400">{getRoleLabel(role)}</p>
                </div>
              </div>
            ) : (
              <div className="flex justify-center">
                {moduleAvatarUrl ? (
                  <img
                    src={moduleAvatarUrl}
                    alt={user?.username ?? 'User'}
                    className="h-9 w-9 rounded-full object-cover ring-2 ring-brand-500/30"
                  />
                ) : (
                  <div className="flex h-9 w-9 items-center justify-center rounded-full bg-brand-500 text-sm font-bold text-white">
                    {user?.username?.charAt(0)?.toUpperCase() ?? 'U'}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </aside>
    </>
  );
};
