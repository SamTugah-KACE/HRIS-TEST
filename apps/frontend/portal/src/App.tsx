import React from 'react';
import { AppRouter } from './router';
import { ModuleCapabilitiesProvider } from './contexts/ModuleCapabilitiesContext';

export const App: React.FC = () => {
  return (
    <ModuleCapabilitiesProvider>
      <AppRouter />
    </ModuleCapabilitiesProvider>
  );
};
