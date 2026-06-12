import { AlertCircle, CheckCircle2 } from 'lucide-react';

import { useI18n } from '../../i18n/LanguageContext.jsx';

const TYPE_META = {
  glioma:     { variant: 'danger',    icon: AlertCircle,  labelKey: 'mri.types.glioma',     tipKey: 'mri.badge.glioma' },
  meningioma: { variant: 'warning',   icon: AlertCircle,  labelKey: 'mri.types.meningioma', tipKey: 'mri.badge.meningioma' },
  pituitary:  { variant: 'secondary', icon: AlertCircle,  labelKey: 'mri.types.pituitary',  tipKey: 'mri.badge.pituitary' },
  notumor:    { variant: 'success',   icon: CheckCircle2, labelKey: 'mri.types.notumor',    tipKey: 'mri.badge.notumor' },
  no_tumor:   { variant: 'success',   icon: CheckCircle2, labelKey: 'mri.types.notumor',    tipKey: 'mri.badge.notumor' },
};

// Pastel chip + dark text stays readable on both the light and dark themes.
const VARIANT_BG = {
  success:   'bg-green-100 text-green-800',
  danger:    'bg-red-100 text-red-800',
  warning:   'bg-amber-100 text-amber-800',
  secondary: 'bg-cyan-100 text-cyan-800',
  gray:      'bg-gray-100 text-gray-700',
};

export default function TumorBadge({ tumorType, detected }) {
  const { t } = useI18n();
  const key = (tumorType || '').toLowerCase();
  const meta = TYPE_META[key];
  const variant = meta ? meta.variant : (detected ? 'danger' : 'gray');
  const Icon = meta ? meta.icon : (detected ? AlertCircle : CheckCircle2);
  const label = meta ? t(meta.labelKey) : (tumorType || t('common.unknown'));
  const tip = meta ? t(meta.tipKey) : (tumorType || t('mri.badge.unknown'));
  return (
    <span
      title={tip}
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${VARIANT_BG[variant]}`}
    >
      <Icon size={12} />
      {label}
    </span>
  );
}
