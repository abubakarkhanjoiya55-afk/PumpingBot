import {
  KEYS,
  OLD_KEYS,
  EVENTS,
  ADMIN_EMAIL,
  SIGNUP_VOLT,
  REF_VOLT,
  WITHDRAW_LOCK_MS,
  GIFTS,
} from './constants.js'
import {
  collectDownline,
  personalDeposited,
  rankForTeamDeposits,
  nextRank,
  teamDepositTotal,
  rankForUser,
} from './team.js'

export { personalDeposited, teamDepositTotal, rankForUser, collectDownline }

function migrateJsonValue(raw) {
  if (!raw) return raw
  return raw
    .replaceAll('"zrBalance"', '"voltBalance"')
    .replaceAll('"REF_ZR"', '"REF_VOLT"')
    .replaceAll('"SIGNUP_ZR"', '"SIGNUP_VOLT"')
    .replaceAll('Welcome ZR allocation', 'Welcome Volt allocation')
    .replaceAll(' ZR', ' Volt')
    .replaceAll('Welcome VOLT allocation', 'Welcome Volt allocation')
    .replaceAll(' VOLT', ' Volt')
}

let migrated = false

export function migrateLegacyStorage() {
  if (migrated || typeof localStorage === 'undefined') return
  migrated = true
  const pairs = [
    [OLD_KEYS.users, KEYS.users],
    [OLD_KEYS.session, KEYS.session],
    [OLD_KEYS.adminSession, KEYS.adminSession],
    [OLD_KEYS.adminLogs, KEYS.adminLogs],
    [OLD_KEYS.withdrawRequests, KEYS.withdrawRequests],
    [OLD_KEYS.giftClaims, KEYS.giftClaims],
    [OLD_KEYS.depositRequests, KEYS.depositRequests],
  ]
  for (const [oldKey, newKey] of pairs) {
    try {
      const existing = localStorage.getItem(newKey)
      if (existing != null && existing !== '') continue
      const old = localStorage.getItem(oldKey)
      if (old == null) continue
      localStorage.setItem(newKey, migrateJsonValue(old))
    } catch {
      /* ignore */
    }
  }
}

export function isAdminEmail(email) {
  return String(email || '').trim().toLowerCase() === ADMIN_EMAIL
}

function uid() {
  return `u_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`
}

export function listUsers() {
  migrateLegacyStorage()
  try {
    return JSON.parse(localStorage.getItem(KEYS.users) || '[]')
  } catch {
    return []
  }
}

export function saveUsers(users) {
  migrateLegacyStorage()
  localStorage.setItem(KEYS.users, JSON.stringify(users))
  try {
    window.dispatchEvent(new Event(EVENTS.usersUpdated))
  } catch {
    /* ignore */
  }
}

export function getSessionEmail() {
  migrateLegacyStorage()
  return localStorage.getItem(KEYS.session) || ''
}

export function setSessionEmail(email) {
  migrateLegacyStorage()
  localStorage.setItem(KEYS.session, email)
}

export function clearSession() {
  migrateLegacyStorage()
  localStorage.removeItem(KEYS.session)
}

export function findUserByEmail(email) {
  const e = String(email || '').trim().toLowerCase()
  return listUsers().find((u) => u.email === e) || null
}

export function upsertUser(user) {
  const users = listUsers()
  const i = users.findIndex((u) => u.email === user.email)
  if (i >= 0) users[i] = user
  else users.push(user)
  saveUsers(users)
  return user
}

export function registerUser({ name, email, password, referralCode }) {
  const e = String(email || '').trim().toLowerCase()
  if (!e || !password) throw new Error('Email and password required')
  if (isAdminEmail(e)) throw new Error('This email is reserved for admin — use /admin/login')
  if (findUserByEmail(e)) throw new Error('Account already exists — please login')
  const users = listUsers()
  const code = e.slice(0, 4).toUpperCase() + Math.random().toString(36).slice(2, 6).toUpperCase()
  let referrerEmail = ''
  const ref = String(referralCode || '').trim().toUpperCase()
  if (ref) {
    const referrer = users.find((u) => String(u.referralCode).toUpperCase() === ref)
    if (referrer) {
      referrerEmail = referrer.email
      referrer.voltBalance = Number(referrer.voltBalance || 0) + REF_VOLT
      referrer.referralCount = Number(referrer.referralCount || 0) + 1
      referrer.history = [
        {
          id: uid(),
          type: 'REF_VOLT',
          amount: REF_VOLT,
          note: `Referral bonus for ${e}`,
          at: Date.now(),
        },
        ...(referrer.history || []),
      ]
      upsertUser(referrer)
    }
  }
  const user = {
    id: uid(),
    name: String(name || 'Investor').trim() || 'Investor',
    email: e,
    password: String(password),
    referralCode: code,
    referrerEmail,
    usdtBalance: 0,
    voltBalance: SIGNUP_VOLT,
    totalDeposited: 0,
    staked: [],
    lastDepositAt: null,
    lastWithdrawAt: null,
    withdrawUnlockAt: null,
    history: [
      {
        id: uid(),
        type: 'SIGNUP_VOLT',
        amount: SIGNUP_VOLT,
        note: 'Welcome Volt allocation',
        at: Date.now(),
      },
    ],
    createdAt: Date.now(),
  }
  return upsertUser(user)
}

export function loginUser(email, password) {
  const e = String(email || '').trim().toLowerCase()
  if (isAdminEmail(e)) throw new Error('Admin account — open /admin/login instead')
  const user = findUserByEmail(e)
  if (!user) throw new Error('Account not found')
  if (String(user.password) !== String(password)) throw new Error('Wrong password')
  return user
}

export function ensureWithdrawUnlock(user) {
  if (!user || user.withdrawUnlockAt) return user
  const history = user.history || []
  const withdraw = history.find((h) => h.type === 'WITHDRAW')
  const deposit = history.find((h) => h.type === 'DEPOSIT')
  let next = { ...user }
  if (withdraw?.at) {
    next.lastWithdrawAt = withdraw.at
    next.withdrawUnlockAt = withdraw.at + WITHDRAW_LOCK_MS
  } else if (deposit?.at) {
    next.lastDepositAt = deposit.at
    next.withdrawUnlockAt = deposit.at + WITHDRAW_LOCK_MS
  } else {
    return user
  }
  return upsertUser(next)
}

export function buildTeamStats(email) {
  const users = listUsers()
  const f = String(email || '').toLowerCase()
  const downline = collectDownline(f, users)
  const direct = downline.filter((m) => m.depth === 1)
  let teamDeposits = 0
  for (const m of downline) teamDeposits += personalDeposited(m.user)
  teamDeposits = Number(teamDeposits.toFixed(2))
  const rank = rankForTeamDeposits(teamDeposits)
  const upcoming = nextRank(rank)
  const progressToNext = upcoming ? Math.min(100, Math.round((teamDeposits / upcoming.minTeam) * 100)) : 100
  const needForNext = upcoming ? Math.max(0, upcoming.minTeam - teamDeposits) : 0
  const gifts = GIFTS.map((g) => ({
    ...g,
    unlocked: teamDeposits >= g.minTeam,
    progress: Math.min(100, Math.round((teamDeposits / g.minTeam) * 100)),
    remaining: Math.max(0, g.minTeam - teamDeposits),
  }))
  const members = downline.map((m) => ({
    name: m.user.name,
    email: m.user.email,
    depth: m.depth,
    deposited: personalDeposited(m.user),
    staked: (m.user.staked || [])
      .filter((s) => String(s.status).toUpperCase() === 'ACTIVE')
      .reduce((sum, s) => sum + Number(s.amount || 0), 0),
  }))
  return {
    teamDeposits,
    teamSize: downline.length,
    directCount: direct.length,
    rank,
    upcoming,
    progressToNext,
    needForNext,
    gifts,
    members,
    refPct: rank.refPct,
    yieldBonus: rank.yieldBonus,
  }
}
