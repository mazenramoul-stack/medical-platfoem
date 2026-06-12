import { Download } from 'lucide-react';

import { useI18n } from '../../i18n/LanguageContext.jsx';

export default function ReportViewer({ report, onDownload }) {
  const { t } = useI18n();
  if (!report?.pdf_url) {
    return <p className="text-sm text-gray-500">{t('reports.viewer.unavailable')}</p>;
  }
  return (
    <div className="space-y-3">
      <div className="border border-gray-200 rounded-lg overflow-hidden bg-gray-100">
        <iframe
          title={t('reports.reportNumber', { id: report.id })}
          src={report.pdf_url}
          className="w-full h-[60vh] bg-white"
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
