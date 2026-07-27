import { createContext, useContext, useEffect, useMemo, useState } from 'react'
import { api, getUserToken, setUserToken } from '../lib/api.js'
import { fetchMe, buildTeamStats } from '../lib/storage.js'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [team, setTeam] = useState(null)
  const [ready, setReady] = useState(false)

  async function loadTeam() {
    if (!getUserToken()) {
      setTeam(null)
      return null
    }
    try {
      const t = await buildTeamStats()
      setTeam(t)
      return t
    } catch {
      setTeam(null)
      return null
    }
  }

  async function refresh() {
    if (!getUserToken()) {
      setUser(null)
      setTeam(null)
      return null
    }
    const u = await fetchMe()
    if (u) {
      setUser(u)
      await loadTeam()
    } else {
      setUser(null)
      setTeam(null)
    }
    return u
  }

  useEffect(() => {
    ;(async () => {
      if (getUserToken()) {
        await refresh()
      }
      setReady(true)
    })()
  }, [])

  const value = useMemo(
    () => ({
      ready,
      user,
      team,
      isAuthed: !!user,
      async register({ name, email, password, referralCode }) {
        const data = await api.register({ name, email, password, referralCode })
        setUserToken(data.token)
        setUser(data.user)
        await loadTeam()
        return data.user
      },
      async login({ email, password }) {
        const data = await api.login({ email, password })
        setUserToken(data.token)
        setUser(data.user)
        await loadTeam()
        return data.user
      },
      async logout() {
        try {
          await api.logout()
        } catch {
          /* ignore */
        }
        setUserToken('')
        setUser(null)
        setTeam(null)
      },
      refresh,
      async claimGift(giftId, choice) {
        const res = await api.claimGift({ giftId, choice })
        await refresh()
        return res
      },
      async deposit({ amount, networkId, txHash } = {}) {
        const res = await api.deposit({ amount: Number(amount), networkId, txHash })
        await refresh()
        return res
      },
      async withdraw({ amount, networkId, address } = {}) {
        const res = await api.withdraw({ amount: Number(amount), networkId, address })
        await refresh()
        return res.user || (await fetchMe())
      },
      async stake(amount, planId) {
        const res = await api.stake({ amount: Number(amount), planId: Number(planId) })
        await refresh()
        return res.user || (await fetchMe())
      },
    }),
    [user, team, ready],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider')
  return ctx
}
