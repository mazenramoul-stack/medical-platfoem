import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { FileText, Loader2 } from 'lucide-react';
import toast from 'react-hot-toast';

import reportService from '../../services/reportService.js';
import { formatDateShort } from '../../utils/formatters.js';
import { useI18n } from '../../i18n/LanguageContext.jsx';

export default function ReportGenerator({ patient, mriOptions = [], ecgOptions = [], echoOptions = [], eegOptions = [], onComplete }) {
  const navigate = useNavigate();
  const { t } = useI18n();
  const [mriId, setMriId] = useState(mriOptions[0]?.id ?? '');
  const [ecgId, setEcgId] = useState(ecgOptions[0]?.id ?? '');
  const [echoId, setEchoId] = useState(echoOptions[0]?.id ?? '');
  const [eegId, setEegId] = useState(eegOptions[0]?.id ?? '');
  const [generating, setGenerating] = useState(false);

  const canSubmit = (mriId || ecgId || echoId || eegId) && !generating;

  const optionLabels = {
    mri: (m) => t('reports.generator.mriOption', {
      id: m.id, result: m.result_tumor_type || '—', date: formatDateShort(m.created_at),
    }),
    ecg: (e) => t('reports.generator.ecgOption', {
      id: e.id, result: e.result_arrhythmia_type || '—', date: formatDateShort(e.created_at),
    }),
    echo: (e) => t('reports.generator.echoOption', {
      id: e.id, ef: typeof e.result_ef === 'number' ? `${e.result_ef.toFixed(1)}%` : '—', date: formatDateShort(e.created_at),
    }),
    eeg: (e) => t('reports.generator.eegOption', {
      id: e.id,
      result: `${e.result_dominant_pattern || '—'}${e.result_harmful ? ` · ${t('reports.generator.harmful')}` : ''}`,
      date: formatDateShort(e.created_at),
    }),
  };

  const sections = [
    { key: 'mri', value: mriId, set: setMriId, options: mriOptions },
    { key: 'ecg', value: ecgId, set: setEcgId, options: ecgOptions },
    { key: 'echo', value: echoId, set: setEchoId, options: echoOptions },
    { key: 'eeg', value: eegId, set: setEegId, options: eegOptions },
  ];

  const onGenerate = async () => {
    if (!canSubmit) return;
    setGenerating(true);
    try {
      const r = await reportService.generate({
        patientId: patient.id,
        mriId: mriId || undefined,
        ecgId: ecgId || undefined,
        echoId: echoId || undefined,
        eegId: eegId || undefined,
      });
      toast.success(t('reports.generator.success'));
      // Auto-download
      try {
        const blob = await reportService.downloadPdf(r.id);
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url; a.download = `medical_report_${patient.id}_${r.id}.pdf`;
        document.body.appendChild(a); a.click(); document.body.removeChild(a);
        setTimeout(() => URL.revokeObjectURL(url), 1000);
      } catch { /* user can re-download from list */ }
      if (onComplete) onComplete(r);
      else navigate(`/patients/${patient.id}`);
    } catch (e) {
      toast.error(e.response?.data?.detail || t('reports.generator.failed'));
    } finally {
      setGenerating(false);
    }
  };

  if (!patient) return null;

  return (
    <div className="space-y-4">
      <div className="text-sm bg-green-50 border border-edge text-green-700 rounded-md px-3 py-2">
        {t('reports.generator.forPatient')} <strong>{patient.full_name}</strong> (#{patient.id})
      </div>

      {sections.map(({ key, value, set, options }) => (
        <div key={key}>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            {t('reports.generator.analysisLabel', { modality: t(`reports.modality.${key}`) })}
          </label>
          <select
            value={value} onChange={(e) => set(e.target.value ? Number(e.target.value) : '')}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-primary"
          >
            <option value="">{t('reports.generator.none')}</option>
            {options.map((o) => <option key={o.id} value={o.id}>{optionLabels[key](o)}</option>)}
          </select>
          {options.length === 0 && (
            <p className="text-xs text-gray-500 mt-1">
              {t('reports.generator.noneAvailable', { modality: t(`reports.modality.${key}`) })}
            </p>
          )}
        </div>
      ))}

      {!mriId && !ecgId && !echoId && !eegId && (
        <p className="text-xs text-danger">{t('reports.generator.selectOne')}</p>
      )}

      <div className="flex justify-end gap-2 pt-2">
        <button
          type="button"
          onClick={() => onComplete && onComplete(null)}
          disabled={generating}
          className="px-4 py-2 rounded-lg text-sm text-gray-700 hover:bg-gray-100 disabled:opacity-50"
        >
          {t('common.cancel')}
        </button>
        <button
          type="button"
          onClick={onGenerate}
          disabled={!canSubmit}
          className="inline-flex items-center gap-2 bg-success text-ink px-4 py-2 rounded-lg text-sm font-medium hover:opacity-90 disabled:opacity-50"
        >
          {generating ? <Loader2 size={16} className="animate-spin" /> : <FileText size={16} />}
          {generating ? t('reports.generator.generating') : t('reports.generator.generate')}
        </button>
      </div>
    </div>
  );
}
