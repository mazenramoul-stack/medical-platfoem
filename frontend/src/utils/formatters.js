import { format, formatDistanceToNow } from 'date-fns';

export const formatDate = (d) => (d ? format(new Date(d), 'PPpp') : '');
export const formatDateShort = (d) => (d ? format(new Date(d), 'PP') : '');
export const formatRelative = (d) =>
  d ? formatDistanceToNow(new Date(d), { addSuffix: true }) : '';
export const formatPercent = (v) =>
  typeof v === 'number' ? `${(v * 100).toFixed(2)}%` : '—';
export const formatBytes = (n) => {
  if (typeof n !== 'number') return '—';
  const units = ['B', 'KB', 'MB', 'GB'];
  let i = 0;
  while (n >= 1024 && i < units.length - 1) { n /= 1024; i += 1; }
  return `${n.toFixed(1)} ${units[i]}`;
};
