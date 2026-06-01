const VERSION_META = {
  supported: {
    tone: 'success',
    label: '支持当前版本',
  },
  unknown: {
    tone: 'muted',
    label: '版本未注明',
  },
  unsupported: {
    tone: 'danger',
    label: '可能不支持当前版本',
  },
}

// 版本号统一截断到 `主版本.次版本`，避免比较时掺入补丁号噪音。
export const normalizeVersion = (value = '') => String(value || '').trim().slice(0, 3).toLowerCase()

export const normalizeVersions = (values = []) => [...new Set(
  (values || [])
    .map(normalizeVersion)
    .filter(Boolean)
)]

// 转成数字元组后，排序和比较都能复用同一套逻辑。
export const parseVersionTuple = (value = '') => {
  const normalized = normalizeVersion(value)
  if (!normalized) return [-1, -1]
  const parts = normalized.split('.')
  const major = Number(parts[0])
  const minor = Number(parts[1] || 0)
  return [Number.isFinite(major) ? major : -1, Number.isFinite(minor) ? minor : -1]
}

export const compareVersionTuple = (left = [-1, -1], right = [-1, -1]) => {
  const leftMajor = Number.isFinite(left?.[0]) ? left[0] : -1
  const rightMajor = Number.isFinite(right?.[0]) ? right[0] : -1
  if (leftMajor !== rightMajor) return leftMajor - rightMajor
  const leftMinor = Number.isFinite(left?.[1]) ? left[1] : -1
  const rightMinor = Number.isFinite(right?.[1]) ? right[1] : -1
  return leftMinor - rightMinor
}

// 排序元信息用于缺失安装候选的优先级选择。
export const getVersionSortMeta = (currentVersion = '', versions = []) => {
  const normalizedVersions = normalizeVersions(versions)
  const currentTuple = parseVersionTuple(currentVersion)
  const tuples = normalizedVersions
    .map(parseVersionTuple)
    .filter(tuple => tuple[0] >= 0)
    .sort(compareVersionTuple)
  if (tuples.length === 0) {
    return {
      tier: 1,
      maxTuple: [-1, -1],
      count: 0,
    }
  }
  const maxTuple = tuples[tuples.length - 1]
  const supportsCurrent = tuples.some(tuple => compareVersionTuple(tuple, currentTuple) === 0)
  const supportsHigher = currentTuple[0] >= 0 && compareVersionTuple(maxTuple, currentTuple) > 0
  return {
    tier: supportsCurrent ? 3 : supportsHigher ? 2 : 0,
    maxTuple,
    count: tuples.length,
  }
}

// 面向 UI 的简化状态，直接告诉调用方是否支持当前版本。
export const getVersionInfo = (currentVersion = '', versions = []) => {
  const normalizedVersions = normalizeVersions(versions)
  if (!normalizeVersion(currentVersion) || normalizedVersions.length === 0) {
    return { ...VERSION_META.unknown, versions: normalizedVersions }
  }
  return normalizedVersions.includes(normalizeVersion(currentVersion))
    ? { ...VERSION_META.supported, versions: normalizedVersions }
    : { ...VERSION_META.unsupported, versions: normalizedVersions }
}

export const buildVersionPreferenceScore = (
  currentVersion = '',
  versions = [],
  { preferWorkshop = false, preferReplacement = false } = {}
) => {
  const meta = getVersionSortMeta(currentVersion, versions)
  return (
    (meta.tier * 1000)
    + ((meta.maxTuple[0] + 1) * 100)
    + ((meta.maxTuple[1] + 1) * 10)
    + meta.count
    + (preferWorkshop ? 20 : 0)
    + (preferReplacement ? 10 : 0)
  )
}
