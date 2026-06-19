import { describe, it, expect, vi } from 'vitest';

// patientsSlice imports patientService, and authSlice (for the reset actions)
// imports authService → api/axios. Mock both so the reducer is tested alone.
vi.mock('../../services/patientService.js', () => ({
  default: {
    getAll: vi.fn(), create: vi.fn(), update: vi.fn(),
    delete: vi.fn(), getById: vi.fn(), getHistory: vi.fn(),
  },
}));
vi.mock('../../services/authService.js', () => ({
  default: { login: vi.fn(), register: vi.fn(), logout: vi.fn(), getMe: vi.fn() },
}));

import reducer, { fetchPatients } from './patientsSlice.js';
import { login, logout, register } from './authSlice.js';

const loaded = {
  items: [{ id: 1 }, { id: 2 }],
  selected: { id: 1 },
  loading: false,
  error: null,
};

describe('patientsSlice — cache reset on auth change', () => {
  it('clears cached patients on logout', () => {
    const s = reducer(loaded, { type: logout.type });
    expect(s.items).toEqual([]);
    expect(s.selected).toBeNull();
  });

  it('clears cached patients when a new user logs in (no reload needed)', () => {
    // Reproduces the bug: a technician's full list must not survive into the
    // next user's session.
    const s = reducer(loaded, { type: login.fulfilled.type, payload: { user: {}, access: 't' } });
    expect(s.items).toEqual([]);
  });

  it('clears cached patients on register', () => {
    const s = reducer(loaded, { type: register.fulfilled.type, payload: { user: {}, access: 't' } });
    expect(s.items).toEqual([]);
  });

  it('still stores patients on fetch fulfilled', () => {
    const s = reducer({ ...loaded, items: [] },
      { type: fetchPatients.fulfilled.type, payload: [{ id: 9 }] });
    expect(s.items).toEqual([{ id: 9 }]);
  });
});
