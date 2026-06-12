import { Loader2 } from 'lucide-react';

import { useI18n } from '../../i18n/LanguageContext.jsx';

export default function Loader({ size = 24, label, className = '' }) {
  const { t } = useI18n();
  const text = label === undefined ? t('common.loading') : label;
  return (
    <div className={`flex items-center justify-center gap-2 text-gray-600 ${className}`}>
      <Loader2 size={size} className="animate-spin" />
      {text && <span className="text-sm">{text}</span>}
    </div>
  );
}
