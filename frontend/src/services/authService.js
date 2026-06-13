import api from './api.js';

const authService = {
  async login(email, password) {
    const { data } = await api.post('/auth/login/', { email, password });
    localStorage.setItem('access_token', data.access);
    localStorage.setItem('refresh_token', data.refresh);
    localStorage.setItem('user', JSON.stringify(data.user));
    return data;
  },

  async register(payload) {
    const { data } = await api.post('/auth/register/', payload);
    localStorage.setItem('access_token', data.access);
    localStorage.setItem('refresh_token', data.refresh);
    localStorage.setItem('user', JSON.stringify(data.user));
    return data;
  },

  async getMe() {
    const { data } = await api.get('/auth/me/');
    return data;
  },

  logout() {
    const refresh = localStorage.getItem('refresh_token');
    const access = localStorage.getItem('access_token');
    // Best-effort server-side revocation (blacklist the refresh token). Send the
    // access token explicitly so it survives the localStorage clear below, and
    // never block local logout on the network call.
    if (refresh && access) {
      api.post('/auth/logout/', { refresh }, { headers: { Authorization: `Bearer ${access}` } })
        .catch(() => {});
    }
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    localStorage.removeItem('user');
  },
};

export default authService;
