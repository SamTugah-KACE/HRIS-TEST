/**
 * ModuleCapabilitiesContext
 * ==========================
 * Stores self-declared profile capabilities from every federated module.
 *
 * Each module sends a MODULE_PROFILE_CAPABILITY postMessage on boot
 * (handled by ModuleFrame.tsx). This context is the single store for
 * those declarations, making the /profile page fully data-driven:
 *
 *   new module added → sends MODULE_PROFILE_CAPABILITY → tab appears
 *   module changes label/path → sends updated message → tab updates
 *   module removed → doesn't send → no tab shown
 *
 * Persistence: capabilities are kept in sessionStorage so navigating
 * away from a module's workspace and back to /profile still shows its
 * tab.  Cleared on logout (AuthProvider dispatches 'hris:logout').
 *
 * Architecture reference: docs/architecture/iframe-bridge-protocol.md §12
 */

import React, { createContext, useCallback, useContext, useEffect, useState } from 'react';

export type ProfileAction = {
  id: string;
  label: string;
};

export type ModuleCapability = {
  moduleId: string;
  /** Tab label shown on the /profile page (e.g. "Staff Profile") */
  label: string;
  /** Path inside the module that renders a profile-only view when embedded */
  profilePath: string;
  /** Quick actions the module supports (e.g. profile:view, profile:reset-password) */
  actions: ProfileAction[];
};

type CapabilityMap = Record<string, ModuleCapability>;

const STORAGE_KEY = 'hris_module_capabilities';

function loadFromStorage(): CapabilityMap {
  try {
    return JSON.parse(sessionStorage.getItem(STORAGE_KEY) || '{}');
  } catch {
    return {};
  }
}

function saveToStorage(map: CapabilityMap): void {
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(map));
  } catch {
    // storage full or private mode — not critical
  }
}

type ContextValue = {
  capabilities: CapabilityMap;
  registerCapability: (cap: ModuleCapability) => void;
  clearAll: () => void;
};

const ModuleCapabilitiesContext = createContext<ContextValue>({
  capabilities: {},
  registerCapability: () => {},
  clearAll: () => {},
});

export const ModuleCapabilitiesProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [capabilities, setCapabilities] = useState<CapabilityMap>(loadFromStorage);

  const registerCapability = useCallback((cap: ModuleCapability) => {
    setCapabilities((prev) => {
      const next = { ...prev, [cap.moduleId]: cap };
      saveToStorage(next);
      return next;
    });
  }, []);

  const clearAll = useCallback(() => {
    sessionStorage.removeItem(STORAGE_KEY);
    setCapabilities({});
  }, []);

  // Clear capabilities when the HRIS session ends.
  useEffect(() => {
    const handle = () => clearAll();
    window.addEventListener('hris:logout', handle);
    return () => window.removeEventListener('hris:logout', handle);
  }, [clearAll]);

  return (
    <ModuleCapabilitiesContext.Provider value={{ capabilities, registerCapability, clearAll }}>
      {children}
    </ModuleCapabilitiesContext.Provider>
  );
};

export const useModuleCapabilities = () => useContext(ModuleCapabilitiesContext);
