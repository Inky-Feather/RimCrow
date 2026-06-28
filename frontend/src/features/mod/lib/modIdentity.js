// 统一清洗后端偶尔返回的空值占位。
const normalizeNullableText = (value = '') => {
  const normalizedValue = String(value || '').trim()
  return normalizedValue && !['undefined', 'null', 'None'].includes(normalizedValue)
    ? normalizedValue
    : ''
}

export const STEAM_PACKAGE_SUFFIX = '_steam'
export const LOCAL_PACKAGE_SUFFIX = '_local'

/**
 * 包 ID 全部转成小写比较，避免同一模组因为大小写不同被视为多个对象。
 */
export const normalizePackageToken = (value = '') => String(value || '').trim().toLowerCase()

export const stripPackageTokenSuffix = (value = '') => {
  const normalizedToken = normalizePackageToken(value)
  if (normalizedToken.endsWith(STEAM_PACKAGE_SUFFIX)) {
    return normalizedToken.slice(0, -STEAM_PACKAGE_SUFFIX.length)
  }
  if (normalizedToken.endsWith(LOCAL_PACKAGE_SUFFIX)) {
    return normalizedToken.slice(0, -LOCAL_PACKAGE_SUFFIX.length)
  }
  return normalizedToken
}

export const normalizePackageId = (value = '') => stripPackageTokenSuffix(value)

export const isSteamPackageToken = (value = '') => normalizePackageToken(value).endsWith(STEAM_PACKAGE_SUFFIX)

export const buildSteamPackageToken = (value = '') => {
  const canonicalId = normalizePackageId(value)
  return canonicalId ? `${canonicalId}${STEAM_PACKAGE_SUFFIX}` : ''
}

export const parsePackageToken = (value = '') => {
  const normalizedToken = normalizePackageToken(value)
  const canonicalPackageId = normalizePackageId(normalizedToken)
  let sourcePreference = 'any'
  if (normalizedToken.endsWith(STEAM_PACKAGE_SUFFIX)) sourcePreference = 'steam'
  else if (normalizedToken.endsWith(LOCAL_PACKAGE_SUFFIX)) sourcePreference = 'local'
  return {
    rawToken: String(value || '').trim(),
    normalizedToken,
    canonicalPackageId,
    sourcePreference,
  }
}

export const normalizeWorkshopId = (value = '') => {
  // Steam 工坊 ID 允许保持原始数字字符串，不做大小写变换。
  return normalizeNullableText(value)
}

export const normalizeUrl = (value = '') => {
  // URL 这里只负责去空值和去占位串，不主动改写内容。
  return normalizeNullableText(value)
}

export const extractWorkshopId = (value = '') => {
  const text = String(value || '').trim()
  if (!text) return ''
  // 兼容直接传工坊 ID。
  if (/^\d{7,}$/.test(text)) return text
  // 兼容从 Steam 链接里提取 `?id=xxxx`。
  const match = text.match(/[?&]id=(\d{7,})/i)
  return match?.[1] || ''
}

export const buildWorkshopUrl = (workshopId = '') => {
  const normalizedWorkshopId = normalizeWorkshopId(workshopId)
  return normalizedWorkshopId
    ? `https://steamcommunity.com/sharedfiles/filedetails/?id=${normalizedWorkshopId}`
    : ''
}

const GIT_REPOSITORY_HOSTS = ['github.com', 'gitlab.com', 'gitgud.io']
const parseUrlHost = (value = '') => {
  try {
    return new URL(value).hostname.toLowerCase()
  } catch {
    return ''
  }
}

export const detectUrlSubtype = (url = '') => {
  const normalizedUrl = normalizeUrl(url).toLowerCase()
  if (!normalizedUrl) return 'other'
  if (GIT_REPOSITORY_HOSTS.includes(parseUrlHost(normalizedUrl))) return 'github'
  if (normalizedUrl.includes('ludeon.com') || normalizedUrl.includes('rimworldgame.com')) return 'official_forum'
  return 'other'
}

export const getInstallSourceKey = (source = {}) => {
  // 工坊来源优先使用 workshopId，普通链接来源则按 url 去重。
  if (source?.kind === 'workshop') {
    return `workshop:${normalizeWorkshopId(source.workshopId || source.workshop_id)}`
  }
  return `url:${normalizeUrl(source?.url)}`
}

export const normalizeInstallSource = (raw = {}, fallbackPackageId = '') => {
  const source = raw && typeof raw === 'object' ? raw : {}
  const packageId = normalizePackageId(source.packageId || source.package_id || fallbackPackageId)
  const normalizedUrl = normalizeUrl(source.url || source.sourceUrl || source.source_url)
  // workshopId 可以直接给，也可以从 url 中反推。
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
    const normalizedSource = normalizeInstallSource(
      source,
      source?.packageId || source?.package_id,
    )
    if (!normalizedSource) return
    sourceMap.set(getInstallSourceKey(normalizedSource), normalizedSource)
  })
  return [...sourceMap.values()]
}

/**
 * 对安装来源做“清洗 + 去重”一体化处理，避免重复遍历和重复归一化。
 */
export const normalizeInstallSources = (sources = [], fallbackPackageId = '') => {
  const sourceMap = new Map()

  ;(sources || []).forEach(source => {
    const normalizedSource = normalizeInstallSource(
      source,
      fallbackPackageId || source?.packageId || source?.package_id,
    )
    if (!normalizedSource) return
    sourceMap.set(getInstallSourceKey(normalizedSource), normalizedSource)
  })

  return [...sourceMap.values()]
}

export const dedupeNormalizedPackageIds = (values = []) => [...new Set(
  (values || [])
    .map(normalizePackageId)
    .filter(Boolean)
)]

// 用于组装显示列表时保持唯一值，避免上层反复手写 includes 判断。
export const pushUnique = (list, value) => {
  if (!value || list.includes(value)) return
  list.push(value)
}

// 展示名称去重时允许调用方传入自己的名称解析逻辑。
export const mapUniqueDisplayNames = (ids = [], resolveName = (value) => value) => [...new Set(
  (ids || [])
    .map(resolveName)
    .filter(Boolean)
)]
