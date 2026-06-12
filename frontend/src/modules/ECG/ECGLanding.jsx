import ModalityLanding from '../../components/ModalityLanding.jsx';
import { useI18n } from '../../i18n/LanguageContext.jsx';
import { useTokens } from '../../theme/ThemeContext.jsx';

export default function ECGLanding() {
  const { t } = useI18n();
  const { accents } = useTokens();
  return (
    <ModalityLanding
      title={t('ecg.landing.title')}
      subtitle={t('ecg.landing.subtitle')}
      accent={accents.ecg.color}
      model="heart"
      description={t('ecg.landing.description')}
      metrics={[
        { label: t('ecg.landing.metrics.meanAuc'), value: '0.980' },
        { label: t('ecg.landing.metrics.balAccuracy'), value: '0.887' },
        { label: t('ecg.landing.metrics.macroF1'), value: '0.73' },
        { label: t('ecg.landing.metrics.pathologies'), value: '7' },
      ]}
      classes={[
        { name: 'AFIB', desc: t('ecg.landing.classes.afib') },
        { name: '1AVB', desc: t('ecg.landing.classes.avb1') },
        { name: 'STACH', desc: t('ecg.landing.classes.stach') },
        { name: 'SBRAD', desc: t('ecg.landing.classes.sbrad') },
        { name: 'RBBB', desc: t('ecg.landing.classes.rbbb') },
        { name: 'LBBB', desc: t('ecg.landing.classes.lbbb') },
        { name: 'PVC', desc: t('ecg.landing.classes.pvc') },
      ]}
      ctaTo="/patients"
      ctaLabel={t('ui.modality.cta')}
    />
  );
}
