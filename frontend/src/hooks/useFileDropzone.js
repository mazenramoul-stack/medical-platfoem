import { useCallback } from 'react';
import { useDropzone } from 'react-dropzone';
import toast from 'react-hot-toast';

import { useI18n } from '../i18n/LanguageContext.jsx';
import { formatBytes } from '../utils/formatters.js';

/**
 * useDropzone wrapper that surfaces a toast when a file is rejected, instead of
 * silently discarding it (the default react-dropzone behaviour). Handles the two
 * rejection causes the upload flows can produce — wrong file type and, when a
 * `maxSize` is given, oversized files. Takes the same options as useDropzone plus
 * an optional `maxSize` in bytes; always single-file.
 */
export function useFileDropzone({ accept, onDrop, maxSize, ...rest }) {
  const { t } = useI18n();

  const onDropRejected = useCallback(
    (rejections) => {
      rejections.forEach(({ file, errors }) => {
        const tooLarge = errors.some((e) => e.code === 'file-too-large');
        toast.error(
          tooLarge
            ? t('common.uploadTooLarge', { name: file.name, max: formatBytes(maxSize) })
            : t('common.uploadInvalidType', { name: file.name }),
        );
      });
    },
    [t, maxSize],
  );

  return useDropzone({ accept, onDrop, maxSize, multiple: false, onDropRejected, ...rest });
}
