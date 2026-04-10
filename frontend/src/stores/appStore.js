// stores/appStore.js

import { defineStore } from 'pinia'
import { ref, reactive, computed, watch } from 'vue'
import { createToastInterface } from 'vue-toastification'
import { useModStore } from './modStore'
import { useGroupStore } from './groupStore'
import { useOrderStore } from './orderStore'
import { useRuleStore } from './ruleStore'
import { useConfirmStore } from './confirmStore'
import { useProfileStore } from './profileStore'
import { cleanRichText } from '../utils/unityTextParser'
import { useWorkspaceStore } from './workspaceStore'

export const useAppStore = defineStore('app', () => {
  const toast = createToastInterface()
  
  // === State ===
  const appVersion = ref('')     // 应用版本号
  const buildMode = ref('')      // 构建模式
  const isLoading = ref(false)   // 加载状态
  const isGameRunning = ref(false) // 新增：全局游戏运行状态
  
  // UI 状态
  const uiState = reactive({
    showSettingsPanel: false,    // 是否显示设置面板
    showUpdateModal: false,      // 是否显示更新弹窗
    showDiffDrawer: false,       // 是否显示差异抽屉
    showLogDrawer: false,        // 是否显示日志抽屉
    showTestDrawer: false,       // 是否显示测试抽屉
    showRuleDrawer: false,       // 是否显示规则抽屉
    showProfileDrawer: false,    // 是否显示环境抽屉
    showAiReviewModal: false,    // 是否显示 AI 弹窗
    showPromptManager: false,    // 是否显示提示词管理器
    showWorkspace: false,    // 是否显示工坊更新管理中心
  })
  // 存储各个列表的滚动偏移量
  // Key: listId (如 'active', 'inactive', 'temp'), Value: Number
  const scrollRegistry = ref(new Map());

  // 扫描进度
  const scanProgress = reactive({
    scanning: false, // 是否正在扫描中
    percent: 0,      // 进度百分比 (0-100)
    message: '',     // 当前正在扫描的文件名或阶段
    total: 0,        // 总文件数
    current: 0       // 当前处理数
  })
  // 更新相关状态
  const updateState = reactive({
    hasUpdate: false,
    info: null,    // 存储后端返回的 UpdateInfo
    isChecking: false,
    // 下载过程状态
    downloadStatus: 'idle', // idle | downloading | verifying | ready | error
    progress: 0,
    speed: '0 B/s',
    errorMsg: ''
  })
  // AI相关状态
  const aiState = reactive({
    isLoading: false,
    chatHistory: [],
    percent: 0,
    message: ''
  })
  const aiBatchResults = ref([]) // 存储实时返回的 AI 数据

  const upgradeContext = ref({}); // 升级上下文

  const taskPool = reactive(new Map());
  // 下载任务
  const downloadTasks = ref(new Map()) // 使用 Map 存储 {id: taskObject}
  // 存储任务回调的 Map
  // Key: task_id, Value: { resolve, reject, timeout }
  const downloadCallbacks = new Map()

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
    prefer_steam_launch: true,           // 是否优先通过 Steam 启动游戏
    steamcmd_mods_path: '',
    workshop_mods_path: '',
    self_mods_path: '',
    move_old_self_mods: false,
    enable_tool_mods: true,  // 是否启用工具 Mod
    link_deployment_mode_full: false,  // 链接部署模式: true=完全重建, false=增量部署

    user_rules_path: '',
    community_rules_url: '',
    community_rules_path: '',
    community_workshop_db_url: '',
    community_workshop_db_path: '',
    community_instead_db_url: '',
    community_instead_db_path: '',
    
    current_profile_id: 'default',
    asset_port: 0,

    // --- 系统 ---
    language: 'ZH-cn',
    window_width: 1400,
    window_height: 900,
    completed_guides: [],
    open_url_on_system: false,

    // --- 界面（UI） ---
    ui: {
      theme: 'system',
      font_size: 14,
      drag_delay: 30,            // 拖动判定延迟 (毫秒)
      detail_delay: 300,          // 详情页加载延迟 (毫秒)
      tooltip_hover_time: 1000,  // 鼠标悬停显示提示时间 (毫秒)
      show_mod_hover_panel: true,  // 是否显示 Mod 悬停面板
      show_ai_assistant: true,  // 是否显示 AI 助手入口
      show_ai_assistant_fab: true,  // 是否显示 AI 助手悬浮球
      double_click_active_mod: true,  // 是否双击启用/停用 Mod
      main_layout: JSON.parse(JSON.stringify(DEFAULT_MAIN_LAYOUT)),  // 主界面布局配置

      show_icons_cloud: true,  // 是否显示动态图标云
      mod_details_layout: JSON.parse(JSON.stringify(DEFAULT_DETAILS_LAYOUT)),   // Mod 详情面板布局配置

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
      provider: 'openai',
      base_url: '',
      api_key: '',
      model: 'gpt-3.5-turbo',
      temperature: 0.7,
      max_tokens: 5000,
      max_concurrency: 3,     // 最大并发请求数（避免被API封锁）
    },
    
    // --- 高级 (Advanced) ---
    backup_retention_days: 30,
    enable_auto_scan: true,
    enable_file_size_scan: true,         // 扫描时是否检查文件大小
    delete_missing_mods_data: false,
    auto_sort_strategy: "classic_sort_logic",  // 自动排序策略
    sort_mods_by: "name",                 // 自动排序排列方式: name, id, alias
    auto_activate_dependencies: false,     // 是否在排序时自动激活依赖项
    coexist_mod_folder_name_type: "workshop_id", // 共存Mod生成方式: workshop_id, package_id, name, alias
    show_coexistence_message: true,       // 是否显示共存Mod提示
    check_language_support: true,        // 是否检查语言支持
    language_packs_follow_targets: false, // 语言包是否贴紧其最后一个前置/依赖目标
    use_raw_ids: false,               // 是否使用原始 Mod ID

    // --- 调试 (Debug) ---
    debug_mode: true,
    log_retention_days: 7,
    log_level: 'INFO',
    enable_auto_update_check: true,  // 自动检查更新开关
    ignored_update_version: '',       // 跳过的版本号
    last_update_check_time: 0,      // 上次检查时间（用于限流）

  })


  // === Getters ===
  // 当前是否有正在进行的下载
  const isDownloading = computed(() => {
    for (const task of downloadTasks.value.values()) {
      if (task.status === 'running' || task.status === 'pending') return true
    }
    return false
  })
  // 获取最活跃的一个任务，用于状态栏显示
  const activeDownloadTask = computed(() => {
    // 优先返回 Running 的，没有则返回 Pending，再没有返回 Error/Completed
    const tasks = Array.from(downloadTasks.value.values())
    return tasks.find(t => t.status === 'running') || 
           tasks.find(t => t.status === 'pending') || 
           null
  })

  // 监听字体大小变化，实时更新根字号
  watch(() => settings.value.ui.font_size, (newSize) => {
    // 将根字号设置为用户定义的数值
    // 默认 14px，用户调大到 16px，所有使用 rem 的组件都会等比例变大
    document.documentElement.style.fontSize = `${newSize}px`;
  }, { immediate: true });
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
  // 通用结果检查
  const checkResult = (res, workname, showSuccess = false) => {
    if (settings.value.debug_mode) console.log('checkResult', workname, res)
    if (res.status === 'success') {
      if(showSuccess) toast.success(`${workname}成功`, {timeout: 1000})
      return true;
    }
    if (res.status === 'warning') toast.warning(`${workname}注意: \n${res.message}`)
    else toast.error(`${workname}失败: \n${res.message}`)
    return false
  }


  // === Actions ===
  // 初始化：获取数据并分类
  const initialize = async () => {
    isLoading.value = true
    try {
      // “暂停”直到 Python 后端连接成功
      await waitForBackend()
      // 注册事件监听
      setupEventListeners()

      // 获取初始数据 (这里包含 settings, version 等)
      await refreshData(true)
      let scanForce = false
      // 只有当版本真的发生过变动，且有待处理任务时才触发
      if (upgradeContext.value.version_changed) {
          console.log("检测到版本升级:", upgradeContext.value.old_version, "->", upgradeContext.value.new_version);
          
          // 1. 处理展示更新日志弹窗
          if (upgradeContext.value.pending_actions.includes('show_update_news')) {
            // handleUpdate(upgradeContext.value.changelog);
          }
          // 2. 强制刷新数据
          if (upgradeContext.value.pending_actions.includes('recommend_scan')) {
            scanForce = true
          }
          // 3. 处理静默通知 (Toast 告知用户后端干了什么)
          if (upgradeContext.value.actions_taken.length > 0) {
            toast.info(`升级完成: ${upgradeContext.value.actions_taken.join(', ')}`);
          }
      }
      const profileStore = useProfileStore()
      // 同步当前 Profile ID 到 profileStore
      if (settings.value.current_profile_id) {
        profileStore.currentProfileId = settings.value.current_profile_id
      }
      // 自动检查更新逻辑
      if (settings.value.enable_auto_update_check) {
        // 距离上次检查超过1天则检查更新
        const lastCheckTime = settings.value.last_update_check_time || 0
        const duration = Date.now() - lastCheckTime
        console.log("上次检查时间:", lastCheckTime, Date.now(), duration)
        if (!lastCheckTime || duration > 24 * 60 * 60 * 1000 || duration<0) {
          console.log("正在执行启动检查更新...")
          // 传入 false 表示静默检查
          checkUpdate(false) 
        }
      }
      // 界面渲染完毕后，根据设置决定是否启动后台扫描
      if (settings.value.enable_auto_scan !== false) {
        console.log("自动扫描开始...")
        toast.info("自动扫描开始...", {timeout: 1000})
        const modStore = useModStore()
        modStore.scanMods(null, scanForce)
      }
      // 检查 Steam 工具
      checkSteamTools()
      
    } catch (e) {
      console.error("初始化失败:", e)
      toast.error(`初始化失败：\n${e}`)
    } finally {
      isLoading.value = false
    }
  }
  // 刷新数据 (初始化核心)
  const refreshData = async (isInit = false) => {
    if (!window.pywebview) return
    isLoading.value = true
    try {
      // 调用后端获取全量数据
      const res = await window.pywebview.api.get_initial_data()
      if (checkResult(res, '刷新数据')) {
        // 覆盖更新 Settings，以后端属性为主 (仅初始化时，避免覆盖用户未保存的修改)
        if (isInit && res.data.settings) {
          settings.value = res.data.settings
          settings.value.asset_port = res.data.asset_port || 0
          upgradeContext.value = res.data.upgrade_context;
        }else{
          Object.assign(settings.value, res.data.settings)
        }
        // console.log('allmods', res.data.is_first_db_init , res.data.context_healthy , !res.data.all_mods||res.data.all_mods?.length==0)
        if (res.data.is_first_db_init && res.data.context_healthy && (!res.data.all_mods||res.data.all_mods?.length==0)) {
          toast.warning("数据库正在进行首次初始化，此过程可能需要您等待一段时间，请您耐心等候。",{position: "top-center",timeout: 10000})
        }
        // 更新软件信息
        appVersion.value = res.data.app_version || 'Unknown'  // 版本
        buildMode.value = res.data.build_mode || ''           // 构建模式
        const profileStore = useProfileStore()
        profileStore.fetchProfiles()
        if (res.data.active_context) {
          profileStore.activeContext = res.data.active_context
          // 触发健康哨兵拦截 (阻止初始化继续)
          // 检查路径 (主要路径无效则打开设置)
          if (!profileStore.activeContext.is_healthy) {
            toast.warning("未配置游戏路径，请先配置游戏路径。",{position: "top-center",timeout: 5000})
            uiState.showSettingsPanel = true
            // profileStore.checkHealthSentinel()
            return // 提早退出，不加载 Mod 列表
          }
        }
        // 更新 Groups (防止分组内的 Mod 被删了但分组里还有 ID)
        const groupStore = useGroupStore()
        groupStore.setGroups(res.data.groups || [])
        // 更新 Active列表 (防止外部修改 Active列表 导致的状态不一致)
        const modStore = useModStore()
        modStore.setMods(res.data)
        // 刷新动态规则
        const ruleStore = useRuleStore()
        ruleStore.fetchRules()
        const workspaceStore = useWorkspaceStore()
        workspaceStore.initData()
        const orderStore = useOrderStore()
        // 备份列表优先保持用户当前正在查看的环境视图；无选择时再回退到当前环境。
        orderStore.getBackups(orderStore.backupProfileId || settings.value.current_profile_id || 'default')
      }
    } catch (e) {
      toast.error(`刷新数据失败: \n${e.message}`)
    } finally {
      isLoading.value = false
    }
  }
  // 注册事件监听
  const setupEventListeners = () => {
    // 防止重复添加监听器
    if (window._modManagerEventsInitialized) return
    window._modManagerEventsInitialized = true
    
    // 监听：扫描开始
    window.addEventListener('scan-start', () => {
      scanProgress.scanning = true
      scanProgress.percent = 0
      scanProgress.message = '准备开始扫描...'
    })
    // 监听：扫描进度
    window.addEventListener('scan-progress', (e) => {
      // Python 发送的数据在 e.detail 中
      Object.assign(scanProgress, e.detail)
    })
    // 监听：扫描完成
    window.addEventListener('scan-complete', async (e) => {
      scanProgress.scanning = false
      scanProgress.message = '扫描完成'
      // 扫描完成后的逻辑主要涉及 Mod 数据更新
      const modStore = useModStore()
      await modStore.scanComplete(e.detail)
    })

    // 监听：下载进度
    window.addEventListener('download-progress', (e) => {
      const d = e.detail
      downloadTasks.value.set(d.id, d)
      // --- 核心：检查是否有正在等待该任务的 Promise ---
      const callback = downloadCallbacks.get(d.id)
      
      if (d.status === 'completed' && d.percent === 100) {
        toast.success(`下载完成: ${d.filename}`)
        console.log(`下载完成:`, d)
        if (callback) {
          clearTimeout(callback.timer)
          callback.resolve(d.file_path) // 返回文件路径
          downloadCallbacks.delete(d.id)
        }
      }
      if (d.status === 'error') {
        const errorMsg = `下载失败: ${d.filename}\n${d.error || ''}`
        toast.error(errorMsg)
        
        if (callback) {
          clearTimeout(callback.timer)
          callback.reject(new Error(errorMsg))
          downloadCallbacks.delete(d.id)
        }
      }
    })
    // 监听后端 EventBus 发出的 'update-status' 事件
    window.addEventListener('update-status', (event) => {
        const data = event.detail // { status, percent, speed, msg, path ... }
        console.log('[Frontend] Update Status:', data)
        
        // 同步状态到 UI
        updateState.downloadStatus = data.status
        
        if (data.status === 'downloading') {
            updateState.progress = data.percent || 0
            updateState.speed = data.speed || '0 B/s'
        } 
        else if (data.status === 'verifying') {
            updateState.speed = '正在校验文件完整性...'
            updateState.progress = 99
        }
        else if (data.status === 'ready') {
            updateState.progress = 100
            updateState.speed = '下载完成'
            // 更新 info 里的状态，让按钮变色
            if (updateState.info) updateState.info.local_status = 'ready'
            
            // 可选：下载完成后自动弹窗提示安装
            _showInstallPrompt(data) 
        }
        else if (data.status === 'error') {
            updateState.errorMsg = data.msg
            toast.error(`更新出错: ${data.msg}`)
        }
    })
    // 监听：AI 批量处理进度
    window.addEventListener('ai-batch-progress', (e) => {
      Object.assign(aiState, e.detail)
      aiState.isLoading = true 
    })

    // 每完成一个 Chunk，将数据推入数组，供弹窗实时渲染
    window.addEventListener('ai-batch-chunk-ready', (e) => {
      if (Array.isArray(e.detail)) {
        aiBatchResults.value.push(...e.detail)
      }
    })
    // 监听：AI 批量处理完成
    window.addEventListener('ai-batch-complete', (e) => {
      aiState.isLoading = false 
      if (e.detail.status === 'success') {
        const payload = e.detail.data // 获取后端的字典结果
        const successCount = payload.success_count || 0
        const failedCount = payload.failed_count || 0
        if (failedCount > 0) {
          toast.warning(`任务完成。成功: ${successCount}，失败/置空: ${failedCount} 项，请手动处理高亮条目。`, {timeout: 6000})
        } else {
          toast.success(`任务完美完成！成功生成 ${successCount} 项。`)
        }
        uiState.showAiReviewModal = true 
      } else {
        toast.error(`AI 任务异常: ${e.detail.message}`)
      }
    })
    // 监听：本地化进度
    window.addEventListener('localize-progress', (e) => {
        // 复用 scanProgress 的状态，或者建立独立的 localizeProgress
        Object.assign(scanProgress, {
            scanning: true, // 借用这个状态让进度条显示
            ...e.detail
        });
    });
    // 监听：本地化完成
    window.addEventListener('localize-complete', (e) => {
        scanProgress.scanning = false;
        const { success_count, error_count, errors } = e.detail;
        console.log(`本地化完成。成功: ${success_count}, 失败: ${error_count}`, errors)
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
      // 2. 停止所有正在轮询的定时器（如果有的话）
      if (scanProgress.scanning) scanProgress.scanning = false;
      // 3. 可以在这里做最后的自动保存
    });
    // 监听游戏状态变化
    window.addEventListener('game-status-changed', (e) => {
      isGameRunning.value = e.detail.running
    })
    // 通用进度更新
    window.addEventListener('global-progress', (e) => {
      const task = e.detail;
      taskPool.set(task.id, task);
      
      // 如果任务完成或失败，延迟 3 秒从 UI 移除
      if (['success', 'failed', 'cancelled'].includes(task.status)) {
        setTimeout(() => taskPool.delete(task.id), 3000);
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
  // 数据库孤立数据清理
  const performDatabaseCleanup = async () => {
    const res = await window.pywebview.api.perform_database_cleanup()
    if (checkResult(res, '数据库深度清理')) {
      toast.success('无效数据清理完成，正在刷新列表...')
      await refreshData()
    }
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
    const orderStore = useOrderStore()
    const res = await orderStore.saveLoadOrder()
    if (!res) return
    if (!window.pywebview) return
    // 直接启动游戏
    const gameRes = await window.pywebview.api.game_launch(profile_id)
    if (checkResult(gameRes, "启动游戏程序")) {
      toast.success(gameRes.message)
    }
  }
  // 触发睡眠 API
  const enterSleepMode = () => {
    if (window.pywebview) {
      window.pywebview.api.monitor_force_sleep()
    }
  }
  // 自动检测路径
  const autoDetectPaths = async (updateStore=true) => {
    if(!window.pywebview) return
    const res = await window.pywebview.api.auto_detect_paths(false)
    if (checkResult(res, "自动检测路径",true) && res.data.paths) {
       // 更新本地 setting store
      if(updateStore) {
        Object.assign(settings.value, res.data.paths)
        toast.success("路径已更新")
      }
      return res.data.paths
    }
  }
  const getDefaultCommunityPaths = async () => {
    if(!window.pywebview) return
    const res = await window.pywebview.api.get_default_community_paths()
    if (checkResult(res, "获取默认社区路径",true) && res.data.paths) {
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
    const confirm = await confirmStore.confirmAction(
      '删除确认', `确定要删除 ${path} 吗？\n文件/文件夹将被移至回收站。`,
      { type: 'error' }
    );
    if(!confirm) return
    const res = await window.pywebview.api.path_delete(path)
    if (checkResult(res, "删除文件/文件夹")) {
      toast.success(`已删除: \n${path}`)
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
    const confirm = await confirmStore.confirmAction(
      '删除确认', `确定要删除这 ${paths.length} 个文件/文件夹吗？\n这些文件/文件夹将被移至回收站。`,
      { type: 'error' }
    );
    if(!confirm) return
    const res = await window.pywebview.api.paths_delete(paths)
    if (checkResult(res, "批量删除文件/文件夹")) {
      toast.success(`已删除 ${paths.length} 个文件/文件夹`)
      // 刷新Mod列表
      const modStore = useModStore()
      modStore.scanMods()
      return true
    }
  }
  // 打开Url
  const openUrl = (url) => {
    if(!url) { toast.warning("网址为空！"); return}
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
    return new Promise((resolve, reject) => {
      // 设置超时处理
      const timer = setTimeout(() => {
        if (downloadCallbacks.has(taskId)) {
          downloadCallbacks.delete(taskId)
          reject(new Error('下载超时'))
        }
      }, timeout)

      // 注册回调
      downloadCallbacks.set(taskId, { resolve, reject, timer })
    })
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

  // === Steam客户端交互 ===
  // 检查Steam工具
  const checkSteamTools = async () => {
    if (!window.pywebview) return
    const res = await window.pywebview.api.check_steam_tools()
    if (checkResult(res, "检查Steam工具")) {
      
    }
  }
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
  // 根据包名下载Mod
  const downloadPackageIds = async (packageIds) => {
    if (!packageIds) return false
    const workshopStore = useWorkspaceStore()
    const workshopIdsMap = await workshopStore.getWorkshopIdsByPackageIdsMap(packageIds)
    if (!workshopIdsMap) return false
    // {zetrith.prepatcher: '2934420800'}
    const workshopIds = Object.values(workshopIdsMap)
    // 调用下载函数
    await downloadWorkshopItems(workshopIds)
    return true
  }
  // 根据包名订阅Mod
  const subscribePackageIds = async (packageIds) => {
    if (!packageIds) return false
    const workshopStore = useWorkspaceStore()
    const workshopIdsMap = await workshopStore.getWorkshopIdsByPackageIdsMap(packageIds)
    if (!workshopIdsMap) return false
    const workshopIds = Object.values(workshopIdsMap)
    // 调用订阅函数
    await subscribeWorkshopIds(workshopIds)
    return true
  }
  // 订阅模组
  const subscribeWorkshopIds = async (workshop_ids) => {
    if (!window.pywebview) return
    if (!workshop_ids || workshop_ids.length === 0) return
    const res = await window.pywebview.api.steam_subscribe(workshop_ids)
    if (checkResult(res, `订阅 ${workshop_ids.length} 个创意工坊项目`)) {
      toast.success(`订阅 ${workshop_ids.length} 个创意工坊项目成功，正在下载中...`)
      return true
    }
    else if (res.data && res.data.action === "need_start_steam") {
      const confirmStore = useConfirmStore()
      const ok = await confirmStore.confirmAction(
        'Steam 未运行', 
        '调用官方 API 订阅模组需要启动 Steam 客户端。\n是否现在启动 Steam？', 
        { type: 'warning', confirmText: '立即启动 Steam' }
      )
      if (ok) {
        const launchRes = await window.pywebview.api.steam_launch_client()
        if (checkResult(launchRes, "启动 Steam 客户端")) {
          // 因为 Steam 启动并登录账号通常需要 10-30 秒，建议提示用户等待后再操作
          toast.info("Steam 正在启动...\n请在登录完毕后，再次点击订阅按钮！", { timeout: 8000 })
        } else {
          toast.error(launchRes.message)
        }
      }
      return false
    } 
    // 其它常规报错
    else {
      toast.error(`订阅失败: ${res.message}`)
      return false
    }
  }
  // 取消订阅模组
  const unsubscribeWorkshopIds = async (workshop_ids) => {
    if (!window.pywebview) return false
    if (!workshop_ids || workshop_ids.length === 0) return
    // const modStore = useModStore()
    // const workshop_ids = modStore.takeModListByIds(mod_ids).filter(m => m.workshop_id).map(m => m.workshop_id)
    const res = await window.pywebview.api.steam_unsubscribe(workshop_ids)
    if (checkResult(res, `取消订阅 ${workshop_ids.length} 个创意工坊项目`,true)) {
      // if(delete_file) workshop_ids.forEach(id => deletePath(modStore.takeModById(id).path))
      toast.success(`已发送取消订阅请求`)
      return true
    }
    else if (res.data && res.data.action === "need_start_steam") {
      const confirmStore = useConfirmStore()
      const ok = await confirmStore.confirmAction(
        'Steam 未运行', 
        '调用官方 API 取消订阅需要启动 Steam 客户端。\n是否现在启动 Steam？', 
        { type: 'warning', confirmText: '立即启动 Steam' }
      )
      
      if (ok) {
        const launchRes = await window.pywebview.api.steam_launch_client()
        if (launchRes.status === 'success') {
          toast.info("Steam 正在启动...\n请在登录完毕后，再次执行取消订阅操作！", { timeout: 8000 })
        } else {
          toast.error(launchRes.message)
        }
      }
      return false
    } 
    // 其它常规报错
    else {
      toast.error(`取消订阅失败: ${res.message}`)
      return false
    }
  }
  // 获取订阅合集列表
  const getCollectionItems = async (collection_id) => {
    if (!window.pywebview) return
    const res = await window.pywebview.api.steam_collection_items_get(collection_id)
    if (checkResult(res, `获取订阅合集列表 ${collection_id}`)) {
      return res.data
    }
  }

  // === AI 交互 ===
  // 获取AI设置
  const getAiConfig = async () => {
    if (!window.pywebview) return
    const res = await window.pywebview.api.ai_get_config()
    if (checkResult(res, "获取AI配置")) {
      res.data.config
      res.data.prompts
    }
  }
  // 保存AI设置
  const saveAIConfig = async (config_data) => {
    if (!window.pywebview) return
    const res = await window.pywebview.api.ai_save_config(config_data)
    if (checkResult(res, "保存AI配置",true)) {
      return true
    }
  }
  // 获取AI厂商或代理协议列表
  const getAiProviders = async () => {
    if (!window.pywebview) return
    aiState.isLoading = true
    const res = await window.pywebview.api.ai_get_providers()
    if (checkResult(res, "获取AI厂商或代理协议列表")) {
      aiState.isLoading = false
      return res.data
    }
    aiState.isLoading = false
  }
  // 获取AI模型 temp_config: {provider, base_url, api_key}
  const getAiModels = async (temp_config) => {
    if (!window.pywebview) return
    if (!temp_config || !temp_config.provider) {
      return
    }
    aiState.isLoading = true
    try {
      const res = await window.pywebview.api.ai_get_models(temp_config)
      if (checkResult(res, "获取AI模型")) {
        return res.data
      }
    } finally {
      aiState.isLoading = false
    }
  }
  // 与AI聊天
  const chatWithAI = async (prompt, temp_config) => {
    if (!window.pywebview) return
    aiState.isLoading = true
    try {
      const res = await window.pywebview.api.ai_chat(prompt, temp_config)
      if (checkResult(res, "与AI聊天")) {
        return res.data
      }
    } finally {
      aiState.isLoading = false
    }
  }
  // 使用AI功能
  const useAI = async (task_key, params) => {
    if (!window.pywebview) return
    aiState.isLoading = true
    if (!settings.value.ai.enabled) {
      toast.warning("AI功能未启用！")
      aiState.isLoading = false
      return
    }
    try {
      const res = await window.pywebview.api.ai_execute_task(task_key, params)
      if (checkResult(res, `使用AI ${task_key}`)) {
        aiState.isLoading = false
        // 【核心修复】：判断返回的数据类型
        const data = res.data
        if (typeof data === 'string') {
          try {
            // 如果是字符串且看起来像 JSON，尝试解析
            if (data.trim().startsWith('{') || data.trim().startsWith('[')) {
              return JSON.parse(data)
            }
            return data // 普通文本字符串
          } catch (e) {
            console.warn("AI 返回了无法解析的字符串内容", data)
            return data
          }
        }
        // 如果已经是对象（后端已经 parse 过了），直接返回
        return data 
      }
    } catch (e) {
      console.error("AI 任务执行异常:", e)
    } finally {
      aiState.isLoading = false
    }
  }
  // 发起批量AI任务
  const startAiBatchTask = async (task_key, modsList) => {
    if (!window.pywebview) return
    aiBatchResults.value = [] // 清空旧数据
    
    // 【修改点 1】：不立刻弹窗，而是明确开启 isLoading 状态唤醒底部状态栏
    // uiState.showAiReviewModal = true 
    aiState.isLoading = true
    aiState.percent = 0
    aiState.message = '正在分配神经元计算资源...'
    
    toast.info("AI 批量任务已在后台启动，请留意底部状态栏。")
    
    // 提取必要字段减小发给大模型的体积
    const items = modsList.map(m => ({
      package_id: m.package_id,
      name: m.name,
      description: cleanRichText(m.description,1000)
    }))
    
    await window.pywebview.api.ai_execute_batch_task(task_key, items, {})
  }
  // --- 提示词管理 ---
  const fetchPrompts = async () => {
    if (!window.pywebview) return {}
    const res = await window.pywebview.api.ai_get_prompts()
    if (checkResult(res, "获取提示词库")) return res.data
    return {}
  }
  const savePrompt = async (id, data) => {
    if (!window.pywebview) return false
    const res = await window.pywebview.api.ai_save_prompt(id, data)
    return checkResult(res, "保存提示词", true) ? res.data : false
  }
  const deletePrompt = async (id) => {
    if (!window.pywebview) return false
    const res = await window.pywebview.api.ai_delete_prompt(id)
    return checkResult(res, "删除提示词", true) ? res.data : false
  }
  const resetPrompts = async () => {
    if (!window.pywebview) return false
    const res = await window.pywebview.api.ai_reset_prompts()
    return checkResult(res, "恢复默认提示词", true) ? res.data : false
  }

  // === 更新相关函数 ===
  // 检查更新
  const checkUpdate = async (manual = true) => {
    updateState.isChecking = true
    updateState.downloadStatus = 'idle' // 重置状态
    updateState.progress = 0
    try {
      const res = await window.pywebview.api.update_check(manual)
      if (checkResult(res, "检查更新")) {
        const info = res.data
        if (info.has_update) {
          updateState.hasUpdate = true
          updateState.info = info
          // 弹出全局确认框
          const confirmStore = useConfirmStore()
          const ok = await confirmStore.confirmAction(
            `发现新版本 v${info.version}`,
            `来源: ${info.source_name}<br/>文件大小: ${info.file_size || '未知'}<br/>更新内容:<br/>${info.changelog}`,
            { confirmText: '立即更新', cancelText: manual ? '以后再说' : '忽略此版本', type: 'success', isHtml: true }
          )
          if (ok) {
            // 触发下载
            _performUpdateAction()
          } else if (!manual) {
            // 如果是启动时的自动弹窗点取消，则询问是否不再提醒该版本
            await window.pywebview.api.update_ignore_version(info.version)
          }
        } else if (manual) {
          toast.success("当前已是最新版本")
        }
      }
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
    if (info.local_status === 'ready' || updateState.downloadStatus === 'ready') {
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
        updateState.downloadStatus = 'downloading'
        toast.info("开始下载更新包...")
      }
    } else {
      toast.error(res.message)
    }
  }
  // 更新外置数据库
  const updateExternalDB = async (type) => {
    try {
      // 调用 API
      const res = await window.pywebview.api.update_external_db(type)
      if (checkResult(res, `更新外置数据库 ${type}`)) {
        const task_id = res.data.task_id
        const filePath = await waitForDownload(task_id)
        // 重新获取数据
        await refreshData() 
      }
    } catch (error) {
      toast.error("更新社区库失败: " + error.message)
    }
  }

  return {
    appVersion, buildMode, uiState, scanProgress, settings, isLoading, isDownloading, downloadTasks, activeDownloadTask, updateState,
    aiState, aiBatchResults, DEFAULT_DETAILS_LAYOUT, DETAILS_LAYOUT_MAPS, DEFAULT_MAIN_LAYOUT, MAIN_LAYOUT_MAPS, SIDEBAR_TABS, activeSidebarTab, isGameRunning, upgradeContext,
    initialize, checkResult, refreshData, toggleUiState, scalePx, performDatabaseCleanup, recordScroll, getScroll, enterSleepMode,
    getThumbUrl, getLocalUrl, getRemoteUrl,
    // 游戏相关
    checkPath, checkPaths, launchGame, autoDetectPaths, getDefaultCommunityPaths, openPath, getFilePath, getFolderPath, deletePath, deletePaths, openUrl, 
    startDownload, waitForDownload, downloadWorkshopItems, getCollectionItems, downloadPackageIds, subscribePackageIds, openSteamWorkshopById,
    saveSetting, applySettings, openSettingsPanel, closeSettingsPanel, resetDatabase, showChangelog, setSidebarTab,
    
    checkSteamTools, openSteamWorkshopUrl, unsubscribeWorkshopIds, subscribeWorkshopIds, checkUpdate, updateExternalDB,
    // AI处理
    getAiConfig, saveAIConfig, getAiProviders, getAiModels, useAI, chatWithAI, startAiBatchTask, 
    fetchPrompts, savePrompt, deletePrompt, resetPrompts,
  }
})
