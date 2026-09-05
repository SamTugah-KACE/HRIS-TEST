import axios from 'axios';

const baseURL = import.meta.env.VITE_HRIS_CORE_API_BASE_URL as string;
const authMode = import.meta.env.VITE_AUTH_MODE as string || 'dev';
const csrfHeaderName = (import.meta.env.VITE_AUTH_CSRF_HEADER_NAME as string) || 'X-CSRF-Token';
const devDefaultEmployeeId = (import.meta.env.VITE_DEV_DEFAULT_EMPLOYEE_ID as string) || 'e001';

function getCookieValue(cookieName: string): string | null {
  if (typeof document === 'undefined') return null;
  const escapedName = cookieName.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const match = document.cookie.match(new RegExp(`(?:^|; )${escapedName}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : null;
}

export const httpClient = axios.create({
  baseURL,
  timeout: 15000,
  withCredentials: true,
});

let refreshPromise: Promise<void> | null = null;

export function refreshSsoSession(): Promise<void> {
  if (refreshPromise) return refreshPromise;
  const csrfToken = getCookieValue('hris_csrf_token');
  refreshPromise = axios.post(
    `${baseURL}/auth/sso/refresh`,
    undefined,
    {
      withCredentials: true,
      headers: csrfToken ? { [csrfHeaderName]: csrfToken } : {},
    },
  ).then(() => undefined).finally(() => {
    refreshPromise = null;
  });
  return refreshPromise;
}

httpClient.interceptors.request.use(async (config) => {
  if ((config.method || 'get').toLowerCase() !== 'get') {
    const csrfToken = getCookieValue('hris_csrf_token');
    if (csrfToken) {
      config.headers = config.headers ?? {};
      config.headers[csrfHeaderName] = csrfToken;
    }
  }

  if (authMode === 'dev') {
    config.headers = config.headers ?? {};
    const storedRole = localStorage.getItem('hris_dev_role');
    if (storedRole) {
      config.headers['X-Debug-Roles'] = storedRole;
    }
    const DEV_USER_NAMES: Record<string, string> = {
      'hris:super_admin': 'super.admin',
      'hris:tenant_admin': 'tenant.admin',
      'hris:hr_manager': 'hr.manager',
      'hris:line_manager': 'line.manager',
      'hris:employee': 'employee',
    };
    if (storedRole && DEV_USER_NAMES[storedRole]) {
      config.headers['X-Debug-Username'] = DEV_USER_NAMES[storedRole];
    }
    const debugEmployeeId = localStorage.getItem('hris_dev_employee_id') || devDefaultEmployeeId;
    config.headers['X-Debug-Employee-Id'] = debugEmployeeId;
    return config;
  }
  return config;
}, (error) => Promise.reject(error));

httpClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error?.config;
    const statusCode = error?.response?.status;
    const isSsoMode = authMode === 'keycloak';
    const isUnauthenticated = statusCode === 401;
    const isRefreshCall = typeof originalRequest?.url === 'string' && originalRequest.url.includes('/auth/sso/refresh');
    if (!isSsoMode || !isUnauthenticated || !originalRequest || isRefreshCall || originalRequest.__isRetryRequest) {
      return Promise.reject(error);
    }

    originalRequest.__isRetryRequest = true;
    try {
      await refreshSsoSession();
      return httpClient(originalRequest);
    } catch (refreshError) {
      return Promise.reject(refreshError);
    }
  },
);
