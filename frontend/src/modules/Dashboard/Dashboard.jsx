import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Activity, Brain, FileText, Heart, HeartPulse, Plus, Upload, Users, Waves } from 'lucide-react';

import RecentActivity from './RecentActivity.jsx';
import TiltCard from '../../components/fx/TiltCard.jsx';
import Scene3D from '../../components/three/Scene3D.jsx';
import Brain3D from '../../components/three/Brain3D.jsx';
import Heart3D from '../../components/three/Heart3D.jsx';
import { useAuth } from '../../hooks/useAuth.js';
import { useI18n } from '../../i18n/LanguageContext.jsx';
import { useTokens } from '../../theme/ThemeContext.jsx';
import ecgService from '../../services/ecgService.js';
import echoService from '../../services/echoService.js';
import eegService from '../../services/eegService.js';
import mriService from '../../services/mriService.js';
import patientService from '../../services/patientService.js';
import reportService from '../../services/reportService.js';
import { normalizeTumorType } from '../MRI/tumorType.js';

function firstName(fullName, fallback) {
  return (fullName || '').trim().split(/\s+/)[0] || fallback;
}

export default function Dashboard() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const { t } = useI18n();
  const { colors } = useTokens();
  const [counts, setCounts] = useState({ patients: null, mri: null, ecg: null, echo: null, eeg: null, reports: null });
  const [recent, setRecent] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const [patients, mri, ecg, echo, eeg, reports] = await Promise.all([
          patientService.getAll().catch(() => []),
          mriService.getAll().catch(() => []),
          ecgService.getAll().catch(() => []),
          echoService.getAll().catch(() => []),
          eegService.getAll().catch(() => []),
          reportService.getAll().catch(() => []),
        ]);
        if (!alive) return;
        setCounts({ patients: patients.length, mri: mri.length, ecg: ecg.length, echo: echo.length, eeg: eeg.length, reports: reports.length });
        const merged = [
          ...mri.map((m) => ({ type: 'mri', id: m.id, created_at: m.created_at, status: m.status, label: normalizeTumorType(m.result_tumor_type) || 'MRI', patient: m.patient })),
          ...ecg.map((e) => ({ type: 'ecg', id: e.id, created_at: e.created_at, status: e.status, label: e.result_arrhythmia_type || 'ECG', patient: e.patient })),
          ...echo.map((ec) => ({ type: 'echo', id: ec.id, created_at: ec.created_at, status: ec.status, label: ec.result_ef_category || 'Echo', patient: ec.patient })),
          ...eeg.map((eg) => ({ type: 'eeg', id: eg.id, created_at: eg.created_at, status: eg.status, label: eg.result_dominant_pattern || 'EEG', patient: eg.patient })),
        ].sort((a, b) => new Date(b.created_at) - new Date(a.created_at)).slice(0, 10);
        setRecent(merged);
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => { alive = false; };
  }, []);

  const tiles = [
    { key: 'patients', icon: Users,      accent: colors.blue,   to: '/patients', value: counts.patients },
    { key: 'mri',      icon: Brain,      accent: colors.neuro,  to: '/mri',      value: counts.mri },
    { key: 'ecg',      icon: Heart,      accent: colors.cardio, to: '/ecg',      value: counts.ecg },
    { key: 'echo',     icon: HeartPulse, accent: colors.amber,  to: '/echo',     value: counts.echo },
    { key: 'eeg',      icon: Waves,      accent: colors.violet, to: '/eeg',      value: counts.eeg },
    { key: 'reports',  icon: FileText,   accent: colors.neuro,  to: '/reports',  value: counts.reports },
  ];

  return (
    <div className="space-y-6">
      {/* ---- 3D hero ---- */}
      <div className="holo-panel relative overflow-hidden">
        <div className="grid md:grid-cols-2 items-center">
          <div className="p-6 sm:p-8 relative z-10">
            <div className="font-mono text-[10px] tracking-[0.4em] text-neuro uppercase mb-2">{t('dashboard.commandCenter')}</div>
            <h1 className="text-2xl sm:text-3xl font-mono font-bold text-hi">
              {t('dashboard.welcomeBack')} <span className="text-neuro">{firstName(user?.full_name, t('dashboard.doctor'))}</span>
            </h1>
            <p className="text-mid text-sm mt-2 max-w-md">
              {t('dashboard.heroDescription')}
            </p>
            <div className="mt-4 inline-flex items-center gap-2 text-xs text-mid">
              <span className="w-2 h-2 rounded-full animate-pulseGlow" style={{ background: 'var(--neuro)', boxShadow: '0 0 8px var(--neuro)' }} />
              {t('dashboard.allSystems')}
            </div>
          </div>
          <div className="h-[240px] md:h-[260px]">
            <Scene3D accent={colors.neuro} height={260} camera={{ position: [0, 0, 5.6], fov: 45 }}>
              <group position={[-1.4, 0.1, 0]} scale={0.78}><Brain3D accent={colors.neuro} /></group>
              <group position={[1.5, -0.1, 0]} scale={0.66}><Heart3D accent={colors.cardio} /></group>
            </Scene3D>
          </div>
        </div>
      </div>

      {/* ---- modality tiles ---- */}
      <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-4">
        {tiles.map((tile) => {
          const Icon = tile.icon;
          return (
            <TiltCard key={tile.key} accent={tile.accent} height={150} onClick={() => navigate(tile.to)}>
              <div className="h-full flex flex-col justify-between p-4 relative z-[1]">
                <div className="flex items-start justify-between">
                  <Icon size={26} style={{ color: tile.accent, filter: `drop-shadow(0 0 8px ${tile.accent})` }} />
                  <span className="text-2xl font-mono font-bold text-hi">{tile.value ?? '—'}</span>
                </div>
                <div>
                  <div className="text-hi font-mono font-bold tracking-wide">{t(`dashboard.tiles.${tile.key}`)}</div>
                  <div className="text-[10px] tracking-[0.3em]" style={{ color: tile.accent }}>{t(`dashboard.sub.${tile.key}`)}</div>
                </div>
              </div>
            </TiltCard>
          );
        })}
      </div>

      {/* ---- recent + quick actions ---- */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2">
          <RecentActivity items={recent} loading={loading} />
        </div>
        <div className="holo-panel p-5">
          <h2 className="text-sm font-mono font-bold text-hi mb-3 tracking-wide">{t('dashboard.quickActions')}</h2>
          <div className="space-y-2">
            <Link
              to="/patients/new"
              className="flex items-center gap-2 justify-center w-full text-sm text-ink px-3 py-2.5 rounded-lg font-semibold"
              style={{ background: 'linear-gradient(135deg, var(--neuro), var(--violet))', boxShadow: '0 0 20px var(--glow-strong)' }}
            >
              <Plus size={16} /> {t('dashboard.newPatient')}
            </Link>
            <Link
              to="/patients"
              className="flex items-center gap-2 justify-center w-full text-sm text-mid border border-edge px-3 py-2.5 rounded-lg hover-glow"
            >
              <Upload size={16} /> {t('dashboard.uploadMriEcg')}
            </Link>
          </div>
          <div className="mt-5 pt-5 text-xs text-low flex items-center gap-2" style={{ borderTop: '1px solid var(--edge)' }}>
            <Activity size={14} className="text-neuro" /> {t('dashboard.systemOperational')}
          </div>
        </div>
      </div>
    </div>
  );
}
