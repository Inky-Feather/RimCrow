import { normalizeWorkshopId } from '../../../utils/modIdentity'

export const MATRIX_FILTER_STATE_OPTIONS = [
  { label: '显示所有', value: 'default' },
  { label: '仅看新增', value: 'new' },
  { label: '仅看变更', value: 'change' },
  { label: '仅看可更新', value: 'update' },
  { label: '仅看跨库同项', value: 'same' },
  { label: '仅看同库冲突', value: 'conflict' },
  { label: '仅看替代项', value: 'replace' },
  { label: '仅看已禁用', value: 'disabled' },
  { label: '仅看已删除', value: 'deleted' },
  { label: '仅看缺失', value: 'missing' },
]

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
    !!item.path &&
    !item.is_missing &&
    normalizeWorkshopId(item.workshop_id) === replacementWorkshopId
  )
}

export const getMatrixItemState = (mod, lastPlayedTime = 0, workspaceStore) => {
  const normalizedLastPlayedTime = Number(lastPlayedTime || 0)
  const hasLastPlayedTime = normalizedLastPlayedTime > 0
  const createTime = Number(mod?.file_create_time || 0)
  const lastSyncTime = Number(mod?.steam_status?.time_last_sync || 0)
  const modifyTime = Number(mod?.file_modify_time || 0)
  const lastChangeTime = Math.max(lastSyncTime, modifyTime)

  const sameTargets = workspaceStore?.getMatrixSameItems?.(mod?.path_hash) || []
  const conflictTargets = workspaceStore?.getMatrixConflictItems?.(mod?.path_hash) || []
  const replacementTargets = getMatrixReplacementTargets(mod, workspaceStore)

  const isNew = hasLastPlayedTime && createTime > normalizedLastPlayedTime
  const isChange = hasLastPlayedTime && !isNew && lastChangeTime > normalizedLastPlayedTime
  const isUpdate = !!(mod?.has_update || mod?.steam_status?.needs_update)
  const isSame = sameTargets.length > 0
  const isConflict = conflictTargets.length > 0
  const isReplace = replacementTargets.length > 0
  const isDisabled = !!mod?.disabled
  const isMissing = !!mod?.is_missing
  const isDeleted = !isMissing && !mod?.path
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
      deleted: isDeleted,
      missing: isMissing,
    },
    isNew,
    isChange,
    isUpdate,
    isSame,
    isConflict,
    isReplace,
    isDisabled,
    isDeleted,
    isMissing,
    isWorkshopUnavailable,
  }
}

export const matchesMatrixFilter = (state, filterState = 'default') => {
  if (filterState === 'default') return true
  return !!state?.statusMap?.[filterState]
}
