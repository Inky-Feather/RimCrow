import { t } from '../../shared/i18n.js'

export const getLocalizedWorkshopSortOptions = () => [
  { label: t('ui.workspace.workshop.sort.relevance', '最相关'), value: 'relevance' },
  { label: t('ui.workspace.workshop.sort.popular', '最热门'), value: 'popular', supportsDays: true, allowUntilNow: false },
  { label: t('ui.workspace.workshop.sort.subscriptions', '最多订阅'), value: 'subscriptions', supportsDays: true, allowUntilNow: true },
  { label: t('ui.workspace.workshop.sort.votes_up', '最多好评'), value: 'votes_up', supportsDays: true, allowUntilNow: true },
  { label: t('ui.workspace.workshop.sort.rating', '最高评分'), value: 'rating', supportsDays: true, allowUntilNow: true },
  { label: t('ui.workspace.workshop.sort.latest', '最近更新'), value: 'latest' },
  { label: t('ui.workspace.workshop.sort.created', '最近发布'), value: 'created' },
]

export const getLocalizedWorkshopDayRangeOptions = () => [
  { label: t('ui.workspace.workshop.days.7', '周内'), shortLabel: t('ui.workspace.workshop.days.7_short', '周内'), value: 7 },
  { label: t('ui.workspace.workshop.days.30', '月内'), shortLabel: t('ui.workspace.workshop.days.30_short', '月内'), value: 30 },
  { label: t('ui.workspace.workshop.days.90', '季内'), shortLabel: t('ui.workspace.workshop.days.90_short', '季内'), value: 90 },
  { label: t('ui.workspace.workshop.days.365', '年内'), shortLabel: t('ui.workspace.workshop.days.365_short', '年内'), value: 365 },
  { label: t('ui.workspace.workshop.days.0', '至今'), shortLabel: t('ui.workspace.workshop.days.0_short', '至今'), value: 0 },
]

export const getLocalizedWorkshopTextTargetOptions = () => [
  { label: t('ui.workspace.workshop.text_target.0', '标题与说明'), value: 0 },
  { label: t('ui.workspace.workshop.text_target.1', '仅标题'), value: 1 },
  { label: t('ui.workspace.workshop.text_target.2', '仅说明'), value: 2 },
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

export const getWorkshopSortOption = (sort = 'popular', options = getLocalizedWorkshopSortOptions()) => (
  options.find(option => option.value === sort) || options[0]
)

export const getEffectiveWorkshopSortOption = (sort = '', hasSearchText = false, options = getLocalizedWorkshopSortOptions()) => (
  getWorkshopSortOption(resolveWorkshopSortSelection(sort, hasSearchText), options)
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
  const sortOptions = getLocalizedWorkshopSortOptions()
  const dayOptions = getLocalizedWorkshopDayRangeOptions()
  const option = getEffectiveWorkshopSortOption(sort, hasSearchText, sortOptions)
  const sortLabel = option?.label || t('ui.workspace.workshop.sort.relevance', '最相关')
  const resolvedDays = resolveWorkshopDays(sort, days, hasSearchText)
  if (!supportsWorkshopDayRange(sort, hasSearchText)) return sortLabel
  if (resolvedDays === undefined) return t('ui.workspace.workshop.sort_state.until_now', '{sort}（至今）', { sort: sortLabel })
  const dayOption = dayOptions.find(item => item.value === resolvedDays)
  const fallbackDays = t('ui.workspace.workshop.sort_state.days', '{days}天', { days: resolvedDays })
  return t('ui.workspace.workshop.sort_state.with_days', '{sort}（{days}）', { sort: sortLabel, days: dayOption?.shortLabel || fallbackDays })
}
