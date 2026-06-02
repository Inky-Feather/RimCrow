import { toast, checkResult } from '../../../shared/lib/common'
import { useModStore } from '../../../features/mod/store/modStore'
import { useProfileStore } from '../../../features/profiles/profileStore'

export const useSettingsActions = ({
  settings,
  uiState,
  isLoading,
  userThemes,
  applyCurrentTheme,
  syncRemoteImageCache,
  refreshData,
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
        // 更新本地 store
        settings.value[key] = value
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

  // 应用全部设置（保存到后端并更新本地）
  const applySettings = async (newSettings) => {
    if (!window.pywebview) return
    isLoading.value = true
    try {
      const res = await window.pywebview.api.save_all_settings(newSettings)
      if (checkResult(res, "应用设置")) {
        const profileStore = useProfileStore()
        // 更新本地 store
        Object.assign(settings.value, res.data.settings)
        applyCurrentTheme()
        syncRemoteImageCache(res.data.remote_image_cache)
        profileStore.activeContext = res.data.active_context

        // 如果路径变了，可能需要重新扫描
        closeSettingsPanel()

        if (settings.value.enable_auto_scan && profileStore.activeContext.is_healthy) {
          const modStore = useModStore()
          await modStore.scanMods(null, false)
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
    // 用户主题
    refreshUserThemes, saveUserTheme, deleteUserTheme,
  }
}
