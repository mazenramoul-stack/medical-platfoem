import { useI18n } from '../../i18n/LanguageContext.jsx';

const KNOWN_CODES = ['AFIB', '1AVB', 'STACH', 'SBRAD', 'IRBBB', 'CRBBB', 'RBBB', 'LBBB', 'PVC'];

export default function PathologyTable({ results }) {
  const { t } = useI18n();
  if (!results) return null;
  const rows = Object.entries(results).sort(([, a], [, b]) => b.probability - a.probability);
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm border-collapse">
        <thead>
          <tr className="text-xs uppercase tracking-wide text-low border-b border-edge">
            <th className="px-3 py-2 text-left w-20 font-medium">{t('ecg.table.code')}</th>
            <th className="px-3 py-2 text-left font-medium">{t('ecg.table.pathology')}</th>
            <th className="px-3 py-2 text-left w-1/3 font-medium">{t('ecg.table.probability')}</th>
            <th className="px-3 py-2 text-center w-24 font-medium">{t('ecg.table.detected')}</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-edge">
          {rows.map(([code, r]) => {
            const pct = (r.probability || 0) * 100;
            const detected = !!r.detected;
            const thr = typeof r.threshold === 'number'
              ? Math.min(100, Math.max(0, r.threshold * 100)) : null;
            return (
              <tr key={code} className={detected ? 'bg-cardio/10' : ''}>
                <td className="px-3 py-2 font-mono text-xs text-low">{code}</td>
                <td className={'px-3 py-2 ' + (detected ? 'text-danger font-medium' : 'text-mid')}>
                  {KNOWN_CODES.includes(code) ? t(`ecg.pathologies.${code}`) : code}
                </td>
                <td className="px-3 py-2">
                  <div className="flex items-center gap-2">
                    <div className="relative flex-1 h-2 bg-paneldeep rounded overflow-hidden">
                      <div
                        className={'h-2 rounded ' + (detected ? 'bg-danger' : 'bg-primary')}
                        style={{ width: `${pct}%` }}
                      />
                      {thr != null && (
                        <div
                          className="absolute top-0 bottom-0 w-0.5 bg-hi/70"
                          style={{ left: `${thr}%` }}
                          title={`${t('ecg.table.threshold')}: ${thr.toFixed(0)}%`}
                        />
                      )}
                    </div>
                    <span className={'text-xs tabular-nums w-12 text-right ' + (detected ? 'text-danger font-semibold' : 'text-mid')}>
                      {pct.toFixed(1)}%
                    </span>
                  </div>
                </td>
                <td className="px-3 py-2 text-center">
                  {detected
                    ? <span className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-danger text-ink text-xs">✓</span>
                    : <span className="text-low">—</span>}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="text-[11px] text-low mt-3 leading-relaxed">{t('ecg.table.thresholdNote')}</p>
    </div>
  );
}
