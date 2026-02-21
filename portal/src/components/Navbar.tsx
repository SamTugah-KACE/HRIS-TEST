import React from 'react';
import { Menu, LogOut } from 'lucide-react';
import { useAuth } from '../auth/AuthProvider';
import { getRoleLabel } from '../auth/roles';
import { RoleSwitcher } from './RoleSwitcher';
import { NotificationPanel } from './NotificationPanel';

type NavbarProps = {
  onMenuToggle: () => void;
};

export const Navbar: React.FC<NavbarProps> = ({ onMenuToggle }) => {
  const { user, logout } = useAuth();

  return (
    <header className="sticky top-0 z-30 flex h-16 items-center justify-between border-b border-gray-200 bg-white px-4 lg:px-6">
      <div className="flex items-center gap-3">
        <button
          onClick={onMenuToggle}
          className="rounded-lg p-2 text-gray-500 hover:bg-gray-100 lg:hidden"
        >
          <Menu className="h-5 w-5" />
        </button>
        <div className="hidden text-sm text-gray-500 lg:block">
          {user?.email && <span>{user.email}</span>}
        </div>
      </div>

      <div className="flex items-center gap-2">
        <RoleSwitcher />

        <NotificationPanel />

        <div className="mx-2 h-6 w-px bg-gray-200" />

        <div className="hidden items-center gap-2 sm:flex">
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-brand-500 text-xs font-bold text-white">
            {user?.username?.charAt(0)?.toUpperCase() ?? 'U'}
          </div>
          <div className="text-right">
            <p className="text-sm font-medium text-gray-900">{user?.username}</p>
            <p className="text-xs text-gray-500">{getRoleLabel(user?.effectiveRole ?? 'hris:employee')}</p>
          </div>
        </div>

        <button
          onClick={logout}
          className="ml-2 rounded-lg p-2 text-gray-500 hover:bg-red-50 hover:text-red-600"
          title="Sign out"
        >
          <LogOut className="h-5 w-5" />
        </button>
      </div>
    </header>
  );
};
