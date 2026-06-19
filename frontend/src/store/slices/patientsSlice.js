import { createAsyncThunk, createSlice } from '@reduxjs/toolkit';

import patientService from '../../services/patientService.js';
import { login, logout, register } from './authSlice.js';

const initialState = {
  items: [],
  selected: null,
  loading: false,
  error: null,
};

// Drop the cached patient list whenever the logged-in user changes. The store
// survives login/logout within a single SPA session (no page reload), so
// without this a technician's full list would still be in `items` when a doctor
// logs in next — and the doctor would briefly see every patient. Clearing here
// forces a fresh, correctly-scoped refetch for the new user.
function resetPatients(state) {
  state.items = [];
  state.selected = null;
  state.error = null;
  state.loading = false;
}

export const fetchPatients = createAsyncThunk('patients/fetch', async (_, { rejectWithValue }) => {
  try {
    return await patientService.getAll();
  } catch (err) {
    return rejectWithValue(err.response?.data?.detail || err.message);
  }
});

export const createPatient = createAsyncThunk('patients/create', async (data, { rejectWithValue }) => {
  try {
    return await patientService.create(data);
  } catch (err) {
    return rejectWithValue(err.response?.data?.detail || err.message);
  }
});

export const updatePatient = createAsyncThunk('patients/update', async ({ id, data }, { rejectWithValue }) => {
  try {
    return await patientService.update(id, data);
  } catch (err) {
    return rejectWithValue(err.response?.data?.detail || err.message);
  }
});

export const deletePatient = createAsyncThunk('patients/delete', async (id, { rejectWithValue }) => {
  try {
    await patientService.delete(id);
    return id;
  } catch (err) {
    return rejectWithValue(err.response?.data?.detail || err.message);
  }
});

const patientsSlice = createSlice({
  name: 'patients',
  initialState,
  reducers: {
    select: (state, action) => { state.selected = action.payload; },
    clearError: (state) => { state.error = null; },
  },
  extraReducers: (builder) => {
    builder
      .addCase(fetchPatients.pending,  (s) => { s.loading = true; s.error = null; })
      .addCase(fetchPatients.fulfilled,(s, a) => { s.loading = false; s.items = a.payload; })
      .addCase(fetchPatients.rejected, (s, a) => { s.loading = false; s.error = a.payload; })
      .addCase(createPatient.fulfilled,(s, a) => { s.items.unshift(a.payload); })
      .addCase(updatePatient.fulfilled,(s, a) => {
        const i = s.items.findIndex((p) => p.id === a.payload.id);
        if (i >= 0) s.items[i] = a.payload;
      })
      .addCase(deletePatient.fulfilled,(s, a) => {
        s.items = s.items.filter((p) => p.id !== a.payload);
      })
      // Reset the cache on every auth transition (new user => fresh data).
      .addCase(logout, resetPatients)
      .addCase(login.fulfilled, resetPatients)
      .addCase(register.fulfilled, resetPatients);
  },
});

export const { select, clearError } = patientsSlice.actions;
export default patientsSlice.reducer;
