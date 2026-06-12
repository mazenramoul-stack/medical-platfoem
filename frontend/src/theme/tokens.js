// Central design tokens. Two palettes (light / dark-neon) mirrored by the CSS
// variables in src/index.css — keep both in sync. Components needing hex values
// in JS (three.js, canvas, charts, `${accent}55` literals) should call
// useTokens() from theme/ThemeContext.jsx rather than importing these directly,
// so they re-render on theme switch.

const DARK = {
  bg: '#07070f',
  panel: '#111122',
  panelDeep: '#0a0a0f',
  border: '#1e1e2e',
  edge: '#1e1e2e',

  // domain accents
  neuro: '#00ffcc', // brain / MRI
  violet: '#a855f7', // EEG
  cardio: '#f43f5e', // heart / ECG / Echo
  amber: '#fbbf24', // ultrasound
  blue: '#60a5fa', // patients

  textHi: '#f4f4fa',
  textMid: '#b9b9d0',
  textLow: '#8a8aa8',

  success: '#00ffcc',
  warning: '#fbbf24',
  danger: '#f43f5e',
};

const LIGHT = {
  bg: '#f4f6fb',
  panel: '#ffffff',
  panelDeep: '#eef1f8',
  border: '#dde3ef',
  edge: '#dde3ef',

  neuro: '#0d9488',
  violet: '#7c3aed',
  cardio: '#e11d48',
  amber: '#d97706',
  blue: '#2563eb',

  textHi: '#0f172a',
  textMid: '#475569',
  textLow: '#5b6477',

  success: '#059669',
  warning: '#b45309',
  danger: '#e11d48',
};

export function getColors(theme) {
  return theme === 'light' ? LIGHT : DARK;
}

// Per-modality accent used by cards, scenes and headers.
export function getAccents(theme) {
  const c = getColors(theme);
  return {
    mri: { color: c.neuro, soft: c.neuro, label: 'NEURO' },
    eeg: { color: c.violet, soft: c.violet, label: 'WAVES' },
    ecg: { color: c.cardio, soft: c.cardio, label: 'CARDIO' },
    echo: { color: c.amber, soft: c.amber, label: 'ULTRASOUND' },
    patients: { color: c.blue, soft: c.blue, label: 'RECORDS' },
    reports: { color: c.neuro, soft: c.neuro, label: 'OUTPUT' },
  };
}

// Legacy exports (dark palette) — prefer useTokens() in components.
export const COLORS = DARK;
export const ACCENTS = getAccents('dark');

export const FONTS = {
  mono: "'Space Mono', monospace",
  sans: "'DM Sans', sans-serif",
};

// honor reduced-motion at the JS layer for canvas/3D loops
export const prefersReducedMotion = () =>
  typeof window !== 'undefined' &&
  window.matchMedia &&
  window.matchMedia('(prefers-reduced-motion: reduce)').matches;
