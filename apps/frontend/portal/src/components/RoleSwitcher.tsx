import React from 'react';
import { useAuth } from '../auth/AuthProvider';
import { HRIS_ROLES, getRoleLabel, type HrisRole } from '../auth/roles';
import { ShieldCheck, ChevronDown } from 'lucide-react';

const ALL_ROLES: HrisRole[] = [
  HRIS_ROLES.SUPER_ADMIN,
  HRIS_ROLES.TENANT_ADMIN,
  HRIS_ROLES.HR_MANAGER,
  HRIS_ROLES.LINE_MANAGER,
  HRIS_ROLES.EMPLOYEE,
];

const ROLE_DESCRIPTIONS: Record<HrisRole, string> = {
  [HRIS_ROLES.SUPER_ADMIN]: 'Full system access, all tenants & modules',
  [HRIS_ROLES.TENANT_ADMIN]: 'Full tenant access, org structure & modules',
  [HRIS_ROLES.HR_MANAGER]: 'Staff records, appraisals, leaves, reports',
  [HRIS_ROLES.LINE_MANAGER]: 'Team members, approvals, team reviews',
  [HRIS_ROLES.EMPLOYEE]: 'Self-service: my profile, leave & appraisals',
};

const ROLE_COLORS: Record<HrisRole, string> = {
  [HRIS_ROLES.SUPER_ADMIN]: 'bg-red-100 text-red-700 border-red-200',
  [HRIS_ROLES.TENANT_ADMIN]: 'bg-orange-100 text-orange-700 border-orange-200',
  [HRIS_ROLES.HR_MANAGER]: 'bg-blue-100 text-blue-700 border-blue-200',
  [HRIS_ROLES.LINE_MANAGER]: 'bg-purple-100 text-purple-700 border-purple-200',
  [HRIS_ROLES.EMPLOYEE]: 'bg-green-100 text-green-700 border-green-200',
};

export const RoleSwitcher: React.FC = () => {
  const { user, switchRole, isDevMode } = useAuth();
  const [open, setOpen] = React.useState(false);
  const ref = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, []);

  if (!isDevMode || !switchRole || !user) return null;

  const currentRole = user.effectiveRole;

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen(!open)}
        className={`flex items-center gap-2 rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors ${ROLE_COLORS[currentRole]}`}
      >
        <ShieldCheck className="h-3.5 w-3.5" />
        <span>{getRoleLabel(currentRole)}</span>
        <ChevronDown className={`h-3 w-3 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>

      {open && (
        <div className="absolute right-0 top-full z-50 mt-2 w-80 rounded-xl border border-gray-200 bg-white shadow-xl">
          <div className="border-b border-gray-100 px-4 py-3">
            <p className="text-xs font-semibold uppercase tracking-wider text-gray-400">Dev Mode - Switch Role</p>
            <p className="mt-0.5 text-xs text-gray-500">See how each role experiences the portal</p>
          </div>
          <div className="p-2">
            {ALL_ROLES.map(role => {
              const isActive = role === currentRole;
              return (
                <button
                  key={role}
                  onClick={() => { switchRole(role); setOpen(false); }}
                  className={`flex w-full items-start gap-3 rounded-lg px-3 py-2.5 text-left transition-colors ${
                    isActive ? 'bg-brand-500/10' : 'hover:bg-gray-50'
                  }`}
                >
                  <div className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border-2 ${
                    isActive ? 'border-brand-500 bg-brand-500' : 'border-gray-300'
                  }`}>
                    {isActive && <div className="h-2 w-2 rounded-full bg-white" />}
                  </div>
                  <div className="min-w-0">
                    <p className={`text-sm font-medium ${isActive ? 'text-brand-600' : 'text-gray-900'}`}>
                      {getRoleLabel(role)}
                    </p>
                    <p className="text-xs text-gray-500">{ROLE_DESCRIPTIONS[role]}</p>
                  </div>
                </button>
              );
            })}
          </div>
          <div className="border-t border-gray-100 px-4 py-2">
            <p className="text-[10px] text-gray-400">Logged in as <span className="font-medium">{user.username}</span> &middot; {user.email}</p>
          </div>
        </div>
      )}
    </div>
  );
};
