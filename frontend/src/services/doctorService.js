import api from './api.js';

// Technician-only: the list of doctors a patient can be assigned to.
// The backend gates this with IsTechnician (a doctor gets 403).
const doctorService = {
  getAll: () => api.get('/auth/doctors/').then((r) => r.data),
};

export default doctorService;
