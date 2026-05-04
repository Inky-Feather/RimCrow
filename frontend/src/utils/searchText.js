export const escapeHtml = (value = '') => String(value)
  .replace(/&/g, '&amp;')
  .replace(/</g, '&lt;')
  .replace(/>/g, '&gt;')
  .replace(/"/g, '&quot;')
  .replace(/'/g, '&#39;')

export function buildSearchRegExp(query, { useRegex = false, caseSensitive = false } = {}) {
  const source = String(query || '')
  if (!source) return null
  const flags = caseSensitive ? 'g' : 'gi'
  if (useRegex) {
    try {
      return new RegExp(source, flags)
    } catch {
      return null
    }
  }
  return new RegExp(source.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), flags)
}
