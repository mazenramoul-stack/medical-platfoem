import { useI18n } from '../../i18n/LanguageContext.jsx';
import { maybePathology } from './diagnosis.js';

const KNOWN_CODES = ['AFIB', '1AVB', 'STACH', 'SBRAD', 'IRBBB', 'CRBBB', 'RBBB', 'LBBB', 'PVC'];

export default function PathologyTable({ results }) {
  const { t } = useI18n();
  if (!results) return null;
  const rows = Object.entries(results).sort(([, a], [, b]) => b.probability - a.probability);
  // The tentative "maybe" pathology (closest to its threshold, still below it)
  // is highlighted in yellow, mirroring the "Maybe …" headline.
  const maybeCode = maybePathology(results)?.code;
  return (
    <div className="space-y-4">
      {/* Screening-mode explanation banner */}
      <div className="flex items-start gap-2 text-xs text-low bg-paneldeep/50 border border-edge rounded-lg px-3 py-2">
        <span className="shrink-0 mt-px">ℹ️</span>
        <span>
          {t('ecg.table.screeningNote')}
        </span>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="text-xs uppercase tracking-wide text-low border-b border-edge">
              <th className="px-3 py-2 text-left w-20 font-medium">{t('ecg.table.code')}</th>
              <th className="px-3 py-2 text-left font-medium">{t('ecg.table.pathology')}</th>
              <th className="px-3 py-2 text-left w-[40%] font-medium">{t('ecg.table.probability')}</th>
              <th className="px-3 py-2 text-center w-24 font-medium">{t('ecg.table.detected')}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-edge">
            {rows.map(([code, r]) => {
              const pct = (r.probability || 0) * 100;
              const detected = !!r.detected;
              const isMaybe = !detected && code === maybeCode;
              const thresholdPct = (r.threshold || 0.5) * 100;
              const rowBg = detected ? 'bg-cardio/10' : isMaybe ? 'bg-warning/10' : '';
              const accent = detected ? 'text-danger' : isMaybe ? 'text-warning' : 'text-mid';
              const barColor = detected ? 'bg-danger' : isMaybe ? 'bg-warning' : 'bg-primary';
              const emphasized = detected || isMaybe;
              return (
                <tr key={code} className={rowBg}>
                  <td className="px-3 py-2 font-mono text-xs text-low">{code}</td>
                  <td className={'px-3 py-2 ' + accent + (emphasized ? ' font-medium' : '')}>
                    {KNOWN_CODES.includes(code) ? t(`ecg.pathologies.${code}`) : code}
                  </td>
                  <td className="px-3 py-2">
                    <div className="flex items-center gap-2">
                      {/* Probability bar with threshold marker */}
                      <div className="flex-1 relative">
                        <div className="h-2.5 bg-paneldeep rounded overflow-hidden">
                          <div
                            className={'h-2.5 rounded transition-all duration-500 ' + barColor}
                            style={{ width: `${pct}%` }}
                          />
                        </div>
                        {/* Threshold marker line */}
                        <div
                          className="absolute top-[-3px] w-[2px] h-[14px] bg-warning rounded-sm"
                          style={{ left: `${thresholdPct}%` }}
                          title={`${t('ecg.table.thresholdLabel')}: ${thresholdPct.toFixed(0)}%`}
                        />
                        {/* Threshold label below the bar */}
                        <div
                          className="absolute top-[14px] text-[9px] font-medium text-warning tabular-nums whitespace-nowrap"
                          style={{
                            left: `${thresholdPct}%`,
                            transform: 'translateX(-50%)',
                          }}
                        >
                          {thresholdPct.toFixed(0)}%
                        </div>
                      </div>
                      <span className={'text-xs tabular-nums w-12 text-right ' + (emphasized ? accent + ' font-semibold' : 'text-mid')}>
                        {pct.toFixed(1)}%
                      </span>
                    </div>
                    {/* Margin indicator: how far above/below threshold */}
                    {detected && (
                      <div className="text-[10px] text-danger/70 mt-2">
                        {t('ecg.table.aboveThreshold', { margin: (pct - thresholdPct).toFixed(1) })}
                      </div>
                    )}
                    {isMaybe && (
                      <div className="text-[10px] text-warning/80 mt-2">
                        {t('ecg.table.maybeNote', { margin: (thresholdPct - pct).toFixed(1) })}
                      </div>
                    )}
                  </td>
                  <td className="px-3 py-2 text-center">
                    {detected
                      ? <span className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-danger text-ink text-xs">✓</span>
                      : isMaybe
                        ? <span className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-warning text-ink text-xs">?</span>
                        : <span className="text-low">—</span>}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Legend */}
      <div className="flex items-center gap-4 text-[10px] text-low px-1">
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-3 h-[2px] bg-warning rounded" />
          {t('ecg.table.legendThreshold')}
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-3 h-2 bg-danger rounded" />
          {t('ecg.table.legendDetected')}
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-3 h-2 bg-warning rounded" />
          {t('ecg.table.legendMaybe')}
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-3 h-2 bg-primary rounded" />
          {t('ecg.table.legendBelow')}
        </span>
      </div>
    </div>
  );
}
