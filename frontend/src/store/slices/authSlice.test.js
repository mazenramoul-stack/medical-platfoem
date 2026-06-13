import { describe, it, expect, vi } from 'vitest';

// authSlice's logout() calls authService.logout() (a side effect → api/axios).
// Mock it so the reducer logic is tested in isolation.
vi.mock('../../services/authService.js', () => ({
  default: { logout: vi.fn(), login: vi.fn(), register: vi.fn() },
}));

import reducer, { logout, setUser, clearError, login, register } from './authSlice.js';

const base = { user: null, token: null, isAuthenticated: false, loading: false, error: null };

describe('authSlice reducer', () => {
  it('login.fulfilled sets user, token, and authenticated', () => {
    const s = reducer(
      { ...base, loading: true },
      { type: login.fulfilled.type, payload: { user: { email: 'a@b.com' }, access: 'tok' } },
    );
    expect(s.isAuthenticated).toBe(true);
    expect(s.token).toBe('tok');
    expect(s.user.email).toBe('a@b.com');
    expect(s.loading).toBe(false);
  });

  it('login.rejected records the error and stays unauthenticated', () => {
    const s = reducer(
      { ...base, loading: true },
      { type: login.rejected.type, payload: 'invalid credentials' },
    );
    expect(s.error).toBe('invalid credentials');
    expect(s.isAuthenticated).toBe(false);
    expect(s.loading).toBe(false);
  });

  it('register.fulfilled authenticates the new user', () => {
    const s = reducer(
      base,
      { type: register.fulfilled.type, payload: { user: { email: 'n@b.com' }, access: 't2' } },
    );
    expect(s.isAuthenticated).toBe(true);
    expect(s.user.email).toBe('n@b.com');
  });

  it('logout clears auth state', () => {
    const s = reducer(
      { ...base, user: { email: 'a' }, token: 't', isAuthenticated: true },
      logout(),
    );
    expect(s.user).toBeNull();
    expect(s.token).toBeNull();
    expect(s.isAuthenticated).toBe(false);
  });

  it('setUser and clearError', () => {
    expect(reducer(base, setUser({ email: 'x' })).user.email).toBe('x');
    expect(reducer({ ...base, error: 'boom' }, clearError()).error).toBeNull();
  });
});
