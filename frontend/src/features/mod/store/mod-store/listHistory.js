import { computed, ref } from 'vue'

const LIST_HISTORY_LIMIT = 100

export const useModListHistory = ({
  activeIds,
  inactiveIds,
  tempIds,
  savedActiveIds,
  activeLoadModifyTime,
  activeLoadVersionToken,
  dataVersion,
  normalizeHistoryModIds,
  resolveStoredMod,
} = {}) => {
  // 列表历史（仅当前会话内存态）
  const listHistoryUndoStack = ref([])
  const listHistoryRedoStack = ref([])
  const isApplyingListHistory = ref(false)

  const listHistoryTotal = computed(() => listHistoryUndoStack.value.length + listHistoryRedoStack.value.length)
  const listHistoryPosition = computed(() => listHistoryUndoStack.value.length)
  const canUndoListHistory = computed(() => listHistoryUndoStack.value.length > 0)
  const canRedoListHistory = computed(() => listHistoryRedoStack.value.length > 0)

  // 创建模组时间快照
  const createModTimeSnapshot = (ids = []) => {
    const snapshot = {}
    normalizeHistoryModIds(ids).forEach(id => {
      const mod = resolveStoredMod(id)
      if (!mod) return
      snapshot[id] = {
        last_active_time: mod.last_active_time || 0,
        last_moved_time: mod.last_moved_time || 0
      }
    })
    return snapshot
  }

  // 创建列表历史记录快照
  const createListHistorySnapshot = (trackedModIds = []) => ({
    activeIds: [...activeIds.value],
    inactiveIds: [...inactiveIds.value],
    tempIds: [...tempIds.value],
    savedActiveIds: [...savedActiveIds.value],
    activeLoadModifyTime: activeLoadModifyTime.value || 0,
    activeLoadVersionToken: { ...(activeLoadVersionToken.value || {}) },
    modTimes: createModTimeSnapshot(trackedModIds)
  })

  // 捕获列表历史记录快照
  const captureListHistorySnapshot = (trackedModIds = []) => createListHistorySnapshot(trackedModIds)

  // 恢复模组时间字段，配合列表撤销/重做还原最近启用和移动时间。
  const restoreModTimeSnapshot = (modTimes = {}) => {
    Object.entries(modTimes || {}).forEach(([id, times]) => {
      const mod = resolveStoredMod(id)
      if (!mod) return
      mod.last_active_time = times?.last_active_time || 0
      mod.last_moved_time = times?.last_moved_time || 0
    })
  }

  // 清空当前会话的列表历史
  const clearListHistory = () => {
    listHistoryUndoStack.value = []
    listHistoryRedoStack.value = []
  }

  const isSameArray = (left = [], right = []) => {
    if (left.length !== right.length) return false
    return left.every((item, index) => item === right[index])
  }

  // 检查列表历史记录快照是否发生变化
  const didListHistorySnapshotChange = (before, after) => {
    if (!before || !after) return false
    if (!isSameArray(before.activeIds, after.activeIds)) return true
    if (!isSameArray(before.inactiveIds, after.inactiveIds)) return true
    if (!isSameArray(before.tempIds, after.tempIds)) return true
    if (!isSameArray(before.savedActiveIds, after.savedActiveIds)) return true
    if (JSON.stringify(before.activeLoadVersionToken || {}) !== JSON.stringify(after.activeLoadVersionToken || {})) return true
    return (before.activeLoadModifyTime || 0) !== (after.activeLoadModifyTime || 0)
  }

  // 推送列表历史记录条目
  const pushListHistoryEntry = (entry) => {
    listHistoryUndoStack.value.push(entry)
    if (listHistoryUndoStack.value.length > LIST_HISTORY_LIMIT) {
      listHistoryUndoStack.value.shift()
    }
    listHistoryRedoStack.value = []
  }

  // 记录列表历史记录
  const recordListHistory = ({ before, trackedModIds = [], type = 'list-edit', label = '' } = {}) => {
    if (isApplyingListHistory.value || !before) return false
    const after = createListHistorySnapshot(trackedModIds)
    if (!didListHistorySnapshotChange(before, after)) return false
    pushListHistoryEntry({
      type,
      label,
      at: Date.now(),
      before,
      after
    })
    return true
  }

  // 运行列表历史记录事务
  const runListHistoryTransaction = async (meta = {}, handler) => {
    if (typeof handler !== 'function') return false
    if (isApplyingListHistory.value) {
      return await handler()
    }
    const trackedModIds = normalizeHistoryModIds(meta.trackedModIds || [])
    const before = createListHistorySnapshot(trackedModIds)
    const result = await handler()
    recordListHistory({ ...meta, before, trackedModIds })
    return result
  }

  // 恢复列表历史记录
  const restoreListHistorySnapshot = (snapshot) => {
    if (!snapshot) return false
    activeIds.value = [...(snapshot.activeIds || [])]
    inactiveIds.value = [...(snapshot.inactiveIds || [])]
    tempIds.value = [...(snapshot.tempIds || [])]
    savedActiveIds.value = [...(snapshot.savedActiveIds || [])]
    activeLoadModifyTime.value = snapshot.activeLoadModifyTime || 0
    activeLoadVersionToken.value = { ...(snapshot.activeLoadVersionToken || {}) }
    restoreModTimeSnapshot(snapshot.modTimes)
    dataVersion.value++
    return true
  }

  // 撤销列表历史记录
  const undoListHistory = () => {
    const entry = listHistoryUndoStack.value.pop()
    if (!entry) return false
    isApplyingListHistory.value = true
    try {
      restoreListHistorySnapshot(entry.before)
      listHistoryRedoStack.value.push(entry)
      return true
    } finally {
      isApplyingListHistory.value = false
    }
  }

  // 重做列表历史记录
  const redoListHistory = () => {
    const entry = listHistoryRedoStack.value.pop()
    if (!entry) return false
    isApplyingListHistory.value = true
    try {
      restoreListHistorySnapshot(entry.after)
      listHistoryUndoStack.value.push(entry)
      return true
    } finally {
      isApplyingListHistory.value = false
    }
  }

  return {
    listHistoryUndoStack,
    listHistoryRedoStack,
    isApplyingListHistory,
    listHistoryTotal,
    listHistoryPosition,
    canUndoListHistory,
    canRedoListHistory,
    captureListHistorySnapshot,
    clearListHistory,
    runListHistoryTransaction,
    recordListHistory,
    undoListHistory,
    redoListHistory,
  }
}
