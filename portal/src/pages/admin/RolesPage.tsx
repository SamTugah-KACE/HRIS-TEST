import React from 'react';
import { Shield, Users, ChevronRight } from 'lucide-react';

type ConsolidatedRole = {
  hrisRole: string;
  label: string;
  srmsMapping: string[];
  eappraisalMapping: string[];
  eleaveMapping: string[];
  description: string;
};

const ROLE_MAPPINGS: ConsolidatedRole[] = [
  {
    hrisRole: 'hris:super_admin',
    label: 'Super Admin',
    srmsMapping: ['Super Admin', 'superadmin'],
    eappraisalMapping: ['System Admin (public)'],
    eleaveMapping: ['SuperAdmin (tenant mgmt)'],
    description: 'Full system access. Can manage tenants, all modules, and all users across the platform.',
  },
  {
    hrisRole: 'hris:tenant_admin',
    label: 'Tenant Admin',
    srmsMapping: ['Admin', 'CEO'],
    eappraisalMapping: ['SYSTEM ADMINISTRATOR'],
    eleaveMapping: ['Admin'],
    description: 'Full access within a tenant. Can configure org structure, roles, and all HR modules.',
  },
  {
    hrisRole: 'hris:hr_manager',
    label: 'HR Manager',
    srmsMapping: ['HR Manager', 'Branch Manager'],
    eappraisalMapping: ['HUMAN RESOURCE'],
    eleaveMapping: ['HR'],
    description: 'Manages all HR functions — staff records, appraisals, leaves, reports, and roles.',
  },
  {
    hrisRole: 'hris:line_manager',
    label: 'Line Manager',
    srmsMapping: ['Manager', 'Department Head', 'HoD'],
    eappraisalMapping: ['STAFF (with review permissions)'],
    eleaveMapping: ['DG', 'Director'],
    description: 'Manages direct reports. Can review appraisals, approve/recommend leave for team members.',
  },
  {
    hrisRole: 'hris:employee',
    label: 'Employee',
    srmsMapping: ['Employee', 'Staff'],
    eappraisalMapping: ['STAFF'],
    eleaveMapping: ['Normal'],
    description: 'Self-service access — view profile, submit appraisals, apply for leave.',
  },
];

export const RolesPage: React.FC = () => {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Roles & Permissions</h1>
        <p className="mt-1 text-sm text-gray-500">
          Consolidated HRIS role model mapping Keycloak roles to each production module's native roles.
        </p>
      </div>

      <div className="card">
        <h2 className="mb-2 text-sm font-semibold text-gray-900">How Role Consolidation Works</h2>
        <p className="text-sm text-gray-500">
          Each user is assigned an HRIS role in Keycloak. When the HRIS Portal calls a production module's API,
          the module uses its own native RBAC to enforce fine-grained permissions. The table below shows how HRIS
          roles map to each module's native roles for reference.
        </p>
      </div>

      <div className="space-y-4">
        {ROLE_MAPPINGS.map(rm => (
          <div key={rm.hrisRole} className="card">
            <div className="flex items-start gap-4">
              <div className="rounded-lg bg-brand-500/10 p-2.5">
                <Shield className="h-5 w-5 text-brand-500" />
              </div>
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <h3 className="text-base font-semibold text-gray-900">{rm.label}</h3>
                  <code className="rounded bg-gray-100 px-2 py-0.5 text-xs text-gray-600">{rm.hrisRole}</code>
                </div>
                <p className="mt-1 text-sm text-gray-500">{rm.description}</p>

                <div className="mt-4 grid gap-3 sm:grid-cols-3">
                  <div className="rounded-lg border border-blue-100 bg-blue-50/50 p-3">
                    <p className="text-xs font-medium text-blue-600">SRMS Roles</p>
                    <div className="mt-1 flex flex-wrap gap-1">
                      {rm.srmsMapping.map(r => (
                        <span key={r} className="inline-flex rounded bg-blue-100 px-1.5 py-0.5 text-xs text-blue-700">{r}</span>
                      ))}
                    </div>
                  </div>
                  <div className="rounded-lg border border-purple-100 bg-purple-50/50 p-3">
                    <p className="text-xs font-medium text-purple-600">eAppraisal Roles</p>
                    <div className="mt-1 flex flex-wrap gap-1">
                      {rm.eappraisalMapping.map(r => (
                        <span key={r} className="inline-flex rounded bg-purple-100 px-1.5 py-0.5 text-xs text-purple-700">{r}</span>
                      ))}
                    </div>
                  </div>
                  <div className="rounded-lg border border-emerald-100 bg-emerald-50/50 p-3">
                    <p className="text-xs font-medium text-emerald-600">eLeave Roles</p>
                    <div className="mt-1 flex flex-wrap gap-1">
                      {rm.eleaveMapping.map(r => (
                        <span key={r} className="inline-flex rounded bg-emerald-100 px-1.5 py-0.5 text-xs text-emerald-700">{r}</span>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
