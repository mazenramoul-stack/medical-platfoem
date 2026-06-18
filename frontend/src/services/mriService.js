import api from './api.js';

const mriService = {
  // mode: 'classify' (grayscale scan → Swin 4-class), 'segment' (colored/masked
  // image → U-Net), or 'full' (both). Defaults to 'full' for backward compat.
  upload(patientId, file, onProgress, mode = 'full') {
    const form = new FormData();
    form.append('patient_id', String(patientId));
    form.append('file', file);
    form.append('mode', mode);
    return api
      .post('/mri/upload/', form, {
        headers: { 'Content-Type': 'multipart/form-data' },
        onUploadProgress: (e) => {
          if (onProgress && e.total) {
            onProgress(Math.round((e.loaded * 100) / e.total));
          }
        },
      })
      .then((r) => r.data);
  },
  getAll:       () => api.get('/mri/').then((r) => r.data),
  getById:      (id) => api.get(`/mri/${id}/`).then((r) => r.data),
  getByPatient: (patientId) => api.get(`/mri/?patient_id=${patientId}`).then((r) => r.data),
  delete:       (id) => api.delete(`/mri/${id}/`).then((r) => r.data),
  // On-demand explainability: Grad-CAM + SHAP overlays for an analyzed scan.
  explainMri:   (id) => api.post(`/mri/${id}/explain/`).then((r) => r.data),
};

export default mriService;
