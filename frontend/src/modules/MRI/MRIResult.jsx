import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, Brain, Download, FileText, Trash2 } from 'lucide-react';
import toast from 'react-hot-toast';

import Badge from '../../components/UI/Badge.jsx';
import ConfirmDialog from '../../components/UI/ConfirmDialog.jsx';
import Loader from '../../components/UI/Loader.jsx';
import Anatomy3DPanel from '../../components/three/Anatomy3DPanel.jsx';
import TumorBadge from './TumorBadge.jsx';
import { mapMriToHighlight } from './mriAnatomy.js';

import mriService from '../../services/mriService.js';
import ecgService from '../../services/ecgService.js';
import patientService from '../../services/patientService.js';
import reportService from '../../services/reportService.js';
import { formatDate, formatPercent } from '../../utils/formatters.js';
import { useI18n } from '../../i18n/LanguageContext.jsx';

const STATUS_VARIANT = { completed: 'success', processing: 'warning', pending: 'gray', failed: 'danger' };
const TAB_IDS = ['overlay', 'mask', 'original'];
const TYPE_KEYS = ['glioma', 'meningioma', 'pituitary', 'notumor', 'no_tumor'];

function ConfidenceBar({ value }) {
  const pct = typeof value === 'number' ? Math.max(0, Math.min(1, value)) * 100 : 0;
  return (
    <div className="w-full h-2 bg-gray-200 rounded">
      <div
        className="h-2 bg-primary rounded transition-all"
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

export default function MRIResult() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { t } = useI18n();
  const [mri, setMri] = useState(null);
  const [patient, setPatient] = useState(null);
  const [completedEcgId, setCompletedEcgId] = useState(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState('overlay');
  const [askDelete, setAskDelete] = useState(false);
  const [generating, setGenerating] = useState(false);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const m = await mriService.getById(id);
        if (!alive) return;
        setMri(m);
        // Classification-only results have no overlay/mask — start on a tab that
        // actually has an image so the doctor doesn't land on an empty panel.
        if (!m.overlay_url) setTab(m.mask_url ? 'mask' : 'original');
        const p = await patientService.getById(m.patient).catch(() => null);
        if (!alive) return;
        setPatient(p);
        const ecgs = await ecgService.getByPatient(m.patient).catch(() => []);
        if (!alive) return;
        const completed = ecgs.find((e) => e.status === 'completed');
        if (completed) setCompletedEcgId(completed.id);
      } catch (e) {
        toast.error(e.response?.data?.detail || t('mri.result.loadFailed'));
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => { alive = false; };
  }, [id]);

  // Map the tumour finding to the brain (cerebrum) for the 3D panel; the actual
  // location is the 2D scan/overlay above (the 3D view is illustrative).
  const brainHighlight = useMemo(() => mapMriToHighlight(mri), [mri]);

  if (loading) return <Loader label={t('mri.result.loading')} className="py-12" />;
  if (!mri)    return <div className="py-12 text-center text-sm text-gray-500">{t('mri.result.notFound')}</div>;

  const onDelete = async () => {
    try {
      await mriService.delete(mri.id);
      toast.success(t('mri.result.deleted'));
      navigate(patient ? `/patients/${patient.id}` : '/patients');
    } catch (e) {
      toast.error(e.response?.data?.detail || t('mri.result.deleteFailed'));
    }
  };

  const onGenerateReport = async () => {
    if (!patient) return;
    setGenerating(true);
    try {
      const r = await reportService.generate({
        patientId: patient.id,
        mriId: mri.id,
        ecgId: completedEcgId,
      });
      toast.success(completedEcgId ? t('mri.result.combinedGenerated') : t('mri.result.mriOnlyGenerated'));
      const blob = await reportService.downloadPdf(r.id);
      triggerBlobDownload(blob, `report_${patient.id}_${r.id}.pdf`);
    } catch (e) {
      toast.error(e.response?.data?.detail || t('mri.result.reportFailed'));
    } finally {
      setGenerating(false);
    }
  };

  const activeUrl = tab === 'mask' ? mri.mask_url : tab === 'original' ? mri.file_url : mri.overlay_url;
  const typeKey = (mri.result_tumor_type || '').toLowerCase();
  const typeLabel = TYPE_KEYS.includes(typeKey)
    ? t(`mri.types.${typeKey === 'no_tumor' ? 'notumor' : typeKey}`)
    : (mri.result_tumor_type || '—');

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <button type="button" onClick={() => navigate(-1)} className="inline-flex items-center gap-1 text-sm text-gray-600 hover:text-gray-900">
          <ArrowLeft size={16} /> {t('common.back')}
        </button>
        <div className="flex items-center gap-2 text-sm">
          <Badge variant={STATUS_VARIANT[mri.status] || 'gray'}>
            {STATUS_VARIANT[mri.status] ? t(`mri.status.${mri.status}`) : mri.status}
          </Badge>
          <span className="text-gray-500">{formatDate(mri.created_at)}</span>
        </div>
      </div>

      {patient && (
        <Link to={`/patients/${patient.id}`} className="inline-flex items-center gap-2 text-sm text-gray-700 hover:text-primary">
          <Brain size={16} className="text-purple-700" />
          {t('mri.result.forPatientPrefix')} <strong>{patient.full_name}</strong>
        </Link>
      )}

      {mri.status !== 'completed' && (
        <div className={
          'rounded-xl border p-4 text-sm '
          + (mri.status === 'failed' ? 'border-red-200 bg-red-50 text-red-800' : 'border-amber-200 bg-amber-50 text-amber-800')
        }>
          {t('mri.result.analysisStatus', { status: STATUS_VARIANT[mri.status] ? t(`mri.status.${mri.status}`) : mri.status })}
          {mri.status === 'failed' ? ` ${t('mri.result.seeReport')}` : ''}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-5">
        <div className="lg:col-span-3">
          <div className="bg-card rounded-xl shadow-sm border border-gray-200 overflow-hidden">
            <div className="flex border-b border-gray-200">
              {TAB_IDS.map((tid) => (
                <button
                  key={tid}
                  type="button"
                  onClick={() => setTab(tid)}
                  className={
                    'px-5 py-3 text-sm font-medium border-b-2 transition '
                    + (tab === tid ? 'border-primary text-primary' : 'border-transparent text-gray-600 hover:text-gray-900')
                  }
                >
                  {t(`mri.result.tabs.${tid}`)}
                </button>
              ))}
              <div className="ml-auto pr-3 flex items-center">
                {activeUrl && (
                  <a
                    href={activeUrl}
                    download
                    className="inline-flex items-center gap-1 text-xs text-gray-600 hover:text-primary"
                  >
                    <Download size={14} /> {t('common.download')}
                  </a>
                )}
              </div>
            </div>
            <div className="bg-gray-50 min-h-[300px] flex items-center justify-center p-3">
              {activeUrl ? (
                <img src={activeUrl} alt={t(`mri.result.tabs.${tab}`)} className="max-w-full max-h-[60vh] rounded shadow-sm" />
              ) : (
                <p className="text-sm text-gray-500">{t('mri.result.noImage')}</p>
              )}
            </div>
          </div>
        </div>

        <div className="lg:col-span-2 space-y-4">
          <div className="bg-card rounded-xl shadow-sm border border-gray-200 p-5">
            <h2 className="text-base font-semibold text-gray-900 mb-3">{t('common.result')}</h2>
            <div className="flex items-center gap-2 mb-3">
              <TumorBadge tumorType={mri.result_tumor_type} detected={mri.result_tumor_detected} />
            </div>
            <div className="space-y-3 text-sm">
              <div>
                <div className="flex justify-between mb-1">
                  <span className="text-gray-600">{t('mri.result.classificationConfidence')}</span>
                  <span className="font-medium text-gray-900">{formatPercent(mri.result_confidence)}</span>
                </div>
                <ConfidenceBar value={mri.result_confidence} />
              </div>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div className="bg-gray-50 rounded px-3 py-2">
                  <div className="text-gray-500">{t('mri.result.tumorType')}</div>
                  <div className="text-gray-900 font-medium">{typeLabel}</div>
                </div>
                <div className="bg-gray-50 rounded px-3 py-2">
                  <div className="text-gray-500">{t('mri.result.detected')}</div>
                  <div className="text-gray-900 font-medium">{mri.result_tumor_detected ? t('common.yes') : t('common.no')}</div>
                </div>
              </div>
            </div>
          </div>

          {mri.model_used && (
            <div className="bg-card rounded-xl shadow-sm border border-gray-200 p-5">
              <h3 className="text-sm font-semibold text-gray-900 mb-2">{t('mri.result.modelsUsed')}</h3>
              <ul className="text-xs text-gray-700 space-y-1 list-disc list-inside">
                {mri.model_used.split('|').map((m, i) => (
                  <li key={i}>{m.trim()}</li>
                ))}
              </ul>
            </div>
          )}

          {mri.result_report && (
            <div className="bg-card rounded-xl shadow-sm border border-gray-200 p-5">
              <h3 className="text-sm font-semibold text-gray-900 mb-2">{t('mri.result.inferenceReport')}</h3>
              <pre className="text-[11px] font-mono text-gray-700 whitespace-pre-wrap leading-relaxed max-h-72 overflow-auto bg-gray-50 rounded p-3 border border-gray-100">
{mri.result_report}
              </pre>
            </div>
          )}
        </div>
      </div>

      {mri.status === 'completed' && <Anatomy3DPanel highlight={brainHighlight} />}

      <div className="flex flex-wrap gap-2 justify-end pt-2">
        <button
          type="button"
          onClick={onGenerateReport}
          disabled={generating || mri.status !== 'completed' || !patient}
          className="inline-flex items-center gap-2 bg-success text-ink px-4 py-2 rounded-lg text-sm font-medium hover:opacity-90 disabled:opacity-50"
        >
          <FileText size={16} />
          {completedEcgId ? t('mri.result.generateCombined') : t('mri.result.downloadPdf')}
        </button>
        <button
          type="button"
          onClick={() => setAskDelete(true)}
          className="inline-flex items-center gap-2 bg-white text-danger border border-edge px-4 py-2 rounded-lg text-sm font-medium hover:bg-red-50"
        >
          <Trash2 size={16} /> {t('common.delete')}
        </button>
      </div>

      <ConfirmDialog
        open={askDelete}
        onClose={() => setAskDelete(false)}
        onConfirm={onDelete}
        title={t('mri.result.deleteTitle')}
        description={t('mri.result.deleteDescription')}
        confirmLabel={t('common.delete')}
      />
    </div>
  );
}

function triggerBlobDownload(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = filename;
  document.body.appendChild(a); a.click();
  document.body.removeChild(a);
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
