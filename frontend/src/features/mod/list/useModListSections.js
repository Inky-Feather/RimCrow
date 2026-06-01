import { computed, nextTick, ref, watch } from 'vue'
import { isSectionHeaderTitle } from '../../../shared/lib/common'

export function useModListSections({
  props,
  appStore,
  modStore,
  profileStore,
  displayList,
  allowSort,
  normalizeId,
}) {
  const collapsedSectionIds = ref([])

  // 标题分组功能只允许在 active 列表开启，避免影响其它列表原本的拖拽/显示语义。
  const sectionFeatureEnabled = computed(() => props.listId === 'active' && !!appStore.settings.ui.enable_active_section_collapse)
  const isSectionHeaderName = (value) => isSectionHeaderTitle(value)
  const isSectionHeaderModId = (id) => {
    const mod = modStore.takeModById(id)
    return isSectionHeaderName(mod?.alias_name) || isSectionHeaderName(mod?.name)
  }
  const isSectionHeaderId = (id) => sectionFeatureEnabled.value && isSectionHeaderModId(id)
  const sectionHeaderIds = computed(() => {
    if (!sectionFeatureEnabled.value) return []
    return props.modelValue.filter(id => isSectionHeaderModId(id))
  })
  const canUseSectionCollapse = computed(() => sectionFeatureEnabled.value && allowSort.value)

  // collapsedSectionIds 是“当前组件内正在使用的折叠状态源”；
  // activeCollapsedSectionIds / collapsedSectionIdSet 则负责把它清洗成当前列表仍然有效的标题集合。
  const activeCollapsedSectionIds = computed(() => {
    const validIds = new Set(sectionHeaderIds.value.map(id => normalizeId(id)))
    return collapsedSectionIds.value.filter(id => validIds.has(id))
  })
  const collapsedSectionIdSet = computed(() => new Set(activeCollapsedSectionIds.value))
  const hasSectionHeaders = computed(() => sectionHeaderIds.value.length > 0)

  // 只有在完成一次“历史状态恢复 / 默认折叠应用”之后，才允许把状态重新写回本地存储，
  // 这样可以避免初次挂载时用空数组覆盖已有状态。
  const sectionStateReady = ref(false)
  // 折叠状态按“环境 + 列表”隔离保存，避免不同 Profile 之间串状态。
  const sectionStateStorageKey = computed(() => {
    if (!sectionFeatureEnabled.value) return ''
    const profileId = profileStore.currentProfileId || appStore.settings.current_profile_id || 'default'
    return `rmm:collapsed-sections:${profileId}:${props.listId}`
  })

  const sectionChildCountMap = computed(() => {
    const map = new Map()
    let currentSectionId = ''
    props.modelValue.forEach(id => {
      if (isSectionHeaderId(id)) {
        currentSectionId = normalizeId(id)
        if (!map.has(currentSectionId)) map.set(currentSectionId, 0)
        return
      }
      if (!currentSectionId) return
      map.set(currentSectionId, (map.get(currentSectionId) || 0) + 1)
    })
    return map
  })
  const getSectionChildCount = (id) => sectionChildCountMap.value.get(normalizeId(id)) || 0
  const isSectionCollapsed = (id) => collapsedSectionIdSet.value.has(normalizeId(id))

  // 所有外部传入的标题 ID（菜单、多选、持久化恢复）都会先经过这一层标准化，
  // 只保留“当前列表里真实存在的标题项”，避免旧数据或跨列表 ID 混入。
  const normalizeSectionIds = (ids) => {
    const validIds = new Set(sectionHeaderIds.value.map(id => normalizeId(id)))
    return [...new Set(ids.map(id => normalizeId(id)).filter(id => validIds.has(id)))]
  }

  // 读取本地持久化的折叠状态；失败时返回 null，交给上层走默认折叠分支。
  const getPersistedSectionIds = () => {
    if (!sectionStateStorageKey.value) return null
    try {
      const raw = window.localStorage?.getItem(sectionStateStorageKey.value)
      if (!raw) return null
      const parsed = JSON.parse(raw)
      return Array.isArray(parsed) ? parsed : null
    } catch {
      return null
    }
  }

  // 把“当前有效折叠状态”写入本地。这里不抛错，避免本地存储异常影响主流程。
  const persistSectionIds = (ids = activeCollapsedSectionIds.value) => {
    if (!sectionStateStorageKey.value) return
    try {
      window.localStorage?.setItem(sectionStateStorageKey.value, JSON.stringify(ids))
    } catch {
    }
  }

  // 单个标题项的直接折叠/展开入口，供标题按钮和双击操作复用。
  const toggleSection = (id) => {
    if (!canUseSectionCollapse.value || getSectionChildCount(id) === 0) return
    const key = normalizeId(id)
    if (collapsedSectionIdSet.value.has(key)) {
      collapsedSectionIds.value = collapsedSectionIds.value.filter(sectionId => sectionId !== key)
      return
    }
    collapsedSectionIds.value = [...activeCollapsedSectionIds.value, key]
  }

  // 批量展开入口，主要给右键菜单使用。
  const expandSections = (ids) => {
    const targetIds = normalizeSectionIds(ids)
    if (!targetIds.length) return
    collapsedSectionIds.value = collapsedSectionIds.value.filter(id => !targetIds.includes(id))
  }

  // 批量折叠入口，主要给右键菜单和默认折叠逻辑使用。
  const collapseSections = (ids) => {
    if (!canUseSectionCollapse.value) return
    const targetIds = normalizeSectionIds(ids)
      .filter(id => getSectionChildCount(id) > 0)
    if (!targetIds.length) return
    collapsedSectionIds.value = [...new Set([...activeCollapsedSectionIds.value, ...targetIds])]
  }

  // 统一的“折叠状态初始化”入口：
  // 1. 若功能关闭或当前列表没有标题项，则清空；
  // 2. 若存在历史保存状态，则优先恢复历史状态；
  // 3. 若没有历史状态，再根据“默认折叠”决定初始状态。
  const hydrateSectionState = () => {
    if (!sectionFeatureEnabled.value) {
      collapsedSectionIds.value = []
      sectionStateReady.value = false
      return
    }
    if (sectionHeaderIds.value.length === 0) {
      collapsedSectionIds.value = []
      sectionStateReady.value = false
      return
    }
    const persistedIds = getPersistedSectionIds()
    if (persistedIds) {
      collapsedSectionIds.value = normalizeSectionIds(persistedIds)
        .filter(id => getSectionChildCount(id) > 0)
    } else if (appStore.settings.ui.default_collapse_active_sections) {
      collapsedSectionIds.value = normalizeSectionIds(sectionHeaderIds.value)
        .filter(id => getSectionChildCount(id) > 0)
    } else {
      collapsedSectionIds.value = []
    }
    sectionStateReady.value = true
    persistSectionIds()
  }

  // 真正渲染、框选、键盘导航、依赖线同步都基于 visibleList，而不是完整 displayList。
  const visibleList = computed(() => {
    if (!canUseSectionCollapse.value || !hasSectionHeaders.value) return displayList.value
    let hideFollowingMods = false
    return displayList.value.filter(id => {
      if (isSectionHeaderId(id)) {
        hideFollowingMods = isSectionCollapsed(id)
        return true
      }
      return !hideFollowingMods
    })
  })

  const findOwningSectionId = (targetId) => {
    let currentSectionId = ''
    for (const id of displayList.value) {
      if (isSectionHeaderId(id)) currentSectionId = id
      if (normalizeId(id) === normalizeId(targetId)) {
        return currentSectionId || ''
      }
    }
    return ''
  }

  // 搜索定位命中折叠组内成员时，先自动展开所属标题组，再滚动过去。
  const revealCollapsedSectionFor = async (targetId) => {
    if (!canUseSectionCollapse.value || visibleList.value.includes(targetId)) return
    const sectionId = findOwningSectionId(targetId)
    if (!sectionId) return
    const key = normalizeId(sectionId)
    if (!collapsedSectionIdSet.value.has(key)) return
    collapsedSectionIds.value = collapsedSectionIds.value.filter(sectionKey => sectionKey !== key)
    await nextTick()
  }

  const sameId = (a, b) => normalizeId(a) === normalizeId(b)

  // 折叠状态下拖动标题时，需要把标题到下一标题之间的所有成员一起打包移动。
  const getSectionMemberIds = (headerId, sourceList = props.modelValue) => {
    const result = []
    let inSection = false
    for (const id of sourceList) {
      if (sameId(id, headerId)) {
        inSection = true
        result.push(id)
        continue
      }
      if (inSection && isSectionHeaderId(id)) break
      if (inSection) result.push(id)
    }
    return result
  }

  // 插入位置按“可见列表位置”换算回“真实列表位置”，并兼容插入到折叠组末尾的需求。
  const getSectionRangeForId = (list, targetId) => {
    let currentHeaderId = ''
    let headerIndex = -1
    let itemIndex = -1
    for (let index = 0; index < list.length; index++) {
      const id = list[index]
      if (isSectionHeaderId(id)) {
        currentHeaderId = id
        headerIndex = index
      }
      if (sameId(id, targetId)) {
        itemIndex = index
        break
      }
    }
    if (itemIndex === -1) return null
    let endIndex = list.length - 1
    for (let index = itemIndex + 1; index < list.length; index++) {
      if (isSectionHeaderId(list[index])) {
        endIndex = index - 1
        break
      }
    }
    return {
      headerId: currentHeaderId,
      headerIndex,
      itemIndex,
      endIndex
    }
  }

  // newIndex 来自“可见列表”，而最终写回的是“真实列表”。
  // 这里负责把拖拽库给的可见位置，翻译成真实数组中的插入点。
  const resolveInsertionIndex = (baseList, dirtyIds, movingIds, newIndex, preferSectionEnd = false) => {
    const movingVisibleSet = new Set(
      movingIds
        .filter(id => visibleList.value.some(visibleId => sameId(visibleId, id)))
        .map(id => normalizeId(id))
    )
    const baseVisibleIds = dirtyIds.filter(id => !movingVisibleSet.has(normalizeId(id)))
    let insertVisibleIndex = 0
    for (let index = 0; index < newIndex; index++) {
      if (!movingVisibleSet.has(normalizeId(dirtyIds[index]))) {
        insertVisibleIndex++
      }
    }
    const prevVisibleId = baseVisibleIds[insertVisibleIndex - 1]
    const nextVisibleId = baseVisibleIds[insertVisibleIndex]

    if (prevVisibleId) {
      const prevRange = getSectionRangeForId(baseList, prevVisibleId)
      if (!prevRange) return baseList.length
      const insertToSectionEnd =
        (preferSectionEnd && !!prevRange.headerId) ||
        (isSectionHeaderId(prevVisibleId) && isSectionCollapsed(prevVisibleId))
      return insertToSectionEnd ? prevRange.endIndex + 1 : prevRange.itemIndex + 1
    }
    if (nextVisibleId) {
      const nextIndex = baseList.findIndex(id => sameId(id, nextVisibleId))
      return nextIndex === -1 ? 0 : nextIndex
    }
    return baseList.length
  }

  // 标题结构变化后，及时清理已经失效的折叠状态。
  watch(sectionHeaderIds, (ids) => {
    const validIds = new Set(ids.map(id => normalizeId(id)))
    collapsedSectionIds.value = collapsedSectionIds.value.filter(id => validIds.has(id))
  }, { immediate: true })

  // 功能关闭时直接清空运行态和恢复标记，避免后续 watch 继续写回旧状态。
  watch(sectionFeatureEnabled, (enabled) => {
    if (!enabled) {
      collapsedSectionIds.value = []
      sectionStateReady.value = false
    }
  }, { immediate: true })

  // 当环境切换、列表切换、标题集合变化时，重新按“历史状态优先”的规则恢复一次折叠状态。
  watch(
    [sectionStateStorageKey, sectionHeaderIds],
    () => {
      hydrateSectionState()
    },
    { immediate: true }
  )

  // 只有在初始化完成后，才把新的折叠状态回写到本地。
  watch(activeCollapsedSectionIds, (ids) => {
    if (!sectionFeatureEnabled.value || !sectionStateReady.value) return
    persistSectionIds(ids)
  })

  // 默认折叠只负责“没有历史状态时”的初始值，不主动覆盖用户已经保存的展开/折叠结果。
  watch(() => appStore.settings.ui.default_collapse_active_sections, (enabled) => {
    if (!sectionFeatureEnabled.value || sectionHeaderIds.value.length === 0) return
    const persistedIds = getPersistedSectionIds()
    if (persistedIds) return
    collapsedSectionIds.value = enabled
      ? normalizeSectionIds(sectionHeaderIds.value).filter(id => getSectionChildCount(id) > 0)
      : []
    sectionStateReady.value = true
    persistSectionIds()
  })

  // VirtualDragList 使用对象数组 { id: ... } 作为渲染与拖拽事件载体。
  // 这里做一个中间层，处理 visibleList 和 modelValue 之间的映射。
  // 注意：拖拽数量、虚影标题这类“只在拖拽开始时需要”的数据不要放进这里。
  // 否则每次多选变化都会重建整条虚拟列表，并连带触发 VirtualDragList 的行高/偏移缓存重算。
  const internalListProxy = computed({
    get() {
      return visibleList.value.map(id => {
        if (isSectionHeaderId(id) && isSectionCollapsed(id)) {
          return {
            id,
            mod_ids: getSectionMemberIds(id, props.modelValue),
          }
        }
        return { id }
      })
    },
    set() {
      // 排序结果最终由 drop 事件统一回写；这里保留空实现，只满足 v-model 接口要求。
    }
  })

  return {
    sectionFeatureEnabled,
    isSectionHeaderId,
    isSectionCollapsed,
    getSectionChildCount,
    toggleSection,
    expandSections,
    collapseSections,
    visibleList,
    revealCollapsedSectionFor,
    sameId,
    getSectionMemberIds,
    resolveInsertionIndex,
    internalListProxy,
  }
}
