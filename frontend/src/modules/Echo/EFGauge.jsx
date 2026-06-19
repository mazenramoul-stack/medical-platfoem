import { useI18n } from '../../i18n/LanguageContext.jsx';

// Clinical EF bands (simplified ASE), matching _ef_category in
// apps/inference/echo_pipeline.py: Reduced < 40, Mildly reduced 40–50,
// Normal >= 50. Widths are percentage points on the 0–100 EF scale.
const BANDS = [
  { key: 'reduced', from: 0, to: 40, rgb: '--rgb-cardio' },
  { key: 'mild', from: 40, to: 50, rgb: '--rgb-amber' },
  { key: 'normal', from: 50, to: 100, rgb: '--rgb-neuro' },
];

const TICKS = [0, 40, 50, 100];

/**
 * Ejection-fraction gauge: the EF value plotted on a 0–100% scale with the
 * three clinical bands shaded and a marker at the patient's EF.
 *
 * EchoNet's EF head is a *regressor*, not a classifier — there is no per-class
 * probability distribution to show (as MRI/EEG have). This banded gauge is the
 * regression analog: it places a single continuous value against clinical bands.
 *
 * @param {{ ef: number|null|undefined, category: string|null, color: string }} props
 *   `color` is the category accent (hex) already computed by EchoResult.
 */
export default function EFGauge({ ef, category, color }) {
  const { t } = useI18n();
  const hasEf = typeof ef === 'number';
  const pct = hasEf ? Math.max(0, Math.min(100, ef)) : 0;
  const markerColor = color || 'var(--text-low)';

  return (
    <div className="mt-5" aria-label={category || undefined}>
      {/* EF% label + banded track + needle marker */}
      <div className="relative">
        {hasEf && (
          <div
            className="absolute -top-5 text-[10px] font-mono tabular-nums whitespace-nowrap"
            style={{ left: `${pct}%`, transform: 'translateX(-50%)', color: markerColor }}
          >
            {ef.toFixed(1)}%
          </div>
        )}
        <div className="flex w-full h-2.5 rounded overflow-hidden">
          {BANDS.map((b) => (
            <div
              key={b.key}
              style={{ width: `${b.to - b.from}%`, background: `rgb(var(${b.rgb}) / 0.3)` }}
            />
          ))}
        </div>
        {hasEf && (
          <div
            className="absolute top-[-3px] w-[2px] h-[16px] rounded"
            style={{
              left: `${pct}%`,
              transform: 'translateX(-50%)',
              background: markerColor,
              boxShadow: `0 0 10px ${markerColor}`,
            }}
          />
        )}
      </div>

      {/* tick labels at the band boundaries */}
      <div className="relative h-4 mt-1.5 text-[10px] text-low font-mono">
        {TICKS.map((tick) => (
          <span
            key={tick}
            className="absolute"
            style={{
              left: `${tick}%`,
              transform: tick === 0 ? 'none' : tick === 100 ? 'translateX(-100%)' : 'translateX(-50%)',
            }}
          >
            {tick}
          </span>
        ))}
      </div>

      {/* band legend */}
      <div className="flex items-center gap-4 text-[10px] text-low mt-2">
        {BANDS.map((b) => (
          <span key={b.key} className="flex items-center gap-1.5">
            <span className="inline-block w-3 h-2 rounded" style={{ background: `rgb(var(${b.rgb}) / 0.6)` }} />
            {t(`echo.gauge.${b.key}`)}
          </span>
        ))}
      </div>
    </div>
  );
}
