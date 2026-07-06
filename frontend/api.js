/**
 * PumpingBot API client — matches backend main.py endpoints exactly.
 */
const API = (() => {
  const BASE = window.location.origin;

  function getToken() {
    return localStorage.getItem('pb_token');
  }

  function setToken(token) {
    if (token) localStorage.setItem('pb_token', token);
    else localStorage.removeItem('pb_token');
  }

  async function request(method, path, body, isForm = false) {
    const headers = {};
    const token = getToken();
    if (token) headers['Authorization'] = `Bearer ${token}`;

    const opts = { method, headers };
    if (body) {
      if (isForm) {
        opts.body = body;
      } else {
        headers['Content-Type'] = 'application/json';
        opts.body = JSON.stringify(body);
      }
    }

    const res = await fetch(`${BASE}${path}`, opts);
    let data;
    const ct = res.headers.get('content-type') || '';
    if (ct.includes('application/json')) {
      data = await res.json();
    } else {
      data = await res.text();
    }

    if (!res.ok) {
      const msg = typeof data === 'object' ? (data.detail || JSON.stringify(data)) : data;
      throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg));
    }
    return data;
  }

  return {
    getToken,
    setToken,
    isLoggedIn: () => !!getToken(),

    // Auth
    login: async (username, password) => {
      const form = new URLSearchParams();
      form.append('username', username);
      form.append('password', password);
      const data = await request('POST', '/token', form, true);
      setToken(data.access_token);
      return data;
    },

    register: (username, email, password, referral_code) =>
      request('POST', '/register', {
        username, email, password,
        referral_code: referral_code || null,
      }),

    logout: () => setToken(null),

    // User
    getMe: () => request('GET', '/me'),
    getStatus: () => request('GET', '/status'),

    // MT5
    connectMT5: (mt5_login, mt5_password, mt5_server) =>
      request('POST', '/connect-mt5', { mt5_login, mt5_password, mt5_server }),

    // Bot
    startBot: () => request('POST', '/bot/start'),
    stopBot: () => request('POST', '/bot/stop'),

    // Data
    getSignals: () => request('GET', '/signals'),
    getTrades: () => request('GET', '/trades'),
    getOpenPositions: () => request('GET', '/open_positions'),

    // Admin
    getAdminStats: () => request('GET', '/admin/stats'),
    getPendingPayments: () => request('GET', '/admin/pending-payments'),
    getAllUsers: () => request('GET', '/admin/users'),
    confirmPayment: (userId) => request('POST', `/admin/confirm-payment/${userId}`),
    toggleBot: (userId) => request('POST', `/admin/toggle-bot/${userId}`),
    deleteUser: (userId) => request('DELETE', `/admin/delete-user/${userId}`),
  };
})();
