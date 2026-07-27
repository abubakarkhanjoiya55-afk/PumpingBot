/** Public invite link for a user's referral code. */
export function referralLink(code) {
  const ref = String(code || '').trim().toUpperCase()
  if (!ref) return ''
  // Prefer real domain when live; otherwise current host (preview/tunnel).
  let origin = 'https://voltix.exchange'
  try {
    const host = typeof window !== 'undefined' ? window.location.hostname : ''
    if (host && host !== 'voltix.exchange' && host !== 'www.voltix.exchange') {
      origin = window.location.origin
    }
  } catch {
    /* keep voltix.exchange */
  }
  return `${origin.replace(/\/$/, '')}/register?ref=${encodeURIComponent(ref)}`
}
