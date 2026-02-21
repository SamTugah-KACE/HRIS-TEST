export const HRIS_ROLES = {
  SUPER_ADMIN: 'hris:super_admin',
  TENANT_ADMIN: 'hris:tenant_admin',
  HR_MANAGER: 'hris:hr_manager',
  LINE_MANAGER: 'hris:line_manager',
  EMPLOYEE: 'hris:employee',
} as const;

export type HrisRole = (typeof HRIS_ROLES)[keyof typeof HRIS_ROLES];

const ROLE_HIERARCHY: HrisRole[] = [
  HRIS_ROLES.SUPER_ADMIN,
  HRIS_ROLES.TENANT_ADMIN,
  HRIS_ROLES.HR_MANAGER,
  HRIS_ROLES.LINE_MANAGER,
  HRIS_ROLES.EMPLOYEE,
];

export function resolveEffectiveRole(roles: string[]): HrisRole {
  for (const role of ROLE_HIERARCHY) {
    if (roles.includes(role)) return role;
  }
  return HRIS_ROLES.EMPLOYEE;
}

export function getRoleLabel(role: string): string {
  const labels: Record<string, string> = {
    [HRIS_ROLES.SUPER_ADMIN]: 'Super Admin',
    [HRIS_ROLES.TENANT_ADMIN]: 'Tenant Admin',
    [HRIS_ROLES.HR_MANAGER]: 'HR Manager',
    [HRIS_ROLES.LINE_MANAGER]: 'Line Manager',
    [HRIS_ROLES.EMPLOYEE]: 'Employee',
  };
  return labels[role] ?? role;
}

export function hasMinimumRole(userRole: HrisRole, requiredRole: HrisRole): boolean {
  return ROLE_HIERARCHY.indexOf(userRole) <= ROLE_HIERARCHY.indexOf(requiredRole);
}

export function isAdminRole(role: HrisRole): boolean {
  return role === HRIS_ROLES.SUPER_ADMIN || role === HRIS_ROLES.TENANT_ADMIN;
}

export function isManagerRole(role: HrisRole): boolean {
  return (
    role === HRIS_ROLES.SUPER_ADMIN ||
    role === HRIS_ROLES.TENANT_ADMIN ||
    role === HRIS_ROLES.HR_MANAGER ||
    role === HRIS_ROLES.LINE_MANAGER
  );
}
