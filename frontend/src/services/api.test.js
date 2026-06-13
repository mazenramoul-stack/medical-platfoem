import { describe, it, expect, vi, beforeEach } from 'vitest';

// react-hot-toast is a side-effecting import; stub it so importing api.js is clean.
vi.mock('react-hot-toast', () => ({ default: { error: vi.fn() } }));

import api from './api.js';

// axios stores registered interceptors on `.handlers`; grab the handlers under test.
const responseRejected = () => api.interceptors.response.handlers[0].rejected;
const requestFulfilled = () => api.interceptors.request.handlers[0].fulfilled;

function setLocation(pathname) {
  Object.defineProperty(window, 'location', {
    configurable: true,
    writable: true,
    value: { pathname, href: '' },
  });
}

describe('api request interceptor', () => {
  beforeEach(() => localStorage.clear());

  it('attaches a Bearer token when one is stored', () => {
    localStorage.setItem('access_token', 'tok123');
    const cfg = requestFulfilled()({ headers: {} });
    expect(cfg.headers.Authorization).toBe('Bearer tok123');
  });

  it('sends no Authorization header when no token', () => {
    const cfg = requestFulfilled()({ headers: {} });
    expect(cfg.headers.Authorization).toBeUndefined();
  });
});

describe('api 401 response interceptor', () => {
  beforeEach(() => {
    localStorage.setItem('access_token', 'a');
    localStorage.setItem('refresh_token', 'r');
    localStorage.setItem('user', '{}');
    setLocation('/dashboard');
  });

  it('on 401 clears tokens and redirects to /login', async () => {
    await expect(responseRejected()({ response: { status: 401 } })).rejects.toBeTruthy();
    expect(localStorage.getItem('access_token')).toBeNull();
    expect(localStorage.getItem('refresh_token')).toBeNull();
    expect(localStorage.getItem('user')).toBeNull();
    expect(window.location.href).toBe('/login');
  });

  it('does not redirect again if already on /login', async () => {
    setLocation('/login');
    await expect(responseRejected()({ response: { status: 401 } })).rejects.toBeTruthy();
    expect(window.location.href).toBe(''); // unchanged
  });

  it('passes non-401 errors through without clearing tokens', async () => {
    await expect(responseRejected()({ response: { status: 500 } })).rejects.toBeTruthy();
    expect(localStorage.getItem('access_token')).toBe('a');
    expect(window.location.href).toBe('');
  });
});
