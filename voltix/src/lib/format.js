export function formatUsd(n) {
  return `$${(Number(n) || 0).toLocaleString(undefined, { maximumFractionDigits: 2 })}`
}

export function formatVolt(n) {
  return `${(Number(n) || 0).toLocaleString()} VOLT`
}

export function formatDate(ts) {
  return ts
    ? new Date(ts).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
    : '—'
}
