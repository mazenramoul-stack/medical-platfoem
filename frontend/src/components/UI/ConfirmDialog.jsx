import Button from './Button.jsx';
import Modal from './Modal.jsx';
import { useI18n } from '../../i18n/LanguageContext.jsx';

export default function ConfirmDialog({
  open, onClose, onConfirm, title,
  description, confirmLabel, cancelLabel,
  variant = 'danger',
}) {
  const { t } = useI18n();
  return (
    <Modal
      open={open}
      onClose={onClose}
      title={title ?? t('ui.confirm.title')}
      footer={(
        <>
          <Button variant="ghost" onClick={onClose}>{cancelLabel ?? t('common.cancel')}</Button>
          <Button variant={variant} onClick={onConfirm}>{confirmLabel ?? t('common.confirm')}</Button>
        </>
      )}
    >
      <p className="text-sm text-gray-700">{description}</p>
    </Modal>
  );
}
