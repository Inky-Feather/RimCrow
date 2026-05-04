import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { checkResult, toast } from '../utils/common'
import { useAppStore } from './appStore'

export const useGroupStore = defineStore('groups', () => {
  const appStore = useAppStore()
  const normalizeGroup = (group = {}) => ({
    ...group,
    mod_ids: Array.isArray(group?.mod_ids) ? [...group.mod_ids] : []
  })
  const normalizeGroups = (groups) => (
    Array.isArray(groups) ? groups.map(group => normalizeGroup(group)) : []
  )

  // === State ===
  const groupList = ref([]) // 分组列表
  const isDraggingGroup = ref(false) // 是否正在拖动分组

  // === Actions ===
  // 设置分组数据
  const setGroups = (groups) => {
    groupList.value = normalizeGroups(groups)
  }
  // 重置分组数据
  const reset = () => {
    groupList.value = []
  }
  // 根据 Mod ID 获取所属分组列表
  const takeGroupsByModId = (modId) => {
    const normalizedModId = String(modId ?? '').trim()
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
  // --- 数据操作 ---
  // 获取分组
  const getGroups = async () => {
    if (!window.pywebview) return
    appStore.isLoading = true
    try {
      const res = await window.pywebview.api.groups_get()
      if (checkResult(res, "获取分组")) {
        groupList.value = normalizeGroups(res.data.groups)
      }
    } catch (e) {
      console.error("获取分组异常:", e)
      toast.error(`获取分组异常: \n${e.message}`)
    } finally {
      appStore.isLoading = false
    }
  }
  // 创建分组（默认名称为“新分组”，随机颜色）
  const createGroup = async (name='新分组', color=`#${Math.floor(Math.random() * 16777216).toString(16).padStart(6, '0')}`) => {
    if (!window.pywebview) return
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
        // 排序
        groupList.value.sort((a, b) => a.sort_index - b.sort_index)
      } else {
        // 失败时才重新拉取数据进行还原
        await getGroups() 
      }
    } catch (e) {
      console.error("创建分组异常:", e)
      toast.error(`创建分组异常: \n${e.message}\n正在还原...`)
      // 失败时才重新拉取数据进行还原
      await getGroups() 
    }
  }
  // 删除分组
  const deleteGroup = async (groupId) => {
    if (!window.pywebview) return
    try {
      const res = await window.pywebview.api.group_delete(groupId)
      // console.log("删除分组:", res)
      if (checkResult(res, "删除分组", true)) {
        // 从列表中移除
        groupList.value = groupList.value.filter(group => group.group_id !== groupId)
      }
    } catch (e) {
      console.error("删除分组异常:", e)
      toast.error(`删除分组异常: \n${e.message}\n正在还原...`)
      // 失败时才重新拉取数据进行还原
      await getGroups() 
    } 
  }
  // 更新分组
  const updateGroup = async (groupId, updates) => {
    if (!window.pywebview) return false
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
      toast.error(`更新分组异常: \n${e.message}\n正在还原...`)
      // 失败时才重新拉取数据进行还原
      await getGroups() 
    }
    return false
  }
  // 分组添加模组
  const groupAddMods = async (groupId, modIds) => {
    if (!window.pywebview) return false
    try {
      // 更新本地分组
      const group = groupList.value.find(g => g.group_id === groupId)
      if (group) { // 确保分组存在, 并去重
        const currentIds = Array.isArray(group.mod_ids) ? group.mod_ids : []
        group.mod_ids = [...new Set([...currentIds, ...modIds])]
      }
      else return false
      const res = await window.pywebview.api.group_add_mods(groupId, modIds)
      // console.log("分组添加模组:", res)
      if (!checkResult(res, "分组添加模组")) {
        // 失败时才重新拉取数据进行还原
        await getGroups() 
      } else {
        return true
      }
    } catch (e) {
      console.error("分组添加模组异常:", e)
      toast.error(`分组添加模组异常: \n${e.message}\n正在还原...`)
      // 失败时才重新拉取数据进行还原
      await getGroups() 
    }
    return false
  }
  // 分组移除模组
  const groupRemoveMods = async (groupId, modIds) => {
    if (!window.pywebview) return false
    try {
      const res = await window.pywebview.api.group_remove_mods(groupId, modIds)
      // console.log("分组移除模组:", res)
      if (checkResult(res, "分组移除模组")) {
        // 更新本地分组
        const group = groupList.value.find(g => g.group_id === groupId)
        if (group) {
          const currentIds = Array.isArray(group.mod_ids) ? group.mod_ids : []
          group.mod_ids = currentIds.filter(id => !modIds.includes(id))
        }
        return true
      }
    } catch (e) {
      console.error("分组移除模组异常:", e)
      toast.error(`分组移除模组异常: \n${e.message}\n正在还原...`)
      // 失败时才重新拉取数据进行还原
      await getGroups() 
    } 
    return false
  }
  // 分组批量展开切换
  const changeAllGroupExpansion = async (isExpanded) => {
    if (!window.pywebview) return false
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
      toast.error(`批量展开切换异常: \n${e.message}\n正在还原...`)
      // 失败时才重新拉取数据进行还原
      await getGroups() 
    }
    return false
  }
  // 分组排序
  const groupReorder = async (groupIds = groupList.value.map(g => g.group_id)) => {
    if (!window.pywebview) return false
    try {
      // 更新本地分组排序
      groupList.value.sort((a, b) => groupIds.indexOf(a.group_id) - groupIds.indexOf(b.group_id))
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
      toast.error(`分组排序异常: \n${e.message}\n正在还原...`)
      // 失败时才重新拉取数据进行还原
      await getGroups() 
    }
    return false
  }
  // 分组内排序
  const groupContentReorder = async (groupId, modIds) => {
    if (!window.pywebview) return false
    if (!modIds || modIds.length === 0) return false
    try {
      // 更新本地分组
      const group = groupList.value.find(g => g.group_id === groupId)
      if (group) group.mod_ids = [...modIds]
      else return false
      const res = await window.pywebview.api.group_content_reorder(groupId, modIds)
      // console.log("分组内排序:", res)
      if (!checkResult(res, "分组内排序")) {
        // 失败时才重新拉取数据进行还原
        await getGroups() 
      } else {
        return true
      }
    } catch (e) {
      console.error("分组内排序异常:", e)
      toast.error(`分组内排序异常: \n${e.message}\n正在还原...`)
      // 失败时才重新拉取数据进行还原
      await getGroups() 
    }
    return false
  }


  return {
    groupList, isDraggingGroup, allGroupNames,
    takeGroupsByModId, takeGroupById, setGroups, reset, 
    getGroups, createGroup, deleteGroup, updateGroup, 
    groupAddMods, groupRemoveMods, changeAllGroupExpansion, groupReorder, groupContentReorder
  }
})
