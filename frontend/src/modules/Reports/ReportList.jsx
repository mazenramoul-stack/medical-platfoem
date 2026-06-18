import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { Activity, Brain, Download, Eye, FileText, Heart, HeartPulse, Trash2 } from 'lucide-react';
import toast from 'react-hot-toast';

import Badge from '../../components/UI/Badge.jsx';
import ConfirmDialog from '../../components/UI/ConfirmDialog.jsx';
import EmptyState from '../../components/UI/EmptyState.jsx';
import Modal from '../../components/UI/Modal.jsx';
import ReportViewer from './ReportViewer.jsx';

import reportService from '../../services/reportService.js';
import { useAuth } from '../../hooks/useAuth.js';
import { useI18n } from '../../i18n/LanguageContext.jsx';
import { formatDate } from '../../utils/formatters.js';

export default function ReportList({ items: itemsProp, onDelete: onDeleteProp }) {
  const params = useParams();
  const patientIdFromUrl = params.patientId;
  const { user } = useAuth();
  const { t } = useI18n();

  const [items, setItems] = useState(itemsProp ?? null);
  const [loading, setLoading] = useState(itemsProp == null);
  const [pendingDelete, setPendingDelete] = useState(null);
  const [viewer, setViewer] = useState(null);

  useEffect(() => {
    if (itemsProp != null) { setItems(itemsProp); setLoading(false); return; }
    let alive = true;
    (async () => {
      try {
        const data = patientIdFromUrl
          ? await reportService.getByPatient(patientIdFromUrl)
          : await reportService.getAll();
        if (alive) setItems(data);
      } catch (e) {
        toast.error(e.response?.data?.detail || t('reports.list.loadFailed'));
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => { alive = false; };
  }, [itemsProp, patientIdFromUrl]);

  const onDelete = async (id) => {
    if (onDeleteProp) {
      await onDeleteProp(id);
      return;
    }
    try {
      await reportService.delete(id);
      toast.success(t('reports.list.deleted'));
      setItems((cur) => (cur || []).filter((r) => r.id !== id));
    } catch (e) {
      toast.error(e.response?.data?.detail || t('reports.list.deleteFailed'));
    }
  };

  const onDownload = async (report) => {
    try {
      const blob = await reportService.downloadPdf(report.id);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `medical_report_${report.patient}_${report.id}.pdf`;
      document.body.appendChild(a); a.click(); document.body.removeChild(a);
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) {
      toast.error(e.response?.data?.detail || t('reports.list.downloadFailed'));
    }
  };

  if (loading) return <div className="py-8 text-center text-sm text-gray-500">{t('reports.list.loading')}</div>;
  if (!items || items.length === 0) {
    return (
      <EmptyState
        icon={FileText}
        title={t('reports.list.emptyTitle')}
        description={t('reports.list.emptyDescription')}
      />
    );
  }

  return (
    <>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {items.map((r) => (
          <div key={r.id} className="border border-gray-200 rounded-xl p-4">
            <div className="flex items-start justify-between gap-3 mb-3">
              <div>
                <div className="text-sm font-medium text-gray-900">{t('reports.reportNumber', { id: r.id })}</div>
                <div className="text-xs text-gray-500 mt-0.5">{formatDate(r.created_at)}</div>
              </div>
              <div className="flex items-center gap-1 flex-wrap">
                {r.mri_analysis && (
                  <Badge variant="primary"><Brain size={10} className="mr-0.5 inline" />MRI</Badge>
                )}
                {r.ecg_analysis && (
                  <Badge variant="danger"><Heart size={10} className="mr-0.5 inline" />ECG</Badge>
                )}
                {r.echo_analysis && (
                  <Badge variant="warning"><HeartPulse size={10} className="mr-0.5 inline" />Echo</Badge>
                )}
                {r.eeg_analysis && (
                  <Badge variant="secondary"><Activity size={10} className="mr-0.5 inline" />EEG</Badge>
                )}
              </div>
            </div>
            <div className="text-xs text-gray-600 mb-3">
              {t('reports.list.generatedBy', { name: user?.full_name || '—' })}
            </div>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => setViewer(r)}
                className="inline-flex items-center gap-1 bg-white text-gray-700 border border-gray-300 px-3 py-1.5 rounded text-xs hover:bg-gray-50"
              >
                <Eye size={14} /> {t('common.view')}
              </button>
              <button
                type="button"
                onClick={() => onDownload(r)}
                className="inline-flex items-center gap-1 bg-primary text-ink px-3 py-1.5 rounded text-xs hover:opacity-90"
              >
                <Download size={14} /> {t('common.download')}
              </button>
              <button
                type="button"
                onClick={() => setPendingDelete(r)}
                className="ml-auto inline-flex items-center gap-1 text-danger px-2 py-1.5 rounded text-xs hover:bg-red-50"
              >
                <Trash2 size={14} />
              </button>
            </div>
          </div>
        ))}
      </div>

      <Modal open={!!viewer} onClose={() => setViewer(null)} title={viewer ? t('reports.reportNumber', { id: viewer.id }) : ''} size="xl">
        {viewer && <ReportViewer report={viewer} onDownload={() => onDownload(viewer)} />}
      </Modal>

      <ConfirmDialog
        open={!!pendingDelete}
        onClose={() => setPendingDelete(null)}
        onConfirm={() => { const id = pendingDelete?.id; setPendingDelete(null); if (id) onDelete(id); }}
        title={t('reports.list.deleteTitle')}
        description={pendingDelete ? t('reports.list.deleteDescription', { id: pendingDelete.id }) : ''}
        confirmLabel={t('common.delete')}
      />
    </>
  );
}
