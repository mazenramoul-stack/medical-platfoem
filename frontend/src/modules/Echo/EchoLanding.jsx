import ModalityLanding from '../../components/ModalityLanding.jsx';
import { useI18n } from '../../i18n/LanguageContext.jsx';
import { useTokens } from '../../theme/ThemeContext.jsx';

export default function EchoLanding() {
  const { t } = useI18n();
  const { accents } = useTokens();
  return (
    <ModalityLanding
      title={t('echo.landing.title')}
      subtitle={t('echo.landing.subtitle')}
      accent={accents.echo.color}
      model="heart"
      description={t('echo.landing.description')}
      metrics={[
        { label: t('echo.landing.metrics.efModel'), value: 'R(2+1)D' },
        { label: t('echo.landing.metrics.segmentation'), value: 'DeepLabV3' },
        { label: t('echo.landing.metrics.output'), value: 'EF %' },
        { label: t('echo.landing.metrics.source'), value: 'EchoNet' },
      ]}
      classes={[
        { name: t('echo.landing.classes.ef.name'), desc: t('echo.landing.classes.ef.desc') },
        { name: t('echo.landing.classes.category.name'), desc: t('echo.landing.classes.category.desc') },
        { name: t('echo.landing.classes.seg.name'), desc: t('echo.landing.classes.seg.desc') },
      ]}
      ctaTo="/patients"
      ctaLabel={t('ui.modality.cta')}
    />
  );
}
