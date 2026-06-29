import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { checkResult, toast, toUserMessage } from '../../../shared/lib/common'
import { useAppStore } from '../../../app/stores/appStore'
import { normalizePackageId } from '../lib/modIdentity'

export const useGroupStore = defineStore('groups', () => {
  const appStore = useAppStore()
  const normalizeGroupModIds = (modIds = []) => {
    const source = Array.isArray(modIds) ? modIds : [modIds]
    return [...new Set(
      source
        .map(id => normalizePackageId(id))
        .filter(Boolean)
    )]
  }
  const normalizeGroup = (group = {}) => ({
    ...group,
    // 分组始终只持久化裸包名，避免 `_steam/_local` token 把同一模组拆成两条关系。
    mod_ids: normalizeGroupModIds(group?.mod_ids || [])
  })
  const normalizeGroups = (groups) => (
    Array.isArray(groups) ? groups.map(group => normalizeGroup(group)) : []
  )
  let pendingWriteChain = Promise.resolve()
  const sortGroupsByIndex = (groups) => {
    groups.sort((a, b) => {
      const indexA = Number.isFinite(Number(a?.sort_index)) ? Number(a.sort_index) : Number.MAX_SAFE_INTEGER
      const indexB = Number.isFinite(Number(b?.sort_index)) ? Number(b.sort_index) : Number.MAX_SAFE_INTEGER
      if (indexA !== indexB) return indexA - indexB
      return String(a?.group_id || '').localeCompare(String(b?.group_id || ''))
    })
  }
  const applyGroupOrder = (groupIds = []) => {
    const normalizedIds = groupIds
      .map(id => String(id ?? '').trim())
      .filter(Boolean)
    const indexMap = new Map(normalizedIds.map((id, index) => [id, index]))
    const unorderedTail = []
    const orderedGroups = []
    groupList.value.forEach(group => {
      const nextIndex = indexMap.get(group.group_id)
      if (nextIndex === undefined) {
        unorderedTail.push(group)
        return
      }
      group.sort_index = nextIndex
      orderedGroups[nextIndex] = group
    })
    sortGroupsByIndex(unorderedTail)
    unorderedTail.forEach((group, offset) => {
      group.sort_index = normalizedIds.length + offset
      orderedGroups.push(group)
    })
    groupList.value = orderedGroups.filter(Boolean)
  }

  // === State ===
  const groupList = ref([]) // 分组列表
  const isDraggingGroup = ref(false) // 是否正在拖动分组
  const targetGroupRequest = ref(null) // 外部页面请求分组面板定位的目标

  // === Actions ===
  const focusGroup = (groupId) => {
    const id = String(groupId ?? '').trim()
    if (!id) return
    targetGroupRequest.value = { groupId: id, requestedAt: Date.now() }
  }
  // 设置分组数据
  const setGroups = (groups) => {
    groupList.value = normalizeGroups(groups)
    sortGroupsByIndex(groupList.value)
  }
  // 重置分组数据
  const reset = () => {
    groupList.value = []
  }
  // 根据 Mod ID 获取所属分组列表
  const takeGroupsByModId = (modId) => {
    const normalizedModId = normalizePackageId(modId)
    if (!normalizedModId) return []
    return groupList.value.filter(g => Array.isArray(g?.mod_ids) && g.mod_ids.includes(normalizedModId))
  }
  // 根据分组 ID 获取分组数据
  const takeGroupById = (groupId) => {
    return groupList.value.find(g => g.group_id === groupId) || null
  }
  const allGroupNames = computed(() => {
    return groupList.value.map(g => g?.name).filter(Boolean)
  })
  const enqueueWrite = (task) => {
    const run = pendingWriteChain.then(() => task())
    pendingWriteChain = run.catch(() => {})
    return run
  }
  // --- 数据操作 ---
  // 获取分组
  const getGroups = async () => {
    if (!window.pywebview) return
    appStore.isLoading = true
    try {
      const res = await window.pywebview.api.groups_get()
      if (checkResult(res, "获取分组")) {
        groupList.value = normalizeGroups(res.data.groups)
        sortGroupsByIndex(groupList.value)
      }
    } catch (e) {
      console.error("获取分组异常:", e)
      toast.error(toUserMessage(e?.message || e, '获取分组失败。可能是数据库或当前环境暂时不可用，请稍后重试。'))
    } finally {
      appStore.isLoading = false
    }
  }
  // 创建分组（默认名称为“新分组”，随机颜色）
  const createGroup = async (name='新分组', color=`#${Math.floor(Math.random() * 16777216).toString(16).padStart(6, '0')}`) => {
    if (!window.pywebview) return
    return enqueueWrite(async () => {
      try {
      // console.log("创建分组:", allGroupNames.value, allGroupNames.value.includes(name))
        if (allGroupNames.value.includes(name)) {
        // 名称冲突，添加序号
          let index = 1
          while (allGroupNames.value.includes(`${name}-${index}`)) {
            index++
          }
          name = `${name}-${index}`
        }
        const res = await window.pywebview.api.group_create(name, color)
      // console.log("创建分组:", res)
        if (checkResult(res, "创建分组")) {
          groupList.value.push(normalizeGroup(res.data.group))
          sortGroupsByIndex(groupList.value)
          return true
        } else {
        // 失败时才重新拉取数据进行还原
          await getGroups()
        }
      } catch (e) {
        console.error("创建分组异常:", e)
        toast.error(toUserMessage(e?.message || e, '创建分组失败，正在还原列表状态。请稍后重试，详细原因已写入系统日志。'))
      // 失败时才重新拉取数据进行还原
        await getGroups()
      }
      return false
    })
  }
  // 删除分组
  const deleteGroup = async (groupId) => {
    if (!window.pywebview) return
    return enqueueWrite(async () => {
      try {
        const res = await window.pywebview.api.group_delete(groupId)
      // console.log("删除分组:", res)
        if (checkResult(res, "删除分组", true)) {
        // 从列表中移除
          groupList.value = groupList.value.filter(group => group.group_id !== groupId)
          return true
        }
        await getGroups()
      } catch (e) {
        console.error("删除分组异常:", e)
        toast.error(toUserMessage(e?.message || e, '删除分组失败，正在还原列表状态。请稍后重试，详细原因已写入系统日志。'))
        // 失败时才重新拉取数据进行还原
        await getGroups()
      }
      return false
    })
  }
  // 更新分组
  const updateGroup = async (groupId, updates) => {
    if (!window.pywebview) return false
    return enqueueWrite(async () => {
      try {
      // 更新本地列表
        const group = groupList.value.find(g => g.group_id === groupId)
        if (group) Object.assign(group, updates)
        else return false
        const res = await window.pywebview.api.group_update(groupId, updates)
      // console.log("更新分组:", res)
        if (!checkResult(res, "更新分组")) {
        // 失败时才重新拉取数据进行还原
          await getGroups()
        } else {
          return true
        }
      } catch (e) {
        console.error("更新分组异常:", e)
        toast.error(toUserMessage(e?.message || e, '更新分组失败，正在还原列表状态。请稍后重试，详细原因已写入系统日志。'))
        // 失败时才重新拉取数据进行还原
        await getGroups()
      }
      return false
    })
  }
  // 分组添加模组
  const groupAddMods = async (groupId, modIds) => {
    if (!window.pywebview) return false
    return enqueueWrite(async () => {
      try {
      const normalizedIds = normalizeGroupModIds(modIds)
      if (normalizedIds.length === 0) return false
      // 更新本地分组
        const group = groupList.value.find(g => g.group_id === groupId)
        if (group) { // 确保分组存在, 并去重
          const currentIds = Array.isArray(group.mod_ids) ? group.mod_ids : []
          group.mod_ids = normalizeGroupModIds([...currentIds, ...normalizedIds])
        }
        else return false
        const res = await window.pywebview.api.group_add_mods(groupId, normalizedIds)
      // console.log("分组添加模组:", res)
        if (!checkResult(res, "分组添加模组")) {
        // 失败时才重新拉取数据进行还原
          await getGroups()
        } else {
          return true
        }
      } catch (e) {
        console.error("分组添加模组异常:", e)
        toast.error(toUserMessage(e?.message || e, '添加模组到分组失败，正在还原列表状态。请稍后重试，详细原因已写入系统日志。'))
        // 失败时才重新拉取数据进行还原
        await getGroups()
      }
      return false
    })
  }
  // 分组移除模组
  const groupRemoveMods = async (groupId, modIds) => {
    if (!window.pywebview) return false
    return enqueueWrite(async () => {
      try {
        const normalizedIds = normalizeGroupModIds(modIds)
        if (normalizedIds.length === 0) return false
        const res = await window.pywebview.api.group_remove_mods(groupId, normalizedIds)
      // console.log("分组移除模组:", res)
        if (checkResult(res, "分组移除模组")) {
        // 更新本地分组
          const group = groupList.value.find(g => g.group_id === groupId)
          if (group) {
            const currentIds = Array.isArray(group.mod_ids) ? group.mod_ids : []
            group.mod_ids = currentIds.filter(id => !normalizedIds.includes(normalizePackageId(id)))
          }
          return true
        }
        await getGroups()
      } catch (e) {
        console.error("分组移除模组异常:", e)
        toast.error(toUserMessage(e?.message || e, '从分组移除模组失败，正在还原列表状态。请稍后重试，详细原因已写入系统日志。'))
        // 失败时才重新拉取数据进行还原
        await getGroups()
      }
      return false
    })
  }
  // 分组批量展开切换
  const changeAllGroupExpansion = async (isExpanded) => {
    if (!window.pywebview) return false
    return enqueueWrite(async () => {
      try {
      // 更新本地分组
        groupList.value.forEach(group => group.is_expanded = isExpanded)
        const res = await window.pywebview.api.groups_expansion_all(isExpanded)
      // console.log("批量展开切换:", res)
        if (!checkResult(res, "批量展开切换")) {
        // 失败时才重新拉取数据进行还原
          await getGroups()
        } else {
          return true
        }
      } catch (e) {
        console.error("批量展开切换异常:", e)
        toast.error(toUserMessage(e?.message || e, '保存分组展开状态失败，正在还原列表状态。请稍后重试。'))
        // 失败时才重新拉取数据进行还原
        await getGroups()
      }
      return false
    })
  }
  // 分组排序
  const groupReorder = async (groupIds = groupList.value.map(g => g.group_id)) => {
    if (!window.pywebview) return false
    return enqueueWrite(async () => {
      try {
      // 先在本地同步数组顺序和 sort_index，避免后续新建分组时再次按旧索引洗乱顺序。
        applyGroupOrder(groupIds)
        const res = await window.pywebview.api.group_reorder(groupIds)
      // console.log("分组排序:", res)
        if (!checkResult(res, "分组排序")) {
        // 失败时才重新拉取数据进行还原
          await getGroups()
        } else {
          return true
        }
      } catch (e) {
        console.error("分组排序异常:", e)
        toast.error(toUserMessage(e?.message || e, '保存分组排序失败，正在还原列表状态。请稍后重试，详细原因已写入系统日志。'))
        // 失败时才重新拉取数据进行还原
        await getGroups()
      }
      return false
    })
  }
  // 分组内排序
  const groupContentReorder = async (groupId, modIds) => {
    if (!window.pywebview) return false
    if (!modIds || modIds.length === 0) return false
    return enqueueWrite(async () => {
      try {
      const normalizedIds = normalizeGroupModIds(modIds)
      if (normalizedIds.length === 0) return false
      // 更新本地分组
        const group = groupList.value.find(g => g.group_id === groupId)
        if (group) group.mod_ids = [...normalizedIds]
        else return false
        const res = await window.pywebview.api.group_content_reorder(groupId, normalizedIds)
      // console.log("分组内排序:", res)
        if (!checkResult(res, "分组内排序")) {
        // 失败时才重新拉取数据进行还原
          await getGroups()
        } else {
          return true
        }
      } catch (e) {
        console.error("分组内排序异常:", e)
        toast.error(toUserMessage(e?.message || e, '保存分组内排序失败，正在还原列表状态。请稍后重试，详细原因已写入系统日志。'))
        // 失败时才重新拉取数据进行还原
        await getGroups()
      }
      return false
    })
  }


  return {
    // 状态
    groupList, isDraggingGroup, targetGroupRequest, allGroupNames,
    // 查询与本地同步
    focusGroup, takeGroupsByModId, takeGroupById, setGroups, reset,
    // 分组管理
    getGroups, createGroup, deleteGroup, updateGroup,
    // 分组内容与排序
    groupAddMods, groupRemoveMods, changeAllGroupExpansion, groupReorder, groupContentReorder,
  }
})
