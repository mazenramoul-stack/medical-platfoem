import { format, formatDistanceToNow } from 'date-fns';
import { fr } from 'date-fns/locale';

// LanguageContext persists the active language in localStorage under 'mp-lang'
// and mirrors it to <html lang>. Read it at call time so a language toggle takes
// effect on the next render without these (hook-free) helpers needing a context.
const STORAGE_KEY = 'mp-lang';
function dateLocale() {
  try {
    const lang = localStorage.getItem(STORAGE_KEY)
      || (typeof document !== 'undefined' ? document.documentElement.lang : '');
    return lang === 'fr' ? fr : undefined; // undefined ⇒ date-fns default (en-US)
  } catch {
    return undefined; // storage unavailable
  }
}

export const formatDate = (d) => (d ? format(new Date(d), 'PPpp', { locale: dateLocale() }) : '');
export const formatDateShort = (d) => (d ? format(new Date(d), 'PP', { locale: dateLocale() }) : '');
export const formatRelative = (d) =>
  d ? formatDistanceToNow(new Date(d), { addSuffix: true, locale: dateLocale() }) : '';
export const formatPercent = (v) =>
  typeof v === 'number' ? `${(v * 100).toFixed(2)}%` : '—';
export const formatBytes = (n) => {
  if (typeof n !== 'number') return '—';
  const units = ['B', 'KB', 'MB', 'GB'];
  let i = 0;
  while (n >= 1024 && i < units.length - 1) { n /= 1024; i += 1; }
  return `${n.toFixed(1)} ${units[i]}`;
};
