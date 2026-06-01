import { nextTick, ref } from 'vue'

export function useModListDrag({
  props,
  appStore,
  modStore,
  vListRef,
  allowSort,
  internalListProxy,
  isSectionHeaderId,
  isSectionCollapsed,
  getSectionMemberIds,
  resolveInsertionIndex,
  normalizeId,
  normalizeCanonicalId,
}) {
  const listKey = ref(0)
  const isDragging = ref(false)
  const suppressNextDrop = ref(false)

  const finishDragSession = ({ suppressDrop = false } = {}) => {
    if (suppressDrop) {
      suppressNextDrop.value = true
    }
    isDragging.value = false
    modStore.isDraggingMod = false
  }

  const dispatchSyntheticDragEnd = () => {
    if (typeof document === 'undefined') return
    document.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true }))
    document.dispatchEvent(new Event('touchend', { bubbles: true, cancelable: true }))
    document.dispatchEvent(new Event('touchcancel', { bubbles: true, cancelable: true }))
  }

  const resetListInstance = async () => {
    await nextTick()
    listKey.value += 1
  }

  const refreshVirtualList = async () => {
    await nextTick()
    // 列表数据写回后只需要刷新虚拟列表尺寸缓存。
    // 旧实现通过反复切换排序状态触发软重绘，会让筛选、排序、依赖线和行代理全部额外重算。
    await vListRef.value?.refresh?.()
  }

  const cancelActiveDrag = async () => {
    if (!isDragging.value) return
    finishDragSession({ suppressDrop: true })
    dispatchSyntheticDragEnd()
    await resetListInstance()
  }

  // 开始拖拽时记录状态，供加载/卸载时取消拖拽使用。
  const startDrag = () => {
    isDragging.value = true
    modStore.isDraggingMod = true
  }

  // 更新子项的排序
  const updateChildren = async (e) => {
    if (suppressNextDrop.value || appStore.isLoading) {
      suppressNextDrop.value = false
      finishDragSession()
      return
    }
    finishDragSession()
    // 排序状态下禁止拖拽
    if (!allowSort.value) {
      // toast.warning("排序状态下禁止拖拽排序")
      return
    }
    // console.log("更新子项排序:", e)
    const oldIds = [...props.modelValue] // 原始数据（即 source of truth）
    // 这里的 newIds (脏数据) 仅用于计算相对位置，不参与数据重组
    const dirtyIds = Array.isArray(e.list) && e.list.length
      ? e.list.map(item => item.id)
      : internalListProxy.value.map(item => item.id)
    // dirtyIds 表示拖拽库视角下“当前可见顺序”的快照，
    // 它可能已经包含占位项或折叠代理项，所以只能用来换算位置，不能直接作为最终结果写回。
    // 1. 获取当前所有需要移动的 ID (处理分组或多选)
    let movingIds = []
    let preferSectionEnd = false
    if (e.item?.mod_ids?.length) {
      // 折叠标题会直接把整组 mod_ids 带进来，这里按整组移动即可。
      movingIds = [...e.item.mod_ids]
      // 顺便更新一下 Store 的选中状态，保持一致性
      modStore.selectMods([...movingIds], e.item?.id || e.key || null)
    } else {
      const draggedId = String(e.item?.id || e.key || dirtyIds[e.newIndex] || '').trim()
      if (draggedId && isSectionHeaderId(draggedId) && isSectionCollapsed(draggedId)) {
        // 某些情况下事件对象里没有完整的 mod_ids，这里再兜底按标题范围重建整组。
        movingIds = getSectionMemberIds(draggedId, oldIds)
        preferSectionEnd = true
        modStore.selectMods([...movingIds], draggedId)
      } else if (draggedId && isSectionHeaderId(draggedId)) {
        // 标题展开时只移动标题本身，不连带后续成员。
        movingIds = [draggedId]
        modStore.selectMods([draggedId], draggedId)
      }
      // 拖动的是列表项 -> 移动当前选中项
      if (movingIds.length === 0) {
        movingIds = [...modStore.selectedIds]
        const fallbackDraggedId = String(e.item?.id || e.key || dirtyIds[e.newIndex] || '').trim()
        // 如果拖拽的项不在选中列表中（比如未选中时直接拖），则把它加入
        if (!movingIds.includes(fallbackDraggedId) && fallbackDraggedId) {
          movingIds.push(fallbackDraggedId)
        }
      }
    }
    const movingIdSet = new Set(movingIds.map(id => normalizeId(id)))
    // 3. 构建新列表
    // 3.1 生成 BaseList：从原始列表中剔除所有移动项
    const baseList = oldIds.filter(id => !movingIdSet.has(normalizeId(id)))
    let correctedIndex = resolveInsertionIndex(baseList, dirtyIds, movingIds, e.newIndex, preferSectionEnd)
    // 联锁修正逻辑仍然保留在真实列表层面，确保标题分组拖拽不会破坏现有联锁语义。
    // 只有当插入点不在头部也不在尾部时才需要检查
    if (!preferSectionEnd && correctedIndex > 0 && correctedIndex < baseList.length) {
      const prevId = baseList[correctedIndex - 1]
      // 检查前一个元素是否有向后的联锁
      let curr = prevId
      while (true) {
        const mod = modStore.takeModById(curr)
        if (!mod || !mod.lock_next_mod) break
        const nextId = normalizeCanonicalId(mod.lock_next_mod)
        // 关键判断：
        // 如果 lock_next 指向的 Mod 就在 baseList 中，
        // 说明链条在 baseList 中是连续存在的。 必须跳过，不能插在它前面。
        const nextIndexInBase = baseList.findIndex(id => normalizeCanonicalId(id) === nextId)
        if (nextIndexInBase !== -1) {
          // 如果 nextId 就在当前插入点或其后方，说明插在了链条中间
          // 将插入点顺延到 nextId 的后面
          if (nextIndexInBase >= correctedIndex) {
            correctedIndex = nextIndexInBase + 1
            curr = baseList[nextIndexInBase] // 继续检查链条中的下一个真实列表项
          } else {
            // nextId 在更前面？说明链条已经乱序了，或者逻辑没问题，停止修正
            break
          }
        } else {
          // lock_next 指向的元素不在 baseList 中（可能在 movingIds 里，或者被删了）
          // 这种情况下，链条已经断了，插入在这里是安全的
          break
        }
      }
    }

    // 3.2 插入：在计算出的纯净位置插入移动项
    const finalList = [...baseList]
    finalList.splice(correctedIndex, 0, ...movingIds)

    // 4. 检查是否有变化
    if (JSON.stringify(finalList) !== JSON.stringify(oldIds)) {
      const isCrossListMove = e.event.target !== e.event.from
      await modStore.runListHistoryTransaction({
        type: isCrossListMove ? 'move-between-lists' : 'reorder-list',
        label: isCrossListMove ? `移动 ${movingIds.length} 项到 ${props.title}` : `调整 ${props.title} 列表顺序`,
        trackedModIds: movingIds
      }, async () => {
        // 同步 Store（移除旧位置的引用等，虽然这里逻辑上已经是新的了）
        modStore.removeIdsOnAllList(movingIds)
        modStore.setListIds(props.listId, finalList)
        // 更新移动时间
        modStore.takeModListByIds(movingIds).forEach(mod => {
          mod.last_moved_time = Date.now()
          if (isCrossListMove) {
            mod.last_active_time = Date.now()
          }
        })
      })
      await refreshVirtualList()
    }
  }

  return {
    listKey,
    isDragging,
    finishDragSession,
    dispatchSyntheticDragEnd,
    refreshVirtualList,
    cancelActiveDrag,
    startDrag,
    updateChildren,
  }
}
