import ModalityLanding from '../../components/ModalityLanding.jsx';
import { useI18n } from '../../i18n/LanguageContext.jsx';
import { useTokens } from '../../theme/ThemeContext.jsx';

export default function EEGLanding() {
  const { t } = useI18n();
  const { accents } = useTokens();
  return (
    <ModalityLanding
      title={t('eeg.landing.title')}
      subtitle={t('eeg.landing.subtitle')}
      accent={accents.eeg.color}
      model="brain"
      description={t('eeg.landing.description')}
      metrics={[
        { label: t('eeg.landing.metrics.patterns'), value: '6 IIIC' },
        { label: t('eeg.landing.metrics.model'), value: 'BIOT' },
        { label: t('eeg.landing.metrics.segment'), value: '10 s' },
        { label: t('eeg.landing.metrics.flag'), value: t('eeg.landing.metrics.flagValue') },
      ]}
      classes={[
        { name: t('eeg.landing.classes.sz.name'), desc: t('eeg.landing.classes.sz.desc') },
        { name: t('eeg.landing.classes.lpd.name'), desc: t('eeg.landing.classes.lpd.desc') },
        { name: t('eeg.landing.classes.gpd.name'), desc: t('eeg.landing.classes.gpd.desc') },
        { name: t('eeg.landing.classes.lrda.name'), desc: t('eeg.landing.classes.lrda.desc') },
        { name: t('eeg.landing.classes.grda.name'), desc: t('eeg.landing.classes.grda.desc') },
        { name: t('eeg.landing.classes.other.name'), desc: t('eeg.landing.classes.other.desc') },
      ]}
      ctaTo="/patients"
      ctaLabel={t('ui.modality.cta')}
    />
  );
}
