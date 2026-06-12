import api from './api.js';

const echoService = {
  upload(patientId, file, onProgress) {
    const form = new FormData();
    form.append('patient_id', String(patientId));
    form.append('file', file);
    return api
      .post('/echo/upload/', form, {
        headers: { 'Content-Type': 'multipart/form-data' },
        onUploadProgress: (e) => {
          if (onProgress && e.total) onProgress(Math.round((e.loaded * 100) / e.total));
        },
      })
      .then((r) => r.data);
  },
  getAll:       () => api.get('/echo/').then((r) => r.data),
  getById:      (id) => api.get(`/echo/${id}/`).then((r) => r.data),
  getByPatient: (patientId) => api.get(`/echo/?patient_id=${patientId}`).then((r) => r.data),
  delete:       (id) => api.delete(`/echo/${id}/`).then((r) => r.data),
};

export default echoService;
