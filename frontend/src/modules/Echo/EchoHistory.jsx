import { useState } from 'react';
import { Link } from 'react-router-dom';
import { HeartPulse, Trash2 } from 'lucide-react';

import Badge from '../../components/UI/Badge.jsx';
import ConfirmDialog from '../../components/UI/ConfirmDialog.jsx';
import EmptyState from '../../components/UI/EmptyState.jsx';
import { formatRelative } from '../../utils/formatters.js';
import { useI18n } from '../../i18n/LanguageContext.jsx';

const STATUS_VARIANT = { completed: 'success', processing: 'warning', pending: 'gray', failed: 'danger' };

function efVariant(cat) {
  if (!cat) return 'gray';
  if (cat.startsWith('Normal')) return 'success';
  if (cat.startsWith('Mildly')) return 'warning';
  return 'danger';
}

export default function EchoHistory({ items = [], onDelete }) {
  const { t } = useI18n();
  const [pending, setPending] = useState(null);

  const categoryLabel = (cat) => {
    if (!cat) return '';
    const known = ['Normal', 'Mildly reduced', 'Reduced'];
    return known.includes(cat) ? t(`echo.categories.${cat}`) : cat;
  };

  if (items.length === 0) {
    return (
      <EmptyState
        icon={HeartPulse}
        title={t('echo.history.emptyTitle')}
        description={t('echo.history.emptyDescription')}
      />
    );
  }

  return (
    <>
      <div className="divide-y divide-gray-100">
        {items.map((e) => (
          <div key={e.id} className="flex items-center gap-3 py-3">
            <Link to={`/echo/${e.id}`}
                  className="w-12 h-12 rounded-lg bg-amber-50 text-amber-700 flex items-center justify-center shrink-0 hover:opacity-90">
              <HeartPulse size={22} />
            </Link>
            <Link to={`/echo/${e.id}`} className="flex-1 min-w-0 group">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="font-medium text-gray-900 group-hover:text-primary">Echo #{e.id}</span>
                <Badge variant={STATUS_VARIANT[e.status] || 'gray'}>
                  {STATUS_VARIANT[e.status] ? t(`echo.status.${e.status}`) : e.status}
                </Badge>
                {typeof e.result_ef === 'number' && (
                  <Badge variant={efVariant(e.result_ef_category)}>
                    EF {e.result_ef.toFixed(1)}% · {categoryLabel(e.result_ef_category)}
                  </Badge>
                )}
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
        title={t('echo.history.deleteTitle')}
        description={pending ? t('echo.history.deleteMessage', { id: pending.id }) : ''}
        confirmLabel={t('common.delete')}
        onConfirm={() => { onDelete?.(pending.id); setPending(null); }}
        onClose={() => setPending(null)}
      />
    </>
  );
}
