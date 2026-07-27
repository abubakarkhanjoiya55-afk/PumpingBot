import { api, getUserToken, setUserToken } from './api.js'

export function isAdminEmail(email) {
  return String(email || '').trim().toLowerCase() === 'admin@voltix.exchange'
}

/** @deprecated localStorage migration no longer needed — server is source of truth */
export function migrateLegacyStorage() {}

export async function registerUser({ name, email, password, referralCode }) {
  const data = await api.register({ name, email, password, referralCode })
  setUserToken(data.token)
  return data.user
}

export async function loginUser(email, password) {
  const data = await api.login({ email, password })
  setUserToken(data.token)
  return data.user
}

export function getSessionEmail() {
  return getUserToken() ? '__token__' : ''
}

export function setSessionEmail() {
  /* token set by login/register */
}

export function clearSession() {
  setUserToken('')
}

export async function fetchMe() {
  if (!getUserToken()) return null
  try {
    return await api.me()
  } catch {
    setUserToken('')
    return null
  }
}

export async function buildTeamStats() {
  return api.team()
}

export async function fetchMyDepositRequests() {
  // Prefer history-driven UI; deposits list is admin-only on API.
  // Return empty and let Deposit page use user.history DEPOSIT_* entries,
  // OR expose a lightweight endpoint — for now return [] and page uses history.
  return []
}
