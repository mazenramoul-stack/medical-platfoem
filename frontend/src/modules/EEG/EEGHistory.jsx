import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Brain, Trash2 } from 'lucide-react';

import Badge from '../../components/UI/Badge.jsx';
import ConfirmDialog from '../../components/UI/ConfirmDialog.jsx';
import EmptyState from '../../components/UI/EmptyState.jsx';
import { formatRelative } from '../../utils/formatters.js';
import { useI18n } from '../../i18n/LanguageContext.jsx';

const STATUS_VARIANT = { completed: 'success', processing: 'warning', pending: 'gray', failed: 'danger' };
const HARMFUL = new Set(['SZ', 'LPD', 'GPD']);

export default function EEGHistory({ items = [], onDelete }) {
  const { t } = useI18n();
  const [pending, setPending] = useState(null);

  if (items.length === 0) {
    return (
      <EmptyState
        icon={Brain}
        title={t('eeg.history.emptyTitle')}
        description={t('eeg.history.emptyDescription')}
      />
    );
  }

  return (
    <>
      <div className="divide-y divide-gray-100">
        {items.map((e) => (
          <div key={e.id} className="flex items-center gap-3 py-3">
            <Link to={`/eeg/${e.id}`}
                  className="w-12 h-12 rounded-lg bg-purple-50 flex items-center justify-center shrink-0 hover:opacity-90"
                  style={{ color: 'var(--violet-fg)' }}>
              <Brain size={22} />
            </Link>
            <Link to={`/eeg/${e.id}`} className="flex-1 min-w-0 group">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="font-medium text-gray-900 group-hover:text-primary">EEG #{e.id}</span>
                <Badge variant={STATUS_VARIANT[e.status] || 'gray'}>
                  {STATUS_VARIANT[e.status] ? t(`eeg.status.${e.status}`) : e.status}
                </Badge>
                {e.result_dominant_pattern && (
                  <Badge variant={HARMFUL.has(e.result_dominant_pattern) ? 'danger' : 'gray'}>
                    {e.result_dominant_pattern}
                  </Badge>
                )}
                {e.result_harmful === true && <Badge variant="danger">{t('eeg.harmful')}</Badge>}
              </div>
              <div className="text-xs text-gray-500 mt-1">{formatRelative(e.created_at)}</div>
            </Link>
            {onDelete && (
              <button type="button" onClick={() => setPending(e)}
                      className="text-gray-400 hover:text-danger p-2" aria-label={t('common.delete')}>
                <Trash2 size={16} />
              </button>
            )}
          </div>
        ))}
      </div>

      <ConfirmDialog
        open={!!pending}
        title={t('eeg.deleteDialog.title')}
        description={pending ? t('eeg.deleteDialog.message', { id: pending.id }) : ''}
        confirmLabel={t('common.delete')}
        onConfirm={() => { onDelete?.(pending.id); setPending(null); }}
        onClose={() => setPending(null)}
      />
    </>
  );
}
