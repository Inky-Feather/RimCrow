// stores/profileStore.js
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { useAppStore } from './appStore'
import { useModStore } from './modStore'
import { useGroupStore } from './groupStore'
import { useConfirmStore } from './confirmStore'
import { toast, checkResult } from '../utils/common'
import { useOrderStore } from './orderStore'


export const useProfileStore = defineStore('profile', () => {
  const appStore = useAppStore()
  
  // === State ===
  const profiles = ref([])      // 所有环境配置
  const currentProfileId = ref('default')
  const orphanedProfiles = ref([]) // 磁盘上存在但数据库没记录的配置
  const isLoading = ref(false)   // 环境列表加载状态

  // 当前激活的严格上下文 (Active Context)
  const activeContext = ref({
    profile_id: '',
    game_install_path: '',
    user_data_path: '',
    game_version: '',
    prefer_steam_launch: true,
    use_workshop_mods: true,
    use_self_mods: false,
    run_commands: [],

    local_mods_path: '',
    game_dlc_path: '',
    game_config_path: '',
    game_saves_path: '',
    mods_config_file: '',
    backup_dir: '',
    
    // 健康哨兵状态
    is_healthy: true,
    health_report: {}
  })

  // === Getters ===
  const currentProfile = computed(() => 
    profiles.value.find(p => p.id === currentProfileId.value) || null
  )

  // === Actions ===
  const sleep = (ms) => new Promise(resolve => window.setTimeout(resolve, ms))

  const buildSteamShortcutProgressMessage = (steps) => (
    [
      'Steam 快捷方式创建步骤：',
      ...steps.map(step => `${step.done ? '√' : step.active ? '&gt;' : '-'} ${step.label}`)
    ].join('<br>')
  )

  const isSteamVdfShortcutFlow = (profile) => {
    if (!profile || profile.id === 'default') return false
    if (!profile.prefer_steam_launch) return false
    const defaultProfile = profiles.value.find(item => item.id === 'default')
    if (!defaultProfile?.game_install_path || !profile.game_install_path) return false
    return String(defaultProfile.game_install_path).trim().toLowerCase() !== String(profile.game_install_path).trim().toLowerCase()
  }
  
  // 获取环境列表
  const fetchProfiles = async () => {
    if (!window.pywebview) return
    const res = await window.pywebview.api.profiles_get()
    if (checkResult(res, '获取环境列表')) {
      profiles.value = res.data
    }
  }

  // 创建新环境
  const createProfile = async (data, copyCurrentData = false) => {
    isLoading.value = true
    try {
      const res = await window.pywebview.api.profile_create(data, copyCurrentData)
      if (checkResult(res, `创建环境 "${data.name}"`,true)) {
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
      const orderStore = useOrderStore()
      await orderStore.saveInactiveOrder();  // 先保存停用列表顺序
      const res = await window.pywebview.api.profile_activate(profileId)
      if (checkResult(res, '切换环境')) {
        currentProfileId.value = profileId
        // 【关键逻辑】环境切换后，重置并刷新所有数据
        const groupStore = useGroupStore()
        // 1. 清空当前前端的缓存，防止数据交叉
        const modStore = useModStore()
        modStore.reset()
        groupStore.reset()
        // 2. 先立即拉取一次新环境上下文，确保停用列表等持久化状态即时恢复
        await appStore.refreshData()
        // 3. 再后台触发一次扫描，补齐该环境的 DLC / Local / Workshop 实际磁盘状态
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
    const res = await window.pywebview.api.profile_update(profileId, updates)
    if (checkResult(res, `更新环境 "${profileId}"`, true)) {
      await fetchProfiles()
      if (profileId === currentProfileId.value) {
        switchProfile(profileId)
      }
    }
  }

  // 删除环境
  const deleteProfile = async (profileId, force = false) => {
    const res = await window.pywebview.api.profile_delete(profileId, !!force)
    if (checkResult(res, '删除环境')) {
      await fetchProfiles()
      // 如果删的是当前的，后端会自动切回 default，前端需要同步
      if (profileId === currentProfileId.value) {
        currentProfileId.value = 'default'
        switchProfile('default')
      }
    }
  }

  // 创建环境桌面快捷方式
  const createDesktopShortcut = async (profileId) => {
    const profile = profiles.value.find(item => item.id === profileId)
    if (isSteamVdfShortcutFlow(profile)) {
      return await createSteamVdfDesktopShortcut(profile)
    }

    const res = await window.pywebview.api.profile_create_desktop_shortcut(profileId)
    if (checkResult(res, '创建环境桌面快捷方式', true)) {
      return res.data
    }
    return null
  }

  const createSteamVdfDesktopShortcut = async (profile) => {
    const confirmStore = useConfirmStore()
    const steps = [
      { label: '等待手动关闭 Steam 进程', done: false, active: true },
      { label: '写入 Steam 快捷方式配置', done: false, active: false },
      { label: '启动 Steam 并等待登录完成', done: false, active: false },
      { label: '确认稳定快捷方式 ID 并创建桌面快捷方式', done: false, active: false },
    ]

    const updateProgress = () => {
      confirmStore.state.title = '创建 Steam 快捷方式'
      confirmStore.state.message = buildSteamShortcutProgressMessage(steps)
      confirmStore.state.isHtml = true
      confirmStore.state.mode = 'confirm'
      confirmStore.state.type = 'warning'
      confirmStore.state.confirmText = '确定'
      confirmStore.state.cancelText = '取消'
      confirmStore.state.actionButtons = [{ label: '取消', value: 'cancel', kind: 'secondary' }]
    }

    const setActiveStep = (index) => {
      steps.forEach((step, idx) => {
        step.active = idx === index
      })
      updateProgress()
    }

    const completeStep = (index) => {
      steps[index].done = true
      steps[index].active = false
      updateProgress()
    }

    let cancelled = false
    confirmStore.open({
      title: '创建 Steam 快捷方式',
      message: buildSteamShortcutProgressMessage(steps),
      isHtml: true,
      mode: 'confirm',
      type: 'warning',
      actionButtons: [{ label: '取消', value: 'cancel', kind: 'secondary' }],
    }).then(() => {
      cancelled = true
      return null
    })

    try {
      setActiveStep(0)
      while (!cancelled) {
        const statusRes = await window.pywebview.api.steam_process_status()
        if (statusRes?.status === 'success' && !statusRes?.data?.running) break
        await sleep(1000)
      }
      if (cancelled) return null
      completeStep(0)

      setActiveStep(1)
      const registerRes = await window.pywebview.api.profile_register_steam_shortcut(profile.id)
      if (!checkResult(registerRes, '写入 Steam 快捷方式配置')) return null
      const logProbe = registerRes?.data?.log_probe || null
      completeStep(1)

      setActiveStep(2)
      const steamLaunchRes = await window.pywebview.api.steam_launch_client()
      if (!checkResult(steamLaunchRes, '启动 Steam 客户端')) return null
      completeStep(2)

      setActiveStep(3)
      const finalizeRes = await window.pywebview.api.profile_finalize_steam_shortcut(profile.id, logProbe)
      if (cancelled) return null

      if (finalizeRes?.status === 'success') {
        completeStep(3)
        confirmStore.closeSilently()
        checkResult(finalizeRes, '创建环境桌面快捷方式', true)
        return finalizeRes.data
      }

      confirmStore.closeSilently()
      if (finalizeRes) {
        checkResult(finalizeRes, '创建环境桌面快捷方式')
      }
      return null
    } finally {
      if (confirmStore.isVisible) confirmStore.closeSilently()
    }
  }

  // 扫描孤立配置
  const scanOrphans = async () => {
    const res = await window.pywebview.api.profiles_scan_orphaned()
    if (checkResult(res, '扫描待恢复环境')) {
      orphanedProfiles.value = res.data
    }
  }

  // 导入孤立配置
  const importOrphan = async (profileData) => {
    const res = await window.pywebview.api.profile_import_orphaned(profileData)
    if (checkResult(res, '导入环境')) {
      toast.success('环境配置已恢复')
      await fetchProfiles()
      await scanOrphans()
    }
  }

  return {
    profiles, currentProfileId, orphanedProfiles, currentProfile, isLoading, activeContext,
    fetchProfiles, createProfile, switchProfile, updateProfile, deleteProfile, createDesktopShortcut,
    scanOrphans, importOrphan
  }
})
