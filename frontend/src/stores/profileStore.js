// stores/profileStore.js
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { useAppStore } from './appStore'
import { useModStore } from './modStore'
import { useGroupStore } from './groupStore'
import { createToastInterface } from 'vue-toastification'


export const useProfileStore = defineStore('profile', () => {
  const toast = createToastInterface()
  const appStore = useAppStore()
  
  // === State ===
  const profiles = ref([])      // 所有环境配置
  const currentProfileId = ref('default')
  const orphanedProfiles = ref([]) // 磁盘上存在但数据库没记录的配置
  const isLoading = ref(false)   // 环境列表加载状态

  // === Getters ===
  const currentProfile = computed(() => 
    profiles.value.find(p => p.id === currentProfileId.value) || null
  )

  // === Actions ===
  
  // 获取环境列表
  const fetchProfiles = async () => {
    if (!window.pywebview) return
    const res = await window.pywebview.api.get_profiles()
    if (appStore.checkResult(res, '获取环境列表')) {
      profiles.value = res.data
      console.log('获取环境列表:', profiles.value)
    }
  }

  // 创建新环境
  const createProfile = async (data, copyCurrentData = false) => {
    isLoading.value = true
    try {
      const res = await window.pywebview.api.create_profile(data, copyCurrentData)
      if (appStore.checkResult(res, `创建环境 "${data.name}"`,true)) {
        await fetchProfiles()
        return true
      }
    } finally {
      isLoading.value = false
    }
    return false
  }

  // 切换环境 (核心逻辑)
  const switchProfile = async (profileId) => {
    // if (profileId === currentProfileId.value) return
    appStore.isLoading = true
    isLoading.value = true
    try {
      const res = await window.pywebview.api.activate_profile(profileId)
      if (appStore.checkResult(res, '切换环境')) {
        currentProfileId.value = profileId
        // 【关键逻辑】环境切换后，重置并刷新所有数据
        const modStore = useModStore()
        const groupStore = useGroupStore()
        // 1. 清空当前前端的缓存，防止数据交叉
        modStore.reset()
        groupStore.reset()
        // 2. 重新从后端拉取新环境的上下文数据 (Mods, Groups, Settings)
        await modStore.scanMods()
        toast.success(`已切换至环境: ${currentProfile.value?.name || profileId}`)
      }
    } finally {
      appStore.isLoading = false
      isLoading.value = false
    }
  }

  // 更新环境信息
  const updateProfile = async (profileId, updates) => {
    const res = await window.pywebview.api.update_profile(profileId, updates)
    if (appStore.checkResult(res, `更新环境 "${updates.name}"`, true)) {
      await fetchProfiles()
      if (profileId === currentProfileId.value) {
        switchProfile(profileId)
      }
    }
  }

  // 删除环境
  const deleteProfile = async (profileId) => {
    const res = await window.pywebview.api.delete_profile(profileId)
    if (appStore.checkResult(res, '删除环境')) {
      await fetchProfiles()
      // 如果删的是当前的，后端会自动切回 default，前端需要同步
      if (profileId === currentProfileId.value) {
        currentProfileId.value = 'default'
        switchProfile('default')
      }
    }
  }

  // 扫描孤立配置
  const scanOrphans = async () => {
    const res = await window.pywebview.api.scan_orphaned_profiles()
    if (appStore.checkResult(res, '扫描待恢复环境')) {
      orphanedProfiles.value = res.data
    }
  }

  // 导入孤立配置
  const importOrphan = async (profileData) => {
    const res = await window.pywebview.api.import_orphaned_profile(profileData)
    if (appStore.checkResult(res, '导入环境')) {
      toast.success('环境配置已恢复')
      await fetchProfiles()
      await scanOrphans()
    }
  }

  return {
    profiles, currentProfileId, orphanedProfiles, currentProfile, isLoading,
    fetchProfiles, createProfile, switchProfile, updateProfile, deleteProfile,
    scanOrphans, importOrphan
  }
})