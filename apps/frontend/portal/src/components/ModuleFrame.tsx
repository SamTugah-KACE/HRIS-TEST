/**
 * ModuleFrame — iFrame host for federated modules (SRMS, eAppraisal, eLeave).
 *
 * Architecture: docs/architecture/iframe-bridge-protocol.md
 *
 * Lifecycle:
 *  1. Resolve module origin (env var or API handoff)
 *  2. Render <iframe> → module sends MODULE_READY
 *  3. relayAuth() → POST /modules/{id}/token → send HRIS_AUTH_RELAY to iframe
 *  4. Module redirects through SSO bridge, re-sends MODULE_READY (guarded against loop)
 *  5. postMessage bridge handles all ongoing communication (search, nav, alerts, theme…)
 *
 * Adding a new module: see §11 of the bridge protocol doc — no changes needed here.
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { AlertTriangle, ExternalLink, RefreshCw } from 'lucide-react';
import { useAuth } from '../auth/AuthProvider';
import { ModuleLoadingSkeleton } from './ModuleLoadingSkeleton';
import { useModuleToken } from '../hooks/useModuleToken';
import { getModuleOrigin } from '../constants/moduleOrigins';
import { useModuleCapabilities } from '../contexts/ModuleCapabilitiesContext';
import { ConfirmDialog } from './ConfirmDialog';

export type ModuleFrameProps = {
  moduleId: string;
  path?: string;
  title?: string;
  /** Tailwind classes for the iframe element */
  className?: string;
};

type FrameState = 'resolving' | 'loading' | 'auth_relayed' | 'error';

type ConfirmRequest = {
  actionId: string;
  title?: string;
  message?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  danger?: boolean;
};

const MODULE_LABELS: Record<string, string> = {
  srms: 'Staff Records',
  eappraisal: 'Performance Appraisal',
  eleave: 'Leave Management',
};

/** Seconds before we stop waiting for MODULE_READY and show the iframe anyway. */
const MODULE_READY_TIMEOUT_MS = 12_000;

export const ModuleFrame: React.FC<ModuleFrameProps> = ({
  moduleId,
  path = '/',
  title,
  className = 'w-full border-0',
}) => {
  const { user } = useAuth();
  const { registerCapability } = useModuleCapabilities();
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const normalizedModuleId = moduleId.toLowerCase();
  const frameLabel = title ?? MODULE_LABELS[normalizedModuleId] ?? moduleId;

  const envOrigin = getModuleOrigin(normalizedModuleId);
  const [iframeSrc, setIframeSrc] = useState<string>(
    envOrigin ? `${envOrigin.replace(/\/$/, '')}${path === '/' ? '' : path}` : '',
  );
  const expectedOriginRef = useRef<string>(envOrigin);

  const [state, setState] = useState<FrameState>(envOrigin ? 'loading' : 'resolving');
  const [error, setError] = useState<string | null>(null);
  // Dynamic iframe height reported by the module via MODULE_HEIGHT_CHANGE.
  // Starts at 0 (falls back to min-height CSS) until the first report arrives.
  const [iframeHeight, setIframeHeight] = useState<number>(0);

  const moduleReadyReceived = useRef(false);
  // Prevents relayAuth from firing more than once per iframe session.
  // SRMS reloads after the SSO bridge redirect (callback page mounts fresh),
  // which sends another MODULE_READY. Without this guard that re-triggers
  // relayAuth → SSO bridge → reload → MODULE_READY → infinite loop.
  const authRelayedRef = useRef(false);
  // Debounce guard for MODULE_SESSION_EXPIRED: if two concurrent module API
  // calls both return 401 and both fire SESSION_EXPIRED, we only want one
  // relayAuth() call. Reset after relay completes.
  const sessionRefreshInFlightRef = useRef(false);

  const { fetchToken, isLoading: tokenLoading } = useModuleToken(normalizedModuleId);

  // Pending MODULE_CONFIRM_ACTION request from the active module.
  // null = dialog closed; non-null = dialog open.
  const [confirmRequest, setConfirmRequest] = useState<ConfirmRequest | null>(null);

  // --- Step 1: Resolve module origin from handoff when env var is absent ---
  useEffect(() => {
    if (envOrigin || iframeSrc) return;
    setState('resolving');
    fetchToken()
      .then((result) => {
        if (!result) {
          setState('error');
          setError('Could not resolve the module launch URL. Check your HRIS Core API settings.');
          return;
        }
        expectedOriginRef.current = result.moduleOrigin;
        setIframeSrc(result.moduleOrigin);
        setState('loading');
      })
      .catch(() => {
        setState('error');
        setError('Module URL resolution failed.');
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // --- Step 2: Relay auth after receiving MODULE_READY ---
  const relayAuth = useCallback(async () => {
    const iframe = iframeRef.current;
    if (!iframe?.contentWindow || !user) return;

    const result = await fetchToken();
    if (!result) {
      setState('error');
      setError('Could not obtain module auth token. Ensure the module handoff is enabled in HRIS settings.');
      return;
    }

    const targetOrigin = expectedOriginRef.current || result.moduleOrigin || '*';
    if (!expectedOriginRef.current && result.moduleOrigin) {
      expectedOriginRef.current = result.moduleOrigin;
    }

    iframe.contentWindow.postMessage(
      {
        type: 'HRIS_AUTH_RELAY',
        token: result.token,
        tenantSlug: result.tenantSlug,
        sub: user.sub,
        username: user.username,
        expiresAt: result.expiresAt,
      },
      targetOrigin,
    );

    // Send current theme immediately after auth so the module starts in the
    // correct mode even when the theme toggle hasn't been touched this session.
    const isDark = document.documentElement.classList.contains('dark');
    iframe.contentWindow.postMessage(
      {
        type: 'THEME_TOKENS',
        tokens: {
          '--hris-theme': isDark ? 'dark' : 'light',
          '--hris-bg': isDark ? '#111827' : '#f9fafb',
          '--hris-surface': isDark ? '#1f2937' : '#ffffff',
          '--hris-text': isDark ? '#f9fafb' : '#111827',
          '--hris-border': isDark ? '#374151' : '#e5e7eb',
          '--hris-brand': '#3b82f6',
        },
      },
      targetOrigin,
    );

    setState('auth_relayed');

    // --- Browser back/forward restore ---
    // If the user navigated back to this module page, the previous module URL
    // is stored in ?module_path. Send it to the module so it restores the
    // last-visited route instead of always starting at the root.
    const params = new URLSearchParams(window.location.search);
    const savedPath = params.get('module_path');
    if (savedPath) {
      // Small delay so the module finishes its own auth setup before we navigate.
      setTimeout(() => {
        iframe.contentWindow?.postMessage(
          { type: 'HRIS_NAV_GO', path: savedPath },
          targetOrigin,
        );
      }, 400);
    }
  }, [user, fetchToken]);

  // --- Step 3: postMessage bridge (module → HRIS) ---
  useEffect(() => {
    const handleMessage = (event: MessageEvent) => {
      const allowed = expectedOriginRef.current;
      if (allowed && event.origin !== allowed) return;

      const data = event.data as {
        type?: string;
        navItems?: unknown;
        path?: string;
        title?: string;
        height?: number;
        placeholder?: string;
        avatarUrl?: string;
        displayName?: string;
      };
      if (!data?.type) return;

      switch (data.type) {
        case 'MODULE_READY':
          moduleReadyReceived.current = true;
          if (!authRelayedRef.current) {
            authRelayedRef.current = true;
            void relayAuth();
          }
          break;

        // Module's short-lived token expired mid-session (got a 401 from its own API).
        // Re-fetch a fresh module token from HRIS Core and relay it — the user's main
        // HRIS session is still valid, so this is transparent (no logout prompt).
        // Debounced: if multiple concurrent requests all 401 at once, only one relay fires.
        case 'MODULE_SESSION_EXPIRED':
          if (!sessionRefreshInFlightRef.current) {
            sessionRefreshInFlightRef.current = true;
            authRelayedRef.current = false;
            // Use a closure so .finally() operates on the real Promise, not void.
            (async () => { await relayAuth(); })().finally(() => {
              sessionRefreshInFlightRef.current = false;
            });
          }
          break;

        case 'MODULE_NAV_UPDATE':
          window.dispatchEvent(
            new CustomEvent('hris:module-nav-update', {
              detail: { moduleId: normalizedModuleId, navItems: data.navItems },
            }),
          );
          break;

        case 'MODULE_ROUTE_CHANGE':
          if (data.path) {
            window.history.replaceState(
              null,
              '',
              `${window.location.pathname}?module_path=${encodeURIComponent(data.path)}`,
            );
          }
          break;

        case 'MODULE_TITLE_CHANGE':
          if (data.title) {
            document.title = `${data.title} — HRIS`;
          }
          break;

        // Module reports its full content height so HRIS can size the iframe
        // to exactly fit the content — eliminating the iframe's own scrollbar.
        case 'MODULE_HEIGHT_CHANGE':
          if (typeof data.height === 'number' && data.height > 0) {
            setIframeHeight(data.height);
          }
          break;

        // Module declares it has a search bar — HRIS Navbar renders one instead.
        case 'MODULE_SEARCH_CONFIG':
          window.dispatchEvent(
            new CustomEvent('hris:module-search-config', {
              detail: {
                moduleId: normalizedModuleId,
                placeholder: data.placeholder ?? 'Search...',
              },
            }),
          );
          break;

        // Module sends logged-in user's avatar/name so HRIS Navbar can show the real photo.
        case 'MODULE_USER_PROFILE':
          window.dispatchEvent(
            new CustomEvent('hris:module-user-profile', {
              detail: {
                moduleId: normalizedModuleId,
                avatarUrl: data.avatarUrl ?? null,
                displayName: data.displayName ?? null,
              },
            }),
          );
          break;

        // Module sends its summary stats (employee counts, units, ranks, etc.)
        // so HRIS can render them natively above the iframe instead of inside it.
        case 'MODULE_SUMMARY_UPDATE':
          window.dispatchEvent(
            new CustomEvent('hris:module-summary-update', {
              detail: {
                moduleId: normalizedModuleId,
                cards: (data as { cards?: unknown }).cards ?? [],
              },
            }),
          );
          break;

        // Module fires this when a new real-time notification arrives (e.g. a new
        // chat message in SRMS) so HRIS can surface it in the notification bell
        // with an action button that opens the module's messaging UI.
        case 'MODULE_NOTIFICATION': {
          const notif = data as {
            notificationType?: string;
            senderName?: string;
            preview?: string;
            conversationId?: string;
          };
          window.dispatchEvent(
            new CustomEvent('hris:module-notification', {
              detail: {
                moduleId: normalizedModuleId,
                notificationType: notif.notificationType ?? 'message',
                senderName: notif.senderName ?? '',
                preview: notif.preview ?? '',
                conversationId: notif.conversationId ?? '',
              },
            }),
          );
          break;
        }

        // Module relays its own toast/alert so HRIS can display it natively
        // (the module's ToastContainer is hidden via CSS when embedded).
        case 'MODULE_ALERT':
          window.dispatchEvent(
            new CustomEvent('hris:module-alert', {
              detail: {
                moduleId: normalizedModuleId,
                message: (data as { message?: string }).message ?? '',
                level: (data as { level?: string }).level ?? 'info',
              },
            }),
          );
          break;

        // Module self-declares its profile capability so HRIS /profile shows
        // a tab for it without any hard-coded module knowledge.
        // Any module — known or unknown — that sends this message gets a tab.
        // See: docs/architecture/iframe-bridge-protocol.md §12
        case 'MODULE_PROFILE_CAPABILITY': {
          const cap = data as {
            label?: string;
            profilePath?: string;
            actions?: { id: string; label: string }[];
          };
          registerCapability({
            moduleId: normalizedModuleId,
            label: cap.label ?? MODULE_LABELS[normalizedModuleId] ?? normalizedModuleId,
            profilePath: cap.profilePath ?? '/hris/profile',
            actions: cap.actions ?? [],
          });
          break;
        }

        // Module requests a native HRIS confirmation dialog before a destructive
        // operation (delete, archive, etc.). HRIS opens a styled React modal;
        // the result is sent back as HRIS_CONFIRM_RESULT once the user responds.
        // This keeps all confirm UX consistent and on-brand across every module.
        case 'MODULE_CONFIRM_ACTION': {
          const req = data as ConfirmRequest;
          setConfirmRequest(req);
          break;
        }

        // Module's JavaScript threw an unhandled error (relayed via window.onerror).
        // Surface it as a module alert so HRIS operators can see runtime crashes
        // without opening DevTools inside the iframe.
        case 'MODULE_RUNTIME_ERROR':
          window.dispatchEvent(
            new CustomEvent('hris:module-alert', {
              detail: {
                moduleId: normalizedModuleId,
                message: `Runtime error in ${MODULE_LABELS[normalizedModuleId] ?? normalizedModuleId}: ${(data as { message?: string }).message ?? 'Unknown error'}`,
                level: 'error',
              },
            }),
          );
          break;

        default:
          break;
      }
    };

    window.addEventListener('message', handleMessage);
    return () => window.removeEventListener('message', handleMessage);
  }, [relayAuth, normalizedModuleId, registerCapability]);

  // --- Step 4: Forward HRIS search queries into the iframe ---
  useEffect(() => {
    const handleSearchQuery = (event: Event) => {
      const detail = (event as CustomEvent<{ query: string }>).detail;
      const iframe = iframeRef.current;
      const targetOrigin = expectedOriginRef.current || '*';
      if (iframe?.contentWindow && detail?.query !== undefined) {
        iframe.contentWindow.postMessage(
          { type: 'HRIS_SEARCH_QUERY', query: detail.query },
          targetOrigin,
        );
      }
    };
    // Namespaced per module so multiple iframes don't cross-fire.
    const evt = `hris:module-search-query-${normalizedModuleId}`;
    window.addEventListener(evt, handleSearchQuery);
    return () => window.removeEventListener(evt, handleSearchQuery);
  }, [normalizedModuleId]);

  // --- Step 5: Forward HRIS sidebar nav clicks into the iframe ---
  useEffect(() => {
    const handleNavGo = (event: Event) => {
      const detail = (event as CustomEvent<{ path: string }>).detail;
      const iframe = iframeRef.current;
      const targetOrigin = expectedOriginRef.current || '*';
      if (iframe?.contentWindow && detail?.path) {
        iframe.contentWindow.postMessage(
          { type: 'HRIS_NAV_GO', path: detail.path },
          targetOrigin,
        );
      }
    };
    const evt = `hris:module-nav-go-${normalizedModuleId}`;
    window.addEventListener(evt, handleNavGo);
    return () => window.removeEventListener(evt, handleNavGo);
  }, [normalizedModuleId]);

  // --- Step 5b: Forward HRIS sidebar action triggers into the iframe ---
  // SRMS sidebar items open modals via TRIGGER_ACTION rather than page navigation.
  // The hidden SRMS Sidebar component listens for this postMessage and opens the
  // correct modal — its React state and event handlers stay active even when the
  // sidebar element itself is hidden by hris-embedded CSS.
  useEffect(() => {
    const handleTriggerAction = (event: Event) => {
      const detail = (event as CustomEvent<{ actionId: string }>).detail;
      const iframe = iframeRef.current;
      const targetOrigin = expectedOriginRef.current || '*';
      if (iframe?.contentWindow && detail?.actionId) {
        iframe.contentWindow.postMessage(
          { type: 'TRIGGER_ACTION', actionId: detail.actionId },
          targetOrigin,
        );
      }
    };
    const evt = `hris:module-trigger-action-${normalizedModuleId}`;
    window.addEventListener(evt, handleTriggerAction);
    return () => window.removeEventListener(evt, handleTriggerAction);
  }, [normalizedModuleId]);

  // --- Step 5c: Relay HRIS dark/light theme to module as THEME_TOKENS ---
  // The module's applyThemeTokens handler (in its own index.js) receives these
  // and sets CSS custom properties on documentElement so the module can adapt.
  useEffect(() => {
    const handleThemeChange = (event: Event) => {
      const { darkMode } = (event as CustomEvent<{ darkMode: boolean }>).detail;
      const iframe = iframeRef.current;
      const targetOrigin = expectedOriginRef.current || '*';
      if (iframe?.contentWindow) {
        iframe.contentWindow.postMessage(
          {
            type: 'THEME_TOKENS',
            tokens: {
              '--hris-theme': darkMode ? 'dark' : 'light',
              '--hris-bg': darkMode ? '#111827' : '#f9fafb',
              '--hris-surface': darkMode ? '#1f2937' : '#ffffff',
              '--hris-text': darkMode ? '#f9fafb' : '#111827',
              '--hris-border': darkMode ? '#374151' : '#e5e7eb',
              '--hris-brand': '#3b82f6',
            },
          },
          targetOrigin,
        );
      }
    };
    window.addEventListener('hris:theme-change', handleThemeChange);
    return () => window.removeEventListener('hris:theme-change', handleThemeChange);
  }, []);

  // --- Step 6: Broadcast HRIS_LOGOUT to iframe when HRIS session ends ---
  // AuthProvider dispatches 'hris:logout' before calling the logout API,
  // giving the iframe a chance to invalidate its own session first.
  useEffect(() => {
    const handleLogout = () => {
      const iframe = iframeRef.current;
      const targetOrigin = expectedOriginRef.current || '*';
      if (iframe?.contentWindow) {
        iframe.contentWindow.postMessage({ type: 'HRIS_LOGOUT' }, targetOrigin);
      }
    };
    window.addEventListener('hris:logout', handleLogout);
    return () => window.removeEventListener('hris:logout', handleLogout);
  }, []);

  // --- Step 7: Fallback timeout ---
  useEffect(() => {
    if (state !== 'loading') return;
    const timer = window.setTimeout(() => {
      setState((current) => {
        if (current !== 'loading') return current;
        if (moduleReadyReceived.current) return 'auth_relayed';
        setError(
          `${frameLabel} is not responding. Make sure the module server is running and accessible.`,
        );
        return 'error';
      });
    }, MODULE_READY_TIMEOUT_MS);
    return () => window.clearTimeout(timer);
  }, [state, frameLabel]);

  // --- Step 8: Clear all module UI chrome when this iframe unmounts ---
  useEffect(() => {
    return () => {
      window.dispatchEvent(new CustomEvent('hris:module-search-config', { detail: null }));
      window.dispatchEvent(new CustomEvent('hris:module-nav-update', { detail: null }));
      window.dispatchEvent(new CustomEvent('hris:module-user-profile', { detail: null }));
      window.dispatchEvent(new CustomEvent('hris:module-summary-update', { detail: null }));
    };
  }, []);

  // --- Retry handler ---
  const handleRetry = useCallback(() => {
    setError(null);
    setIframeHeight(0);
    moduleReadyReceived.current = false;
    authRelayedRef.current = false;
    expectedOriginRef.current = envOrigin;
    if (envOrigin) {
      setIframeSrc(`${envOrigin.replace(/\/$/, '')}${path === '/' ? '' : path}`);
      setState('loading');
    } else {
      setIframeSrc('');
      setState('resolving');
    }
  }, [envOrigin, path]);

  // Sends HRIS_CONFIRM_RESULT back to the module and closes the dialog.
  const handleConfirmResult = useCallback((confirmed: boolean) => {
    if (confirmRequest) {
      const targetOrigin = expectedOriginRef.current || '*';
      iframeRef.current?.contentWindow?.postMessage(
        { type: 'HRIS_CONFIRM_RESULT', actionId: confirmRequest.actionId, confirmed },
        targetOrigin,
      );
    }
    setConfirmRequest(null);
  }, [confirmRequest]);

  // --- Render: resolving / loading skeleton ---
  if (state === 'resolving') {
    return <ModuleLoadingSkeleton />;
  }

  // --- Render: error ---
  if (state === 'error') {
    return (
      <div className="m-4 rounded-lg border border-red-200 bg-red-50 p-6 dark:border-red-900/50 dark:bg-red-950/30">
        <div className="flex items-start gap-3">
          <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-red-500" />
          <div className="flex-1">
            <p className="font-semibold text-red-800 dark:text-red-200">
              {frameLabel} unavailable
            </p>
            <p className="mt-1 text-sm text-red-700 dark:text-red-300">
              {error || 'The module could not be loaded.'}
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              <button type="button" onClick={handleRetry} className="btn-secondary py-1.5 text-xs">
                <RefreshCw className="h-3.5 w-3.5" /> Retry
              </button>
              {iframeSrc && (
                <a
                  href={iframeSrc}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="btn-secondary py-1.5 text-xs"
                >
                  <ExternalLink className="h-3.5 w-3.5" /> Open in new tab
                </a>
              )}
            </div>
          </div>
        </div>
      </div>
    );
  }

  // Iframe height: use dynamic content height once reported; fall back to
  // a viewport-filling minimum so the skeleton covers the full pane on first load.
  const frameHeight = iframeHeight > 0 ? iframeHeight : undefined;

  // --- Render: iframe (with skeleton overlay while awaiting MODULE_READY + auth) ---
  return (
    <>
    <ConfirmDialog
      open={confirmRequest !== null}
      title={confirmRequest?.title}
      message={confirmRequest?.message}
      confirmLabel={confirmRequest?.confirmLabel}
      cancelLabel={confirmRequest?.cancelLabel}
      danger={confirmRequest?.danger}
      onConfirm={() => handleConfirmResult(true)}
      onCancel={() => handleConfirmResult(false)}
    />
    <div className="relative w-full">
      {(state === 'loading' || tokenLoading) && (
        <div className="absolute inset-0 z-10 bg-white dark:bg-gray-900">
          <ModuleLoadingSkeleton />
        </div>
      )}
      {iframeSrc && (
        <iframe
          ref={iframeRef}
          title={frameLabel}
          src={iframeSrc}
          className={className}
          style={{
            height: frameHeight ? `${frameHeight}px` : 'calc(100vh - 8rem)',
            // Overflow hidden eliminates the iframe's own scrollbar.
            // The module reports its content height via MODULE_HEIGHT_CHANGE,
            // which sizes the iframe to exactly fit — no internal scroll needed.
            overflow: 'hidden',
            display: 'block',
          }}
          sandbox="allow-forms allow-scripts allow-same-origin allow-popups allow-downloads allow-modals allow-popups-to-escape-sandbox"
          onError={() => {
            setState('error');
            setError(
              'The module could not be embedded. It may be offline or its server is blocking iFrame access.',
            );
          }}
        />
      )}
    </div>
    </>
  );
};
