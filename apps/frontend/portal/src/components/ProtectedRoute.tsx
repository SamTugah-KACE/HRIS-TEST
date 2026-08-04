import React, { ReactNode } from 'react';
import { useAuth } from '../auth/AuthProvider';

type Props = {
  children: ReactNode;
};

export const ProtectedRoute: React.FC<Props> = ({ children }) => {
  const { initialized, authenticated } = useAuth();

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

  return <>{children}</>;
};
