import React, { useEffect, useMemo, useState } from 'react';
import { Building2, Upload, CheckCircle, XCircle, Eye, EyeOff, Copy, Check, Rocket, AlertTriangle } from 'lucide-react';
import { clsx } from 'clsx';
import {
  getTenantBranding,
  importTenantOnboarding,
  resetTenantUserPassword,
  getTenantStorageProviders,
  listTenants,
  type TenantUserPasswordResetResponse,
  updateTenantBranding,
  updateTenantStorageProviders,
  uploadTenantLogo,
  type TenantRow,
} from '../../api/hrisCoreClient';
import { useAuth } from '../../auth/AuthProvider';
import { HRIS_ROLES } from '../../auth/roles';

export const TenantManagementPage: React.FC = () => {
  const { user } = useAuth();
  const isSuperAdmin = user?.effectiveRole === HRIS_ROLES.SUPER_ADMIN;
  const [onboardBusy, setOnboardBusy] = useState(false);
  const [onboardError, setOnboardError] = useState('');
  const [onboardResult, setOnboardResult] = useState<unknown>(null);
  const [onboardPayload, setOnboardPayload] = useState({
    tenant_id: '',
    code: '',
    name: '',
    srms_schema: '',
    srms_slug: '',
    eappraisal_subdomain: '',
    eleave_subdomain: '',
    is_active: true,
  });
  const [tenants, setTenants] = useState<TenantRow[]>([]);
  const [selectedTenantId, setSelectedTenantId] = useState('');
  const [brandName, setBrandName] = useState('');
  const [supportEmail, setSupportEmail] = useState('');
  const [providersJson, setProvidersJson] = useState('[{"name":"s3","config":{}},{"name":"local","config":{}}]');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string>('');
  const [resetBusy, setResetBusy] = useState(false);
  const [resetEmail, setResetEmail] = useState('');
  const [resetUsername, setResetUsername] = useState('');
  const [resetReason, setResetReason] = useState('manual_admin_reset');
  const [resetResult, setResetResult] = useState<TenantUserPasswordResetResponse | null>(null);
  const [showTemporaryPassword, setShowTemporaryPassword] = useState(false);
  const [copiedTemporaryPassword, setCopiedTemporaryPassword] = useState(false);
  const [resetConfirmationText, setResetConfirmationText] = useState('');

  const selectedTenant = useMemo(
    () => tenants.find((t) => t.tenant_id === selectedTenantId) || null,
    [tenants, selectedTenantId]
  );
  const resetConfirmationPhrase = 'RESET';
  const canSubmitManualReset = Boolean(
    selectedTenantId &&
    !resetBusy &&
    (resetEmail.trim() || resetUsername.trim()) &&
    resetConfirmationText.trim().toUpperCase() === resetConfirmationPhrase
  );

  const canSubmitOnboarding = Boolean(
    isSuperAdmin &&
    onboardPayload.code.trim() &&
    onboardPayload.name.trim() &&
    !onboardBusy
  );

  useEffect(() => {
    let mounted = true;
    setLoading(true);
    listTenants(500)
      .then((payload) => {
        if (!mounted) return;
        setTenants(payload.tenants || []);
        if (payload.tenants?.length) {
          if (isSuperAdmin) {
            setSelectedTenantId((prev) => prev || payload.tenants[0].tenant_id);
          } else {
            setSelectedTenantId(user?.tenantId || payload.tenants[0].tenant_id);
          }
        }
      })
      .finally(() => {
        if (mounted) setLoading(false);
      });
    return () => {
      mounted = false;
    };
  }, [isSuperAdmin, user?.tenantId]);

  const submitOnboarding = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmitOnboarding) return;
    setOnboardBusy(true);
    setOnboardError('');
    setOnboardResult(null);
    try {
      const cleaned = {
        ...onboardPayload,
        tenant_id: onboardPayload.tenant_id.trim() || undefined,
        srms_schema: onboardPayload.srms_schema.trim() || undefined,
        srms_slug: onboardPayload.srms_slug.trim() || undefined,
        eappraisal_subdomain: onboardPayload.eappraisal_subdomain.trim() || undefined,
        eleave_subdomain: onboardPayload.eleave_subdomain.trim() || undefined,
      };
      const response = await importTenantOnboarding(cleaned);
      setOnboardResult(response.result ?? response);
      // Refresh list so the new/updated tenant is visible immediately.
      const refreshed = await listTenants(500);
      setTenants(refreshed.tenants || []);
    } catch {
      setOnboardError('Failed to import tenant. Check Core API logs and Tenant Registry credentials.');
    } finally {
      setOnboardBusy(false);
    }
  };

  useEffect(() => {
    let mounted = true;
    if (!selectedTenantId) return () => { mounted = false; };
    Promise.all([getTenantBranding(selectedTenantId), getTenantStorageProviders(selectedTenantId)])
      .then(([branding, providers]) => {
        if (!mounted) return;
        setBrandName(branding.branding?.brand_name || '');
        setSupportEmail(branding.branding?.support_email || '');
        setProvidersJson(JSON.stringify(providers.providers || [], null, 2));
      })
      .catch(() => {
        if (!mounted) return;
        setMessage('Unable to load tenant branding/storage settings.');
      });
    return () => {
      mounted = false;
    };
  }, [selectedTenantId]);

  useEffect(() => {
    if (!resetResult?.temporary_password) {
      setShowTemporaryPassword(false);
      setCopiedTemporaryPassword(false);
      return;
    }
    setShowTemporaryPassword(false);
    setCopiedTemporaryPassword(false);
    const timer = window.setTimeout(() => {
      setShowTemporaryPassword(false);
    }, 60_000);
    return () => window.clearTimeout(timer);
  }, [resetResult?.temporary_password]);

  const onSaveBranding = async () => {
    if (!selectedTenantId) return;
    setSaving(true);
    setMessage('');
    try {
      await updateTenantBranding(selectedTenantId, {
        brand_name: brandName,
        support_email: supportEmail,
      });
      setMessage('Branding saved.');
    } catch {
      setMessage('Failed to save branding.');
    } finally {
      setSaving(false);
    }
  };

  const onSaveProviders = async () => {
    if (!selectedTenantId) return;
    setSaving(true);
    setMessage('');
    try {
      const parsed = JSON.parse(providersJson);
      await updateTenantStorageProviders(selectedTenantId, parsed);
      setMessage('Storage providers saved.');
    } catch {
      setMessage('Failed to save storage providers (check JSON format).');
    } finally {
      setSaving(false);
    }
  };

  const onUploadLogo = async (kind: 'primary' | 'symbol' | 'favicon', file: File | null) => {
    if (!selectedTenantId || !file) return;
    setSaving(true);
    setMessage('');
    try {
      await uploadTenantLogo(selectedTenantId, kind, file);
      setMessage(`${kind} logo uploaded.`);
    } catch {
      setMessage(`Failed to upload ${kind} logo.`);
    } finally {
      setSaving(false);
    }
  };

  const makeIdempotencyKey = (): string => {
    if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
      return `portal-reset-${crypto.randomUUID()}`;
    }
    return `portal-reset-${Date.now()}`;
  };

  const onManualPasswordReset = async () => {
    if (!selectedTenantId) return;
    const email = resetEmail.trim().toLowerCase();
    const username = resetUsername.trim().toLowerCase();
    if (!email && !username) {
      setMessage('Provide at least email or username for manual reset.');
      return;
    }
    if (resetConfirmationText.trim().toUpperCase() !== resetConfirmationPhrase) {
      setMessage(`Type ${resetConfirmationPhrase} to confirm this security action.`);
      return;
    }

    setResetBusy(true);
    setMessage('');
    setResetResult(null);
    try {
      const result = await resetTenantUserPassword(selectedTenantId, {
        email: email || undefined,
        username: username || undefined,
        reason: (resetReason || 'manual_admin_reset').trim(),
        idempotency_key: makeIdempotencyKey(),
      });
      setResetResult(result);
      setCopiedTemporaryPassword(false);
      setShowTemporaryPassword(false);
      if (result.idempotent_replay) {
        setMessage('Duplicate reset request detected and safely ignored.');
      } else if (result.reset_applied) {
        setMessage('Manual password reset completed.');
      } else {
        setMessage(result.reason || 'Manual password reset was not applied.');
      }
      setResetConfirmationText('');
    } catch {
      setMessage('Failed to perform manual password reset.');
    } finally {
      setResetBusy(false);
    }
  };

  const onCopyTemporaryPassword = async () => {
    const temp = resetResult?.temporary_password;
    if (!temp || typeof navigator === 'undefined' || !navigator.clipboard) {
      return;
    }
    try {
      await navigator.clipboard.writeText(temp);
      setCopiedTemporaryPassword(true);
      window.setTimeout(() => setCopiedTemporaryPassword(false), 2_000);
    } catch {
      setCopiedTemporaryPassword(false);
    }
  };

  if (loading) {
    return <div className="text-sm text-gray-500">Loading tenant configuration...</div>;
  }

  return (
    <div className="space-y-6">
      {isSuperAdmin && (
        <div className="card">
          <div className="mb-4 flex items-start justify-between gap-4">
            <div>
              <h2 className="text-sm font-semibold text-gray-900">Tenant onboarding (registry import)</h2>
              <p className="mt-1 text-xs text-gray-500">
                Creates/updates a tenant in the Tenant Registry. Module enablement is inferred from routing metadata.
              </p>
            </div>
            <span className="inline-flex items-center gap-2 rounded-lg bg-brand-500/10 px-3 py-2 text-xs font-medium text-brand-600">
              <Rocket className="h-4 w-4" /> Superadmin
            </span>
          </div>

          <form onSubmit={submitOnboarding} className="space-y-3">
            <div className="grid gap-3 md:grid-cols-2">
              <label className="space-y-1">
                <span className="text-xs font-medium text-gray-600">Tenant code</span>
                <input
                  className="input-field"
                  value={onboardPayload.code}
                  onChange={(e) => setOnboardPayload((p) => ({ ...p, code: e.target.value }))}
                  required
                />
              </label>
              <label className="space-y-1">
                <span className="text-xs font-medium text-gray-600">Tenant name</span>
                <input
                  className="input-field"
                  value={onboardPayload.name}
                  onChange={(e) => setOnboardPayload((p) => ({ ...p, name: e.target.value }))}
                  required
                />
              </label>
              <label className="space-y-1">
                <span className="text-xs font-medium text-gray-600">Tenant ID (optional)</span>
                <input
                  className="input-field"
                  value={onboardPayload.tenant_id}
                  onChange={(e) => setOnboardPayload((p) => ({ ...p, tenant_id: e.target.value }))}
                />
              </label>
              <label className="flex items-center gap-2 pt-6">
                <input
                  type="checkbox"
                  checked={onboardPayload.is_active}
                  onChange={(e) => setOnboardPayload((p) => ({ ...p, is_active: e.target.checked }))}
                />
                <span className="text-sm text-gray-700">Active</span>
              </label>
              <label className="space-y-1">
                <span className="text-xs font-medium text-gray-600">SRMS slug</span>
                <input
                  className="input-field"
                  value={onboardPayload.srms_slug}
                  onChange={(e) => setOnboardPayload((p) => ({ ...p, srms_slug: e.target.value }))}
                />
              </label>
              <label className="space-y-1">
                <span className="text-xs font-medium text-gray-600">SRMS schema</span>
                <input
                  className="input-field"
                  value={onboardPayload.srms_schema}
                  onChange={(e) => setOnboardPayload((p) => ({ ...p, srms_schema: e.target.value }))}
                />
              </label>
              <label className="space-y-1">
                <span className="text-xs font-medium text-gray-600">eAppraisal subdomain</span>
                <input
                  className="input-field"
                  value={onboardPayload.eappraisal_subdomain}
                  onChange={(e) => setOnboardPayload((p) => ({ ...p, eappraisal_subdomain: e.target.value }))}
                />
              </label>
              <label className="space-y-1">
                <span className="text-xs font-medium text-gray-600">eLeave subdomain</span>
                <input
                  className="input-field"
                  value={onboardPayload.eleave_subdomain}
                  onChange={(e) => setOnboardPayload((p) => ({ ...p, eleave_subdomain: e.target.value }))}
                />
              </label>
            </div>

            <button className={clsx('btn-primary', onboardBusy && 'opacity-70')} disabled={!canSubmitOnboarding} type="submit">
              {onboardBusy ? 'Importing…' : 'Import tenant'}
            </button>

            {onboardError && (
              <div className="mt-3 flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
                <AlertTriangle className="mt-0.5 h-4 w-4" /> {onboardError}
              </div>
            )}
            {onboardResult != null ? (
              <pre className="mt-3 max-h-64 overflow-auto rounded-lg bg-gray-50 p-3 text-xs text-gray-700">
                {JSON.stringify(onboardResult, null, 2) ?? ''}
              </pre>
            ) : null}
          </form>
        </div>
      )}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Tenant Management</h1>
        <p className="mt-1 text-sm text-gray-500">
          Manage tenant branding and storage stack with per-tenant isolation and secure media handling.
        </p>
      </div>

      <div className="card overflow-hidden p-0">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-gray-200 bg-gray-50">
            <tr>
              <th className="px-4 py-3 font-medium text-gray-500">Organization</th>
              <th className="px-4 py-3 font-medium text-gray-500">Code</th>
              <th className="px-4 py-3 font-medium text-gray-500">SRMS Schema</th>
              <th className="px-4 py-3 font-medium text-gray-500">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {tenants.map((t) => (
              <tr
                key={t.tenant_id}
                className={`hover:bg-gray-50 ${selectedTenantId === t.tenant_id ? 'bg-brand-50/30' : ''}`}
                onClick={() => setSelectedTenantId(t.tenant_id)}
              >
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2">
                    <Building2 className="h-4 w-4 text-gray-400" />
                    <span className="font-medium text-gray-900">{t.name}</span>
                  </div>
                </td>
                <td className="px-4 py-3 font-mono text-xs text-gray-600">{t.code}</td>
                <td className="px-4 py-3 text-xs text-gray-600">{t.srms_schema || 'N/A'}</td>
                <td className="px-4 py-3">
                  {t.is_active ? (
                    <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-xs text-emerald-700">
                      <CheckCircle className="h-3.5 w-3.5" /> active
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1 rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-600">
                      <XCircle className="h-3.5 w-3.5" /> inactive
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {selectedTenant && (
        <div className="grid gap-6 lg:grid-cols-2">
          <div className="card space-y-4">
            <h2 className="text-sm font-semibold text-gray-900">Branding ({selectedTenant.name})</h2>
            <div>
              <label className="mb-1 block text-xs font-medium text-gray-600">Brand Name</label>
              <input
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
                value={brandName}
                onChange={(e) => setBrandName(e.target.value)}
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-gray-600">Support Email</label>
              <input
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
                value={supportEmail}
                onChange={(e) => setSupportEmail(e.target.value)}
              />
            </div>
            <div className="grid gap-2 sm:grid-cols-3">
              <label className="flex cursor-pointer items-center gap-2 rounded-md border border-gray-300 px-3 py-2 text-xs text-gray-700">
                <Upload className="h-4 w-4" /> Primary
                <input type="file" className="hidden" onChange={(e) => onUploadLogo('primary', e.target.files?.[0] || null)} />
              </label>
              <label className="flex cursor-pointer items-center gap-2 rounded-md border border-gray-300 px-3 py-2 text-xs text-gray-700">
                <Upload className="h-4 w-4" /> Symbol
                <input type="file" className="hidden" onChange={(e) => onUploadLogo('symbol', e.target.files?.[0] || null)} />
              </label>
              <label className="flex cursor-pointer items-center gap-2 rounded-md border border-gray-300 px-3 py-2 text-xs text-gray-700">
                <Upload className="h-4 w-4" /> Favicon
                <input type="file" className="hidden" onChange={(e) => onUploadLogo('favicon', e.target.files?.[0] || null)} />
              </label>
            </div>
            <button className="btn-primary" disabled={saving} onClick={onSaveBranding}>
              Save Branding
            </button>
          </div>

          <div className="card space-y-4">
            <h2 className="text-sm font-semibold text-gray-900">Storage Provider Stack (JSON)</h2>
            <textarea
              className="h-64 w-full rounded-md border border-gray-300 px-3 py-2 font-mono text-xs"
              value={providersJson}
              onChange={(e) => setProvidersJson(e.target.value)}
            />
            <button className="btn-primary" disabled={saving} onClick={onSaveProviders}>
              Save Storage Providers
            </button>
          </div>

          <div className="card space-y-4 lg:col-span-2">
            <h2 className="text-sm font-semibold text-gray-900">Manual User Password Reset (Admin Only)</h2>
            <p className="text-xs text-amber-700">
              Use only for intentional credential recovery. The generated temporary password is shown once.
            </p>
            <div className="grid gap-3 md:grid-cols-2">
              <div>
                <label className="mb-1 block text-xs font-medium text-gray-600">User Email</label>
                <input
                  className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
                  value={resetEmail}
                  onChange={(e) => setResetEmail(e.target.value)}
                  placeholder="employee@example.com"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-gray-600">Username (optional)</label>
                <input
                  className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
                  value={resetUsername}
                  onChange={(e) => setResetUsername(e.target.value)}
                  placeholder="employee@example.com"
                />
              </div>
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-gray-600">Reason</label>
              <input
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
                value={resetReason}
                onChange={(e) => setResetReason(e.target.value)}
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-gray-600">
                Confirmation (type <span className="font-mono">{resetConfirmationPhrase}</span>)
              </label>
              <input
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm font-mono"
                value={resetConfirmationText}
                onChange={(e) => setResetConfirmationText(e.target.value)}
                placeholder={resetConfirmationPhrase}
                autoComplete="off"
              />
            </div>
            <button className="btn-primary" disabled={!canSubmitManualReset} onClick={onManualPasswordReset}>
              {resetBusy ? 'Resetting Password...' : 'Reset User Password'}
            </button>
            {resetResult ? (
              <div className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
                <div>
                  <span className="font-semibold">Target:</span>{' '}
                  {resetResult.target_email || resetResult.target_username || 'unknown'}
                </div>
                <div>
                  <span className="font-semibold">Applied:</span> {String(Boolean(resetResult.reset_applied))}
                </div>
                {resetResult.temporary_password ? (
                  <div className="space-y-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-semibold">Temporary Password:</span>
                      <button
                        type="button"
                        className="inline-flex items-center gap-1 rounded border border-amber-300 bg-white px-2 py-1 text-xs"
                        onClick={() => setShowTemporaryPassword((prev) => !prev)}
                      >
                        {showTemporaryPassword ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
                        {showTemporaryPassword ? 'Hide' : 'Reveal'}
                      </button>
                      <button
                        type="button"
                        className="inline-flex items-center gap-1 rounded border border-amber-300 bg-white px-2 py-1 text-xs"
                        onClick={onCopyTemporaryPassword}
                      >
                        {copiedTemporaryPassword ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
                        {copiedTemporaryPassword ? 'Copied' : 'Copy'}
                      </button>
                    </div>
                    <div className="break-all rounded border border-amber-200 bg-white p-2 font-mono text-xs">
                      {showTemporaryPassword
                        ? resetResult.temporary_password
                        : '******** ******** ********'}
                    </div>
                    <div className="text-xs">
                      Password visibility auto-hides after 60 seconds.
                    </div>
                  </div>
                ) : null}
              </div>
            ) : null}
          </div>
        </div>
      )}

      {message ? (
        <div className="rounded-md border border-gray-200 bg-gray-50 px-3 py-2 text-sm text-gray-700">{message}</div>
      ) : null}
    </div>
  );
};
