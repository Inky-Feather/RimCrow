export const normalizeTranslationSourceDetection = (value = {}) => {
  const source = value && typeof value === 'object' ? value : {}
  const mode = String(source.mode || '').toLowerCase() === 'and' ? 'and' : 'or'
  const terms = Array.isArray(source.terms)
    ? source.terms.map(item => String(item || '').trim()).filter(Boolean)
    : []
  return {
    enabled: !!source.enabled,
    mode,
    terms,
  }
}

export const escapeRegexLiteral = (value = '') => (
  String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
)

export const matchesTranslationSourceDetection = (text = '', detection = {}) => {
  const config = normalizeTranslationSourceDetection(detection)
  const sourceText = String(text || '')
  if (!config.enabled || !sourceText || config.terms.length === 0) return false
  const matches = config.terms.map((term) => new RegExp(escapeRegexLiteral(term), 'i').test(sourceText))
  return config.mode === 'and' ? matches.every(Boolean) : matches.some(Boolean)
}
