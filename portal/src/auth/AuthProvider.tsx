import React, { createContext, useContext, useEffect, useState, ReactNode, useCallback } from 'react';
import axios from 'axios';
import { resolveEffectiveRole, type HrisRole, HRIS_ROLES } from './roles';

const ENTERPRISE_PRIMARY_LOGO_URL = new URL('../../hris_enterprise_primary_logo.png', import.meta.url).href;
const AUTH_MODE = import.meta.env.VITE_AUTH_MODE as string || 'dev';
const HRIS_CORE_API_BASE_URL = import.meta.env.VITE_HRIS_CORE_API_BASE_URL as string;
const AUTH_CSRF_HEADER_NAME = (import.meta.env.VITE_AUTH_CSRF_HEADER_NAME as string) || 'X-CSRF-Token';
const DEV_REQUIRE_LOGIN = (import.meta.env.VITE_DEV_REQUIRE_LOGIN as string || 'false').toLowerCase() === 'true';
const DEV_DEFAULT_TENANT_ID = (import.meta.env.VITE_DEV_DEFAULT_TENANT_ID as string) || '11111111-1111-1111-1111-111111111111';

export type AuthUser = {
  sub: string;
  username: string;
  email?: string;
  tenantId: string;
  roles: string[];
  effectiveRole: HrisRole;
};

type AuthContextValue = {
  initialized: boolean;
  authenticated: boolean;
  user: AuthUser | null;
  logout: () => void;
  switchRole?: (role: HrisRole) => void;
  isDevMode: boolean;
};

type SsoSessionResponse = {
  authenticated: boolean;
  sub: string;
  username: string;
  email?: string;
  tenant_id: string;
  roles: string[];
  effective_role: HrisRole;
};

type SsoLogoutResponse = {
  logout_url?: string;
};

const authApi = axios.create({
  baseURL: HRIS_CORE_API_BASE_URL,
  timeout: 15000,
  withCredentials: true,
});

function getCookieValue(cookieName: string): string | null {
  if (typeof document === 'undefined') return null;
  const escapedName = cookieName.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const match = document.cookie.match(new RegExp(`(?:^|; )${escapedName}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : null;
}

authApi.interceptors.request.use((config) => {
  if ((config.method || 'get').toLowerCase() !== 'get') {
    const csrfToken = getCookieValue('hris_csrf_token');
    if (csrfToken) {
      config.headers = config.headers ?? {};
      config.headers[AUTH_CSRF_HEADER_NAME] = csrfToken;
    }
  }
  return config;
});

const AuthContext = createContext<AuthContextValue | undefined>(undefined);
const DEV_ROLE_STORAGE_KEY = 'hris_dev_role';

const DEV_USER_PROFILES: Record<HrisRole, { username: string; email: string }> = {
  [HRIS_ROLES.SUPER_ADMIN]: { username: 'super.admin', email: 'super.admin@hris.local' },
  [HRIS_ROLES.TENANT_ADMIN]: { username: 'tenant.admin', email: 'tenant.admin@hris.local' },
  [HRIS_ROLES.HR_MANAGER]: { username: 'hr.manager', email: 'hr.manager@hris.local' },
  [HRIS_ROLES.LINE_MANAGER]: { username: 'line.manager', email: 'line.manager@hris.local' },
  [HRIS_ROLES.EMPLOYEE]: { username: 'employee', email: 'employee@hris.local' },
};

export const useAuth = (): AuthContextValue => {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
};

function buildDevUser(role: HrisRole): AuthUser {
  const profile = DEV_USER_PROFILES[role];
  return {
    sub: `dev-${role}`,
    username: profile.username,
    email: profile.email,
    tenantId: DEV_DEFAULT_TENANT_ID,
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

function mapSessionToAuthUser(session: SsoSessionResponse): AuthUser {
  return {
    sub: session.sub,
    username: session.username,
    email: session.email,
    tenantId: session.tenant_id,
    roles: session.roles ?? [],
    effectiveRole: session.effective_role ?? resolveEffectiveRole(session.roles ?? []),
  };
}

function readAuthErrorFromQuery(): string | null {
  if (typeof window === 'undefined') return null;
  const params = new URLSearchParams(window.location.search);
  const raw = params.get('auth_error');
  if (!raw) return null;
  const normalized = raw.toLowerCase();
  if (normalized.includes('state')) return 'Your sign-in session expired. Please try again.';
  if (normalized.includes('token')) return 'Authentication token exchange failed. Please sign in again.';
  if (normalized.includes('missing_code_or_state')) return 'Sign-in was interrupted. Please continue with SSO again.';
  return 'Sign-in could not be completed. Please try again.';
}

export const AuthProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [initialized, setInitialized] = useState(false);
  const [authenticated, setAuthenticated] = useState(false);
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loginBusy, setLoginBusy] = useState(false);
  const [loginError, setLoginError] = useState<string | null>(null);
  const [selectedDevRole, setSelectedDevRole] = useState<HrisRole>(getStoredDevRole());

  const switchRole = useCallback((role: HrisRole) => {
    localStorage.setItem(DEV_ROLE_STORAGE_KEY, role);
    setUser(buildDevUser(role));
  }, []);

  const bootstrapSsoSession = useCallback(async () => {
    try {
      const response = await authApi.get<SsoSessionResponse>('/auth/sso/session');
      setUser(mapSessionToAuthUser(response.data));
      setAuthenticated(true);
    } catch {
      setUser(null);
      setAuthenticated(false);
    } finally {
      setInitialized(true);
    }
  }, []);

  useEffect(() => {
    const authError = readAuthErrorFromQuery();
    if (authError) {
      setLoginError(authError);
      const currentUrl = new URL(window.location.href);
      currentUrl.searchParams.delete('auth_error');
      window.history.replaceState({}, '', currentUrl.toString());
    }
    if (AUTH_MODE === 'dev') {
      if (DEV_REQUIRE_LOGIN) {
        setAuthenticated(false);
        setUser(null);
      } else {
        const role = getStoredDevRole();
        setUser(buildDevUser(role));
        setAuthenticated(true);
      }
      setInitialized(true);
      return;
    }

    void bootstrapSsoSession();
  }, [bootstrapSsoSession]);

  useEffect(() => {
    if (AUTH_MODE !== 'keycloak' || !authenticated) return;
    const refreshInterval = window.setInterval(async () => {
      try {
        await authApi.post('/auth/sso/refresh');
      } catch {
        setAuthenticated(false);
        setUser(null);
      }
    }, 45_000);
    return () => window.clearInterval(refreshInterval);
  }, [authenticated]);

  const startSsoLogin = useCallback(() => {
    setLoginBusy(true);
    setLoginError(null);
    const nextPath = `${window.location.pathname}${window.location.search}`;
    const redirectUrl = `${HRIS_CORE_API_BASE_URL}/auth/sso/start?next=${encodeURIComponent(nextPath)}`;
    window.location.assign(redirectUrl);
  }, []);

  const startDevLogin = useCallback(() => {
    setLoginBusy(true);
    setLoginError(null);
    localStorage.setItem(DEV_ROLE_STORAGE_KEY, selectedDevRole);
    setUser(buildDevUser(selectedDevRole));
    setAuthenticated(true);
    setLoginBusy(false);
  }, [selectedDevRole]);

  const logout = useCallback(() => {
    if (AUTH_MODE === 'dev') {
      setAuthenticated(false);
      setUser(null);
      return;
    }
    void authApi.post<SsoLogoutResponse>('/auth/sso/logout').then((response) => {
      const logoutUrl = response.data?.logout_url;
      setAuthenticated(false);
      setUser(null);
      if (logoutUrl) {
        window.location.assign(logoutUrl);
      }
    }).catch(() => {
      setAuthenticated(false);
      setUser(null);
    });
  }, []);

  if (!initialized) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="h-12 w-12 animate-spin rounded-full border-4 border-gray-300 border-t-brand-500" />
      </div>
    );
  }

  if (!authenticated) {
    if (AUTH_MODE === 'dev' && DEV_REQUIRE_LOGIN) {
      return (
        <div className="flex min-h-screen items-center justify-center bg-gray-50 px-4 py-10">
          <div className="w-full max-w-md rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
            <div className="mb-6 text-center">
              <img
                alt="HRIS Enterprise"
                className="mx-auto mb-4 h-12 w-auto"
                src={ENTERPRISE_PRIMARY_LOGO_URL}
              />
              <h1 className="text-2xl font-bold text-gray-900">HRIS Sign In</h1>
              <p className="mt-2 text-sm text-gray-600">
                Development login with native HRIS experience.
              </p>
            </div>
            {loginError ? (
              <p className="mb-4 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
                {loginError}
              </p>
            ) : null}
            <label className="mb-2 block text-sm font-medium text-gray-700" htmlFor="dev-role-select">
              Role
            </label>
            <select
              id="dev-role-select"
              value={selectedDevRole}
              onChange={(e) => setSelectedDevRole(e.target.value as HrisRole)}
              className="mb-4 w-full rounded-md border border-gray-300 px-3 py-2 text-sm text-gray-900 focus:border-brand-500 focus:outline-none"
            >
              {Object.values(HRIS_ROLES).map((role) => (
                <option key={role} value={role}>
                  {role}
                </option>
              ))}
            </select>
            <button
              type="button"
              onClick={startDevLogin}
              disabled={loginBusy}
              className="w-full rounded-md bg-brand-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {loginBusy ? 'Signing in...' : 'Continue'}
            </button>
          </div>
        </div>
      );
    }
    if (AUTH_MODE !== 'dev') {
      return (
        <div className="flex min-h-screen items-center justify-center bg-gray-50 px-4 py-10">
          <div className="w-full max-w-md rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
            <div className="mb-6 text-center">
              <img
                alt="HRIS Enterprise"
                className="mx-auto mb-4 h-12 w-auto"
                src={ENTERPRISE_PRIMARY_LOGO_URL}
              />
              <h1 className="text-2xl font-bold text-gray-900">HRIS Sign In</h1>
              <p className="mt-2 text-sm text-gray-600">
                Sign in securely with your organization identity provider.
              </p>
            </div>
            {loginError ? (
              <p className="mb-4 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
                {loginError}
              </p>
            ) : null}
            <button
              type="button"
              onClick={startSsoLogin}
              disabled={loginBusy}
              className="w-full rounded-md bg-brand-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {loginBusy ? 'Redirecting to Identity Provider...' : 'Continue with SSO'}
            </button>
          </div>
        </div>
      );
    }
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="h-12 w-12 animate-spin rounded-full border-4 border-gray-300 border-t-brand-500" />
      </div>
    );
  }

  return (
    <AuthContext.Provider
      value={{
        initialized,
        authenticated,
        user,
        logout,
        switchRole: AUTH_MODE === 'dev' ? switchRole : undefined,
        isDevMode: AUTH_MODE === 'dev',
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};
