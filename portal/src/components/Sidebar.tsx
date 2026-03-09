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
};

const navLinkClass = ({ isActive }: { isActive: boolean }) =>
  clsx(
    'flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors',
    isActive
      ? 'bg-brand-500/10 text-brand-500'
      : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'
  );

export const Sidebar: React.FC<SidebarProps> = ({ open, onClose }) => {
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
          'fixed inset-y-0 left-0 z-50 flex w-64 flex-col border-r border-gray-200 bg-white transition-transform lg:static lg:translate-x-0',
          open ? 'translate-x-0' : '-translate-x-full'
        )}
      >
        <div className="flex h-16 items-center justify-between border-b border-gray-200 px-4">
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
            <span className="text-base font-semibold text-gray-900">{brandName}</span>
          </div>
          <button onClick={onClose} className="rounded-lg p-1 text-gray-400 hover:bg-gray-100 lg:hidden">
            <X className="h-5 w-5" />
          </button>
        </div>

        <nav className="flex-1 space-y-1 overflow-y-auto px-3 py-4">
          <p className="mb-2 px-3 text-xs font-semibold uppercase tracking-wider text-gray-400">Overview</p>
          <NavLink to="/" end className={navLinkClass} onClick={onClose}>
            <LayoutDashboard className="h-4 w-4" /> Dashboard
          </NavLink>

          {hasMinimumRole(role, HRIS_ROLES.LINE_MANAGER) && (
            <>
              <p className="mb-2 mt-6 px-3 text-xs font-semibold uppercase tracking-wider text-gray-400">HR Modules</p>
              {(visibleModules.length > 0 ? visibleModules : [
                { id: 'srms', label: 'Staff Records', path: '/employees', icon: Users },
                { id: 'eappraisal', label: 'Performance Appraisal', path: '/modules/appraisal', icon: ClipboardList },
                { id: 'eleave', label: 'Leave Management', path: '/modules/leave', icon: CalendarDays },
              ]).map((module) => (
                <NavLink key={module.id} to={module.path} className={navLinkClass} onClick={onClose}>
                  <module.icon className="h-4 w-4" /> {module.label}
                </NavLink>
              ))}
            </>
          )}

          {!hasMinimumRole(role, HRIS_ROLES.LINE_MANAGER) && (
            <>
              <p className="mb-2 mt-6 px-3 text-xs font-semibold uppercase tracking-wider text-gray-400">Self Service</p>
              <NavLink to="/profile" className={navLinkClass} onClick={onClose}>
                <Users className="h-4 w-4" /> My Profile
              </NavLink>
              {(visibleModules.filter((module) => module.id !== 'srms').length > 0
                ? visibleModules.filter((module) => module.id !== 'srms')
                : [
                    { id: 'eappraisal', label: 'My Appraisals', path: '/modules/appraisal', icon: ClipboardList },
                    { id: 'eleave', label: 'My Leave', path: '/modules/leave', icon: CalendarDays },
                  ]
              ).map((module) => (
                <NavLink key={module.id} to={module.path} className={navLinkClass} onClick={onClose}>
                  <module.icon className="h-4 w-4" /> {module.label}
                </NavLink>
              ))}
            </>
          )}

          {hasMinimumRole(role, HRIS_ROLES.HR_MANAGER) && (
            <>
              <p className="mb-2 mt-6 px-3 text-xs font-semibold uppercase tracking-wider text-gray-400">Reports</p>
              <NavLink to="/reports" className={navLinkClass} onClick={onClose}>
                <FileText className="h-4 w-4" /> Reports
              </NavLink>
            </>
          )}

          {hasMinimumRole(role, HRIS_ROLES.TENANT_ADMIN) && (
            <>
              <p className="mb-2 mt-6 px-3 text-xs font-semibold uppercase tracking-wider text-gray-400">Administration</p>
              <NavLink to="/admin/roles" className={navLinkClass} onClick={onClose}>
                <Shield className="h-4 w-4" /> Roles & Permissions
              </NavLink>
              <NavLink to="/admin/tenants" className={navLinkClass} onClick={onClose}>
                <Building2 className="h-4 w-4" /> Tenant Management
              </NavLink>
            </>
          )}
        </nav>

        <div className="border-t border-gray-200 p-4">
          <div className="rounded-lg bg-gray-50 p-3">
            <p className="text-sm font-medium text-gray-900">{user?.username}</p>
            <p className="text-xs text-gray-500">{getRoleLabel(role)}</p>
          </div>
        </div>
      </aside>
    </>
  );
};
