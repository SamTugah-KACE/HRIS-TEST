import React from 'react';
import { createBrowserRouter, RouterProvider } from 'react-router-dom';
import { Layout } from './components/Layout';
import { DashboardPage } from './pages/DashboardPage';
import { ProfileHubPage } from './pages/ProfileHubPage';
import { EmployeeDetailPage } from './pages/EmployeeDetailPage';
import { LeavePage } from './pages/modules/LeavePage';
import { ModuleWorkspacePage } from './pages/modules/ModuleWorkspacePage';
import { RolesPage } from './pages/admin/RolesPage';
import { TenantManagementPage } from './pages/admin/TenantManagementPage';
import { ReportsPage } from './pages/ReportsPage';
import { NotFoundPage } from './pages/NotFoundPage';
import { ProtectedRoute } from './components/ProtectedRoute';
import { HRIS_ROLES, type HrisRole } from './auth/roles';

const protect = (element: React.ReactNode, minimumRole: HrisRole = HRIS_ROLES.EMPLOYEE) => (
  <ProtectedRoute minimumRole={minimumRole}>{element}</ProtectedRoute>
);

const router = createBrowserRouter([
  {
    path: '/',
    element: <Layout />,
    children: [
      { index: true, element: protect(<DashboardPage />) },
      { path: 'profile', element: protect(<ProfileHubPage />) },
      { path: 'employees', element: protect(<ModuleWorkspacePage fixedModuleId="srms" />, HRIS_ROLES.HR_MANAGER) },
      { path: 'employees/team', element: protect(<ModuleWorkspacePage fixedModuleId="srms" />, HRIS_ROLES.LINE_MANAGER) },
      { path: 'employees/:employeeId', element: protect(<EmployeeDetailPage />, HRIS_ROLES.LINE_MANAGER) },
      { path: 'modules/appraisal', element: protect(<ModuleWorkspacePage fixedModuleId="eappraisal" />) },
      { path: 'modules/leave', element: protect(<LeavePage />) },
      { path: 'modules/:moduleId/native', element: protect(<ModuleWorkspacePage />) },
      { path: 'reports', element: protect(<ReportsPage />, HRIS_ROLES.HR_MANAGER) },
      { path: 'admin/roles', element: protect(<RolesPage />, HRIS_ROLES.TENANT_ADMIN) },
      { path: 'admin/tenants', element: protect(<TenantManagementPage />, HRIS_ROLES.TENANT_ADMIN) },
    ],
  },
  { path: '*', element: <NotFoundPage /> },
]);

export const AppRouter: React.FC = () => <RouterProvider router={router} />;
