export const WORKSHOP_SORT_OPTIONS = [
  { label: '最相关', value: 'relevance' },
  { label: '最热门', value: 'popular', supportsDays: true, allowUntilNow: false },
  { label: '最多订阅', value: 'subscriptions', supportsDays: true, allowUntilNow: true },
  { label: '最多好评', value: 'votes_up', supportsDays: true, allowUntilNow: true },
  { label: '最高评分', value: 'rating', supportsDays: true, allowUntilNow: true },
  { label: '最近更新', value: 'latest' },
  { label: '最近发布', value: 'created' },
]

export const WORKSHOP_DAY_RANGE_OPTIONS = [
  { label: '周内', shortLabel: '周内', value: 7 },
  { label: '月内', shortLabel: '月内', value: 30 },
  { label: '季内', shortLabel: '季内', value: 90 },
  { label: '年内', shortLabel: '年内', value: 365 },
  { label: '至今', shortLabel: '至今', value: 0 },
]

export const WORKSHOP_TEXT_TARGET_OPTIONS = [
  { label: '标题与说明', value: 0 },
  { label: '仅标题', value: 1 },
  { label: '仅说明', value: 2 },
]

export const hasWorkshopSearchText = (tokens = []) => (
  (tokens || []).some(token => (
    !token?.exclude
    && (
      token.type === 'text'
      || token.key === 'text'
    )
    && String(token.value || '').trim()
  ))
)

export const resolveWorkshopSort = (sort = '', hasSearchText = false) => {
  const normalized = String(sort || '').trim()
  if (!normalized) return hasSearchText ? 'relevance' : 'popular'
  if (normalized === 'relevance' && !hasSearchText) return 'popular'
  return normalized
}

export const resolveWorkshopSortSelection = (sort = '', hasSearchText = false) => {
  const normalized = String(sort || '').trim()
  if (!normalized) return hasSearchText ? 'relevance' : 'popular'
  if (normalized === 'relevance' && !hasSearchText) return 'popular'
  return normalized
}

export const getWorkshopSortOption = (sort = 'popular') => (
  WORKSHOP_SORT_OPTIONS.find(option => option.value === sort) || WORKSHOP_SORT_OPTIONS[0]
)

export const getEffectiveWorkshopSortOption = (sort = '', hasSearchText = false) => (
  getWorkshopSortOption(resolveWorkshopSortSelection(sort, hasSearchText))
)

export const supportsWorkshopDayRange = (sort = '', hasSearchText = false) => (
  !!getEffectiveWorkshopSortOption(sort, hasSearchText)?.supportsDays
)

export const allowsWorkshopUntilNow = (sort = '', hasSearchText = false) => (
  !!getEffectiveWorkshopSortOption(sort, hasSearchText)?.allowUntilNow
)

export const resolveWorkshopDays = (sort = '', days = 7, hasSearchText = false) => {
  if (!supportsWorkshopDayRange(sort, hasSearchText)) return undefined
  const normalizedDays = Number(days)
  if (normalizedDays === 0) return allowsWorkshopUntilNow(sort, hasSearchText) ? undefined : 7
  return Number.isFinite(normalizedDays) && normalizedDays > 0 ? normalizedDays : 7
}

export const formatWorkshopSortStateLabel = (sort = '', days = 7, hasSearchText = false) => {
  const option = getEffectiveWorkshopSortOption(sort, hasSearchText)
  const sortLabel = option?.label || '最相关'
  const resolvedDays = resolveWorkshopDays(sort, days, hasSearchText)
  if (!supportsWorkshopDayRange(sort, hasSearchText)) return sortLabel
  if (resolvedDays === undefined) return `${sortLabel}（至今）`
  const dayOption = WORKSHOP_DAY_RANGE_OPTIONS.find(item => item.value === resolvedDays)
  return `${sortLabel}（${dayOption?.shortLabel || `${resolvedDays}天`}）`
}
