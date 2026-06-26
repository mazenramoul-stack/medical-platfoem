import { useCallback, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { FileText, Loader2, Upload, X } from 'lucide-react';
import toast from 'react-hot-toast';

import ecgService from '../../services/ecgService.js';
import { useFileDropzone } from '../../hooks/useFileDropzone.js';
import { ECG_ALLOWED_EXTENSIONS, ECG_MAX_BYTES } from '../../utils/constants.js';
import { formatBytes } from '../../utils/formatters.js';
import { useI18n } from '../../i18n/LanguageContext.jsx';

const ACCEPT = {
  'text/csv':                  ['.csv'],
  'application/octet-stream':  ['.edf', '.dat', '.hea'],
  // Smartwatch ECG export (single lead) → single-lead rate/rhythm screening.
  'application/pdf':           ['.pdf'],
};

export default function ECGUpload({ patient, onComplete }) {
  const navigate = useNavigate();
  const { t } = useI18n();
  const [file, setFile] = useState(null);
  const [progress, setProgress] = useState(0);
  const [uploading, setUploading] = useState(false);
  const [stage, setStage] = useState('idle');

  const onDrop = useCallback((accepted) => {
    const f = accepted[0];
    if (f) setFile(f);
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useFileDropzone({
    accept: ACCEPT, maxSize: ECG_MAX_BYTES, onDrop,
  });

  const reset = () => { setFile(null); setProgress(0); setStage('idle'); };

  const onSubmit = async () => {
    if (!file || !patient) return;
    setUploading(true);
    setStage('uploading');
    try {
      const analysis = await ecgService.upload(patient.id, file, (p) => {
        setProgress(p);
        if (p >= 100) setStage('inferring');
      });
      toast.success(t('ecg.upload.complete'));
      if (onComplete) onComplete(analysis);
      navigate(`/ecg/${analysis.id}`);
    } catch (e) {
      toast.error(e.response?.data?.detail || e.message || t('ecg.upload.failed'));
      setUploading(false);
      setStage('idle');
    }
  };

  return (
    <div className="space-y-4">
      {patient && (
        <div className="text-sm bg-red-50 border border-red-200 text-red-900 rounded-md px-3 py-2">
          {t('ecg.upload.forPatient')} <strong>{patient.full_name}</strong> (#{patient.id})
        </div>
      )}

      {!file && (
        <div
          {...getRootProps()}
          className={
            'border-2 border-dashed rounded-xl px-6 py-10 text-center cursor-pointer transition '
            + (isDragActive ? 'border-danger bg-red-50' : 'border-gray-300 hover:border-danger hover:bg-red-50/50')
          }
        >
          <input {...getInputProps()} />
          <div className="inline-flex items-center justify-center w-12 h-12 rounded-full bg-red-50 text-danger mb-3">
            <Upload size={22} />
          </div>
          <p className="text-sm font-medium text-gray-900">
            {isDragActive ? t('ecg.upload.dropHere') : t('ecg.upload.dragOrBrowse')}
          </p>
          <p className="text-xs text-gray-500 mt-1">
            {t('ecg.upload.formats', { formats: ECG_ALLOWED_EXTENSIONS.join(', ') })}
          </p>
          <p className="text-xs text-gray-500 mt-3 max-w-sm mx-auto">
            {t('ecg.upload.formatHint')}
          </p>
          <p className="text-xs text-gray-500 mt-1">{t('ecg.upload.maxSize')}</p>
        </div>
      )}

      {file && (
        <div className="border border-gray-200 rounded-xl p-4 flex items-center gap-4">
          <div className="w-16 h-16 rounded bg-gray-100 flex items-center justify-center text-gray-500">
            <FileText size={24} />
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-sm font-medium text-gray-900 truncate">{file.name}</div>
            <div className="text-xs text-gray-500">{formatBytes(file.size)}</div>
          </div>
          {!uploading && (
            <button type="button" onClick={reset} className="text-gray-400 hover:text-gray-600 p-1" aria-label={t('ecg.upload.remove')}>
              <X size={18} />
            </button>
          )}
        </div>
      )}

      {uploading && (
        <div className="space-y-3">
          {stage === 'uploading' && (
            <>
              <div className="flex items-center justify-between text-xs text-gray-600">
                <span>{t('ecg.upload.uploadingFile')}</span>
                <span>{progress}%</span>
              </div>
              <div className="w-full h-2 bg-gray-200 rounded">
                <div className="h-2 bg-danger rounded transition-all" style={{ width: `${progress}%` }} />
              </div>
            </>
          )}
          {stage === 'inferring' && (
            <div className="text-sm bg-amber-50 border border-amber-200 rounded-lg px-3 py-3">
              <div className="font-medium flex items-center gap-2 text-amber-900">
                <Loader2 size={16} className="animate-spin" />
                {t('ecg.upload.running')}
              </div>
              <p className="text-xs text-amber-800 mt-1">
                {t('ecg.upload.runningHint')}
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
          className="inline-flex items-center gap-2 bg-danger text-ink px-4 py-2 rounded-lg text-sm font-medium hover:opacity-90 disabled:opacity-50"
        >
          {uploading && <Loader2 size={16} className="animate-spin" />}
          {uploading ? t('ecg.upload.analyzing') : t('ecg.upload.analyze')}
        </button>
      </div>
    </div>
  );
}
