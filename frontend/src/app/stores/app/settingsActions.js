import { toast, checkResult } from '../../../shared/lib/common'
import { useProfileStore } from '../../../features/profiles/profileStore'

const SETTING_KEYS_REQUIRING_LIST_SCAN = [
  'workshop_mods_path',
  'self_mods_path',
  'steamcmd_mods_path',
]

const takeModListSettingsSnapshot = (settings = {}, context = {}) => ({
  settings: Object.fromEntries(
    SETTING_KEYS_REQUIRING_LIST_SCAN.map(key => [key, settings?.[key] ?? null])
  ),
  context: {
    profile_id: context?.profile_id || '',
    game_install_path: context?.game_install_path || '',
    user_data_path: context?.user_data_path || '',
    use_workshop_mods: !!context?.use_workshop_mods,
    use_self_mods: !!context?.use_self_mods,
  },
})

const shouldRefreshModListAfterSettingsSave = (before, after) => {
  return (
    SETTING_KEYS_REQUIRING_LIST_SCAN.some(key => before.settings[key] !== after.settings[key])
    || Object.keys(before.context).some(key => before.context[key] !== after.context[key])
  )
}

export const useSettingsActions = ({
  settings,
  uiState,
  isLoading,
  userThemes,
  applyCurrentTheme,
  syncRemoteImageCache,
  refreshData,
  requestModScan,
} = {}) => {
  // 打开/关闭设置页面
  const openSettingsPanel = () => { uiState.showSettingsPanel = true }
  const closeSettingsPanel = () => { uiState.showSettingsPanel = false }

  // 保存单项设置
  const saveSetting = async (key, value) => {
    if (!window.pywebview) return
    isLoading.value = true
    try {
      const res = await window.pywebview.api.save_setting(key, value)
      if (checkResult(res, "保存单项设置", true)) {
        const nextSettings = res.data?.settings || null
        if (nextSettings) Object.assign(settings.value, nextSettings)
        else settings.value[key] = value
      }
    } catch (e) {
      console.error("保存单项设置异常:", e)
      toast.error(`保存单项设置异常: \n${e.message}`)
    } finally {
      isLoading.value = false
    }
  }

  const refreshUserThemes = async () => {
    if (!window.pywebview) return userThemes.value
    const res = await window.pywebview.api.theme_list_user()
    if (checkResult(res, "读取用户主题", true)) {
      userThemes.value = res.data?.themes || []
      applyCurrentTheme()
    }
    return userThemes.value
  }

  const saveUserTheme = async (theme) => {
    if (!window.pywebview) return null
    const res = await window.pywebview.api.theme_save_user(theme)
    if (!checkResult(res, "保存用户主题")) return null
    const savedTheme = res.data?.theme
    if (savedTheme) {
      const nextThemes = userThemes.value.filter(item => item.id !== savedTheme.id)
      userThemes.value = [...nextThemes, savedTheme]
      applyCurrentTheme()
    }
    return savedTheme
  }

  const deleteUserTheme = async (themeId) => {
    if (!window.pywebview) return false
    const res = await window.pywebview.api.theme_delete_user(themeId)
    if (!checkResult(res, "删除用户主题")) return false
    userThemes.value = userThemes.value.filter(item => item.id !== themeId)
    applyCurrentTheme()
    return !!res.data?.deleted
  }

  const revealSecret = async (secretKey, options = {}) => {
    if (!window.pywebview) return null
    const res = await window.pywebview.api.settings_reveal_secret(secretKey)
    if (!checkResult(res, '读取已保存密钥', false, { ...options, debugMode: false })) return null
    return res.data || null
  }

  const clearSecret = async (secretKey) => {
    if (!window.pywebview) return false
    const res = await window.pywebview.api.settings_clear_secret(secretKey)
    if (!checkResult(res, '清除密钥', true)) return false
    if (res.data?.settings) Object.assign(settings.value, res.data.settings)
    return true
  }

  // 应用全部设置（保存到后端并更新本地）
  const applySettings = async (newSettings) => {
    if (!window.pywebview) return
    isLoading.value = true
    try {
      const profileStore = useProfileStore()
      const previousListSnapshot = takeModListSettingsSnapshot(settings.value, profileStore.activeContext)
      const res = await window.pywebview.api.save_all_settings(newSettings)
      if (checkResult(res, "应用设置")) {
        const nextSettings = res.data.settings || {}
        const nextContext = res.data.active_context || profileStore.activeContext
        // 更新本地 store
        Object.assign(settings.value, nextSettings)
        applyCurrentTheme()
        syncRemoteImageCache(res.data.remote_image_cache)
        profileStore.activeContext = nextContext

        closeSettingsPanel()

        const nextListSnapshot = takeModListSettingsSnapshot(settings.value, nextContext)
        if (!shouldRefreshModListAfterSettingsSave(previousListSnapshot, nextListSnapshot)) {
          return
        }

        if (settings.value.enable_auto_scan && nextContext?.is_healthy && requestModScan) {
          await requestModScan()
        } else{
          await refreshData()
        }
        // await initialize()
      }
    } catch (e) {
      console.error("应用设置异常:", e)
      toast.error(`应用设置异常: \n${e.message}`)
    } finally {
      isLoading.value = false
    }
  }

  return {
    // 面板
    openSettingsPanel, closeSettingsPanel,
    // 设置保存
    saveSetting, applySettings,
    // 密钥
    revealSecret, clearSecret,
    // 用户主题
    refreshUserThemes, saveUserTheme, deleteUserTheme,
  }
}
