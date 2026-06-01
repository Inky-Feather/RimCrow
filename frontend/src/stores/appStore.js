// stores/appStore.js

import { defineStore } from 'pinia'
import { ref, reactive, computed, watch } from 'vue'
import { checkResult, deepClone, toast } from '../utils/common'
import { useModStore } from './modStore'
import { useGroupStore } from './groupStore'
import { useOrderStore } from './orderStore'
import { useRuleStore } from './ruleStore'
import { useConfirmStore } from './confirmStore'
import { useProfileStore } from './profileStore'
import { useTextureStore } from './textureStore'
import { useWorkspaceStore } from './workspaceStore'
import { useTaskStore } from './taskStore'
import { usePromptQueueStore } from './promptQueueStore'
import { useStartupStore } from './startupStore'
import { isBrowserRuntime, openManagedSubBrowserUrl } from '../runtime/runtimeBridge'
import { normalizeInstallSource, normalizeInstallSources } from '../utils/modIdentity'
import { DEFAULT_THEME_ID, applyTheme, findThemeById, mergeThemes } from '../modules/theme/themeManager'

export const useAppStore = defineStore('app', () => {
  const taskStore = useTaskStore()

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
    showModConfigManager: false, // 是否显示模组配置弹窗
    showFileSearchWorkbench: false, // 是否显示文件内容搜索工作台
    showPackageTransferDialog: false, // 是否显示模组包/数据包传输弹窗
  })
  const packageTransferDialog = reactive({
    mode: 'mod-import',
    preset: {},
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
  const cancelPendingTaskIds = ref(new Set())
  const cancelPendingTimers = new Map()
  const CANCELLATION_PENDING_TIMEOUT_MS = 15000
  let suspendRecoveryTimer = null
  let suspendRecoveryPromise = null

  const upgradeContext = ref({}); // 升级上下文

  // 定义侧边栏标签配置 (ID 与 标题绑定)
  const SIDEBAR_TABS = [
    { id: 'temp', title: '临时' },
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
      enable_active_section_collapse: false,  // 是否启用启用列表标题分组折叠（仅 active 列表生效）
      default_collapse_active_sections: false,  // 若当前环境/列表还没有保存过折叠状态，首次是否默认折叠
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
    steam_web_api_key: '',

    // --- 贴图优化 ---
    texture_opt: {
      texture_tools_path: "",       // 贴图工具目录
      process_mode: 'scaled_only_overwrite',
      generate_mipmaps: true,       // 是否生成远近层级
      scale_factor: 0.5,            // 缩放比例
      max_size: 128,                // 最低清晰度
      skip_small_textures: true,    // 超出建议范围时不参与缩放
      min_dimension: 128,           // 最短边低于该值时不参与缩放
      max_source_dimension: 2048,   // 最长边高于该值时不参与缩放
    },
    
    // --- 高级 (Advanced) ---
    backup_retention_days: 30,
    enable_auto_scan: true,
    enable_file_size_scan: true,         // 扫描时是否检查文件大小
    delete_missing_mods_data: false,
    auto_sort_strategy: "classic_sort_logic",  // 自动排序策略
    sort_mods_by: "name",                 // 自动排序排列方式: name, id, alias
    coexist_mod_folder_name_type: "workshop_id", // 共存Mod生成方式: workshop_id, package_id, name, alias
    bundle_mod_folder_name_type: "default", // 模组包内文件夹命名方式
    show_coexistence_message: true,       // 是否显示共存Mod提示
    enable_action_prechecks: true,        // 关键动作前是否执行启用/安装检查
    check_language_support: true,        // 是否检查语言支持
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


  // === Getters ===
  const isDownloading = computed(() => taskStore.hasActiveTaskOfType(['download', 'update', 'steamcmd-download']))
  const isScanRunning = computed(() => taskStore.hasActiveTaskOfType('scan'))
  const updateInstallPrompted = new Set()
  const exportCompletePrompted = new Set()
  const pendingModScanRequested = ref(null)
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
      window.__RMM_DEBUG_MODE__ = !!enabled
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

  const isTimedCheckDue = (enabled, lastCheckTime, intervalDays, fallbackDays = 1) => {
    if (!enabled) return false
    const last = Number(lastCheckTime || 0)
    const interval = Math.max(1, Number(intervalDays || fallbackDays)) * 24 * 60 * 60 * 1000
    const duration = Date.now() - last
    return !last || duration > interval || duration < 0
  }

  const buildTimedCheckDecision = ({ enabled, lastCheckTime, intervalDays, fallbackDays = 1 } = {}) => {
    const last = Number(lastCheckTime || 0)
    const interval = Math.max(1, Number(intervalDays || fallbackDays)) * 24 * 60 * 60 * 1000
    const elapsed = Date.now() - last
    const due = !!enabled && (!last || elapsed > interval || elapsed < 0)
    const reason = !enabled ? 'disabled' : (!last ? 'never_checked' : (elapsed < 0 ? 'clock_rollback' : (due ? 'interval_due' : 'interval_not_due')))
    return { due, reason, enabled: !!enabled, lastCheckTime: last, intervalDays: Math.round(interval / 24 / 60 / 60 / 1000), elapsedMs: elapsed }
  }

  const logMaintenanceCheck = (event, payload = {}, level = 'info') => {
    // 统一启动/维护检测日志格式，排查“为什么没自动检查”时只需要搜索这个前缀。
    const method = level === 'warn' ? 'warn' : level === 'error' ? 'error' : 'info'
    console[method]('[RMM][maintenance-check]', { event, ...payload })
  }

  const formatDateTime = (timestamp) => {
    const value = Number(timestamp || 0)
    if (!value) return '未知'
    try {
      return new Date(value).toLocaleString('zh-CN')
    } catch {
      return '未知'
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

  const applyInitialPayload = (payload, { isInit = false, historyLabel = '刷新磁盘状态' } = {}) => {
    if (!payload) return false

    if (isInit && payload.settings) {
      settings.value = payload.settings
      settings.value.asset_port = payload.asset_port || 0
      upgradeContext.value = payload.upgrade_context
    } else {
      Object.assign(settings.value, payload.settings)
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
        toast.warning("未配置游戏路径，请先配置游戏路径。",{position: "top-center",timeout: 5000})
        uiState.showSettingsPanel = true
        return false
      }
    }

    const groupStore = useGroupStore()
    groupStore.setGroups(payload.groups || [])

    const modStore = useModStore()
    const previousSnapshot = isInit ? null : modStore.captureListHistorySnapshot()
    modStore.setMods(payload, { resetHistory: !!isInit })
    if (previousSnapshot) {
      modStore.recordListHistory({
        before: previousSnapshot,
        type: 'refresh-data',
        label: historyLabel,
      })
    }

    return true
  }

  // 扫描完成后只同步与模组相关的数据，避免再次触发整套工作区/集合/GitHub 初始化。
  const refreshModsData = async (historyLabel = '扫描后同步模组数据') => {
    if (!window.pywebview) return false
    try {
      const res = await window.pywebview.api.get_initial_data()
      if (!checkResult(res, '同步模组数据')) return false
      const applied = applyInitialPayload(res.data, { isInit: false, historyLabel })
      if (!applied) return false

      const ruleStore = useRuleStore()
      ruleStore.fetchRules()
      const orderStore = useOrderStore()
      orderStore.getBackups(orderStore.backupProfileId || settings.value.current_profile_id || 'default')

      const workspaceStore = useWorkspaceStore()
      // 扫描只会改变本地三库模组事实，不需要顺带刷新 GitHub/合集列表。
      void workspaceStore.refreshLoadedData({ librariesOnly: true })
      return true
    } catch (e) {
      toast.error(`同步模组数据失败: \n${e.message}`)
      return false
    }
  }

  const requestModScan = async ({ forcedUpdate = false, specificPaths = null } = {}) => {
    const normalizeScanRequest = (request = {}) => {
      const normalizedPaths = Array.isArray(request.specificPaths)
        ? request.specificPaths.map(path => String(path || '').trim()).filter(Boolean)
        : null
      return {
        forcedUpdate: !!request.forcedUpdate,
        specificPaths: normalizedPaths && normalizedPaths.length > 0 ? [...new Set(normalizedPaths)] : null,
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
      }
    }
    const scanRequest = normalizeScanRequest({ forcedUpdate, specificPaths })
    if (isScanRunning.value) {
      pendingModScanRequested.value = mergeScanRequest(pendingModScanRequested.value, scanRequest)
      return false
    }

    pendingModScanRequested.value = null
    const modStore = useModStore()
    await modStore.scanMods(scanRequest.specificPaths, scanRequest.forcedUpdate)
    return true
  }

  const flushQueuedModScan = async () => {
    if (!pendingModScanRequested.value || isScanRunning.value) return false
    const queuedRequest = pendingModScanRequested.value
    pendingModScanRequested.value = null
    const modStore = useModStore()
    await modStore.scanMods(queuedRequest.specificPaths, queuedRequest.forcedUpdate)
    return true
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
        toast.error(`恢复界面失败: \n${e.message || e}`)
      } finally {
        isLoading.value = false
        suspendRecoveryPromise = null
      }
    })()

    return suspendRecoveryPromise
  }

  const installToolIssues = async (issues = []) => {
    if (!window.pywebview || !Array.isArray(issues) || issues.length === 0) return false
    let started = false
    const hasSteamCmdIssue = issues.some(item => item?.tool_id === 'steamcmd')
    const hasToddsIssue = issues.some(item => item?.tool_id === 'todds')
    const hasRipgrepIssue = issues.some(item => item?.tool_id === 'ripgrep')

    if (hasSteamCmdIssue) {
      const res = await window.pywebview.api.steam_tools_install()
      if (checkResult(res, '处理 SteamCMD 环境')) {
        started = true
        if (Array.isArray(res.data?.pending_tasks) && res.data.pending_tasks.length > 0) {
          toast.info('SteamCMD 相关任务已启动，请留意底部状态栏。')
        }
      }
    }

    if (hasToddsIssue) {
      const res = await window.pywebview.api.texture_prepare_download(settings.value.texture_opt)
      if (checkResult(res, '处理 todds 环境')) {
        started = true
        if (!res.data?.already_ready) {
          toast.info('todds 下载任务已启动，请留意底部状态栏。')
        }
      }
    }

    if (hasRipgrepIssue) {
      const ripgrepIssue = issues.find(item => item?.tool_id === 'ripgrep') || {}
      const res = await window.pywebview.api.ripgrep_prepare_download(ripgrepIssue?.maintenance_action === 'upgrade')
      if (checkResult(res, '处理 ripgrep 环境')) {
        started = true
        if (!res.data?.already_ready) {
          toast.info('ripgrep 下载任务已启动，请留意底部状态栏。')
        }
      }
    }
    return started
  }

  const getToolIssueActionLabel = (item = {}) => {
    // 后端会把存在性、初始化、升级判断统一成 maintenance_action，前端只负责显示用户能理解的动作。
    const action = String(item?.maintenance_action || '').trim()
    if (action === 'upgrade') return '升级'
    if (action === 'initialize') return '初始化'
    if (action === 'install') return '安装'
    return '处理'
  }

  const triggerGithubManagedModUpdate = async (item = {}) => {
    if (!window.pywebview || !item?.repo_url) return false
    const targetVersion = String(item.target_version || item.latest_version || '').trim()
    const res = await window.pywebview.api.github_trigger_download(item.repo_url, item.install_type || 'source', targetVersion)
    if (!checkResult(res, `更新 Git 仓库模组 ${item.title || ''}`.trim())) return false
    toast.info('Git 仓库部署任务已启动，请留意底部状态栏。', { timeout: 4000 })
    const workspaceStore = useWorkspaceStore()
    workspaceStore.startGithubTimelinePolling(item.repo_url, { intervalMs: 4000, maxPolls: 15 })
    return true
  }

  const updateManagedModItems = async (items = []) => {
    // 批量动作按来源拆分：SteamCMD 支持合并下载，Git 仓库订阅逐项启动部署任务。
    const normalizedItems = Array.isArray(items) ? items : []
    const workshopIds = [...new Set(
      normalizedItems
        .filter(item => String(item?.source || '').toLowerCase() === 'steamcmd')
        .map(item => String(item?.workshop_id || '').trim())
        .filter(Boolean)
    )]
    if (workshopIds.length > 0) await downloadWorkshopItems(workshopIds)

    for (const item of normalizedItems.filter(item => String(item?.source || '').toLowerCase() === 'github')) {
      await triggerGithubManagedModUpdate(item)
    }
    return workshopIds.length > 0 || normalizedItems.some(item => String(item?.source || '').toLowerCase() === 'github')
  }

  // 维护检查的时间戳统一在前端落到 settings，避免每个检查函数重复处理“何时算检查成功”。
  const persistMaintenanceCheckedAt = (settingKey, data, shouldPersist = null) => {
    const checkedAt = Number(data?.checked_at || 0)
    if (!settingKey || !checkedAt) return
    if (typeof shouldPersist === 'function' && !shouldPersist(data)) return
    settings.value[settingKey] = checkedAt
  }

  // 维护类接口都遵循同一返回格式：手动触发走 checkResult 给用户反馈，启动期静默触发只接受 success。
  const fetchMaintenanceData = async ({
    apiName,
    workName,
    manual = true,
    lastCheckKey = '',
    shouldPersistCheckedAt = null,
  } = {}) => {
    if (!window.pywebview) return null
    const caller = window.pywebview.api?.[apiName]
    if (typeof caller !== 'function') return null

    const res = await caller()
    if (manual ? !checkResult(res, workName) : res?.status !== 'success') {
      logMaintenanceCheck('api_result', { apiName, workName, manual, status: res?.status || 'missing', message: res?.message || '' }, manual ? 'warn' : 'error')
      return null
    }

    const data = res.data || {}
    persistMaintenanceCheckedAt(lastCheckKey, data, shouldPersistCheckedAt)
    logMaintenanceCheck('api_result', { apiName, workName, manual, status: res.status, checkedAt: data.checked_at || 0, count: data.count ?? data.issues?.length ?? data.updates?.length ?? 0 })
    return data
  }

  // 工具环境可能涉及外部下载，因此只做检查本身静默；发现问题后统一进入提示队列交给用户决定。
  const checkToolMaintenance = async ({ manual = true, prompt = true } = {}) => {
    const data = await fetchMaintenanceData({
      apiName: 'maintenance_check_tools',
      workName: '检查工具环境',
      manual,
      lastCheckKey: 'last_tool_check_time',
    })
    if (!data) return null

    const issues = Array.isArray(data.issues) ? data.issues : []
    if (!prompt) return data
    if (issues.length === 0) {
      if (manual) toast.success('工具环境检查完成，当前均已就绪。')
      return data
    }

    const promptQueue = usePromptQueueStore()
    await promptQueue.enqueue({
      category: 'startup-tools',
      title: '工具环境需要处理',
      message: '以下工具当前未就绪，可单独处理，也可以批量处理。',
      type: 'warning',
      priority: manual ? 30 : 60,
      items: issues.map(item => ({
        id: item.tool_id || item.name,
        title: item.name || item.tool_id || '工具',
        description: item.message || '需要处理',
        meta: [
          item.resolved_path,
          item.current_version ? `当前版本 ${item.current_version}` : '',
          item.latest_version ? `最新版本 ${item.latest_version}` : '',
        ].filter(Boolean),
        raw: item,
        actions: [
          { id: 'install', label: getToolIssueActionLabel(item), kind: 'primary' },
          { id: 'skip', label: '稍后', kind: 'secondary' },
        ],
      })),
      bulkActions: [
        { id: 'install_all', label: '全部处理', kind: 'primary' },
        { id: 'skip_all', label: '全部稍后', kind: 'secondary' },
      ],
      onItemAction: async (item, actionId) => {
        if (actionId === 'install') await installToolIssues([item])
      },
      onBulkAction: async (actionId, items) => {
        if (actionId === 'install_all') await installToolIssues(items)
      },
    })
    return data
  }

  // 外部库更新属于网络下载动作：启动期可以静默检查，但实际更新必须经由队列弹窗确认。
  const checkExternalDataUpdates = async ({ manual = true, prompt = true } = {}) => {
    const data = await fetchMaintenanceData({
      apiName: 'maintenance_check_external_data',
      workName: '检查外部库更新',
      manual,
      lastCheckKey: 'last_external_data_update_check_time',
      // 整轮远端状态都没拿到时，不要把失败记录成一次成功检查。
      shouldPersistCheckedAt: (payload) => {
        const items = Array.isArray(payload?.items) ? payload.items : []
        const failed = Array.isArray(payload?.failed) ? payload.failed : []
        return items.length === 0 || failed.length < items.length
      },
    })
    if (!data) return null

    const updates = Array.isArray(data.updates) ? data.updates : []
    const failed = Array.isArray(data.failed) ? data.failed : []
    if (!prompt) return data
    if (failed.length > 0 && updates.length === 0) {
      const summary = failed.slice(0, 3).map(item => item.name || item.data_type || '外部库').join('、')
      const remain = failed.length > 3 ? ` 等 ${failed.length} 项` : ''
      toast.warning(`外部库检查未完成：${summary}${remain} 检查失败，请稍后重试或检查网络环境。`, { timeout: 4500 })
      return data
    }
    if (updates.length === 0) {
      if (manual) toast.success('外部库检查完成，当前均已是最新。')
      return data
    }

    const promptQueue = usePromptQueueStore()
    await promptQueue.enqueue({
      category: 'startup-external-data',
      title: '发现外部库更新',
      message: failed.length > 0
        ? `另有 ${failed.length} 项外部库暂时检查失败，本次只展示已成功获取到远端状态的更新项。`
        : '以下外部库文件检测到更新，可单独更新，也可以批量更新。',
      type: 'warning',
      priority: manual ? 35 : 65,
      items: updates.map(item => ({
        id: item.data_type || item.name,
        title: item.name || item.data_type || '外部库',
        description: item.message || '检测到远端版本与本地不一致。',
        meta: [
          item.local_version ? `本地版本 ${item.local_version}` : `本地时间 ${formatDateTime(item.local_mtime)}`,
          item.remote_version ? `远端签名 ${item.remote_version}` : `远端时间 ${formatDateTime(item.remote_updated_at)}`,
        ],
        raw: item,
        actions: [
          { id: 'update', label: '更新', kind: 'primary' },
          { id: 'skip', label: '稍后', kind: 'secondary' },
        ],
      })),
      bulkActions: [
        { id: 'update_all', label: '全部更新', kind: 'primary' },
        { id: 'skip_all', label: '全部稍后', kind: 'secondary' },
      ],
      onItemAction: async (item, actionId) => {
        if (actionId === 'update') await updateExternalDB(item.data_type)
      },
      onBulkAction: async (actionId, items) => {
        if (actionId !== 'update_all') return
        for (const item of items) {
          // 顺序执行，避免同时刷新同一批缓存时互相打断。
          await updateExternalDB(item.data_type)
        }
      },
    })
    return data
  }

  // 管理器负责的模组更新包含 SteamCMD 工坊模组和 Git 仓库订阅模组，统一弹窗避免多来源重复打扰。
  const checkManagedModUpdates = async ({ manual = true, prompt = true } = {}) => {
    const data = await fetchMaintenanceData({
      apiName: 'maintenance_check_managed_mod_updates',
      workName: '检查管理器模组更新',
      manual,
      lastCheckKey: 'last_steamcmd_mod_update_check_time',
    })
    if (!data) return null

    const updates = Array.isArray(data.updates) ? data.updates : []
    if (!prompt) return data
    if (updates.length === 0) {
      if (manual) toast.success('管理器模组检查完成，当前均已是最新。')
      return data
    }

    const promptQueue = usePromptQueueStore()
    await promptQueue.enqueue({
      category: 'startup-managed-mods',
      title: '发现管理器模组更新',
      message: `检测到 ${updates.length} 个由管理器维护的模组有新版本。`,
      type: 'warning',
      priority: manual ? 40 : 70,
      items: updates.map(item => ({
        id: `${item.source || 'mod'}:${item.workshop_id || item.repo_url || item.title}`,
        title: item.title || item.workshop_id || '未知模组',
        description: item.message || (item.workshop_id ? `Workshop ID: ${item.workshop_id}` : item.repo_url || ''),
        meta: [
          item.source_label || item.source,
          item.installed_version ? `当前版本 ${item.installed_version}` : '',
          item.latest_version ? `最新版本 ${item.latest_version}` : '',
        ].filter(Boolean),
        raw: item,
        actions: [
          { id: 'update', label: '更新', kind: 'primary' },
          { id: 'skip', label: '稍后', kind: 'secondary' },
        ],
      })),
      bulkActions: [
        { id: 'update_all', label: '全部更新', kind: 'primary' },
        { id: 'skip_all', label: '全部稍后', kind: 'secondary' },
      ],
      onItemAction: async (item, actionId) => {
        if (actionId === 'update') await updateManagedModItems([item])
      },
      onBulkAction: async (actionId, items) => {
        if (actionId === 'update_all') await updateManagedModItems(items)
      },
    })
    return data
  }
  const checkSteamcmdModUpdates = checkManagedModUpdates

  // 启动后的维护检查只做轻量描述表，不引入任务引擎；以后新增检查时只追加一项配置。
  const getScheduledMaintenanceChecks = () => [
    {
      id: 'tools',
      name: '外部工具',
      enabled: settings.value.enable_auto_tool_check,
      lastCheckTime: settings.value.last_tool_check_time,
      intervalDays: settings.value.tool_check_interval_days,
      fallbackDays: 3,
      run: () => checkToolMaintenance({ manual: false, prompt: true }),
    },
    {
      id: 'external-data',
      name: '外部库',
      enabled: settings.value.enable_auto_external_data_update_check,
      lastCheckTime: settings.value.last_external_data_update_check_time,
      intervalDays: settings.value.external_data_update_check_interval_days,
      fallbackDays: 1,
      run: () => checkExternalDataUpdates({ manual: false, prompt: true }),
    },
    {
      id: 'managed-mods',
      name: '管理器模组更新',
      enabled: settings.value.enable_auto_steamcmd_mod_update_check,
      lastCheckTime: settings.value.last_steamcmd_mod_update_check_time,
      intervalDays: settings.value.steamcmd_mod_update_check_interval_days,
      fallbackDays: 1,
      run: () => checkManagedModUpdates({ manual: false, prompt: true }),
    },
  ]

  const runScheduledMaintenanceChecks = async () => {
    for (const check of getScheduledMaintenanceChecks()) {
      const decision = buildTimedCheckDecision(check)
      logMaintenanceCheck('schedule_decision', { id: check.id, name: check.name, ...decision })
      if (!decision.due) continue
      try {
        logMaintenanceCheck('schedule_run', { id: check.id, name: check.name })
        await check.run()
        logMaintenanceCheck('schedule_done', { id: check.id, name: check.name })
      } catch (error) {
        logMaintenanceCheck('schedule_error', { id: check.id, name: check.name, message: error?.message || String(error || '') }, 'error')
        throw error
      }
    }
  }

  // === Actions ===
  // 初始化只保留“设置 loading + 调用启动编排 + 统一失败提示”，具体启动步骤交给 startupStore。
  const initialize = async () => {
    isLoading.value = true
    try {
      const startupStore = useStartupStore()
      await startupStore.run({
        waitForBackend,
        setupEventListeners,
        refreshData,
        settings,
        upgradeContext,
        uiState,
        checkUpdate,
        runScheduledMaintenanceChecks,
      })
    } catch (e) {
      console.error("初始化失败:", e)
      toast.error(`初始化失败：\n${e}`)
    } finally {
      isLoading.value = false
    }
  }
  // 刷新数据 (初始化核心)
  const refreshData = async (isInit = false, historyLabel = '刷新磁盘状态') => {
    if (!window.pywebview) return false
    isLoading.value = true
    try {
      // 调用后端获取全量数据
      const res = await window.pywebview.api.get_initial_data()
      if (!checkResult(res, '刷新数据')) return false
      const applied = applyInitialPayload(res.data, { isInit, historyLabel })
      if (!applied) return false
      // 刷新动态规则
      const ruleStore = useRuleStore()
      ruleStore.fetchRules()
      const orderStore = useOrderStore()
      // 备份列表优先保持用户当前正在查看的环境视图；无选择时再回退到当前环境。
      orderStore.getBackups(orderStore.backupProfileId || settings.value.current_profile_id || 'default')
      return true
    } catch (e) {
      toast.error(`刷新数据失败: \n${e.message}`)
      return false
    } finally {
      isLoading.value = false
    }
  }
  const applyModPackageImportPostActions = async (task) => {
    const profileStore = useProfileStore()
    const workspaceStore = useWorkspaceStore()
    const postActions = task?.metrics?.post_actions || {}
    const shouldScanCurrentView = !!postActions.scan_current_view
    const shouldRefreshCurrentProfile = !!postActions.refresh_current_profile
    const shouldRefreshProfileList = !!postActions.refresh_profile_list

    const followUpTasks = []
    if (shouldRefreshProfileList) {
      followUpTasks.push(profileStore.fetchProfiles())
    }
    if (shouldRefreshCurrentProfile) {
      followUpTasks.push(refreshData())
    }
    if (shouldRefreshProfileList) {
      followUpTasks.push(workspaceStore.fetchGithubRepos())
      followUpTasks.push(workspaceStore.fetchSavedCollections())
    }
    if (followUpTasks.length > 0) {
      await Promise.all(followUpTasks)
    }
    if (shouldScanCurrentView) {
      await requestModScan()
    }
  }
  const showExportCompleteDialog = async (title, targetPath) => {
    const normalizedPath = String(targetPath || '').trim()
    if (!normalizedPath) {
      toast.success(`${title}完成`)
      return
    }
    const confirmStore = useConfirmStore()
    const action = await confirmStore.confirmAction(
      `${title}完成`,
      `导出路径：${normalizedPath}`,
      {
        type: 'success',
        actionButtons: [
          { label: '打开导出目录', value: 'open', kind: 'primary' },
          { label: '关闭', value: 'close', kind: 'secondary' },
        ],
      }
    )
    if (action === 'open') {
      // 后端会在传入文件路径时打开其所在目录，这里保留完整导出路径方便日志和异常提示定位。
      await openPath(normalizedPath)
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
      await modStore.scanComplete(detail)
      if (pendingModScanRequested.value) {
        window.setTimeout(() => {
          void flushQueuedModScan()
        }, 0)
      }
    })

    // 监听：本地化完成
    window.addEventListener('localize-complete', (e) => {
        const { success_count, error_count, errors, status } = e.detail;
        console.log(`本地化完成。成功: ${success_count}, 失败: ${error_count}`, errors)
        if (status === 'cancelled') {
            toast.info('本地化任务已取消');
            return
        }
        if (error_count > 0) {
            toast.warning(`本地化完成。成功: ${success_count}, 失败: ${error_count}`);
        } else {
            toast.success(`成功本地化 ${success_count} 个模组`);
        }
        const modStore = useModStore()
        modStore.scanMods()
    });
    // 监听：游戏暂停
    window.addEventListener('app-suspending', () => {
      console.log('检测到游戏启动，停止所有界面活动...');
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
        toast.error(detail.message)
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
        if (filename) toast.success(`下载完成: ${filename}`)
        const textureStore = useTextureStore()
        textureStore.handleDownloadEvent(task)
      }
      if (task.type === 'download' && task.status === 'failed') {
        toast.error(`下载失败: ${task.metrics?.filename || task.message}\n${task.metrics?.error || ''}`)
      }
      if (task.type === 'steamcmd-download' && task.status === 'failed') {
        toast.error(`SteamCMD 下载失败: ${task.metrics?.error || task.message}`)
      }
      if (task.type === 'steam-subscribe' && task.status === 'success') {
        void (async () => {
          await requestModScan()
          toast.success('Steam 订阅已完成')
        })()
      }
      if (task.type === 'steam-unsubscribe' && task.status === 'success') {
        void (async () => {
          await requestModScan()
          toast.success('Steam 取消订阅已完成')
        })()
      }
      if (task.type === 'steam-subscribe' && task.status === 'failed') {
        toast.error(`Steam 订阅失败: ${task.metrics?.error || task.message}`)
      }
      if (task.type === 'steam-unsubscribe' && task.status === 'failed') {
        toast.error(`Steam 取消订阅失败: ${task.metrics?.error || task.message}`)
      }
      if (task.type === 'update' && task.status === 'success' && task.metrics?.ready_to_install) {
        if (updateState.info) updateState.info.local_status = 'ready'
        if (!updateInstallPrompted.has(task.id)) {
          updateInstallPrompted.add(task.id)
          _showInstallPrompt(task.metrics)
        }
      }
      if (task.type === 'update' && task.status === 'failed') {
        toast.error(`更新出错: ${task.metrics?.error || task.message}`)
      }
      if (task.type === 'mod-export' && task.status === 'success') {
        if (!task.id || !exportCompletePrompted.has(task.id)) {
          if (task.id) exportCompletePrompted.add(task.id)
          void showExportCompleteDialog('模组包导出', task.metrics?.target_path)
        }
      }
      if (task.type === 'mod-export' && task.status === 'failed') {
        toast.error(task.metrics?.error || task.message || '模组包导出失败')
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
        toast.error(task.metrics?.error || task.message || '模组包导入失败')
      }
      if (task.type === 'mod-import' && task.status === 'cancelled') {
        toast.warning('模组包导入已取消')
      }
    });
    // 监听：后端弹窗
    window.addEventListener('backend-popup', (e) => {
      console.log('收到后端弹窗:', e)
      _backendPopup(e)
    })
  }

  // --- 设置相关 ---
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
  // 重置数据库
  const resetDatabase = async () => {
    if (!window.pywebview) return
    isLoading.value = true
    try {
      const res = await window.pywebview.api.reset_database()
      if (checkResult(res, "重置数据库")) {
        closeSettingsPanel()
        // 提示成功
        toast.success("数据库已重置！")
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
      toast.success('无效数据清理完成，正在刷新列表...')
      await refreshData()
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
      toast.error(`取消任务异常: \n${e.message}`)
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
  // 自动检测路径
  const autoDetectPaths = async (updateStore = false) => {
    if(!window.pywebview) return
    const res = await window.pywebview.api.auto_detect_paths(false)
    if (checkResult(res, "自动检测路径", true) && res.data.paths) {
       // 更新本地 setting store
      if(updateStore) {
        Object.assign(settings.value, res.data.paths)
        toast.success("路径已更新")
      }
      return res.data.paths
    }
  }
  const getDefaultExternalPaths = async () => {
    if(!window.pywebview) return
    const res = await window.pywebview.api.get_default_external_paths()
    if (checkResult(res, "获取默认外部路径",true) && res.data.paths) {
      return res.data.paths
    }
  }
  // 检测路径信息
  const checkPath = async (path_type, path) => {
    if(!path_type || !path) return
    if(!window.pywebview) return
    const res = await window.pywebview.api.path_check(path_type, path)
    if (checkResult(res, "检测路径信息")) {
      return res.data
    }
  }
  // 检测路径信息
  const checkPaths = async (path_data) => {
    if(!path_data) return
    if(!window.pywebview) return
    const res = await window.pywebview.api.paths_check(path_data)
    if (checkResult(res, "批量检测路径信息")) {
      return res.data
    }
  }
  // 打开路径
  const openPath = async (path) => {
    if(!window.pywebview) return
    if(!path) return
    console.log("打开路径:", path)
    const res = await window.pywebview.api.path_open(path)
    checkResult(res, "打开路径")
  }
  const openFile = async (path) => {
    if (!window.pywebview) return
    if (!path) return
    const res = await window.pywebview.api.path_open_file(path)
    checkResult(res, '打开文件')
  }
  const readTextFile = async (path, maxBytes = 2 * 1024 * 1024) => {
    if (!window.pywebview) return null
    if (!path) return null
    const res = await window.pywebview.api.path_read_text_file(path, maxBytes)
    if (checkResult(res, '读取文本文件', false)) {
      return res.data
    }
    return null
  }
  // 获取文件路径
  const getFilePath = async (home_path, file_types=('XML Files (*.xml;*.rws)', 'All Files (*.*)')) => {
    if(!window.pywebview) return
    // 调用后端 API
    const res = await window.pywebview.api.file_select_dialog(home_path, file_types)
    if (checkResult(res, "获取文件路径")) {
      return res.data
    } else return
  }
  // 获取文件夹路径
  const getFolderPath = async (home_path) => {
    if(!window.pywebview) return
    if(!home_path) home_path=''
    // 调用后端 API
    const res = await window.pywebview.api.folder_select_dialog(home_path)
    if (checkResult(res, "获取文件夹路径")) {
        return res.data
    } else if (res.status === 'error') {
        console.error("获取文件夹路径异常:", res.message)
    }
  }
  // 删除文件/文件夹
  const deletePath = async (path, reScan=true) => {
    if(!window.pywebview) return
    const confirmStore = useConfirmStore()
    const decision = await confirmStore.confirmDeleteAction(
      '删除确认', `确定要删除 ${path} 吗？`,
      {
        trashOptionText: '移入回收站',
        forceOptionText: '强制删除',
      }
    );
    if(!decision?.confirmed) return
    const res = await window.pywebview.api.path_delete(path, !!decision.force)
    if (checkResult(res, "删除文件/文件夹")) {
      toast.success(`${decision.force ? '已彻底删除' : '已移入回收站'}: \n${path}`)
      if(reScan){
        // 刷新Mod列表
        const modStore = useModStore()
        modStore.scanMods()
      }
      return true
    }
  }
  // 批量删除文件/文件夹
  const deletePaths = async (paths) => {
    if(!window.pywebview) return
    const confirmStore = useConfirmStore()
    const decision = await confirmStore.confirmDeleteAction(
      '删除确认', `确定要删除这 ${paths.length} 个文件/文件夹吗？`,
      {
        trashOptionText: '移入回收站',
        forceOptionText: '强制删除',
      }
    );
    if(!decision?.confirmed) return
    const res = await window.pywebview.api.paths_delete(paths, !!decision.force)
    if (checkResult(res, "批量删除文件/文件夹")) {
      toast.success(`${decision.force ? '已彻底删除' : '已移入回收站'} ${paths.length} 个文件/文件夹`)
      // 刷新Mod列表
      const modStore = useModStore()
      modStore.scanMods()
      return true
    }
  }
  // 打开Url
  const openUrl = (url) => {
    if(!url) { toast.warning("网址为空！"); return}
    if (isBrowserRuntime()) {
      openManagedSubBrowserUrl(url, 'RimModManager')
      return
    }
    if(settings.value.open_url_on_system){
      window.open(url, '_blank')
    }else{
      if (!window.pywebview) return
      window.pywebview.api.open_sub_browser(url)
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
  const GAME_LAUNCH_WARNING_REASON = Object.freeze({
    STEAM_PATH_INVALID: 'steam_path_invalid',
    STEAM_RUNNING_WORKSHOP_CONFLICT: 'steam_running_workshop_conflict',
  })
  const sleep = (ms) => new Promise(resolve => window.setTimeout(resolve, ms))

  const showSteamNotReadyHint = (res) => {
    const statusHint = res?.data?.steam_status?.user_hint
    if (res?.data?.action === 'steam_not_ready' && statusHint?.message) {
      toast.warning(`${statusHint.title || 'Steam 未就绪'}\n${statusHint.message}`, { timeout: 6000 })
    }
  }

  const buildGameLaunchWarningConfig = (gameRes) => {
    const reason = String(gameRes?.data?.reason || '').trim()
    const fallbackMessage = String(gameRes?.message || '').trim()
    switch (reason) {
      case GAME_LAUNCH_WARNING_REASON.STEAM_PATH_INVALID:
        return {
          type: 'warning',
          mode: 'confirm',
          title: 'Steam 启动不可用',
          message: '当前环境配置为优先使用 Steam 启动，但未检测到有效的 Steam 程序路径。\n你可以改为直接启动游戏本体，或先修复 Steam 路径后重试。',
          confirmText: '直接启动',
          cancelText: '取消',
          action: 'continue',
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
    console.log('后端弹窗:', event.detail)
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
    const safePath = encodeURIComponent(rawPath)
    return `${getAssetBaseUrl()}/thumb?id=${packageId}&path=${safePath}`
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
    const safeUrl = encodeURIComponent(remoteUrl)
    return `${getAssetBaseUrl()}/remote?url=${safeUrl}`
  }

  const refreshRemoteImageCacheStats = async () => {
    if (!window.pywebview) return null
    const res = await window.pywebview.api.get_remote_image_cache_stats()
    if (!checkResult(res, '获取网络图片缓存统计')) return null
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

  const openPackageTransferDialog = (mode = 'mod-import', preset = {}) => {
    packageTransferDialog.mode = String(mode || 'mod-import')
    packageTransferDialog.preset = { ...(preset || {}) }
    uiState.showPackageTransferDialog = true
  }

  const openCustomModExportDialog = ({
    title = '导出模组',
    description = '可按需附带依赖、联锁项和语言包。',
    modIds = [],
    summary = '',
  } = {}) => {
    const normalizedModIds = [...new Set(
      (modIds || [])
        .map(id => String(id || '').trim())
        .filter(Boolean)
    )]
    openPackageTransferDialog('mod-export', {
      title,
      description,
      mod_ids: normalizedModIds,
      allowExtraOptions: true,
      export_scope: 'custom',
      summary: summary || `已选 ${normalizedModIds.length} 个模组。`,
    })
  }

  const updatePackageTransferDialogPreset = (patch = {}) => {
    Object.assign(packageTransferDialog.preset, patch || {})
  }

  const closePackageTransferDialog = () => {
    uiState.showPackageTransferDialog = false
    packageTransferDialog.mode = 'mod-import'
    packageTransferDialog.preset = {}
  }

  // === Steam客户端交互 ===
  // 兼容旧调用名：手动检查工具环境并按需弹窗。
  const checkSteamTools = async () => checkToolMaintenance({ manual: true, prompt: true })
  // 下载创意工坊项目
  const downloadWorkshopItems = async (workshop_ids) => {
    if (!window.pywebview) return
    const res = await window.pywebview.api.steamcmd_download(workshop_ids)
    if (checkResult(res, "下载创意工坊项目")) {
      toast.success(`开始下载 ${workshop_ids.length} 个创意工坊项目`)
    }
  }
  // 打开Steam创意工坊
  const openSteamWorkshopUrl = (url) => {
    if(url) {
      const steamUrl = url.replace('https://steamcommunity.com/sharedfiles/filedetails/?id=', 'steam://url/CommunityFilePage/')
      window.open(steamUrl, '_blank')
    }
  }
  const openSteamWorkshopById = (id) => {
    if(id) {
      const steamUrl = `steam://url/CommunityFilePage/${id}`
      window.open(steamUrl, '_blank')
    }
  }
  const openInstallSource = (source) => {
    const normalizedSource = normalizeInstallSource(source, source?.packageId || source?.package_id)
    if (!normalizedSource) return false
    if (normalizedSource.kind === 'workshop') {
      openSteamWorkshopById(normalizedSource.workshopId)
      return true
    }
    openUrl(normalizedSource.url)
    return true
  }
  const subscribeInstallSources = async (sources = []) => {
    const normalizedSources = normalizeInstallSources(sources)
    const workshopIds = [...new Set(
      normalizedSources
        .filter(source => source.kind === 'workshop')
        .map(source => source.workshopId)
        .filter(Boolean)
    )]
    const skippedUrlCount = normalizedSources.filter(source => source.kind === 'url').length
    if (workshopIds.length === 0) {
      if (skippedUrlCount > 0) {
        toast.info('URL 来源暂不支持订阅，只能打开来源页或后续扩展下载流程。')
      }
      return false
    }
    const success = await subscribeWorkshopIds(workshopIds)
    if (success && skippedUrlCount > 0) {
      toast.info(`已跳过 ${skippedUrlCount} 个 URL 来源订阅项`)
    }
    return success
  }
  const downloadInstallSources = async (sources = []) => {
    const normalizedSources = normalizeInstallSources(sources)
    const workshopIds = [...new Set(
      normalizedSources
        .filter(source => source.kind === 'workshop')
        .map(source => source.workshopId)
        .filter(Boolean)
    )]
    const urlSources = normalizedSources.filter(source => source.kind === 'url' && source.url)
    if (workshopIds.length === 0 && urlSources.length === 0) return false
    if (workshopIds.length > 0) {
      await downloadWorkshopItems(workshopIds)
    }
    if (urlSources.length > 0) {
      urlSources.forEach(source => openUrl(source.url))
      toast.info(`已打开 ${urlSources.length} 个外部来源，后续可接入专门下载流程。`)
    }
    return true
  }
  const resolveWorkshopIdsFromPackageIds = async (packageIds) => {
    if (!packageIds) return []
    const workshopStore = useWorkspaceStore()
    return await workshopStore.resolvePackageIdsToWorkshopIds(packageIds)
  }
  // 根据包名下载Mod
  const downloadPackageIds = async (packageIds) => {
    const workshopIds = await resolveWorkshopIdsFromPackageIds(packageIds)
    if (workshopIds.length === 0) return false
    // 调用下载函数
    await downloadWorkshopItems(workshopIds)
    return true
  }
  // 根据包名订阅Mod
  const subscribePackageIds = async (packageIds) => {
    const workshopIds = await resolveWorkshopIdsFromPackageIds(packageIds)
    if (workshopIds.length === 0) return false
    // 调用订阅函数
    await subscribeWorkshopIds(workshopIds)
    return true
  }
  // 订阅模组
  const subscribeWorkshopIds = async (workshop_ids) => {
    if (!window.pywebview) return
    if (!workshop_ids || workshop_ids.length === 0) return
    const res = await window.pywebview.api.steam_subscribe(workshop_ids)
    if (res?.status === 'success') {
      toast.info(`已发送 ${workshop_ids.length} 个创意工坊项目的订阅请求`, { timeout: 2500 })
      return true
    }
    if (res?.status === 'warning') {
      showSteamNotReadyHint(res)
      return false
    }
    toast.error(`订阅失败: ${res?.message || '未知错误'}`)
    return false
  }
  // 取消订阅模组
  const unsubscribeWorkshopIds = async (workshop_ids, deletePathHashes = null, deleteOptions = {}) => {
    if (!window.pywebview) return false
    if (!workshop_ids || workshop_ids.length === 0) return
    const res = await window.pywebview.api.steam_unsubscribe(workshop_ids)
    if (res?.status === 'success') {
      const normalizedDeleteHashes = Array.isArray(deletePathHashes)
        ? deletePathHashes.filter(Boolean)
        : []
      if (normalizedDeleteHashes.length > 0) {
        const deleteRes = await window.pywebview.api.mods_delete(normalizedDeleteHashes, !!deleteOptions.force)
        if (deleteRes?.status !== 'success') {
          toast.error(`取消订阅成功，但删除副本失败: ${deleteRes?.message || '未知错误'}`)
          return false
        }
        const modStore = useModStore()
        await modStore.scanMods()
        toast.info(`已取消订阅并删除 ${normalizedDeleteHashes.length} 个工坊副本`, { timeout: 2500 })
        return true
      }
      toast.info(`已发送 ${workshop_ids.length} 个创意工坊项目的取消订阅请求`, { timeout: 2500 })
      return true
    }
    if (res?.status === 'warning') {
      showSteamNotReadyHint(res)
      return false
    }
    toast.error(`取消订阅失败: ${res?.message || '未知错误'}`)
    return false
  }
  // 获取订阅合集列表
  const getCollectionItems = async (collection_id) => {
    if (!window.pywebview) return
    const res = await window.pywebview.api.steam_collection_items_get(collection_id)
    if (checkResult(res, `获取订阅合集列表 ${collection_id}`)) {
      return res.data
    }
  }

  // --- 统一软件数据导入导出 ---
  const getDataBundleSchema = async () => {
    if (!window.pywebview) return null
    const res = await window.pywebview.api.data_bundle_get_schema()
    return checkResult(res, '获取数据导入导出配置') ? res.data : null
  }
  const inspectDataBundle = async (bundlePath) => {
    if (!window.pywebview || !bundlePath) return null
    const res = await window.pywebview.api.data_bundle_inspect(bundlePath)
    return checkResult(res, '读取数据包摘要') ? res.data : null
  }
  const exportDataBundle = async (payload = {}) => {
    if (!window.pywebview) return false
    const res = await window.pywebview.api.data_bundle_export(payload)
    if (!checkResult(res, '导出软件数据', true)) return false
    window.setTimeout(() => {
      void showExportCompleteDialog('软件数据导出', res.data?.path)
    }, 0)
    return res.data
  }
  const importDataBundle = async (bundlePath, payload = {}) => {
    if (!window.pywebview || !bundlePath) return false
    isLoading.value = true
    try {
      const res = await window.pywebview.api.data_bundle_import(bundlePath, payload)
      if (!checkResult(res, '导入软件数据', true)) return false

      const profileStore = useProfileStore()
      const workspaceStore = useWorkspaceStore()
      Object.assign(settings.value, res.data?.settings || {})
      profileStore.activeContext = res.data?.active_context || profileStore.activeContext

      await refreshData()
      await Promise.all([
        profileStore.fetchProfiles(),
        workspaceStore.fetchGithubRepos(),
        workspaceStore.fetchSavedCollections(),
      ])

      const warnings = res.data?.result?.warnings || []
      if (warnings.length > 0) {
        toast.warning(warnings.join('\n'), { timeout: 8000 })
      }
      return res.data
    } finally {
      isLoading.value = false
    }
  }
  const getModPackageSchema = async () => {
    if (!window.pywebview) return null
    const res = await window.pywebview.api.mod_package_get_schema()
    return checkResult(res, '获取模组打包配置') ? res.data : null
  }
  const prepareModPackageImport = async (bundlePath, payload = {}) => {
    if (!window.pywebview || !bundlePath) return null
    const res = await window.pywebview.api.mod_package_prepare_import(bundlePath, payload)
    return checkResult(res, '预检模组包导入') ? res.data : null
  }
  const getModPackageProfileSummary = async (profileId = '') => {
    if (!window.pywebview) return null
    const res = await window.pywebview.api.mod_package_get_profile_summary(profileId)
    return checkResult(res, '读取环境导出统计') ? res.data : null
  }
  const exportModPackage = async (payload = {}) => {
    if (!window.pywebview) return false
    const res = await window.pywebview.api.mod_package_export(payload)
    if (!checkResult(res, '启动导出任务')) return false
    const taskId = String(res.data?.task_id || '').trim()
    if (taskId) {
      taskStore.createPlaceholderTask({
        id: taskId,
        type: 'mod-export',
        status: 'pending',
        progress: 0,
        message: '准备导出模组包...',
        metrics: {
          title: '导出模组包',
          target_path: res.data?.target_path || '',
        },
      })
    }
    return res.data
  }
  const importModPackage = async (bundlePath, payload = {}) => {
    if (!window.pywebview || !bundlePath) return false
    if (taskStore.hasActiveTaskOfType('mod-import')) {
      toast.info('已有模组包导入任务正在进行')
      return false
    }
    const normalizedPayload = { ...(payload || {}) }
    const res = await window.pywebview.api.mod_package_import(bundlePath, normalizedPayload)
    if (!checkResult(res, '启动模组包导入')) return false
    const taskId = String(res.data?.task_id || '').trim()
    if (taskId) {
      taskStore.createPlaceholderTask({
        id: taskId,
        type: 'mod-import',
        status: 'pending',
        progress: 0,
        message: '准备导入模组包...',
        metrics: {
          title: '导入模组包',
          bundle_path: bundlePath,
        },
      })
    }
    return res.data
  }

  // === 更新相关函数 ===
  // 检查更新
  const checkUpdate = async (manual = true) => {
    updateState.isChecking = true
    logMaintenanceCheck('api_start', { id: 'app-update', name: '软件更新', manual })
    try {
      const res = await window.pywebview.api.update_check(manual)
      if (checkResult(res, "检查更新")) {
        const info = res.data
        logMaintenanceCheck('api_result', { id: 'app-update', name: '软件更新', manual, status: res.status, hasUpdate: !!info?.has_update, version: info?.version || '', localStatus: info?.local_status || '' })
        if (info.has_update) {
          updateState.hasUpdate = true
          updateState.info = info
          const promptQueue = usePromptQueueStore()
          await promptQueue.enqueue({
            category: 'startup-app-update',
            title: `发现新版本 v${info.version}`,
            message: `来源: ${info.source_name || '未知'}。文件大小: ${info.file_size || '未知'}。`,
            type: 'success',
            priority: manual ? 20 : 50,
            items: [{
              id: info.version || 'app-update',
              title: `RimModManager v${info.version}`,
              description: info.changelog || '发现可用更新。',
              raw: info,
              actions: [
                { id: 'update', label: '立即更新', kind: 'primary' },
                { id: manual ? 'skip' : 'ignore', label: manual ? '以后再说' : '忽略此版本', kind: 'secondary' },
              ],
            }],
            bulkActions: [
              { id: 'update_all', label: '立即更新', kind: 'primary' },
              { id: manual ? 'skip_all' : 'ignore_all', label: manual ? '以后再说' : '忽略此版本', kind: 'secondary' },
            ],
            onItemAction: async (_item, actionId) => {
              if (actionId === 'update') {
                await _performUpdateAction()
              } else if (actionId === 'ignore' && !manual) {
                await window.pywebview.api.update_ignore_version(info.version)
              }
            },
            onBulkAction: async (actionId) => {
              if (actionId === 'update_all') {
                await _performUpdateAction()
              } else if (actionId === 'ignore_all' && !manual) {
                await window.pywebview.api.update_ignore_version(info.version)
              }
            },
          })
        } else if (manual) {
          toast.success("当前已是最新版本")
        }
      } else {
        logMaintenanceCheck('api_result', { id: 'app-update', name: '软件更新', manual, status: res?.status || 'error', message: res?.message || '' }, 'warn')
      }
    } catch (error) {
      logMaintenanceCheck('api_error', { id: 'app-update', name: '软件更新', manual, message: error?.message || String(error || '') }, 'error')
      throw error
    } finally {
      updateState.isChecking = false
    }
  }
  const showChangelog = async () => {
    // 1. 如果当前没有日志数据（比如是从设置面板点进来的），主动从后端拉取
    if (!upgradeContext.value.changelog || upgradeContext.value.changelog.length === 0) {
      isLoading.value = true // 开启加载动画
      try {
        const res = await window.pywebview.api.get_changelog()
        if (res.status === 'success') {
          upgradeContext.value.changelog = res.data
        }
      } catch (e) {
          console.error("无法获取更新日志:", e)
      } finally {
          isLoading.value = false
      }
    }
    // 2. 显示弹窗
    uiState.showUpdateModal = true
  }
  const _showInstallPrompt = async (data) => {
    const confirmStore = useConfirmStore()
    const ok = await confirmStore.confirmAction(
      `确认安装更新？`,
      `压缩包已经下载到：${data.path}\n是否继续安装更新？安装后将重启应用程序。`,
      { confirmText: '确认安装', cancelText: '取消', type: 'warning' }
    )
    if (!ok) return toast.info("用户取消安装")
    await _performUpdateAction()
  }
  // 触发操作 (下载 OR 安装)
  const _performUpdateAction = async () => {
    const info = updateState.info
    if (!info) return
    // 如果是 Ready 状态，弹出最后确认框 (因为会重启)
    if (info.local_status === 'ready') {
      const confirmStore = useConfirmStore()
      const ok = await confirmStore.confirmAction(
        "准备重启",
        "安装包已准备就绪。点击确认将关闭当前程序并自动安装更新。",
        { confirmText: '立即重启安装', type: 'warning' }
      )
      if (!ok) return
    }

    // 调用统一接口
    const res = await window.pywebview.api.update_trigger_action()
    if (checkResult(res,'开始下载更新包')) {
      // 如果后端开始下载，这里不需要做什么，因为 EventListener 会接管进度条
      if (res.data && res.data.status === 'downloading') {
        toast.info("开始下载更新包...")
      }
    } else {
      toast.error(res.message)
    }
  }
  // 更新外置数据库
  const updateExternalDB = async (type) => {
    try {
      const workNameMap = {
        community_rules: '更新社区规则库',
        workshop_db: '更新社区工坊数据库',
        instead_db: '更新替代 Mod 数据库',
      }
      // 调用 API
      const res = await window.pywebview.api.update_external_db(type)
      if (checkResult(res, workNameMap[type] || `更新外置数据库 ${type}`)) {
        const task_id = res.data.task_id
        await waitForDownload(task_id)
        // 重新获取数据
        await refreshData() 
      }
    } catch (error) {
      toast.error("更新社区库失败: " + error.message)
    }
  }

  return {
    appVersion, buildMode, uiState, settings, isLoading, isDownloading, isScanRunning, updateState,
    themes, currentTheme, userThemes, themeEditor,
    packageTransferDialog,
    remoteImageCache, DEFAULT_DETAILS_LAYOUT, DETAILS_LAYOUT_MAPS, DEFAULT_MAIN_LAYOUT, MAIN_LAYOUT_MAPS, SIDEBAR_TABS, activeSidebarTab, isGameRunning, isSuspended, runtimeSession, upgradeContext,
    initialize, checkResult, refreshData, toggleUiState, scalePx, performDatabaseCleanup, recordScroll, getScroll, enterSleepMode, exitSleepMode,
    refreshModsData,
    requestModScan,
    getThumbUrl, getLocalUrl, getRemoteUrl, refreshRemoteImageCacheStats, clearRemoteImageCache,
    // 游戏相关
  checkPath, checkPaths, launchGame, autoDetectPaths, getDefaultExternalPaths, openPath, openFile, readTextFile, getFilePath, getFolderPath, deletePath, deletePaths, openUrl,
    startDownload, waitForDownload, downloadWorkshopItems, getCollectionItems, downloadPackageIds, subscribePackageIds, openSteamWorkshopById,
    saveSetting, applySettings, refreshUserThemes, saveUserTheme, deleteUserTheme, openSettingsPanel, closeSettingsPanel, resetDatabase, repairDatabase, restartApplication, showChangelog, setSidebarTab, cancelTextureTask, cancelTaskByProgress, supportsTaskCancellation, canCancelTask, isTaskCancelPending,
    openPackageTransferDialog, openCustomModExportDialog, updatePackageTransferDialogPreset, closePackageTransferDialog,
    
    checkSteamTools, checkToolMaintenance, checkExternalDataUpdates, checkManagedModUpdates, checkSteamcmdModUpdates, runScheduledMaintenanceChecks,
    openSteamWorkshopUrl, unsubscribeWorkshopIds, subscribeWorkshopIds, subscribeInstallSources, downloadInstallSources, openInstallSource, checkUpdate, updateExternalDB,
    getDataBundleSchema, inspectDataBundle, exportDataBundle, importDataBundle,
    getModPackageSchema, prepareModPackageImport, getModPackageProfileSummary, exportModPackage, importModPackage,
  }
})
