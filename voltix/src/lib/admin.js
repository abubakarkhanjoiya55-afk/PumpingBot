import {
  KEYS,
  EVENTS,
  ADMIN_EMAIL,
  ADMIN_PASSWORD,
  PLANS,
  DEFAULT_REF_PCT,
  WITHDRAW_LOCK_MS,
  GIFTS,
} from './constants.js'
import {
  migrateLegacyStorage,
  listUsers,
  saveUsers,
  isAdminEmail,
  personalDeposited,
  getSessionEmail,
  clearSession,
} from './storage.js'
import { teamDepositTotal, rankForUser } from './team.js'
import { getPlan } from './constants.js'

function admId() {
  return `adm_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 7)}`
}

export function purgeAdminFromUsers() {
  migrateLegacyStorage()
  const cleaned = listUsers().filter((u) => !isAdminEmail(u.email))
  saveUsers(cleaned)
  try {
    const session = getSessionEmail()
    if (isAdminEmail(session)) clearSession()
  } catch {
    /* ignore */
  }
}

export function isAdminAuthed() {
  migrateLegacyStorage()
  return localStorage.getItem(KEYS.adminSession) === '1'
}

export function adminLogin(email, password) {
  if (String(email || '').trim().toLowerCase() !== ADMIN_EMAIL || String(password) !== ADMIN_PASSWORD) {
    throw new Error('Invalid admin credentials')
  }
  purgeAdminFromUsers()
  localStorage.setItem(KEYS.adminSession, '1')
  return true
}

export function adminLogout() {
  migrateLegacyStorage()
  localStorage.removeItem(KEYS.adminSession)
}

function readLogs() {
  migrateLegacyStorage()
  try {
    return JSON.parse(localStorage.getItem(KEYS.adminLogs) || '[]')
  } catch {
    return []
  }
}

function pushLog(entry) {
  const logs = readLogs()
  logs.unshift(entry)
  localStorage.setItem(KEYS.adminLogs, JSON.stringify(logs.slice(0, 200)))
  return entry
}

export function getAdminLogs() {
  return readLogs()
}

export function liveStakesByPlan() {
  const users = listUsers().filter((u) => !isAdminEmail(u.email))
  return PLANS.map((plan) => {
    let stakes = 0
    let amount = 0
    let userCount = 0
    for (const u of users) {
      const active = (u.staked || []).filter(
        (s) => Number(s.planId) === Number(plan.id) && String(s.status).toUpperCase() === 'ACTIVE',
      )
      if (active.length) {
        userCount += 1
        for (const s of active) {
          stakes += 1
          amount += Number(s.amount || 0)
        }
      }
    }
    return {
      planId: plan.id,
      planName: plan.name,
      tag: plan.tag,
      stakes,
      amount: Number(amount.toFixed(2)),
      users: userCount,
    }
  })
}

export function payoutPlanProfit(planId, percent, note = '') {
  const plan = getPlan(planId)
  if (!plan) throw new Error('Invalid plan')
  const pct = Number(percent)
  if (!Number.isFinite(pct) || pct <= 0 || pct > 100) throw new Error('Enter a profit % between 0 and 100')
  const users = listUsers()
  let usersHit = 0
  let stakesHit = 0
  let totalPaid = 0
  for (const user of users) {
    const active = (user.staked || []).filter(
      (s) => Number(s.planId) === Number(planId) && String(s.status).toUpperCase() === 'ACTIVE',
    )
    if (!active.length) continue
    let credit = 0
    const rank = rankForUser(user.email, users)
    const effective = pct + Number(rank.yieldBonus || 0)
    for (const stake of active) {
      const earned = Number(((Number(stake.amount) * effective) / 100).toFixed(4))
      if (earned <= 0) continue
      credit += earned
      stakesHit += 1
      stake.earnedProfit = Number((Number(stake.earnedProfit || 0) + earned).toFixed(4))
    }
    if (credit <= 0) continue
    usersHit += 1
    totalPaid += credit
    user.usdtBalance = Number((Number(user.usdtBalance || 0) + credit).toFixed(4))
    user.totalProfit = Number((Number(user.totalProfit || 0) + credit).toFixed(4))
    user.history = [
      {
        id: admId(),
        type: 'PLAN_PROFIT',
        amount: credit,
        note:
          note ||
          `${plan.name} ${pct}%` +
            (rank.yieldBonus ? ` + ${rank.name} bonus ${rank.yieldBonus}%` : '') +
            ` · ${new Date().toLocaleDateString()}`,
        at: Date.now(),
        planId: plan.id,
      },
      ...(user.history || []),
    ]
  }
  if (stakesHit === 0) {
    throw new Error(`No active stakes on ${plan.name}. Pick the plan users actually staked (see Live stakes below).`)
  }
  saveUsers(users)
  return pushLog({
    id: admId(),
    type: 'PLAN_PROFIT',
    planId: plan.id,
    planName: plan.name,
    percent: pct,
    usersHit,
    stakesHit,
    totalPaid: Number(totalPaid.toFixed(4)),
    note: note || '',
    at: Date.now(),
  })
}

export function platformStats() {
  const users = listUsers().filter((u) => !isAdminEmail(u.email))
  let usdt = 0
  let volt = 0
  let staked = 0
  let activeStakes = 0
  for (const u of users) {
    usdt += Number(u.usdtBalance || 0)
    volt += Number(u.voltBalance || 0)
    for (const s of u.staked || []) {
      if (String(s.status).toUpperCase() === 'ACTIVE') {
        staked += Number(s.amount || 0)
        activeStakes += 1
      }
    }
  }
  return {
    users: users.length,
    usdt: Number(usdt.toFixed(2)),
    volt: Number(volt.toFixed(0)),
    zr: Number(volt.toFixed(0)), // legacy alias used in some UI
    staked: Number(staked.toFixed(2)),
    activeStakes,
  }
}

function readWithdraws() {
  migrateLegacyStorage()
  try {
    return JSON.parse(localStorage.getItem(KEYS.withdrawRequests) || '[]')
  } catch {
    return []
  }
}

function saveWithdraws(list) {
  migrateLegacyStorage()
  localStorage.setItem(KEYS.withdrawRequests, JSON.stringify(list))
  try {
    window.dispatchEvent(new Event(EVENTS.withdrawUpdated))
  } catch {
    /* ignore */
  }
}

export function listWithdrawRequests() {
  return readWithdraws()
}

export function createWithdrawRequest({ userEmail, userName, amount, networkId, networkLabel, address }) {
  const addr = String(address || '').trim()
  if (!addr || addr.length < 8) throw new Error('Enter a valid wallet address')
  if (!networkId || !networkLabel) throw new Error('Select a withdraw network')
  const list = readWithdraws()
  const row = {
    id: admId(),
    userEmail,
    userName: userName || '',
    amount: Number(amount),
    networkId,
    networkLabel,
    address: addr,
    status: 'PENDING',
    at: Date.now(),
    paidAt: null,
  }
  list.unshift(row)
  saveWithdraws(list.slice(0, 300))
  return row
}

export function updateWithdrawStatus(id, status) {
  const list = readWithdraws()
  const i = list.findIndex((r) => r.id === id)
  if (i < 0) throw new Error('Request not found')
  list[i] = {
    ...list[i],
    status,
    paidAt: status === 'PAID' ? Date.now() : list[i].paidAt,
  }
  saveWithdraws(list)
  return list[i]
}

function readGifts() {
  migrateLegacyStorage()
  try {
    return JSON.parse(localStorage.getItem(KEYS.giftClaims) || '[]')
  } catch {
    return []
  }
}

function saveGifts(list) {
  migrateLegacyStorage()
  localStorage.setItem(KEYS.giftClaims, JSON.stringify(list))
  try {
    window.dispatchEvent(new Event(EVENTS.giftUpdated))
  } catch {
    /* ignore */
  }
}

export function listGiftClaims() {
  return readGifts()
}

export function createGiftClaim({ userEmail, userName, giftId, teamDeposits, rankName, choice }) {
  const gift = GIFTS.find((g) => g.id === giftId)
  if (!gift) throw new Error('Invalid milestone')
  const c = String(choice || '').toUpperCase()
  if (c !== 'USDT' && c !== 'GIFT') throw new Error('Choose USDT cash or physical gift')
  const users = listUsers()
  const user = users.find((u) => u.email === String(userEmail || '').toLowerCase())
  if (!user) throw new Error('User not found')
  const claimed = user.claimedGifts || []
  if (claimed.includes(giftId)) throw new Error('You already claimed this milestone')
  const team = Number(teamDeposits)
  if (!Number.isFinite(team) || team < gift.minTeam) {
    throw new Error(`Need $${gift.minTeam.toLocaleString()} team deposits to claim`)
  }
  if (readGifts().find((g) => g.userEmail === user.email && g.giftId === giftId && g.status === 'PENDING')) {
    throw new Error('Claim already pending — wait for admin')
  }
  const choiceLabel = c === 'USDT' ? `${gift.cashUsdt} USDT cash` : gift.giftLabel
  user.claimedGifts = [...claimed, giftId]
  user.history = [
    {
      id: admId(),
      type: 'GIFT_CLAIM',
      amount: c === 'USDT' ? gift.cashUsdt : gift.minTeam,
      note: `Claimed ${choiceLabel} · pending admin`,
      at: Date.now(),
      giftId,
      choice: c,
    },
    ...(user.history || []),
  ]
  saveUsers(users)
  const row = {
    id: admId(),
    userEmail: user.email,
    userName: userName || user.name || '',
    giftId: gift.id,
    giftTitle: gift.title,
    giftLabel: gift.giftLabel,
    cashUsdt: gift.cashUsdt,
    giftDetail: gift.detail,
    choice: c,
    choiceLabel,
    teamDeposits: team,
    rankName: rankName || '',
    status: 'PENDING',
    at: Date.now(),
    fulfilledAt: null,
  }
  const list = readGifts()
  list.unshift(row)
  saveGifts(list.slice(0, 300))
  return row
}

export function updateGiftClaimStatus(id, status) {
  const list = readGifts()
  const i = list.findIndex((r) => r.id === id)
  if (i < 0) throw new Error('Claim not found')
  const row = list[i]
  if (row.status !== 'PENDING' && status !== row.status) throw new Error('Claim already reviewed')
  const now = Date.now()
  list[i] = {
    ...row,
    status,
    fulfilledAt: status === 'FULFILLED' ? now : row.fulfilledAt,
  }
  saveGifts(list)
  if (status === 'FULFILLED' && row.choice === 'USDT') {
    const users = listUsers()
    const ui = users.findIndex((u) => u.email === row.userEmail)
    if (ui >= 0) {
      const user = users[ui]
      const cash = Number(row.cashUsdt || 0)
      user.usdtBalance = Number((Number(user.usdtBalance || 0) + cash).toFixed(4))
      user.history = [
        {
          id: admId(),
          type: 'GIFT_USDT',
          amount: cash,
          note: `Milestone cash reward · ${row.giftTitle}`,
          at: now,
          giftId: row.giftId,
        },
        ...(user.history || []),
      ]
      users[ui] = user
      saveUsers(users)
    }
  }
  if (status === 'REJECTED') {
    const users = listUsers()
    const user = users.find((u) => u.email === row.userEmail)
    if (user) {
      user.claimedGifts = (user.claimedGifts || []).filter((g) => g !== row.giftId)
      saveUsers(users)
    }
  }
  return list[i]
}

export function listAdminUsers() {
  purgeAdminFromUsers()
  const users = listUsers().filter((u) => !isAdminEmail(u.email))
  return users.map((u) => {
    const personalDeposit = personalDeposited(u)
    const teamDeposit = teamDepositTotal(u.email, users)
    const rank = rankForUser(u.email, users)
    const active = (u.staked || []).filter((s) => String(s.status).toUpperCase() === 'ACTIVE')
    const stakedTotal = active.reduce((sum, s) => sum + Number(s.amount || 0), 0)
    return {
      ...u,
      password: undefined,
      personalDeposit,
      teamDeposit,
      rankName: rank.name,
      rankId: rank.id,
      refPct: rank.refPct,
      stakedTotal,
      activeStakeCount: active.length,
    }
  })
}

function readDeposits() {
  migrateLegacyStorage()
  try {
    return JSON.parse(localStorage.getItem(KEYS.depositRequests) || '[]')
  } catch {
    return []
  }
}

function saveDeposits(list) {
  migrateLegacyStorage()
  localStorage.setItem(KEYS.depositRequests, JSON.stringify(list))
  try {
    window.dispatchEvent(new Event(EVENTS.depositUpdated))
  } catch {
    /* ignore */
  }
}

export function listDepositRequests() {
  return readDeposits()
}

export function createDepositRequest({ userEmail, userName, amount, networkId, networkLabel, txHash }) {
  const amt = Number(amount)
  if (!Number.isFinite(amt) || amt < 10) throw new Error('Minimum deposit is 10 USDT')
  if (!networkId || !networkLabel) throw new Error('Select deposit network')
  const email = String(userEmail || '').trim().toLowerCase()
  const users = listUsers()
  const user = users.find((u) => u.email === email)
  if (!user) throw new Error('User not found')
  if (readDeposits().find((d) => d.userEmail === email && d.status === 'PENDING' && Number(d.amount) === amt)) {
    throw new Error('Similar pending deposit already waiting for admin')
  }
  const row = {
    id: admId(),
    userEmail: email,
    userName: userName || user.name || '',
    amount: amt,
    networkId,
    networkLabel,
    txHash: String(txHash || '').trim(),
    status: 'PENDING',
    at: Date.now(),
    reviewedAt: null,
  }
  const list = readDeposits()
  list.unshift(row)
  saveDeposits(list.slice(0, 400))
  user.history = [
    {
      id: admId(),
      type: 'DEPOSIT_PENDING',
      amount: amt,
      note: `Deposit request ${networkLabel} · waiting admin approval`,
      at: Date.now(),
      requestId: row.id,
    },
    ...(user.history || []),
  ]
  saveUsers(users)
  return row
}

export function approveDeposit(id) {
  const list = readDeposits()
  const i = list.findIndex((r) => r.id === id)
  if (i < 0) throw new Error('Deposit request not found')
  const row = list[i]
  if (row.status !== 'PENDING') throw new Error('Request already reviewed')
  const users = listUsers()
  const ui = users.findIndex((u) => u.email === row.userEmail)
  if (ui < 0) throw new Error('User not found')
  const user = users[ui]
  const amount = Number(row.amount)
  const now = Date.now()
  user.usdtBalance = Number((Number(user.usdtBalance || 0) + amount).toFixed(4))
  user.totalDeposited = Number((personalDeposited(user) + amount).toFixed(2))
  user.lastDepositAt = now
  user.withdrawUnlockAt = user.withdrawUnlockAt || now + WITHDRAW_LOCK_MS
  user.history = [
    {
      id: admId(),
      type: 'DEPOSIT',
      amount,
      note: `Approved deposit · ${row.networkLabel}${row.txHash ? ` · ${row.txHash.slice(0, 10)}…` : ''}`,
      at: now,
      requestId: row.id,
    },
    ...(user.history || []),
  ]
  users[ui] = user
  if (user.referrerEmail) {
    const ri = users.findIndex((u) => u.email === String(user.referrerEmail).toLowerCase())
    if (ri >= 0) {
      const ref = users[ri]
      const rank = rankForUser(ref.email, users)
      const pct = Number(rank?.refPct ?? DEFAULT_REF_PCT)
      const commission = Number(((amount * pct) / 100).toFixed(2))
      ref.usdtBalance = Number((Number(ref.usdtBalance || 0) + commission).toFixed(4))
      ref.history = [
        {
          id: admId(),
          type: 'REF_DEPOSIT',
          amount: commission,
          note: `${pct}% (${rank.name}) of approved ${amount} USDT from ${user.email}`,
          at: now,
        },
        ...(ref.history || []),
      ]
      users[ri] = ref
    }
  }
  saveUsers(users)
  list[i] = { ...row, status: 'APPROVED', reviewedAt: now }
  saveDeposits(list)
  return list[i]
}

export function rejectDeposit(id, reason = '') {
  const list = readDeposits()
  const i = list.findIndex((r) => r.id === id)
  if (i < 0) throw new Error('Deposit request not found')
  const row = list[i]
  if (row.status !== 'PENDING') throw new Error('Request already reviewed')
  const now = Date.now()
  list[i] = { ...row, status: 'REJECTED', reviewedAt: now, rejectReason: reason || '' }
  saveDeposits(list)
  const users = listUsers()
  const user = users.find((u) => u.email === row.userEmail)
  if (user) {
    user.history = [
      {
        id: admId(),
        type: 'DEPOSIT_REJECTED',
        amount: row.amount,
        note: reason || 'Deposit request rejected by admin',
        at: now,
        requestId: row.id,
      },
      ...(user.history || []),
    ]
    saveUsers(users)
  }
  return list[i]
}
