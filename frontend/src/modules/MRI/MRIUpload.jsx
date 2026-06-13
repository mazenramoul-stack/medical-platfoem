import { useCallback, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { FileImage, Layers, Loader2, ScanLine, Upload, X } from 'lucide-react';
import toast from 'react-hot-toast';

import mriService from '../../services/mriService.js';
import { useFileDropzone } from '../../hooks/useFileDropzone.js';
import { MRI_ALLOWED_EXTENSIONS, MRI_MAX_BYTES } from '../../utils/constants.js';
import { formatBytes } from '../../utils/formatters.js';
import { useI18n } from '../../i18n/LanguageContext.jsx';

const ACCEPT = {
  'image/png':  ['.png'],
  'image/jpeg': ['.jpg', '.jpeg'],
  'image/tiff': ['.tif', '.tiff'],
  'image/bmp':  ['.bmp'],
  'application/dicom': ['.dcm'],
  'application/octet-stream': ['.nii', '.nii.gz'],
};

// Image-type → model routing thresholds.
const COLOR_SPREAD_THRESHOLD = 18;     // per-channel diff above which a pixel counts as "colored"
const COLORED_FRACTION_CUTOFF = 0.02;  // >2% colored pixels ⇒ colored/masked image ⇒ segmentation

/**
 * Inspect an uploaded image in the browser and decide which MRI model to run.
 * Returns a Promise resolving to:
 *   'classify' — effectively grayscale (black/white raw scan) → Swin 4-class
 *   'segment'  — has meaningful color (a mask / colored overlay)  → U-Net
 *   null       — could not decode (e.g. DICOM/NIfTI) → caller falls back to a default
 */
function detectImageMode(file) {
  return new Promise((resolve) => {
    if (!file || !file.type || !file.type.startsWith('image/')) {
      resolve(null);
      return;
    }
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      try {
        const W = 64, H = 64;
        const canvas = document.createElement('canvas');
        canvas.width = W;
        canvas.height = H;
        const ctx = canvas.getContext('2d', { willReadFrequently: true });
        if (!ctx) { resolve(null); return; }
        ctx.drawImage(img, 0, 0, W, H);
        const { data } = ctx.getImageData(0, 0, W, H);
        let colored = 0;
        let total = 0;
        for (let i = 0; i < data.length; i += 4) {
          const r = data[i], g = data[i + 1], b = data[i + 2], a = data[i + 3];
          if (a < 8) continue; // ignore transparent pixels
          total += 1;
          const spread = Math.max(Math.abs(r - g), Math.abs(g - b), Math.abs(r - b));
          if (spread > COLOR_SPREAD_THRESHOLD) colored += 1;
        }
        const frac = total ? colored / total : 0;
        resolve(frac > COLORED_FRACTION_CUTOFF ? 'segment' : 'classify');
      } catch {
        resolve(null);
      } finally {
        URL.revokeObjectURL(url);
      }
    };
    img.onerror = () => { URL.revokeObjectURL(url); resolve(null); };
    img.src = url;
  });
}

export default function MRIUpload({ patient, onComplete }) {
  const navigate = useNavigate();
  const { t } = useI18n();
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [progress, setProgress] = useState(0);
  const [uploading, setUploading] = useState(false);
  const [stage, setStage] = useState('idle'); // 'idle' | 'uploading' | 'inferring'
  const [mode, setMode] = useState('classify'); // 'classify' (B/W) | 'segment' (colored/mask)
  const [autoMode, setAutoMode] = useState(null); // detected value, or null if undetectable
  const [detecting, setDetecting] = useState(false);

  const onDrop = useCallback((accepted) => {
    const f = accepted[0];
    if (!f) return;
    setFile(f);
    setPreview(f.type.startsWith('image/') ? URL.createObjectURL(f) : null);
    setDetecting(true);
    setAutoMode(null);
    detectImageMode(f).then((detected) => {
      setDetecting(false);
      if (detected) {
        setAutoMode(detected);
        setMode(detected);
      } else {
        // Non-previewable (DICOM/NIfTI): raw scans are usually grayscale → classify.
        setAutoMode(null);
        setMode('classify');
      }
    });
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useFileDropzone({
    accept: ACCEPT, maxSize: MRI_MAX_BYTES, onDrop,
  });

  const reset = () => {
    setFile(null); setPreview(null); setProgress(0); setStage('idle');
    setMode('classify'); setAutoMode(null); setDetecting(false);
  };

  const onSubmit = async () => {
    if (!file || !patient) return;
    setUploading(true);
    setStage('uploading');
    setProgress(0);
    try {
      const analysis = await mriService.upload(patient.id, file, (p) => {
        setProgress(p);
        if (p >= 100) setStage('inferring');
      }, mode);
      toast.success(t('mri.upload.complete'));
      if (onComplete) onComplete(analysis);
      navigate(`/mri/${analysis.id}`);
    } catch (e) {
      const msg = e.response?.data?.detail || e.message || t('mri.upload.uploadFailed');
      toast.error(msg);
      setUploading(false);
      setStage('idle');
    }
  };

  const MODE_OPTIONS = [
    { key: 'classify', icon: ScanLine, label: t('mri.upload.modeClassify'), hint: t('mri.upload.modeClassifyHint') },
    { key: 'segment',  icon: Layers,   label: t('mri.upload.modeSegment'),  hint: t('mri.upload.modeSegmentHint') },
  ];

  const runningLabel = mode === 'segment'
    ? t('mri.upload.runningSegment')
    : t('mri.upload.runningClassify');

  return (
    <div className="space-y-4">
      {patient && (
        <div className="text-sm bg-blue-50 border border-blue-200 text-blue-900 rounded-md px-3 py-2">
          {t('mri.upload.forPatientPrefix')} <strong>{patient.full_name}</strong> (#{patient.id})
        </div>
      )}

      {!file && (
        <div
          {...getRootProps()}
          className={
            'border-2 border-dashed rounded-xl px-6 py-10 text-center cursor-pointer transition '
            + (isDragActive ? 'border-primary bg-blue-50' : 'border-gray-300 hover:border-primary hover:bg-blue-50/50')
          }
        >
          <input {...getInputProps()} />
          <div className="inline-flex items-center justify-center w-12 h-12 rounded-full bg-blue-50 text-primary mb-3">
            <Upload size={22} />
          </div>
          <p className="text-sm font-medium text-gray-900">
            {isDragActive ? t('mri.upload.dropActive') : t('mri.upload.drag')}
          </p>
          <p className="text-xs text-gray-500 mt-1">
            {t('mri.upload.formats', { formats: MRI_ALLOWED_EXTENSIONS.join(', ') })}
          </p>
          <p className="text-xs text-gray-500">{t('mri.upload.maxSize')}</p>
        </div>
      )}

      {file && (
        <div className="border border-gray-200 rounded-xl p-4 flex items-center gap-4">
          {preview ? (
            <img src={preview} alt="" className="w-16 h-16 rounded object-cover bg-gray-100" />
          ) : (
            <div className="w-16 h-16 rounded bg-gray-100 flex items-center justify-center text-gray-500">
              <FileImage size={24} />
            </div>
          )}
          <div className="flex-1 min-w-0">
            <div className="text-sm font-medium text-gray-900 truncate">{file.name}</div>
            <div className="text-xs text-gray-500">{formatBytes(file.size)}</div>
          </div>
          {!uploading && (
            <button type="button" onClick={reset} className="text-gray-400 hover:text-gray-600 p-1" aria-label={t('mri.upload.remove')}>
              <X size={18} />
            </button>
          )}
        </div>
      )}

      {/* Model routing: auto-detected from the image type, overridable */}
      {file && (
        <div className="border border-gray-200 rounded-xl p-3 space-y-2">
          <div className="text-xs font-medium text-gray-700 flex flex-wrap items-center gap-x-2 gap-y-1">
            <span>{t('mri.upload.modeTitle')}</span>
            {detecting && <span className="text-gray-400">{t('mri.upload.modeDetecting')}</span>}
            {!detecting && autoMode && (
              <span className="text-gray-400">
                · {autoMode === 'classify' ? t('mri.upload.modeAutoClassify') : t('mri.upload.modeAutoSegment')}
                {mode !== autoMode && ` · ${t('mri.upload.modeOverridden')}`}
              </span>
            )}
            {!detecting && !autoMode && (
              <span className="text-amber-600">· {t('mri.upload.modeAutoUnavailable')}</span>
            )}
          </div>
          <div className="grid grid-cols-2 gap-2">
            {MODE_OPTIONS.map((opt) => {
              const Icon = opt.icon;
              const active = mode === opt.key;
              return (
                <button
                  key={opt.key}
                  type="button"
                  onClick={() => setMode(opt.key)}
                  disabled={uploading}
                  className={
                    'text-left rounded-lg border px-3 py-2 transition disabled:opacity-50 '
                    + (active
                      ? 'border-primary bg-blue-50 ring-1 ring-primary'
                      : 'border-gray-200 hover:border-gray-300')
                  }
                >
                  <div className="flex items-center gap-2 text-sm font-medium text-gray-900">
                    <Icon size={15} className={active ? 'text-primary' : 'text-gray-400'} />
                    {opt.label}
                  </div>
                  <div className="text-xs text-gray-500 mt-0.5">{opt.hint}</div>
                </button>
              );
            })}
          </div>
        </div>
      )}

      {uploading && (
        <div className="space-y-3">
          {stage === 'uploading' && (
            <>
              <div className="flex items-center justify-between text-xs text-gray-600">
                <span>{t('mri.upload.uploadingFile')}</span>
                <span>{progress}%</span>
              </div>
              <div className="w-full h-2 bg-gray-200 rounded">
                <div className="h-2 bg-primary rounded transition-all" style={{ width: `${progress}%` }} />
              </div>
            </>
          )}
          {stage === 'inferring' && (
            <div className="text-sm text-gray-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-3">
              <div className="font-medium flex items-center gap-2 text-amber-900">
                <Loader2 size={16} className="animate-spin" />
                {runningLabel}
              </div>
              <p className="text-xs text-amber-800 mt-1">
                {t('mri.upload.runningHint')}
              </p>
            </div>
          )}
        </div>
      )}

      <div className="flex justify-end gap-2">
        <button
          type="button"
          onClick={onComplete ? () => onComplete(null) : reset}
          disabled={uploading}
          className="px-4 py-2 rounded-lg text-sm text-gray-700 hover:bg-gray-100 disabled:opacity-50"
        >
          {t('common.cancel')}
        </button>
        <button
          type="button"
          onClick={onSubmit}
          disabled={!file || uploading}
          className="inline-flex items-center gap-2 bg-primary text-ink px-4 py-2 rounded-lg text-sm font-medium hover:opacity-90 disabled:opacity-50"
        >
          {uploading && <Loader2 size={16} className="animate-spin" />}
          {uploading ? t('mri.upload.analyzing') : t('mri.upload.analyze')}
        </button>
      </div>
    </div>
  );
}
