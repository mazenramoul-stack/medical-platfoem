import { useState } from 'react';
import toast from 'react-hot-toast';

import ecgService from '../../services/ecgService.js';
import { formatPercent } from '../../utils/formatters.js';
import { useI18n } from '../../i18n/LanguageContext.jsx';

// The 7 pathologies the ECG models attribute (canonical codes — not translated).
const PATHOLOGIES = ['AFIB', '1AVB', 'STACH', 'SBRAD', 'RBBB', 'LBBB', 'PVC'];

// On-demand SHAP saliency panel for an analyzed ECG. Mirrors the MRI explain
// panel: a button triggers ecgService.explain, then we render the returned SHAP
// plot (signed URL) + per-lead importance + top leads. Honest framing: this is
// signal-level saliency, not a clinical rationale.
export default function ECGExplain({ id, disabled = false }) {
  const { t } = useI18n();
  const [pathology, setPathology] = useState('');
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);

  const onExplain = async () => {
    setLoading(true);
    try {
      setResult(await ecgService.explain(id, pathology || undefined));
    } catch (e) {
      toast.error(e.response?.data?.detail || t('ecg.explain.failed'));
    } finally {
      setLoading(false);
    }
  };

  const leadImportance = result?.per_lead_importance || {};
  const sortedLeads = Object.entries(leadImportance).sort((a, b) => b[1] - a[1]);

  return (
    <div className="bg-card rounded-xl shadow-sm border border-gray-200 p-5">
      <h3 className="text-sm font-semibold text-gray-900 mb-1">{t('ecg.explain.title')}</h3>
      <p className="text-xs text-gray-500 mb-3">{t('ecg.explain.caveat')}</p>

      {/* Chooser stays visible so you can pick another pathology and re-run at any
          time (no dead-end once a result is shown). */}
      <div className="flex flex-wrap items-end gap-3">
        <label className="text-xs text-gray-600">
          <span className="block mb-1">{t('ecg.explain.pickPathology')}</span>
          <select
            value={pathology}
            onChange={(e) => setPathology(e.target.value)}
            disabled={loading}
            className="border border-gray-300 rounded-lg px-2 py-1.5 text-sm bg-white disabled:opacity-50"
          >
            <option value="">{t('ecg.explain.primaryOption')}</option>
            {PATHOLOGIES.map((p) => (
              <option key={p} value={p}>{p}</option>
            ))}
          </select>
        </label>
        <button
          type="button"
          onClick={onExplain}
          disabled={disabled || loading}
          className="inline-flex items-center gap-2 bg-primary text-white px-4 py-2 rounded-lg text-sm font-medium hover:opacity-90 disabled:opacity-50"
        >
          {loading ? t('ecg.explain.running') : (result ? t('ecg.explain.rerun') : t('ecg.explain.button'))}
        </button>
      </div>

      {result && (
        <div className="space-y-4 mt-4 pt-4 border-t border-gray-100">
          <p className="text-xs text-gray-600">
            {t('ecg.explain.attributing')}: <strong>{result.pathology}</strong>
            {typeof result.probability === 'number' ? ` (${formatPercent(result.probability)})` : ''}
          </p>

          <div className="bg-gray-50 p-3 rounded overflow-auto">
            <img
              src={result.shap_path}
              alt="ECG SHAP saliency"
              className="max-w-full rounded shadow-sm mx-auto"
            />
          </div>

          <div>
            <div className="flex items-baseline justify-between mb-2">
              <span className="text-xs font-medium text-gray-500">{t('ecg.explain.perLead')}</span>
              <span className="text-xs text-gray-600">
                {t('ecg.explain.topLeads')}: <strong>{(result.top_leads || []).join(', ')}</strong>
              </span>
            </div>
            <div className="space-y-1">
              {sortedLeads.map(([lead, score]) => (
                <div key={lead} className="flex items-center gap-2 text-xs">
                  <span className="w-10 font-mono text-gray-700">{lead}</span>
                  <div className="flex-1 h-2 bg-gray-200 rounded">
                    <div
                      className="h-2 rounded bg-primary"
                      style={{ width: `${Math.max(0, Math.min(1, score)) * 100}%` }}
                    />
                  </div>
                  <span className="w-12 text-right text-gray-500">{formatPercent(score)}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
