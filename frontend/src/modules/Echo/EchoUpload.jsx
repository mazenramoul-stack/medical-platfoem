import { useCallback, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { FileVideo, Loader2, Upload, X } from 'lucide-react';
import toast from 'react-hot-toast';

import echoService from '../../services/echoService.js';
import { useFileDropzone } from '../../hooks/useFileDropzone.js';
import { formatBytes } from '../../utils/formatters.js';
import { useI18n } from '../../i18n/LanguageContext.jsx';

const ACCEPT = {
  'video/x-msvideo': ['.avi'],
  'video/mp4': ['.mp4'],
  'video/quicktime': ['.mov'],
  'video/webm': ['.webm'],
  'video/x-matroska': ['.mkv'],
};

export default function EchoUpload({ patient, onComplete }) {
  const navigate = useNavigate();
  const { t } = useI18n();
  const [file, setFile] = useState(null);
  const [progress, setProgress] = useState(0);
  const [uploading, setUploading] = useState(false);
  const [stage, setStage] = useState('idle');

  const onDrop = useCallback((accepted) => {
    if (accepted[0]) setFile(accepted[0]);
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useFileDropzone({ accept: ACCEPT, onDrop });
  const reset = () => { setFile(null); setProgress(0); setStage('idle'); };

  const onSubmit = async () => {
    if (!file || !patient) return;
    setUploading(true); setStage('uploading'); setProgress(0);
    try {
      const analysis = await echoService.upload(patient.id, file, (p) => {
        setProgress(p);
        if (p >= 100) setStage('inferring');
      });
      toast.success(t('echo.upload.complete'));
      if (onComplete) onComplete(analysis);
      navigate(`/echo/${analysis.id}`);
    } catch (e) {
      toast.error(e.response?.data?.detail || e.message || t('echo.upload.failed'));
      setUploading(false); setStage('idle');
    }
  };

  return (
    <div className="space-y-4">
      {patient && (
        <div className="text-sm bg-blue-50 border border-edge text-gray-700 rounded-md px-3 py-2">
          {t('echo.upload.forPatient')} <strong>{patient.full_name}</strong> (#{patient.id})
        </div>
      )}

      {!file && (
        <div
          {...getRootProps()}
          className={'border-2 border-dashed rounded-xl px-6 py-10 text-center cursor-pointer transition '
            + (isDragActive ? 'border-primary bg-blue-50' : 'border-gray-300 hover:border-primary hover:bg-blue-50/50')}
        >
          <input {...getInputProps()} />
          <div className="inline-flex items-center justify-center w-12 h-12 rounded-full bg-blue-50 text-primary mb-3">
            <Upload size={22} />
          </div>
          <p className="text-sm font-medium text-gray-900">
            {isDragActive ? t('echo.upload.dropHere') : t('echo.upload.dragOrBrowse')}
          </p>
          <p className="text-xs text-gray-500 mt-1">{t('echo.upload.supported')}</p>
        </div>
      )}

      {file && (
        <div className="border border-gray-200 rounded-xl p-4 flex items-center gap-4">
          <div className="w-16 h-16 rounded bg-gray-100 flex items-center justify-center text-gray-500">
            <FileVideo size={24} />
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-sm font-medium text-gray-900 truncate">{file.name}</div>
            <div className="text-xs text-gray-500">{formatBytes(file.size)}</div>
          </div>
          {!uploading && (
            <button type="button" onClick={reset} className="text-gray-400 hover:text-gray-600 p-1" aria-label={t('echo.upload.remove')}>
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
                <span>{t('echo.upload.uploadingVideo')}</span><span>{progress}%</span>
              </div>
              <div className="w-full h-2 bg-gray-200 rounded">
                <div className="h-2 bg-primary rounded transition-all" style={{ width: `${progress}%` }} />
              </div>
            </>
          )}
          {stage === 'inferring' && (
            <div className="text-sm bg-amber-50 border border-edge rounded-lg px-3 py-3">
              <div className="font-medium flex items-center gap-2 text-amber-700">
                <Loader2 size={16} className="animate-spin" />
                {t('echo.upload.running')}
              </div>
              <p className="text-xs text-gray-500 mt-1">{t('echo.upload.cpuNote')}</p>
            </div>
          )}
        </div>
      )}

      <div className="flex justify-end gap-2">
        <button type="button" onClick={onComplete ? () => onComplete(null) : reset} disabled={uploading}
                className="px-4 py-2 rounded-lg text-sm text-gray-600 hover:bg-gray-100 disabled:opacity-50">
          {t('common.cancel')}
        </button>
        <button type="button" onClick={onSubmit} disabled={!file || uploading}
                className="inline-flex items-center gap-2 text-ink px-4 py-2 rounded-lg text-sm font-semibold disabled:opacity-50"
                style={{ background: 'linear-gradient(135deg, var(--amber), var(--cardio))' }}>
          {uploading && <Loader2 size={16} className="animate-spin" />}
          {uploading ? t('echo.upload.analyzing') : t('echo.upload.analyze')}
        </button>
      </div>
    </div>
  );
}
