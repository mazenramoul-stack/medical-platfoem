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
          <tr className="bg-gray-50 text-xs uppercase tracking-wide text-gray-500">
            <th className="px-3 py-2 text-left w-20">{t('ecg.table.code')}</th>
            <th className="px-3 py-2 text-left">{t('ecg.table.pathology')}</th>
            <th className="px-3 py-2 text-left w-1/3">{t('ecg.table.probability')}</th>
            <th className="px-3 py-2 text-center w-24">{t('ecg.table.detected')}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(([code, r]) => {
            const pct = (r.probability || 0) * 100;
            const detected = !!r.detected;
            return (
              <tr key={code} className={detected ? 'bg-red-50/60' : 'odd:bg-gray-50/50'}>
                <td className="px-3 py-2 font-mono text-xs text-gray-700">{code}</td>
                <td className={'px-3 py-2 ' + (detected ? 'text-danger font-medium' : 'text-gray-700')}>
                  {KNOWN_CODES.includes(code) ? t(`ecg.pathologies.${code}`) : code}
                </td>
                <td className="px-3 py-2">
                  <div className="flex items-center gap-2">
                    <div className="flex-1 h-2 bg-gray-200 rounded">
                      <div
                        className={'h-2 rounded ' + (detected ? 'bg-danger' : 'bg-primary')}
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                    <span className={'text-xs tabular-nums w-12 text-right ' + (detected ? 'text-danger font-semibold' : 'text-gray-700')}>
                      {pct.toFixed(1)}%
                    </span>
                  </div>
                </td>
                <td className="px-3 py-2 text-center">
                  {detected
                    ? <span className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-danger text-ink text-xs">✓</span>
                    : <span className="text-gray-300">—</span>}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
