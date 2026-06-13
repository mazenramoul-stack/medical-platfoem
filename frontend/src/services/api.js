import axios from 'axios';
import toast from 'react-hot-toast';

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000/api',
  timeout: 5 * 60 * 1000, // 5 minutes — uploads trigger synchronous inference
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Clear all auth state and bounce to /login (unless already there).
function clearSession() {
  localStorage.removeItem('access_token');
  localStorage.removeItem('refresh_token');
  localStorage.removeItem('user');
  if (!window.location.pathname.startsWith('/login')) {
    window.location.href = '/login';
  }
}

// De-dupe concurrent refreshes: with ROTATE_REFRESH_TOKENS the old refresh token
// is blacklisted on first use, so parallel 401s must share ONE refresh call (a
// second call would send the now-blacklisted token and fail). Uses a bare axios
// (not `api`) so the refresh request doesn't recurse through this interceptor.
let refreshPromise = null;
function refreshAccessToken() {
  if (!refreshPromise) {
    const refresh = localStorage.getItem('refresh_token');
    refreshPromise = axios
      .post(`${api.defaults.baseURL}/auth/refresh/`, { refresh })
      .then(({ data }) => {
        localStorage.setItem('access_token', data.access);
        if (data.refresh) localStorage.setItem('refresh_token', data.refresh); // rotation
        return data.access;
      })
      .finally(() => { refreshPromise = null; });
  }
  return refreshPromise;
}

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (!error.response) {
      toast.error('Server unreachable');
      return Promise.reject(error);
    }
    const original = error.config || {};
    const url = original.url || '';
    const isAuthCall = /\/auth\/(login|refresh|logout)/.test(url);

    // On a 401, try a one-shot silent refresh and retry the original request
    // before giving up. Skip for the auth endpoints themselves (a failed login
    // or refresh must not trigger another refresh) and when no refresh token
    // exists, and never more than once per request (_retried guard).
    if (
      error.response.status === 401
      && !original._retried
      && !isAuthCall
      && localStorage.getItem('refresh_token')
    ) {
      original._retried = true;
      try {
        const access = await refreshAccessToken();
        original.headers = original.headers || {};
        original.headers.Authorization = `Bearer ${access}`;
        return await api(original); // retry once with the fresh token
      } catch {
        clearSession(); // refresh itself failed → the session is dead
        return Promise.reject(error);
      }
    }

    if (error.response.status === 401) {
      clearSession(); // no refresh token, an auth-endpoint 401, or a retried 401
    }
    return Promise.reject(error);
  },
);

export default api;
