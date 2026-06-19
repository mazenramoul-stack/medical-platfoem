import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { configureStore } from '@reduxjs/toolkit';
import { Provider } from 'react-redux';
import { MemoryRouter } from 'react-router-dom';

vi.mock('../../services/patientService.js', () => ({
  default: { getById: vi.fn(), create: vi.fn(), update: vi.fn() },
}));
vi.mock('../../services/doctorService.js', () => ({
  default: { getAll: vi.fn() },
}));
vi.mock('react-hot-toast', () => ({ default: { success: vi.fn(), error: vi.fn() } }));

import patientService from '../../services/patientService.js';
import doctorService from '../../services/doctorService.js';
import authReducer from '../../store/slices/authSlice.js';
import patientsReducer from '../../store/slices/patientsSlice.js';
import PatientForm from './PatientForm.jsx';
import { LanguageProvider } from '../../i18n/LanguageContext.jsx';

function renderForm(role) {
  const store = configureStore({
    reducer: { auth: authReducer, patients: patientsReducer },
    preloadedState: {
      auth: {
        user: { full_name: 'U', email: 'u@x.com', role },
        token: 't', isAuthenticated: true, loading: false, error: null,
      },
    },
  });
  return render(
    <Provider store={store}>
      <MemoryRouter>
        <LanguageProvider>
          <PatientForm />
        </LanguageProvider>
      </MemoryRouter>
    </Provider>,
  );
}

describe('PatientForm doctor assignment', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    doctorService.getAll.mockResolvedValue([
      { id: 11, full_name: 'Dr Alice', email: 'alice@x.com' },
      { id: 22, full_name: 'Dr Bob', email: 'bob@x.com' },
    ]);
    patientService.create.mockResolvedValue({ id: 99, full_name: 'Jane', doctors: [] });
  });

  it('hides the doctor assignment section for a doctor', () => {
    renderForm('doctor');
    expect(screen.queryByText('Assign to doctors')).toBeNull();
    expect(doctorService.getAll).not.toHaveBeenCalled();
  });

  it('shows the assignment section and lists doctors for a technician', async () => {
    renderForm('technician');
    expect(screen.getByText('Assign to doctors')).toBeInTheDocument();
    expect(await screen.findByText('Dr Alice')).toBeInTheDocument();
    expect(screen.getByText('Dr Bob')).toBeInTheDocument();
  });

  it('submits doctor_ids when a technician assigns a doctor', async () => {
    renderForm('technician');
    await screen.findByText('Dr Alice');
    fireEvent.change(screen.getByLabelText('Full name'), { target: { value: 'Jane' } });
    fireEvent.change(screen.getByLabelText('Age'), { target: { value: '40' } });
    fireEvent.click(screen.getByRole('checkbox', { name: /Dr Alice/ }));
    fireEvent.click(screen.getByRole('button', { name: /Create patient/i }));
    await waitFor(() => {
      expect(patientService.create).toHaveBeenCalledWith(
        expect.objectContaining({ full_name: 'Jane', age: 40, doctor_ids: [11] }),
      );
    });
  });
});
