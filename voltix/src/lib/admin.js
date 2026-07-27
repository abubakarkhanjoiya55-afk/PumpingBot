import { api, getAdminToken, setAdminToken } from './api.js'

export function isAdminAuthed() {
  return !!getAdminToken()
}

export async function adminLogin(email, password) {
  const data = await api.adminLogin({ email, password })
  setAdminToken(data.token)
  return true
}

export async function adminLogout() {
  try {
    await api.adminLogout()
  } catch {
    /* ignore */
  }
  setAdminToken('')
}

export function purgeAdminFromUsers() {
  /* no-op with server auth */
}

export async function platformStats() {
  const o = await api.adminOverview()
  return o.stats || o
}

export async function liveStakesByPlan() {
  const o = await api.adminOverview()
  return o.liveStakes || o.stakes || []
}

export async function listAdminUsers() {
  return api.adminUsers()
}

export async function getAdminLogs() {
  return api.adminLogs()
}

export async function listWithdrawRequests() {
  return api.adminWithdraws()
}

export async function listGiftClaims() {
  return api.adminGifts()
}

export async function listDepositRequests() {
  return api.adminDeposits()
}

export async function payoutPlanProfit(planId, percent, note = '') {
  return api.payoutProfit({ planId: Number(planId), percent: Number(percent), note })
}

export async function updateWithdrawStatus(id, status) {
  if (status === 'PAID') return api.payWithdraw(id)
  if (status === 'REJECTED') return api.rejectWithdraw(id)
  throw new Error('Unsupported withdraw status')
}

export async function updateGiftClaimStatus(id, status) {
  if (status === 'FULFILLED') return api.fulfillGift(id)
  if (status === 'REJECTED') return api.rejectGift(id)
  throw new Error('Unsupported gift status')
}

export async function approveDeposit(id) {
  return api.approveDeposit(id)
}

export async function rejectDeposit(id, reason = '') {
  return api.rejectDeposit(id, reason)
}

export async function createGiftClaim() {
  throw new Error('Use auth.claimGift')
}

export async function createDepositRequest() {
  throw new Error('Use auth.deposit')
}

export async function createWithdrawRequest() {
  throw new Error('Use auth.withdraw')
}
