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

export const useAppStore = defineStore('app', () => {
  const toast = createToastInterface()
  
  // === State ===
  const appVersion = ref('')     // 应用版本号
  const buildMode = ref('')      // 构建模式
  const isLoading = ref(false)   // 加载状态
  
  // UI 状态
  const uiState = reactive({
    showSettingsPanel: false,    // 是否显示设置面板
    showDiffDrawer: false,       // 是否显示差异抽屉
    showLogDrawer: false,        // 是否显示日志抽屉
    showTestDrawer: false,       // 是否显示测试抽屉
    showRuleDrawer: false,       // 是否显示规则抽屉
    showProfileDrawer: false,    // 是否显示环境抽屉
  })
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
    isChecking: false
  })
  // AI相关状态
  const aiState = reactive({
    isLoading: false,
    chatHistory: []

  })
  // 下载任务
  const downloadTasks = ref(new Map()) // 使用 Map 存储 {id: taskObject}
  // 存储任务回调的 Map
  // Key: task_id, Value: { resolve, reject, timeout }
  const downloadCallbacks = new Map()

  // 全局设置
  const settings = ref({
    // --- 路径 (Paths) ---
    game_install_path: '',
    user_data_path: '',
    game_saves_path: '',
    game_config_path: '',
    game_dlc_path: '',
    local_mods_path: '',
    workshop_mods_path: '',
    use_workshop_mods: true,
    home_path: '',
    community_rules_url: '',
    community_rules_path: '',
    user_rules_path: '',
    game_version: '',
    current_profile_id: 'default',

    // --- 系统 ---
    language: 'ZH-cn',
    window_width: 1400,
    window_height: 900,
    open_url_on_system: false,

    // --- 界面（UI） ---
    ui: {
      theme: 'system',
      font_size: 14,
      tooltip_hover_time: 1000,  // 鼠标悬停显示提示时间 (毫秒)
      show_mod_hover_panel: true,  // 是否显示 Mod 悬停面板

      show_mod_details_panel: true,  // 是否显示 Mod 详情面板
      show_icons_cloud: true,  // 是否显示动态图标云
      show_mod_details_author_info: true,  // 是否显示 Mod 详情面板作者信息
      show_mod_details_files_info: true,  // 是否显示 Mod 详情面板文件信息
      show_mod_details_time_info: true,  // 是否显示 Mod 详情面板时间信息
      show_mod_details_dependencies_info: true,  // 是否显示 Mod 详情面板依赖信息
      show_mod_details_user_info: true,  // 是否显示 Mod 详情面板自定义信息
      show_mod_details_description: true,  // 是否显示 Mod 详情面板描述

      show_dependency_graph: true,  // 是否显示依赖关系图
      show_list_index: true,  // 是否显示列表索引列
      show_list_icon: true,       // 是否显示 Mod 图标
      show_list_mod_icon: true,       // 是否显示 Mod 图标
      show_list_modtype_icon: true,  // 是否显示 Mod 类型图标
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
      hosts: {} // Object: { 'domain': 'ip' }
    },

    // --- Steam ---
    steam: {
      steamcmd_path: '',
      use_steam_client: true,
      steam_appid: 294100
    },

    // --- AI ---
    ai: {
      enabled: false,
      provider: 'openai',
      base_url: 'https://api.openai.com/v1',
      api_key: '',
      model: 'gpt-3.5-turbo',
      temperature: 0.7,
      max_tokens: 2000
    },
    
    // --- 高级 (Advanced) ---
    backup_retention_days: 30,
    enable_auto_scan: true,
    delete_missing_mods_data: false,
    prefer_steam_launch: true,           // 是否优先通过 Steam 启动游戏
    sort_mods_by: "name",                 // 自动排序排列方式: name, id, alias
    coexist_mod_folder_name_type: "workshop_id", // 共存Mod生成方式: workshop_id, package_id, name, alias
    show_coexistence_message: true,       // 是否显示共存Mod提示

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

      // 先获取 Profile 列表和当前 ID
      const profileStore = useProfileStore()
      await profileStore.fetchProfiles()

      // 获取初始数据 (这里包含 settings, version 等)
      await refreshData(true)
      // 同步当前 Profile ID 到 profileStore
      if (settings.value.current_profile_id) {
        profileStore.currentProfileId = settings.value.current_profile_id
      }
      // 自动检查更新逻辑
      if (settings.value.enable_auto_update_check) {
        // 距离上次检查超过1天则检查更新
        const lastCheckTime = settings.value.last_update_check_time
        if (lastCheckTime && Date.now() - lastCheckTime > 24 * 60 * 60 * 1000) {
          console.log("正在执行启动检查更新...")
          // 传入 false 表示静默检查
          checkUpdate(false) 
        }
      }
      // 界面渲染完毕后，根据设置决定是否启动后台扫描
      if (settings.value.enable_auto_scan !== false && settings.value.game_install_path) {
        console.log("自动扫描开始...")
        toast.info("自动扫描开始...", {timeout: 1000})
        const modStore = useModStore()
        modStore.scanMods()
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
      // 刷新动态规则
      const ruleStore = useRuleStore()
      ruleStore.fetchRules()
      // 调用后端获取全量数据
      const res = await window.pywebview.api.get_initial_data()
      if (checkResult(res, '刷新数据')) {
        // 覆盖更新 Settings，以后端属性为主 (仅初始化时，避免覆盖用户未保存的修改)
        if (isInit && res.data.settings) {
          settings.value = res.data.settings
        }else{
          Object.assign(settings.value, res.data.settings)
        }
        // console.log('allmods', res.data.is_first_db_init , res.data.paths_configured , !res.data.all_mods||res.data.all_mods?.length==0)
        if (res.data.is_first_db_init && res.data.paths_configured && (!res.data.all_mods||res.data.all_mods?.length==0)) {
          toast.warning("数据库正在进行首次初始化，此过程可能需要您等待一段时间，请您耐心等候。",{position: "top-center",timeout: 10000})
        }
        // 更新 Groups (防止分组内的 Mod 被删了但分组里还有 ID)
        const groupStore = useGroupStore()
        groupStore.setGroups(res.data.groups || [])
        // 更新 Active列表 (防止外部修改 Active列表 导致的状态不一致)
        const modStore = useModStore()
        modStore.setMods(res.data)
        // 更新软件信息
        appVersion.value = res.data.app_version || 'Unknown'  // 版本
        buildMode.value = res.data.build_mode || ''           // 构建模式
        // 检查路径 (主要路径无效则打开设置)
        if (!res.data.paths_configured) {
          toast.warning("未配置游戏路径，请先配置游戏路径。",{position: "top-center",timeout: 5000})
          uiState.showSettingsPanel = true
        }
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
      if (checkResult(res, "保存单项设置")) {
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
        // 更新本地 store
        Object.assign(settings.value, newSettings)
        // 如果路径变了，可能需要重新扫描
        closeSettingsPanel()
        // 如果启用了自动扫描且路径有变化，触发扫描
        if (newSettings.game_install_path && settings.value.enable_auto_scan) {
          // const modStore = useModStore()
          // modStore.scanMods()
          await initialize()
        }else{
          await refreshData()
        }

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
  
  // === 系统操作 ===
  // 启动游戏
  const launchGame = async (profile_id=null) => {
    const orderStore = useOrderStore()
    const res = await orderStore.saveLoadOrder()
    if (!res) return
    if(settings.value.prefer_steam_launch && (!profile_id || profile_id === 'default') && settings.value.game_install_path?.includes("SteamLibrary\\steamapps\\common")){
      // 通过 steam 启动游戏
      window.open("steam://rungameid/294100", '_blank')
      toast.success("正在通过 steam 启动游戏……")
      console.log("通过 steam 启动游戏")
    }else if(profile_id || settings.value.game_install_path){
      if (!window.pywebview) return
      // 直接启动游戏
      const res = await window.pywebview.api.launch_game(profile_id)
      if (checkResult(res, "直接启动游戏程序")) {
        toast.success("直接启动游戏程序成功！")
      } else {
        console.error("直接启动游戏程序异常:", res.message)
        toast.error(`直接启动游戏程序异常: \n${res.message}`)
      }
    }
    else{
      console.error("启动游戏异常:")
      toast.error(`启动游戏出现异常！`)
    }
  }
  // 自动检测路径
  const autoDetectPaths = async (updateStore=true) => {
    if(!window.pywebview) return
    const res = await window.pywebview.api.auto_detect_paths(false)
    if (checkResult(res, "自动检测路径") && res.data.paths) {
       // 更新本地 setting store
      if(updateStore) {
        Object.assign(settings.value, res.data.paths)
        toast.success("路径已更新")
      }
      return res.data.paths
    }
  }
  // 获取游戏信息
  const getGameInfo = async (path) => {
    if(!path) return
    if(!window.pywebview) return
    const res = await window.pywebview.api.get_game_info(path)
    if (checkResult(res, "获取游戏信息")) {
      return res.data
    }
  }
  // 打开路径
  const openPath = async (path) => {
    if(!window.pywebview) return
    if(!path) return
    console.log("打开路径:", path)
    const res = await window.pywebview.api.open_path(path)
    checkResult(res, "打开路径")
  }
  // 获取文件路径
  const getFilePath = async (home_path, file_types=('XML Files (*.xml;*.rws)', 'All Files (*.*)')) => {
    if(!window.pywebview) return
    // 调用后端 API
    const res = await window.pywebview.api.select_file_dialog(home_path, file_types)
    if (checkResult(res, "获取文件路径")) {
      return res.data
    } else if (res.status === 'error') {
        console.error("获取文件路径异常:", res.message)
    }
  }
  // 获取文件夹路径
  const getFolderPath = async (home_path) => {
    if(!window.pywebview) return
    // 调用后端 API
    const res = await window.pywebview.api.select_folder_dialog(home_path)
    if (checkResult(res, "获取文件夹路径")) {
        return res.data
    } else if (res.status === 'error') {
        console.error("获取文件夹路径异常:", res.message)
    }
  }
  // 删除文件/文件夹
  const deletePath = async (path) => {
    if(!window.pywebview) return
    const confirmStore = useConfirmStore()
    const confirm = await confirmStore.confirmAction(
      '删除确认', `确定要删除 ${path} 吗？\n文件/文件夹将被移至回收站。`,
      { type: 'error' }
    );
    if(!confirm) return
    const res = await window.pywebview.api.delete_path(path)
    if (checkResult(res, "删除文件/文件夹")) {
      toast.success(`已删除: \n${path}`)
      // 刷新Mod列表
      const modStore = useModStore()
      modStore.scanMods()
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
    const res = await window.pywebview.api.delete_paths(paths)
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

  // === Steam客户端交互 ===
  // 检查Steam工具
  const checkSteamTools = async () => {
    if (!window.pywebview) return
    const res = await window.pywebview.api.check_steam_tools()
    if (checkResult(res, "检查Steam工具")) {
      
    }
  }
  // 打开Steam创意工坊
  const openSteamWorkshopUrl = (url) => {
    if(url) {
      const steamUrl = url.replace('https://steamcommunity.com/sharedfiles/filedetails/?id=', 'steam://url/CommunityFilePage/')
      window.open(steamUrl, '_blank')
    }
  }
  // 订阅模组
  const subscribeMod = async (mod_id) => {
    if (!window.pywebview) return
    const modStore = useModStore()
    const workshop_id = modStore.takeModById(mod_id).workshop_id
    if(!workshop_id) return
    const res = await window.pywebview.api.steam_subscribe(workshop_id)
    if (checkResult(res, `订阅模组 ${modStore.displayNameById(mod_id)}`)) {
    } else {
      console.error("订阅模组异常:", res.message)
    }
  }
  // 取消订阅模组
  const unsubscribeMod = async (mod_id, delete_file = false) => {
    if (!window.pywebview) return
    const modStore = useModStore()
    const workshop_id = modStore.takeModById(mod_id).workshop_id
    if(!workshop_id) return
    const res = await window.pywebview.api.steam_unsubscribe(workshop_id)
    if (checkResult(res, `取消订阅模组 ${modStore.displayNameById(mod_id)}`)) {
      if(delete_file) deletePath(modStore.takeModById(mod_id).path)
    } else {
      console.error("取消订阅模组异常:", res.message)
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
  // 获取AI模型 temp_config: {provider, base_url, api_key}
  const fetchAiModels = async (temp_config) => {
    if (!window.pywebview) return
    aiState.isLoading = true
    const res = await window.pywebview.api.ai_fetch_models(temp_config)
    if (checkResult(res, "获取AI模型")) {
      aiState.isLoading = false
      return res.data
    }
    aiState.isLoading = false
  }
  // 与AI聊天
  const chatWithAI = async (prompt, temp_config) => {
    if (!window.pywebview) return
    aiState.isLoading = true
    const res = await window.pywebview.api.ai_chat(prompt, temp_config)
    if (checkResult(res, "与AI聊天")) {
      aiState.isLoading = false
      return res.data
    }
    aiState.isLoading = false
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
    const res = await window.pywebview.api.ai_execute_task(task_key, params)
    if (checkResult(res, `使用AI ${task_key}`)) {
      aiState.isLoading = false
      return JSON.parse(res.data)
    }
    aiState.isLoading = false
  }

  // === 更新相关函数 ===
  // 检查更新方法
  const checkUpdate = async (manual = true) => {
    updateState.isChecking = true
    try {
      const res = await window.pywebview.api.check_update(manual)
      if (checkResult(res, "检查更新")) {
        const info = res.data
        if (info.has_update) {
          updateState.hasUpdate = true
          updateState.info = info
          
          // 弹出全局确认框
          const confirmStore = useConfirmStore()
          const ok = await confirmStore.confirmAction(
            `发现新版本 v${info.version}`,
            `来源: ${info.source_name}\n文件大小: ${info.file_size || '未知'}\n\n更新内容:\n${info.changelog}`,
            { confirmText: '立即更新', cancelText: manual ? '以后再说' : '忽略此版本', type: 'success' }
          )

          if (ok) {
            startUpdateProcess()
          } else if (!manual) {
            // 如果是启动时的自动弹窗点取消，则询问是否不再提醒该版本
            await window.pywebview.api.ignore_version(info.version)
          }
        } else if (manual) {
          toast.success("当前已是最新版本")
        }
      }
    } finally {
      updateState.isChecking = false
    }
  }

  // 执行更新下载与安装
  const startUpdateProcess = async () => {
    const url = updateState.info.download_url
    if (!url) return toast.error("无效的下载地址")

    toast.info("正在下载更新包，请稍后...")
    
    try {
      // 利用现有的文件管理器下载到 download 目录
      const res = await window.pywebview.api.download_file(url)
      if (checkResult(res, "下载更新包")) {
        const task_id = res.data.task_id
        // 等待下载完成，直接拿取 file_path
        // 代码会在这里“暂停”，直到全局监听器触发 resolve
        const filePath = await waitForDownload(task_id)
        // 下载完成后，自动执行安装
        toast.success("下载已就绪，正在准备安装...")
        await window.pywebview.api.install_update(filePath)
      }
    } catch (e) {
      toast.error(`更新失败: ${e.message}`)
      console.error('更新失败:', e)
    }
  }

  return {
    appVersion, buildMode, uiState, scanProgress, settings, isLoading, isDownloading, downloadTasks, activeDownloadTask, updateState, aiState,
    initialize, checkResult, refreshData, toggleUiState, scalePx, performDatabaseCleanup,
    // 游戏相关
    getGameInfo, launchGame, autoDetectPaths, openPath, getFilePath, getFolderPath, deletePath, deletePaths, openUrl, startDownload, waitForDownload, 
    saveSetting, applySettings, openSettingsPanel, closeSettingsPanel, resetDatabase,
    checkSteamTools, openSteamWorkshopUrl, unsubscribeMod, subscribeMod, checkUpdate, 
    getAiConfig, saveAIConfig, useAI, fetchAiModels, chatWithAI
  }
})