/**
 * ProfileHubPage  (/profile)
 * ===========================
 * Unified profile page that merges:
 *
 *  1. HRIS Identity section — always present, editable.
 *     Reads/writes the user's Keycloak account: display name, email, password.
 *     Changes apply across the entire HRIS system and all federated modules
 *     because Keycloak is the single source of identity.
 *
 *  2. Module Profile tabs — one per federated module.
 *     Tabs are DATA-DRIVEN from two sources:
 *       a. The module catalog (GET /modules/catalog) — tells us which modules
 *          are active for this tenant. We show a pending tab for each.
 *       b. MODULE_PROFILE_CAPABILITY postMessages — modules self-declare their
 *          profile path and preferred label when their iframe loads.
 *          ModuleFrame stores these in ModuleCapabilitiesContext.
 *     Clicking a tab lazily loads <ModuleFrame moduleId="X" path="/hris/profile" />.
 *     The module renders whatever profile UI it chooses — HRIS never hard-codes
 *     knowledge of module profile fields.
 *
 * Adaptive contract:
 *   - Adding a new module: it sends MODULE_PROFILE_CAPABILITY → tab appears.
 *   - Module redesigns profile UI: the iframe shows the new design automatically.
 *   - Module removes profile capability: it stops sending the message → tab absent.
 *   - Unknown future module: same — HRIS code doesn't change.
 *
 * Architecture reference: docs/architecture/iframe-bridge-protocol.md §12
 */

import React, { useEffect, useRef, useState } from 'react';
import { Eye, EyeOff, KeyRound, Mail, Save, User } from 'lucide-react';
import { clsx } from 'clsx';
import { useAuth } from '../auth/AuthProvider';
import { useModuleCapabilities } from '../contexts/ModuleCapabilitiesContext';
import { getModulesCatalog, type ModuleCatalogItem } from '../api/hrisCoreClient';
import {
  changeAccountPassword,
  getAccountProfile,
  resendVerificationEmail,
  updateAccountProfile,
  type AccountProfile,
} from '../api/accountClient';
import { ModuleFrame } from '../components/ModuleFrame';

// ---------------------------------------------------------------------------
// Sub-component: HRIS Identity section (editable Keycloak account fields)
// ---------------------------------------------------------------------------

const HrisIdentitySection: React.FC = () => {
  const { user } = useAuth();
  const [profile, setProfile] = useState<AccountProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState<{ msg: string; ok: boolean } | null>(null);

  // Edit state
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [email, setEmail] = useState('');

  // Password change
  const [showPasswordForm, setShowPasswordForm] = useState(false);
  const [currentPwd, setCurrentPwd] = useState('');
  const [newPwd, setNewPwd] = useState('');
  const [confirmPwd, setConfirmPwd] = useState('');
  const [showNewPwd, setShowNewPwd] = useState(false);
  const [changingPwd, setChangingPwd] = useState(false);
  const [resending, setResending] = useState(false);

  const showToast = (msg: string, ok = true) => {
    setToast({ msg, ok });
    setTimeout(() => setToast(null), 4000);
  };

  useEffect(() => {
    setLoading(true);
    getAccountProfile()
      .then((p) => {
        setProfile(p);
        setFirstName(p.first_name);
        setLastName(p.last_name);
        setEmail(p.email);
      })
      .catch(() => {
        // Fall back to JWT claims already in auth context
        setFirstName(user?.username ?? '');
        setEmail(user?.email ?? '');
      })
      .finally(() => setLoading(false));
  }, [user]);

  const handleSaveProfile = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      const result = await updateAccountProfile({
        first_name: firstName || undefined,
        last_name: lastName || undefined,
        email: email !== profile?.email ? email : undefined,
      });
      showToast(result.message, true);
      if (result.email_changed) {
        setProfile((p) => p ? { ...p, email, email_verified: false } : p);
      }
    } catch {
      showToast('Could not save profile. Please try again.', false);
    } finally {
      setSaving(false);
    }
  };

  const handlePasswordChange = async (e: React.FormEvent) => {
    e.preventDefault();
    if (newPwd !== confirmPwd) {
      showToast('New passwords do not match.', false);
      return;
    }
    if (newPwd.length < 8) {
      showToast('New password must be at least 8 characters.', false);
      return;
    }
    setChangingPwd(true);
    try {
      const result = await changeAccountPassword(currentPwd, newPwd);
      showToast(result.message, true);
      setCurrentPwd('');
      setNewPwd('');
      setConfirmPwd('');
      setShowPasswordForm(false);
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        'Password change failed. Check your current password and try again.';
      showToast(msg, false);
    } finally {
      setChangingPwd(false);
    }
  };

  const avatarLetter = (firstName[0] || user?.username?.[0] || 'U').toUpperCase();

  return (
    <div className="card space-y-6 overflow-hidden p-0">
      {/* Header */}
      <div className="bg-gradient-to-r from-brand-600 to-brand-700 px-6 py-6">
        <div className="flex items-center gap-4">
          <div className="flex h-16 w-16 shrink-0 items-center justify-center rounded-full bg-white/20 text-2xl font-bold text-white">
            {avatarLetter}
          </div>
          <div className="text-white">
            <h2 className="text-xl font-bold">
              {firstName || lastName ? `${firstName} ${lastName}`.trim() : (user?.username ?? 'My Account')}
            </h2>
            <p className="mt-0.5 text-sm text-white/80">{user?.email}</p>
            <div className="mt-1.5 flex flex-wrap gap-1.5">
              <span className="rounded-full bg-white/20 px-2 py-0.5 text-xs font-medium">
                @{user?.username}
              </span>
              {profile && (
                <span
                  className={clsx(
                    'rounded-full px-2 py-0.5 text-xs font-medium',
                    profile.email_verified
                      ? 'bg-emerald-400/30 text-emerald-100'
                      : 'bg-amber-400/30 text-amber-100',
                  )}
                >
                  {profile.email_verified ? 'Email verified' : 'Email unverified'}
                </span>
              )}
            </div>
          </div>
        </div>
      </div>

      <div className="space-y-6 px-6 pb-6">
        {/* Toast */}
        {toast && (
          <div
            className={clsx(
              'rounded-lg px-4 py-3 text-sm font-medium',
              toast.ok
                ? 'bg-emerald-50 text-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-200'
                : 'bg-red-50 text-red-800 dark:bg-red-950/50 dark:text-red-200',
            )}
          >
            {toast.msg}
          </div>
        )}

        {/* Email verification banner — shown when email is unverified.
            Keycloak automatically sends the email on change; this lets the
            user request another copy if it didn't arrive. */}
        {profile && !profile.email_verified && (
          <div className="flex items-start justify-between gap-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 dark:border-amber-800/50 dark:bg-amber-950/30">
            <div>
              <p className="text-sm font-medium text-amber-800 dark:text-amber-200">
                Email address not verified
              </p>
              <p className="mt-0.5 text-xs text-amber-700 dark:text-amber-300">
                A verification link was sent to <strong>{profile.email}</strong>. Click it to
                activate your new address across all HRIS modules. Check your spam folder if
                it hasn't arrived.
              </p>
            </div>
            <button
              type="button"
              disabled={resending}
              onClick={async () => {
                setResending(true);
                try {
                  const r = await resendVerificationEmail();
                  showToast(r.message, true);
                } catch {
                  showToast('Could not resend verification email. Try again later.', false);
                } finally {
                  setResending(false);
                }
              }}
              className="shrink-0 rounded-lg border border-amber-300 bg-white px-3 py-1.5 text-xs font-medium text-amber-800 hover:bg-amber-50 disabled:opacity-60 dark:border-amber-700 dark:bg-transparent dark:text-amber-200"
            >
              {resending ? 'Sending…' : 'Resend email'}
            </button>
          </div>
        )}

        {/* Profile fields form */}
        {loading ? (
          <div className="h-24 animate-pulse rounded-lg bg-gray-100 dark:bg-gray-800" />
        ) : (
          <form onSubmit={handleSaveProfile} className="space-y-4">
            <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
              Account Information
            </h3>
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <label className="mb-1 block text-xs font-medium text-gray-600 dark:text-gray-400">
                  First Name
                </label>
                <div className="relative">
                  <User className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
                  <input
                    type="text"
                    value={firstName}
                    onChange={(e) => setFirstName(e.target.value)}
                    placeholder="First name"
                    className="input-field pl-9"
                  />
                </div>
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-gray-600 dark:text-gray-400">
                  Last Name
                </label>
                <div className="relative">
                  <User className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
                  <input
                    type="text"
                    value={lastName}
                    onChange={(e) => setLastName(e.target.value)}
                    placeholder="Last name"
                    className="input-field pl-9"
                  />
                </div>
              </div>
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-gray-600 dark:text-gray-400">
                Email Address
              </label>
              <div className="relative">
                <Mail className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="Email address"
                  className="input-field pl-9"
                />
              </div>
              <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                Changing your email will require re-verification. It updates across all HRIS modules.
              </p>
            </div>
            <div className="flex justify-end">
              <button
                type="submit"
                disabled={saving}
                className="btn-primary flex items-center gap-2 text-sm disabled:opacity-60"
              >
                <Save className="h-4 w-4" />
                {saving ? 'Saving…' : 'Save Changes'}
              </button>
            </div>
          </form>
        )}

        {/* Divider */}
        <div className="border-t border-gray-200 dark:border-gray-800" />

        {/* Password change */}
        <div>
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">Password</h3>
            <button
              type="button"
              onClick={() => setShowPasswordForm((v) => !v)}
              className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium text-brand-600 hover:bg-brand-50 dark:text-brand-400 dark:hover:bg-brand-900/20"
            >
              <KeyRound className="h-3.5 w-3.5" />
              {showPasswordForm ? 'Cancel' : 'Change password'}
            </button>
          </div>

          {showPasswordForm && (
            <form onSubmit={handlePasswordChange} className="mt-4 space-y-3">
              <div>
                <label className="mb-1 block text-xs font-medium text-gray-600 dark:text-gray-400">
                  Current Password
                </label>
                <input
                  type="password"
                  value={currentPwd}
                  onChange={(e) => setCurrentPwd(e.target.value)}
                  required
                  className="input-field"
                  autoComplete="current-password"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-gray-600 dark:text-gray-400">
                  New Password
                </label>
                <div className="relative">
                  <input
                    type={showNewPwd ? 'text' : 'password'}
                    value={newPwd}
                    onChange={(e) => setNewPwd(e.target.value)}
                    required
                    minLength={8}
                    className="input-field pr-10"
                    autoComplete="new-password"
                  />
                  <button
                    type="button"
                    onClick={() => setShowNewPwd((v) => !v)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
                  >
                    {showNewPwd ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-gray-600 dark:text-gray-400">
                  Confirm New Password
                </label>
                <input
                  type="password"
                  value={confirmPwd}
                  onChange={(e) => setConfirmPwd(e.target.value)}
                  required
                  className={clsx(
                    'input-field',
                    confirmPwd && confirmPwd !== newPwd && 'border-red-400 focus:ring-red-400',
                  )}
                  autoComplete="new-password"
                />
                {confirmPwd && confirmPwd !== newPwd && (
                  <p className="mt-1 text-xs text-red-500">Passwords do not match</p>
                )}
              </div>
              <div className="flex justify-end">
                <button
                  type="submit"
                  disabled={changingPwd || !currentPwd || !newPwd || newPwd !== confirmPwd}
                  className="btn-primary flex items-center gap-2 text-sm disabled:opacity-60"
                >
                  <KeyRound className="h-4 w-4" />
                  {changingPwd ? 'Changing…' : 'Change Password'}
                </button>
              </div>
            </form>
          )}
        </div>
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export const ProfileHubPage: React.FC = () => {
  const { capabilities } = useModuleCapabilities();
  const [catalog, setCatalog] = useState<ModuleCatalogItem[]>([]);
  const [activeModuleTab, setActiveModuleTab] = useState<string | null>(null);
  // Track which module iframes have been rendered at least once (lazy loading).
  const renderedTabs = useRef<Set<string>>(new Set());

  useEffect(() => {
    getModulesCatalog()
      .then((resp) => {
        const active = (resp.modules ?? []).filter(
          (m) => String(m.status ?? '').toLowerCase() === 'active',
        );
        setCatalog(active);
        // Auto-select first module tab if any are active.
        if (active.length > 0 && activeModuleTab === null) {
          setActiveModuleTab(active[0].id);
        }
      })
      .catch(() => setCatalog([]));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleTabClick = (moduleId: string) => {
    setActiveModuleTab(moduleId);
    renderedTabs.current.add(moduleId);
  };

  // Merge catalog (source of truth for which modules exist) with capability
  // declarations (source of truth for label and profile path).
  const moduleTabs = catalog.map((item) => {
    const cap = capabilities[item.id.toLowerCase()];
    return {
      moduleId: item.id.toLowerCase(),
      label: cap?.label ?? item.label ?? item.id,
      profilePath: cap?.profilePath ?? '/hris/profile',
      hasCapability: Boolean(cap),
    };
  });

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      {/* Page title */}
      <div>
        <h1 className="text-xl font-bold text-gray-900 dark:text-gray-100">My Profile</h1>
        <p className="mt-0.5 text-sm text-gray-500 dark:text-gray-400">
          Manage your HRIS account and view your profile across connected modules.
        </p>
      </div>

      {/* ── HRIS Identity Section ─────────────────────────────────────────── */}
      <HrisIdentitySection />

      {/* ── Module Profile Tabs ───────────────────────────────────────────── */}
      {moduleTabs.length > 0 && (
        <div className="card overflow-hidden p-0">
          {/* Tab bar */}
          <div className="border-b border-gray-200 dark:border-gray-800">
            <div className="-mb-px flex overflow-x-auto">
              {moduleTabs.map((tab) => (
                <button
                  key={tab.moduleId}
                  type="button"
                  onClick={() => handleTabClick(tab.moduleId)}
                  className={clsx(
                    'flex shrink-0 items-center gap-2 border-b-2 px-5 py-3.5 text-sm font-medium transition-colors',
                    activeModuleTab === tab.moduleId
                      ? 'border-brand-500 bg-brand-50/50 text-brand-600 dark:border-brand-400 dark:bg-brand-900/20 dark:text-brand-300'
                      : 'border-transparent text-gray-500 hover:border-gray-300 hover:text-gray-700 dark:text-gray-400 dark:hover:border-gray-600 dark:hover:text-gray-200',
                  )}
                >
                  {tab.label}
                  {/* Dot indicator: capability declared = module has a profile view ready */}
                  {tab.hasCapability && (
                    <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                  )}
                </button>
              ))}
            </div>
          </div>

          {/* Tab content — lazy: iframe mounts on first tab click, stays mounted after.
              ModuleFrame always loads regardless of hasCapability so the module can
              boot, send MODULE_PROFILE_CAPABILITY, and populate its own tab.
              Without this, we'd have a chicken-and-egg: capability never declared
              because the frame never loaded. The green dot on the tab button shows
              when the capability has been confirmed. */}
          <div>
            {moduleTabs.map((tab) => {
              const isActive = activeModuleTab === tab.moduleId;
              // Render once clicked; keep in DOM after so the module state is preserved.
              if (!isActive && !renderedTabs.current.has(tab.moduleId)) return null;

              return (
                <div key={tab.moduleId} className={isActive ? 'block' : 'hidden'}>
                  <ModuleFrame
                    moduleId={tab.moduleId}
                    path={tab.profilePath}
                    title={`${tab.label} — Profile`}
                  />
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
};
