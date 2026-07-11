export function formatRelative(iso) {
  if (!iso) return '—'
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return '—'

  const now = new Date()
  const diffMs = date.getTime() - now.getTime()
  const diffSec = Math.round(diffMs / 1000)
  const abs = Math.abs(diffSec)

  const fmt = (n, unit) => `${n} ${unit}${n === 1 ? '' : 's'}`

  if (abs < 60) return diffSec <= 0 ? 'just now' : 'in <1m'
  if (abs < 3600) {
    const n = Math.round(abs / 60)
    return diffSec <= 0 ? `${fmt(n, 'min')} ago` : `in ${fmt(n, 'min')}`
  }
  if (abs < 86400) {
    const n = Math.round(abs / 3600)
    return diffSec <= 0 ? `${fmt(n, 'hour')} ago` : `in ${fmt(n, 'hour')}`
  }
  return date.toLocaleString(undefined, {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  })
}

export function formatTimestamp(iso) {
  if (!iso) return '—'
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return date.toLocaleString(undefined, {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  })
}
