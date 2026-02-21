import React from 'react';
import { Link } from 'react-router-dom';
import { Home } from 'lucide-react';

export const NotFoundPage: React.FC = () => {
  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50">
      <div className="text-center">
        <p className="text-6xl font-bold text-brand-500">404</p>
        <h1 className="mt-4 text-2xl font-bold text-gray-900">Page not found</h1>
        <p className="mt-2 text-sm text-gray-500">The page you're looking for doesn't exist.</p>
        <Link to="/" className="btn-primary mt-6 inline-flex">
          <Home className="h-4 w-4" /> Back to Dashboard
        </Link>
      </div>
    </div>
  );
};
