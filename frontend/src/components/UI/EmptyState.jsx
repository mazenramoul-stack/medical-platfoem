import { Inbox } from 'lucide-react';

import { useI18n } from '../../i18n/LanguageContext.jsx';

export default function EmptyState({ icon: Icon = Inbox, title, description, action }) {
  const { t } = useI18n();
  return (
    <div className="flex flex-col items-center justify-center text-center py-16 px-4">
      <div
        className="w-16 h-16 rounded-2xl flex items-center justify-center mb-4"
        style={{ background: 'rgb(var(--rgb-neuro) / 0.08)', border: '1px solid var(--edge)', color: 'var(--neuro-fg)', boxShadow: '0 0 24px var(--glow-soft)' }}
      >
        <Icon size={28} />
      </div>
      <h3 className="text-base font-mono font-bold text-hi tracking-wide">{title ?? t('ui.empty.title')}</h3>
      {description && <p className="text-sm text-low mt-1 max-w-md">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
