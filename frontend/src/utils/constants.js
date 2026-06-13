export const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';

export const GENDERS = [
  { value: 'M', label: 'Male' },
  { value: 'F', label: 'Female' },
  { value: 'O', label: 'Other' },
];

export const ROLES = [
  { value: 'doctor', label: 'Doctor' },
  { value: 'admin', label: 'Admin' },
];

export const MRI_ALLOWED_EXTENSIONS = ['.png', '.jpg', '.jpeg', '.tif', '.tiff', '.bmp', '.dcm', '.nii', '.nii.gz'];
export const ECG_ALLOWED_EXTENSIONS = ['.csv', '.edf', '.dat', '.hea'];

// Upload size caps — kept in sync with the "Max NN MB" hints shown in the dropzones.
export const MRI_MAX_BYTES = 100 * 1024 * 1024; // 100 MB
export const ECG_MAX_BYTES = 50 * 1024 * 1024;  // 50 MB

export const STATUS_LABELS = {
  pending:    'Pending',
  processing: 'Processing',
  completed:  'Completed',
  failed:     'Failed',
};
