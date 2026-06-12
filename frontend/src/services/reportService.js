import api from './api.js';

const reportService = {
  generate({ patientId, mriId, ecgId, echoId, eegId }) {
    return api
      .post('/reports/generate/', {
        patient_id: patientId,
        mri_analysis_id: mriId ?? undefined,
        ecg_analysis_id: ecgId ?? undefined,
        echo_analysis_id: echoId ?? undefined,
        eeg_analysis_id: eegId ?? undefined,
      })
      .then((r) => r.data);
  },
  getAll:       () => api.get('/reports/').then((r) => r.data),
  getById:      (id) => api.get(`/reports/${id}/`).then((r) => r.data),
  getByPatient: (patientId) => api.get(`/reports/?patient_id=${patientId}`).then((r) => r.data),
  delete:       (id) => api.delete(`/reports/${id}/`).then((r) => r.data),
  downloadPdf:  (id) =>
    api.get(`/reports/${id}/download/`, { responseType: 'blob' }).then((r) => r.data),
};

export default reportService;
