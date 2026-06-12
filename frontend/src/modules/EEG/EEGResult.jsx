import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, Brain, Trash2 } from 'lucide-react';
import toast from 'react-hot-toast';

import Badge from '../../components/UI/Badge.jsx';
import ConfirmDialog from '../../components/UI/ConfirmDialog.jsx';
import Loader from '../../components/UI/Loader.jsx';
import eegService from '../../services/eegService.js';
import patientService from '../../services/patientService.js';
import { formatDate } from '../../utils/formatters.js';
import { useI18n } from '../../i18n/LanguageContext.jsx';
import { useTokens } from '../../theme/ThemeContext.jsx';

const STATUS_VARIANT = { completed: 'success', processing: 'warning', pending: 'gray', failed: 'danger' };

const IIIC = [
  ['SZ', 'sz', true],
  ['LPD', 'lpd', true],
  ['GPD', 'gpd', true],
  ['LRDA', 'lrda', false],
  ['GRDA', 'grda', false],
  ['Other', 'other', false],
];

export default function EEGResult() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { t } = useI18n();
  const { colors } = useTokens();
  const [eeg, setEeg] = useState(null);
  const [patient, setPatient] = useState(null);
  const [loading, setLoading] = useState(true);
  const [confirm, setConfirm] = useState(false);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const e = await eegService.getById(id);
        if (!alive) return;
        setEeg(e);
        if (e.patient) {
          const p = await patientService.getById(e.patient).catch(() => null);
          if (alive) setPatient(p);
        }
      } catch {
        toast.error(t('eeg.result.loadFailed'));
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => { alive = false; };
  }, [id]);

  const onDelete = async () => {
    try {
      await eegService.delete(id);
      toast.success(t('eeg.result.deleted'));
      navigate(-1);
    } catch {
      toast.error(t('eeg.result.deleteFailed'));
    }
  };

  if (loading) return <Loader />;
  if (!eeg) return null;

  const violet = colors.violet;
  const red = colors.cardio;
  const dist = eeg.result_class_distribution || {};
  const dominant = eeg.result_dominant_pattern;
  const statusLabel = STATUS_VARIANT[eeg.status] ? t(`eeg.status.${eeg.status}`) : eeg.status;

  return (
    <div className="space-y-5 max-w-4xl">
      <div className="flex items-center justify-between">
        <button type="button" onClick={() => navigate(-1)} className="inline-flex items-center gap-2 text-sm text-mid hover:text-hi">
          <ArrowLeft size={16} /> {t('common.back')}
        </button>
        <button type="button" onClick={() => setConfirm(true)} className="inline-flex items-center gap-2 text-sm text-danger hover:opacity-80">
          <Trash2 size={16} /> {t('common.delete')}
        </button>
      </div>

      <div className="holo-panel p-6">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-11 h-11 rounded-xl flex items-center justify-center" style={{ background: 'rgb(var(--rgb-violet) / 0.12)', color: 'var(--violet-fg)' }}>
            <Brain size={22} />
          </div>
          <div>
            <h1 className="text-lg font-mono font-bold text-hi">EEG #{eeg.id}</h1>
            <div className="text-xs text-low">
              {patient ? `${patient.full_name} · ` : ''}{formatDate(eeg.created_at)}
              {'  '}<Badge variant={STATUS_VARIANT[eeg.status] || 'gray'}>{statusLabel}</Badge>
            </div>
          </div>
        </div>

        {eeg.status === 'completed' ? (
          <div className="grid md:grid-cols-2 gap-6">
            {/* dominant + distribution */}
            <div>
              <div className="text-[10px] tracking-[0.3em] uppercase text-low mb-1">{t('eeg.result.dominantPattern')}</div>
              <div className="flex items-end gap-3">
                <span className="text-4xl font-mono font-bold" style={{ color: IIIC.find((c) => c[0] === dominant)?.[2] ? red : violet }}>
                  {dominant || '—'}
                </span>
                {eeg.result_harmful === true
                  ? <Badge variant="danger">{t('eeg.harmful')}</Badge>
                  : <Badge variant="success">{t('eeg.result.noHarmful')}</Badge>}
              </div>

              <div className="text-[10px] tracking-[0.3em] uppercase text-low mt-5 mb-2">{t('eeg.result.distribution')}</div>
              <div className="space-y-2">
                {IIIC.map(([code, key, harmful]) => {
                  const pct = Math.round(((dist[code] ?? 0) * 100));
                  return (
                    <div key={code}>
                      <div className="flex justify-between text-xs mb-0.5">
                        <span className="text-mid" title={t(`eeg.classes.${key}`)}>
                          {code}{harmful && <span className="text-danger"> •</span>}
                        </span>
                        <span className="text-low font-mono">{pct}%</span>
                      </div>
                      <div className="w-full h-2 bg-gray-200 rounded overflow-hidden">
                        <div className="h-2 rounded transition-all"
                             style={{ width: `${pct}%`, background: harmful ? red : violet,
                                      boxShadow: pct > 0 ? `0 0 10px ${harmful ? red : violet}` : 'none' }} />
                      </div>
                    </div>
                  );
                })}
              </div>
              <p className="text-[10px] text-low mt-3"><span className="text-danger">•</span> {t('eeg.result.harmfulLegend')}</p>
            </div>

            {/* plot */}
            <div>
              <div className="text-[10px] tracking-[0.3em] uppercase text-low mb-2">{t('eeg.result.plotTitle')}</div>
              {eeg.plot_url ? (
                <img src={eeg.plot_url} alt={t('eeg.result.plotAlt')} className="w-full rounded-lg border border-edge" />
              ) : (
                <div className="text-sm text-low">{t('eeg.result.noPlot')}</div>
              )}
            </div>
          </div>
        ) : (
          <div className="text-sm" style={{ color: 'var(--violet-fg)' }}>
            {t('eeg.result.analysisStatus', { status: statusLabel })} {eeg.status === 'failed' ? t('eeg.result.seeReport') : ''}
          </div>
        )}
      </div>

      {eeg.result_report && (
        <div className="holo-panel p-5">
          <h2 className="text-sm font-mono font-bold text-hi tracking-wide mb-3">{t('eeg.result.report')}</h2>
          <pre className="text-xs text-mid whitespace-pre-wrap font-mono leading-relaxed">{eeg.result_report}</pre>
        </div>
      )}

      <ConfirmDialog
        open={confirm}
        title={t('eeg.deleteDialog.title')}
        description={t('eeg.deleteDialog.message', { id: eeg.id })}
        confirmLabel={t('common.delete')}
        onConfirm={() => { setConfirm(false); onDelete(); }}
        onClose={() => setConfirm(false)}
      />
    </div>
  );
}
