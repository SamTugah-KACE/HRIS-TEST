import React, { ReactNode } from 'react';
import { useAuth } from '../auth/AuthProvider';
import { hasMinimumRole, type HrisRole } from '../auth/roles';

type Props = {
  children: ReactNode;
  minimumRole?: HrisRole;
  allowedRoles?: HrisRole[];
};

export const ProtectedRoute: React.FC<Props> = ({ children, minimumRole, allowedRoles }) => {
  const { initialized, authenticated, user } = useAuth();

  if (!initialized) return null;
  if (!authenticated) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="card text-center">
          <h2 className="text-lg font-semibold text-gray-900">Access Denied</h2>
          <p className="mt-2 text-sm text-gray-500">You are not authenticated.</p>
        </div>
      </div>
    );
  }

  const roleAllowed = Boolean(
    user &&
    (!minimumRole || hasMinimumRole(user.effectiveRole, minimumRole)) &&
    (!allowedRoles || allowedRoles.includes(user.effectiveRole)),
  );
  if (!roleAllowed) {
    return (
      <div className="mx-auto mt-12 max-w-lg rounded-xl border border-red-200 bg-red-50 p-6 text-center" role="alert">
        <h2 className="text-lg font-semibold text-red-900">You do not have permission</h2>
        <p className="mt-2 text-sm text-red-700">Your account cannot open this HRIS page. Contact your HR administrator if you believe this is incorrect.</p>
      </div>
    );
  }

  return <>{children}</>;
};
