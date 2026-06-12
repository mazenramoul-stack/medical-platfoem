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

export const STATUS_LABELS = {
  pending:    'Pending',
  processing: 'Processing',
  completed:  'Completed',
  failed:     'Failed',
};
