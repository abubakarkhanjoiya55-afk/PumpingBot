import axios from 'axios';

// proactive-healing = PumpingBot (not My Signals / 26ef9)
const RAILWAY_API = 'https://web-production-c78a0.up.railway.app';

function resolveApiUrl() {
  if (import.meta.env.VITE_API_URL) return import.meta.env.VITE_API_URL;
  if (typeof window !== 'undefined' && window.location.hostname.includes('railway.app')) {
    return window.location.origin;
  }
  return RAILWAY_API;
}

const API_URL = resolveApiUrl();

const api = axios.create({ baseURL: API_URL });

export function getToken() {
  return localStorage.getItem('pb_token');
}

export function setToken(token) {
  if (token) localStorage.setItem('pb_token', token);
  else localStorage.removeItem('pb_token');
}

function authHeaders() {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export async function login(emailOrUsername, password) {
  const form = new URLSearchParams();
  form.append('username', emailOrUsername);
  form.append('password', password);
  const { data } = await api.post('/token', form, {
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
  });
  setToken(data.access_token);
  return data;
}

export async function register(username, email, password, referral_code) {
  const payload = { username, email, password };
  if (referral_code) payload.referral_code = referral_code;
  const { data } = await api.post('/register', payload);
  return data;
}

export async function fetchDashboard() {
  const headers = authHeaders();
  const settled = await Promise.allSettled([
    api.get('/me', { headers }),
    api.get('/signals', { headers }),
    api.get('/trades', { headers }),
    api.get('/open_positions', { headers }),
  ]);
  const val = (i, fallback) =>
    settled[i].status === 'fulfilled' ? settled[i].value.data : fallback;

  const meRes = settled[0];
  if (meRes.status === 'rejected') {
    const err = meRes.reason;
    if (err?.response?.status === 401) throw err;
    throw err || new Error('Failed to load /me');
  }

  return {
    me: val(0, null),
    signals: val(1, []) || [],
    trades: val(2, []) || [],
    positions: val(3, []) || [],
  };
}

export async function connectMT5(creds) {
  const { data } = await api.post('/connect-mt5', creds, { headers: authHeaders() });
  return data;
}

export async function disconnectMT5() {
  const { data } = await api.post('/disconnect-mt5', null, { headers: authHeaders() });
  return data;
}

export async function startBot() {
  const { data } = await api.post('/bot/start', null, { headers: authHeaders() });
  return data;
}

export async function stopBot() {
  const { data } = await api.post('/bot/stop', null, { headers: authHeaders() });
  return data;
}

export async function uploadPaymentScreenshot(file, kind = 'auto') {
  const form = new FormData();
  form.append('file', file);
  const { data } = await api.post(`/subscription/upload-screenshot?kind=${encodeURIComponent(kind)}`, form, {
    headers: { ...authHeaders(), 'Content-Type': 'multipart/form-data' },
  });
  return data;
}

export async function fetchAgentToken() {
  const { data } = await api.post('/me/agent-token', null, { headers: authHeaders() });
  return data;
}

export async function fetchAgentSetup() {
  const { data } = await api.get('/me/agent-setup', { headers: authHeaders() });
  return data;
}

export function eaDownloadUrl() {
  return `${API_URL}/ea/download`;
}

export async function adminDailyUnlock(userId) {
  const { data } = await api.post(`/admin/daily-unlock/${userId}`, null, { headers: authHeaders() });
  return data;
}

export async function adminDailyUnlockAllClear() {
  const { data } = await api.post('/admin/daily-unlock-all-clear', null, { headers: authHeaders() });
  return data;
}

export async function fetchAdminStats() {
  const { data } = await api.get('/admin/stats', { headers: authHeaders() });
  return data;
}

export async function fetchAdminUsers() {
  const { data } = await api.get('/admin/users', { headers: authHeaders() });
  return data;
}

export async function fetchPendingPayments() {
  const { data } = await api.get('/admin/pending-payments', { headers: authHeaders() });
  return data;
}

export async function confirmPayment(userId) {
  const { data } = await api.post(`/admin/confirm-payment/${userId}`, null, { headers: authHeaders() });
  return data;
}

export async function rejectPayment(userId) {
  const { data } = await api.post(`/admin/reject-payment/${userId}`, null, { headers: authHeaders() });
  return data;
}

export async function toggleUserBot(userId) {
  const { data } = await api.post(`/admin/toggle-bot/${userId}`, null, { headers: authHeaders() });
  return data;
}

export async function deleteUser(userId) {
  const { data } = await api.delete(`/admin/delete-user/${userId}`, { headers: authHeaders() });
  return data;
}

export function paymentScreenshotUrl(userId) {
  return `${API_URL}/admin/payment-screenshot/${userId}`;
}

export async function fetchApiInfo() {
  const { data } = await api.get('/api');
  return data;
}

/** Hard refresh — clears caches / SW so Railway deploy dikhe */
export async function applyAppUpdate() {
  try {
    if ('caches' in window) {
      const keys = await caches.keys();
      await Promise.all(keys.map((k) => caches.delete(k)));
    }
    if ('serviceWorker' in navigator) {
      const regs = await navigator.serviceWorker.getRegistrations();
      await Promise.all(regs.map((r) => r.unregister()));
    }
  } catch (_) {
    /* ignore */
  }
  const url = new URL(window.location.href);
  url.searchParams.set('v', String(Date.now()));
  window.location.replace(url.toString());
}

export { API_URL };
