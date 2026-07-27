export const DEPOSIT_WALLETS = [
  {
    id: 'bnb',
    network: 'BNB (BEP20)',
    asset: 'USDT',
    address: '0xe6c8255c0382cbdf87032dc827fb3d65a603ee9',
    hint: 'Send only USDT on BNB Smart Chain',
  },
  {
    id: 'trc20',
    network: 'TRC20 (Tron)',
    asset: 'USDT',
    address: 'TAViWpUZ7FiDsoJWGn4R43AXjLD9C2bBHv',
    hint: 'Send only USDT-TRC20',
  },
  {
    id: 'arb',
    network: 'Arbitrum',
    asset: 'USDT',
    address: '0xe6c8255c0382cbdf87032dc827fb3d65a603ee9',
    hint: 'Send only USDT on Arbitrum One',
  },
]

export const WITHDRAW_NETWORKS = [
  { id: 'bnb', label: 'BNB (BEP20)', placeholder: '0x… BEP20 address' },
  { id: 'trc20', label: 'TRC20 (Tron)', placeholder: 'T… TRC20 address' },
  { id: 'arb', label: 'Arbitrum', placeholder: '0x… Arbitrum address' },
]

export function getWithdrawNetwork(id) {
  return WITHDRAW_NETWORKS.find((n) => n.id === id) || null
}

export const PLANS = [
  { id: 1, name: 'Plan 1', tag: 'Starter', min: 10, max: 100, yieldMin: 6, yieldMax: 8, color: '#3ecf8e' },
  { id: 2, name: 'Plan 2', tag: 'Growth', min: 100, max: 500, yieldMin: 7, yieldMax: 12, color: '#c9a227' },
  { id: 3, name: 'Plan 3', tag: 'Pro', min: 500, max: 2e3, yieldMin: 10, yieldMax: 15, color: '#e0b93c' },
  { id: 4, name: 'Plan 4', tag: 'Prime', min: 2e3, max: 1e4, yieldMin: 12, yieldMax: 20, color: '#f5d76e' },
]

export const DEFAULT_REF_PCT = 5

export function getPlan(id) {
  return PLANS.find((p) => p.id === Number(id)) || null
}

export function planForAmount(amount) {
  const n = Number(amount)
  if (!Number.isFinite(n)) return null
  for (let i = PLANS.length - 1; i >= 0; i -= 1) {
    const p = PLANS[i]
    if (n >= p.min && n <= p.max) return p
  }
  return null
}

export const WITHDRAW_LOCK_DAYS = 10
export const WITHDRAW_LOCK_MS = WITHDRAW_LOCK_DAYS * 24 * 60 * 60 * 1e3
/** Testing: lock is off (matches production UI copy). */
export const WITHDRAW_LOCK_ENABLED = false

export const SIGNUP_VOLT = 1000
export const REF_VOLT = 200

export const RANKS = [
  { id: 'scout', name: 'Scout', minTeam: 0, refPct: 5, yieldBonus: 0, tagline: 'Start building your Voltix team' },
  { id: 'bronze', name: 'Bronze', minTeam: 500, refPct: 6, yieldBonus: 0.15, tagline: 'First promoters · +0.15% stake bonus' },
  { id: 'silver', name: 'Silver', minTeam: 2e3, refPct: 7, yieldBonus: 0.3, tagline: 'Growing network · +0.30% stake bonus' },
  { id: 'gold', name: 'Gold', minTeam: 5e3, refPct: 8, yieldBonus: 0.5, tagline: 'Strong leaders · +0.50% stake bonus' },
  { id: 'platinum', name: 'Platinum', minTeam: 1e4, refPct: 9, yieldBonus: 0.75, tagline: 'Elite builders · +0.75% stake bonus' },
  { id: 'diamond', name: 'Diamond', minTeam: 2e4, refPct: 11, yieldBonus: 1, tagline: 'Top earners · +1.00% stake bonus' },
  { id: 'crown', name: 'Crown', minTeam: 4e4, refPct: 13, yieldBonus: 1.25, tagline: 'Empire tier · +1.25% stake bonus' },
  { id: 'legend', name: 'Legend', minTeam: 1e5, refPct: 15, yieldBonus: 2, tagline: 'Voltix legends · +2.00% stake bonus' },
]

export const GIFTS = [
  {
    id: 'tier10k',
    minTeam: 1e4,
    title: '$10,000 team milestone',
    giftLabel: 'Google Pixel 7',
    cashUsdt: 350,
    detail: 'Choose Google Pixel 7 or 350 USDT cash — unlock at $10,000 team deposits',
  },
  {
    id: 'tier20k',
    minTeam: 2e4,
    title: '$20,000 team milestone',
    giftLabel: 'Google Pixel 11',
    cashUsdt: 700,
    detail: 'Choose Google Pixel 11 or 700 USDT cash — unlock at $20,000 team deposits',
  },
  {
    id: 'tier40k',
    minTeam: 4e4,
    title: '$40,000 team milestone',
    giftLabel: 'iPhone 17 Pro',
    cashUsdt: 1500,
    detail: 'Choose iPhone 17 Pro or 1,500 USDT cash — unlock at $40,000 team deposits',
  },
]

export const ADMIN_EMAIL = 'admin@voltix.exchange'
export const ADMIN_PASSWORD = 'VoltixAdmin@2026'

export const KEYS = {
  users: 'voltix_users_v1',
  session: 'voltix_session_v1',
  adminSession: 'voltix_admin_session_v1',
  adminLogs: 'voltix_admin_logs_v1',
  withdrawRequests: 'voltix_withdraw_requests_v1',
  giftClaims: 'voltix_gift_claims_v1',
  depositRequests: 'voltix_deposit_requests_v1',
}

export const OLD_KEYS = {
  users: 'zaar_users_v1',
  session: 'zaar_session_v1',
  adminSession: 'zaar_admin_session_v1',
  adminLogs: 'zaar_admin_logs_v1',
  withdrawRequests: 'zaar_withdraw_requests_v1',
  giftClaims: 'zaar_gift_claims_v1',
  depositRequests: 'zaar_deposit_requests_v1',
}

export const EVENTS = {
  usersUpdated: 'voltix-users-updated',
  withdrawUpdated: 'voltix-withdraw-updated',
  giftUpdated: 'voltix-gift-updated',
  depositUpdated: 'voltix-deposit-updated',
}
