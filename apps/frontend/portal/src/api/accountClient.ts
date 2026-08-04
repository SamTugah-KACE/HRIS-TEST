/**
 * accountClient — typed wrappers for the HRIS account self-service endpoints.
 *
 * All calls go to HRIS Core API (/account/…) which proxies to Keycloak.
 * The user's session cookie is forwarded automatically by httpClient.
 */
import { httpClient } from './httpClient';

export type AccountProfile = {
  sub: string;
  username: string;
  email: string;
  first_name: string;
  last_name: string;
  email_verified: boolean;
};

export type ProfileUpdatePayload = {
  first_name?: string;
  last_name?: string;
  email?: string;
};

export type ProfileUpdateResult = {
  status: string;
  message: string;
  email_changed?: boolean;
  verification_required?: boolean;
};

export type PasswordChangeResult = {
  status: string;
  message: string;
};

export const getAccountProfile = async (): Promise<AccountProfile> => {
  const r = await httpClient.get<AccountProfile>('/account/profile');
  return r.data;
};

export const updateAccountProfile = async (
  payload: ProfileUpdatePayload,
): Promise<ProfileUpdateResult> => {
  const r = await httpClient.patch<ProfileUpdateResult>('/account/profile', payload);
  return r.data;
};

export const resendVerificationEmail = async (): Promise<{ status: string; message: string }> => {
  const r = await httpClient.post<{ status: string; message: string }>('/account/resend-verification');
  return r.data;
};

export const changeAccountPassword = async (
  currentPassword: string,
  newPassword: string,
): Promise<PasswordChangeResult> => {
  const r = await httpClient.post<PasswordChangeResult>('/account/password', {
    current_password: currentPassword,
    new_password: newPassword,
  });
  return r.data;
};
