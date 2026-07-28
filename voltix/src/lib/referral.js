/** Public invite link — always branded voltix.exchange (never Railway hostname). */

const ORIGIN = 'https://voltix.exchange'

export function referralOrigin() {
  return ORIGIN
}

export function referralLink(code) {
  const ref = String(code || '').trim().toUpperCase()
  if (!ref) return ''
  return `${ORIGIN}/register?ref=${encodeURIComponent(ref)}`
}

/** Kept for boot compatibility; origin is always branded. */
export async function refreshReferralOrigin() {
  return ORIGIN
}
