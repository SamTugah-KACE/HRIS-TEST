import React from 'react';
import { createBrowserRouter, RouterProvider } from 'react-router-dom';
import { Layout } from './components/Layout';
import { DashboardPage } from './pages/DashboardPage';
import { ProfilePage } from './pages/ProfilePage';
import { EmployeeListPage } from './pages/EmployeeListPage';
import { EmployeeDetailPage } from './pages/EmployeeDetailPage';
import { AppraisalPage } from './pages/modules/AppraisalPage';
import { LeavePage } from './pages/modules/LeavePage';
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
      { path: 'profile', element: <ProfilePage /> },
      { path: 'employees', element: <EmployeeListPage /> },
      { path: 'employees/:employeeId', element: <EmployeeDetailPage /> },
      { path: 'modules/appraisal', element: <AppraisalPage /> },
      { path: 'modules/leave', element: <LeavePage /> },
      { path: 'reports', element: <ReportsPage /> },
      { path: 'admin/roles', element: <RolesPage /> },
      { path: 'admin/tenants', element: <TenantManagementPage /> },
    ],
  },
  { path: '*', element: <NotFoundPage /> },
]);

export const AppRouter: React.FC = () => <RouterProvider router={router} />;
