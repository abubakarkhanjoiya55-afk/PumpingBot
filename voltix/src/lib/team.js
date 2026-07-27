import { RANKS, GIFTS } from './constants.js'

export function rankForTeamDeposits(teamDeposits) {
  const n = Number(teamDeposits) || 0
  let rank = RANKS[0]
  for (const r of RANKS) {
    if (n >= r.minTeam) rank = r
  }
  return rank
}

export function nextRank(rank) {
  const i = RANKS.findIndex((r) => r.id === rank.id)
  return i < 0 || i >= RANKS.length - 1 ? null : RANKS[i + 1]
}

export function personalDeposited(user) {
  if (!user) return 0
  return Number(user.totalDeposited) > 0
    ? Number(user.totalDeposited)
    : (user.history || [])
        .filter((h) => h.type === 'DEPOSIT')
        .reduce((sum, h) => sum + Number(h.amount || 0), 0)
}

export function collectDownline(email, users, maxDepth = 8) {
  const root = String(email || '').toLowerCase()
  const byReferrer = new Map()
  for (const u of users || []) {
    const ref = String(u.referrerEmail || '').toLowerCase()
    if (!ref) continue
    if (!byReferrer.has(ref)) byReferrer.set(ref, [])
    byReferrer.get(ref).push(u)
  }
  const members = []
  let frontier = [root]
  const seen = new Set([root])
  for (let depth = 1; depth <= maxDepth; depth += 1) {
    const next = []
    for (const e of frontier) {
      for (const u of byReferrer.get(e) || []) {
        const m = String(u.email).toLowerCase()
        if (seen.has(m)) continue
        seen.add(m)
        members.push({ user: u, depth })
        next.push(m)
      }
    }
    frontier = next
    if (!frontier.length) break
  }
  return members
}

export function teamDepositTotal(email, users) {
  let total = 0
  for (const m of collectDownline(email, users)) {
    total += personalDeposited(m.user)
  }
  return Number(total.toFixed(2))
}

export function rankForUser(email, users) {
  return rankForTeamDeposits(teamDepositTotal(email, users))
}

export { GIFTS, RANKS }
