import { useEffect, useState } from 'react';
import { Download, Loader2 } from 'lucide-react';

import reportService from '../../services/reportService.js';
import { useI18n } from '../../i18n/LanguageContext.jsx';

export default function ReportViewer({ report, onDownload }) {
  const { t } = useI18n();
  const [blobUrl, setBlobUrl] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!report?.id) return undefined;
    let alive = true;
    setLoading(true);
    setError(null);

    (async () => {
      try {
        const blob = await reportService.downloadPdf(report.id);
        if (!alive) return;
        const url = URL.createObjectURL(blob);
        setBlobUrl(url);
      } catch {
        if (alive) setError(t('reports.viewer.loadFailed'));
      } finally {
        if (alive) setLoading(false);
      }
    })();

    return () => {
      alive = false;
      setBlobUrl((prev) => { if (prev) URL.revokeObjectURL(prev); return null; });
    };
  }, [report?.id]);

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-16 gap-3">
        <Loader2 size={28} className="animate-spin text-primary" />
        <span className="text-sm text-mid">{t('reports.viewer.loading')}</span>
      </div>
    );
  }

  if (error || !blobUrl) {
    return (
      <div className="space-y-3 text-center py-8">
        <p className="text-sm text-danger">{error || t('reports.viewer.unavailable')}</p>
        <button
          type="button"
          onClick={onDownload}
          className="inline-flex items-center gap-2 bg-primary text-ink px-4 py-2 rounded-lg text-sm hover:opacity-90"
        >
          <Download size={16} /> {t('reports.viewer.downloadInstead')}
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="border border-edge rounded-lg overflow-hidden bg-paneldeep">
        <iframe
          title={t('reports.reportNumber', { id: report.id })}
          src={blobUrl}
          className="w-full h-[70vh]"
        />
      </div>
      <div className="flex justify-end">
        <button
          type="button"
          onClick={onDownload}
          className="inline-flex items-center gap-2 bg-primary text-ink px-4 py-2 rounded-lg text-sm hover:opacity-90"
        >
          <Download size={16} /> {t('reports.viewer.downloadPdf')}
        </button>
      </div>
    </div>
  );
}
