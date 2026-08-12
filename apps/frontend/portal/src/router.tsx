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

const router = createBrowserRouter([
  {
    path: '/',
    element: <Layout />,
    children: [
      { index: true, element: <DashboardPage /> },
      { path: 'profile', element: <ProfileHubPage /> },
      { path: 'employees', element: <ModuleWorkspacePage fixedModuleId="srms" /> },
      { path: 'employees/team', element: <ModuleWorkspacePage fixedModuleId="srms" /> },
      { path: 'employees/:employeeId', element: <EmployeeDetailPage /> },
      { path: 'modules/appraisal', element: <ModuleWorkspacePage fixedModuleId="eappraisal" /> },
      { path: 'modules/leave', element: <LeavePage /> },
      { path: 'modules/:moduleId/native', element: <ModuleWorkspacePage /> },
      { path: 'reports', element: <ReportsPage /> },
      { path: 'admin/roles', element: <RolesPage /> },
      { path: 'admin/tenants', element: <TenantManagementPage /> },
    ],
  },
  { path: '*', element: <NotFoundPage /> },
]);

export const AppRouter: React.FC = () => <RouterProvider router={router} />;
