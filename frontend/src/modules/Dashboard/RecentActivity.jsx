import { Link } from 'react-router-dom';
import { Activity, Brain, Clock, Heart, HeartPulse } from 'lucide-react';

import Badge from '../../components/UI/Badge.jsx';
import EmptyState from '../../components/UI/EmptyState.jsx';
import { SkeletonRow } from '../../components/UI/Skeleton.jsx';
import { formatRelative } from '../../utils/formatters.js';
import { useI18n } from '../../i18n/LanguageContext.jsx';

const STATUS_VARIANT = {
  completed:  'success',
  processing: 'warning',
  pending:    'gray',
  failed:     'danger',
};

// Icon + chip tone per modality, aligned with the Dashboard tiles / PatientDetail tabs.
const TYPE_META = {
  mri:  { icon: Brain,      tone: 'bg-purple-50 text-purple-700' },
  ecg:  { icon: Heart,      tone: 'bg-red-50 text-danger' },
  echo: { icon: HeartPulse, tone: 'bg-amber-50 text-amber-700' },
  eeg:  { icon: Activity,   tone: 'bg-violet-50 text-violet-700' },
};

function Row({ item }) {
  const { t } = useI18n();
  const meta = TYPE_META[item.type] || TYPE_META.mri;
  const Icon = meta.icon;
  const tone = meta.tone;
  const to = `/${item.type}/${item.id}`;
  const statusLabel = STATUS_VARIANT[item.status] ? t(`dashboard.status.${item.status}`) : item.status;
  return (
    <Link to={to} className="flex items-center gap-3 px-5 py-3 hover:bg-gray-50 transition">
      <div className={`w-9 h-9 rounded-lg flex items-center justify-center shrink-0 ${tone}`}>
        <Icon size={18} />
      </div>
      <div className="flex-1 min-w-0">
        <div className="text-sm font-medium text-gray-900 truncate">
          {item.type.toUpperCase()} · {item.label || '—'}
        </div>
        <div className="text-xs text-gray-500">{formatRelative(item.created_at)}</div>
      </div>
      <Badge variant={STATUS_VARIANT[item.status] || 'gray'}>{statusLabel}</Badge>
    </Link>
  );
}

export default function RecentActivity({ items = [], loading = false }) {
  const { t } = useI18n();
  return (
    <div className="bg-card rounded-xl shadow-sm border border-gray-200 overflow-hidden">
      <div className="px-5 py-4 border-b border-gray-200">
        <h2 className="text-base font-semibold text-gray-900">{t('dashboard.recent.title')}</h2>
      </div>
      {loading ? (
        <div className="divide-y divide-gray-100 px-5">
          {Array.from({ length: 4 }).map((_, i) => <SkeletonRow key={i} />)}
        </div>
      ) : items.length === 0 ? (
        <EmptyState
          icon={Clock}
          title={t('dashboard.recent.emptyTitle')}
          description={t('dashboard.recent.emptyDescription')}
        />
      ) : (
        <div className="divide-y divide-gray-100">
          {items.map((it) => <Row key={`${it.type}-${it.id}`} item={it} />)}
        </div>
      )}
    </div>
  );
}
