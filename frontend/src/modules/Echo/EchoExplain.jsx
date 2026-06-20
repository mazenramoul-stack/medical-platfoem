import { useState } from 'react';
import toast from 'react-hot-toast';

import echoService from '../../services/echoService.js';
import { formatPercent } from '../../utils/formatters.js';
import { useI18n } from '../../i18n/LanguageContext.jsx';
import { useTokens } from '../../theme/ThemeContext.jsx';

// On-demand SHAP saliency panel for an analyzed Echo. Mirrors ECGExplain / EEGExplain:
// a button triggers echoService.explain, then we render the returned saliency montage
// (signed URL) + a temporal frame-importance strip + the top frames. EF is a SINGLE
// regression output, so there is no class chooser. Honest framing: this is pixel and
// temporal saliency over a single 2D ultrasound plane — which frames and regions drove
// the EF estimate — NOT regional wall-motion analysis or a clinical rationale (hence
// the 3D heart panel stays a global-LV highlight; no fabricated regional marker here).
export default function EchoExplain({ id, disabled = false }) {
  const { t } = useI18n();
  const { colors } = useTokens();
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);

  const amber = colors.amber;
  const red = colors.cardio;

  const onExplain = async () => {
    setLoading(true);
    try {
      setResult(await echoService.explain(id));
    } catch (e) {
      toast.error(e.response?.data?.detail || t('echo.explain.failed'));
    } finally {
      setLoading(false);
    }
  };

  const frames = result?.frame_importance || [];
  const topFrames = result?.top_frames || [];
  const topSet = new Set(topFrames.map((f) => f.clip_index));

  return (
    <div className="holo-panel p-5">
      <h3 className="text-sm font-mono font-bold text-hi tracking-wide mb-1">{t('echo.explain.title')}</h3>
      <p className="text-xs text-low mb-3">{t('echo.explain.caveat')}</p>

      {/* No class chooser — EF is a single regression output. The button stays
          visible so the analysis can be re-run at any time. */}
      <button
        type="button"
        onClick={onExplain}
        disabled={disabled || loading}
        className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium disabled:opacity-50"
        style={{ background: amber, color: '#07070b' }}
      >
        {loading ? t('echo.explain.running') : (result ? t('echo.explain.rerun') : t('echo.explain.button'))}
      </button>

      {result && (
        <div className="space-y-4 mt-4 pt-4 border-t border-edge">
          <p className="text-xs text-mid">
            {t('echo.explain.efLabel')}: <strong className="text-hi">
              {typeof result.ef === 'number' ? `${result.ef.toFixed(1)}%` : '—'}
            </strong>
          </p>

          <div className="bg-paneldeep p-3 rounded overflow-auto">
            <img
              src={result.shap_path}
              alt="Echo SHAP saliency"
              className="max-w-full rounded mx-auto"
            />
          </div>

          {frames.length > 0 && (
            <div>
              <div className="flex items-baseline justify-between mb-2">
                <span className="text-xs font-medium text-low">{t('echo.explain.frameImportance')}</span>
                <span className="text-xs text-mid">
                  {t('echo.explain.topFrames')}: <strong className="text-hi">
                    {topFrames.map((f) => f.video_frame).join(', ')}
                  </strong>
                </span>
              </div>
              {/* Temporal frame-importance strip: one bar per analysed clip frame,
                  height ∝ importance, the top frames marked in red. */}
              <div className="flex items-end gap-[2px] h-16 bg-paneldeep rounded p-2 overflow-x-auto">
                {frames.map((score, i) => (
                  <div
                    key={i}
                    title={`frame ${i} · ${formatPercent(score)}`}
                    className="flex-1 min-w-[3px] rounded-sm"
                    style={{
                      height: `${Math.max(2, Math.max(0, Math.min(1, score)) * 100)}%`,
                      background: topSet.has(i) ? red : amber,
                    }}
                  />
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
