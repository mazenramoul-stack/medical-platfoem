import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import axios from 'axios';

// react-hot-toast is a side-effecting import; stub it so importing api.js is clean.
vi.mock('react-hot-toast', () => ({ default: { error: vi.fn() } }));

import api from './api.js';

// axios stores registered interceptors on `.handlers`; grab the ones under test.
const responseRejected = () => api.interceptors.response.handlers[0].rejected;
const requestFulfilled = () => api.interceptors.request.handlers[0].fulfilled;

function setLocation(pathname) {
  Object.defineProperty(window, 'location', {
    configurable: true,
    writable: true,
    value: { pathname, href: '' },
  });
}

beforeEach(() => {
  localStorage.clear();
  setLocation('/dashboard');
  delete api.defaults.adapter; // reset any retry-adapter stub from a prior test
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('api request interceptor', () => {
  it('attaches a Bearer token when one is stored', () => {
    localStorage.setItem('access_token', 'tok123');
    expect(requestFulfilled()({ headers: {} }).headers.Authorization).toBe('Bearer tok123');
  });

  it('sends no Authorization header when no token', () => {
    expect(requestFulfilled()({ headers: {} }).headers.Authorization).toBeUndefined();
  });
});

describe('api 401 silent-refresh interceptor', () => {
  it('with no refresh token: clears session and redirects to /login', async () => {
    localStorage.setItem('access_token', 'a');
    await expect(
      responseRejected()({ config: { url: '/mri/' }, response: { status: 401 } }),
    ).rejects.toBeTruthy();
    expect(localStorage.getItem('access_token')).toBeNull();
    expect(window.location.href).toBe('/login');
  });

  it('with a refresh token: refreshes (storing the rotated token) and retries the request', async () => {
    localStorage.setItem('access_token', 'old');
    localStorage.setItem('refresh_token', 'r');
    const postSpy = vi
      .spyOn(axios, 'post')
      .mockResolvedValue({ data: { access: 'newtok', refresh: 'newref' } });
    const adapter = vi.fn().mockResolvedValue({ data: { ok: true }, status: 200, headers: {}, config: {} });
    api.defaults.adapter = adapter;

    const res = await responseRejected()({
      config: { url: '/mri/', headers: {} },
      response: { status: 401 },
    });

    expect(postSpy).toHaveBeenCalledWith(expect.stringContaining('/auth/refresh/'), { refresh: 'r' });
    expect(localStorage.getItem('access_token')).toBe('newtok');
    expect(localStorage.getItem('refresh_token')).toBe('newref'); // rotation persisted
    expect(adapter).toHaveBeenCalled(); // original request was retried
    expect(res.data.ok).toBe(true);
  });

  it('when the refresh itself fails: clears session and redirects', async () => {
    localStorage.setItem('access_token', 'old');
    localStorage.setItem('refresh_token', 'r');
    vi.spyOn(axios, 'post').mockRejectedValue(new Error('refresh expired'));
    await expect(
      responseRejected()({ config: { url: '/mri/', headers: {} }, response: { status: 401 } }),
    ).rejects.toBeTruthy();
    expect(localStorage.getItem('access_token')).toBeNull();
    expect(window.location.href).toBe('/login');
  });

  it('does not attempt a refresh on an auth-endpoint 401 (e.g. failed login)', async () => {
    localStorage.setItem('refresh_token', 'r');
    const postSpy = vi.spyOn(axios, 'post');
    setLocation('/login');
    await expect(
      responseRejected()({ config: { url: '/auth/login/' }, response: { status: 401 } }),
    ).rejects.toBeTruthy();
    expect(postSpy).not.toHaveBeenCalled();
  });

  it('passes non-401 errors through without clearing tokens', async () => {
    localStorage.setItem('access_token', 'a');
    await expect(
      responseRejected()({ config: { url: '/mri/' }, response: { status: 500 } }),
    ).rejects.toBeTruthy();
    expect(localStorage.getItem('access_token')).toBe('a');
    expect(window.location.href).toBe('');
  });
});
