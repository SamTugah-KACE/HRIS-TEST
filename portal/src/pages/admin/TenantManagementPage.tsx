import React from 'react';
import { Building2, Globe, CheckCircle, XCircle } from 'lucide-react';

type TenantRow = {
  name: string;
  code: string;
  modules: { srms: boolean; eappraisal: boolean; eleave: boolean };
  status: 'active' | 'inactive';
};

const DEMO_TENANTS: TenantRow[] = [
  { name: 'GI-KACE', code: 'GI-KACE', modules: { srms: true, eappraisal: true, eleave: true }, status: 'active' },
  { name: 'Development Tenant', code: 'DEV-TENANT', modules: { srms: true, eappraisal: true, eleave: true }, status: 'active' },
  { name: 'Ministry of Finance', code: 'MOF', modules: { srms: true, eappraisal: false, eleave: true }, status: 'active' },
  { name: 'Test Organization', code: 'TEST-ORG', modules: { srms: true, eappraisal: true, eleave: false }, status: 'inactive' },
];

export const TenantManagementPage: React.FC = () => {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Tenant Management</h1>
        <p className="mt-1 text-sm text-gray-500">
          Manage organizations (tenants) and their module configurations. Each tenant maps to specific
          schemas/databases in each production module.
        </p>
      </div>

      <div className="card overflow-hidden p-0">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-gray-200 bg-gray-50">
            <tr>
              <th className="px-4 py-3 font-medium text-gray-500">Organization</th>
              <th className="px-4 py-3 font-medium text-gray-500">Code</th>
              <th className="px-4 py-3 font-medium text-gray-500">SRMS</th>
              <th className="px-4 py-3 font-medium text-gray-500">eAppraisal</th>
              <th className="px-4 py-3 font-medium text-gray-500">eLeave</th>
              <th className="px-4 py-3 font-medium text-gray-500">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {DEMO_TENANTS.map(t => (
              <tr key={t.code} className="hover:bg-gray-50">
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2">
                    <Building2 className="h-4 w-4 text-gray-400" />
                    <span className="font-medium text-gray-900">{t.name}</span>
                  </div>
                </td>
                <td className="px-4 py-3 font-mono text-xs text-gray-600">{t.code}</td>
                <td className="px-4 py-3">
                  {t.modules.srms
                    ? <CheckCircle className="h-4 w-4 text-emerald-500" />
                    : <XCircle className="h-4 w-4 text-gray-300" />}
                </td>
                <td className="px-4 py-3">
                  {t.modules.eappraisal
                    ? <CheckCircle className="h-4 w-4 text-emerald-500" />
                    : <XCircle className="h-4 w-4 text-gray-300" />}
                </td>
                <td className="px-4 py-3">
                  {t.modules.eleave
                    ? <CheckCircle className="h-4 w-4 text-emerald-500" />
                    : <XCircle className="h-4 w-4 text-gray-300" />}
                </td>
                <td className="px-4 py-3">
                  <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${
                    t.status === 'active' ? 'bg-emerald-50 text-emerald-700' : 'bg-gray-100 text-gray-600'
                  }`}>
                    {t.status}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card">
        <h2 className="mb-2 text-sm font-semibold text-gray-900">Tenant Registry</h2>
        <p className="text-sm text-gray-500">
          The Tenant Registry service maintains the canonical mapping between global tenant IDs and each module's
          native tenant identifier (SRMS schema, eAppraisal subdomain, eLeave database name). When a user logs in via
          Keycloak, their <code className="rounded bg-gray-100 px-1 text-xs">tenant_id</code> claim is used to look up
          these mappings, ensuring tenant isolation across all modules.
        </p>
      </div>
    </div>
  );
};
