import React, { useEffect, useMemo, useState } from 'react';
import { Building2, Upload, CheckCircle, XCircle } from 'lucide-react';
import {
  getTenantBranding,
  getTenantStorageProviders,
  listTenants,
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
  const [tenants, setTenants] = useState<TenantRow[]>([]);
  const [selectedTenantId, setSelectedTenantId] = useState('');
  const [brandName, setBrandName] = useState('');
  const [supportEmail, setSupportEmail] = useState('');
  const [providersJson, setProvidersJson] = useState('[{"name":"s3","config":{}},{"name":"local","config":{}}]');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string>('');

  const selectedTenant = useMemo(
    () => tenants.find((t) => t.tenant_id === selectedTenantId) || null,
    [tenants, selectedTenantId]
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

  if (loading) {
    return <div className="text-sm text-gray-500">Loading tenant configuration...</div>;
  }

  return (
    <div className="space-y-6">
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
        </div>
      )}

      {message ? (
        <div className="rounded-md border border-gray-200 bg-gray-50 px-3 py-2 text-sm text-gray-700">{message}</div>
      ) : null}
    </div>
  );
};
