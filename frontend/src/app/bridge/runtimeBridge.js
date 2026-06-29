export const getRuntimeMode = () => String(window.__APP_RUNTIME_MODE__ || 'desktop')

export const isBrowserRuntime = () => getRuntimeMode() === 'browser'

export const getBrowserApiBaseUrl = () => String(window.__APP_API_BASE_URL__ || '').replace(/\/$/, '')

export const buildManagedSubBrowserUrl = (url, title = 'RimCrow') => {
  const normalizedUrl = String(url || '').trim()
  if (!normalizedUrl) return ''

  const baseUrl = getBrowserApiBaseUrl()
  if (!isBrowserRuntime() || !baseUrl) {
    return normalizedUrl
  }

  try {
    const parsed = new URL(normalizedUrl)
    if (['http:', 'https:'].includes(parsed.protocol) && parsed.hostname.endsWith('steamcommunity.com')) {
      return `${baseUrl}/workshop-view?url=${encodeURIComponent(normalizedUrl)}`
    }
  } catch {}

  const helperTitle = String(title || 'RimCrow').trim() || 'RimCrow'
  return `${baseUrl}/sub-browser-helper?url=${encodeURIComponent(normalizedUrl)}&title=${encodeURIComponent(helperTitle)}`
}

export const openManagedSubBrowserUrl = (url, title = 'RimCrow') => {
  const targetUrl = buildManagedSubBrowserUrl(url, title)
  if (!targetUrl) return ''
  window.open(targetUrl, '_blank', 'noopener,noreferrer')
  return targetUrl
}
