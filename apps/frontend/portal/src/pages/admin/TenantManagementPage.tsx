import React, { useEffect, useMemo, useState } from 'react';
import { Building2, Upload, CheckCircle, XCircle, Eye, EyeOff, Copy, Check, Rocket, AlertTriangle } from 'lucide-react';
import { clsx } from 'clsx';
import {
  getTenantBranding,
  importTenantOnboarding,
  resetTenantUserPassword,
  getTenantStorageProviders,
  getModuleReadinessSnapshot,
  getJitAuditSnapshot,
  listNativeTenantInventory,
  createTenantLinkClaim,
  confirmTenantLinkClaim,
  approveTenantLinkClaim,
  listTenantLinkClaims,
  listTenants,
  runFederatedKeycloakSync,
  type FederatedKeycloakSyncResponse,
  type TenantUserPasswordResetResponse,
  updateTenantBranding,
  updateTenantStorageProviders,
  uploadTenantLogo,
  type TenantRow,
  type ModuleReadinessSnapshotResponse,
  type JitAuditSnapshotResponse,
  type NativeTenantInventoryRow,
  type TenantLinkClaim,
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
    primary_admin_email: '',
    organization_email: '',
    country: 'GH',
    organization_type: 'PRIVATE',
    employee_range: '0-10',
    contact_person: '',
    phone_number: '',
    organization_nature: 'single_managed',
    subscription_plan: 'Basic',
    enabled_modules: ['srms', 'eappraisal'] as string[],
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
  const [federatedDryRun, setFederatedDryRun] = useState(true);
  const [federatedMaxUsers, setFederatedMaxUsers] = useState(50);
  const [federatedGlobalScope, setFederatedGlobalScope] = useState(false);
  const [federatedBusy, setFederatedBusy] = useState(false);
  const [federatedError, setFederatedError] = useState('');
  const [federatedResult, setFederatedResult] = useState<FederatedKeycloakSyncResponse | null>(null);
  const [federatedApplyConfirmation, setFederatedApplyConfirmation] = useState('');
  const [readinessEmail, setReadinessEmail] = useState('');
  const [readinessUsername, setReadinessUsername] = useState('');
  const [readinessEmployeeId, setReadinessEmployeeId] = useState('');
  const [readinessBusy, setReadinessBusy] = useState(false);
  const [readinessError, setReadinessError] = useState('');
  const [readinessResult, setReadinessResult] = useState<ModuleReadinessSnapshotResponse | null>(null);
  const [jitAuditModule, setJitAuditModule] = useState('');
  const [jitAuditBusy, setJitAuditBusy] = useState(false);
  const [jitAuditError, setJitAuditError] = useState('');
  const [jitAuditResult, setJitAuditResult] = useState<JitAuditSnapshotResponse | null>(null);
  const [nativeInventory, setNativeInventory] = useState<NativeTenantInventoryRow[]>([]);
  const [claimModule, setClaimModule] = useState('eappraisal');
  const [claimNativeTenantId, setClaimNativeTenantId] = useState('');
  const [claimReason, setClaimReason] = useState('Verified customer request to federate the native tenant');
  const [activeClaim, setActiveClaim] = useState<TenantLinkClaim | null>(null);
  const [claimChallenge, setClaimChallenge] = useState('');
  const [claimAssertion, setClaimAssertion] = useState('');
  const [claimBusy, setClaimBusy] = useState(false);
  const [claimError, setClaimError] = useState('');
  const [openClaims, setOpenClaims] = useState<TenantLinkClaim[]>([]);

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
    onboardPayload.primary_admin_email.trim() &&
    (!onboardPayload.enabled_modules.includes('srms') || onboardPayload.phone_number.trim()) &&
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

  useEffect(() => {
    if (!isSuperAdmin) return;
    Promise.all([listNativeTenantInventory(claimModule), listTenantLinkClaims()])
      .then(([rows, claims]) => {
        setNativeInventory(rows);
        setOpenClaims(claims.filter((claim) => ['verification_pending', 'native_confirmed'].includes(claim.state)));
        setClaimNativeTenantId((current) => current || rows.find((row) => row.inventory_status !== 'claimed')?.native_tenant_id || '');
      })
      .catch(() => setClaimError('Unable to load native tenant inventory.'));
  }, [claimModule, isSuperAdmin]);

  const beginTenantClaim = async () => {
    if (!selectedTenantId || !claimNativeTenantId) return;
    setClaimBusy(true); setClaimError('');
    try {
      const result = await createTenantLinkClaim({
        canonical_tenant_id: selectedTenantId, module_name: claimModule,
        native_tenant_id: claimNativeTenantId, reason: claimReason,
      });
      setActiveClaim(result.claim); setClaimChallenge(result.challenge); setClaimAssertion('');
      setOpenClaims((claims) => [result.claim, ...claims.filter((claim) => claim.claim_id !== result.claim.claim_id)]);
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } };
      setClaimError(e.response?.data?.detail || 'Could not create tenant claim.');
    } finally { setClaimBusy(false); }
  };

  const confirmTenantClaim = async () => {
    if (!activeClaim || !claimAssertion.trim()) return;
    setClaimBusy(true); setClaimError('');
    try {
      const result = await confirmTenantLinkClaim(activeClaim.claim_id, claimAssertion.trim());
      setActiveClaim(result.claim);
      setOpenClaims((claims) => claims.map((claim) => claim.claim_id === result.claim.claim_id ? result.claim : claim));
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } };
      setClaimError(e.response?.data?.detail || 'Native assertion was rejected.');
    } finally { setClaimBusy(false); }
  };

  const approveTenantClaim = async () => {
    if (!activeClaim) return;
    setClaimBusy(true); setClaimError('');
    try {
      await approveTenantLinkClaim(activeClaim.claim_id, claimReason);
      setActiveClaim({ ...activeClaim, state: 'approved' });
      setOpenClaims((claims) => claims.filter((claim) => claim.claim_id !== activeClaim.claim_id));
      setClaimChallenge(''); setClaimAssertion('');
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } };
      setClaimError(e.response?.data?.detail || 'A different superadmin must approve the confirmed claim.');
    } finally { setClaimBusy(false); }
  };

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
        primary_admin_email: onboardPayload.primary_admin_email.trim(),
        organization_email: onboardPayload.organization_email.trim() || onboardPayload.primary_admin_email.trim(),
      };
      const response = await importTenantOnboarding(cleaned);
      setOnboardResult(response);
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

  const onRunFederatedSync = async () => {
    if (!federatedDryRun && federatedApplyConfirmation.trim().toUpperCase() !== 'APPLY') {
      setFederatedError('Type APPLY to confirm non-dry-run sync.');
      return;
    }
    setFederatedBusy(true);
    setFederatedError('');
    setFederatedResult(null);
    try {
      const payload = await runFederatedKeycloakSync({
        tenant_id: federatedGlobalScope ? undefined : (selectedTenantId || undefined),
        dry_run: federatedDryRun,
        max_users: Math.max(1, Number(federatedMaxUsers) || 1),
      });
      setFederatedResult(payload);
      setMessage(
        federatedDryRun
          ? 'Federated Keycloak dry-run completed.'
          : 'Federated Keycloak sync completed.'
      );
      if (!federatedDryRun) {
        setFederatedApplyConfirmation('');
      }
    } catch (err: unknown) {
      const maybeAxios = err as {
        response?: { status?: number; data?: { detail?: string; message?: string } };
        message?: string;
      };
      const status = maybeAxios?.response?.status;
      const detail =
        maybeAxios?.response?.data?.detail ||
        maybeAxios?.response?.data?.message ||
        maybeAxios?.message ||
        'Unknown error';
      setFederatedError(
        `Failed to run federated Keycloak sync (${status ?? 'no-status'}): ${detail}`
      );
    } finally {
      setFederatedBusy(false);
    }
  };

  const onRunModuleReadiness = async () => {
    setReadinessBusy(true);
    setReadinessError('');
    setReadinessResult(null);
    try {
      const payload = await getModuleReadinessSnapshot({
        tenant_id: selectedTenantId || undefined,
        email: readinessEmail.trim() || undefined,
        username: readinessUsername.trim() || undefined,
        employee_id: readinessEmployeeId.trim() || undefined,
      });
      setReadinessResult(payload);
    } catch (err: unknown) {
      const maybeAxios = err as { response?: { data?: { detail?: string } }; message?: string };
      setReadinessError(maybeAxios?.response?.data?.detail || maybeAxios?.message || 'Failed to load module readiness snapshot');
    } finally {
      setReadinessBusy(false);
    }
  };

  const onRunJitAudit = async () => {
    setJitAuditBusy(true);
    setJitAuditError('');
    setJitAuditResult(null);
    try {
      const payload = await getJitAuditSnapshot({
        tenant_id: selectedTenantId || undefined,
        module_name: jitAuditModule.trim() || undefined,
        limit: 50,
      });
      setJitAuditResult(payload);
    } catch (err: unknown) {
      const maybeAxios = err as { response?: { data?: { detail?: string } }; message?: string };
      setJitAuditError(maybeAxios?.response?.data?.detail || maybeAxios?.message || 'Failed to load JIT audit history');
    } finally {
      setJitAuditBusy(false);
    }
  };

  if (loading) {
    return <div className="text-sm text-gray-500">Loading tenant configuration...</div>;
  }

  return (
    <div className="space-y-6">
      {isSuperAdmin && (
        <div className="card space-y-4">
          <div>
            <h2 className="text-sm font-semibold text-gray-900">Legacy native tenant claim</h2>
            <p className="mt-1 text-xs text-gray-500">
              Names are discovery hints only. Select the exact native ID, obtain a signed assertion from an authority in that native tenant, then have a different HRIS superadmin approve it.
            </p>
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            <select className="input-field" value={claimModule} onChange={(e) => { setClaimModule(e.target.value); setClaimNativeTenantId(''); }}>
              <option value="srms">Staff Records</option><option value="eappraisal">Performance Appraisal</option>
            </select>
            <select className="input-field" value={claimNativeTenantId} onChange={(e) => setClaimNativeTenantId(e.target.value)}>
              <option value="">Select an unclaimed native tenant</option>
              {nativeInventory.map((row) => <option key={`${row.module_name}:${row.native_tenant_id}`} value={row.native_tenant_id}>{row.display_name} — {row.native_tenant_id} ({row.inventory_status})</option>)}
            </select>
          </div>
          <textarea className="input-field min-h-20" value={claimReason} onChange={(e) => setClaimReason(e.target.value)} aria-label="Claim reason" />
          <button type="button" className="btn-primary" disabled={claimBusy || !selectedTenantId || !claimNativeTenantId} onClick={beginTenantClaim}>Create verification challenge</button>
          {openClaims.length > 0 && <div className="space-y-2"><div className="text-xs font-medium">Open claims (select one to continue or approve)</div>{openClaims.map((claim) => <button type="button" className="block w-full rounded border border-gray-200 p-2 text-left text-xs" key={claim.claim_id} onClick={() => { setActiveClaim(claim); setClaimChallenge(''); setClaimAssertion(''); }}><span className="font-mono">{claim.claim_id}</span> — {claim.module_name} — {claim.state}</button>)}</div>}
          {activeClaim && <div className="rounded border border-gray-200 p-3 text-xs"><div>Claim: <span className="font-mono">{activeClaim.claim_id}</span></div><div>State: {activeClaim.state}</div></div>}
          {claimChallenge && <div><label className="text-xs font-medium">One-time challenge (expires in five minutes)</label><textarea readOnly className="input-field mt-1 min-h-20 font-mono text-xs" value={claimChallenge} /></div>}
          {activeClaim?.state === 'verification_pending' && <div className="space-y-2"><label className="text-xs font-medium">Signed assertion returned by the native tenant authority</label><textarea className="input-field min-h-24 font-mono text-xs" value={claimAssertion} onChange={(e) => setClaimAssertion(e.target.value)} /><button type="button" className="btn-secondary" disabled={claimBusy || !claimAssertion.trim()} onClick={confirmTenantClaim}>Verify native assertion</button></div>}
          {activeClaim?.state === 'native_confirmed' && <button type="button" className="btn-primary" disabled={claimBusy} onClick={approveTenantClaim}>Approve as second superadmin</button>}
          {claimError && <div className="rounded border border-red-200 bg-red-50 p-2 text-xs text-red-700">{String(claimError)}</div>}
        </div>
      )}
      {isSuperAdmin && (
        <div className="card">
          <div className="mb-4 flex items-start justify-between gap-4">
            <div>
              <h2 className="text-sm font-semibold text-gray-900">Tenant onboarding and module federation</h2>
              <p className="mt-1 text-xs text-gray-500">
                Creates a canonical tenant or provisions missing native modules for the explicitly selected tenant.
              </p>
            </div>
            <span className="inline-flex items-center gap-2 rounded-lg bg-brand-500/10 px-3 py-2 text-xs font-medium text-brand-600">
              <Rocket className="h-4 w-4" /> Superadmin
            </span>
          </div>

          <form onSubmit={submitOnboarding} className="space-y-3">
            {selectedTenant && (
              <button
                type="button"
                className="btn-secondary"
                onClick={() => setOnboardPayload((p) => ({
                  ...p,
                  tenant_id: selectedTenant.tenant_id,
                  code: selectedTenant.code,
                  name: selectedTenant.name,
                  is_active: selectedTenant.is_active,
                }))}
              >
                Federate selected tenant by canonical ID
              </button>
            )}
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
                <span className="text-xs font-medium text-gray-600">Primary administrator email</span>
                <input
                  className="input-field"
                  type="email"
                  value={onboardPayload.primary_admin_email}
                  onChange={(e) => setOnboardPayload((p) => ({ ...p, primary_admin_email: e.target.value }))}
                  required
                />
              </label>
              <label className="space-y-1">
                <span className="text-xs font-medium text-gray-600">Contact person</span>
                <input
                  className="input-field"
                  value={onboardPayload.contact_person}
                  onChange={(e) => setOnboardPayload((p) => ({ ...p, contact_person: e.target.value }))}
                  placeholder="Tenant administrator"
                />
              </label>
              <label className="space-y-1">
                <span className="text-xs font-medium text-gray-600">Contact phone</span>
                <input
                  className="input-field"
                  type="tel"
                  value={onboardPayload.phone_number}
                  onChange={(e) => setOnboardPayload((p) => ({ ...p, phone_number: e.target.value }))}
                  required={onboardPayload.enabled_modules.includes('srms')}
                  placeholder="Required for Staff Records"
                />
              </label>
              <label className="space-y-1">
                <span className="text-xs font-medium text-gray-600">Organization email</span>
                <input
                  className="input-field"
                  type="email"
                  value={onboardPayload.organization_email}
                  onChange={(e) => setOnboardPayload((p) => ({ ...p, organization_email: e.target.value }))}
                  placeholder="Defaults to administrator email"
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
                <span className="text-xs font-medium text-gray-600">Country</span>
                <input className="input-field" value={onboardPayload.country} onChange={(e) => setOnboardPayload((p) => ({ ...p, country: e.target.value }))} />
              </label>
              <label className="space-y-1">
                <span className="text-xs font-medium text-gray-600">Organization type</span>
                <select className="input-field" value={onboardPayload.organization_type} onChange={(e) => setOnboardPayload((p) => ({ ...p, organization_type: e.target.value }))}>
                  <option value="PRIVATE">Private</option>
                  <option value="PUBLIC">Public</option>
                  <option value="CIVIL">Civil</option>
                  <option value="NGO">NGO</option>
                </select>
              </label>
              <fieldset className="space-y-2 md:col-span-2">
                <legend className="text-xs font-medium text-gray-600">Modules to provision</legend>
                <div className="flex flex-wrap gap-4">
                  {[
                    ['srms', 'Staff Records'],
                    ['eappraisal', 'Performance Appraisal'],
                    ['eleave', 'Leave Management'],
                  ].map(([id, label]) => (
                    <label key={id} className="flex items-center gap-2 text-sm text-gray-700">
                      <input
                        type="checkbox"
                        checked={onboardPayload.enabled_modules.includes(id)}
                        onChange={(e) => setOnboardPayload((p) => ({
                          ...p,
                          enabled_modules: e.target.checked
                            ? [...p.enabled_modules, id]
                            : p.enabled_modules.filter((value) => value !== id),
                        }))}
                      />
                      {label}
                    </label>
                  ))}
                </div>
                <p className="text-xs text-gray-500">HRIS generates canonical and native routing identifiers; names and codes are never used to match tenants.</p>
              </fieldset>
            </div>

            <button className={clsx('btn-primary', onboardBusy && 'opacity-70')} disabled={!canSubmitOnboarding} type="submit">
              {onboardBusy ? 'Provisioning…' : onboardPayload.tenant_id ? 'Provision selected tenant' : 'Create and provision tenant'}
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
      {isSuperAdmin && (
        <div className="card">
          <div className="mb-4 flex items-start justify-between gap-4">
            <div>
              <h2 className="text-sm font-semibold text-gray-900">Federated Keycloak Sync (email-only)</h2>
              <p className="mt-1 text-xs text-gray-500">
                Uses federated inventory users with valid emails. No module provisioning is performed.
              </p>
            </div>
            <span className="inline-flex items-center gap-2 rounded-lg bg-brand-500/10 px-3 py-2 text-xs font-medium text-brand-600">
              <Rocket className="h-4 w-4" /> Superadmin
            </span>
          </div>

          <div className="grid gap-3 md:grid-cols-3">
            <label className="space-y-1">
              <span className="text-xs font-medium text-gray-600">Scope tenant</span>
              <select
                className="input-field"
                value={selectedTenantId}
                onChange={(e) => setSelectedTenantId(e.target.value)}
                disabled={federatedGlobalScope}
              >
                {tenants.map((t) => (
                  <option key={t.tenant_id} value={t.tenant_id}>
                    {t.name} ({t.code})
                  </option>
                ))}
              </select>
            </label>
            <label className="space-y-1">
              <span className="text-xs font-medium text-gray-600">Max users per run</span>
              <input
                className="input-field"
                type="number"
                min={1}
                value={federatedMaxUsers}
                onChange={(e) => setFederatedMaxUsers(Number(e.target.value) || 1)}
              />
            </label>
            <label className="flex items-center gap-2 pt-6">
              <input
                type="checkbox"
                checked={federatedDryRun}
                onChange={(e) => setFederatedDryRun(e.target.checked)}
              />
              <span className="text-sm text-gray-700">Dry run (recommended)</span>
            </label>
            <label className="flex items-center gap-2 pt-0 md:pt-6">
              <input
                type="checkbox"
                checked={federatedGlobalScope}
                onChange={(e) => setFederatedGlobalScope(e.target.checked)}
              />
              <span className="text-sm text-gray-700">Global scope (all tenants)</span>
            </label>
          </div>

          <div className="mt-3">
            {!federatedDryRun ? (
              <div className="mb-3 rounded-md border border-amber-200 bg-amber-50 p-3">
                <label className="mb-1 block text-xs font-medium text-amber-900">
                  Confirmation required (type <span className="font-mono">APPLY</span>)
                </label>
                <input
                  className="input-field"
                  value={federatedApplyConfirmation}
                  onChange={(e) => setFederatedApplyConfirmation(e.target.value)}
                  placeholder="APPLY"
                  autoComplete="off"
                />
              </div>
            ) : null}
            <button
              className="btn-primary"
              disabled={
                federatedBusy ||
                (!federatedGlobalScope && !selectedTenantId) ||
                (!federatedDryRun && federatedApplyConfirmation.trim().toUpperCase() !== 'APPLY')
              }
              onClick={onRunFederatedSync}
            >
              {federatedBusy ? 'Running...' : federatedDryRun ? 'Run Dry-Run Sync' : 'Run Apply Sync'}
            </button>
          </div>

          {federatedError ? (
            <div className="mt-3 flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
              <AlertTriangle className="mt-0.5 h-4 w-4" /> {federatedError}
            </div>
          ) : null}

          {federatedResult ? (
            <div className="mt-4 space-y-3">
              <div className="grid gap-2 text-xs text-gray-700 md:grid-cols-3">
                <div className="rounded-md border border-gray-200 bg-gray-50 p-2">processed_users: {federatedResult.processed_users}</div>
                <div className="rounded-md border border-gray-200 bg-gray-50 p-2">created_count: {federatedResult.created_count}</div>
                <div className="rounded-md border border-gray-200 bg-gray-50 p-2">existing_count: {federatedResult.existing_count}</div>
                <div className="rounded-md border border-gray-200 bg-gray-50 p-2">failed_count: {federatedResult.failed_count}</div>
                <div className="rounded-md border border-gray-200 bg-gray-50 p-2">skipped_missing_email: {federatedResult.skipped_missing_email}</div>
                <div className="rounded-md border border-gray-200 bg-gray-50 p-2">
                  skipped_no_temporary_password: {federatedResult.skipped_no_temporary_password ?? 0}
                </div>
                <div className="rounded-md border border-gray-200 bg-gray-50 p-2">dry_run: {String(federatedResult.dry_run)}</div>
                <div className="rounded-md border border-gray-200 bg-gray-50 p-2">
                  welcome_emails_sent: {federatedResult.welcome_emails_sent ?? 0}
                </div>
                <div className="rounded-md border border-gray-200 bg-gray-50 p-2">
                  welcome_emails_skipped: {federatedResult.welcome_emails_skipped ?? 0}
                </div>
              </div>
              {federatedResult.tenant_discovery?.length ? (
                <div className="overflow-auto rounded-lg border border-gray-200">
                  <table className="w-full text-left text-xs">
                    <thead className="bg-gray-50 text-gray-600"><tr><th className="px-3 py-2">Tenant</th><th className="px-3 py-2">Users</th><th className="px-3 py-2">Module inventory readiness</th></tr></thead>
                    <tbody className="divide-y divide-gray-100 bg-white">
                      {federatedResult.tenant_discovery.map((row, idx) => (
                        <tr key={`${row.tenant.tenant_id || 'tenant'}-${idx}`}>
                          <td className="px-3 py-2"><div className="font-medium">{row.tenant.name || row.tenant.code}</div><div className="font-mono text-[10px] text-gray-500">{row.tenant.tenant_id}</div></td>
                          <td className="px-3 py-2">{row.summary.users_total ?? 0}</td>
                          <td className="px-3 py-2">
                            <div className="flex flex-wrap gap-1">
                              {Object.entries(row.module_status || {}).map(([module, state]) => (
                                <span key={module} title={state.detail || ''} className={clsx('rounded-full px-2 py-0.5', state.status === 'ok' ? 'bg-emerald-100 text-emerald-700' : state.status === 'not_present' ? 'bg-gray-100 text-gray-600' : 'bg-amber-100 text-amber-800')}>
                                  {module}: {state.status}
                                </span>
                              ))}
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : null}
              {federatedResult.dev_credentials_exports?.length ? (
                <div className="rounded-md border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900">
                  <div className="mb-1 font-semibold">Development credential exports</div>
                  <ul className="space-y-1 font-mono">
                    {federatedResult.dev_credentials_exports.map((p) => (
                      <li key={p}>{p}</li>
                    ))}
                  </ul>
                </div>
              ) : null}
              <div className="max-h-72 overflow-auto rounded-lg border border-gray-200">
                <table className="w-full text-left text-xs">
                  <thead className="sticky top-0 bg-gray-50 text-gray-600">
                    <tr>
                      <th className="px-3 py-2 font-medium">Tenant</th>
                      <th className="px-3 py-2 font-medium">Email</th>
                      <th className="px-3 py-2 font-medium">Status</th>
                      <th className="px-3 py-2 font-medium">Keycloak ID</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100 bg-white">
                    {federatedResult.results.slice(0, 100).map((row, idx) => (
                      <tr key={`${row.tenant_id}-${row.email}-${idx}`}>
                        <td className="px-3 py-2 font-mono text-[11px] text-gray-700">{row.tenant_id}</td>
                        <td className="px-3 py-2 text-gray-700">{row.email || '-'}</td>
                        <td className="px-3 py-2">
                          <span
                            className={clsx(
                              'inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium',
                              row.status === 'created' && 'bg-emerald-100 text-emerald-700',
                              row.status === 'existing' && 'bg-blue-100 text-blue-700',
                              row.status === 'dry_run' && 'bg-amber-100 text-amber-700',
                              row.status === 'failed' && 'bg-red-100 text-red-700',
                              row.status === 'skipped_missing_email' && 'bg-gray-200 text-gray-700'
                            )}
                          >
                            {row.status}
                          </span>
                        </td>
                        <td className="px-3 py-2 font-mono text-[11px] text-gray-600">{row.keycloak_user_id || '-'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ) : null}
        </div>
      )}
      {isSuperAdmin && (
        <div className="card">
          <div className="mb-4 flex items-start justify-between gap-4">
            <div>
              <h2 className="text-sm font-semibold text-gray-900">Module Readiness (tenant + user)</h2>
              <p className="mt-1 text-xs text-gray-500">
                Validates runtime readiness for SRMS, Appraisal, and eLeave with optional user identity hints.
              </p>
            </div>
          </div>
          <div className="grid gap-3 md:grid-cols-4">
            <input className="input-field" placeholder="Email (optional)" value={readinessEmail} onChange={(e) => setReadinessEmail(e.target.value)} />
            <input className="input-field" placeholder="Username (optional)" value={readinessUsername} onChange={(e) => setReadinessUsername(e.target.value)} />
            <input className="input-field" placeholder="Employee ID (optional)" value={readinessEmployeeId} onChange={(e) => setReadinessEmployeeId(e.target.value)} />
            <button className="btn-primary" onClick={onRunModuleReadiness} disabled={readinessBusy || !selectedTenantId}>
              {readinessBusy ? 'Checking...' : 'Check Readiness'}
            </button>
          </div>
          {readinessError ? (
            <div className="mt-3 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">{readinessError}</div>
          ) : null}
          {readinessResult ? (
            <div className="mt-3 rounded-lg border border-gray-200 bg-gray-50 p-3 text-xs">
              <div className="mb-2 text-gray-700">
                Tenant: <span className="font-mono">{readinessResult.tenant.tenant_id}</span> ({readinessResult.tenant.code})
              </div>
              <div className="space-y-2">
                {Object.entries(readinessResult.modules || {}).map(([module, rs]) => (
                  <div key={module} className="rounded border border-gray-200 bg-white p-2">
                    <div className="font-semibold text-gray-800">{module}</div>
                    <div className="text-gray-600">ready: {String(Boolean(rs.ready))}</div>
                    <div className="text-gray-600">code: {String(rs.code || '')}</div>
                    <div className="text-gray-600">detail: {String(rs.detail || '')}</div>
                  </div>
                ))}
              </div>
            </div>
          ) : null}
        </div>
      )}
      {isSuperAdmin && (
        <div className="card">
          <div className="mb-4 flex items-start justify-between gap-4">
            <div>
              <h2 className="text-sm font-semibold text-gray-900">JIT Audit & Cooldown</h2>
              <p className="mt-1 text-xs text-gray-500">
                View recent JIT setup outcomes, idempotency keys, and active cooldown state for the selected tenant.
              </p>
            </div>
          </div>
          <div className="grid gap-3 md:grid-cols-3">
            <input
              className="input-field"
              placeholder="Module filter: eappraisal/eleave (optional)"
              value={jitAuditModule}
              onChange={(e) => setJitAuditModule(e.target.value)}
            />
            <div />
            <button className="btn-primary" onClick={onRunJitAudit} disabled={jitAuditBusy || !selectedTenantId}>
              {jitAuditBusy ? 'Loading...' : 'Load JIT Audit'}
            </button>
          </div>
          {jitAuditError ? (
            <div className="mt-3 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">{jitAuditError}</div>
          ) : null}
          {jitAuditResult ? (
            <div className="mt-3 space-y-3">
              <div className="rounded-md border border-gray-200 bg-gray-50 p-2 text-xs text-gray-700">
                rows_count: {jitAuditResult.rows_count} | cooldown_settings: {jitAuditResult.cooldown_settings?.length || 0}
              </div>
              {jitAuditResult.tenant_links?.length ? (
                <div className="rounded-md border border-gray-200 bg-gray-50 p-2 text-xs text-gray-700">
                  <div className="mb-1 font-semibold">Tenant link ledger</div>
                  <div className="space-y-1">
                    {jitAuditResult.tenant_links.map((link, idx) => (
                      <div key={`${link.target_module}-${idx}`} className="font-mono">
                        {link.target_module}: {link.decision} ({link.target_tenant_ref || 'none'})
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}
              <div className="max-h-56 overflow-auto rounded-lg border border-gray-200">
                <table className="w-full text-left text-xs">
                  <thead className="sticky top-0 bg-gray-50 text-gray-600">
                    <tr>
                      <th className="px-3 py-2 font-medium">Time</th>
                      <th className="px-3 py-2 font-medium">Module</th>
                      <th className="px-3 py-2 font-medium">Status</th>
                      <th className="px-3 py-2 font-medium">Tenant Decision</th>
                      <th className="px-3 py-2 font-medium">Email</th>
                      <th className="px-3 py-2 font-medium">Idempotency</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100 bg-white">
                    {jitAuditResult.rows.slice(0, 100).map((row, idx) => (
                      <tr key={`${row.run_id || 'run'}-${idx}`}>
                        <td className="px-3 py-2 text-gray-700">{row.created_at || '-'}</td>
                        <td className="px-3 py-2 text-gray-700">{row.module_name}</td>
                        <td className="px-3 py-2 text-gray-700">{row.status}</td>
                        <td className="px-3 py-2 text-gray-700">
                          {String(
                            ((row.payload_json as { tenant_decision?: { decision?: string } } | undefined)?.tenant_decision
                              ?.decision) || '-'
                          )}
                        </td>
                        <td className="px-3 py-2 text-gray-700">{row.email || '-'}</td>
                        <td className="px-3 py-2 font-mono text-[11px] text-gray-600">{row.idempotency_key || '-'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ) : null}
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
