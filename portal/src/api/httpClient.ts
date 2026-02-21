import axios from 'axios';
import { keycloak } from '../keycloak';

const baseURL = import.meta.env.VITE_HRIS_CORE_API_BASE_URL as string;
const authMode = import.meta.env.VITE_AUTH_MODE as string || 'dev';

export const httpClient = axios.create({
  baseURL,
  timeout: 15000,
});

httpClient.interceptors.request.use(async (config) => {
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
    return config;
  }
  if (keycloak.authenticated && keycloak.token) {
    config.headers = config.headers ?? {};
    config.headers.Authorization = `Bearer ${keycloak.token}`;
  }
  return config;
}, (error) => Promise.reject(error));
