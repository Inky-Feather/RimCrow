import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { createToastInterface } from 'vue-toastification'


// 等待 pywebview 就绪
const waitForBackend = () => {
  return new Promise((resolve) => {
    // 情况 1: 如果 API 已经存在（前端加载慢，后端已经注入了），直接继续
    if (window.pywebview) {
      resolve()
    } else {
      // 情况 2: API 还没来（前端加载快），监听 pywebviewready 事件
      // { once: true } 确保只触发一次
      window.addEventListener('pywebviewready', () => resolve(), { once: true })
    }
  })
}

// Mod 管理 Store
export const useModStore = defineStore('mods', () => {
  const toast = createToastInterface()
  // 数据状态
  const allModsMap = ref(new Map()) // 使用 Map 加速查找
  const dataVersion = ref(0) // 数据版本号

  const activeIds = ref([]) // 绑定的启用列表
  const tempIds = ref([])   // 临时列表
  const groupList = ref([]) // 分组列表
  
  // 选择状态
  const currentTargetId = ref('') // 当前目标 ID (定位用)
  const selectedIds = ref(new Set())
  const lastSelectedId = ref(null)      // 最后点击的 ID (用于 Shift 连选定位)
  const lastSelectedListId = ref(null)  // 最后点击所在的列表标识 (防止跨列表连选)

  // 设置状态
  const showSettings = ref(false) // 是否显示设置弹窗
  const isLoading = ref(false)
  const isDirty = ref(false)
  const settings = ref({
    game_install_path: '',
    workshop_mods_path: '',
    local_mods_path: '',
    game_config_path: '',
    game_version: '',
    window_width: 1400,
    window_height: 900,
    font_size: 14,
  })
  // 扫描进度状态
  const scanProgress = ref({
    scanning: false, // 是否正在扫描中
    percent: 0,      // 进度百分比 (0-100)
    message: '',     // 当前正在扫描的文件名或阶段
    total: 0,        // 总文件数
    current: 0       // 当前处理数
  })

  // ==== 智能计算 ====
  // 获取非活跃 Mod ID 列表 (全集 - 活跃 - 临时)
  // 注意：这里不负责筛选和排序，只提供原始数据
  const inactiveIds = computed(() => {
    const activeSet = new Set(activeIds.value.map(id => id.toLowerCase()))
    const tempSet = new Set(tempIds.value.map(id => id.toLowerCase()))
    
    const result = []
    for (const mod of allModsMap.value.values()) {
      const pid = mod.package_id.toLowerCase()
      if (!activeSet.has(pid) && !tempSet.has(pid)) {
        result.push(mod.package_id)
      }
    }
    // 默认按名称排序，保证基础列表不乱
    return result.sort((a, b) => {
      const mA = allModsMap.value.get(a.toLowerCase())
      const mB = allModsMap.value.get(b.toLowerCase())
      return (mA?.name || a).localeCompare(mB?.name || b)
    })
  })
  // 选中的模组对象列表
  const selectedMods = computed(() => {
    return Array.from(selectedIds.value).map(id => getModById(id))
  })


  // 初始化：获取数据并分类
  const initialize = async () => {
    isLoading.value = true
    try {
      // “暂停”直到 Python 后端连接成功
      await waitForBackend()
      // 1. 注册事件监听
      setupEventListeners()
      // 2. 获取初始数据
      await refreshModList(true) // 复用 refreshModList 逻辑
      // 3. 【第三步】界面渲染完毕后，根据设置决定是否启动后台扫描
      // 检查 settings.enable_auto_scan (假设你在 settings.py 里加了这个字段)
      if (settings.value.enable_auto_scan !== false) {
          console.log("启动自动扫描...")
          toast.info("自动扫描已启动...")
          scanMods() // 这里调用是异步的，不会阻塞界面
      }
    } catch (e) {
      console.error("初始化失败:", e)
      toast.error("初始化失败，请检查日志")
    } finally {
      isLoading.value = false
    }
  }
  // 事件监听
  const setupEventListeners = () => {
    // 防止重复添加监听器（简单判断，生产环境可以用更严谨的方式）
    if (window._modManagerEventsInitialized) return
    window._modManagerEventsInitialized = true
    // 监听：扫描开始
    window.addEventListener('scan-start', () => {
      scanProgress.value.scanning = true
      scanProgress.value.percent = 0
      scanProgress.value.message = '准备开始扫描...'
    })
    // 监听：扫描进度
    window.addEventListener('scan-progress', (e) => {
      // Python 发送的数据在 e.detail 中
      const d = e.detail
      scanProgress.value.percent = d.percent || 0
      scanProgress.value.message = d.message || ''
      if (d.total) {
        scanProgress.value.total = d.total
        scanProgress.value.current = d.current
      }
    })
    // 监听：扫描完成
    window.addEventListener('scan-complete', async (e) => {
      scanProgress.value.scanning = false
      scanProgress.value.message = '扫描完成'
      console.log("扫描统计:", e.detail)
      toast.success(`扫描完成，共计扫描${e.detail.total}个模组，新增${e.detail.stats.added}个，
更新${e.detail.stats.updated}个，已知${e.detail.stats.skipped}个。`)
      // [关键] 扫描结束后，主动拉取一次最新数据刷新界面
      await refreshModList()
    })
  }
  // 获取加载顺序
  const openLoadOrder = async (mods_config_file_path=null) => {
    if (!window.pywebview) return
    const res = await window.pywebview.api.open_load_order_file(mods_config_file_path)
    if (res.status === 'success' && res.load_order) {
      activeIds.value = res.load_order
      // 如果有指定路径，标记为脏状态，等待保存
      if (mods_config_file_path) isDirty.value = true
      else isDirty.value = false
      console.log("打开加载顺序:", res)
      toast.success("Mod序列已加载")
    }
  }

  // ===== Mod操作 =====
  // 获取 Mod 对象
  const getModById = (id) => {
    if (!id) return null
    const lowerId = id.toLowerCase()
    if (allModsMap.value.has(lowerId)) {
      return allModsMap.value.get(lowerId)
    }
    // 构造缺失模组的“幽灵对象”
    return {
      package_id: id,
      name: `⚠ 未知模组 (${id})`,
      author: ['Unknown'],
      is_missing: true,
      description: '该模组在本地未找到，可能未下载，或已被手动删除。'
    }
  }
  // 获取 Mod 对象列表 (根据 ID 列表筛选)
  const getModListByIds = (ids) => {
    return Array.from(allModsMap.value.values()).filter(mod => ids.includes(mod.package_id))
  }
  // 获取图片 URL (基于后端 FileManager)
  const getIconUrl = (id) => {
    const mod = getModById(id)
    if (mod && mod.icon_url) return mod.icon_url // 列表图标
    if (mod && mod.thumb_url) return mod.thumb_url // 缩略图
    if (mod && mod.preview_url) return mod.preview_url // 详情大图
    return '' // 返回空或默认图路径
  }
   // 单独抽离刷新列表的方法，用于初始化、扫描完成后、或手动刷新
  const refreshModList = async (isInit = false) => {
    try {
      // 调用后端获取全量数据
      const res = await window.pywebview.api.get_initial_data()
      
      if (res.status === 'success') {
        // 1. 更新设置 (仅初始化时，避免覆盖用户未保存的修改)
        if (isInit && res.settings) {
          settings.value = res.settings
        }
        // 2. 更新 Mod Map
        // 直接重建 Map，确保删除的 Mod 能被移除，新增的能被加入
        const tempMap = new Map()
        res.all_mods.forEach(mod => {
          // 预先生成搜索索引字符串
          mod._searchStr = [
            mod.name,
            mod.alias_name,
            mod.package_id,
            ...(mod.tags || []),
            mod.author
          ].filter(Boolean).join(' ').toLowerCase(); // 拼接成一个长字符串
          
          // 预先将 Tags 转为小写 Set，加速精确匹配
          mod._tagsLower = new Set((mod.tags || []).map(t => t.toLowerCase()));
          
          tempMap.set(mod.package_id.toLowerCase(), mod)
        })
        allModsMap.value = tempMap
        // 3. 更新分组 (防止分组内的 Mod 被删了但分组里还有 ID)
        groupList.value = res.groups || []
        // 4. 更新激活列表 (通常扫描不会变动 active list，但为了同步“缺失”状态，更新一下也好)
        activeIds.value = (res.active_load_order || []).map(id => id.toLowerCase())
        // 5. 检查路径 (仅初始化时)
        if (isInit && !res.paths_configured) {
          showSettings.value = true
        }
      }
      // 6. 更新数据版本号
      dataVersion.value ++;

      console.log("刷新列表成功:", res)
    } catch (e) {
      console.error("刷新列表失败:", e)
    }
  }
  // 选择/取消选择 Mod
  const selectMod = (id, isMulti = false, isRange = false) => {
    const lowerId = id.toLowerCase();
    if (isRange) {
      // Shift 连选逻辑
      if (selectedIds.value.size === 0) {
        selectedIds.value.add(lowerId);
        return;
      }

      // 找到当前列表的所有可见ID
      const currentListIds = [...activeIds.value, ...inactiveIds.value, ...tempIds.value]; // 假设这三者是所有可能的列表
      
      // 找到最近一次选择的ID
      let lastSelectedId = null;
      // 遍历Set，找到第一个（或最后一个，取决于实现）
      if (selectedIds.value.size > 0) {
        lastSelectedId = Array.from(selectedIds.value)[selectedIds.value.size - 1]; 
      }
      
      if (!lastSelectedId) {
        selectedIds.value.add(lowerId);
        return;
      }

      const lastIndex = currentListIds.indexOf(lastSelectedId);
      const currentIndex = currentListIds.indexOf(lowerId);

      if (lastIndex !== -1 && currentIndex !== -1) {
        const start = Math.min(lastIndex, currentIndex);
        const end = Math.max(lastIndex, currentIndex);
        for (let i = start; i <= end; i++) {
          selectedIds.value.add(currentListIds[i]);
        }
      } else {
        selectedIds.value.add(lowerId); // 如果找不到范围，就只选中当前项
      }

    } else if (isMulti) {
      // Ctrl/Meta 多选逻辑
      if (selectedIds.value.has(lowerId)) {
        selectedIds.value.delete(lowerId);
      } else {
        // 检查是否所有已选项都在同一列表中
        selectedIds.value.add(lowerId);
        if (Array.from(selectedIds.value).every(id => activeIds.value.includes(id)) || 
          Array.from(selectedIds.value).every(id => inactiveIds.value.includes(id)) ||
          Array.from(selectedIds.value).every(id => tempIds.value.includes(id))) {
          // 全部在同一列表中，允许多选
        } else {
          selectedIds.value.clear();
          selectedIds.value.add(lowerId);
        }
      }
    } else {
      // 单选逻辑
      selectedIds.value.clear();
      selectedIds.value.add(lowerId);
    }
  }
  // 清除选择
  const clearSelection = () => {
    selectedIds.value.clear()
    lastSelectedId.value = null
    lastSelectedListId.value = null
  }

  // ===== Mod管理 =====
  // 扫描 Mod
  const scanMods = async (path) => {
    if (scanProgress.value.scanning || !window.pywebview) return
    try {
      const paths = path ? [path] : null
      
      // 调用 API，它现在会立即返回 { status: 'started' }
      const res = await window.pywebview.api.scan_mods(paths)
      
      if (res.status !== 'success' && res.status !== 'started') {
        console.error("启动扫描失败:", res.message)
        toast.error("扫描启动失败，请检查日志")
        return
      }
    } catch (e) {
      console.error("扫描请求异常:", e)
      toast.error("扫描请求异常，请检查日志")
    }
  }
  // 保存Mod加载顺序
  const saveLoadOrder = async () => {
    if (!window.pywebview) return false
    isLoading.value = true
    try {
      // 使用默认路径
      const res = await window.pywebview.api.save_load_order(activeIds.value)
      if (res.status === 'success') {
        isDirty.value = false
        // console.log("保存加载顺序成功:", res)
        toast.success("Mod序列已保存")
        return true
      } else {
        console.error("保存Mod序列失败:", res.message)
        toast.error("保存Mod序列失败，请检查日志")
      }
    } finally {
      isLoading.value = false
    }
    return false
  }
  // 更新Mod用户数据
  const updateModUserData = async (modId, userData) => {
    if (!window.pywebview) return
    isLoading.value = true
    try {
      const res = await window.pywebview.api.update_mod_user_data(modId, userData)
      if (res.status === 'success') {
        // 更新本地 Map
        const mod = allModsMap.value.get(modId.toLowerCase())
        if (mod) {
          Object.assign(mod, userData)
        }
        toast.success("Mod用户数据已更新")
        return true
      } else {
        console.error("更新Mod用户数据失败:", res.message)
        toast.error("更新Mod用户数据失败，请检查日志")
      }
    } catch (e) {
      console.error(e)
      toast.error("更新Mod用户数据失败，请检查日志")
    } finally {
      isLoading.value = false
    }
    return false
  }

  // === 分组操作 ====
  // 获取分组
  const getGroups = async () => {
    if (!window.pywebview) return
    isLoading.value = true
    try {
      const res = await window.pywebview.api.get_groups()
      if (res.status === 'success') {
        groupList.value = res.groups || []
      }
    } catch (e) {
      console.error(e)
    } finally {
      isLoading.value = false
    }
  }
  // 创建分组（默认名称为“新分组”，随机颜色）
  const createGroup = async (name='新分组', color=`#${Math.floor(Math.random() * 16777216).toString(16).padStart(6, '0')}`) => {
    if (!window.pywebview) return
    isLoading.value = true
    try {
      const res = await window.pywebview.api.create_group(name, color)
      console.log("创建分组:", res)
      if (res.status === 'success') {
        groupList.value.push(res.group)
        // 排序
        groupList.value.sort((a, b) => a.sort_index - b.sort_index)
      }
    } catch (e) {
      console.error(e)
    } finally {
      isLoading.value = false
    }
  }
  // 删除分组
  const deleteGroup = async (groupId) => {
    if (!window.pywebview) return
    isLoading.value = true
    try {
      const res = await window.pywebview.api.delete_group(groupId)
      console.log("删除分组:", res)
      if (res.status === 'success') {
        // 从列表中移除
        groupList.value = groupList.value.filter(group => group.id !== groupId)
        // 排序
        groupList.value.sort((a, b) => a.sort_index - b.sort_index)
      }
    } catch (e) {
      console.error(e)
    } finally {
      isLoading.value = false
    }
  }
  // 更新分组
  const updateGroup = async (groupId, updates) => {
    if (!window.pywebview) return
    isLoading.value = true
    try {
      const res = await window.pywebview.api.update_group(groupId, updates)
      console.log("更新分组:", res)
      if (res.status === 'success') {
        // 更新本地列表
        const group = groupList.value.find(g => g.id === groupId)
        if (group) {
          Object.assign(group, updates)
        }
        // 排序
        groupList.value.sort((a, b) => a.sort_index - b.sort_index)
      }
    } catch (e) {
      console.error(e)
    } finally {
      isLoading.value = false
    }
  }
  // 分组添加模组
  const groupAddMods = async (groupId, modIds) => {
    if (!window.pywebview) return
    isLoading.value = true
    try {
      const res = await window.pywebview.api.group_add_mods(groupId, modIds)
      console.log("分组添加模组:", res)
      if (res.status === 'success') {
        // 更新本地分组
        const group = groupList.value.find(g => g.id === groupId)
        if (group) {
          group.mod_ids.push(...modIds)
        }
      }
    } catch (e) {
      console.error(e)
    } finally {
      isLoading.value = false
    }
  }
  // 分组移除模组
  const groupRemoveMods = async (groupId, modIds) => {
    if (!window.pywebview) return
    isLoading.value = true
    try {
      const res = await window.pywebview.api.group_remove_mods(groupId, modIds)
      console.log("分组移除模组:", res)
      if (res.status === 'success') {
        // 更新本地分组
        const group = groupList.value.find(g => g.id === groupId)
        if (group) {
          group.mod_ids = group.mod_ids.filter(id => !modIds.includes(id))
        }
      }
    } catch (e) {
      console.error(e)
    } finally {
      isLoading.value = false
    }
  }
  // 分组排序
  const groupReorder = async (groupIds=groupList.value.map(g => g.group_id)) => {
    if (!window.pywebview) return
    isLoading.value = true
    try {
      const res = await window.pywebview.api.group_reorder(groupIds)
      console.log("分组排序:", res)
      if (res.status === 'success') {
        getGroups()
      }
    } catch (e) {
      console.error(e)
    } finally {
      isLoading.value = false
    }
  }
  // 分组内排序
  const groupContentReorder = async (groupId, modIds) => {
    if (!window.pywebview) return
    isLoading.value = true
    try {
      const res = await window.pywebview.api.group_content_reorder(groupId, modIds)
      console.log("分组内排序:", res)
      if (res.status === 'success') {
        // 更新本地分组
        const group = groupList.value.find(g => g.id === groupId)
        if (group) {
          group.mod_ids = modIds
        }
      }
    } catch (e) {
      console.error(e)
    } finally {
      isLoading.value = false
    }
  }

  // ===== 设置相关 =====
  // 打开/关闭设置的方法
  const openSettings = () => { showSettings.value = true }
  const closeSettings = () => { showSettings.value = false }
  // 应用设置（保存到后端并更新本地）
  const applySettings = async (newSettings) => {
    if (!window.pywebview) return
    isLoading.value = true
    try {
        const res = await window.pywebview.api.save_all_settings(newSettings)
        if (res.status === 'success') {
            // 更新本地 store
            Object.assign(settings.value, newSettings)
            // 如果路径变了，可能需要重新扫描，这里简单起见先关闭弹窗
            closeSettings()
            // 可以在这里触发一次重新初始化或扫描
            await initialize() 
        }
    } finally {
        isLoading.value = false
    }
  }
  // 保存单项设置
  const saveSetting = async (key, value) => {
    if (!window.pywebview) return
    isLoading.value = true
    try {
      const res = await window.pywebview.api.save_setting(key, value)
      if (res.status === 'success') {
        // 更新本地 store
        settings.value[key] = value
      }
    } catch (e) {
      console.error(e)
    } finally {
      isLoading.value = false
    }
  }
  // 辅助：标记脏状态
  const markDirty = () => { isDirty.value = true }

  // ===== 系统操作 =====
  // 启动游戏
  const launchGame = async () => {
    const saved = await saveLoadOrder()
    if (saved) {
      await window.pywebview.api.launch_game()
    }
  }
  // 打开路径
  const openPath = async (path) => {
    if(!window.pywebview) return
    await window.pywebview.api.open_path(path)
  }
  // 辅助：自动检测路径
  const autoDetectPaths = async () => {
    if(!window.pywebview) return
    const res = await window.pywebview.api.auto_detect_paths()
    if(res.status === 'success' && res.paths) {
       // 更新本地 setting store
       Object.assign(settings.value, res.paths)
       toast.success("路径已更新")
    }
  }

  return {
    // 状态管理
    scanProgress, dataVersion,
    initialize, openLoadOrder,
    // Mod 相关
    allModsMap, activeIds, tempIds, inactiveIds, selectedIds, selectedMods, lastSelectedId, lastSelectedListId, currentTargetId, 
    getModById, getIconUrl, selectMod, clearSelection, refreshModList, scanMods, saveLoadOrder, updateModUserData, getModListByIds,

    // 分组相关
    groupList, 
    getGroups, createGroup, deleteGroup, updateGroup, groupAddMods, groupRemoveMods, groupReorder, groupContentReorder,

    // 设置相关
    showSettings, isLoading, isDirty, settings, 
    openSettings, closeSettings, applySettings, saveSetting, markDirty,

    // 系统操作
    launchGame, openPath, autoDetectPaths,
  }
})