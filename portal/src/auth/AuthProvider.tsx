import React, { createContext, useContext, useEffect, useState, ReactNode, useCallback } from 'react';
import { keycloak } from '../keycloak';
import { resolveEffectiveRole, type HrisRole, HRIS_ROLES } from './roles';

const AUTH_MODE = import.meta.env.VITE_AUTH_MODE as string || 'dev';

export type AuthUser = {
  sub: string;
  username: string;
  email?: string;
  tenantId: string;
  roles: string[];
  effectiveRole: HrisRole;
  token?: string;
};

type AuthContextValue = {
  initialized: boolean;
  authenticated: boolean;
  user: AuthUser | null;
  logout: () => void;
  switchRole?: (role: HrisRole) => void;
  isDevMode: boolean;
};

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export const useAuth = (): AuthContextValue => {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
};

const DEV_ROLE_STORAGE_KEY = 'hris_dev_role';

const DEV_USER_PROFILES: Record<HrisRole, { username: string; email: string }> = {
  [HRIS_ROLES.SUPER_ADMIN]: { username: 'super.admin', email: 'super.admin@hris.local' },
  [HRIS_ROLES.TENANT_ADMIN]: { username: 'tenant.admin', email: 'tenant.admin@hris.local' },
  [HRIS_ROLES.HR_MANAGER]: { username: 'hr.manager', email: 'hr.manager@hris.local' },
  [HRIS_ROLES.LINE_MANAGER]: { username: 'line.manager', email: 'line.manager@hris.local' },
  [HRIS_ROLES.EMPLOYEE]: { username: 'employee', email: 'employee@hris.local' },
};

function buildDevUser(role: HrisRole): AuthUser {
  const profile = DEV_USER_PROFILES[role];
  return {
    sub: `dev-${role}`,
    username: profile.username,
    email: profile.email,
    tenantId: '11111111-1111-1111-1111-111111111111',
    roles: [role],
    effectiveRole: role,
  };
}

function getStoredDevRole(): HrisRole {
  if (typeof window === 'undefined') return HRIS_ROLES.HR_MANAGER;
  const stored = localStorage.getItem(DEV_ROLE_STORAGE_KEY);
  if (stored && Object.values(HRIS_ROLES).includes(stored as HrisRole)) {
    return stored as HrisRole;
  }
  return HRIS_ROLES.HR_MANAGER;
}

export const AuthProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [initialized, setInitialized] = useState(false);
  const [authenticated, setAuthenticated] = useState(false);
  const [user, setUser] = useState<AuthUser | null>(null);

  const switchRole = useCallback((role: HrisRole) => {
    localStorage.setItem(DEV_ROLE_STORAGE_KEY, role);
    setUser(buildDevUser(role));
  }, []);

  useEffect(() => {
    if (AUTH_MODE === 'dev') {
      const role = getStoredDevRole();
      setUser(buildDevUser(role));
      setAuthenticated(true);
      setInitialized(true);
      return;
    }

    let isMounted = true;
    let refreshInterval: number | undefined;

    const init = async () => {
      try {
        const auth = await keycloak.init({
          onLoad: 'login-required',
          checkLoginIframe: false,
          pkceMethod: 'S256',
        });

        if (!isMounted) return;

        setAuthenticated(auth);
        if (auth && keycloak.tokenParsed) {
          const tp = keycloak.tokenParsed as Record<string, unknown>;
          const roles = (tp['roles'] as string[]) ?? (tp['realm_access'] as { roles?: string[] })?.roles ?? [];
          setUser({
            sub: (tp['sub'] as string) ?? '',
            username: (tp['preferred_username'] as string) ?? '',
            email: (tp['email'] as string) ?? undefined,
            tenantId: (tp['tenant_id'] as string) ?? '',
            roles,
            effectiveRole: resolveEffectiveRole(roles),
            token: keycloak.token ?? undefined,
          });
        }

        refreshInterval = window.setInterval(async () => {
          if (!keycloak.authenticated) return;
          try {
            const refreshed = await keycloak.updateToken(60);
            if (refreshed && keycloak.token && isMounted) {
              setUser(prev => prev ? { ...prev, token: keycloak.token! } : prev);
            }
          } catch {
            /* token refresh failed */
          }
        }, 30_000);

        if (isMounted) setInitialized(true);
      } catch {
        if (isMounted) {
          setInitialized(true);
          setAuthenticated(false);
        }
      }
    };

    void init();
    return () => {
      isMounted = false;
      if (refreshInterval !== undefined) window.clearInterval(refreshInterval);
    };
  }, []);

  const logout = useCallback(() => {
    if (AUTH_MODE === 'dev') {
      setAuthenticated(false);
      setUser(null);
      return;
    }
    keycloak.logout();
  }, []);

  if (!initialized) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="h-12 w-12 animate-spin rounded-full border-4 border-gray-300 border-t-brand-500" />
      </div>
    );
  }

  if (!authenticated) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="card text-center">
          <h2 className="text-lg font-semibold text-gray-900">Authentication Failed</h2>
          <p className="mt-2 text-sm text-gray-500">Please refresh the page to try again.</p>
        </div>
      </div>
    );
  }

  return (
    <AuthContext.Provider value={{ initialized, authenticated, user, logout, switchRole: AUTH_MODE === 'dev' ? switchRole : undefined, isDevMode: AUTH_MODE === 'dev' }}>
      {children}
    </AuthContext.Provider>
  );
};
