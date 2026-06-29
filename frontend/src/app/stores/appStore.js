// stores/appStore.js

import { defineStore } from 'pinia'
import { ref, reactive, computed, watch } from 'vue'
import { checkResult, deepClone, toast, toUserMessage } from '../../shared/lib/common'
import { startupPerfMark, startupPerfMeasure } from '../../shared/lib/startupPerf'
import { useModStore } from '../../features/mod/stores/modStore'
import { useGroupStore } from '../../features/mod/stores/groupStore'
import { useOrderStore } from '../../features/load-order/orderStore'
import { useRuleStore } from '../../features/rules/ruleStore'
import { useConfirmStore } from '../../shared/components/modal/confirmStore'
import { useProfileStore } from '../../features/profiles/profileStore'
import { useTextureStore } from '../../features/texture-opt/textureStore'
import { useWorkspaceStore } from '../../features/workspace/workspaceStore'
import { useModResidueStore } from '../../features/mod-residue/modResidueStore'
import { useTaskStore } from './taskStore'
import { useStartupStore } from './startupStore'
import { DEFAULT_THEME_ID, applyTheme, findThemeById, mergeThemes } from '../../features/settings/theme/themeManager'
import { usePathActions } from './app/pathActions'
import { useSettingsActions } from './app/settingsActions'
import { usePackageTransferActions } from './app/packageTransferActions'
import { useSteamWorkshopActions } from './app/steamWorkshopActions'
import { useMaintenanceActions } from './app/maintenanceActions'
import { useUpdateActions } from './app/updateActions'

export const useAppStore = defineStore('app', () => {
  const taskStore = useTaskStore()
  const confirmStore = useConfirmStore()

  const createDefaultRuntimeSession = () => ({
    profile_id: '',
    state: 'idle',
    source: 'manager',
    launch_mode: 'unknown',
    requested_at: null,
    deadline_at: null,
    started_at: null,
    failure_reason: '',
    message: '',
  })

  // === State ===
  const appVersion = ref('')     // 应用版本号
  const buildMode = ref('')      // 构建模式
  const isLoading = ref(false)   // 加载状态
  const settingsReady = ref(false) // 后端设置已注入，避免其它 store 把默认空配置误判为用户配置
  const isGameRunning = ref(false) // 全局游戏运行状态
  const isSuspended = ref(false) // 浏览器模式下的同页静默挂起状态
  // 运行时会话与 UI 当前环境分离：这里只记录“游戏现在实际按谁在跑”。
  const runtimeSession = ref(createDefaultRuntimeSession())

  // UI 状态
  const uiState = reactive({
    showSettingsPanel: false,    // 是否显示设置面板
    showUpdateModal: false,      // 是否显示更新弹窗
    showDiffDrawer: false,       // 是否显示差异抽屉
    showLogDrawer: false,        // 是否显示日志抽屉
    showTestDrawer: false,       // 是否显示测试抽屉
    showRuleDrawer: false,       // 是否显示规则抽屉
    showProfileDrawer: false,    // 是否显示环境抽屉
    showModAliasReviewModal: false,    // 是否显示模组别名检阅弹窗
    showAIDefinitionManager: false,    // 是否显示 AI 定义管理器
    showWorkspace: false,        // 是否显示工坊更新管理中心
    showTextureOptModal: false,  // 是否显示贴图优化弹窗
    showModSettingsManager: false, // 是否显示模组配置弹窗
    showModResidueCleanup: false, // 是否显示卸载残留清理弹窗
    showFileSearchWorkbench: false, // 是否显示文件内容搜索工作台
    showPackageTransferDialog: false, // 是否显示模组包/数据包传输弹窗
    showRecommendationExportDialog: false, // 是否显示推荐导出弹窗
  })
  const packageTransferDialog = reactive({
    mode: 'mod-import',
    preset: {},
  })
  // 推荐导出弹窗只保存入口上下文，真正的模组详情在弹窗打开时从 modStore 读取最新值。
  const recommendationExportDialog = reactive({
    title: '推荐导出',
    sourceName: '已选模组',
    modIds: [],
  })
  // 存储各个列表的滚动偏移量
  // Key: listId (如 'active', 'inactive', 'temp'), Value: Number
  const scrollRegistry = ref(new Map());

  // 更新相关状态
  const updateState = reactive({
    hasUpdate: false,
    info: null,    // 存储后端返回的 UpdateInfo
    isChecking: false,
  })
  const remoteImageCache = reactive({
    file_count: 0,
    total_bytes: 0,
  })
  const translationProviders = ref([{ id: 'ai.default', label: 'AI 翻译', type: 'ai' }])
  const isTranslationProvidersLoaded = ref(false)
  const cancelPendingTaskIds = ref(new Set())
  const cancelPendingTimers = new Map()
  const CANCELLATION_PENDING_TIMEOUT_MS = 15000
  let suspendRecoveryTimer = null
  let suspendRecoveryPromise = null
  let modResidueCheckTimer = null

  const upgradeContext = ref({}); // 升级上下文
  let modEnrichmentRequestVersion = 0

  const createDefaultTranslationSettings = () => ({
    default: {
      target_language: 'follow_ui',
      provider: 'ai.default',
    },
    workshop_detail: {
      target_language: 'default',
      provider: 'default',
      prefer_ui_language_translation: true,
      auto_translate_missing: false,
      source_detection: { enabled: false, mode: 'or', terms: [] },
    },
  })

  const normalizeTranslationSettings = (value = {}) => {
    const defaults = createDefaultTranslationSettings()
    const source = value && typeof value === 'object' ? value : {}
    const globalDefault = source.default && typeof source.default === 'object' ? source.default : {}
    const workshopDetail = source.workshop_detail && typeof source.workshop_detail === 'object' ? source.workshop_detail : {}
    const sourceDetection = workshopDetail.source_detection && typeof workshopDetail.source_detection === 'object' ? workshopDetail.source_detection : {}
    const normalized = {
      ...source,
      default: {
        ...defaults.default,
        ...globalDefault,
      },
      workshop_detail: {
        ...defaults.workshop_detail,
        ...workshopDetail,
        source_detection: {
          ...defaults.workshop_detail.source_detection,
          ...sourceDetection,
          terms: Array.isArray(sourceDetection.terms) ? sourceDetection.terms.map(item => String(item || '').trim()).filter(Boolean) : [],
          mode: String(sourceDetection.mode || '').toLowerCase() === 'and' ? 'and' : 'or',
          enabled: !!sourceDetection.enabled,
        },
      },
    }
    delete normalized.defaults
    delete normalized.scopes
    return normalized
  }

  const ensureTranslationSettingsShape = () => {
    settings.value.translation = normalizeTranslationSettings(settings.value.translation)
    return settings.value.translation
  }

  const getTranslationFeatureSettings = (feature = 'workshop_detail') => {
    const translation = normalizeTranslationSettings(settings.value.translation)
    const defaults = createDefaultTranslationSettings()
    const globalDefault = translation.default || defaults.default
    const fallback = defaults[feature] && typeof defaults[feature] === 'object' ? defaults[feature] : {}
    const featureSettings = translation[feature] && typeof translation[feature] === 'object' ? translation[feature] : {}
    const merged = { ...globalDefault, ...fallback, ...featureSettings }
    const targetLanguage = String(merged.target_language || '').trim()
    const provider = String(merged.provider || '').trim()
    return {
      ...merged,
      target_language: !targetLanguage || targetLanguage === 'default' ? globalDefault.target_language : targetLanguage,
      provider: !provider || provider === 'default' ? globalDefault.provider : provider,
    }
  }

  const saveTranslationFeatureSettings = async (feature = 'workshop_detail', patch = {}) => {
    const translation = ensureTranslationSettingsShape()
    translation[feature] = {
      ...(translation[feature] || {}),
      ...(patch && typeof patch === 'object' ? patch : {}),
    }
    await saveSetting('translation', translation)
    return translation[feature]
  }

  // 定义侧边栏标签配置 (ID 与 标题绑定)
  const SIDEBAR_TABS = [
    { id: 'temp', title: '临时' },
    { id: 'disabled', title: '禁用' },
    { id: 'group', title: '分组' },
    { id: 'backup', title: '备份' }
  ]
  // 响应式状态：当前选中的标签 ID
  const activeSidebarTab = ref('temp')

  // 定义默认布局配置
  const DEFAULT_DETAILS_LAYOUT = [
    { id: 'basic_info', visible: true }, // 包ID、作者、链接、路径
    { id: 'files_info', visible: true },  // 文件统计
    { id: 'time_info', visible: true },  // 其它信息
    { id: 'relations_info', visible: true },  // 依赖关系
    { id: 'user_info', visible: true }, // 标签、备注、分组
    { id: 'description', visible: true }, // Mod 描述
  ]
  const DETAILS_LAYOUT_MAPS = {
    basic_info: {label: '基础信息', desc:'控制详情页中 Mod 作者及来源板块的显示。'},
    files_info: {label: '文件统计', desc:'控制详情页中 Mod 文件统计板块的显示。'},
    time_info: {label: '其它信息', desc:'控制详情页中 Mod 其它信息板块的显示。'},
    relations_info: {label: '依赖关系', desc:'控制详情页中 Mod 依赖板块的显示。'},
    user_info: {label: '自定义信息', desc:'控制详情页中 Mod 自定义信息板块的显示。'},
    description: {label: 'Mod描述', desc:'控制详情页中 Mod 说明板块的显示。'},
  }
  const DEFAULT_MAIN_LAYOUT = [
    { id: 'details', visible: true }, // Mod 详情面板
    { id: 'library', visible: true }, // Mod 停用列表
    { id: 'active', visible: true },  // Mod 启用列表
    { id: 'sidebar', visible: true },  // 侧边功能栏
  ]
  const MAIN_LAYOUT_MAPS = {
    details: {label: 'Mod详情', desc:'控制主界面中 Mod 详情面板的显示。'},
    library: {label: '停用列表', desc:'控制主界面中 Mod 停用列表的显示。'},
    active: {label: '启用列表', desc:'控制主界面中 Mod 启用列表的显示。'},
    sidebar: {label: '侧边栏', desc:'控制主界面中侧边功能栏的显示。'},
  }

  // 全局设置
  const settings = ref({
    // --- 路径 (Paths) ---
    home_path: '',
    steam_path: '',
    steamcmd_mods_path: '',
    workshop_mods_path: '',
    self_mods_path: '',
    ripgrep_path: '',
    move_old_self_mods: false,
    enable_tool_mods: false,  // 是否启用工具 Mod
    link_deployment_mode_full: false,  // 链接部署模式: true=完全重建, false=增量部署

    user_rules_path: '',
    community_rules_url: '',
    community_rules_path: '',
    git_provider_catalog_url: '',
    community_workshop_db_url: '',
    community_workshop_db_path: '',
    community_instead_db_url: '',
    community_instead_db_path: '',

    current_profile_id: 'default',
    browser_mode: false,
    auto_enter_silent_mode: true,
    silent_mode_default_view: 'home',
    asset_port: 0,

    // --- 系统 ---
    language: 'zh-CN',
    window_width: 1400,
    window_height: 900,
    completed_guides: [],
    open_url_on_system: false,

    // --- 界面（UI） ---
    ui: {
      theme_id: DEFAULT_THEME_ID,
      font_size: 14,
      drag_delay: 30,            // 拖动判定延迟 (毫秒)
      detail_delay: 300,          // 详情页加载延迟 (毫秒)
      tooltip_hover_time: 1000,  // 鼠标悬停显示提示时间 (毫秒)
      show_mod_hover_panel: true,  // 是否显示 Mod 悬停面板
      show_ai_assistant: true,  // 是否显示 AI 助手入口
      show_ai_assistant_fab: true,  // 是否显示 AI 助手悬浮球
      double_click_active_mod: true,  // 是否双击启用/停用 Mod
      main_layout: deepClone(DEFAULT_MAIN_LAYOUT),  // 主界面布局配置

      show_icons_cloud: true,  // 是否显示动态图标云
      mod_details_layout: deepClone(DEFAULT_DETAILS_LAYOUT),   // Mod 详情面板布局配置

      show_dependency_graph: true,  // 是否显示依赖关系图
      smooth_list_target_scroll: true,  // 定位到列表项时是否使用平滑滚动
      hidden_dependency_graph_source_ids: [],  // 全局隐藏的依赖源包名列表
      keybindings: { version: 1, bindings: {}, disabledDefaults: {} },  // 用户自定义快捷键覆盖配置
      enable_active_section_collapse: false,  // 是否启用启用列表标题分组折叠
      enable_inactive_section_collapse: false,  // 是否启用停用列表标题分组折叠
      default_collapse_active_sections: false,  // 若当前环境/启用列表还没有保存过折叠状态，首次是否默认折叠
      default_collapse_inactive_sections: false,  // 若当前环境/停用列表还没有保存过折叠状态，首次是否默认折叠
      persist_temp_mod_list: false,  // 是否按环境保存临时列表
      show_list_index: true,  // 是否显示列表索引列
      show_list_icon: true,       // 是否显示 Mod 图标
      show_list_mod_icon: true,       // 是否显示 Mod 图标
      show_list_modtype_icon: true,  // 是否显示 Mod 类型图标

      show_group_index: true,  // 是否显示分组索引列
      show_group_icon: true,  // 是否显示分组图标

    },

    // --- 网络 (Network) - 深度嵌套 ---
    network: {
      proxy: {
        enabled: false,
        type: 'http',
        host: '',
        port: 0,
        username: '',
        password: '',
        bypass_list: ['127.0.0.1', 'localhost']
      },
      hosts: {},                      // Object: { 'domain': 'ip' }
      write_to_system_hosts: false,   // 是否将自定义 Hosts 写入系统 hosts 文件
      use_proxy_on_steamcmd: false,   // SteamCMD 是否使用代理
      use_proxy_on_ai: false          // AI 是否使用代理
    },

    // --- AI ---
    ai: {
      enabled: false,
      provider: 'openai_compatible',
      base_url: '',
      api_key: '',
      model: 'gpt-3.5-turbo',
      temperature: 0.7,
      max_output_tokens: 0,
      max_input_tokens: 0,
      context_window_tokens: 0,
      max_concurrency: 3,     // 最大并发请求数（避免被API封锁）
    },
    translation: {
      default: {
        target_language: 'follow_ui',
        provider: 'ai.default',
      },
      workshop_detail: {
        target_language: 'default',
        provider: 'default',
        prefer_ui_language_translation: true,
        auto_translate_missing: false,
        source_detection: { enabled: false, mode: 'or', terms: [] },
      },
    },
    enable_steam_enhanced_api: false,
    steam_web_api_key: '',
    _secret_status: {},

    // --- 贴图优化 ---
    texture_opt: {
      texture_tools_path: "",       // 贴图工具目录
      process_mode: 'scaled_only_overwrite',
      output_format: 'dds',         // 输出格式：dds 或 zstd
      generate_mipmaps: true,       // 是否生成远近层级
      scale_factor: 0.5,            // 缩放比例
      max_size: 128,                // 最低清晰度
      skip_small_textures: true,    // 超出建议范围时不参与缩放
      min_dimension: 128,           // 最短边低于该值时不参与缩放
      max_source_dimension: 2048,   // 最长边高于该值时不参与缩放
      zstd_clean_old_dds: false,    // 生成 ZSTD 成功后是否清理旧 DDS
      clean_output_format: 'dds',   // 清理格式：dds 或 zstd
    },

    // --- 高级 (Advanced) ---
    backup_retention_days: 30,
    enable_auto_scan: true,
    enable_file_size_scan: true,         // 扫描时是否检查文件大小
    enable_mod_residue_scan: true,       // 扫描时是否识别卸载残留
    startup_inventory_prompt_new_only: false, // 启动库存提醒是否只显示新发现的问题
    strict_disabled_mode: false,         // 扫描时是否按禁用记录自动恢复被外部启用的 Mod
    delete_missing_mods_data: false,
    auto_sort_strategy: "classic_sort_logic",  // 自动排序策略
    sort_mods_by: "name",                 // 自动排序排列方式: name, id, alias
    coexist_mod_folder_name_type: "workshop_id", // 共存Mod生成方式: workshop_id, package_id, name, alias
    bundle_mod_folder_name_type: "default", // 模组包内文件夹命名方式
    show_coexistence_message: true,       // 是否显示共存Mod提示
    enable_action_prechecks: true,        // 关键动作前是否执行启用/安装检查
    check_language_support: true,        // 是否检查语言支持
    skip_language_pack_alias_generation: true, // 批量生成别名备注时是否跳过语言包
    regular_mods_follow_dependencies: false, // 普通模组是否贴紧其最后一个依赖目标
    language_packs_follow_targets: false, // 语言包是否贴紧其最后一个前置/依赖目标

    // --- 调试 (Debug) ---
    debug_mode: true,
    log_retention_days: 7,
    log_level: 'INFO',
    enable_auto_update_check: true,  // 自动检查更新开关
    ignored_update_version: '',       // 跳过的版本号
    last_update_check_time: 0,      // 上次检查时间（用于限流）
    enable_auto_tool_check: true,
    tool_check_interval_days: 3,
    last_tool_check_time: 0,
    enable_auto_external_data_update_check: true,
    enable_silent_external_data_update: false,
    external_data_update_check_interval_days: 1,
    last_external_data_update_check_time: 0,
    enable_auto_steamcmd_mod_update_check: true,
    steamcmd_mod_update_check_interval_days: 1,
    last_steamcmd_mod_update_check_time: 0,

  })
  const userThemes = ref([])
  const themes = computed(() => mergeThemes(userThemes.value))
  const currentTheme = computed(() => findThemeById(themes.value, settings.value.ui?.theme_id || DEFAULT_THEME_ID))
  const themeEditor = reactive({
    isOpen: false,
    theme: null,
  })

  const applyCurrentTheme = () => {
    applyTheme(currentTheme.value)
  }

  const {
    // 路径检测
    autoDetectPaths, getDefaultExternalPaths, checkPath, checkPaths,
    // 打开、选择与删除
    openPath, openFile, readTextFile, getFilePath, getFolderPath, deletePath, deletePaths, openUrl,
  } = usePathActions({
    settings,
    requestModScan: (...args) => requestModScan(...args),
  })

  const {
    // 设置面板
    openSettingsPanel, closeSettingsPanel,
    // 设置保存与主题
    saveSetting, applySettings, revealSecret, clearSecret, refreshUserThemes, saveUserTheme, deleteUserTheme,
  } = useSettingsActions({
    settings,
    uiState,
    isLoading,
    userThemes,
    applyCurrentTheme,
    syncRemoteImageCache: (...args) => syncRemoteImageCache(...args),
    refreshData: (...args) => refreshData(...args),
    requestModScan: (...args) => requestModScan(...args),
  })

  const {
    // 弹窗入口
    openPackageTransferDialog, openCustomModExportDialog, updatePackageTransferDialogPreset, closePackageTransferDialog,
    // 导入导出后续动作
    applyModPackageImportPostActions, showExportCompleteDialog,
    // 数据包
    getDataBundleSchema, inspectDataBundle, exportDataBundle, importDataBundle,
    // 模组包
    getModPackageSchema, prepareModPackageImport, getModPackageProfileSummary, exportModPackage, importModPackage,
  } = usePackageTransferActions({
    uiState,
    packageTransferDialog,
    isLoading,
    settings,
    taskStore,
    openPath,
    refreshData: (...args) => refreshData(...args),
    requestModScan: (...args) => requestModScan(...args),
  })

  const openRecommendationExportDialog = ({
    title = '推荐导出',
    sourceName = '已选模组',
    modIds = [],
  } = {}) => {
    // 右键菜单、分组列表等入口都可能传入重复 ID，打开弹窗前先收敛成稳定的导出列表。
    const normalizedModIds = [...new Set(
      (modIds || []).map(id => String(id || '').trim()).filter(Boolean)
    )]
    recommendationExportDialog.title = String(title || '推荐导出')
    recommendationExportDialog.sourceName = String(sourceName || '已选模组')
    recommendationExportDialog.modIds = normalizedModIds
    uiState.showRecommendationExportDialog = true
  }

  const closeRecommendationExportDialog = () => {
    // 关闭时清掉上一次选择，避免下次打开弹窗时短暂显示旧的导出对象。
    uiState.showRecommendationExportDialog = false
    recommendationExportDialog.title = '推荐导出'
    recommendationExportDialog.sourceName = '已选模组'
    recommendationExportDialog.modIds = []
  }

  const {
    // 工坊打开
    openSteamWorkshopUrl, openSteamWorkshopById, openInstallSource,
    // 订阅与下载
    downloadWorkshopItems, subscribeInstallSources, downloadInstallSources,
    downloadPackageIds, subscribePackageIds, subscribeWorkshopIds, unsubscribeWorkshopIds,
    downloadWorkshopItemsViaSteam, querySteamWorkshopDetails,
    // 合集
    getCollectionItems,
  } = useSteamWorkshopActions({
    openUrl,
  })

  const {
    // 日志与调度
    logMaintenanceCheck, runScheduledMaintenanceChecks,
    // 检查入口
    checkSteamTools, checkToolMaintenance, checkExternalDataUpdates, checkManagedModUpdates, checkSteamcmdModUpdates,
    // 更新动作
    updateExternalDB,
  } = useMaintenanceActions({
    settings,
    waitForDownload: (...args) => waitForDownload(...args),
    refreshData: (...args) => refreshData(...args),
    refreshModsData: (...args) => refreshModsData(...args),
    refreshModCoreData: (...args) => refreshModCoreData(...args),
    downloadWorkshopItems: (...args) => downloadWorkshopItems(...args),
  })

  const {
    // 更新检查与安装提示
    checkUpdate, showChangelog, _showInstallPrompt,
  } = useUpdateActions({
    updateState,
    upgradeContext,
    isLoading,
    uiState,
    logMaintenanceCheck,
  })


  // === Getters ===
  const isDownloading = computed(() => taskStore.hasActiveTaskOfType(['download', 'update', 'steamcmd-download', 'steam-workshop-download']))
  const isScanRunning = computed(() => taskStore.hasActiveTaskOfType('scan'))
  const updateInstallPrompted = new Set()
  const exportCompletePrompted = new Set()
  const pendingModScanRequested = ref(null)
  // 记录当前扫描请求的列表保留策略，等扫描完成事件回来时再交给 Mod Store。
  const activeModScanRequest = ref(null)
  // 这里只保留后端已实现“真实终止点”的任务类型，避免按钮可点但实际上无法取消。
  const cancellableTaskTypes = new Set([
    'scan',
    'download',
    'update',
    'localize',
    'mod-import',
    'mod-export',
    'steamcmd-download',
    'steamcmd-init',
    'steam-subscribe',
    'steam-unsubscribe',
    'steam-workshop-download',
    'texture-opt',
    'texture-opt-analyze',
    'ai-task',
    'file-search',
  ])

  const isTaskCancelPending = (taskId = '') => cancelPendingTaskIds.value.has(String(taskId || ''))

  const clearTaskCancelPending = (taskId = '') => {
    const normalizedTaskId = String(taskId || '')
    if (!normalizedTaskId) return
    const timer = cancelPendingTimers.get(normalizedTaskId)
    if (timer) {
      clearTimeout(timer)
      cancelPendingTimers.delete(normalizedTaskId)
    }
    if (!cancelPendingTaskIds.value.has(normalizedTaskId)) return
    const next = new Set(cancelPendingTaskIds.value)
    next.delete(normalizedTaskId)
    cancelPendingTaskIds.value = next
  }

  const markTaskCancelPending = (taskId = '') => {
    const normalizedTaskId = String(taskId || '')
    if (!normalizedTaskId) return
    const next = new Set(cancelPendingTaskIds.value)
    next.add(normalizedTaskId)
    cancelPendingTaskIds.value = next
    const existingTimer = cancelPendingTimers.get(normalizedTaskId)
    if (existingTimer) clearTimeout(existingTimer)
    const timer = window.setTimeout(() => clearTaskCancelPending(normalizedTaskId), CANCELLATION_PENDING_TIMEOUT_MS)
    cancelPendingTimers.set(normalizedTaskId, timer)
  }

  const supportsTaskCancellation = (task) => {
    const type = String(task?.type || '')
    const status = String(task?.status || '')
    return ['pending', 'running'].includes(status) && cancellableTaskTypes.has(type)
  }

  const canCancelTask = (task) => supportsTaskCancellation(task) && !isTaskCancelPending(task?.id)

  // 监听字体大小变化，实时更新根字号
  watch(() => settings.value.ui.font_size, (newSize) => {
    // 将根字号设置为用户定义的数值
    // 默认 14px，用户调大到 16px，所有使用 rem 的组件都会等比例变大
    document.documentElement.style.fontSize = `${newSize}px`;
  }, { immediate: true });
  watch(() => settings.value.debug_mode, (enabled) => {
    // 让通用 checkResult 感知当前调试开关，避免 appStore 再维护一份重复实现。
    if (typeof window !== 'undefined') {
      window.__APP_DEBUG_MODE__ = !!enabled
    }
  }, { immediate: true });
  watch(currentTheme, (theme) => {
    applyTheme(theme)
  }, { immediate: true, deep: true })
  // 像素值缩放函数
  const scalePx = (basePx, defaultFontSize = 16) => {
    if (!settings.value.ui.font_size) return basePx;
    // 核心公式
    const scaled = basePx * (settings.value.ui.font_size / defaultFontSize);
    // 返回四舍五入后的整数，防止某些库对浮点数支持不佳导致抖动
    return Math.round(scaled);
  };

  // === Utils ===
  // 等待后端就绪
  const waitForBackend = () => {
    return new Promise((resolve) => {
      // 情况 1: 如果 API 已经存在（前端加载慢，后端已经注入了），直接继续
      if (window.pywebview) resolve()
      // 情况 2: API 还没来（前端加载快），监听 pywebviewready 事件, { once: true } 确保只触发一次
      else window.addEventListener('pywebviewready', () => resolve(), { once: true })
    })
  }

  const notifyFrontendReady = async () => {
    if (window.pywebview?.api?.monitor_frontend_ready) {
      await window.pywebview.api.monitor_frontend_ready()
    }
  }

  const syncRemoteImageCache = (cacheStats = {}) => {
    // 统一整理后端返回的缓存统计，避免各入口分别处理默认值。
    remoteImageCache.file_count = Number(cacheStats?.file_count || 0)
    remoteImageCache.total_bytes = Number(cacheStats?.total_bytes || 0)
  }

  const setRuntimeSession = (session = {}) => {
    runtimeSession.value = {
      ...createDefaultRuntimeSession(),
      ...(session || {}),
    }
    isGameRunning.value = runtimeSession.value.state === 'running'
  }

  const applyModsPayload = (payload, { isInit = false, historyLabel = '刷新磁盘状态', preserveListState = false } = {}) => {
    if (!payload) return false

    const groupStore = useGroupStore()
    groupStore.setGroups(payload.groups || [])

    const modStore = useModStore()
    modEnrichmentRequestVersion += 1
    // 保留列表状态的刷新只替换模组主数据，不进入三列表撤销历史。
    const previousSnapshot = isInit || preserveListState ? null : modStore.captureListHistorySnapshot()
    modStore.setMods(payload, { resetHistory: !!isInit, preserveListState })
    if (!preserveListState && previousSnapshot) {
      modStore.recordListHistory({
        before: previousSnapshot,
        type: 'refresh-data',
        label: historyLabel,
      })
    }

    return true
  }

  const applyInitialPayload = (payload, { isInit = false, historyLabel = '刷新磁盘状态' } = {}) => {
    if (!payload) return false

    if (isInit && payload.settings) {
      settings.value = payload.settings
      settings.value.asset_port = payload.asset_port || 0
      upgradeContext.value = payload.upgrade_context
    } else if (payload.settings) {
      Object.assign(settings.value, payload.settings)
    }
    if (payload.settings) {
      settings.value.translation = normalizeTranslationSettings(settings.value.translation)
      settingsReady.value = true
    }
    if (Array.isArray(payload.user_themes)) {
      userThemes.value = payload.user_themes
    }
    applyCurrentTheme()

    syncRemoteImageCache(payload.remote_image_cache)
    if (payload.is_first_db_init && payload.context_healthy && (!payload.all_mods || payload.all_mods?.length === 0)) {
      toast.warning("数据库正在进行首次初始化，此过程可能需要您等待一段时间，请您耐心等候。",{position: "top-center",timeout: 10000})
    }

    appVersion.value = payload.app_version || 'Unknown'
    buildMode.value = payload.build_mode || ''
    setRuntimeSession(payload.runtime_session)

    const profileStore = useProfileStore()
    profileStore.fetchProfiles()
    if (payload.active_context) {
      profileStore.activeContext = payload.active_context
      if (!profileStore.activeContext.is_healthy) {
        toast.warning("需要确认路径配置。已自动搜索到的路径会填入设置面板，请确认后保存。",{position: "top-center",timeout: 5000})
        uiState.showSettingsPanel = true
        return false
      }
    }

    return applyModsPayload(payload, { isInit, historyLabel })
  }

  const applyStartupBootstrapPayload = (payload) => {
    if (!payload) return false

    if (payload.settings) {
      settings.value = payload.settings
      settings.value.asset_port = payload.asset_port || 0
      settings.value.translation = normalizeTranslationSettings(settings.value.translation)
      settingsReady.value = true
    }
    upgradeContext.value = payload.upgrade_context || {}
    if (Array.isArray(payload.user_themes)) {
      userThemes.value = payload.user_themes
    }
    applyCurrentTheme()
    syncRemoteImageCache(payload.remote_image_cache)
    appVersion.value = payload.app_version || 'Unknown'
    buildMode.value = payload.build_mode || ''
    setRuntimeSession(payload.runtime_session)

    const profileStore = useProfileStore()
    profileStore.fetchProfiles()
    if (payload.active_context) {
      profileStore.activeContext = payload.active_context
      if (!profileStore.activeContext.is_healthy) {
        toast.warning("需要确认路径配置。已自动搜索到的路径会填入设置面板，请确认后保存。",{position: "top-center",timeout: 5000})
        uiState.showSettingsPanel = true
        // 路径未配置时仍要完成前端 ready，否则设置保存后触发的扫描事件会被后端事件总线丢弃。
        return true
      }
    }
    return true
  }

  const loadStartupCoreData = async () => {
    if (!window.pywebview) return false
    startupPerfMark('startup_core_data_start')
    const bootstrapRes = await startupPerfMeasure('startup.get_startup_bootstrap', () => window.pywebview.api.get_startup_bootstrap())
    if (!checkResult(bootstrapRes, '加载启动配置')) return false
    if (!applyStartupBootstrapPayload(bootstrapRes.data)) return false

    const coreRes = await startupPerfMeasure('startup.get_mod_list_core', () => window.pywebview.api.get_mod_list_core())
    if (!checkResult(coreRes, '加载模组列表')) return false
    if (coreRes.data?.is_first_db_init && coreRes.data?.context_healthy && (!coreRes.data?.all_mods || coreRes.data.all_mods.length === 0)) {
      toast.warning("数据库正在进行首次初始化，此过程可能需要您等待一段时间，请您耐心等候。",{position: "top-center",timeout: 10000})
    }
    const applied = applyModsPayload(coreRes.data, { isInit: true, historyLabel: '启动加载核心数据' })
    startupPerfMark('startup_core_data_done')
    return applied
  }

  const refreshRuleData = async (options = {}) => {
    const ruleStore = useRuleStore()
    return await ruleStore.fetchRules(options)
  }

  const refreshBackupData = (options = {}) => {
    const orderStore = useOrderStore()
    const promise = orderStore.getBackups(orderStore.backupProfileId || settings.value.current_profile_id || 'default', options)
    void promise
    return promise
  }

  const refreshWorkspaceLibraryData = () => {
    const workspaceStore = useWorkspaceStore()
    // 扫描只会改变本地三库模组事实，不需要顺带刷新 GitHub/合集列表。
    void workspaceStore.refreshLoadedData({ librariesOnly: true })
  }

  const refreshModsRelatedData = async (options = {}) => {
    if (options?.refreshRules !== false) await refreshRuleData()
    if (options?.refreshBackups !== false) refreshBackupData()
    if (options?.refreshWorkspaceLibraries !== false) refreshWorkspaceLibraryData()
  }

  const refreshModEnrichment = async ({ silent = false } = {}) => {
    if (!window.pywebview) return false
    const requestVersion = ++modEnrichmentRequestVersion
    try {
      const res = await startupPerfMeasure('refresh_mod_enrichment.get_mod_list_enrichment', () => window.pywebview.api.get_mod_list_enrichment())
      if (!checkResult(res, '补充列表标记', false, { silent })) return false
      if (requestVersion !== modEnrichmentRequestVersion) {
        startupPerfMark('refresh_mod_enrichment_skipped_stale')
        return false
      }
      const modStore = useModStore()
      modStore.mergeModEnrichment(res.data || {})
      startupPerfMark('refresh_mod_enrichment_done', { mods: Object.keys(res.data?.mods || {}).length })
      return true
    } catch (e) {
      if (!silent) toast.error(toUserMessage(e?.message || e, '补充列表标记失败。部分问题提示、替代版本或联机兼容状态可能暂时不显示。'))
      return false
    }
  }

  const refreshModCoreData = async (historyLabel = '同步模组核心数据', options = {}) => {
    if (!window.pywebview) return false
    startupPerfMark('refresh_mod_core_data_start', { historyLabel })
    try {
      const res = await startupPerfMeasure('refresh_mod_core_data.get_mod_list_core', () => window.pywebview.api.get_mod_list_core(), { historyLabel })
      if (!checkResult(res, '同步模组核心数据')) return false
      const applied = applyModsPayload(res.data, {
        isInit: false,
        historyLabel,
        preserveListState: !!options?.preserveListState,
      })
      if (!applied) return false
      if (options?.refreshRelated !== false) {
        await startupPerfMeasure('refresh_mod_core_data.related_data', () => refreshModsRelatedData(options), { historyLabel })
      }
      if (options?.refreshEnrichment !== false) {
        void refreshModEnrichment({ silent: true })
      }
      startupPerfMark('refresh_mod_core_data_done', { historyLabel })
      return true
    } catch (e) {
      toast.error(toUserMessage(e?.message || e, '同步模组核心数据失败。可能是数据库、扫描结果或运行环境暂时不可用，详细原因已写入系统日志。'))
      return false
    }
  }

  const loadStartupInventorySummary = async ({ silent = false } = {}) => {
    if (!window.pywebview) return []
    const res = await startupPerfMeasure('startup.workspace_inventory_summary', () => window.pywebview.api.workspace_get_startup_inventory_summary())
    if (!checkResult(res, '启动库存检测', false, { silent })) return false
    const workspaceStore = useWorkspaceStore()
    return workspaceStore.applyStartupInventorySummary(res.data || {})
  }

  // 扫描完成后只同步与模组相关的数据，避免再次触发整套工作区/集合/GitHub 初始化。
  const refreshModsData = async (historyLabel = '扫描后同步模组数据', options = {}) => {
    if (!window.pywebview) return false
    startupPerfMark('refresh_mods_data_start', { historyLabel })
    try {
      const res = await startupPerfMeasure('refresh_mods_data.get_initial_data', () => window.pywebview.api.get_initial_data(), { historyLabel })
      if (!checkResult(res, '同步模组数据')) return false
      const applied = applyModsPayload(res.data, {
        isInit: false,
        historyLabel,
        preserveListState: !!options?.preserveListState,
      })
      if (!applied) return false

      await startupPerfMeasure('refresh_mods_data.related_data', () => refreshModsRelatedData(options), { historyLabel })
      startupPerfMark('refresh_mods_data_done', { historyLabel })
      return true
    } catch (e) {
      toast.error(toUserMessage(e?.message || e, '同步模组数据失败。可能是数据库、扫描结果或运行环境暂时不可用，详细原因已写入系统日志。'))
      return false
    }
  }

  const requestModScan = async ({ forcedUpdate = false, specificPaths = null, preserveListState = false, sizeCheckOverride = null, sizeCheckPaths = null, startupWorkshopChanges = null, refreshRules = true, refreshBackups = true, refreshWorkspaceLibraries = true, silentSuccess = false } = {}) => {
    // 多次扫描请求合并时，任意一次要求保留列表状态，最终扫描完成也要保留。
    const normalizeScanRequest = (request = {}) => {
      const normalizedPaths = Array.isArray(request.specificPaths)
        ? request.specificPaths.map(path => String(path || '').trim()).filter(Boolean)
        : null
      return {
        forcedUpdate: !!request.forcedUpdate,
        specificPaths: normalizedPaths && normalizedPaths.length > 0 ? [...new Set(normalizedPaths)] : null,
        preserveListState: !!request.preserveListState,
        sizeCheckOverride: request.sizeCheckOverride == null ? null : !!request.sizeCheckOverride,
        sizeCheckPaths: Array.isArray(request.sizeCheckPaths)
          ? [...new Set(request.sizeCheckPaths.map(path => String(path || '').trim()).filter(Boolean))]
          : [],
        startupWorkshopChanges: Array.isArray(request.startupWorkshopChanges)
          ? request.startupWorkshopChanges
          : [],
        refreshRules: request.refreshRules !== false,
        refreshBackups: request.refreshBackups !== false,
        refreshWorkspaceLibraries: request.refreshWorkspaceLibraries !== false,
        silentSuccess: !!request.silentSuccess,
      }
    }
    const mergeScanRequest = (left, right) => {
      if (!left) return right
      if (!right) return left
      return {
        forcedUpdate: !!(left.forcedUpdate || right.forcedUpdate),
        specificPaths: (!left.specificPaths || !right.specificPaths)
          ? null
          : [...new Set([...left.specificPaths, ...right.specificPaths])],
        preserveListState: !!(left.preserveListState || right.preserveListState),
        sizeCheckOverride: left.sizeCheckOverride === true || right.sizeCheckOverride === true
          ? true
          : (left.sizeCheckOverride === false || right.sizeCheckOverride === false ? false : null),
        sizeCheckPaths: [...new Set([...(left.sizeCheckPaths || []), ...(right.sizeCheckPaths || [])])],
        startupWorkshopChanges: [...(left.startupWorkshopChanges || []), ...(right.startupWorkshopChanges || [])],
        refreshRules: left.refreshRules !== false || right.refreshRules !== false,
        refreshBackups: left.refreshBackups !== false || right.refreshBackups !== false,
        refreshWorkspaceLibraries: left.refreshWorkspaceLibraries !== false || right.refreshWorkspaceLibraries !== false,
        silentSuccess: !!(left.silentSuccess && right.silentSuccess),
      }
    }
    const scanRequest = normalizeScanRequest({ forcedUpdate, specificPaths, preserveListState, sizeCheckOverride, sizeCheckPaths, startupWorkshopChanges, refreshRules, refreshBackups, refreshWorkspaceLibraries, silentSuccess })
    if (isScanRunning.value) {
      pendingModScanRequested.value = mergeScanRequest(pendingModScanRequested.value, scanRequest)
      return false
    }

    pendingModScanRequested.value = null
    // 扫描任务本身不带前端选项，先暂存在这里，等 scan-complete 事件回来再使用。
    activeModScanRequest.value = scanRequest
    const modStore = useModStore()
    const started = await modStore.scanMods(scanRequest.specificPaths, scanRequest.forcedUpdate, scanRequest.sizeCheckOverride, scanRequest.sizeCheckPaths)
    if (!started) activeModScanRequest.value = null
    return !!started
  }

  const flushQueuedModScan = async () => {
    if (!pendingModScanRequested.value || isScanRunning.value) return false
    const queuedRequest = pendingModScanRequested.value
    pendingModScanRequested.value = null
    // 延迟扫描同样要保留原始请求选项，避免排队后丢失列表状态策略。
    activeModScanRequest.value = queuedRequest
    const modStore = useModStore()
    const started = await modStore.scanMods(queuedRequest.specificPaths, queuedRequest.forcedUpdate, queuedRequest.sizeCheckOverride, queuedRequest.sizeCheckPaths)
    if (!started) activeModScanRequest.value = null
    return !!started
  }

  const recoverFromSuspendedState = async () => {
    if (suspendRecoveryPromise) return suspendRecoveryPromise

    suspendRecoveryPromise = (async () => {
      try {
        const clearedScanTasks = taskStore.settleActiveTasks('scan', {
          status: 'cancelled',
          message: '扫描因界面挂起而中断，请重新刷新。',
          metrics: { resumed_after_suspend: true },
        })
        if (clearedScanTasks > 0) {
          toast.info('已清理挂起前遗留的扫描任务，请按需重新刷新。', { timeout: 2500 })
        }

        await waitForBackend()
        if (window.pywebview?.api?.monitor_frontend_ready) {
          await window.pywebview.api.monitor_frontend_ready()
        }
        const orderStore = useOrderStore()
        const resumeSnapshot = orderStore.captureRuntimeRefreshSnapshot()
        await refreshData(false, '游戏退出后刷新磁盘状态')
        await orderStore.presentRuntimeRefreshDiff(resumeSnapshot)
      } catch (e) {
        console.error("恢复挂起界面失败:", e)
        toast.error(toUserMessage(e?.message || e, '恢复界面失败。请刷新界面或重启软件后重试，详细原因已写入系统日志。'))
      } finally {
        isLoading.value = false
        suspendRecoveryPromise = null
      }
    })()

    return suspendRecoveryPromise
  }

  const scheduleModResidueCheck = (delayMs = 4500) => {
    if (modResidueCheckTimer) clearTimeout(modResidueCheckTimer)
    modResidueCheckTimer = window.setTimeout(() => {
      modResidueCheckTimer = null
      if (isScanRunning.value || pendingModScanRequested.value) {
        scheduleModResidueCheck(3000)
        return
      }
      void (async () => {
        try {
          const residueStore = useModResidueStore()
          const overview = await startupPerfMeasure('post_scan.mod_residue_overview', () => residueStore.loadOverview({ silent: true }))
          startupPerfMark('post_scan.mod_residue_done', {
            items: Number(overview?.summary?.item_count || 0),
            groups: Number(overview?.summary?.group_count || 0),
          })
          if (overview?.summary?.item_count > 0) uiState.showModResidueCleanup = true
          if (!overview && window.pywebview?.api?.mod_residue_get_overview) {
            toast.warning('卸载残留检查未完成，可稍后手动打开残留清理。', { timeout: 3000 })
          }
        } catch (error) {
          console.warn('卸载残留检测失败:', error)
          toast.warning('卸载残留检查未完成，可稍后手动打开残留清理。', { timeout: 3000 })
        }
      })()
    }, delayMs)
  }

  // === Actions ===
  // 初始化只保留“设置 loading + 调用启动编排 + 统一失败提示”，具体启动步骤交给 startupStore。
  const initialize = async () => {
    isLoading.value = true
    startupPerfMark('app_initialize_start')
    try {
      const startupStore = useStartupStore()
      await startupPerfMeasure('app_initialize.startup_store_run', () => startupStore.run({
        waitForBackend,
        setupEventListeners,
        notifyFrontendReady,
        loadStartupCoreData,
        refreshModEnrichment,
        refreshBackupData,
        loadStartupInventorySummary,
        isScanRunning,
        settings,
        upgradeContext,
        uiState,
        checkUpdate,
        requestModScan,
        runScheduledMaintenanceChecks,
      }))
      startupPerfMark('app_initialize_done')
    } catch (e) {
      console.error("初始化失败:", e)
      toast.error(toUserMessage(e?.message || e, '初始化失败。可能是配置、数据库或运行环境暂时不可用，详细原因已写入系统日志。'))
    } finally {
      isLoading.value = false
    }
  }
  // 刷新数据 (初始化核心)
  const refreshData = async (isInit = false, historyLabel = '刷新磁盘状态') => {
    if (!window.pywebview) return false
    isLoading.value = true
    startupPerfMark('refresh_data_start', { isInit, historyLabel })
    try {
      // 调用后端获取全量数据
      const res = await startupPerfMeasure('refresh_data.get_initial_data', () => window.pywebview.api.get_initial_data(), { isInit, historyLabel })
      if (!checkResult(res, '刷新数据')) return false
      const applied = applyInitialPayload(res.data, { isInit, historyLabel })
      if (!applied) return false
      // 刷新动态规则
      const ruleStore = useRuleStore()
      void startupPerfMeasure('refresh_data.rules_get_all', () => ruleStore.fetchRules(), { isInit })
      const orderStore = useOrderStore()
      // 备份列表优先保持用户当前正在查看的环境视图；无选择时再回退到当前环境。
      void startupPerfMeasure('refresh_data.backups_get_all', () => orderStore.getBackups(orderStore.backupProfileId || settings.value.current_profile_id || 'default'), { isInit })
      startupPerfMark('refresh_data_done', { isInit, historyLabel })
      return true
    } catch (e) {
      toast.error(toUserMessage(e?.message || e, '刷新数据失败。可能是扫描器、数据库或当前环境暂时不可用，请稍后重试。'))
      return false
    } finally {
      isLoading.value = false
    }
  }
  // 注册事件监听
  const setupEventListeners = () => {
    // 防止重复添加监听器
    if (window._modManagerEventsInitialized) return
    window._modManagerEventsInitialized = true

    // 监听：扫描完成
    window.addEventListener('scan-complete', async (e) => {
      const detail = e?.detail || {}
      const taskId = String(detail.task_id || detail.id || '')
      if (taskId) {
        taskStore.upsertTask({
          id: taskId,
          type: 'scan',
          status: String(detail.status || 'success'),
          progress: Number(detail.progress ?? (detail.status === 'success' ? 100 : 0)),
          message: detail.message || (detail.status === 'success' ? '扫描完成' : ''),
          metrics: {
            title: '模组扫描',
            ...(detail.metrics || {}),
            ...(detail.stats ? { stats: detail.stats } : {}),
            ...(detail.runtime_sync_message ? { runtime_sync_message: detail.runtime_sync_message } : {}),
          },
          timestamp: Date.now(),
        })
      }
      // 扫描完成后的逻辑主要涉及 Mod 数据更新
      const modStore = useModStore()
      // 取出并清空本次扫描选项，避免下一次外部扫描误用旧状态。
      const scanRequest = activeModScanRequest.value
      activeModScanRequest.value = null
      await modStore.scanComplete(detail, {
        preserveListState: !!scanRequest?.preserveListState,
        refreshRules: scanRequest?.refreshRules !== false,
        refreshBackups: scanRequest?.refreshBackups !== false,
        refreshWorkspaceLibraries: scanRequest?.refreshWorkspaceLibraries !== false,
        silentSuccess: !!scanRequest?.silentSuccess,
      })
      if (detail.status === 'success' && scanRequest?.startupWorkshopChanges?.length) {
        void useWorkspaceStore().showStartupWorkshopChangesPrompt(scanRequest.startupWorkshopChanges)
      }
      if (detail.status === 'success' && detail.should_check_mod_residue) {
        scheduleModResidueCheck()
      }
      if (pendingModScanRequested.value) {
        window.setTimeout(() => {
          void flushQueuedModScan()
        }, 0)
      }
    })

    // 监听：本地共存任务完成
    window.addEventListener('localize-complete', (e) => {
        const detail = e?.detail || {}
        const { success_count, error_count, errors, status, title } = detail;
        const taskTitle = title || '本地共存任务'
        console.info(`${taskTitle}完成。成功 ${success_count} 项，失败 ${error_count} 项。`, errors)
        if (status === 'cancelled') {
            toast.info(`${taskTitle}已取消`);
            return
        }
        if (error_count > 0) {
            toast.warning(`${taskTitle}已完成，成功 ${success_count} 项，失败 ${error_count} 项。失败详情已写入系统日志。`);
        } else {
            toast.success(`${taskTitle}已完成：${success_count} 个模组`);
        }
        const sizeCheckPaths = Array.isArray(detail.size_check_paths)
          ? detail.size_check_paths.map(path => String(path || '').trim()).filter(Boolean)
          : []
        void requestModScan({ preserveListState: true, sizeCheckPaths })
    });
    // 监听：游戏暂停
    window.addEventListener('app-suspending', () => {
      console.info('检测到游戏启动，停止所有界面活动。');
      // 1. 设置全局加载状态，屏蔽用户操作
      isLoading.value = true;
      if (suspendRecoveryTimer) {
        clearTimeout(suspendRecoveryTimer)
        suspendRecoveryTimer = null
      }
    });
    // 监听游戏状态变化
    window.addEventListener('game-status-changed', (e) => {
      const detail = e?.detail || {}
      if (detail.runtime_session) {
        setRuntimeSession(detail.runtime_session)
      } else {
        isGameRunning.value = !!detail.running
      }
      if (detail.profile_id && detail.last_played_time) {
        useProfileStore().applyLastPlayedTime(detail.profile_id, detail.last_played_time)
      }
      if (detail.source === 'external' && detail.message) {
        toast.info(detail.message, { timeout: 4000 })
      }
      if (detail.failure_reason && detail.message) {
        toast.error(toUserMessage(detail.message, '游戏启动状态异常。可能是游戏路径、启动参数或运行环境暂时不可用，详细原因已写入系统日志。'))
      }
    })
    window.addEventListener('app-suspending', () => {
      isSuspended.value = true
    })
    window.addEventListener('app-resuming', () => {
      isSuspended.value = false
      isLoading.value = true
      if (suspendRecoveryTimer) clearTimeout(suspendRecoveryTimer)
      suspendRecoveryTimer = window.setTimeout(() => {
        suspendRecoveryTimer = null
        void recoverFromSuspendedState()
      }, 120)
    })
    // 通用进度更新
    window.addEventListener('global-progress', (e) => {
      const task = taskStore.upsertTask(e.detail)
      if (!task) return
      if (['success', 'failed', 'cancelled'].includes(task.status)) {
        clearTaskCancelPending(task.id)
      }

      if (task.type === 'texture-opt' || task.type === 'texture-opt-analyze') {
        const textureStore = useTextureStore()
        textureStore.handleProgressEvent(task)
      }
      if (task.type === 'download' && task.status === 'success') {
        const filename = task.metrics?.filename || task.message
        if (filename) toast.success(`下载已完成：${filename}`)
        const textureStore = useTextureStore()
        textureStore.handleDownloadEvent(task)
      }
      if (task.type === 'download' && task.status === 'failed') {
        const filename = task.metrics?.filename || task.message || '文件'
        toast.error(`${filename} 下载失败。可能是网络连接、代理设置、下载源不可用或磁盘权限问题，详细原因已写入系统日志。`)
      }
      if (task.type === 'steamcmd-download' && task.status === 'failed') {
        toast.error(toUserMessage(task.metrics?.error || task.message, 'SteamCMD 下载失败。请检查网络连接、代理设置、下载源可用性和目标目录权限，详细原因已写入系统日志。'))
      }
      if (task.type === 'steam-workshop-download' && task.status === 'success') {
        void (async () => {
          await requestModScan({ preserveListState: true })
          toast.success('Steam 下载已完成')
        })()
      }
      if (task.type === 'steam-workshop-download' && task.status === 'failed') {
        toast.error(toUserMessage(task.metrics?.error || task.message, 'Steam 下载失败。请确认 Steam 已登录并正常联网，或检查代理设置和工坊项目状态。'))
      }
      if (task.type === 'steam-subscribe' && task.status === 'success') {
        void (async () => {
          await requestModScan({ preserveListState: true })
          toast.success('Steam 订阅已完成')
        })()
      }
      if (task.type === 'steam-subscribe' && task.status === 'failed') {
        toast.error(toUserMessage(task.metrics?.error || task.message, 'Steam 订阅失败。请确认 Steam 已登录、网络可用，且目标工坊项目仍可访问。'))
      }
      if (task.type === 'steam-unsubscribe' && task.status === 'failed') {
        toast.error(toUserMessage(task.metrics?.error || task.message, '取消订阅失败。请确认 Steam 已登录、网络可用，稍后重试。'))
      }
      if (task.type === 'update' && task.status === 'success' && task.metrics?.ready_to_install) {
        if (updateState.info) updateState.info.local_status = 'ready'
        if (!updateInstallPrompted.has(task.id)) {
          updateInstallPrompted.add(task.id)
          _showInstallPrompt(task.metrics)
        }
      }
      if (task.type === 'update' && task.status === 'failed') {
        if (task.metrics?.has_fallback_source) return
        toast.error(toUserMessage(task.metrics?.error || task.message, '下载更新包失败。请检查网络连接、代理设置和磁盘空间，稍后重试。'))
      }
      if (task.type === 'mod-export' && task.status === 'success') {
        if (!task.id || !exportCompletePrompted.has(task.id)) {
          if (task.id) exportCompletePrompted.add(task.id)
          void showExportCompleteDialog('模组包导出', task.metrics?.target_path)
        }
      }
      if (task.type === 'mod-export' && task.status === 'failed') {
        toast.error(toUserMessage(task.metrics?.error || task.message, '模组包导出失败。请检查导出目录权限、磁盘空间和待导出模组状态，详细原因已写入系统日志。'))
      }
      if (task.type === 'mod-export' && task.status === 'cancelled') {
        toast.warning('模组包导出已取消')
      }
      if (task.type === 'mod-import' && task.status === 'success') {
        void (async () => {
          await applyModPackageImportPostActions(task)
          const warnings = Array.isArray(task.metrics?.warnings) ? task.metrics.warnings : []
          if (warnings.length > 0) {
            toast.warning(warnings.join('\n'), { timeout: 8000 })
          }
          toast.success('模组包导入完成')
        })()
      }
      if (task.type === 'mod-import' && task.status === 'failed') {
        toast.error(toUserMessage(task.metrics?.error || task.message, '模组包导入失败。请检查文件是否完整、目标目录权限和磁盘空间，详细原因已写入系统日志。'))
      }
      if (task.type === 'mod-import' && task.status === 'cancelled') {
        toast.warning('模组包导入已取消')
      }
    });
    // 监听：后端弹窗
    window.addEventListener('backend-popup', (e) => {
      console.debug('收到后端弹窗:', e)
      _backendPopup(e)
    })
  }

  // 重置数据库
  const resetDatabase = async () => {
    if (!window.pywebview) return
    isLoading.value = true
    try {
      const res = await window.pywebview.api.reset_database()
      if (checkResult(res, "重置数据库")) {
        closeSettingsPanel()
        // 提示成功
        toast.success("数据库已重置。")
        // 清空本地状态
        const modStore = useModStore()
        modStore.reset()
        const groupStore = useGroupStore()
        groupStore.groupList = []
        // 重新初始化 (这会触发扫描)
        await initialize()
        // 或者直接触发扫描
        // scanMods()
      }
    } finally {
      isLoading.value = false
    }
  }
  // 主动修复数据库
  const repairDatabase = async () => {
    if (!window.pywebview) return
    isLoading.value = true
    try {
      const res = await window.pywebview.api.repair_database()
      if (!checkResult(res, "修复数据库")) {
        return res
      }
      if (res.data?.initialized) {
        // 数据库文件不存在时，后端会直接初始化新库，这里同步把前端状态也重建一次。
        const modStore = useModStore()
        modStore.reset()
        const groupStore = useGroupStore()
        groupStore.groupList = []
        await initialize()
      }
      return res
    } finally {
      isLoading.value = false
    }
  }
  // 主动重启应用
  const restartApplication = async () => {
    if (!window.pywebview) return
    isLoading.value = true
    try {
      // 修复结果切换发生在重启后的启动阶段，这里只负责让当前实例安全退出并拉起新实例。
      const res = await window.pywebview.api.restart_application()
      checkResult(res, "重启应用")
      return res
    } finally {
      isLoading.value = false
    }
  }
  // 数据库孤立数据清理
  const performDatabaseCleanup = async () => {
    const res = await window.pywebview.api.perform_database_cleanup()
    if (checkResult(res, '数据库深度清理')) {
      toast.success('无效数据清理完成，正在刷新列表。')
      await refreshModCoreData('无效数据清理后同步模组数据', {
        refreshRules: false,
        refreshBackups: false,
        refreshWorkspaceLibraries: false,
      })
    }
  }
  const cancelTaskByProgress = async (task) => {
    if (!window.pywebview || !task?.id) return false
    if (!supportsTaskCancellation(task)) return false
    if (isTaskCancelPending(task.id)) return true
    markTaskCancelPending(task.id)
    try {
      const displayName = task?.metrics?.title || task?.message || '任务'
      const res = await window.pywebview.api.cancel_progress_task(task.id, task.type)
      if (checkResult(res, `取消${displayName}`, false)) {
        return true
      }
      clearTaskCancelPending(task.id)
      return false
    } catch (e) {
      clearTaskCancelPending(task.id)
      console.error('取消任务异常:', e)
      toast.error(toUserMessage(e?.message || e, '取消任务失败。可能是任务已经结束或后端暂时不可用，请稍后刷新状态。'))
      return false
    }
  }

  const cancelTextureTask = async (taskId, taskType = 'texture-opt') => {
    return cancelTaskByProgress({
      id: taskId,
      type: taskType,
      status: 'running',
      message: '贴图任务',
      metrics: { title: '贴图任务' },
    })
  }
  // 变更 UI 状态
  const toggleUiState = (key) => {
    uiState[key] = !uiState[key]
  }
  // 记录滚动位置状态
  const recordScroll = (listId, offset) => {
    scrollRegistry.value.set(listId, offset);
  };
  // 获取滚动位置状态
  const getScroll = (listId) => {
    return scrollRegistry.value.get(listId) || 0;
  };
  // 设置侧边栏选中标签
  const setSidebarTab = (tabId) => {
    if (SIDEBAR_TABS.some(t => t.id === tabId)) {
      activeSidebarTab.value = tabId
    }
  }
  // === 系统操作 ===
  // 启动游戏
  const launchGame = async (profile_id=null) => {
    const profileStore = useProfileStore()
    const normalizedTargetProfileId = String(profile_id || '').trim()
    const currentProfileId = String(profileStore.currentProfileId || '').trim()
    const effectiveTargetProfileId = normalizedTargetProfileId || currentProfileId
    const targetProfile = (profileStore.profiles || []).find(item => item.id === effectiveTargetProfileId)
    const targetProfileName = targetProfile?.name || effectiveTargetProfileId || '当前环境'
    // 当前环境启动前必须先把界面里的最新工作序列落盘；
    // 只有“启动别的环境”时，才允许跳过这一步。
    if (!normalizedTargetProfileId || normalizedTargetProfileId === currentProfileId) {
      const orderStore = useOrderStore()
      const res = await orderStore.saveLoadOrder({ actionLabel: '运行' })
      if (!res) return
    }
    if (!window.pywebview) return
    let gameRes = await window.pywebview.api.game_launch(profile_id)
    gameRes = await resolveGameLaunchWarning(gameRes, profile_id)
    if (!gameRes) return
    if (checkResult(gameRes, "启动游戏程序")) {
      const runtimeState = String(gameRes?.data?.runtime_session?.state || '').trim()
      if (runtimeState === 'launching') {
        toast.success(`正在启动“${targetProfileName}”环境，请等待游戏进程确认。`)
      } else {
        toast.success(gameRes.message)
      }
    }
  }
  // 触发睡眠 API
  const enterSleepMode = () => {
    if (window.pywebview) {
      window.pywebview.api.monitor_force_sleep()
    }
  }
  const exitSleepMode = () => {
    if (window.pywebview) {
      window.pywebview.api.monitor_force_wake()
    }
  }
  // 下载文件
  const startDownload = async (url, targetDir = null, filename = null) => {
    if (!window.pywebview) return
    try {
      const res = await window.pywebview.api.download_file(url, targetDir, filename)
      if (checkResult(res, "添加下载任务")) {
        // 成功
      }
    } catch (e) {
      console.error('添加下载任务异常:', e)
    }
  }
  /**
   * 通用下载等待函数
   * @param {string} taskId - 后端返回的任务 ID
   * @param {number} timeout - 超时时间(ms)，默认 10 分钟
   */
  const waitForDownload = (taskId, timeout = 600000) => {
    return taskStore.waitForTaskCompletion(taskId, timeout).then(task => (
      task?.metrics?.file_path || task?.metrics?.path || ''
    ))
  }

  const WAIT_STEAM_EXIT_ACTION = 'wait_steam_exit'
  const GAME_LAUNCH_ACTION = Object.freeze({
    CONTINUE: 'continue',
    CHECK_STEAM_STATUS: 'check_steam_status',
    DISABLE_STEAM_LAUNCH: 'disable_steam_launch',
    CANCEL: 'cancel',
  })
  const GAME_LAUNCH_WARNING_REASON = Object.freeze({
    STEAM_PATH_INVALID: 'steam_path_invalid',
    STEAM_NOT_READY: 'steam_not_ready',
    STEAM_RUNNING_WORKSHOP_CONFLICT: 'steam_running_workshop_conflict',
  })
  const sleep = (ms) => new Promise(resolve => window.setTimeout(resolve, ms))

  const steamLaunchFallbackButtons = () => [
    { label: '本次直启游戏', value: GAME_LAUNCH_ACTION.CONTINUE, kind: 'primary' },
    { label: '检查 Steam 状态', value: GAME_LAUNCH_ACTION.CHECK_STEAM_STATUS, kind: 'secondary' },
    { label: '关闭 Steam 优先启动', value: GAME_LAUNCH_ACTION.DISABLE_STEAM_LAUNCH, kind: 'danger' },
    { label: '取消', value: GAME_LAUNCH_ACTION.CANCEL, kind: 'secondary' },
  ]

  const buildGameLaunchWarningConfig = (gameRes) => {
    const reason = String(gameRes?.data?.reason || '').trim()
    const fallbackMessage = String(gameRes?.message || '').trim()
    switch (reason) {
      case GAME_LAUNCH_WARNING_REASON.STEAM_PATH_INVALID:
        return {
          type: 'warning',
          mode: 'actions',
          title: 'Steam 启动不可用',
          message: '当前环境配置为优先使用 Steam 启动，但未检测到有效的 Steam 程序路径。\n你可以只在本次改为直接启动，也可以检查 Steam 状态，或关闭这个开关并保存。',
          actionButtons: steamLaunchFallbackButtons(),
        }
      case GAME_LAUNCH_WARNING_REASON.STEAM_NOT_READY:
        return {
          type: 'warning',
          mode: 'actions',
          title: 'Steam 暂时不可用',
          message: `${fallbackMessage || 'Steam 未能进入可用状态。'}\n你可以只在本次改为直接启动，也可以检查 Steam 状态，或关闭这个开关并保存。`,
          actionButtons: steamLaunchFallbackButtons(),
        }
      case GAME_LAUNCH_WARNING_REASON.STEAM_RUNNING_WORKSHOP_CONFLICT:
        return {
          type: 'warning',
          mode: 'wait_steam_exit',
          title: '建议先停用 Steam',
          message: '当前环境配置为直接启动游戏本体，且已将创意工坊模组链接部署到本地模组目录。\n检测到 Steam 已在运行，如果现在继续启动游戏，Steam 会接管本次启动，游戏内将同时出现两套创意工坊模组。\n默认会优先加载本地目录中的那一套，一般不会影响实际游戏，但界面显示和后续管理会变得混乱。\n你可以手动退出 Steam；当前窗口会保持等待，Steam 完全退出后将自动启动游戏。\n如果你清楚影响，也可以直接继续运行。',
          actionButtons: [
            { label: '继续运行', value: 'continue', kind: 'primary' },
            { label: '取消', value: 'cancel', kind: 'secondary' },
          ],
        }
      default:
        if (gameRes?.data?.requires_fallback_confirm) {
          return {
            type: 'warning',
            mode: 'confirm',
            title: '启动前确认',
            message: fallbackMessage || '当前环境需要先确认后再继续启动。',
            confirmText: '继续',
            cancelText: '取消',
            action: 'continue',
          }
        }
        return null
    }
  }

  const showSteamStatusForLaunch = async () => {
    const statusRes = await window.pywebview.api.steam_client_status()
    if (!checkResult(statusRes, '检查 Steam 状态')) return null
    const hint = statusRes?.data?.user_hint || {}
    await confirmStore.alert(
      hint.title || 'Steam 状态',
      hint.message || statusRes.message || '已完成 Steam 状态检查。',
      { type: statusRes?.data?.ready ? 'success' : 'warning' }
    )
    return null
  }

  const disableSteamLaunchForProfile = async (profileId) => {
    const targetProfileId = String(profileId || '').trim()
    if (!targetProfileId) return null
    const profileStore = useProfileStore()
    await profileStore.updateProfile(targetProfileId, { prefer_steam_launch: false })
    return null
  }

  const resolveGameLaunchWarning = async (gameRes, requestedProfileId = null) => {
    if (gameRes?.status !== 'warning' || gameRes?.data?.action !== 'confirm_direct_launch') {
      return gameRes
    }

    const profileStore = useProfileStore()
    const targetProfileId = gameRes?.data?.profile_id || requestedProfileId || profileStore.currentProfileId
    const confirmStore = useConfirmStore()
    const warningConfig = buildGameLaunchWarningConfig(gameRes)
    if (!warningConfig) {
      return gameRes
    }

    if (warningConfig.mode === 'confirm') {
      const ok = await confirmStore.confirmAction(
        warningConfig.title,
        warningConfig.message,
        { type: warningConfig.type, confirmText: warningConfig.confirmText, cancelText: warningConfig.cancelText }
      )
      if (!ok) return null
      return window.pywebview.api.game_launch_resolve_warning(targetProfileId, warningConfig.action || 'continue')
    }

    if (warningConfig.mode === 'actions') {
      const choice = await confirmStore.open({
        title: warningConfig.title,
        message: warningConfig.message,
        mode: 'confirm',
        type: warningConfig.type || 'warning',
        actionButtons: warningConfig.actionButtons,
      })
      if (!choice || choice === GAME_LAUNCH_ACTION.CANCEL) return null
      if (choice === GAME_LAUNCH_ACTION.CHECK_STEAM_STATUS) return await showSteamStatusForLaunch()
      if (choice === GAME_LAUNCH_ACTION.DISABLE_STEAM_LAUNCH) return await disableSteamLaunchForProfile(targetProfileId)
      return window.pywebview.api.game_launch_resolve_warning(targetProfileId, choice)
    }

    if (warningConfig.mode === 'wait_steam_exit') {
      return await waitSteamExitAndLaunch(targetProfileId, warningConfig)
    }
    return gameRes
  }

  const waitSteamExitAndLaunch = async (targetProfileId, warningConfig) => {
    const confirmStore = useConfirmStore()
    let stopPolling = false
    let autoLaunchResult = null
    let autoResolved = false

    const choicePromise = confirmStore.open({
      title: warningConfig?.title || '建议先停用 Steam',
      message: warningConfig?.message || '',
      mode: 'confirm',
      type: warningConfig?.type || 'warning',
      actionButtons: Array.isArray(warningConfig?.actionButtons) && warningConfig.actionButtons.length
        ? warningConfig.actionButtons
        : [
            { label: '继续运行', value: 'continue', kind: 'primary' },
            { label: '取消', value: 'cancel', kind: 'secondary' },
          ],
    })

    const pollingPromise = (async () => {
      while (!stopPolling && confirmStore.isVisible) {
        try {
          const statusRes = await window.pywebview.api.steam_process_status()
          const isRunning = !!statusRes?.data?.running
          if (statusRes?.status === 'success' && !isRunning) {
            const launchRes = await window.pywebview.api.game_launch_resolve_warning(targetProfileId, WAIT_STEAM_EXIT_ACTION)
            if (
              launchRes?.status === 'warning'
              && launchRes?.data?.action === WAIT_STEAM_EXIT_ACTION
              && launchRes?.data?.steam_running
            ) {
              // Steam 尚未完全退出，继续等待下一轮轮询。
            } else {
              autoLaunchResult = launchRes
              autoResolved = true
              stopPolling = true
              confirmStore.closeSilently()
              return
            }
          }
        } catch (e) {
          console.error('轮询 Steam 进程状态失败:', e)
        }
        await sleep(1000)
      }
    })()

    const choice = await choicePromise

    stopPolling = true
    await pollingPromise

    if (autoResolved) return autoLaunchResult
    if (!choice || choice === 'cancel') return null
    return window.pywebview.api.game_launch_resolve_warning(targetProfileId, choice)
  }

  // 后端弹窗
  const _backendPopup = (event) => {
    const confirmStore = useConfirmStore()
    const { mode, title, message, type, duration } = event.detail
    console.debug('后端弹窗:', event.detail)
    // 模式1: 轻提示 (Toast)
    if (mode === 'toast') {
      const toastType = type || 'info' // success, error, warning, info
      toast[toastType](message, {
        timeout: duration || 3000
      })
    }
    // 模式2: 模态框 (Modal/Confirm)
    else {
      confirmStore.open({
        title: title || '系统提示',
        message: message,
        type: type || 'info', // info, success, warning, error
        mode: 'alert', // 强制设为 alert 模式，因为后端无法直接await前端的选择结果(除非用更复杂的Promise桥接)
      })
    }
  }

  // 比如在 get_initial_data 中返回：asset_server_port: 54321
  const getAssetBaseUrl = () => `http://127.0.0.1:${settings.value.asset_port}`

  // 生成列表缩略图 URL
  const getThumbUrl = (packageId, rawPath) => {
    if (!rawPath) return ''
    const safeId = encodeURIComponent(packageId || '')
    const safePath = encodeURIComponent(rawPath)
    return `${getAssetBaseUrl()}/thumb?id=${safeId}&path=${safePath}`
  }

  // 生成详情页本地大图 URL
  const getLocalUrl = (rawPath) => {
    if (!rawPath) return ''
    const safePath = encodeURIComponent(rawPath)

    return `${getAssetBaseUrl()}/local?path=${safePath}`
  }

  // 生成网络代理图 URL (如 Steam 截图)
  const getRemoteUrl = (remoteUrl) => {
    if (!remoteUrl) return ''
    if (String(remoteUrl).startsWith(getAssetBaseUrl())) return remoteUrl
    const safeUrl = encodeURIComponent(remoteUrl)
    return `${getAssetBaseUrl()}/remote?url=${safeUrl}`
  }

  const refreshRemoteImageCacheStats = async ({ silent = false } = {}) => {
    if (!window.pywebview) return null
    const res = await window.pywebview.api.get_remote_image_cache_stats()
    if (!checkResult(res, '获取网络图片缓存统计', false, { silent })) return false
    syncRemoteImageCache(res.data)
    return res.data
  }

  const clearRemoteImageCache = async () => {
    if (!window.pywebview) return false
    const res = await window.pywebview.api.clear_remote_image_cache()
    if (!checkResult(res, '清理网络图片缓存', true)) return false
    // 清理接口会同时返回清理后的统计，前端直接复用即可。
    syncRemoteImageCache(res.data?.current)
    return res.data
  }

  const ensureTranslationProviders = async () => {
    if (!window.pywebview || isTranslationProvidersLoaded.value) return translationProviders.value
    const res = await window.pywebview.api.translation_get_providers()
    if (checkResult(res, '获取翻译器列表', false, { silent: true })) {
      translationProviders.value = Array.isArray(res.data) && res.data.length ? res.data : translationProviders.value
      isTranslationProvidersLoaded.value = true
    }
    return translationProviders.value
  }

  return {
    // 基础状态
    appVersion, buildMode, uiState, settings, settingsReady, isLoading, isDownloading, isScanRunning, updateState,
    themes, currentTheme, userThemes, themeEditor, packageTransferDialog, recommendationExportDialog,
    // 布局与运行态
    remoteImageCache, translationProviders, isTranslationProvidersLoaded, DEFAULT_DETAILS_LAYOUT, DETAILS_LAYOUT_MAPS, DEFAULT_MAIN_LAYOUT, MAIN_LAYOUT_MAPS, SIDEBAR_TABS, activeSidebarTab, isGameRunning, isSuspended, runtimeSession, upgradeContext,
    // 生命周期与通用工具
    initialize, checkResult, refreshData, loadStartupCoreData, refreshRuleData, refreshBackupData, loadStartupInventorySummary, toggleUiState, scalePx, performDatabaseCleanup, recordScroll, getScroll, enterSleepMode, exitSleepMode,
    refreshModsData, refreshModCoreData, refreshModEnrichment, requestModScan,
    // 图片与缓存
    getThumbUrl, getLocalUrl, getRemoteUrl, refreshRemoteImageCacheStats, clearRemoteImageCache, ensureTranslationProviders, normalizeTranslationSettings, getTranslationFeatureSettings, saveTranslationFeatureSettings,
    // 路径与游戏启动
    checkPath, checkPaths, launchGame, autoDetectPaths, getDefaultExternalPaths, openPath, openFile, readTextFile, getFilePath, getFolderPath, deletePath, deletePaths, openUrl,
    // 下载与工坊
    startDownload, waitForDownload, downloadWorkshopItems, getCollectionItems, downloadPackageIds, subscribePackageIds, openSteamWorkshopById,
    openSteamWorkshopUrl, unsubscribeWorkshopIds, subscribeWorkshopIds, subscribeInstallSources, downloadInstallSources, openInstallSource,
    downloadWorkshopItemsViaSteam, querySteamWorkshopDetails,
    // 设置、任务与应用维护
    saveSetting, applySettings, revealSecret, clearSecret, refreshUserThemes, saveUserTheme, deleteUserTheme, openSettingsPanel, closeSettingsPanel, resetDatabase, repairDatabase, restartApplication, showChangelog, setSidebarTab, cancelTextureTask, cancelTaskByProgress, supportsTaskCancellation, canCancelTask, isTaskCancelPending,
    checkSteamTools, checkToolMaintenance, checkExternalDataUpdates, checkManagedModUpdates, checkSteamcmdModUpdates, runScheduledMaintenanceChecks, checkUpdate, updateExternalDB,
    // 包传输
    openPackageTransferDialog, openCustomModExportDialog, updatePackageTransferDialogPreset, closePackageTransferDialog,
    getDataBundleSchema, inspectDataBundle, exportDataBundle, importDataBundle,
    getModPackageSchema, prepareModPackageImport, getModPackageProfileSummary, exportModPackage, importModPackage,
    // 推荐导出
    openRecommendationExportDialog, closeRecommendationExportDialog,
  }
})
