import { Link } from 'react-router-dom';
import { ArrowRight } from 'lucide-react';

import Scene3D from './three/Scene3D.jsx';
import Brain3D from './three/Brain3D.jsx';
import Heart3D from './three/Heart3D.jsx';
import { useI18n } from '../i18n/LanguageContext.jsx';
import { useTokens } from '../theme/ThemeContext.jsx';

/**
 * Landing page for an active modality (MRI / ECG): a 3D hero + capability
 * chips + a metric strip + a CTA. Uploads happen from a patient's page,
 * so the CTA routes to Patients.
 */
export default function ModalityLanding({
  title,
  subtitle,
  description,
  accent,
  model = 'brain',
  classes = [],
  metrics = [],
  ctaTo = '/patients',
  ctaLabel,
}) {
  const { t } = useI18n();
  const { colors } = useTokens();
  const accentHex = accent || colors.neuro;
  const cta = ctaLabel ?? t('ui.modality.cta');
  return (
    <div className="space-y-6 max-w-5xl animate-fade-up">
      {/* hero */}
      <div className="holo-panel grid md:grid-cols-2 items-center overflow-hidden">
        <div className="p-6 sm:p-8">
          <div className="font-mono text-[10px] tracking-[0.4em] uppercase mb-2" style={{ color: accentHex }}>
            {subtitle}
          </div>
          <h1 className="text-2xl sm:text-3xl font-mono font-bold text-hi mb-3">{title}</h1>
          <p className="text-sm text-mid leading-relaxed mb-5 max-w-md">{description}</p>
          <Link
            to={ctaTo}
            className="inline-flex items-center gap-2 text-ink px-4 py-2.5 rounded-lg text-sm font-semibold"
            style={{ background: `linear-gradient(135deg, ${accentHex}, ${colors.violet})`, boxShadow: `0 0 22px ${accentHex}55` }}
          >
            {cta} <ArrowRight size={16} />
          </Link>
        </div>
        <div className="h-[280px]">
          <Scene3D accent={accentHex} height={280} camera={{ position: [0, 0, 4.4], fov: 45 }}>
            {model === 'heart'
              ? <Heart3D accent={accentHex} scale={1.1} />
              : <Brain3D accent={accentHex} scale={1.05} />}
          </Scene3D>
        </div>
      </div>

      {/* metric strip */}
      {metrics.length > 0 && (
        <div className="holo-panel p-5 grid grid-cols-2 sm:grid-cols-4 gap-4">
          {metrics.map((m) => (
            <div key={m.label} className="text-center">
              <div className="text-2xl font-mono font-bold" style={{ color: accentHex }}>{m.value}</div>
              <div className="text-[10px] tracking-[0.25em] uppercase text-low mt-1">{m.label}</div>
            </div>
          ))}
        </div>
      )}

      {/* capability chips */}
      {classes.length > 0 && (
        <div className="holo-panel p-5">
          <h2 className="text-sm font-mono font-bold text-hi tracking-wide mb-4">{t('ui.modality.detects')}</h2>
          <div className="grid sm:grid-cols-2 gap-3">
            {classes.map((c) => (
              <div key={c.name} className="flex items-start gap-3 rounded-lg p-3 hover-glow"
                   style={{ border: '1px solid var(--edge)', background: 'var(--paneldeep)' }}>
                <span className="w-2 h-2 rounded-full mt-1.5 shrink-0"
                      style={{ background: accentHex, boxShadow: `0 0 8px ${accentHex}` }} />
                <div>
                  <div className="text-sm font-medium text-hi">{c.name}</div>
                  {c.desc && <div className="text-xs text-low">{c.desc}</div>}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
