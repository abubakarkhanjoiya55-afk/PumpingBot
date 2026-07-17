import axios from 'axios';

const RAILWAY_API = 'https://web-production-26ef9.up.railway.app';

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
  const { data } = await api.post('/register', {
    username, email, password, referral_code: referral_code || null,
  });
  return data;
}

export async function fetchDashboard() {
  const headers = authHeaders();
  const [me, signals, trades, positions] = await Promise.all([
    api.get('/me', { headers }),
    api.get('/signals', { headers }),
    api.get('/trades', { headers }),
    api.get('/open_positions', { headers }),
  ]);
  return {
    me: me.data,
    signals: signals.data,
    trades: trades.data,
    positions: positions.data,
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

export async function uploadPaymentScreenshot(file) {
  const form = new FormData();
  form.append('file', file);
  const { data } = await api.post('/subscription/upload-screenshot', form, {
    headers: { ...authHeaders(), 'Content-Type': 'multipart/form-data' },
  });
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

export { API_URL };
