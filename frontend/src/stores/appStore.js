import { defineStore } from 'pinia'
import { ref, reactive, computed } from 'vue'
import { createToastInterface } from 'vue-toastification'
import { useModStore } from './modStore'
import { useGroupStore } from './groupStore'
import { useOrderStore } from './orderStore'
import { useRuleStore } from './ruleStore'

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
  })
  // 扫描进度
  const scanProgress = reactive({
    scanning: false, // 是否正在扫描中
    percent: 0,      // 进度百分比 (0-100)
    message: '',     // 当前正在扫描的文件名或阶段
    total: 0,        // 总文件数
    current: 0       // 当前处理数
  })
  // 下载任务
  const downloadTasks = ref(new Map()) // 使用 Map 存储 {id: taskObject}
  // 全局设置
  const settings = ref({
    game_install_path: '',
    workshop_mods_path: '',
    local_mods_path: '',
    game_config_path: '',
    home_path: '',
    game_version: '',
    enable_auto_scan: true,
    window_width: 1400,
    window_height: 900,
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
      
      // 级联初始化其他 Store
      const modStore = useModStore()
      const orderStore = useOrderStore()
      
      // 获取初始数据 (这里包含 settings, version 等)
      await refreshData(true) 
      // 界面渲染完毕后，根据设置决定是否启动后台扫描
      if (settings.value.enable_auto_scan !== false) {
        console.log("启动自动扫描...")
        toast.info("自动扫描已启动...")
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
      if (checkResult(res, '刷新数据', true)) {
        // 覆盖更新 Settings，以后端属性为主 (仅初始化时，避免覆盖用户未保存的修改)
        if (isInit && res.data.settings) {
          settings.value = res.data.settings
        }
        if (res.data.is_first_db_init) {
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
        if (!res.data.paths_configured) uiState.showSettingsPanel = true
        console.log("刷新数据成功:", res)
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
      // 更新或插入 Map
      downloadTasks.value.set(d.id, d)
      // 如果完成了，可以弹个 Toast (可选，防止太吵)
      if (d.status === 'completed' && d.percent === 100) {
        // 可以在这里移除任务，或者保留一会
        // setTimeout(() => downloadTasks.value.delete(d.id), 5000)
        toast.success(`下载完成: ${d.filename}`)
      }
      if (d.status === 'error') {
        toast.error(`下载失败: ${d.filename}\n${d.error}`)
      }
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
        // 如果路径变了，可能需要重新扫描，这里简单起见先关闭弹窗
        closeSettingsPanel()
        // 可以在这里触发一次重新初始化或扫描
        await initialize() 
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
  // 变更 UI 状态
  const toggleUiState = (key) => {
    uiState[key] = !uiState[key]
  }
  
  // === 系统操作 ===
  // 启动游戏
  const launchGame = async () => {
    const orderStore = useOrderStore()
    const res = await orderStore.saveLoadOrder()
    if (!res) return
    if(settings.value.game_install_path?.includes("SteamLibrary\\steamapps\\common")){
      // 通过 steam 启动游戏
      window.open("steam://rungameid/294100", '_blank')
      toast.success("正在通过 steam 启动游戏……")
      console.log("通过 steam 启动游戏")
    }else if(settings.value.game_install_path){
      if (!window.pywebview) return
      // 直接启动游戏
      const res = await window.pywebview.api.launch_game()
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
    }
  }
  // 获取文件夹路径
  const getFolderPath = async (home_path) => {
    if(!window.pywebview) return
    // 调用后端 API
    const res = await window.pywebview.api.select_folder_dialog(home_path)
    if (checkResult(res, "获取文件夹路径")) {
        return res.data
    } else{
        console.error("获取文件夹路径异常:", res.message)
        toast.error(`获取文件夹路径异常: \n${res.message}`)
        return
    }
  }
  // 删除文件/文件夹
  const deletePath = async (path) => {
    if(!window.pywebview) return
    const res = await window.pywebview.api.delete_path(path)
    if (checkResult(res, "删除文件/文件夹")) {
      toast.success(`文件/文件夹已删除: \n${path}`)
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
      console.error(e)
    }
  }

  // === Steam客户端交互 ===
  // 检查Steam工具
  const checkSteamTools = async () => {
    if (!window.pywebview) return
    const res = await window.pywebview.api.check_steam_tools()
    if (checkResult(res, "检查Steam工具")) {
      toast.success(`检查Steam工具成功！`)
    } else {
      console.error("检查Steam工具异常:", res.message)
      toast.error(`检查Steam工具异常: \n${res.message}`)
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
    if (checkResult(res, "订阅模组")) {
      toast.success(`订阅模组 ${mod_id} 成功！`)
    } else {
      console.error("订阅模组异常:", res.message)
      toast.error(`订阅模组 ${mod_id} 异常: \n${res.message}`)
    }
  }
  // 取消订阅模组
  const unsubscribeMod = async (mod_id) => {
    if (!window.pywebview) return
    const modStore = useModStore()
    const workshop_id = modStore.takeModById(mod_id).workshop_id
    if(!workshop_id) return
    const res = await window.pywebview.api.steam_unsubscribe(workshop_id)
    if (checkResult(res, "取消订阅模组")) {
      toast.success(`取消订阅模组 ${mod_id} 成功！`)
    } else {
      console.error("取消订阅模组异常:", res.message)
      toast.error(`取消订阅模组 ${mod_id} 异常: \n${res.message}`)
    }
  }

  return {
    appVersion, buildMode, uiState, scanProgress, settings, isLoading, isDownloading, downloadTasks, activeDownloadTask, 
    initialize, checkResult, refreshData, toggleUiState,
    launchGame, autoDetectPaths, openPath, getFilePath, getFolderPath, deletePath, openUrl, startDownload, 
    saveSetting, applySettings, openSettingsPanel, closeSettingsPanel, resetDatabase, 
    checkSteamTools, openSteamWorkshopUrl, unsubscribeMod, subscribeMod
  }
})