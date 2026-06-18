import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { Activity, AlertTriangle, ArrowLeft, Download, Heart, Save, Trash2 } from 'lucide-react';
import toast from 'react-hot-toast';

import Badge from '../../components/UI/Badge.jsx';
import ConfirmDialog from '../../components/UI/ConfirmDialog.jsx';
import Loader from '../../components/UI/Loader.jsx';
import Anatomy3DPanel from '../../components/three/Anatomy3DPanel.jsx';
import HRVMetrics from './HRVMetrics.jsx';
import PathologyTable from './PathologyTable.jsx';
import { mapEcgToHighlight } from './ecgAnatomy.js';

import ecgService from '../../services/ecgService.js';
import patientService from '../../services/patientService.js';
import { formatDate, formatPercent } from '../../utils/formatters.js';
import { useI18n } from '../../i18n/LanguageContext.jsx';

const STATUS_VARIANT = { completed: 'success', processing: 'warning', pending: 'gray', failed: 'danger' };

function ConfidenceBar({ value, abnormal }) {
  const pct = typeof value === 'number' ? Math.max(0, Math.min(1, value)) * 100 : 0;
  return (
    <div className="w-full h-2 bg-gray-200 rounded">
      <div
        className={'h-2 rounded transition-all ' + (abnormal ? 'bg-danger' : 'bg-success')}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

export default function ECGResult() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { t } = useI18n();
  const [ecg, setEcg] = useState(null);
  const [patient, setPatient] = useState(null);
  const [loading, setLoading] = useState(true);
  const [askDelete, setAskDelete] = useState(false);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const e = await ecgService.getById(id);
        if (!alive) return;
        setEcg(e);
        const p = await patientService.getById(e.patient).catch(() => null);
        if (!alive) return;
        setPatient(p);
      } catch (err) {
        toast.error(err.response?.data?.detail || t('ecg.result.loadFailed'));
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => { alive = false; };
  }, [id]);

  // Map the ECG findings to the implicated heart structures for the 3D panel.
  const heartHighlight = useMemo(() => mapEcgToHighlight(ecg), [ecg]);

  if (loading) return <Loader label={t('ecg.result.loading')} className="py-12" />;
  if (!ecg)    return <div className="py-12 text-center text-sm text-gray-500">{t('ecg.result.notFound')}</div>;

  const onDelete = async () => {
    try {
      await ecgService.delete(ecg.id);
      toast.success(t('ecg.result.deleted'));
      navigate(patient ? `/patients/${patient.id}` : '/patients');
    } catch (e) {
      toast.error(e.response?.data?.detail || t('ecg.result.deleteFailed'));
    }
  };

  const onSave = () => {
    toast.success(t('ecg.result.saved'));
    navigate(patient ? `/patients/${patient.id}` : '/patients');
  };

  const hrv = ecg.result_hrv_metrics || {};
  const abnormal = !!ecg.result_arrhythmia_detected;
  const hr = hrv.heart_rate_bpm;
  const hrClsRaw = hrv.hr_classification;
  const hrCls = hrClsRaw && hrClsRaw !== 'N/A'
    ? (['Normal', 'Tachycardia', 'Bradycardia'].includes(hrClsRaw) ? t(`ecg.hrCls.${hrClsRaw}`) : hrClsRaw)
    : '—';
  const flags = hrv.additional_flags || [];

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <button type="button" onClick={() => navigate(-1)} className="inline-flex items-center gap-1 text-sm text-gray-600 hover:text-gray-900">
          <ArrowLeft size={16} /> {t('common.back')}
        </button>
        <div className="flex items-center gap-2 text-sm">
          <Badge variant={STATUS_VARIANT[ecg.status] || 'gray'}>
            {STATUS_VARIANT[ecg.status] ? t(`ecg.status.${ecg.status}`) : ecg.status}
          </Badge>
          <span className="text-gray-500">{formatDate(ecg.created_at)}</span>
        </div>
      </div>

      {patient && (
        <Link to={`/patients/${patient.id}`} className="inline-flex items-center gap-2 text-sm text-gray-700 hover:text-primary">
          <Heart size={16} className="text-danger" />
          {t('ecg.result.forPatientPrefix')} <strong>{patient.full_name}</strong>
        </Link>
      )}

      {ecg.status !== 'completed' && (
        <div className={
          'rounded-xl border p-4 text-sm '
          + (ecg.status === 'failed' ? 'border-red-200 bg-red-50 text-red-800' : 'border-amber-200 bg-amber-50 text-amber-800')
        }>
          {t('ecg.result.analysisStatus', { status: STATUS_VARIANT[ecg.status] ? t(`ecg.status.${ecg.status}`) : ecg.status })}
          {ecg.status === 'failed' ? ` ${t('ecg.result.seeReport')}` : ''}
        </div>
      )}

      {ecg.plot_url && (
        <div className="bg-card rounded-xl shadow-sm border border-gray-200 overflow-hidden">
          <div className="flex items-center justify-between px-5 py-3 border-b border-gray-200">
            <h2 className="text-sm font-semibold text-gray-900">{t('ecg.result.plotTitle')}</h2>
            <a href={ecg.plot_url} download className="inline-flex items-center gap-1 text-xs text-gray-600 hover:text-primary">
              <Download size={14} /> {t('common.download')}
            </a>
          </div>
          <div className="bg-gray-50 p-3 overflow-auto">
            <img src={ecg.plot_url} alt={t('ecg.result.plotAlt')} className="max-w-full rounded shadow-sm mx-auto" />
          </div>
        </div>
      )}

      {ecg.status === 'completed' && (
        <div className={'rounded-xl shadow-sm border p-5 ' + (abnormal ? 'border-red-200 bg-red-50' : 'border-green-200 bg-green-50')}>
          <div className="flex items-center justify-between gap-4 flex-wrap">
            <div>
              <div className="text-xs font-semibold uppercase tracking-wide text-gray-600">{t('ecg.result.primaryDiagnosis')}</div>
              <div className={'text-2xl font-bold mt-1 ' + (abnormal ? 'text-danger' : 'text-success')}>
                {ecg.result_arrhythmia_type || '—'}
              </div>
              <div className="text-sm text-gray-700 mt-1">
                {t('ecg.result.statusLabel')}: <strong>{abnormal ? t('ecg.result.abnormal') : t('ecg.result.normal')}</strong>
              </div>
            </div>
            <div className="min-w-[180px] flex-1 max-w-sm">
              <div className="flex justify-between text-xs text-gray-700 mb-1">
                <span>{t('ecg.result.confidence')}</span>
                <span className="font-medium">{formatPercent(ecg.result_confidence)}</span>
              </div>
              <ConfidenceBar value={ecg.result_confidence} abnormal={abnormal} />
            </div>
          </div>
        </div>
      )}

      {ecg.status === 'completed' && <Anatomy3DPanel highlight={heartHighlight} />}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="bg-card rounded-xl shadow-sm border border-gray-200 p-5">
          <h3 className="text-sm font-semibold text-gray-900 mb-3">{t('ecg.result.hrvTitle')}</h3>
          <HRVMetrics metrics={hrv} />
        </div>

        <div className="bg-card rounded-xl shadow-sm border border-gray-200 p-5">
          <h3 className="text-sm font-semibold text-gray-900 mb-3">{t('ecg.result.heartRateTitle')}</h3>
          <div className="flex items-end gap-2 mb-2">
            <Activity size={24} className="text-primary mb-1" />
            <div className="text-4xl font-bold text-gray-900 leading-none">
              {typeof hr === 'number' ? hr.toFixed(0) : '—'}
            </div>
            <div className="text-sm text-gray-500 mb-1">{t('ecg.result.bpm')}</div>
          </div>
          <Badge variant={hrClsRaw === 'Normal' ? 'success' : (!hrClsRaw || hrClsRaw === 'N/A') ? 'gray' : 'warning'}>
            {hrCls}
          </Badge>
          <div className="mt-3 text-xs text-gray-500">
            {t('ecg.result.normalRange')}
          </div>
        </div>

        <div className="bg-card rounded-xl shadow-sm border border-gray-200 p-5">
          <h3 className="text-sm font-semibold text-gray-900 mb-3">{t('ecg.result.flagsTitle')}</h3>
          {flags.length === 0 ? (
            <p className="text-sm text-gray-500">{t('ecg.result.noFlags')}</p>
          ) : (
            <ul className="space-y-2">
              {flags.map((f, i) => (
                <li key={i} className="flex items-start gap-2 text-sm text-gray-800">
                  <AlertTriangle size={14} className="text-warning mt-0.5 shrink-0" />
                  <span>{f}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      {ecg.result_pathology_probabilities && (
        <div className="bg-card rounded-xl shadow-sm border border-gray-200 p-5">
          <h3 className="text-sm font-semibold text-gray-900 mb-3">{t('ecg.result.pathologyTitle')}</h3>
          <PathologyTable results={ecg.result_pathology_probabilities} />
        </div>
      )}

      {ecg.model_used && (
        <div className="bg-card rounded-xl shadow-sm border border-gray-200 p-5">
          <h3 className="text-sm font-semibold text-gray-900 mb-2">{t('ecg.result.modelsUsed')}</h3>
          <ul className="text-xs text-gray-700 space-y-1 list-disc list-inside">
            {ecg.model_used.split('|').map((m, i) => <li key={i}>{m.trim()}</li>)}
          </ul>
        </div>
      )}

      {ecg.result_report && (
        <div className="bg-card rounded-xl shadow-sm border border-gray-200 p-5">
          <h3 className="text-sm font-semibold text-gray-900 mb-2">{t('ecg.result.inferenceReport')}</h3>
          <pre className="text-[11px] font-mono text-gray-700 whitespace-pre-wrap leading-relaxed max-h-72 overflow-auto bg-gray-50 rounded p-3 border border-gray-100">
{ecg.result_report}
          </pre>
        </div>
      )}

      <div className="flex flex-wrap gap-2 justify-end pt-2">
        <button
          type="button"
          onClick={onSave}
          disabled={ecg.status !== 'completed'}
          className="inline-flex items-center gap-2 bg-success text-ink px-4 py-2 rounded-lg text-sm font-medium hover:opacity-90 disabled:opacity-50"
        >
          <Save size={16} />
          {t('common.save')}
        </button>
        <button
          type="button"
          onClick={() => setAskDelete(true)}
          className="inline-flex items-center gap-2 bg-white text-danger border border-red-200 px-4 py-2 rounded-lg text-sm font-medium hover:bg-red-50"
        >
          <Trash2 size={16} /> {t('common.delete')}
        </button>
      </div>

      <ConfirmDialog
        open={askDelete}
        onClose={() => setAskDelete(false)}
        onConfirm={onDelete}
        title={t('ecg.result.deleteTitle')}
        description={t('ecg.result.deleteDescription')}
        confirmLabel={t('common.delete')}
      />
    </div>
  );
}
