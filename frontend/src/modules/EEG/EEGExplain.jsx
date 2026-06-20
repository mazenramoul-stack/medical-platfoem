import { useState } from 'react';
import toast from 'react-hot-toast';

import eegService from '../../services/eegService.js';
import { formatPercent } from '../../utils/formatters.js';
import { useI18n } from '../../i18n/LanguageContext.jsx';
import { useTokens } from '../../theme/ThemeContext.jsx';
import { channelXY } from './eegAnatomy.js';

// The 6 IIIC classes the BIOT head attributes (canonical codes — not translated).
const IIIC_CLASSES = ['SZ', 'LPD', 'GPD', 'LRDA', 'GRDA', 'Other'];

// Small schematic scalp topomap: a nose-up head with the 16 bipolar channels placed
// at their (approximate) 10-20 midpoints and coloured by SHAP per-channel importance.
// Coarse by construction — see the topomap caveat in the panel.
function ScalpTopomap({ importance, topChannels, violet, red }) {
  const S = 200;
  const toPx = (xy) => [20 + xy[0] * 160, 20 + xy[1] * 160];
  const top = topChannels && topChannels[0];
  const dots = Object.entries(importance || {})
    .map(([ch, score]) => {
      const xy = channelXY(ch);
      if (!xy) return null;
      const [cx, cy] = toPx(xy);
      return { ch, score: Math.max(0, Math.min(1, score)), cx, cy };
    })
    .filter(Boolean);

  return (
    <svg viewBox={`0 0 ${S} ${S}`} className="w-full max-w-[260px] mx-auto" role="img" aria-label="EEG scalp importance map">
      {/* nose */}
      <polygon points="100,4 92,20 108,20" fill="none" stroke="currentColor" className="text-low" strokeWidth="1.5" />
      {/* ears */}
      <path d="M18,100 q-8,-12 0,-24 q6,12 0,24" fill="none" stroke="currentColor" className="text-low" strokeWidth="1.5" transform="translate(0,12)" />
      <path d="M182,100 q8,-12 0,-24 q-6,12 0,24" fill="none" stroke="currentColor" className="text-low" strokeWidth="1.5" transform="translate(0,12)" />
      {/* head */}
      <circle cx="100" cy="100" r="84" fill="none" stroke="currentColor" className="text-edge" strokeWidth="2" />
      {dots.map((d) => (
        <g key={d.ch}>
          <circle
            cx={d.cx}
            cy={d.cy}
            r={5 + d.score * 6}
            fill={d.ch === top ? red : violet}
            fillOpacity={0.2 + 0.8 * d.score}
            stroke={d.ch === top ? red : violet}
            strokeOpacity={0.9}
            strokeWidth={d.ch === top ? 2 : 1}
          />
        </g>
      ))}
    </svg>
  );
}

// On-demand SHAP saliency panel for an analyzed EEG. Mirrors ECGExplain: a button
// triggers eegService.explain, then we render the returned SHAP plot (signed URL) +
// per-channel importance + top channels + a scalp topomap. Honest framing: this is
// signal-level saliency (which channels/segments drove the call), not a clinical
// rationale. `onResult` lifts the result so the page can enrich the 3D brain marker.
export default function EEGExplain({ id, disabled = false, onResult }) {
  const { t } = useI18n();
  const { colors } = useTokens();
  const [targetClass, setTargetClass] = useState('');
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);

  const violet = colors.violet;
  const red = colors.cardio;

  const onExplain = async () => {
    setLoading(true);
    try {
      const res = await eegService.explain(id, targetClass || undefined);
      setResult(res);
      if (onResult) onResult(res);
    } catch (e) {
      toast.error(e.response?.data?.detail || t('eeg.explain.failed'));
    } finally {
      setLoading(false);
    }
  };

  const channelImportance = result?.per_channel_importance || {};
  const sortedChannels = Object.entries(channelImportance).sort((a, b) => b[1] - a[1]);

  return (
    <div className="holo-panel p-5">
      <h3 className="text-sm font-mono font-bold text-hi tracking-wide mb-1">{t('eeg.explain.title')}</h3>
      <p className="text-xs text-low mb-3">{t('eeg.explain.caveat')}</p>

      {/* Chooser stays visible so you can pick another class and re-run at any time
          (no dead-end once a result is shown). */}
      <div className="flex flex-wrap items-end gap-3">
        <label className="text-xs text-mid">
          <span className="block mb-1">{t('eeg.explain.pickClass')}</span>
          <select
            value={targetClass}
            onChange={(e) => setTargetClass(e.target.value)}
            disabled={loading}
            className="bg-paneldeep border border-edge text-mid rounded-lg px-2 py-1.5 text-sm disabled:opacity-50"
          >
            <option value="">{t('eeg.explain.predictedOption')}</option>
            {IIIC_CLASSES.map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
        </label>
        <button
          type="button"
          onClick={onExplain}
          disabled={disabled || loading}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium disabled:opacity-50"
          style={{ background: violet, color: '#07070b' }}
        >
          {loading ? t('eeg.explain.running') : (result ? t('eeg.explain.rerun') : t('eeg.explain.button'))}
        </button>
      </div>

      {result && (
        <div className="space-y-4 mt-4 pt-4 border-t border-edge">
          <p className="text-xs text-mid">
            {t('eeg.explain.attributing')}: <strong className="text-hi">{result.target_class}</strong>
            {typeof result.probability === 'number' ? ` (${formatPercent(result.probability)})` : ''}
          </p>

          <div className="bg-paneldeep p-3 rounded overflow-auto">
            <img
              src={result.shap_path}
              alt="EEG SHAP saliency"
              className="max-w-full rounded mx-auto"
            />
          </div>

          <div className="grid md:grid-cols-2 gap-5">
            {/* per-channel importance bars */}
            <div>
              <div className="flex items-baseline justify-between mb-2">
                <span className="text-xs font-medium text-low">{t('eeg.explain.perChannel')}</span>
                <span className="text-xs text-mid">
                  {t('eeg.explain.topChannels')}: <strong className="text-hi">{(result.top_channels || []).join(', ')}</strong>
                </span>
              </div>
              <div className="space-y-1">
                {sortedChannels.map(([ch, score]) => (
                  <div key={ch} className="flex items-center gap-2 text-xs">
                    <span className="w-14 font-mono text-mid">{ch}</span>
                    <div className="flex-1 h-2 bg-paneldeep rounded overflow-hidden">
                      <div
                        className="h-2 rounded"
                        style={{ width: `${Math.max(0, Math.min(1, score)) * 100}%`, background: violet }}
                      />
                    </div>
                    <span className="w-12 text-right text-low">{formatPercent(score)}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* scalp topomap */}
            <div>
              <div className="text-xs font-medium text-low mb-2">{t('eeg.explain.topomapTitle')}</div>
              <ScalpTopomap
                importance={channelImportance}
                topChannels={result.top_channels}
                violet={violet}
                red={red}
              />
              <p className="text-[10px] text-low mt-2">{t('eeg.explain.topomapCaveat')}</p>
            </div>
          </div>

          {typeof result.segment_index === 'number' && (
            <p className="text-[10px] text-low">{t('eeg.explain.segmentNote')}</p>
          )}
        </div>
      )}
    </div>
  );
}
