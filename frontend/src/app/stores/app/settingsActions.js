import { toast, checkResult, toUserMessage } from '../../../shared/lib/common'
import { useProfileStore } from '../../../features/profiles/profileStore'
import { t } from '../../../shared/i18n.js'

// 改变模组来源或可见模组类型：必须重新扫描磁盘，拿到新的模组清单。
const SETTING_KEYS_REQUIRING_LIST_SCAN = [
  'workshop_mods_path',
  'self_mods_path',
  'steamcmd_mods_path',
  'enable_tool_mods',
]

// 改变核心状态判定：只需要重拉核心数据，保留当前列表滚动、选择等前端状态。
const SETTING_KEYS_REQUIRING_MOD_CORE_REFRESH = [
  'language',
  'wide_language_pack_detection',
]

// 改变补充信息判定：只刷新联机兼容等补充数据，不重拉核心列表。
const SETTING_KEYS_REQUIRING_MOD_ENRICHMENT_REFRESH = [
  'enable_multiplayer_compatibility_check',
]

// 改变规则文件来源：要重新读取规则，但不需要重新扫描模组目录。
const SETTING_KEYS_REQUIRING_RULE_SOURCE_REFRESH = [
  'user_rules_path',
  'community_rules_path',
]

// 改变外部数据库来源：需要重算模组补充状态，但不需要刷新规则、备份和工作区库。
const SETTING_KEYS_REQUIRING_EXTERNAL_DATA_REFRESH = [
  'community_workshop_db_path',
  'community_instead_db_path',
  'multiplayer_compatibility_path',
  'mp_compat_package_ids_path',
]

// 这些字段决定“当前应该读取哪些模组”。变化后要重新扫描磁盘，不能只刷新内存数据。
const takeModListSettingsSnapshot = (settings = {}, context = {}) => ({
  settings: Object.fromEntries(
    SETTING_KEYS_REQUIRING_LIST_SCAN.map(key => [key, settings?.[key] ?? null])
  ),
  // 模组来源一部分来自全局设置，一部分来自当前环境上下文，两边都要一起比较。
  context: {
    profile_id: context?.profile_id || '',
    game_install_path: context?.game_install_path || '',
    user_data_path: context?.user_data_path || '',
    prefer_steam_launch: !!context?.prefer_steam_launch,
    use_workshop_mods: !!context?.use_workshop_mods,
    use_self_mods: !!context?.use_self_mods,
  },
})

// 列表来源变化是最重的刷新路径，优先级高于后面的规则、补充信息和普通状态刷新。
const shouldRefreshModListAfterSettingsSave = (before, after) => {
  return (
    SETTING_KEYS_REQUIRING_LIST_SCAN.some(key => before.settings[key] !== after.settings[key])
    || Object.keys(before.context).some(key => before.context[key] !== after.context[key])
  )
}

const takeSettingsSnapshot = (keys = [], settings = {}) => Object.fromEntries(
  keys.map(key => [key, settings?.[key] ?? null])
)

const hasSnapshotChanged = (before = {}, after = {}) => (
  Object.keys(before).some(key => before[key] !== after[key])
)

// 保存前拍快照，保存后用后端返回的完整设置再比较，避免漏掉后端联动更新的字段。
const takeRefreshSettingsSnapshot = (settings = {}, context = {}) => ({
  list: takeModListSettingsSnapshot(settings, context),
  core: takeSettingsSnapshot(SETTING_KEYS_REQUIRING_MOD_CORE_REFRESH, settings),
  enrichment: takeSettingsSnapshot(SETTING_KEYS_REQUIRING_MOD_ENRICHMENT_REFRESH, settings),
  rules: takeSettingsSnapshot(SETTING_KEYS_REQUIRING_RULE_SOURCE_REFRESH, settings),
  external: takeSettingsSnapshot(SETTING_KEYS_REQUIRING_EXTERNAL_DATA_REFRESH, settings),
})

const getRefreshSettingsChanges = (before, settings = {}, context = {}) => {
  const after = takeRefreshSettingsSnapshot(settings, context)
  return {
    // 按刷新成本分组，后续按从重到轻的顺序只执行一条路径。
    listSourceChanged: shouldRefreshModListAfterSettingsSave(before.list, after.list),
    modCoreSettingsChanged: hasSnapshotChanged(before.core, after.core),
    modEnrichmentSettingsChanged: hasSnapshotChanged(before.enrichment, after.enrichment),
    ruleSourceChanged: hasSnapshotChanged(before.rules, after.rules),
    externalDataChanged: hasSnapshotChanged(before.external, after.external),
  }
}

export const useSettingsActions = ({
  settings,
  uiState,
  isLoading,
  userThemes,
  applyCurrentTheme,
  syncRemoteImageCache,
  refreshData,
  refreshModCoreData,
  refreshModEnrichment,
  requestModScan,
} = {}) => {
  // 打开/关闭设置页面
  const openSettingsPanel = () => { uiState.showSettingsPanel = true }
  const closeSettingsPanel = () => { uiState.showSettingsPanel = false }

  const refreshAfterModListSourceChange = async (nextContext) => {
    if (settings.value.enable_auto_scan && nextContext?.is_healthy && requestModScan) {
      await requestModScan({ forceCoreRefresh: true })
    } else if (refreshData) {
      await refreshData()
    }
  }

  const refreshAfterModStateSettingsChange = async ({ coreChanged = false, enrichmentChanged = false } = {}) => {
    if (coreChanged && refreshModCoreData) {
      const refreshOptions = {
        preserveListState: true,
        refreshRules: false,
        refreshBackups: false,
        refreshWorkspaceLibraries: false,
      }
      // 核心刷新默认会顺手异步刷新补充信息；这里需要等待补充信息完成时，先关掉默认异步刷新。
      if (enrichmentChanged && refreshModEnrichment) refreshOptions.refreshEnrichment = false
      await refreshModCoreData(t('check.settings.refresh_mod_state_after_change', '设置变更后同步模组状态'), refreshOptions)
      if (enrichmentChanged && refreshModEnrichment) {
        await refreshModEnrichment({ silent: true })
      }
      return
    }
    if (enrichmentChanged && refreshModEnrichment) {
      await refreshModEnrichment({ silent: true })
      return
    }
    if (coreChanged && refreshData) await refreshData()
  }

  // 规则路径和外部数据路径只影响规则/补充判定，不需要重新扫描磁盘，也不需要刷新备份和工作区库。
  const refreshAfterModDataSourceSettingsChange = async ({ refreshRules = false } = {}) => {
    if (refreshModCoreData) {
      await refreshModCoreData(t('check.settings.refresh_mod_state_after_change', '设置变更后同步模组状态'), {
        preserveListState: true,
        refreshRules: !!refreshRules,
        refreshBackups: false,
        refreshWorkspaceLibraries: false,
      })
      return
    }
    if (refreshData) await refreshData()
  }

  const refreshAfterSettingsSave = async (changes, nextContext) => {
    // 只执行最高优先级的一条刷新路径，避免一次保存触发扫描、核心刷新和补充刷新重复排队。
    if (changes.listSourceChanged) {
      await refreshAfterModListSourceChange(nextContext)
      return
    }
    if (changes.ruleSourceChanged || changes.externalDataChanged) {
      await refreshAfterModDataSourceSettingsChange({ refreshRules: changes.ruleSourceChanged })
      return
    }
    if (changes.modCoreSettingsChanged || changes.modEnrichmentSettingsChanged) {
      await refreshAfterModStateSettingsChange({
        coreChanged: changes.modCoreSettingsChanged,
        enrichmentChanged: changes.modEnrichmentSettingsChanged,
      })
    }
  }

  // 保存单项设置
  const saveSetting = async (key, value) => {
    if (!window.pywebview) return false
    isLoading.value = true
    try {
      const profileStore = useProfileStore()
      const previousSnapshot = takeRefreshSettingsSnapshot(settings.value, profileStore.activeContext)
      const res = await window.pywebview.api.save_setting(key, value)
      if (checkResult(res, t('check.settings.save_one', '保存单项设置'), true)) {
        const nextSettings = res.data?.settings || null
        if (nextSettings) Object.assign(settings.value, nextSettings)
        else settings.value[key] = value
        const changes = getRefreshSettingsChanges(previousSnapshot, settings.value, profileStore.activeContext)
        await refreshAfterSettingsSave(changes, profileStore.activeContext)
        return true
      }
      return false
    } catch (e) {
      console.error("保存单项设置异常:", e)
      toast.error(toUserMessage(e?.message || e, t('toast.settings.save_failed', '保存设置失败。可能是后端服务暂时不可用、配置文件无法写入或当前路径权限不足，请稍后重试。')))
      return false
    } finally {
      isLoading.value = false
    }
  }

  const refreshUserThemes = async () => {
    if (!window.pywebview) return userThemes.value
    const res = await window.pywebview.api.theme_list_user()
    if (checkResult(res, t('check.settings.read_user_themes', '读取用户主题'), true)) {
      userThemes.value = res.data?.themes || []
      applyCurrentTheme()
    }
    return userThemes.value
  }

  const saveUserTheme = async (theme) => {
    if (!window.pywebview) return null
    const res = await window.pywebview.api.theme_save_user(theme)
    if (!checkResult(res, t('check.settings.save_user_theme', '保存用户主题'))) return null
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
    if (!checkResult(res, t('check.settings.delete_user_theme', '删除用户主题'))) return false
    userThemes.value = userThemes.value.filter(item => item.id !== themeId)
    applyCurrentTheme()
    return !!res.data?.deleted
  }

  const revealSecret = async (secretKey, options = {}) => {
    if (!window.pywebview) return null
    const res = await window.pywebview.api.settings_reveal_secret(secretKey)
    if (!checkResult(res, t('check.settings.read_saved_secret', '读取已保存密钥'), false, { ...options, debugMode: false })) return null
    return res.data || null
  }

  const clearSecret = async (secretKey) => {
    if (!window.pywebview) return false
    const res = await window.pywebview.api.settings_clear_secret(secretKey)
    if (!checkResult(res, t('check.settings.clear_secret', '清除密钥'), true)) return false
    if (res.data?.settings) Object.assign(settings.value, res.data.settings)
    return true
  }

  // 应用全部设置（保存到后端并更新本地）
  const applySettings = async (newSettings) => {
    if (!window.pywebview) return
    isLoading.value = true
    try {
      const profileStore = useProfileStore()
      const previousSnapshot = takeRefreshSettingsSnapshot(settings.value, profileStore.activeContext)
      const res = await window.pywebview.api.save_all_settings(newSettings)
      if (checkResult(res, t('check.settings.apply', '应用设置'))) {
        const nextSettings = res.data.settings || {}
        const nextContext = res.data.active_context || profileStore.activeContext
        // 更新本地 store
        Object.assign(settings.value, nextSettings)
        applyCurrentTheme()
        if (res.data.remote_image_cache) syncRemoteImageCache(res.data.remote_image_cache)
        profileStore.currentProfileId = nextContext?.profile_id || nextSettings.current_profile_id || profileStore.currentProfileId
        profileStore.activeContext = nextContext
        await profileStore.fetchProfiles()

        closeSettingsPanel()

        const changes = getRefreshSettingsChanges(previousSnapshot, settings.value, nextContext)
        await refreshAfterSettingsSave(changes, nextContext)
        // await initialize()
      }
    } catch (e) {
      console.error("应用设置异常:", e)
      toast.error(toUserMessage(e?.message || e, t('toast.settings.apply_failed', '应用设置失败。可能是配置校验未通过、路径无法访问或配置文件无法写入，详细原因已写入系统日志。')))
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
