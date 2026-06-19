import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Brain, Trash2 } from 'lucide-react';

import Badge from '../../components/UI/Badge.jsx';
import ConfirmDialog from '../../components/UI/ConfirmDialog.jsx';
import EmptyState from '../../components/UI/EmptyState.jsx';
import TumorBadge from './TumorBadge.jsx';
import { formatRelative } from '../../utils/formatters.js';
import { useI18n } from '../../i18n/LanguageContext.jsx';

const STATUS_VARIANT = { completed: 'success', processing: 'warning', pending: 'gray', failed: 'danger' };

export default function MRIHistory({ items = [], onDelete }) {
  const { t } = useI18n();
  const [pending, setPending] = useState(null);

  if (items.length === 0) {
    return (
      <EmptyState
        icon={Brain}
        title={t('mri.history.emptyTitle')}
        description={t('mri.history.emptyDescription')}
      />
    );
  }

  return (
    <>
      <div className="divide-y divide-gray-100">
        {items.map((m) => (
          <div key={m.id} className="flex items-center gap-3 py-3">
            <Link
              to={`/mri/${m.id}`}
              className="w-12 h-12 rounded-lg bg-purple-50 text-purple-700 flex items-center justify-center shrink-0 hover:opacity-90"
            >
              <Brain size={22} />
            </Link>
            <Link to={`/mri/${m.id}`} className="flex-1 min-w-0 group">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="font-medium text-gray-900 group-hover:text-primary">{t('mri.history.itemTitle', { id: m.id })}</span>
                <Badge variant={STATUS_VARIANT[m.status] || 'gray'}>
                  {STATUS_VARIANT[m.status] ? t(`mri.status.${m.status}`) : m.status}
                </Badge>
                {(m.result_tumor_type || m.result_tumor_detected != null)
                  && <TumorBadge tumorType={m.result_tumor_type} detected={m.result_tumor_detected} />}
              </div>
              <div className="text-xs text-gray-500 mt-1">{formatRelative(m.created_at)}</div>
            </Link>
            {onDelete && (
              <button
                type="button"
                onClick={() => setPending(m)}
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
        title={t('mri.history.deleteTitle')}
        description={pending ? t('mri.history.deleteDescription', { id: pending.id }) : ''}
        confirmLabel={t('common.delete')}
      />
    </>
  );
}
