import React, { useState } from 'react';
import { Outlet } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { Navbar } from './Navbar';

export const Layout: React.FC = () => {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  return (
    <div className="flex h-screen overflow-hidden bg-gray-50 dark:bg-gray-950">
      <Sidebar
        open={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        collapsed={sidebarCollapsed}
        onToggleCollapse={() => setSidebarCollapsed((v) => !v)}
      />
      <div className="flex flex-1 flex-col overflow-hidden">
        <Navbar
          onMenuToggle={() => setSidebarOpen(o => !o)}
          sidebarCollapsed={sidebarCollapsed}
          onToggleSidebarCollapse={() => setSidebarCollapsed((v) => !v)}
        />
        <main className="flex-1 overflow-y-auto bg-gray-50 p-4 transition-colors lg:p-6 dark:bg-gray-950">
          <Outlet />
        </main>
        <footer className="border-t border-gray-200 bg-white px-4 py-3 text-xs text-gray-500 transition-colors dark:border-gray-800 dark:bg-gray-900 dark:text-gray-400 lg:px-6">
          <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
            <span>HRIS Platform</span>
            <span>Secure unified HR workflows across devices.</span>
          </div>
        </footer>
      </div>
    </div>
  );
};
