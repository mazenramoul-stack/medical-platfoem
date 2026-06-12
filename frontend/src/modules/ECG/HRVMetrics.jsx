import { useI18n } from '../../i18n/LanguageContext.jsx';

/**
 * HRV reference ranges (approximate, healthy adults at rest):
 *   RMSSD: 20–60 ms     (lower → reduced parasympathetic activity)
 *   SDNN:  50–100 ms    (over 24h; short windows are lower)
 *   pNN50: 5–25%
 * These are rough guides — clinical interpretation requires context.
 */
const RANGES = {
  RMSSD: { min: 20, max: 60,  unit: 'ms' },
  SDNN:  { min: 20, max: 100, unit: 'ms' },
  pNN50: { min: 5,  max: 30,  unit: '%' },
};

function statusFor(value, { min, max }) {
  if (typeof value !== 'number') return 'gray';
  if (value < min) return 'warning';
  if (value > max) return 'warning';
  return 'success';
}

const STATUS_BG = {
  success: 'bg-green-100 text-green-800',
  warning: 'bg-amber-100 text-amber-800',
  gray:    'bg-gray-100 text-gray-600',
};

function MetricCard({ label, value, unit, range }) {
  const { t } = useI18n();
  const status = statusFor(value, range);
  const statusLabel = status === 'success' ? t('ecg.hrv.inRange')
    : status === 'warning' ? t('ecg.hrv.outsideRange')
    : t('ecg.hrv.notAvailable');
  return (
    <div className="rounded-lg border border-gray-200 p-3">
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs font-medium text-gray-600">{label}</span>
        <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${STATUS_BG[status]}`}>
          {statusLabel}
        </span>
      </div>
      <div className="text-2xl font-semibold text-gray-900 leading-none">
        {typeof value === 'number' ? value.toFixed(2) : '—'}
        <span className="text-xs text-gray-500 ml-1 font-normal">{unit}</span>
      </div>
      <div className="text-[11px] text-gray-500 mt-1">
        {t('ecg.hrv.normal')}: {range.min}–{range.max} {range.unit}
      </div>
    </div>
  );
}

export default function HRVMetrics({ metrics }) {
  if (!metrics) return null;
  return (
    <div className="space-y-2">
      <MetricCard label="RMSSD" value={metrics.RMSSD_ms}      unit="ms" range={RANGES.RMSSD} />
      <MetricCard label="SDNN"  value={metrics.SDNN_ms}       unit="ms" range={RANGES.SDNN} />
      <MetricCard label="pNN50" value={metrics.pNN50_percent} unit="%"  range={RANGES.pNN50} />
    </div>
  );
}
