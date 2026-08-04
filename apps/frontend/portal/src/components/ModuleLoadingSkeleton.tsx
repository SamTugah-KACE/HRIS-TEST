import React from 'react';

export const ModuleLoadingSkeleton: React.FC = () => (
  <div className="flex h-full w-full flex-col gap-4 p-6 animate-pulse">
    <div className="h-8 w-48 rounded-lg bg-gray-200 dark:bg-gray-800" />
    <div className="h-4 w-72 rounded bg-gray-100 dark:bg-gray-800" />
    <div className="mt-4 grid grid-cols-3 gap-4">
      {[1, 2, 3].map((i) => (
        <div key={i} className="h-24 rounded-xl bg-gray-100 dark:bg-gray-800" />
      ))}
    </div>
    <div className="mt-2 h-64 rounded-xl bg-gray-100 dark:bg-gray-800" />
    <div className="mt-2 h-40 rounded-xl bg-gray-100 dark:bg-gray-800" />
  </div>
);
