import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, HeartPulse, Trash2 } from 'lucide-react';
import toast from 'react-hot-toast';

import Badge from '../../components/UI/Badge.jsx';
import ConfirmDialog from '../../components/UI/ConfirmDialog.jsx';
import Loader from '../../components/UI/Loader.jsx';
import echoService from '../../services/echoService.js';
import patientService from '../../services/patientService.js';
import { formatDate } from '../../utils/formatters.js';
import { useI18n } from '../../i18n/LanguageContext.jsx';
import { useTokens } from '../../theme/ThemeContext.jsx';

const STATUS_VARIANT = { completed: 'success', processing: 'warning', pending: 'gray', failed: 'danger' };

export default function EchoResult() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { t } = useI18n();
  const { colors } = useTokens();
  const [echo, setEcho] = useState(null);
  const [patient, setPatient] = useState(null);
  const [loading, setLoading] = useState(true);
  const [confirm, setConfirm] = useState(false);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const e = await echoService.getById(id);
        if (!alive) return;
        setEcho(e);
        if (e.patient) {
          const p = await patientService.getById(e.patient).catch(() => null);
          if (alive) setPatient(p);
        }
      } catch {
        toast.error(t('echo.result.loadFailed'));
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => { alive = false; };
  }, [id]);

  const onDelete = async () => {
    try {
      await echoService.delete(id);
      toast.success(t('echo.result.deleted'));
      navigate(-1);
    } catch {
      toast.error(t('echo.result.deleteFailed'));
    }
  };

  if (loading) return <Loader />;
  if (!echo) return null;

  const efColor = (cat) => {
    if (!cat) return colors.textLow;
    if (cat.startsWith('Normal')) return colors.neuro;
    if (cat.startsWith('Mildly')) return colors.amber;
    return colors.cardio;
  };

  const categoryLabel = (cat) => {
    if (!cat) return '—';
    const known = ['Normal', 'Mildly reduced', 'Reduced'];
    return known.includes(cat) ? t(`echo.categories.${cat}`) : cat;
  };

  const ef = echo.result_ef;
  const color = efColor(echo.result_ef_category);
  const pct = typeof ef === 'number' ? Math.max(0, Math.min(100, ef)) : 0;
  const statusLabel = STATUS_VARIANT[echo.status] ? t(`echo.status.${echo.status}`) : echo.status;

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
          <div className="w-11 h-11 rounded-xl flex items-center justify-center" style={{ background: 'rgb(var(--rgb-amber) / 0.12)', color: 'var(--amber-fg)' }}>
            <HeartPulse size={22} />
          </div>
          <div>
            <h1 className="text-lg font-mono font-bold text-hi">Echo #{echo.id}</h1>
            <div className="text-xs text-low">
              {patient ? `${patient.full_name} · ` : ''}{formatDate(echo.created_at)}
              {'  '}<Badge variant={STATUS_VARIANT[echo.status] || 'gray'}>{statusLabel}</Badge>
            </div>
          </div>
        </div>

        {echo.status === 'completed' ? (
          <div className="grid md:grid-cols-2 gap-6">
            {/* EF */}
            <div>
              <div className="text-[10px] tracking-[0.3em] uppercase text-low mb-1">{t('echo.result.ejectionFraction')}</div>
              <div className="flex items-end gap-2">
                <span className="text-5xl font-mono font-bold" style={{ color }}>{typeof ef === 'number' ? ef.toFixed(1) : '—'}</span>
                <span className="text-xl text-low mb-1">%</span>
              </div>
              <div className="mt-2">
                <Badge variant={echo.result_ef_category?.startsWith('Normal') ? 'success' : echo.result_ef_category?.startsWith('Mildly') ? 'warning' : 'danger'}>
                  {categoryLabel(echo.result_ef_category)}
                </Badge>
              </div>
              <div className="w-full h-2.5 bg-gray-200 rounded mt-4 overflow-hidden">
                <div className="h-2.5 rounded transition-all" style={{ width: `${pct}%`, background: color, boxShadow: `0 0 12px ${color}` }} />
              </div>
              <div className="flex justify-between text-[10px] text-low mt-1"><span>0</span><span>40</span><span>50</span><span>100</span></div>
              <div className="grid grid-cols-2 gap-3 mt-5 text-sm">
                <div className="rounded-lg p-3" style={{ border: '1px solid var(--edge)', background: 'var(--paneldeep)' }}>
                  <div className="text-low text-xs">{t('echo.result.edArea')}</div>
                  <div className="text-hi font-mono">{echo.result_ed_area ?? '—'} px</div>
                </div>
                <div className="rounded-lg p-3" style={{ border: '1px solid var(--edge)', background: 'var(--paneldeep)' }}>
                  <div className="text-low text-xs">{t('echo.result.esArea')}</div>
                  <div className="text-hi font-mono">{echo.result_es_area ?? '—'} px</div>
                </div>
              </div>
            </div>
            {/* overlay */}
            <div>
              <div className="text-[10px] tracking-[0.3em] uppercase text-low mb-2">{t('echo.result.segmentation')}</div>
              {echo.overlay_url ? (
                <img src={echo.overlay_url} alt={t('echo.result.overlayAlt')} className="w-full rounded-lg border border-edge" />
              ) : (
                <div className="text-sm text-low">{t('echo.result.noOverlay')}</div>
              )}
            </div>
          </div>
        ) : (
          <div className="text-sm text-cardio">
            {t('echo.result.analysisStatus', { status: statusLabel })} {echo.status === 'failed' ? t('echo.result.seeReport') : ''}
          </div>
        )}
      </div>

      {echo.result_report && (
        <div className="holo-panel p-5">
          <h2 className="text-sm font-mono font-bold text-hi tracking-wide mb-3">{t('echo.result.report')}</h2>
          <pre className="text-xs text-mid whitespace-pre-wrap font-mono leading-relaxed">{echo.result_report}</pre>
        </div>
      )}

      <ConfirmDialog
        open={confirm}
        title={t('echo.history.deleteTitle')}
        description={t('echo.history.deleteMessage', { id: echo.id })}
        confirmLabel={t('common.delete')}
        onConfirm={() => { setConfirm(false); onDelete(); }}
        onClose={() => setConfirm(false)}
      />
    </div>
  );
}
