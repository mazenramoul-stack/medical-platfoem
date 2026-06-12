import { createAsyncThunk, createSlice } from '@reduxjs/toolkit';

import authService from '../../services/authService.js';

function readUser() {
  try {
    const raw = localStorage.getItem('user');
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

const initialState = {
  user: readUser(),
  token: localStorage.getItem('access_token'),
  isAuthenticated: Boolean(localStorage.getItem('access_token')),
  loading: false,
  error: null,
};

export const login = createAsyncThunk('auth/login', async ({ email, password }, { rejectWithValue }) => {
  try {
    return await authService.login(email, password);
  } catch (err) {
    return rejectWithValue(err.response?.data?.detail || err.message || 'Login failed');
  }
});

export const register = createAsyncThunk('auth/register', async (payload, { rejectWithValue }) => {
  try {
    return await authService.register(payload);
  } catch (err) {
    return rejectWithValue(
      err.response?.data?.detail
        || JSON.stringify(err.response?.data ?? {})
        || err.message
        || 'Registration failed',
    );
  }
});

const authSlice = createSlice({
  name: 'auth',
  initialState,
  reducers: {
    logout: (state) => {
      authService.logout();
      state.user = null;
      state.token = null;
      state.isAuthenticated = false;
      state.error = null;
    },
    setUser: (state, action) => {
      state.user = action.payload;
    },
    clearError: (state) => {
      state.error = null;
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(login.pending, (s) => { s.loading = true; s.error = null; })
      .addCase(login.fulfilled, (s, a) => {
        s.loading = false;
        s.user = a.payload.user;
        s.token = a.payload.access;
        s.isAuthenticated = true;
      })
      .addCase(login.rejected, (s, a) => { s.loading = false; s.error = a.payload; })
      .addCase(register.pending, (s) => { s.loading = true; s.error = null; })
      .addCase(register.fulfilled, (s, a) => {
        s.loading = false;
        s.user = a.payload.user;
        s.token = a.payload.access;
        s.isAuthenticated = true;
      })
      .addCase(register.rejected, (s, a) => { s.loading = false; s.error = a.payload; });
  },
});

export const { logout, setUser, clearError } = authSlice.actions;
export default authSlice.reducer;
