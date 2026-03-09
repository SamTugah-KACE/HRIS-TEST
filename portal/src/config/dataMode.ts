export const portalDataMode = (import.meta.env.VITE_PORTAL_DATA_MODE as string | undefined)?.toLowerCase() === 'api'
  ? 'api'
  : 'mock';

export const isApiDataMode = portalDataMode === 'api';
