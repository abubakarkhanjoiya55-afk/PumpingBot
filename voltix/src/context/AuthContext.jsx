import { createContext, useContext, useEffect, useMemo, useState } from 'react'
import {
  registerUser,
  loginUser,
  getSessionEmail,
  setSessionEmail,
  clearSession,
  findUserByEmail,
  upsertUser,
  ensureWithdrawUnlock,
  buildTeamStats,
  migrateLegacyStorage,
  isAdminEmail,
} from '../lib/storage.js'
import { KEYS, EVENTS, getWithdrawNetwork, getPlan, planForAmount } from '../lib/constants.js'
import { purgeAdminFromUsers, createGiftClaim, createDepositRequest, createWithdrawRequest } from '../lib/admin.js'

const AuthContext = createContext(null)

function txId() {
  return `tx_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 7)}`
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [ready, setReady] = useState(false)

  useEffect(() => {
    migrateLegacyStorage()
    purgeAdminFromUsers()
    const email = getSessionEmail()
    if (email) {
      if (isAdminEmail(email)) {
        clearSession()
        setReady(true)
        return
      }
      const u = ensureWithdrawUnlock(findUserByEmail(email))
      if (u) setUser(u)
      else clearSession()
    }
    setReady(true)
  }, [])

  useEffect(() => {
    function refreshFromStorage() {
      const email = getSessionEmail()
      if (!email) return
      const u = findUserByEmail(email)
      if (u) setUser({ ...u })
    }
    function onStorage(e) {
      if (e.key === KEYS.users) refreshFromStorage()
    }
    window.addEventListener('storage', onStorage)
    window.addEventListener(EVENTS.usersUpdated, refreshFromStorage)
    return () => {
      window.removeEventListener('storage', onStorage)
      window.removeEventListener(EVENTS.usersUpdated, refreshFromStorage)
    }
  }, [])

  function persist(next) {
    const saved = upsertUser(next)
    setUser({ ...saved })
    return saved
  }

  const value = useMemo(
    () => ({
      ready,
      user,
      isAuthed: !!user,
      register({ name, email, password, referralCode }) {
        const u = registerUser({ name, email, password, referralCode })
        setSessionEmail(u.email)
        setUser(u)
        return u
      },
      login({ email, password }) {
        const u = loginUser(email, password)
        setSessionEmail(u.email)
        setUser(u)
        return u
      },
      logout() {
        clearSession()
        setUser(null)
      },
      refresh() {
        if (!user?.email) return null
        const u = findUserByEmail(user.email)
        if (u) setUser(u)
        return u
      },
      claimGift(giftId, choice) {
        if (!user) throw new Error('Login required')
        const team = buildTeamStats(user.email)
        const claim = createGiftClaim({
          userEmail: user.email,
          userName: user.name,
          giftId,
          teamDeposits: team.teamDeposits,
          rankName: team.rank.name,
          choice,
        })
        const u = findUserByEmail(user.email)
        if (u) setUser({ ...u })
        return claim
      },
      deposit({ amount, networkId, txHash } = {}) {
        if (!user) throw new Error('Login required')
        const network = getWithdrawNetwork(networkId)
        if (!network) throw new Error('Select the network you sent on')
        const req = createDepositRequest({
          userEmail: user.email,
          userName: user.name,
          amount,
          networkId: network.id,
          networkLabel: network.label,
          txHash,
        })
        const u = findUserByEmail(user.email)
        if (u) setUser({ ...u })
        return req
      },
      withdraw({ amount, networkId, address } = {}) {
        if (!user) throw new Error('Login required')
        const amt = Number(amount)
        const bal = Number(user.usdtBalance || 0)
        const network = getWithdrawNetwork(networkId)
        const addr = String(address || '').trim()
        if (!Number.isFinite(amt) || amt <= 0) throw new Error('Enter a valid amount')
        if (amt > bal) throw new Error('Insufficient USDT balance')
        if (!network) throw new Error('Select a withdraw network')
        if (!addr || addr.length < 8) throw new Error('Enter your payout wallet address')
        const now = Date.now()
        const id = txId()
        createWithdrawRequest({
          userEmail: user.email,
          userName: user.name,
          amount: amt,
          networkId: network.id,
          networkLabel: network.label,
          address: addr,
        })
        return persist({
          ...user,
          usdtBalance: bal - amt,
          lastWithdrawAt: now,
          lastWithdrawAddress: addr,
          lastWithdrawNetworkId: network.id,
          withdrawUnlockAt: user.withdrawUnlockAt,
          history: [
            {
              id,
              type: 'WITHDRAW',
              amount: amt,
              note: `Withdraw ${network.label} · ${addr.slice(0, 6)}…${addr.slice(-4)} · pending admin`,
              at: now,
              networkId: network.id,
              address: addr,
            },
            ...(user.history || []),
          ],
        })
      },
      stake(amount, planId) {
        if (!user) throw new Error('Login required')
        const amt = Number(amount)
        const bal = Number(user.usdtBalance || 0)
        const plan = planId ? getPlan(planId) : planForAmount(amt)
        if (!plan) throw new Error('Select a valid plan')
        if (!Number.isFinite(amt) || amt < plan.min || amt > plan.max) {
          throw new Error(`${plan.name} accepts $${plan.min}–$${plan.max} only`)
        }
        if (amt > bal) throw new Error('Deposit USDT first — insufficient balance')
        const stakeRow = {
          id: txId(),
          planId: plan.id,
          planName: plan.name,
          amount: amt,
          yieldMin: plan.yieldMin,
          yieldMax: plan.yieldMax,
          startedAt: Date.now(),
          status: 'ACTIVE',
        }
        return persist({
          ...user,
          usdtBalance: bal - amt,
          staked: [stakeRow, ...(user.staked || [])],
          history: [
            {
              id: txId(),
              type: 'STAKE',
              amount: amt,
              note: `${plan.name} · ${plan.yieldMin}–${plan.yieldMax}% / mo`,
              at: Date.now(),
            },
            ...(user.history || []),
          ],
        })
      },
    }),
    [user, ready],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider')
  return ctx
}
