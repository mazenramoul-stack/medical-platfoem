import { useMemo } from 'react';
import { Info } from 'lucide-react';

import Scene3D from './Scene3D.jsx';
import Heart3D from './Heart3D.jsx';
import { useI18n } from '../../i18n/LanguageContext.jsx';
import { useTokens } from '../../theme/ThemeContext.jsx';

/**
 * Interactive 3D anatomy panel for a result page. Renders the organ (heart for
 * now) and glows the structures the model's finding implicates, beside an honest
 * legend + caveat. `highlight` is the descriptor from a pure map*ToHighlight()
 * function: { organ, regions:[{id,score,severity}], findings:[{code,score}],
 * beatsPerMinute, rateOnly, rateScore, normal }.
 */
export default function Anatomy3DPanel({ accent, highlight }) {
  const { t } = useI18n();
  const { colors } = useTokens();

  // Bright green (the app's neuro accent) reads clearly on the dark-red heart and
  // the dark scene. Glow STRENGTH ∝ the finding's probability: a high-confidence
  // finding glows strong, a low-confidence one glows faint.
  const glowColor = colors.neuro;
  const clamp01 = (x) => Math.max(0, Math.min(1, x || 0));
  const scoreToIntensity = (score) => 0.5 + clamp01(score) * 1.4; // ~0.5 (faint) → 1.9 (strong)

  // id -> { color, intensity } for the 3D model.
  const highlightMap = useMemo(() => {
    const m = {};
    if (highlight.rateOnly) {
      // Rate finding → no localized site: glow the whole heart "examined", at a
      // strength reflecting the rate finding's probability.
      const intensity = scoreToIntensity(highlight.rateScore ?? 0.6);
      for (const id of ['lv', 'rv', 'la', 'ra']) m[id] = { color: glowColor, intensity };
    } else {
      for (const r of highlight.regions || []) m[r.id] = { color: glowColor, intensity: scoreToIntensity(r.score) };
    }
    return m;
    // colors change with theme; highlight changes with the result
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [highlight, colors]);

  const accentColor = accent || colors.cardio;
  const bpm = highlight.beatsPerMinute || 72;

  return (
    <div className="bg-card rounded-xl shadow-sm border border-gray-200 overflow-hidden">
      <div className="flex items-center justify-between px-5 py-3 border-b border-gray-200">
        <h2 className="text-sm font-semibold text-gray-900">{t('anatomy3d.title')}</h2>
        <span className="text-xs text-gray-400">{t('anatomy3d.rotateHint')}</span>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2">
        {/* 3D canvas */}
        <div className="bg-gray-50 border-b lg:border-b-0 lg:border-r border-gray-100">
          <Scene3D accent={accentColor} height={340} autoRotate={false} float={false} camera={{ position: [0, 0, 5], fov: 45 }}>
            <Heart3D accent={accentColor} highlight={highlightMap} bpm={bpm} scale={1.15} />
          </Scene3D>
        </div>

        {/* legend + honest caption */}
        <div className="p-5 space-y-4">
          {highlight.normal ? (
            <p className="text-sm text-success font-medium">{t('anatomy3d.none')}</p>
          ) : (
            <>
              {highlight.rateOnly ? (
                <p className="flex items-start gap-2 text-sm text-gray-800">
                  <span
                    className="inline-block w-2.5 h-2.5 rounded-full shrink-0 mt-1.5"
                    style={{ background: glowColor, boxShadow: `0 0 8px ${glowColor}` }}
                  />
                  <span>{t('anatomy3d.rateNote')}</span>
                </p>
              ) : (
                <div>
                  <div className="text-xs font-semibold uppercase tracking-wide text-gray-500 mb-2">
                    {t('anatomy3d.implicated')}
                  </div>
                  <ul className="space-y-2">
                    {highlight.regions.map((r) => {
                      const pct = Math.round(clamp01(r.score) * 100);
                      return (
                        <li key={r.id} className="flex items-center gap-2 text-sm text-gray-800">
                          <span
                            className="inline-block w-2.5 h-2.5 rounded-full shrink-0"
                            style={{ background: glowColor, opacity: 0.35 + clamp01(r.score) * 0.65, boxShadow: `0 0 ${4 + pct / 12}px ${glowColor}` }}
                          />
                          <span className="font-medium">{t(`anatomy3d.regions.${r.id}`)}</span>
                          <span className="text-xs text-gray-400 tabular-nums">· {pct}%</span>
                        </li>
                      );
                    })}
                  </ul>
                </div>
              )}

              {highlight.findings?.length > 0 && (
                <ul className="space-y-1 text-xs text-gray-600">
                  {highlight.findings.map((f) => {
                    const label = t(`anatomy3d.findings.${f.code}`);
                    const text = label === `anatomy3d.findings.${f.code}` ? f.code : label;
                    return (
                      <li key={f.code}>
                        • {text} <span className="text-gray-400 tabular-nums">({Math.round(clamp01(f.score) * 100)}%)</span>
                      </li>
                    );
                  })}
                </ul>
              )}
            </>
          )}

          {highlight.beatsPerMinute && (
            <p className="text-xs text-gray-500">{t('anatomy3d.measuredRate', { bpm: highlight.beatsPerMinute })}</p>
          )}

          <p className="flex items-start gap-1.5 text-[11px] text-gray-400 pt-1 border-t border-gray-100">
            <Info size={13} className="mt-0.5 shrink-0" />
            <span>{t('anatomy3d.caveat')}</span>
          </p>
        </div>
      </div>
    </div>
  );
}
