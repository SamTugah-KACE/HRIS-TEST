import React, { useEffect, useState } from 'react';
import {
  User, Mail, Phone, MapPin, Calendar, Briefcase, GraduationCap,
  Shield, Heart, FileText, Pencil, Save, X, Camera, Download,
  Award, Clock, CheckCircle, AlertCircle, ChevronRight,
} from 'lucide-react';
import { clsx } from 'clsx';
import { getMyProfile, type ProfileDataResponse } from '../api/hrisCoreClient';
import { isApiDataMode } from '../config/dataMode';

type TabId = 'personal' | 'employment' | 'qualifications' | 'emergency' | 'documents';

const TABS: { id: TabId; label: string; icon: React.FC<{ className?: string }> }[] = [
  { id: 'personal', label: 'Personal Info', icon: User },
  { id: 'employment', label: 'Employment', icon: Briefcase },
  { id: 'qualifications', label: 'Qualifications', icon: GraduationCap },
  { id: 'emergency', label: 'Emergency Contacts', icon: Heart },
  { id: 'documents', label: 'Documents', icon: FileText },
];

const PROFILE = {
  firstName: 'Kwame', lastName: 'Asante', otherNames: 'Osei',
  staffId: 'STF-001', email: 'kwame.asante@gi-kace.gov.gh',
  phone: '+233 24 123 4567', personalEmail: 'kwame.asante@gmail.com',
  dateOfBirth: '1990-05-15', gender: 'Male', maritalStatus: 'Married',
  nationality: 'Ghanaian', ghanaCardNo: 'GHA-098765432-1',
  ssnitNo: 'A012345678', tinNo: 'P0012345678',
  residentialAddress: '12 Independence Avenue, Accra',
  digitalAddress: 'GA-123-4567',
};

const EMPLOYMENT = {
  organization: 'Development Tenant', branch: 'Head Office',
  department: 'Information Technology', unit: 'Software Development',
  position: 'Senior Software Engineer', rank: 'Principal Technical Officer',
  employeeType: 'Full-time', hireDate: '2020-01-15',
  confirmationDate: '2020-07-15', status: 'Active',
  supervisorName: 'Dr. Ama Mensah', supervisorTitle: 'Director of IT',
  gradeLevel: 'Grade 14', salaryStep: 'Step 3',
  previousPositions: [
    { title: 'Software Engineer', department: 'IT', from: '2020-01-15', to: '2022-06-30' },
    { title: 'Senior Software Engineer', department: 'IT', from: '2022-07-01', to: 'Present' },
  ],
};

const QUALIFICATIONS = [
  { type: 'Degree', title: 'BSc Computer Science', institution: 'University of Ghana', year: '2012', grade: 'First Class' },
  { type: 'Degree', title: 'MSc Information Technology', institution: 'KNUST', year: '2015', grade: 'Distinction' },
  { type: 'Certification', title: 'AWS Solutions Architect', institution: 'Amazon Web Services', year: '2023', grade: 'Certified' },
  { type: 'Certification', title: 'PMP', institution: 'PMI', year: '2024', grade: 'Certified' },
  { type: 'Training', title: 'Leadership Development Program', institution: 'GI-KACE', year: '2025', grade: 'Completed' },
];

const EMERGENCY_CONTACTS = [
  { name: 'Akua Asante', relationship: 'Spouse', phone: '+233 20 987 6543', email: 'akua.a@gmail.com', isPrimary: true },
  { name: 'Yaw Asante', relationship: 'Brother', phone: '+233 24 555 1234', email: 'yaw.a@gmail.com', isPrimary: false },
];

const DOCUMENTS = [
  { name: 'Employment Letter', type: 'PDF', size: '245 KB', uploadedAt: '2020-01-15', category: 'Employment' },
  { name: 'BSc Certificate', type: 'PDF', size: '1.2 MB', uploadedAt: '2020-01-10', category: 'Education' },
  { name: 'MSc Certificate', type: 'PDF', size: '1.1 MB', uploadedAt: '2020-01-10', category: 'Education' },
  { name: 'AWS Certificate', type: 'PDF', size: '890 KB', uploadedAt: '2023-06-20', category: 'Certification' },
  { name: 'Ghana Card', type: 'JPEG', size: '2.5 MB', uploadedAt: '2020-01-08', category: 'Identification' },
  { name: 'SSNIT Card', type: 'PDF', size: '340 KB', uploadedAt: '2020-01-08', category: 'Identification' },
  { name: 'Passport Photo', type: 'JPEG', size: '560 KB', uploadedAt: '2024-03-15', category: 'Photo' },
];

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

  const showToast = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 3000);
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

    const fullName = [profile.firstName, profile.otherNames, profile.lastName].filter(Boolean).join(' ');

    return (
      <div className="space-y-6">
        <div className="card overflow-hidden p-0">
          <div className="bg-gradient-to-r from-brand-600 to-brand-700 px-6 py-8 text-white">
            <h1 className="text-2xl font-bold">{fullName || 'My Profile'}</h1>
            <p className="mt-1 text-sm text-white/80">
              {(employment.position as string) || 'Position not available'} &middot; {(employment.department as string) || 'Department not available'}
            </p>
            <div className="mt-2 flex flex-wrap gap-2">
              <span className="rounded-full bg-emerald-400/30 px-2.5 py-0.5 text-xs font-medium text-emerald-100">native</span>
              <span className="rounded-full bg-blue-400/30 px-2.5 py-0.5 text-xs font-medium text-blue-100">native-readonly</span>
              <span className="rounded-full bg-white/20 px-2.5 py-0.5 text-xs font-medium">{String(profile.staffId ?? 'N/A')}</span>
              <span className="rounded-full bg-emerald-400/30 px-2.5 py-0.5 text-xs font-medium text-emerald-100">{String(employment.status ?? 'N/A')}</span>
              <span className="rounded-full bg-white/20 px-2.5 py-0.5 text-xs font-medium">{String(employment.branch ?? 'N/A')}</span>
            </div>
          </div>
          <div className="grid grid-cols-2 divide-x divide-gray-100 border-b border-gray-100 sm:grid-cols-4">
            {[
              { label: 'Years of Service', value: String(quickStats.years_of_service ?? 'N/A'), icon: Clock },
              { label: 'Leave Balance', value: String(quickStats.leave_balance ?? 'N/A'), icon: Calendar },
              { label: 'Appraisal Score', value: String(quickStats.appraisal_score ?? 'N/A'), icon: Award },
              { label: 'Certifications', value: String(quickStats.certifications ?? 'N/A'), icon: GraduationCap },
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

        <div className="grid gap-6 lg:grid-cols-2">
          <div className="card">
            <h3 className="mb-3 text-sm font-semibold text-gray-900">Personal</h3>
            <dl className="space-y-2 text-sm">
              <div><dt className="text-gray-500">Email</dt><dd className="font-medium text-gray-900">{String(profile.email ?? 'N/A')}</dd></div>
              <div><dt className="text-gray-500">Phone</dt><dd className="font-medium text-gray-900">{String(profile.phone ?? 'N/A')}</dd></div>
              <div><dt className="text-gray-500">Gender</dt><dd className="font-medium text-gray-900">{String(profile.gender ?? 'N/A')}</dd></div>
            </dl>
          </div>
          <div className="card">
            <h3 className="mb-3 text-sm font-semibold text-gray-900">Employment</h3>
            <dl className="space-y-2 text-sm">
              <div><dt className="text-gray-500">Organization</dt><dd className="font-medium text-gray-900">{String(employment.organization ?? 'N/A')}</dd></div>
              <div><dt className="text-gray-500">Department</dt><dd className="font-medium text-gray-900">{String(employment.department ?? 'N/A')}</dd></div>
              <div><dt className="text-gray-500">Rank</dt><dd className="font-medium text-gray-900">{String(employment.rank ?? 'N/A')}</dd></div>
            </dl>
          </div>
        </div>

        <div className="grid gap-6 lg:grid-cols-3">
          <div className="card lg:col-span-1">
            <h3 className="mb-3 text-sm font-semibold text-gray-900">Qualifications</h3>
            <div className="space-y-2">
              {qualifications.length === 0 ? <p className="text-sm text-gray-500">No qualifications available.</p> : qualifications.map((q, i) => (
                <div key={i} className="rounded-lg border border-gray-100 p-3">
                  <p className="text-sm font-medium text-gray-900">{String(q.title ?? 'Untitled')}</p>
                  <p className="text-xs text-gray-500">{String(q.institution ?? '')}</p>
                </div>
              ))}
            </div>
          </div>
          <div className="card lg:col-span-1">
            <h3 className="mb-3 text-sm font-semibold text-gray-900">Emergency Contacts</h3>
            <div className="space-y-2">
              {contacts.length === 0 ? <p className="text-sm text-gray-500">No contacts available.</p> : contacts.map((c, i) => (
                <div key={i} className="rounded-lg border border-gray-100 p-3">
                  <p className="text-sm font-medium text-gray-900">{String(c.name ?? 'N/A')}</p>
                  <p className="text-xs text-gray-500">{String(c.relationship ?? '')} &middot; {String(c.phone ?? '')}</p>
                </div>
              ))}
            </div>
          </div>
          <div className="card lg:col-span-1">
            <h3 className="mb-3 text-sm font-semibold text-gray-900">Documents</h3>
            <div className="space-y-2">
              {documents.length === 0 ? <p className="text-sm text-gray-500">No documents available.</p> : documents.map((d, i) => (
                <div key={i} className="rounded-lg border border-gray-100 p-3">
                  <p className="text-sm font-medium text-gray-900">{String(d.name ?? 'Untitled')}</p>
                  <p className="text-xs text-gray-500">{String(d.category ?? '')} &middot; {String(d.type ?? '')}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
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
            { label: 'Years of Service', value: '6 years', icon: Clock },
            { label: 'Leave Balance', value: '15 days', icon: Calendar },
            { label: 'Appraisal Score', value: '3.9 / 5.0', icon: Award },
            { label: 'Certifications', value: '2 active', icon: GraduationCap },
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
