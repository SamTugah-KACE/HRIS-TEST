import React, { useEffect, useState } from 'react';
import {
  User, Mail, Phone, MapPin, Calendar, Briefcase, GraduationCap,
  Shield, Heart, FileText, Pencil, Save, X, Camera, Download,
  Award, Clock, CheckCircle, AlertCircle, ChevronRight,
} from 'lucide-react';
import { clsx } from 'clsx';
import { getModulesCatalog, getMyProfile, type ProfileDataResponse } from '../api/hrisCoreClient';
import { httpClient } from '../api/httpClient';
import { isApiDataMode } from '../config/dataMode';
import { getModuleModeHint } from '../shared/moduleMode';

type TabId = 'personal' | 'employment' | 'qualifications' | 'emergency' | 'documents';
type PreviousPosition = { title: string; department: string; from: string; to: string };
type Qualification = { type: string; title: string; institution: string; year: string; grade: string };
type EmergencyContact = { name: string; relationship: string; phone: string; email: string; isPrimary: boolean };
type ProfileDocument = { name: string; category: string; type: string; size: string; uploadedAt: string };

const TABS: { id: TabId; label: string; icon: React.FC<{ className?: string }> }[] = [
  { id: 'personal', label: 'Personal Info', icon: User },
  { id: 'employment', label: 'Employment', icon: Briefcase },
  { id: 'qualifications', label: 'Qualifications', icon: GraduationCap },
  { id: 'emergency', label: 'Emergency Contacts', icon: Heart },
  { id: 'documents', label: 'Documents', icon: FileText },
];

const PROFILE = {
  firstName: '', lastName: '', otherNames: '',
  staffId: '', email: '',
  phone: '', personalEmail: '',
  dateOfBirth: '', gender: '', maritalStatus: '',
  nationality: '', ghanaCardNo: '',
  ssnitNo: '', tinNo: '',
  residentialAddress: '',
  digitalAddress: '',
};

const EMPLOYMENT = {
  organization: '', branch: '',
  department: '', unit: '',
  position: '', rank: '',
  employeeType: '', hireDate: '',
  confirmationDate: '', status: '',
  supervisorName: '', supervisorTitle: '',
  gradeLevel: '', salaryStep: '',
  previousPositions: [] as PreviousPosition[],
};

const QUALIFICATIONS: Qualification[] = [];

const EMERGENCY_CONTACTS: EmergencyContact[] = [];

const DOCUMENTS: ProfileDocument[] = [];

const isHonorific = (value: unknown): boolean => {
  const raw = String(value ?? '').trim().toLowerCase();
  const compact = raw.replace(/[^a-z0-9]/g, '');
  return ['mr', 'mrs', 'ms', 'miss', 'dr', 'prof', 'phd'].includes(compact);
};

function InfoRow({ icon: Icon, label, value, editable, editing }: {
  icon: React.FC<{ className?: string }>; label: string; value: string;
  editable?: boolean; editing?: boolean;
}) {
  return (
    <div className="flex items-start gap-3 py-2.5">
      <Icon className="mt-0.5 h-4 w-4 shrink-0 text-gray-400" />
      <div className="min-w-0 flex-1">
        <dt className="text-xs text-gray-500">{label}</dt>
        {editing && editable ? (
          <input defaultValue={value} className="input-field mt-0.5 py-1 text-sm" />
        ) : (
          <dd className="text-sm font-medium text-gray-900">{value || '\u2014'}</dd>
        )}
      </div>
    </div>
  );
}

export const ProfilePage: React.FC = () => {
  const [activeTab, setActiveTab] = useState<TabId>('personal');
  const [editing, setEditing] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [apiData, setApiData] = useState<ProfileDataResponse | null>(null);
  const [loading, setLoading] = useState(isApiDataMode);
  const [error, setError] = useState<string | null>(null);
  const [dataSourceMode, setDataSourceMode] = useState<'native' | 'unavailable'>('native');
  const [readMode, setReadMode] = useState('native-readonly');
  const [previewDocument, setPreviewDocument] = useState<{ name: string; url: string; inlineSupported: boolean; reason?: string } | null>(null);

  const showToast = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 3000);
  };

  const resolveDocumentUrl = (documentRow: Record<string, unknown>): string => {
    const toAbsoluteApiUrl = (value: string): string => {
      const raw = String(value || '').trim();
      if (!raw) return '';
      if (raw.startsWith('http://') || raw.startsWith('https://')) return raw;
      if (raw.startsWith('/')) {
        const base = String(httpClient.defaults.baseURL || '').replace(/\/+$/, '');
        return `${base}${raw}`;
      }
      return raw;
    };
    const explicit = String(documentRow.url ?? '').trim();
    if (explicit) return toAbsoluteApiUrl(explicit);
    const path = String(documentRow.path ?? '').trim();
    if (!path) return '';
    return toAbsoluteApiUrl(path);
  };

  const resolveInlineDocumentUrl = (documentRow: Record<string, unknown>): string => {
    const inline = String(documentRow.inlineUrl ?? '').trim();
    if (inline) {
      const base = String(httpClient.defaults.baseURL || '').replace(/\/+$/, '');
      return inline.startsWith('/') ? `${base}${inline}` : inline;
    }
    return resolveDocumentUrl(documentRow);
  };

  const getDocumentExtension = (documentRow: Record<string, unknown>): string => {
    const fileName = String(documentRow.name ?? '').trim();
    const path = String(documentRow.path ?? '').trim();
    const candidates = [fileName, path].filter(Boolean);
    for (const candidate of candidates) {
      const withoutQueryOrHash = candidate.split(/[?#]/)[0];
      const lastSegment = withoutQueryOrHash.split('/').pop() || withoutQueryOrHash;
      const dotIdx = lastSegment.lastIndexOf('.');
      if (dotIdx > -1 && dotIdx < lastSegment.length - 1) {
        return lastSegment.slice(dotIdx + 1).toLowerCase();
      }
    }
    return '';
  };

  const canInlinePreview = (documentRow: Record<string, unknown>): { supported: boolean; reason?: string } => {
    const ext = getDocumentExtension(documentRow);
    // Keep preview permissive for backward compatibility: unknown extensions
    // should still attempt inline preview, just like before.
    const nonPreviewable = new Set([
      'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx',
      'zip', 'rar', '7z', 'tar', 'gz',
      'exe', 'msi', 'apk',
    ]);
    if (ext && nonPreviewable.has(ext)) {
      return { supported: false, reason: `.${ext.toUpperCase()} is not reliably previewable in browser iframe.` };
    }
    return { supported: true };
  };

  const canDownloadDocument = (documentRow: Record<string, unknown>): boolean => {
    const explicit = documentRow.downloadable;
    if (typeof explicit === 'boolean') return explicit;
    const permissions = documentRow.permissions;
    if (permissions && typeof permissions === 'object' && 'download' in (permissions as Record<string, unknown>)) {
      return Boolean((permissions as Record<string, unknown>).download);
    }
    const url = resolveDocumentUrl(documentRow);
    return Boolean(url);
  };

  const isMeaningful = (value: unknown): boolean => {
    const text = String(value ?? '').trim();
    if (!text) return false;
    return text.toLowerCase() !== 'n/a';
  };

  const handleSave = () => {
    setEditing(false);
    showToast('Profile updated successfully');
  };

  useEffect(() => {
    if (!isApiDataMode) return;
    let mounted = true;
    setLoading(true);
    setError(null);
    getMyProfile()
      .then((data) => {
        if (mounted) setApiData(data);
      })
      .catch(() => {
        if (mounted) setError('Failed to load profile data from API mode.');
      })
      .finally(() => {
        if (mounted) setLoading(false);
      });
    getModulesCatalog()
      .then((catalog) => {
        if (!mounted) return;
        const srms = (catalog.modules || []).find((m) => String(m.id || '').toLowerCase() === 'srms');
        const mode = String(srms?.capabilities?.read_mode || 'native-readonly').trim();
        setDataSourceMode('native');
        setReadMode(mode || 'native-readonly');
      })
      .catch(() => {
        if (!mounted) return;
        setDataSourceMode('native');
        setReadMode('native-readonly');
      });
    return () => {
      mounted = false;
    };
  }, []);

  if (isApiDataMode) {
    if (loading) {
      return (
        <div className="flex items-center justify-center py-20">
          <div className="h-10 w-10 animate-spin rounded-full border-4 border-gray-300 border-t-brand-500" />
        </div>
      );
    }

    if (error || !apiData) {
      return (
        <div className="rounded-xl border border-red-200 bg-red-50 p-6">
          <p className="text-sm text-red-700">{error ?? 'No profile data available in API mode.'}</p>
        </div>
      );
    }

    const profile = apiData.profile;
    const employment = apiData.employment;
    const qualifications = apiData.qualifications;
    const contacts = apiData.emergency_contacts;
    const documents = apiData.documents;
    const quickStats = apiData.quick_stats;

    const fullNameCore = [profile.firstName, profile.otherNames, profile.lastName].filter(Boolean).join(' ');
    const titleValue = String(profile.title ?? '').trim();
    const fullName = [titleValue, fullNameCore].filter(Boolean).join(' ');
    const normalizedPosition = isHonorific(employment.position) ? '' : String(employment.position ?? '').trim();
    const subtitleLeft = normalizedPosition || String(employment.rank ?? '').trim() || String(employment.employeeType ?? '').trim() || 'Position not available';
    const subtitleRight = String(employment.department ?? '').trim() || String(employment.unit ?? '').trim() || 'Department not available';

    const personalRows = [
      { label: 'Staff ID', value: String(profile.staffId ?? '') },
      { label: 'Email', value: String(profile.email ?? '') },
      { label: 'Phone', value: String(profile.phone ?? '') },
      { label: 'Gender', value: String(profile.gender ?? '') },
      { label: 'Date of Birth', value: String(profile.dateOfBirth ?? '') },
      { label: 'Marital Status', value: String(profile.maritalStatus ?? '') },
      { label: 'Residential Address', value: String(profile.residentialAddress ?? '') },
    ].filter((row) => isMeaningful(row.value));

    const employmentRows = [
      { label: 'Organization', value: String(employment.organization ?? '') },
      { label: 'Branch', value: String(employment.branch ?? '') },
      { label: 'Department', value: String(employment.department ?? '') },
      { label: 'Unit', value: String(employment.unit ?? '') },
      { label: 'Position', value: normalizedPosition || '' },
      { label: 'Rank', value: String(employment.rank ?? '') },
      { label: 'Employee Type', value: String(employment.employeeType ?? '') },
      { label: 'Hire Date', value: String(employment.hireDate ?? '') },
      { label: 'Status', value: String(employment.status ?? '') },
    ].filter((row) => isMeaningful(row.value));

    const preview = previewDocument;
    const extractYearValue = (qualification: Record<string, unknown>): number | null => {
      const raw = String(qualification.year ?? qualification.year_obtained ?? '').trim();
      const match = raw.match(/\b(19|20)\d{2}\b/);
      return match ? Number(match[0]) : null;
    };
    const sortByYearAscending = (a: Record<string, unknown>, b: Record<string, unknown>): number => {
      const yearA = extractYearValue(a);
      const yearB = extractYearValue(b);
      if (yearA === null && yearB === null) return 0;
      if (yearA === null) return 1;
      if (yearB === null) return -1;
      return yearA - yearB;
    };
    const academicQualifications = qualifications.filter((q) => {
      const type = String(q.type ?? '').toLowerCase();
      return type.includes('academic') || type.includes('degree');
    }).sort((a, b) => sortByYearAscending(a as Record<string, unknown>, b as Record<string, unknown>));
    const professionalQualifications = qualifications.filter((q) => {
      const type = String(q.type ?? '').toLowerCase();
      return type.includes('professional') || type.includes('cert');
    }).sort((a, b) => sortByYearAscending(a as Record<string, unknown>, b as Record<string, unknown>));
    return (
      <div className="space-y-6">
        <div className="card overflow-hidden p-0">
          <div className="bg-gradient-to-r from-brand-600 to-brand-700 px-6 py-8 text-white">
            <h1 className="text-2xl font-bold">{fullName || 'My Profile'}</h1>
            <p className="mt-1 text-sm text-white/80">
              {subtitleLeft} &middot; {subtitleRight}
            </p>
            <div className="mt-2 flex flex-wrap gap-2">
              <span
                title={getModuleModeHint(dataSourceMode)}
                className="cursor-help rounded-full bg-emerald-400/30 px-2.5 py-0.5 text-xs font-medium text-emerald-100"
              >
                {dataSourceMode}
              </span>
              <span
                title={getModuleModeHint(readMode)}
                className="cursor-help rounded-full bg-blue-400/30 px-2.5 py-0.5 text-xs font-medium text-blue-100"
              >
                {readMode}
              </span>
              <span className="rounded-full bg-white/20 px-2.5 py-0.5 text-xs font-medium">{String(profile.staffId ?? 'N/A')}</span>
              <span className="rounded-full bg-emerald-400/30 px-2.5 py-0.5 text-xs font-medium text-emerald-100">{String(employment.status ?? 'N/A')}</span>
              <span className="rounded-full bg-white/20 px-2.5 py-0.5 text-xs font-medium">{String(employment.branch ?? 'N/A')}</span>
            </div>
          </div>
          <div className="grid grid-cols-2 divide-x divide-gray-100 border-b border-gray-100 sm:grid-cols-4 dark:divide-gray-800 dark:border-gray-800">
            {[
              { label: 'Years of Service', value: String(quickStats.years_of_service ?? 'N/A'), icon: Clock },
              { label: 'Leave Balance', value: String(quickStats.leave_balance ?? 'N/A'), icon: Calendar },
              { label: 'Appraisal Score', value: String(quickStats.appraisal_score ?? 'N/A'), icon: Award },
              { label: 'Certifications', value: String(quickStats.certifications ?? 'N/A'), icon: GraduationCap },
            ].map(s => (
              <div key={s.label} className="flex items-center gap-3 px-4 py-3">
                <s.icon className="h-5 w-5 text-brand-500" />
                <div>
                  <p className="text-xs text-gray-500 dark:text-gray-400">{s.label}</p>
                  <p className="text-sm font-semibold text-gray-900 dark:text-gray-100">{s.value}</p>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="grid gap-6 md:grid-cols-2 xl:grid-cols-3">
          <div className="card">
            <h3 className="mb-3 text-sm font-semibold text-gray-900 dark:text-gray-100">Personal</h3>
            <dl className="space-y-2 text-sm">
              {personalRows.length === 0 ? (
                <p className="text-sm text-gray-500 dark:text-gray-400">No personal data available.</p>
              ) : personalRows.map((row) => (
                <div key={row.label} className="min-w-0">
                  <dt className="text-gray-500 dark:text-gray-400">{row.label}</dt>
                  <dd className="break-words font-medium text-gray-900 dark:text-gray-100">{row.value}</dd>
                </div>
              ))}
            </dl>
          </div>
          <div className="card">
            <h3 className="mb-3 text-sm font-semibold text-gray-900 dark:text-gray-100">Employment</h3>
            <dl className="space-y-2 text-sm">
              {employmentRows.length === 0 ? (
                <p className="text-sm text-gray-500 dark:text-gray-400">No employment data available.</p>
              ) : employmentRows.map((row) => (
                <div key={row.label} className="min-w-0">
                  <dt className="text-gray-500 dark:text-gray-400">{row.label}</dt>
                  <dd className="break-words font-medium text-gray-900 dark:text-gray-100">{row.value}</dd>
                </div>
              ))}
            </dl>
          </div>
          <div className="card">
            <h3 className="mb-3 text-sm font-semibold text-gray-900 dark:text-gray-100">Emergency Contacts</h3>
            <div className="space-y-2">
              {contacts.length === 0 ? <p className="text-sm text-gray-500">No contacts available.</p> : contacts.map((c, i) => (
                <div key={i} className="rounded-lg border border-gray-100 p-3 transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md dark:border-gray-800">
                  <p className="text-sm font-medium text-gray-900 dark:text-gray-100">{String(c.name ?? 'N/A')}</p>
                  <p className="text-xs text-gray-500 dark:text-gray-400">{String(c.relationship ?? '')} &middot; {String(c.phone ?? '')}</p>
                </div>
              ))}
            </div>
          </div>
        </div>

        <details className="card group" open>
          <summary className="flex cursor-pointer list-none items-center justify-between gap-2">
            <span className="text-sm font-semibold text-gray-900 dark:text-gray-100">Qualifications</span>
            <span className="text-xs text-gray-500 transition-transform group-open:rotate-180 dark:text-gray-400">▼</span>
          </summary>
          <div className="mt-4 grid gap-4 xl:grid-cols-2">
            <div className="overflow-hidden rounded-lg border border-gray-200 dark:border-gray-800">
              <div className="border-b border-gray-200 bg-gray-50 px-4 py-2 dark:border-gray-800 dark:bg-gray-900/60">
                <h4 className="text-xs font-semibold uppercase tracking-wide text-gray-600 dark:text-gray-300">Academic</h4>
              </div>
              <div className="overflow-x-auto">
                <table className="min-w-full text-left text-sm">
                  <thead className="border-b border-gray-200 dark:border-gray-800">
                    <tr>
                      <th className="px-3 py-2 font-medium text-gray-500 dark:text-gray-400">Qualification</th>
                      <th className="px-3 py-2 font-medium text-gray-500 dark:text-gray-400">Institution</th>
                      <th className="px-3 py-2 font-medium text-gray-500 dark:text-gray-400">Year</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                    {academicQualifications.length === 0 ? (
                      <tr>
                        <td className="px-3 py-3 text-sm text-gray-500 dark:text-gray-400" colSpan={3}>No academic qualifications.</td>
                      </tr>
                    ) : academicQualifications.map((q, i) => (
                      <tr key={`a-${i}`} className="hover:bg-gray-50 dark:hover:bg-gray-800/40">
                        <td className="px-3 py-2 font-medium text-gray-900 dark:text-gray-100">{String(q.title ?? 'Untitled')}</td>
                        <td className="px-3 py-2 text-gray-600 dark:text-gray-300">{String(q.institution ?? 'N/A')}</td>
                        <td className="px-3 py-2 text-gray-600 dark:text-gray-300">{String(q.year ?? q.year_obtained ?? 'N/A')}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
            <div className="overflow-hidden rounded-lg border border-gray-200 dark:border-gray-800">
              <div className="border-b border-gray-200 bg-gray-50 px-4 py-2 dark:border-gray-800 dark:bg-gray-900/60">
                <h4 className="text-xs font-semibold uppercase tracking-wide text-gray-600 dark:text-gray-300">Professional</h4>
              </div>
              <div className="overflow-x-auto">
                <table className="min-w-full text-left text-sm">
                  <thead className="border-b border-gray-200 dark:border-gray-800">
                    <tr>
                      <th className="px-3 py-2 font-medium text-gray-500 dark:text-gray-400">Qualification</th>
                      <th className="px-3 py-2 font-medium text-gray-500 dark:text-gray-400">Institution</th>
                      <th className="px-3 py-2 font-medium text-gray-500 dark:text-gray-400">Year</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                    {professionalQualifications.length === 0 ? (
                      <tr>
                        <td className="px-3 py-3 text-sm text-gray-500 dark:text-gray-400" colSpan={3}>No professional qualifications.</td>
                      </tr>
                    ) : professionalQualifications.map((q, i) => (
                      <tr key={`p-${i}`} className="hover:bg-gray-50 dark:hover:bg-gray-800/40">
                        <td className="px-3 py-2 font-medium text-gray-900 dark:text-gray-100">{String(q.title ?? 'Untitled')}</td>
                        <td className="px-3 py-2 text-gray-600 dark:text-gray-300">{String(q.institution ?? 'N/A')}</td>
                        <td className="px-3 py-2 text-gray-600 dark:text-gray-300">{String(q.year ?? q.year_obtained ?? 'N/A')}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </details>

        <div className="card">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">Documents</h3>
            <div className="flex flex-wrap items-center gap-2 text-[11px]">
              <span className="rounded-full bg-emerald-50 px-2 py-0.5 font-medium text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300">Preview</span>
              <span className="text-gray-500 dark:text-gray-400">opens inline</span>
              <span className="rounded-full bg-amber-50 px-2 py-0.5 font-medium text-amber-700 dark:bg-amber-900/30 dark:text-amber-300">Download only</span>
              <span className="text-gray-500 dark:text-gray-400">open in tab/download</span>
            </div>
          </div>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {documents.length === 0 ? <p className="text-sm text-gray-500">No documents available.</p> : documents.map((d, i) => (
              <div key={i} className="rounded-lg border border-gray-100 p-3 transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md dark:border-gray-800">
                <p className="text-sm font-medium text-gray-900 dark:text-gray-100">{String(d.name ?? 'Untitled')}</p>
                <p className="text-xs text-gray-500 dark:text-gray-400">{String(d.category ?? '')} &middot; {String(d.type ?? '')}</p>
                {(() => {
                  const doc = d as Record<string, unknown>;
                  const previewSupport = canInlinePreview(doc);
                  const canDownload = canDownloadDocument(doc);
                  return (
                    <div className="mt-1 flex flex-wrap gap-1.5">
                      {previewSupport.supported && (
                        <span className="inline-flex rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-medium text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300">
                          Preview
                        </span>
                      )}
                      {canDownload && (
                        <span className="inline-flex rounded-full bg-blue-50 px-2 py-0.5 text-[11px] font-medium text-blue-700 dark:bg-blue-900/30 dark:text-blue-300">
                          Download
                        </span>
                      )}
                      {!previewSupport.supported && !canDownload && (
                        <span className="inline-flex rounded-full bg-amber-50 px-2 py-0.5 text-[11px] font-medium text-amber-700 dark:bg-amber-900/30 dark:text-amber-300">
                          Restricted
                        </span>
                      )}
                    </div>
                  );
                })()}
                <p className="mt-1 break-all text-[11px] text-gray-400 dark:text-gray-500">{String(d.path ?? '')}</p>
                <div className="mt-2 flex flex-wrap gap-2">
                  {resolveDocumentUrl(d as Record<string, unknown>) ? (
                    <>
                      {canInlinePreview(d as Record<string, unknown>).supported && (
                        <button
                          type="button"
                          onClick={() => {
                            const doc = d as Record<string, unknown>;
                            const previewSupport = canInlinePreview(doc);
                            setPreviewDocument({
                              name: String(d.name ?? 'Document'),
                              url: resolveInlineDocumentUrl(doc),
                              inlineSupported: previewSupport.supported,
                              reason: previewSupport.reason,
                            });
                          }}
                          className="btn-secondary py-1 text-xs"
                          title="Open inline preview"
                        >
                          <FileText className="h-3.5 w-3.5" /> View
                        </button>
                      )}
                      {canDownloadDocument(d as Record<string, unknown>) && (
                        <a
                          href={resolveDocumentUrl(d as Record<string, unknown>)}
                          download
                          className="btn-secondary py-1 text-xs"
                        >
                          <Download className="h-3.5 w-3.5" /> Download
                        </a>
                      )}
                      {!canInlinePreview(d as Record<string, unknown>).supported && !canDownloadDocument(d as Record<string, unknown>) && (
                      <button
                        type="button"
                        onClick={() => {
                          const doc = d as Record<string, unknown>;
                          const previewSupport = canInlinePreview(doc);
                          setPreviewDocument({
                            name: String(d.name ?? 'Document'),
                            url: resolveInlineDocumentUrl(doc),
                            inlineSupported: previewSupport.supported,
                            reason: previewSupport.reason,
                          });
                        }}
                        className="btn-secondary py-1 text-xs"
                        title="Restricted document"
                      >
                        <FileText className="h-3.5 w-3.5" /> Details
                      </button>
                      )}
                    </>
                  ) : (
                    <span className="text-xs text-amber-600 dark:text-amber-400">Document URL unavailable</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
        {preview && (
          <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/60 p-4">
            <div className="max-h-[92vh] w-full max-w-5xl overflow-hidden rounded-xl border border-gray-200 bg-white shadow-xl dark:border-gray-800 dark:bg-gray-900">
              <div className="flex items-center justify-between border-b border-gray-200 px-4 py-3 dark:border-gray-800">
                <p className="truncate text-sm font-semibold text-gray-900 dark:text-gray-100">{preview.name}</p>
                <button
                  type="button"
                  onClick={() => setPreviewDocument(null)}
                  className="rounded-lg p-2 text-gray-500 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-800"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
              <div className="h-[75vh] w-full bg-gray-50 dark:bg-gray-950">
                {preview.inlineSupported ? (
                  <iframe
                    src={preview.url}
                    title={preview.name}
                    className="h-full w-full"
                  />
                ) : (
                  <div className="flex h-full w-full flex-col items-center justify-center gap-3 p-6 text-center">
                    <p className="text-sm font-medium text-gray-900 dark:text-gray-100">{preview.reason || 'Inline preview unavailable for this file.'}</p>
                    <p className="text-xs text-gray-500 dark:text-gray-400">Use Open in new tab or Download to access this document.</p>
                  </div>
                )}
              </div>
              <div className="flex justify-end border-t border-gray-200 px-4 py-3 dark:border-gray-800">
                <a href={preview.url} target="_blank" rel="noreferrer" className="btn-secondary py-1 text-xs">
                  Open in new tab
                </a>
              </div>
            </div>
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Toast */}
      {toast && (
        <div className="fixed right-4 top-20 z-50 flex items-center gap-2 rounded-lg bg-emerald-600 px-4 py-3 text-sm font-medium text-white shadow-lg animate-in slide-in-from-right">
          <CheckCircle className="h-4 w-4" /> {toast}
        </div>
      )}

      {/* Profile Header Card */}
      <div className="card overflow-hidden p-0">
        <div className="bg-gradient-to-r from-brand-600 to-brand-700 px-6 py-8">
          <div className="flex flex-col items-start gap-4 sm:flex-row sm:items-center">
            <div className="group relative">
              <div className="flex h-20 w-20 items-center justify-center rounded-full border-4 border-white/30 bg-white/20 text-3xl font-bold text-white">
                {PROFILE.firstName[0]}{PROFILE.lastName[0]}
              </div>
              <button className="absolute bottom-0 right-0 rounded-full bg-white p-1.5 text-gray-600 shadow-md opacity-0 transition-opacity group-hover:opacity-100">
                <Camera className="h-3.5 w-3.5" />
              </button>
            </div>
            <div className="flex-1 text-white">
              <h1 className="text-2xl font-bold">{PROFILE.firstName} {PROFILE.otherNames} {PROFILE.lastName}</h1>
              <p className="mt-0.5 text-sm text-white/80">{EMPLOYMENT.position} &middot; {EMPLOYMENT.department}</p>
              <div className="mt-2 flex flex-wrap gap-2">
                <span className="rounded-full bg-white/20 px-2.5 py-0.5 text-xs font-medium">{PROFILE.staffId}</span>
                <span className="rounded-full bg-emerald-400/30 px-2.5 py-0.5 text-xs font-medium text-emerald-100">{EMPLOYMENT.status}</span>
                <span className="rounded-full bg-white/20 px-2.5 py-0.5 text-xs font-medium">{EMPLOYMENT.branch}</span>
              </div>
            </div>
            <div className="flex gap-2">
              {editing ? (
                <>
                  <button onClick={handleSave} className="flex items-center gap-1.5 rounded-lg bg-white px-4 py-2 text-sm font-medium text-brand-600 hover:bg-white/90">
                    <Save className="h-4 w-4" /> Save Changes
                  </button>
                  <button onClick={() => setEditing(false)} className="flex items-center gap-1.5 rounded-lg bg-white/20 px-4 py-2 text-sm font-medium text-white hover:bg-white/30">
                    <X className="h-4 w-4" /> Cancel
                  </button>
                </>
              ) : (
                <button onClick={() => setEditing(true)} className="flex items-center gap-1.5 rounded-lg bg-white/20 px-4 py-2 text-sm font-medium text-white hover:bg-white/30">
                  <Pencil className="h-4 w-4" /> Edit Profile
                </button>
              )}
            </div>
          </div>
        </div>

        {/* Quick Stats Bar */}
        <div className="grid grid-cols-2 divide-x divide-gray-100 border-b border-gray-100 sm:grid-cols-4">
          {[
            { label: 'Years of Service', value: 'N/A', icon: Clock },
            { label: 'Leave Balance', value: 'N/A', icon: Calendar },
            { label: 'Appraisal Score', value: 'N/A', icon: Award },
            { label: 'Certifications', value: 'N/A', icon: GraduationCap },
          ].map(s => (
            <div key={s.label} className="flex items-center gap-3 px-4 py-3">
              <s.icon className="h-5 w-5 text-brand-500" />
              <div>
                <p className="text-xs text-gray-500">{s.label}</p>
                <p className="text-sm font-semibold text-gray-900">{s.value}</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Tabs */}
      <div className="border-b border-gray-200">
        <div className="-mb-px flex gap-1 overflow-x-auto">
          {TABS.map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={clsx(
                'flex shrink-0 items-center gap-2 border-b-2 px-4 pb-3 text-sm font-medium transition-colors',
                activeTab === tab.id
                  ? 'border-brand-500 text-brand-500'
                  : 'border-transparent text-gray-500 hover:border-gray-300 hover:text-gray-700'
              )}
            >
              <tab.icon className="h-4 w-4" />
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {/* Personal Info Tab */}
      {activeTab === 'personal' && (
        <div className="grid gap-6 lg:grid-cols-2">
          <div className="card">
            <h3 className="mb-2 text-sm font-semibold text-gray-900">Basic Information</h3>
            <dl className="divide-y divide-gray-50">
              <InfoRow icon={User} label="First Name" value={PROFILE.firstName} editable editing={editing} />
              <InfoRow icon={User} label="Last Name" value={PROFILE.lastName} editable editing={editing} />
              <InfoRow icon={User} label="Other Names" value={PROFILE.otherNames} editable editing={editing} />
              <InfoRow icon={Calendar} label="Date of Birth" value={PROFILE.dateOfBirth} />
              <InfoRow icon={User} label="Gender" value={PROFILE.gender} />
              <InfoRow icon={User} label="Marital Status" value={PROFILE.maritalStatus} />
              <InfoRow icon={Shield} label="Nationality" value={PROFILE.nationality} />
            </dl>
          </div>
          <div className="space-y-6">
            <div className="card">
              <h3 className="mb-2 text-sm font-semibold text-gray-900">Contact Details</h3>
              <dl className="divide-y divide-gray-50">
                <InfoRow icon={Mail} label="Work Email" value={PROFILE.email} />
                <InfoRow icon={Mail} label="Personal Email" value={PROFILE.personalEmail} editable editing={editing} />
                <InfoRow icon={Phone} label="Phone" value={PROFILE.phone} editable editing={editing} />
                <InfoRow icon={MapPin} label="Residential Address" value={PROFILE.residentialAddress} editable editing={editing} />
                <InfoRow icon={MapPin} label="Digital Address" value={PROFILE.digitalAddress} editable editing={editing} />
              </dl>
            </div>
            <div className="card">
              <h3 className="mb-2 text-sm font-semibold text-gray-900">Identification</h3>
              <dl className="divide-y divide-gray-50">
                <InfoRow icon={Shield} label="Ghana Card No." value={PROFILE.ghanaCardNo} />
                <InfoRow icon={Shield} label="SSNIT No." value={PROFILE.ssnitNo} />
                <InfoRow icon={Shield} label="TIN" value={PROFILE.tinNo} />
              </dl>
            </div>
          </div>
        </div>
      )}

      {/* Employment Tab */}
      {activeTab === 'employment' && (
        <div className="grid gap-6 lg:grid-cols-2">
          <div className="card">
            <h3 className="mb-2 text-sm font-semibold text-gray-900">Current Position</h3>
            <dl className="divide-y divide-gray-50">
              <InfoRow icon={Briefcase} label="Organization" value={EMPLOYMENT.organization} />
              <InfoRow icon={MapPin} label="Branch" value={EMPLOYMENT.branch} />
              <InfoRow icon={Briefcase} label="Department" value={EMPLOYMENT.department} />
              <InfoRow icon={Briefcase} label="Unit" value={EMPLOYMENT.unit} />
              <InfoRow icon={Award} label="Position" value={EMPLOYMENT.position} />
              <InfoRow icon={Award} label="Rank" value={EMPLOYMENT.rank} />
              <InfoRow icon={Briefcase} label="Employee Type" value={EMPLOYMENT.employeeType} />
              <InfoRow icon={Award} label="Grade Level" value={EMPLOYMENT.gradeLevel} />
            </dl>
          </div>
          <div className="space-y-6">
            <div className="card">
              <h3 className="mb-2 text-sm font-semibold text-gray-900">Service Details</h3>
              <dl className="divide-y divide-gray-50">
                <InfoRow icon={Calendar} label="Hire Date" value={EMPLOYMENT.hireDate} />
                <InfoRow icon={Calendar} label="Confirmation Date" value={EMPLOYMENT.confirmationDate} />
                <InfoRow icon={User} label="Supervisor" value={`${EMPLOYMENT.supervisorName} (${EMPLOYMENT.supervisorTitle})`} />
              </dl>
            </div>
            <div className="card">
              <h3 className="mb-4 text-sm font-semibold text-gray-900">Position History</h3>
              <div className="relative space-y-4 pl-6 before:absolute before:left-[9px] before:top-2 before:h-[calc(100%-16px)] before:w-0.5 before:bg-gray-200">
                {EMPLOYMENT.previousPositions.map((p, i) => (
                  <div key={i} className="relative">
                    <div className={clsx(
                      'absolute -left-6 top-1 h-3 w-3 rounded-full border-2',
                      i === EMPLOYMENT.previousPositions.length - 1
                        ? 'border-brand-500 bg-brand-500'
                        : 'border-gray-300 bg-white'
                    )} />
                    <p className="text-sm font-medium text-gray-900">{p.title}</p>
                    <p className="text-xs text-gray-500">{p.department} &middot; {p.from} to {p.to}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Qualifications Tab */}
      {activeTab === 'qualifications' && (
        <div className="space-y-6">
          {['Degree', 'Certification', 'Training'].map(type => {
            const items = QUALIFICATIONS.filter(q => q.type === type);
            if (items.length === 0) return null;
            return (
              <div key={type}>
                <h3 className="mb-3 text-sm font-semibold text-gray-900">{type === 'Degree' ? 'Academic Qualifications' : type === 'Certification' ? 'Professional Certifications' : 'Trainings & Workshops'}</h3>
                <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                  {items.map((q, i) => (
                    <div key={i} className="card">
                      <div className="flex items-start gap-3">
                        <div className={clsx(
                          'rounded-lg p-2',
                          type === 'Degree' ? 'bg-blue-50 text-blue-600' : type === 'Certification' ? 'bg-purple-50 text-purple-600' : 'bg-green-50 text-green-600'
                        )}>
                          <GraduationCap className="h-5 w-5" />
                        </div>
                        <div className="min-w-0 flex-1">
                          <p className="text-sm font-semibold text-gray-900">{q.title}</p>
                          <p className="text-xs text-gray-500">{q.institution}</p>
                          <div className="mt-2 flex gap-2">
                            <span className="rounded bg-gray-100 px-1.5 py-0.5 text-xs text-gray-600">{q.year}</span>
                            <span className={clsx(
                              'rounded px-1.5 py-0.5 text-xs font-medium',
                              q.grade === 'First Class' || q.grade === 'Distinction' ? 'bg-emerald-50 text-emerald-700' : 'bg-blue-50 text-blue-700'
                            )}>{q.grade}</span>
                          </div>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            );
          })}
          <button onClick={() => showToast('Add qualification form would open here')} className="btn-secondary text-sm">
            <GraduationCap className="h-4 w-4" /> Add Qualification
          </button>
        </div>
      )}

      {/* Emergency Contacts Tab */}
      {activeTab === 'emergency' && (
        <div className="space-y-4">
          {EMERGENCY_CONTACTS.map((c, i) => (
            <div key={i} className="card flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
              <div className="flex items-center gap-4">
                <div className={clsx(
                  'flex h-12 w-12 items-center justify-center rounded-full text-lg font-bold',
                  c.isPrimary ? 'bg-red-100 text-red-600' : 'bg-gray-100 text-gray-600'
                )}>
                  {c.name[0]}
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <p className="text-sm font-semibold text-gray-900">{c.name}</p>
                    {c.isPrimary && <span className="rounded-full bg-red-50 px-2 py-0.5 text-xs font-medium text-red-600">Primary</span>}
                  </div>
                  <p className="text-xs text-gray-500">{c.relationship}</p>
                  <div className="mt-1 flex flex-wrap gap-3 text-xs text-gray-500">
                    <span className="flex items-center gap-1"><Phone className="h-3 w-3" /> {c.phone}</span>
                    <span className="flex items-center gap-1"><Mail className="h-3 w-3" /> {c.email}</span>
                  </div>
                </div>
              </div>
              <button onClick={() => showToast('Edit contact form would open here')} className="btn-secondary py-1.5 text-xs">
                <Pencil className="h-3.5 w-3.5" /> Edit
              </button>
            </div>
          ))}
          <button onClick={() => showToast('Add contact form would open here')} className="btn-secondary text-sm">
            <Heart className="h-4 w-4" /> Add Emergency Contact
          </button>
        </div>
      )}

      {/* Documents Tab */}
      {activeTab === 'documents' && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <p className="text-sm text-gray-500">{DOCUMENTS.length} documents uploaded</p>
            <button onClick={() => showToast('Upload dialog would open here')} className="btn-primary text-sm">
              <FileText className="h-4 w-4" /> Upload Document
            </button>
          </div>
          <div className="card overflow-hidden p-0">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-gray-200 bg-gray-50">
                <tr>
                  <th className="px-4 py-3 font-medium text-gray-500">Document</th>
                  <th className="px-4 py-3 font-medium text-gray-500">Category</th>
                  <th className="px-4 py-3 font-medium text-gray-500">Type</th>
                  <th className="px-4 py-3 font-medium text-gray-500">Size</th>
                  <th className="px-4 py-3 font-medium text-gray-500">Uploaded</th>
                  <th className="px-4 py-3 font-medium text-gray-500">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {DOCUMENTS.map((doc, i) => (
                  <tr key={i} className="hover:bg-gray-50">
                    <td className="px-4 py-3 font-medium text-gray-900">
                      <div className="flex items-center gap-2">
                        <FileText className="h-4 w-4 text-gray-400" />
                        {doc.name}
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <span className="rounded bg-gray-100 px-1.5 py-0.5 text-xs text-gray-600">{doc.category}</span>
                    </td>
                    <td className="px-4 py-3 text-gray-500">{doc.type}</td>
                    <td className="px-4 py-3 text-gray-500">{doc.size}</td>
                    <td className="px-4 py-3 text-gray-500">{doc.uploadedAt}</td>
                    <td className="px-4 py-3">
                      <button onClick={() => showToast(`Downloading ${doc.name}...`)} className="inline-flex items-center gap-1 text-sm font-medium text-brand-500 hover:text-brand-600">
                        <Download className="h-3.5 w-3.5" /> Download
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};
