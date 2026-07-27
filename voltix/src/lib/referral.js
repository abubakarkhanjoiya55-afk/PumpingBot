/** Public invite link for a user's referral code. */
export function referralLink(code) {
  const ref = String(code || '').trim().toUpperCase()
  if (!ref) return ''
  // Always use the branded domain in invite links.
  const origin = 'https://voltix.exchange'
  return `${origin}/register?ref=${encodeURIComponent(ref)}`
}
