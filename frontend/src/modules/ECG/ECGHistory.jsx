import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Heart, Trash2 } from 'lucide-react';

import Badge from '../../components/UI/Badge.jsx';
import ConfirmDialog from '../../components/UI/ConfirmDialog.jsx';
import EmptyState from '../../components/UI/EmptyState.jsx';
import { formatRelative } from '../../utils/formatters.js';
import { useI18n } from '../../i18n/LanguageContext.jsx';

const STATUS_VARIANT = { completed: 'success', processing: 'warning', pending: 'gray', failed: 'danger' };

export default function ECGHistory({ items = [], onDelete }) {
  const { t } = useI18n();
  const [pending, setPending] = useState(null);

  if (items.length === 0) {
    return (
      <EmptyState
        icon={Heart}
        title={t('ecg.history.emptyTitle')}
        description={t('ecg.history.emptyDescription')}
      />
    );
  }

  return (
    <>
      <div className="divide-y divide-gray-100">
        {items.map((e) => (
          <div key={e.id} className="flex items-center gap-3 py-3">
            <Link
              to={`/ecg/${e.id}`}
              className="w-12 h-12 rounded-lg bg-red-50 text-danger flex items-center justify-center shrink-0 hover:opacity-90"
            >
              <Heart size={22} />
            </Link>
            <Link to={`/ecg/${e.id}`} className="flex-1 min-w-0 group">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="font-medium text-gray-900 group-hover:text-primary">ECG #{e.id}</span>
                <Badge variant={STATUS_VARIANT[e.status] || 'gray'}>
                  {STATUS_VARIANT[e.status] ? t(`ecg.status.${e.status}`) : e.status}
                </Badge>
                {e.result_arrhythmia_type && (
                  <Badge variant={e.result_arrhythmia_detected ? 'danger' : 'success'}>
                    {e.result_arrhythmia_type}
                  </Badge>
                )}
              </div>
              <div className="text-xs text-gray-500 mt-1">{formatRelative(e.created_at)}</div>
            </Link>
            {onDelete && (
              <button
                type="button"
                onClick={() => setPending(e)}
                className="p-2 rounded text-gray-400 hover:text-danger hover:bg-red-50"
                aria-label={t('common.delete')}
              >
                <Trash2 size={16} />
              </button>
            )}
          </div>
        ))}
      </div>
      <ConfirmDialog
        open={!!pending}
        onClose={() => setPending(null)}
        onConfirm={() => { const id = pending?.id; setPending(null); if (id && onDelete) onDelete(id); }}
        title={t('ecg.history.deleteTitle')}
        description={pending ? t('ecg.history.deleteDescription', { id: pending.id }) : ''}
        confirmLabel={t('common.delete')}
      />
    </>
  );
}
