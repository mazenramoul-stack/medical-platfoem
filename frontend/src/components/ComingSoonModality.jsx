import { Lock, Upload } from 'lucide-react';

import Badge from './UI/Badge.jsx';
import Scene3D from './three/Scene3D.jsx';
import Brain3D from './three/Brain3D.jsx';
import Heart3D from './three/Heart3D.jsx';
import { useI18n } from '../i18n/LanguageContext.jsx';
import { useTokens } from '../theme/ThemeContext.jsx';

/**
 * Frontend-only placeholder for a modality with no backend yet.
 * Themed, with a live 3D model, plus a realistic-but-disabled upload
 * surface so the modality looks present without pretending to work.
 */
export default function ComingSoonModality({
  title,
  subtitle,
  description,
  formats,
  accent,
  model = 'brain', // 'brain' | 'heart'
}) {
  const { t } = useI18n();
  const { colors } = useTokens();
  const accentHex = accent || colors.violet;
  return (
    <div className="space-y-6 max-w-4xl animate-fade-up">
      {/* header + 3D hero */}
      <div className="holo-panel grid md:grid-cols-2 items-center overflow-hidden">
        <div className="p-6">
          <div className="flex items-center gap-2 flex-wrap mb-1">
            <h1 className="text-xl font-mono font-bold text-hi">{title}</h1>
            <Badge variant="warning">{t('ui.comingSoon.badge')}</Badge>
          </div>
          {subtitle && <p className="text-sm" style={{ color: accentHex }}>{subtitle}</p>}
          {description && <p className="text-sm text-mid mt-3 leading-relaxed">{description}</p>}
        </div>
        <div className="h-[220px]">
          <Scene3D accent={accentHex} height={220} camera={{ position: [0, 0, 4.4], fov: 45 }}>
            {model === 'heart'
              ? <Heart3D accent={accentHex} scale={1.1} />
              : <Brain3D accent={accentHex} scale={1.05} />}
          </Scene3D>
        </div>
      </div>

      {/* not-available banner */}
      <div className="flex items-start gap-3 text-sm rounded-lg px-4 py-3"
           style={{ background: 'rgb(var(--rgb-amber) / 0.10)', border: '1px solid var(--edge)', color: 'var(--amber-fg)' }}>
        <Lock size={16} className="mt-0.5 shrink-0" />
        <p>{t('ui.comingSoon.preview', { title })}</p>
      </div>

      {/* realistic-but-disabled upload */}
      <div className="holo-panel p-5 space-y-4 opacity-90">
        <div
          aria-disabled="true"
          className="rounded-xl px-6 py-10 text-center cursor-not-allowed select-none"
          style={{ border: '2px dashed var(--edge)', background: `${accentHex}0d` }}
        >
          <div className="inline-flex items-center justify-center w-12 h-12 rounded-full mb-3"
               style={{ background: 'var(--paneldeep)', color: 'var(--text-low)', border: '1px solid var(--edge)' }}>
            <Upload size={22} />
          </div>
          <p className="text-sm font-medium text-low">{t('ui.comingSoon.drag')}</p>
          {formats && <p className="text-xs text-low mt-1">{t('ui.comingSoon.formats', { formats })}</p>}
          <p className="text-xs text-low">{t('ui.comingSoon.maxSize')}</p>
        </div>
        <div className="flex justify-end gap-2">
          <button type="button" disabled className="px-4 py-2 rounded-lg text-sm text-low cursor-not-allowed">{t('common.cancel')}</button>
          <button type="button" disabled title={t('ui.comingSoon.notAvailable')}
                  className="px-4 py-2 rounded-lg text-sm font-semibold cursor-not-allowed"
                  style={{ background: 'var(--edge)', color: 'var(--text-low)' }}>
            {t('ui.comingSoon.analyze')}
          </button>
        </div>
      </div>
    </div>
  );
}
