export const normalizePackageId = (value = '') => String(value || '').trim().toLowerCase()

export const normalizeWorkshopId = (value = '') => {
  const wid = String(value || '').trim()
  return wid && wid !== 'undefined' && wid !== 'null' && wid !== 'None' ? wid : ''
}

export const normalizeUrl = (value = '') => {
  const url = String(value || '').trim()
  return url && url !== 'undefined' && url !== 'null' && url !== 'None' ? url : ''
}

export const extractWorkshopId = (value = '') => {
  const text = String(value || '').trim()
  if (!text) return ''
  if (/^\d{7,}$/.test(text)) return text
  const match = text.match(/[?&]id=(\d{7,})/i)
  return match?.[1] || ''
}

export const buildWorkshopUrl = (workshopId = '') => {
  const normalizedWorkshopId = normalizeWorkshopId(workshopId)
  return normalizedWorkshopId
    ? `https://steamcommunity.com/sharedfiles/filedetails/?id=${normalizedWorkshopId}`
    : ''
}

export const detectUrlSubtype = (url = '') => {
  const normalizedUrl = normalizeUrl(url).toLowerCase()
  if (!normalizedUrl) return 'other'
  if (normalizedUrl.includes('github.com')) return 'github'
  if (normalizedUrl.includes('ludeon.com') || normalizedUrl.includes('rimworldgame.com')) return 'official_forum'
  return 'other'
}

export const getInstallSourceKey = (source = {}) => {
  if (source?.kind === 'workshop') {
    return `workshop:${normalizeWorkshopId(source.workshopId || source.workshop_id)}`
  }
  return `url:${normalizeUrl(source?.url)}`
}

export const normalizeInstallSource = (raw = {}, fallbackPackageId = '') => {
  const source = raw && typeof raw === 'object' ? raw : {}
  const packageId = normalizePackageId(source.packageId || source.package_id || fallbackPackageId)
  const normalizedUrl = normalizeUrl(source.url || source.sourceUrl || source.source_url)
  const workshopId = normalizeWorkshopId(
    source.workshopId
    || source.workshop_id
    || extractWorkshopId(normalizedUrl)
  )
  const supportedVersions = Array.isArray(source.supportedVersions || source.supported_versions)
    ? [...new Set((source.supportedVersions || source.supported_versions).map(value => String(value || '').trim()).filter(Boolean))]
    : []

  if (workshopId) {
    return {
      kind: 'workshop',
      packageId,
      workshopId,
      url: buildWorkshopUrl(workshopId),
      title: String(source.title || source.name || packageId || workshopId).trim(),
      supportedVersions,
      sourceOrigin: String(source.sourceOrigin || source.source_origin || '').trim() || 'unknown',
      isReplacement: !!source.isReplacement,
      urlSubtype: 'workshop',
    }
  }

  if (!normalizedUrl) return null
  return {
    kind: 'url',
    packageId,
    url: normalizedUrl,
    title: String(source.title || source.name || packageId || normalizedUrl).trim(),
    supportedVersions,
    sourceOrigin: String(source.sourceOrigin || source.source_origin || '').trim() || 'unknown',
    isReplacement: !!source.isReplacement,
    urlSubtype: detectUrlSubtype(normalizedUrl),
  }
}

export const dedupeInstallSources = (sources = []) => {
  const sourceMap = new Map()
  ;(sources || []).forEach(source => {
    const normalizedSource = normalizeInstallSource(source, source?.packageId || source?.package_id)
    if (!normalizedSource) return
    sourceMap.set(getInstallSourceKey(normalizedSource), normalizedSource)
  })
  return [...sourceMap.values()]
}

export const normalizeInstallSources = (sources = [], fallbackPackageId = '') => (
  dedupeInstallSources(
    (sources || [])
      .map(source => normalizeInstallSource(source, fallbackPackageId || source?.packageId || source?.package_id))
      .filter(Boolean)
  )
)

export const dedupeNormalizedPackageIds = (values = []) => [...new Set(
  (values || [])
    .map(normalizePackageId)
    .filter(Boolean)
)]

export const pushUnique = (list, value) => {
  if (!value || list.includes(value)) return
  list.push(value)
}

export const mapUniqueDisplayNames = (ids = [], resolveName = (value) => value) => [...new Set(
  (ids || [])
    .map(resolveName)
    .filter(Boolean)
)]
