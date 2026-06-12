import api from './api.js';

const patientService = {
  getAll: () => api.get('/patients/').then((r) => r.data),
  getById: (id) => api.get(`/patients/${id}/`).then((r) => r.data),
  create: (data) => api.post('/patients/', data).then((r) => r.data),
  update: (id, data) => api.patch(`/patients/${id}/`, data).then((r) => r.data),
  delete: (id) => api.delete(`/patients/${id}/`).then((r) => r.data),
  getHistory: (id) => api.get(`/patients/${id}/history/`).then((r) => r.data),
};

export default patientService;
