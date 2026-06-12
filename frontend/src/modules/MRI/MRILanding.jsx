import ModalityLanding from '../../components/ModalityLanding.jsx';
import { useI18n } from '../../i18n/LanguageContext.jsx';
import { useTokens } from '../../theme/ThemeContext.jsx';

export default function MRILanding() {
  const { t } = useI18n();
  const { accents } = useTokens();
  return (
    <ModalityLanding
      title={t('mri.landing.title')}
      subtitle={t('mri.landing.subtitle')}
      accent={accents.mri.color}
      model="brain"
      description={t('mri.landing.description')}
      metrics={[
        { label: t('mri.landing.metrics.classifierAcc'), value: '95.4%' },
        { label: t('mri.landing.metrics.macroF1'), value: '0.95' },
        { label: t('mri.landing.metrics.segDice'), value: '0.85' },
        { label: t('mri.landing.metrics.classes'), value: '4' },
      ]}
      classes={[
        { name: t('mri.types.glioma'), desc: t('mri.landing.classes.glioma') },
        { name: t('mri.types.meningioma'), desc: t('mri.landing.classes.meningioma') },
        { name: t('mri.types.pituitary'), desc: t('mri.landing.classes.pituitary') },
        { name: t('mri.types.notumor'), desc: t('mri.landing.classes.notumor') },
      ]}
      ctaTo="/patients"
    />
  );
}
