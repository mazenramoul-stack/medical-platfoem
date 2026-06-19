import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, Brain, Download, Save, Trash2 } from 'lucide-react';
import toast from 'react-hot-toast';

import Badge from '../../components/UI/Badge.jsx';
import ConfirmDialog from '../../components/UI/ConfirmDialog.jsx';
import Loader from '../../components/UI/Loader.jsx';
import Anatomy3DPanel from '../../components/three/Anatomy3DPanel.jsx';
import TumorBadge from './TumorBadge.jsx';
import ClassProbabilities from './ClassProbabilities.jsx';
import { mapMriToHighlight } from './mriAnatomy.js';
import { normalizeTumorType } from './tumorType.js';

import mriService from '../../services/mriService.js';
import patientService from '../../services/patientService.js';
import { formatDate, formatPercent } from '../../utils/formatters.js';
import { useI18n } from '../../i18n/LanguageContext.jsx';

const STATUS_VARIANT = { completed: 'success', processing: 'warning', pending: 'gray', failed: 'danger' };
const TAB_IDS = ['overlay', 'mask', 'original'];
const TYPE_KEYS = ['glioma', 'meningioma', 'pituitary', 'notumor', 'no_tumor'];

// Fallback for analyses created before `result_segmentation_confidence` existed:
// the value is still embedded in the saved report ("Segmentation Confidence: 99.82%").
function parseSegConfidence(report) {
  if (!report) return null;
  const m = report.match(/Segmentation Confidence:\s*([\d.]+)\s*%/i);
  if (!m) return null;
  const v = parseFloat(m[1]) / 100;
  return Number.isFinite(v) ? Math.max(0, Math.min(1, v)) : null;
}

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
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState('overlay');
  const [askDelete, setAskDelete] = useState(false);
  // Segmentation-mask analysis: null = not analysed (classifier fallback),
  // { present, x, y } once the U-Net mask has been read for tumour location.
  const [maskInfo, setMaskInfo] = useState(null);
  // On-demand explanation: the Explain (SHAP) panel renders both Grad-CAM and
  // SHAP, so there is no separate inline Grad-CAM image tab.
  const [explain, setExplain] = useState(null);
  const [explaining, setExplaining] = useState(false);

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
      } catch (e) {
        toast.error(e.response?.data?.detail || t('mri.result.loadFailed'));
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => { alive = false; };
  }, [id]);

  // Read the U-Net segmentation mask to drive the 3D brain: where the tumour is
  // (centroid of the bright region, projected to brain coords) and whether one is
  // present at all. Falls back to the classifier (maskInfo=null) if there is no
  // mask or it can't be read (e.g. CORS-tainted canvas).
  const maskUrl = mri ? mri.mask_url : null;
  useEffect(() => {
    if (!maskUrl) { setMaskInfo(null); return undefined; }
    let alive = true;
    const img = new Image();
    img.crossOrigin = 'anonymous';
    img.onload = () => {
      if (!alive) return;
      try {
        const W = 96;
        const H = 96;
        const canvas = document.createElement('canvas');
        canvas.width = W;
        canvas.height = H;
        const ctx = canvas.getContext('2d', { willReadFrequently: true });
        if (!ctx) { setMaskInfo(null); return; }
        ctx.drawImage(img, 0, 0, W, H);
        const { data } = ctx.getImageData(0, 0, W, H);
        let sx = 0;
        let sy = 0;
        let n = 0;
        let total = 0;
        for (let i = 0; i < data.length; i += 4) {
          if (data[i + 3] < 8) continue; // transparent
          total += 1;
          const lum = 0.299 * data[i] + 0.587 * data[i + 1] + 0.114 * data[i + 2];
          if (lum > 110) { // bright = tumour pixel in the binary mask
            const idx = i / 4;
            sx += idx % W;
            sy += Math.floor(idx / W);
            n += 1;
          }
        }
        const frac = total ? n / total : 0;
        if (n === 0 || frac <= 0.003) { setMaskInfo({ present: false }); return; }
        if (frac > 0.6) { setMaskInfo(null); return; } // saturated/invalid → classifier
        const nx = (sx / n) / W;
        const ny = (sy / n) / H;
        setMaskInfo({ present: true, x: (nx - 0.5) * 1.7, y: (0.5 - ny) * 1.3 });
      } catch {
        setMaskInfo(null); // tainted canvas (CORS) → classifier fallback
      }
    };
    img.onerror = () => { if (alive) setMaskInfo(null); };
    img.src = maskUrl;
    return () => { alive = false; };
  }, [maskUrl]);

  // 3D brain: localized tumour marker from the segmentation mask when available,
  // else the classifier verdict (whole cerebrum). Caption points to the 2D scan.
  // Grad-CAM peak from the on-demand explanation, projected to brain coords (same
  // formula the mask centroid used: flipped Y, per-axis scales).
  const gradcamPeak = useMemo(
    () => (explain?.peak
      ? { x: (explain.peak.nx - 0.5) * 1.7, y: (0.5 - explain.peak.ny) * 1.3 }
      : null),
    [explain],
  );
  const brainHighlight = useMemo(
    () => mapMriToHighlight(mri, maskInfo, gradcamPeak),
    [mri, maskInfo, gradcamPeak],
  );

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

  const onSave = () => {
    toast.success(t('mri.result.saved'));
    navigate(patient ? `/patients/${patient.id}` : '/patients');
  };

  const onExplain = async () => {
    setExplaining(true);
    try {
      setExplain(await mriService.explainMri(mri.id));
    } catch (e) {
      toast.error(e.response?.data?.detail || t('mri.explain.failed'));
    } finally {
      setExplaining(false);
    }
  };

  const tabIds = TAB_IDS;
  const activeUrl = tab === 'mask' ? mri.mask_url
    : tab === 'original' ? mri.file_url
    : mri.overlay_url;
  const typeKey = normalizeTumorType(mri.result_tumor_type);
  const typeLabel = TYPE_KEYS.includes(typeKey)
    ? t(`mri.types.${typeKey === 'no_tumor' ? 'notumor' : typeKey}`)
    : (mri.result_tumor_type || '—');
  // Segmentation-only result: the classifier never ran (no classification
  // confidence) yet a U-Net mask exists. There, "Classification confidence" and
  // "Tumor type" don't apply — show the segmentation confidence under a plain
  // "Confidence" label and drop the tumour-type cell.
  const classificationRan = typeof mri.result_confidence === 'number';
  const segmentationOnly = !classificationRan && Boolean(mri.mask_url);
  // Prefer the structured field; fall back to the value parsed from the report
  // so segmentation analyses created before that field existed still show it.
  const segConfidence = typeof mri.result_segmentation_confidence === 'number'
    ? mri.result_segmentation_confidence
    : parseSegConfidence(mri.result_report);
  const confidenceValue = segmentationOnly ? segConfidence : mri.result_confidence;
  const confidenceLabel = segmentationOnly ? t('mri.result.confidence') : t('mri.result.classificationConfidence');

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
              {tabIds.map((tid) => (
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
                  <span className="text-gray-600">{confidenceLabel}</span>
                  <span className="font-medium text-gray-900">{formatPercent(confidenceValue)}</span>
                </div>
                <ConfidenceBar value={confidenceValue} />
              </div>
              <div className={`grid ${segmentationOnly ? 'grid-cols-1' : 'grid-cols-2'} gap-2 text-xs`}>
                {!segmentationOnly && (
                  <div className="bg-gray-50 rounded px-3 py-2">
                    <div className="text-gray-500">{t('mri.result.tumorType')}</div>
                    <div className="text-gray-900 font-medium">{typeLabel}</div>
                  </div>
                )}
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

        </div>
      </div>

      {mri.result_class_probabilities && (
        <div className="bg-card rounded-xl shadow-sm border border-gray-200 p-5">
          <h3 className="text-base font-semibold text-gray-900 mb-3">{t('mri.classProb.title')}</h3>
          <ClassProbabilities probabilities={mri.result_class_probabilities} />
        </div>
      )}

      {mri.result_tumor_detected !== null && (
        <div className="bg-card rounded-xl shadow-sm border border-gray-200 p-5">
          <h3 className="text-base font-semibold text-gray-900 mb-3">{t('mri.explain.title')}</h3>
          {explain ? (
            <div className="space-y-3">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <div className="text-xs font-medium text-gray-500 mb-1">{t('mri.explain.gradcamLabel')}</div>
                  <img src={explain.gradcam_path} alt="Grad-CAM" className="max-w-full max-h-[26rem] rounded shadow-sm" />
                </div>
                <div>
                  <div className="text-xs font-medium text-gray-500 mb-1">{t('mri.explain.shapLabel')}</div>
                  <img src={explain.shap_path} alt="SHAP" className="max-w-full max-h-[26rem] rounded shadow-sm" />
                </div>
              </div>
              <p className="text-xs text-gray-600">
                {t('mri.explain.agreement', { rho: (explain.agreement?.spearman ?? 0).toFixed(2) })}
              </p>
            </div>
          ) : (
            <>
              <p className="text-xs text-gray-500 mb-3">{t('mri.explain.hint')}</p>
              <button
                type="button"
                onClick={onExplain}
                disabled={mri.status !== 'completed' || explaining}
                className="inline-flex items-center gap-2 bg-primary text-white px-4 py-2 rounded-lg text-sm font-medium hover:opacity-90 disabled:opacity-50"
              >
                {explaining ? t('mri.explain.running') : t('mri.explain.button')}
              </button>
            </>
          )}
        </div>
      )}

      {mri.status === 'completed' && <Anatomy3DPanel highlight={brainHighlight} />}

      {mri.result_report && (
        <div className="bg-card rounded-xl shadow-sm border border-gray-200 p-5">
          <h3 className="text-base font-semibold text-gray-900 mb-3">{t('mri.result.inferenceReport')}</h3>
          <pre className="text-[11px] font-mono text-gray-700 whitespace-pre-wrap leading-relaxed max-h-96 overflow-auto bg-gray-50 rounded p-3 border border-gray-100">
{mri.result_report}
          </pre>
        </div>
      )}

      <div className="flex flex-wrap gap-2 justify-end pt-2">
        <button
          type="button"
          onClick={onSave}
          disabled={mri.status !== 'completed'}
          className="inline-flex items-center gap-2 bg-success text-ink px-4 py-2 rounded-lg text-sm font-medium hover:opacity-90 disabled:opacity-50"
        >
          <Save size={16} />
          {t('common.save')}
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
