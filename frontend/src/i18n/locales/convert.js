export default {
  en: {
    title: 'Convert data',
    subtitle:
      'Standardize a raw clinic file into the exact format each model needs, then '
      + 'download it and run the analysis from the usual page.',
    technicianBadge: 'Technician tool',
    tabs: { mri: 'MRI', ecg: 'ECG', echo: 'Echo', eeg: 'EEG' },
    modalities: {
      mri: {
        name: 'Brain MRI',
        desc: 'DICOM (.dcm or a .zip of a series) or NIfTI volume → a single 8-bit PNG slice.',
      },
      ecg: {
        name: '12-lead ECG',
        desc: 'DICOM ECG waveform (.dcm) → a 12-lead CSV at 500 Hz.',
      },
      echo: {
        name: 'Echocardiogram',
        desc: 'DICOM ultrasound cine (.dcm) or a video file → an MP4 clip.',
      },
      eeg: {
        name: 'EEG',
        desc: 'BrainVision / BioSemi (.bdf) / EEGLAB (.set) — multi-file sets as a .zip → an EDF.',
      },
    },
    dropPrompt: 'Drag a file here, or click to browse',
    dropActive: 'Drop the file…',
    formatsLabel: 'Accepted: {formats}',
    selectedFile: 'Selected file',
    remove: 'Remove',
    params: {
      sliceIndex: 'Slice index (optional)',
      sliceIndexHint: 'Which 2D slice to extract. Leave blank for the middle slice.',
      fps: 'Frames per second (optional)',
      fpsHint: 'Output frame rate. Leave blank to keep the source rate.',
    },
    convert: 'Convert & download',
    converting: 'Converting…',
    success: 'Converted — downloading {name}',
    errors: {
      noFile: 'Choose a file to convert first.',
      generic: 'Conversion failed. Check the file and try again.',
    },
  },
  fr: {
    title: 'Convertir les données',
    subtitle:
      'Standardisez un fichier clinique brut dans le format exact attendu par chaque '
      + 'modèle, puis téléchargez-le et lancez l’analyse depuis la page habituelle.',
    technicianBadge: 'Outil technicien',
    tabs: { mri: 'IRM', ecg: 'ECG', echo: 'Écho', eeg: 'EEG' },
    modalities: {
      mri: {
        name: 'IRM cérébrale',
        desc: 'DICOM (.dcm ou un .zip de série) ou volume NIfTI → une coupe PNG 8 bits.',
      },
      ecg: {
        name: 'ECG 12 dérivations',
        desc: 'Tracé ECG DICOM (.dcm) → un CSV 12 dérivations à 500 Hz.',
      },
      echo: {
        name: 'Échocardiographie',
        desc: 'Ciné-boucle échographique DICOM (.dcm) ou un fichier vidéo → un clip MP4.',
      },
      eeg: {
        name: 'EEG',
        desc: 'BrainVision / BioSemi (.bdf) / EEGLAB (.set) — jeux multi-fichiers en .zip → un EDF.',
      },
    },
    dropPrompt: 'Glissez un fichier ici, ou cliquez pour parcourir',
    dropActive: 'Déposez le fichier…',
    formatsLabel: 'Formats acceptés : {formats}',
    selectedFile: 'Fichier sélectionné',
    remove: 'Retirer',
    params: {
      sliceIndex: 'Indice de coupe (optionnel)',
      sliceIndexHint: 'Quelle coupe 2D extraire. Laissez vide pour la coupe centrale.',
      fps: 'Images par seconde (optionnel)',
      fpsHint: 'Cadence de sortie. Laissez vide pour conserver la cadence source.',
    },
    convert: 'Convertir et télécharger',
    converting: 'Conversion…',
    success: 'Converti — téléchargement de {name}',
    errors: {
      noFile: 'Choisissez d’abord un fichier à convertir.',
      generic: 'Échec de la conversion. Vérifiez le fichier et réessayez.',
    },
  },
};
