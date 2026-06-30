import { normalizeWorkshopId } from '../../mod/lib/modIdentity'

export const MATRIX_FILTER_STATE_OPTIONS = [
  { label: '显示所有', value: 'default' },
  { label: '仅看新增', value: 'new' },
  { label: '仅看变更', value: 'change' },
  { label: '仅看可更新', value: 'update' },
  { label: '仅看跨库同项', value: 'same' },
  { label: '仅看同库冲突', value: 'conflict' },
  { label: '仅看替代项', value: 'replace' },
  { label: '仅看已禁用', value: 'disabled' },
  { label: '仅看缺失', value: 'missing' },
  { label: '仅看已删除', value: 'deleted' },
]

export const isMatrixModDeleted = (mod) => !!mod?.is_deleted || mod?.state === 'deleted'
export const isMatrixModMissing = (mod) => !!mod?.is_missing && !isMatrixModDeleted(mod)
export const isMatrixModUnavailable = (mod) => !!mod?.is_unavailable || isMatrixModMissing(mod) || isMatrixModDeleted(mod)

export const isMatrixModAvailable = (mod) => !!mod?.path && !isMatrixModUnavailable(mod)

export const getMatrixReplacementTargets = (mod, workspaceStore) => {
  const replacementWorkshopId = normalizeWorkshopId(mod?.replacement?.new_workshop_id)
  if (!replacementWorkshopId || !workspaceStore?.installedAllIds?.has(replacementWorkshopId)) {
    return []
  }

  const allMods = [
    ...(workspaceStore?.librariesMods?.workshop || []),
    ...(workspaceStore?.librariesMods?.self || []),
    ...(workspaceStore?.librariesMods?.local || []),
  ]

  return allMods.filter(item =>
    item?.path_hash &&
    item.path_hash !== mod?.path_hash &&
    isMatrixModAvailable(item) &&
    normalizeWorkshopId(item.workshop_id) === replacementWorkshopId
  )
}

export const normalizeMatrixTimestamp = (value) => {
  if (value === null || value === undefined || value === '' || value === '0') return 0
  if (typeof value === 'number') {
    if (!Number.isFinite(value) || value <= 0) return 0
    return value < 1e11 ? Math.trunc(value * 1000) : Math.trunc(value)
  }

  const raw = String(value).trim()
  if (!raw) return 0
  if (/^\d+$/.test(raw)) {
    const numeric = Number(raw)
    if (!Number.isFinite(numeric) || numeric <= 0) return 0
    return numeric < 1e11 ? Math.trunc(numeric * 1000) : Math.trunc(numeric)
  }

  const parsed = Date.parse(raw)
  return Number.isFinite(parsed) ? parsed : 0
}

export const getMatrixMeaningfulChangeTime = (mod = {}) => Math.max(
  normalizeMatrixTimestamp(mod?.download_status?.download_time),
  normalizeMatrixTimestamp(mod?.steam_status?.installed_version_time),
  normalizeMatrixTimestamp(mod?.file_modify_time),
  normalizeMatrixTimestamp(mod?.file_create_time),
)

export const getMatrixItemState = (mod, lastPlayedTime = 0, workspaceStore, lastRunTime = 0) => {
  const normalizedLastPlayedTime = Number(lastPlayedTime || 0)
  const hasLastPlayedTime = normalizedLastPlayedTime > 0
  const normalizedLastRunTime = Number(lastRunTime || 0)
  const referenceTime = hasLastPlayedTime ? normalizedLastPlayedTime : normalizedLastRunTime
  const hasReferenceTime = referenceTime > 0
  const createTime = normalizeMatrixTimestamp(mod?.file_create_time)
  const lastChangeTime = getMatrixMeaningfulChangeTime(mod)

  const sameTargets = workspaceStore?.getMatrixSameItems?.(mod?.path_hash) || []
  const conflictTargets = workspaceStore?.getMatrixConflictItems?.(mod?.path_hash) || []
  const replacementTargets = getMatrixReplacementTargets(mod, workspaceStore)

  const isNew = hasReferenceTime && createTime > referenceTime
  const isChange = hasReferenceTime && !isNew && lastChangeTime > referenceTime
  const isUpdate = !!(mod?.has_update || mod?.steam_status?.needs_update)
  const isSame = sameTargets.length > 0
  const isConflict = conflictTargets.length > 0
  const isReplace = replacementTargets.length > 0
  const isDisabled = !!mod?.disabled
  const isDeleted = isMatrixModDeleted(mod)
  const isMissing = isMatrixModMissing(mod)
  const isWorkshopUnavailable = mod?.workshop_online_status === 'unavailable'

  return {
    sameTargets,
    conflictTargets,
    replacementTargets,
    statusMap: {
      new: isNew,
      change: isChange,
      update: isUpdate,
      same: isSame,
      conflict: isConflict,
      replace: isReplace,
      disabled: isDisabled,
      missing: isMissing,
      deleted: isDeleted,
    },
    isNew,
    isChange,
    isUpdate,
    isSame,
    isConflict,
    isReplace,
    isDisabled,
    isMissing,
    isDeleted,
    isWorkshopUnavailable,
  }
}

export const matchesMatrixFilter = (state, filterState = 'default') => {
  if (filterState === 'default') return true
  return !!state?.statusMap?.[filterState]
}
