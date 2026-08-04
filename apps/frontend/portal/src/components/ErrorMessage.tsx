import React from 'react';
import { AlertTriangle } from 'lucide-react';

type Props = { message: string };

export const ErrorMessage: React.FC<Props> = ({ message }) => {
  return (
    <div className="flex items-start gap-3 rounded-xl border border-red-200 bg-red-50 p-4">
      <AlertTriangle className="mt-0.5 h-5 w-5 text-red-500" />
      <p className="text-sm text-red-700">{message}</p>
    </div>
  );
};
