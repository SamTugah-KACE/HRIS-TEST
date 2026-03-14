import React, { useEffect, useState } from 'react';
import { NavLink } from 'react-router-dom';
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
} from 'lucide-react';
import { useAuth } from '../auth/AuthProvider';
import { hasMinimumRole, HRIS_ROLES, getRoleLabel } from '../auth/roles';
import { clsx } from 'clsx';
import { getModulesCatalog, getTenantBranding, type ModuleCatalogItem } from '../api/hrisCoreClient';
import { httpClient } from '../api/httpClient';

type SidebarProps = {
  open: boolean;
  onClose: () => void;
  collapsed: boolean;
  onToggleCollapse: () => void;
};

const navLinkClass = ({ isActive, collapsed }: { isActive: boolean; collapsed: boolean }) =>
  clsx(
    'flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors',
    collapsed && 'justify-center',
    isActive
      ? 'bg-brand-500/10 text-brand-500'
      : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900 dark:text-gray-300 dark:hover:bg-gray-800 dark:hover:text-gray-100'
  );

export const Sidebar: React.FC<SidebarProps> = ({ open, onClose, collapsed, onToggleCollapse }) => {
  const { user } = useAuth();
  const role = user?.effectiveRole ?? HRIS_ROLES.EMPLOYEE;
  const [brandName, setBrandName] = useState('HRIS Portal');
  const [logoPrimaryUri, setLogoPrimaryUri] = useState<string>('');
  const [catalogModules, setCatalogModules] = useState<ModuleCatalogItem[]>([]);

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

  const iconForModule = (moduleId: string) => {
    const normalized = moduleId.toLowerCase();
    if (normalized === 'srms') return Users;
    if (normalized === 'eappraisal') return ClipboardList;
    if (normalized === 'eleave') return CalendarDays;
    return Layers;
  };

  const visibleModules = catalogModules
    .filter((module) => module.enabled && module.visible && module.ui?.path)
    .map((module) => ({
      ...module,
      path: String(module.ui.path),
      icon: iconForModule(module.id),
    }));

  return (
    <>
      {open && (
        <div className="fixed inset-0 z-40 bg-black/30 lg:hidden" onClick={onClose} />
      )}
      <aside
        className={clsx(
          'fixed inset-y-0 left-0 z-50 flex flex-col border-r border-gray-200 bg-white transition-all lg:static lg:translate-x-0 dark:border-gray-800 dark:bg-gray-900',
          collapsed ? 'w-20' : 'w-64',
          open ? 'translate-x-0' : '-translate-x-full'
        )}
      >
        <div className="flex h-16 items-center justify-between border-b border-gray-200 px-4 dark:border-gray-800">
          <div className="flex items-center gap-2">
            {logoPrimaryUri ? (
              <img
                alt={brandName}
                className="h-8 w-8 rounded object-contain"
                src={logoPrimaryUri}
              />
            ) : (
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-500 text-xs font-bold text-white">
                HR
              </div>
            )}
            {!collapsed && <span className="text-base font-semibold text-gray-900 dark:text-gray-100">{brandName}</span>}
          </div>
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={onToggleCollapse}
              title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
              className="hidden rounded-lg p-1 text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 lg:inline-flex"
            >
              {collapsed ? <Layers className="h-5 w-5" /> : <X className="h-5 w-5 rotate-45" />}
            </button>
            <button onClick={onClose} className="rounded-lg p-1 text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 lg:hidden">
              <X className="h-5 w-5" />
            </button>
          </div>
        </div>

        <nav className="flex-1 space-y-1 overflow-y-auto px-3 py-4">
          {!collapsed && <p className="mb-2 px-3 text-xs font-semibold uppercase tracking-wider text-gray-400 dark:text-gray-500">Overview</p>}
          <NavLink to="/" end className={({ isActive }) => navLinkClass({ isActive, collapsed })} onClick={onClose} title="Dashboard">
            <LayoutDashboard className="h-4 w-4" /> {!collapsed && 'Dashboard'}
          </NavLink>

          {hasMinimumRole(role, HRIS_ROLES.LINE_MANAGER) && (
            <>
              {!collapsed && <p className="mb-2 mt-6 px-3 text-xs font-semibold uppercase tracking-wider text-gray-400 dark:text-gray-500">HR Modules</p>}
              {(visibleModules.length > 0 ? visibleModules : [
                { id: 'srms', label: 'Staff Records', path: '/employees', icon: Users },
                { id: 'eappraisal', label: 'Performance Appraisal', path: '/modules/appraisal', icon: ClipboardList },
                { id: 'eleave', label: 'Leave Management', path: '/modules/leave', icon: CalendarDays },
              ]).map((module) => (
                <NavLink key={module.id} to={module.path} className={({ isActive }) => navLinkClass({ isActive, collapsed })} onClick={onClose} title={module.label}>
                  <module.icon className="h-4 w-4" /> {!collapsed && module.label}
                </NavLink>
              ))}
            </>
          )}

          {!hasMinimumRole(role, HRIS_ROLES.LINE_MANAGER) && (
            <>
              {!collapsed && <p className="mb-2 mt-6 px-3 text-xs font-semibold uppercase tracking-wider text-gray-400 dark:text-gray-500">Self Service</p>}
              <NavLink to="/profile" className={({ isActive }) => navLinkClass({ isActive, collapsed })} onClick={onClose} title="My Profile">
                <Users className="h-4 w-4" /> {!collapsed && 'My Profile'}
              </NavLink>
              {(visibleModules.filter((module) => module.id !== 'srms').length > 0
                ? visibleModules.filter((module) => module.id !== 'srms')
                : [
                    { id: 'eappraisal', label: 'My Appraisals', path: '/modules/appraisal', icon: ClipboardList },
                    { id: 'eleave', label: 'My Leave', path: '/modules/leave', icon: CalendarDays },
                  ]
              ).map((module) => (
                <NavLink key={module.id} to={module.path} className={({ isActive }) => navLinkClass({ isActive, collapsed })} onClick={onClose} title={module.label}>
                  <module.icon className="h-4 w-4" /> {!collapsed && module.label}
                </NavLink>
              ))}
            </>
          )}

          {hasMinimumRole(role, HRIS_ROLES.HR_MANAGER) && (
            <>
              {!collapsed && <p className="mb-2 mt-6 px-3 text-xs font-semibold uppercase tracking-wider text-gray-400 dark:text-gray-500">Reports</p>}
              <NavLink to="/reports" className={({ isActive }) => navLinkClass({ isActive, collapsed })} onClick={onClose} title="Reports">
                <FileText className="h-4 w-4" /> {!collapsed && 'Reports'}
              </NavLink>
            </>
          )}

          {hasMinimumRole(role, HRIS_ROLES.TENANT_ADMIN) && (
            <>
              {!collapsed && <p className="mb-2 mt-6 px-3 text-xs font-semibold uppercase tracking-wider text-gray-400 dark:text-gray-500">Administration</p>}
              <NavLink to="/admin/roles" className={({ isActive }) => navLinkClass({ isActive, collapsed })} onClick={onClose} title="Roles & Permissions">
                <Shield className="h-4 w-4" /> {!collapsed && 'Roles & Permissions'}
              </NavLink>
              <NavLink to="/admin/tenants" className={({ isActive }) => navLinkClass({ isActive, collapsed })} onClick={onClose} title="Tenant Management">
                <Building2 className="h-4 w-4" /> {!collapsed && 'Tenant Management'}
              </NavLink>
            </>
          )}
        </nav>

        <div className="border-t border-gray-200 p-4 dark:border-gray-800">
          <div className="rounded-lg bg-gray-50 p-3 dark:bg-gray-800">
            {!collapsed ? (
              <>
                <p className="text-sm font-medium text-gray-900 dark:text-gray-100">{user?.username}</p>
                <p className="text-xs text-gray-500 dark:text-gray-400">{getRoleLabel(role)}</p>
              </>
            ) : (
              <p className="text-center text-xs font-medium text-gray-500 dark:text-gray-300">
                {user?.username?.charAt(0)?.toUpperCase() ?? 'U'}
              </p>
            )}
          </div>
        </div>
      </aside>
    </>
  );
};
