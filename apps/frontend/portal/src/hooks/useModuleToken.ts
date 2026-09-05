import { useCallback, useState } from 'react';
import { createModuleHandoffLaunch } from '../api/hrisCoreClient';

export type ModuleTokenResult = {
  code: string;
  tenantSlug: string;
  moduleOrigin: string;
  expiresAt: number;
};

export type UseModuleTokenReturn = {
  fetchToken: () => Promise<ModuleTokenResult | null>;
  isLoading: boolean;
  error: string | null;
};

/**
 * Fetches a short-lived, random, single-use HRIS handoff code.
 *
 * The handoff endpoint returns a launch_url of the form:
 *   {module_origin}/{tenant_slug}/dashboard?hris_handoff={OPAQUE_CODE}
 *
 * The value contains no identity claims. The module must send it to its own
 * backend, which redeems it server-to-server. The browser-facing relay names
 * this value `code`; `token` is reserved for actual authentication tokens.
 */
export function useModuleToken(moduleId: string): UseModuleTokenReturn {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchToken = useCallback(async (): Promise<ModuleTokenResult | null> => {
    setIsLoading(true);
    setError(null);
    try {
      const handoff = await createModuleHandoffLaunch(moduleId);
      const launchUrl = String(handoff.launch_url || '');
      if (!launchUrl) {
        throw new Error('No launch URL returned from handoff endpoint');
      }

      const url = new URL(launchUrl);
      const code = url.searchParams.get('hris_handoff') ?? '';
      if (!code) {
        throw new Error('No handoff code found in launch URL');
      }

      // Path format: /{tenant_slug}/dashboard — first segment is the tenant slug
      const pathParts = url.pathname.split('/').filter(Boolean);
      const tenantSlug = String(handoff.tenant_slug || pathParts[0] || '');
      const moduleOrigin = url.origin;

      return {
        code,
        tenantSlug,
        moduleOrigin,
        expiresAt: Number(handoff.expires_at || 0),
      };
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to fetch module handoff code';
      setError(msg);
      return null;
    } finally {
      setIsLoading(false);
    }
  }, [moduleId]);

  return { fetchToken, isLoading, error };
}
