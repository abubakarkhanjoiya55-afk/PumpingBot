/** Public invite link for a user's referral code. */

const BRANDED_ORIGIN = 'https://voltix.exchange'
const LIVE_ORIGIN = 'https://voltix-production-ecd8.up.railway.app'

/**
 * Default to the live Railway host until the branded domain serves Volt.
 * WhatsApp scrapes the invite host — never ship a link that still shows legacy branding.
 */
let inviteOrigin = LIVE_ORIGIN

export function referralOrigin() {
  return inviteOrigin
}

export function referralLink(code) {
  const ref = String(code || '').trim().toUpperCase()
  if (!ref) return ''
  return `${inviteOrigin}/register?ref=${encodeURIComponent(ref)}`
}

/** Prefer branded domain only when its HTML title is Volt. */
export async function refreshReferralOrigin() {
  try {
    const ctrl = new AbortController()
    const timer = setTimeout(() => ctrl.abort(), 4500)
    const html = await fetch(`${BRANDED_ORIGIN}/?v=${Date.now()}`, {
      signal: ctrl.signal,
      cache: 'no-store',
      mode: 'cors',
    }).then((r) => r.text())
    clearTimeout(timer)
    const isVolt = /<title>\s*Volt\s*<\/title>/i.test(html)
    inviteOrigin = isVolt ? BRANDED_ORIGIN : LIVE_ORIGIN
  } catch {
    inviteOrigin = LIVE_ORIGIN
  }
  return inviteOrigin
}
