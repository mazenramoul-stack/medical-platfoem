import { useMemo, useRef, useState } from 'react';
import {
  Activity, Brain, Download, FileDown, Heart, HeartPulse, Loader2, Upload, Waves, X,
} from 'lucide-react';
import toast from 'react-hot-toast';

import conversionService, { downloadBlob } from '../../services/conversionService.js';
import { useI18n } from '../../i18n/LanguageContext.jsx';
import { useTokens } from '../../theme/ThemeContext.jsx';
import { formatBytes } from '../../utils/formatters.js';

// One descriptor per modality: the icon, theme accent, accepted upload formats,
// and any optional conversion params the technician can set.
const MODALITIES = [
  { key: 'mri', icon: Brain, accent: 'neuro', accept: '.dcm,.zip,.nii,.nii.gz',
    params: [{ name: 'slice_index', type: 'number', labelKey: 'sliceIndex', hintKey: 'sliceIndexHint', min: 0 }] },
  { key: 'ecg', icon: Heart, accent: 'cardio', accept: '.dcm,.pdf', params: [] },
  { key: 'echo', icon: HeartPulse, accent: 'amber', accept: '.dcm,.mov,.mkv,.avi,.webm,.mp4',
    params: [{ name: 'fps', type: 'number', labelKey: 'fps', hintKey: 'fpsHint', min: 1 }] },
  { key: 'eeg', icon: Waves, accent: 'violet', accept: '.zip,.bdf,.set,.vhdr', params: [] },
];

// Lightweight inline ECG trace preview (no chart lib): map the downsampled
// signal to an SVG polyline, normalized to its own min/max.
function TraceSparkline({ points, color }) {
  if (!points || points.length < 2) return null;
  const w = 600;
  const h = 120;
  const pad = 4;
  let min = Infinity;
  let max = -Infinity;
  for (const v of points) {
    if (v < min) min = v;
    if (v > max) max = v;
  }
  const range = max - min || 1;
  const n = points.length;
  const coords = points
    .map((v, i) => {
      const x = pad + (i / (n - 1)) * (w - 2 * pad);
      const y = pad + (1 - (v - min) / range) * (h - 2 * pad);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(' ');
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="w-full" style={{ height: 120 }} preserveAspectRatio="none">
      <polyline points={coords} fill="none" stroke={color} strokeWidth="1.2" />
    </svg>
  );
}

// Parse the JSON error envelope out of an axios blob-response failure.
async function extractError(err, t) {
  const data = err?.response?.data;
  if (data && typeof data.text === 'function') {
    try {
      return JSON.parse(await data.text()).error || t('convert.errors.generic');
    } catch {
      return t('convert.errors.generic');
    }
  }
  return data?.error || err?.message || t('convert.errors.generic');
}

export default function ConvertPage() {
  const { t } = useI18n();
  const { colors } = useTokens();
  const [active, setActive] = useState('mri');
  const [file, setFile] = useState(null);
  const [params, setParams] = useState({});
  const [loading, setLoading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [result, setResult] = useState(null);
  const inputRef = useRef(null);

  const modality = useMemo(() => MODALITIES.find((m) => m.key === active), [active]);
  const accentHex = colors[modality.accent];

  // A smartwatch ECG (single-lead PDF) is analyzed inline instead of downloaded.
  const isSmartwatchEcg = active === 'ecg' && !!file && file.name.toLowerCase().endsWith('.pdf');

  const pickFile = (f) => {
    setFile(f);
    setResult(null);
  };

  const switchTo = (key) => {
    if (key === active) return;
    setActive(key);
    setFile(null);
    setParams({});
    setResult(null);
  };

  const onDrop = (e) => {
    e.preventDefault();
    setDragOver(false);
    const dropped = e.dataTransfer?.files?.[0];
    if (dropped) pickFile(dropped);
  };

  const onConvert = async () => {
    if (!file) {
      toast.error(t('convert.errors.noFile'));
      return;
    }
    setLoading(true);
    setResult(null);
    try {
      if (isSmartwatchEcg) {
        const data = await conversionService.convertEcgPdf(file);
        setResult(data);
        toast.success(t('convert.analyzed'));
      } else {
        const { blob, filename } = await conversionService.convert(active, file, params);
        downloadBlob(blob, filename);
        toast.success(t('convert.success', { name: filename }));
      }
    } catch (err) {
      toast.error(await extractError(err, t));
    } finally {
      setLoading(false);
    }
  };

  const downloadResultCsv = () => {
    if (!result?.csv_text) return;
    downloadBlob(new Blob([result.csv_text], { type: 'text/csv' }), result.csv_filename || 'leadI.csv');
  };

  const tval = (v) => {
    const known = ['Normal', 'Bradycardia', 'Tachycardia', 'Regular', 'Irregular', 'Undetermined'];
    if (v && known.includes(v)) return t(`convert.result.values.${v}`);
    return v || t('convert.result.na');
  };

  return (
    <div className="max-w-3xl mx-auto space-y-5">
      <div>
        <div className="flex items-center gap-3">
          <h1 className="text-xl font-mono font-bold text-hi">{t('convert.title')}</h1>
          <span
            className="text-[10px] uppercase tracking-[0.2em] px-2 py-0.5 rounded-full"
            style={{ background: `${accentHex}1f`, color: accentHex, border: `1px solid ${accentHex}55` }}
          >
            {t('convert.technicianBadge')}
          </span>
        </div>
        <p className="text-sm text-mid mt-1">{t('convert.subtitle')}</p>
      </div>

      {/* Modality tabs */}
      <div className="flex flex-wrap gap-2">
        {MODALITIES.map((m) => {
          const Icon = m.icon;
          const isActive = m.key === active;
          const hex = colors[m.accent];
          return (
            <button
              key={m.key}
              type="button"
              onClick={() => switchTo(m.key)}
              className="inline-flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium border transition"
              style={{
                color: isActive ? colors.textHi : colors.textMid,
                background: isActive ? `${hex}18` : 'transparent',
                borderColor: isActive ? hex : 'var(--edge)',
              }}
            >
              <Icon size={16} style={{ color: isActive ? hex : colors.textLow }} />
              {t(`convert.tabs.${m.key}`)}
            </button>
          );
        })}
      </div>

      {/* Active modality card */}
      <div className="holo-panel p-5 space-y-4">
        <div>
          <div className="text-sm font-semibold text-hi">{t(`convert.modalities.${active}.name`)}</div>
          <p className="text-xs text-mid mt-1">{t(`convert.modalities.${active}.desc`)}</p>
        </div>

        {/* Dropzone / file picker */}
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
          onDragLeave={() => setDragOver(false)}
          onDrop={onDrop}
          className="w-full border-2 border-dashed rounded-xl px-6 py-8 text-center transition"
          style={{ borderColor: dragOver ? accentHex : 'var(--edge)', background: dragOver ? `${accentHex}10` : 'transparent' }}
        >
          <div
            className="inline-flex items-center justify-center w-11 h-11 rounded-full mb-2"
            style={{ background: `${accentHex}1f`, color: accentHex }}
          >
            <Upload size={20} />
          </div>
          <p className="text-sm font-medium text-hi">
            {dragOver ? t('convert.dropActive') : t('convert.dropPrompt')}
          </p>
          <p className="text-xs text-low mt-1">{t('convert.formatsLabel', { formats: modality.accept })}</p>
          <input
            ref={inputRef}
            type="file"
            accept={modality.accept}
            className="hidden"
            onChange={(e) => pickFile(e.target.files?.[0] || null)}
          />
        </button>

        {file && (
          <div className="flex items-center gap-3 rounded-lg border border-edge bg-paneldeep px-3 py-2">
            <FileDown size={18} style={{ color: accentHex }} />
            <div className="flex-1 min-w-0">
              <div className="text-sm font-medium text-hi truncate">{file.name}</div>
              <div className="text-xs text-low">{formatBytes(file.size)}</div>
            </div>
            {!loading && (
              <button
                type="button"
                onClick={() => setFile(null)}
                className="text-low hover:text-hi p-1"
                aria-label={t('convert.remove')}
              >
                <X size={16} />
              </button>
            )}
          </div>
        )}

        {/* Optional per-modality params */}
        {modality.params.length > 0 && (
          <div className="grid gap-3 sm:grid-cols-2">
            {modality.params.map((p) => (
              <div key={p.name}>
                <label htmlFor={`param-${p.name}`} className="block text-xs font-medium text-mid mb-1">
                  {t(`convert.params.${p.labelKey}`)}
                </label>
                <input
                  id={`param-${p.name}`}
                  type={p.type}
                  min={p.min}
                  value={params[p.name] ?? ''}
                  onChange={(e) => setParams((prev) => ({ ...prev, [p.name]: e.target.value }))}
                  className="w-full px-3 py-2 rounded-lg text-sm bg-paneldeep text-hi border border-edge focus:outline-none focus:ring-2 focus:ring-neuro/70"
                />
                <p className="text-[11px] text-low mt-1">{t(`convert.params.${p.hintKey}`)}</p>
              </div>
            ))}
          </div>
        )}

        <div className="flex justify-end">
          <button
            type="button"
            onClick={onConvert}
            disabled={!file || loading}
            className="inline-flex items-center gap-2 text-ink px-4 py-2 rounded-lg text-sm font-semibold transition disabled:opacity-50"
            style={{ background: `linear-gradient(135deg, ${accentHex}, var(--violet))`, boxShadow: '0 0 18px var(--glow-soft)' }}
          >
            {loading
              ? <Loader2 size={16} className="animate-spin" />
              : (isSmartwatchEcg ? <Activity size={16} /> : <FileDown size={16} />)}
            {loading
              ? t('convert.converting')
              : (isSmartwatchEcg ? t('convert.analyze') : t('convert.convert'))}
          </button>
        </div>
      </div>

      {/* Single-lead smartwatch ECG result */}
      {result && (
        <div className="holo-panel p-5 space-y-4">
          <div className="flex items-center justify-between gap-3">
            <div className="text-sm font-semibold text-hi">{t('convert.result.title')}</div>
            <button
              type="button"
              onClick={downloadResultCsv}
              className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium border border-edge text-mid hover:text-hi transition"
            >
              <Download size={14} style={{ color: accentHex }} />
              {t('convert.result.downloadCsv')}
            </button>
          </div>
          <p className="text-xs text-mid">{t('convert.result.note')}</p>

          <div className="grid gap-3 sm:grid-cols-3">
            <div className="rounded-lg border border-edge bg-paneldeep px-4 py-3">
              <div className="text-[11px] uppercase tracking-wide text-low">{t('convert.result.heartRate')}</div>
              <div className="mt-1 flex items-baseline gap-1.5">
                <Heart size={16} style={{ color: accentHex }} />
                <span className="text-2xl font-mono font-bold text-hi">
                  {result.screening?.mean_hr_bpm ?? t('convert.result.na')}
                </span>
                <span className="text-xs text-low">{t('convert.result.bpm')}</span>
              </div>
              <div className="text-xs text-mid mt-0.5">{tval(result.screening?.hr_classification)}</div>
            </div>

            <div className="rounded-lg border border-edge bg-paneldeep px-4 py-3">
              <div className="text-[11px] uppercase tracking-wide text-low">{t('convert.result.rhythm')}</div>
              <div className="mt-1 text-lg font-semibold text-hi">{tval(result.screening?.rhythm)}</div>
              <div className="text-xs text-mid mt-0.5">
                {result.screening?.n_beats ?? 0} {t('convert.result.beats')}
              </div>
            </div>

            <div className="rounded-lg border border-edge bg-paneldeep px-4 py-3">
              <div className="text-[11px] uppercase tracking-wide text-low">{t('convert.result.hrv')}</div>
              <div className="mt-1 text-sm text-hi">
                {t('convert.result.rmssd')}: {result.screening?.hrv_rmssd_ms ?? t('convert.result.na')} ms
              </div>
              <div className="text-sm text-hi">
                {t('convert.result.sdnn')}: {result.screening?.hrv_sdnn_ms ?? t('convert.result.na')} ms
              </div>
            </div>
          </div>

          <div>
            <div className="text-xs text-low mb-1">{t('convert.result.tracePreview')}</div>
            <div className="rounded-lg border border-edge bg-paneldeep p-2">
              <TraceSparkline points={result.signal_preview} color={accentHex} />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
