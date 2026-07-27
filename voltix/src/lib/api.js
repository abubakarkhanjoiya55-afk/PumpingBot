const USER_TOKEN_KEY = 'voltix_token_v1'
const ADMIN_TOKEN_KEY = 'voltix_admin_token_v1'

/** Same-origin when served by FastAPI; override with VITE_API_URL if needed. */
export function apiBase() {
  const env = import.meta.env?.VITE_API_URL
  if (env) return String(env).replace(/\/$/, '')
  return ''
}

export function getUserToken() {
  try {
    return localStorage.getItem(USER_TOKEN_KEY) || ''
  } catch {
    return ''
  }
}

export function setUserToken(token) {
  if (token) localStorage.setItem(USER_TOKEN_KEY, token)
  else localStorage.removeItem(USER_TOKEN_KEY)
}

export function getAdminToken() {
  try {
    return localStorage.getItem(ADMIN_TOKEN_KEY) || ''
  } catch {
    return ''
  }
}

export function setAdminToken(token) {
  if (token) localStorage.setItem(ADMIN_TOKEN_KEY, token)
  else localStorage.removeItem(ADMIN_TOKEN_KEY)
}

async function request(path, { method = 'GET', body, token, admin = false } = {}) {
  const headers = { Accept: 'application/json' }
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  const auth = token || (admin ? getAdminToken() : getUserToken())
  if (auth) headers.Authorization = `Bearer ${auth}`

  const res = await fetch(`${apiBase()}${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })

  let data = null
  const text = await res.text()
  try {
    data = text ? JSON.parse(text) : null
  } catch {
    data = { detail: text || res.statusText }
  }

  if (!res.ok) {
    const detail = data?.detail
    const msg =
      typeof detail === 'string'
        ? detail
        : Array.isArray(detail)
          ? detail.map((d) => d.msg || JSON.stringify(d)).join(', ')
          : data?.message || res.statusText || 'Request failed'
    throw new Error(msg)
  }
  return data
}

export const api = {
  health: () => request('/api/health'),
  register: (body) => request('/api/auth/register', { method: 'POST', body }),
  login: (body) => request('/api/auth/login', { method: 'POST', body }),
  logout: () => request('/api/auth/logout', { method: 'POST' }),
  me: () => request('/api/me'),
  team: () => request('/api/team'),
  stake: (body) => request('/api/stake', { method: 'POST', body }),
  deposit: (body) => request('/api/deposit', { method: 'POST', body }),
  withdraw: (body) => request('/api/withdraw', { method: 'POST', body }),
  claimGift: (body) => request('/api/gift/claim', { method: 'POST', body }),
  myDeposits: () => request('/api/my/deposits'),
  myGifts: () => request('/api/my/gifts'),
  adminLogin: (body) => request('/api/admin/login', { method: 'POST', body }),
  adminLogout: () => request('/api/admin/logout', { method: 'POST', admin: true }),
  adminOverview: () => request('/api/admin/overview', { admin: true }),
  adminUsers: () => request('/api/admin/users', { admin: true }),
  adminDeposits: () => request('/api/admin/deposits', { admin: true }),
  adminWithdraws: () => request('/api/admin/withdraws', { admin: true }),
  adminGifts: () => request('/api/admin/gifts', { admin: true }),
  adminLogs: () => request('/api/admin/logs', { admin: true }),
  approveDeposit: (id) => request(`/api/admin/deposits/${id}/approve`, { method: 'POST', admin: true }),
  rejectDeposit: (id, reason = '') =>
    request(`/api/admin/deposits/${id}/reject`, { method: 'POST', body: { reason }, admin: true }),
  payWithdraw: (id) => request(`/api/admin/withdraws/${id}/paid`, { method: 'POST', admin: true }),
  rejectWithdraw: (id, reason = '') =>
    request(`/api/admin/withdraws/${id}/reject`, { method: 'POST', body: { reason }, admin: true }),
  fulfillGift: (id) => request(`/api/admin/gifts/${id}/fulfill`, { method: 'POST', admin: true }),
  rejectGift: (id, reason = '') =>
    request(`/api/admin/gifts/${id}/reject`, { method: 'POST', body: { reason }, admin: true }),
  payoutProfit: (body) => request('/api/admin/profit', { method: 'POST', body, admin: true }),
}
