import axios from 'axios';

const API_URL = import.meta.env.VITE_API_URL || 'https://web-production-6a35f.up.railway.app';

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

export async function login(username, password) {
  const form = new URLSearchParams();
  form.append('username', username);
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

export async function startBot() {
  const { data } = await api.post('/bot/start', null, { headers: authHeaders() });
  return data;
}

export async function stopBot() {
  const { data } = await api.post('/bot/stop', null, { headers: authHeaders() });
  return data;
}

export { API_URL };
