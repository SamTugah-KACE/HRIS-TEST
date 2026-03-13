export const getModuleModeHint = (mode: string): string => {
  const normalized = String(mode || '').trim().toLowerCase();
  if (normalized === 'native') {
    return 'Data comes from the live native module integration path.';
  }
  if (normalized === 'native-readonly') {
    return 'Data comes from the native module, but this screen only reads data and does not write changes upstream.';
  }
  if (normalized === 'mock') {
    return 'Data is sourced from local/demo fallback fixtures.';
  }
  return `Runtime mode: ${mode || 'unknown'}.`;
};
