import { AlertCircle, CheckCircle2 } from 'lucide-react';

import Badge from '../../components/UI/Badge.jsx';
import { useI18n } from '../../i18n/LanguageContext.jsx';
import { normalizeTumorType } from './tumorType.js';

const TUMOR_TYPES = ['glioma', 'meningioma', 'pituitary'];

/**
 * Unified tumour-status badge for MRI results. A tumour is present when the
 * Swin classifier predicted a tumour type (glioma / meningioma / pituitary) OR
 * segmentation flagged one (`detected`) — both collapse to a single red
 * "Tumor" pill. Negatives show a green "No tumour" pill. The specific
 * classifier type, when known, is kept in the tooltip. Uses the shared Badge so
 * the pill style matches the rest of the app (e.g. the ECG pathology badges).
 *
 * @param {{ tumorType: string|null, detected: boolean|null }} props
 */
export default function TumorBadge({ tumorType, detected }) {
  const { t } = useI18n();
  const key = normalizeTumorType(tumorType);
  const isNoTumor = key === 'notumor' || key === 'no_tumor';
  const isTumor = TUMOR_TYPES.includes(key) || (detected === true && !isNoTumor);

  if (isTumor) {
    // Known classifier type -> name it (Glioma/Meningioma/Pituitary); a tumour
    // detected without a type (e.g. segmentation-only) -> generic "Tumor".
    const hasType = TUMOR_TYPES.includes(key);
    const label = hasType ? t(`mri.types.${key}`) : t('mri.types.tumor');
    const tip = hasType ? t(`mri.badge.${key}`) : t('mri.badge.tumor');
    return (
      <Badge variant="danger" className="gap-1" title={tip}>
        <AlertCircle size={12} />
        {label}
      </Badge>
    );
  }

  if (isNoTumor || detected === false) {
    return (
      <Badge variant="success" className="gap-1" title={t('mri.badge.notumor')}>
        <CheckCircle2 size={12} />
        {t('mri.types.notumor')}
      </Badge>
    );
  }

  return (
    <Badge variant="gray" className="gap-1" title={t('mri.badge.unknown')}>
      {tumorType || t('common.unknown')}
    </Badge>
  );
}
