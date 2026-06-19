import { useI18n } from '../../i18n/LanguageContext.jsx';
import { normalizeTumorType } from './tumorType.js';

const TYPE_KEYS = ['glioma', 'meningioma', 'pituitary', 'notumor', 'no_tumor'];

// Translate a raw class label to its localized display name, falling back to
// the raw code for anything outside the known 4-class set.
function typeLabel(t, code) {
  const key = normalizeTumorType(code);
  const i18nKey = key === 'no_tumor' ? 'notumor' : key;
  return TYPE_KEYS.includes(key) ? t(`mri.types.${i18nKey}`) : code;
}

/**
 * Per-class probability breakdown for the Swin/ViT 4-class MRI classifier.
 *
 * Unlike the ECG PathologyTable (multi-label sigmoid, per-pathology thresholds),
 * this is a softmax distribution: probabilities sum to ~1 and exactly one class
 * wins. So there is no threshold marker — the highest-probability class is the
 * prediction and is highlighted as such.
 *
 * @param {{ probabilities: Object<string, number> }} props - {label: prob} map
 *   from `result_class_probabilities`. Renders nothing if empty/absent.
 */
export default function ClassProbabilities({ probabilities }) {
  const { t } = useI18n();
  if (!probabilities || typeof probabilities !== 'object') return null;
  const rows = Object.entries(probabilities)
    .map(([code, p]) => [code, typeof p === 'number' ? p : 0])
    .sort(([, a], [, b]) => b - a);
  if (rows.length === 0) return null;
  const topProb = rows[0][1];

  return (
    <div className="space-y-4">
      <div className="flex items-start gap-2 text-xs text-gray-500 bg-gray-50 border border-gray-200 rounded-lg px-3 py-2">
        <span className="shrink-0 mt-px">ℹ️</span>
        <span>{t('mri.classProb.note')}</span>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="text-xs uppercase tracking-wide text-gray-500 border-b border-gray-200">
              <th className="px-3 py-2 text-left font-medium">{t('mri.classProb.type')}</th>
              <th className="px-3 py-2 text-left w-[55%] font-medium">{t('mri.classProb.probability')}</th>
              <th className="px-3 py-2 text-center w-28 font-medium">{t('mri.classProb.predicted')}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {rows.map(([code, p], i) => {
              const pct = Math.max(0, Math.min(1, p)) * 100;
              const isPredicted = i === 0 && topProb > 0;
              return (
                <tr key={code} className={isPredicted ? 'bg-primary/5' : ''}>
                  <td className={'px-3 py-2 ' + (isPredicted ? 'text-primary font-semibold' : 'text-gray-700')}>
                    {typeLabel(t, code)}
                  </td>
                  <td className="px-3 py-2">
                    <div className="flex items-center gap-2">
                      <div className="flex-1 h-2.5 bg-gray-200 rounded overflow-hidden">
                        <div
                          className={'h-2.5 rounded transition-all duration-500 ' + (isPredicted ? 'bg-primary' : 'bg-gray-400')}
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                      <span className={'text-xs tabular-nums w-14 text-right ' + (isPredicted ? 'text-primary font-semibold' : 'text-gray-600')}>
                        {pct.toFixed(1)}%
                      </span>
                    </div>
                  </td>
                  <td className="px-3 py-2 text-center">
                    {isPredicted
                      ? <span className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-primary text-ink text-xs">✓</span>
                      : <span className="text-gray-400">—</span>}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="flex items-center gap-4 text-[10px] text-gray-500 px-1">
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-3 h-2 bg-primary rounded" />
          {t('mri.classProb.legendPredicted')}
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-3 h-2 bg-gray-400 rounded" />
          {t('mri.classProb.legendOther')}
        </span>
      </div>
    </div>
  );
}
