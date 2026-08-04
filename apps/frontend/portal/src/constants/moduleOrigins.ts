const SRMS_ORIGIN = (import.meta.env.VITE_SRMS_ORIGIN as string) || '';
const EAPPRAISAL_ORIGIN = (import.meta.env.VITE_EAPPRAISAL_ORIGIN as string) || '';
const ELEAVE_ORIGIN = (import.meta.env.VITE_ELEAVE_ORIGIN as string) || '';

export const MODULE_ORIGINS: Record<string, string> = {
  srms: SRMS_ORIGIN,
  eappraisal: EAPPRAISAL_ORIGIN,
  eleave: ELEAVE_ORIGIN,
};

export function getModuleOrigin(moduleId: string): string {
  return MODULE_ORIGINS[String(moduleId).toLowerCase()] ?? '';
}
