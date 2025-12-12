import { defineStore } from 'pinia'
import { ref,computed } from 'vue'

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
  const allModsMap = ref(new Map()) // 使用 Map 加速查找
  const activeIds = ref([])   // 绑定的 启用 列表
  const tempIds = ref([]) // 临时存放拖拽的 Mod 列表
  const groupList = ref([]) // 分组列表
  const selectedIds = ref(new Set())  // 多选状态

  // 系统状态
  const isLoading = ref(false)
  const assetPort = ref(0)
  const showSettings = ref(false)
  const isDirty = ref(false) // 是否有未保存的更改
  const librarySearchQuery = ref('')  // 搜索状态
  
  // 界面设置 (从 API 读取或默认)
  const settings = ref({
    game_install_path: '',
    workshop_mods_path: '',
    local_mods_path: '',
    game_config_path: '',
    game_version: '',
    window_width: 1400,
    window_height: 900,
    font_size: 14,
    primary_color: '#06b6d4' // Cyan
  })

  // ==================== 智能计算与 Helpers ====================

  // 获取缩略图 URL 的辅助函数
  const getAssetUrl = (id) => {
    if (!id || !assetPort.value) return ''
    // 假设后端 AssetServer 路由是 /thumbnails/<id>.webp
    return `http://localhost:${assetPort.value}/thumbnails/${id.toLowerCase()}.webp`
  }

  //根据 ID 获取对象 (处理缺失情况) ---
  const getModById = (id) => {
    const lowerId = id.toLowerCase()
    if (allModsMap.value.has(lowerId)) {
      return allModsMap.value.get(lowerId)
    }
    // 构造缺失模组的“幽灵对象”
    return {
      package_id: id,
      name: `⚠ ${id}`,
      author: 'Unknown',
      is_missing: true,
      description: 'Local file not found.'
    }
  }

  // 选中的模组对象列表
  const selectedMods = computed(() => {
    return Array.from(selectedIds.value).map(id => getModById(id))
  })

  // InactiveIds (库列表) ---
  // 这是一个“可写计算属性”。
  // 读取时：它是 (所有模组 - 启用模组 - 临时模组) + 搜索过滤
  // 写入时：如果拖拽把东西放回库里，意味着从 Active/Temp 中移除
  const inactiveIds = computed({
    get() {
      const activeSet = new Set(activeIds.value.map(id => id.toLowerCase()))
      const tempSet = new Set(tempIds.value.map(id => id.toLowerCase()))
      const query = librarySearchQuery.value.toLowerCase().trim()

      const result = []
      for (const mod of allModsMap.value.values()) {
        // 1. 排除已在 Active 或 Temp 中的
        if (activeSet.has(mod.package_id.toLowerCase())) continue
        if (tempSet.has(mod.package_id.toLowerCase())) continue

        // 2. 执行搜索过滤
        if (query) {
          if (!mod.name.toLowerCase().includes(query) && 
              !mod.package_id.toLowerCase().includes(query) &&
              !mod.author?.toLowerCase().includes(query)) {
            continue
          }
        }
        result.push(mod.package_id)
      }
      // 3. 默认按名称排序
      return result.sort((a, b) => getModById(a).name.localeCompare(getModById(b).name))
    },
    set(newIds) {
      // 库列表本质上是“剩余项”。
      // 当 VueDraggable 试图更新库列表时（例如从 Active 拖回 Library），
      // 我们不需要真正去“保存”库列表的顺序（因为它总是自动排序的），
      // 我们只需要确保这些 ID 不再出现在 ActiveIds 或 TempIds 中即可。
      
      // 实际上，VueDraggable 的 group 机制会自动从 Source 数组移除。
      // 当从 Active 拖到 Inactive 时，ActiveIds 会自动更新移除该项。
      // 所以这里甚至可以是空的，或者处理特殊的重新排序逻辑。
      // 为了逻辑严谨，我们什么都不做，因为 inactiveIds 是由 activeIds 自动反向推导的。
      // 库列表只读/自动推导，写入操作不需要做任何事
      // VueDraggable 移出操作会自动更新 activeIds
    }
  })


  // 初始化：获取数据并分类
  const initialize = async () => {
    isLoading.value = true
    
    try {
      // 1. 这里会“暂停”直到 Python 后端连接成功
      await waitForBackend() 
      const res = await window.pywebview.api.get_initial_data()
      console.log("初始化数据：", res)
      
      // 1. 设置
      if (res.settings) settings.value = { ...settings.value, ...res.settings }
      assetPort.value = res.asset_server_port
      applyStyles() // 应用自定义样式

      // 2. 构建 Map 索引 (ID -> ModData)
      const tempMap = new Map()
      res.all_mods.forEach(mod => {
        tempMap.set(mod.package_id.toLowerCase(), mod)
      })
      allModsMap.value = tempMap
      
      // 3. 处理 ID 列表，不再构建对象数组 ---
      if (res.active_load_order) {
        // 直接存 ID 字符串，并转小写确保匹配
        activeIds.value = res.active_load_order.map(id => id.toLowerCase())
      } else {
        activeIds.value = []
      }

      isDirty.value = false

      if (!res.paths_configured) {
        // 如果路径未配置，自动打开设置面板
        console.log("路径未配置，打开设置面板")
        showSettings.value = true
        autoDetectPaths() // 尝试自动检测路径
      }
      
    } catch (e) {
      console.error("初始化失败：", e)
    } finally {
      isLoading.value = false
    }
  }

  // 选择/取消选择 Mod
  const selectMod0 = (id, toggle = false) => {
    if (!id) return
    if (toggle) {
      if (selectedIds.value.has(id)) selectedIds.value.delete(id)
      else selectedIds.value.add(id)
    } else {
      selectedIds.value.clear()
      selectedIds.value.add(id)
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
  }

  // 保存当前顺序
  const saveLoadOrder = async () => {
    if (!window.pywebview) return
    isLoading.value = true
    // 提取 ID 列表
    const ids = activeIds.value 
    const res = await window.pywebview.api.save_load_order(ids)
    isLoading.value = false
    if (res.status === 'success') {
      isDirty.value = false
      // alert("加载顺序已成功保存！") // 暂用 Alert，建议改为 Toast
    } else {
      // alert("保存错误：" + res.message)
    }
    return res.status === 'success';
  }

  // 监听 activeMods 变化设置 dirty
  const markDirty = () => { isDirty.value = true }

  // 启动游戏
  const launchGame = async () => {
    const saved = await saveLoadOrder() // 先保存
    if (saved) {
        await window.pywebview.api.launch_game()
    } else {
        console.warn("未能启动游戏：加载顺序保存失败。")
    }
  }

  // 应用设置
  const saveSettings = async () => {
    if (!window.pywebview) return
    await window.pywebview.api.save_all_settings(JSON.parse(JSON.stringify(settings.value)))
    showSettings.value = false
    applyStyles() // 应用自定义样式
  }
  // 更新设置项
  const updateSetting = (key, value) => {
    settings.value[key] = value
    saveSettings()
  }
  
  const scanMods = async (path) => {
    if (isLoading.value || !window.pywebview) return
    isLoading.value = true
    // 收集当前设置的路径
    // 如果传入的是 Event 对象（点击事件），则视为无参数，使用默认路径
    console.log("扫描 Mod，路径参数：", path)
    let pathsToScan = []
    if (typeof path === 'string') {
        pathsToScan = [path]
        try {
          // 扫描后重新初始化，以刷新列表
          await window.pywebview.api.scan_mods(pathsToScan) // 发送清洗后的路径列表
          await initialize() 
        } catch (e) {
          console.error(e)
        } finally {
          isLoading.value = false
        }
        return
    }
    try {
      // 使用默认路径
      await window.pywebview.api.scan_current_paths()
      await initialize() 
    } catch (e) {
      console.error(e)
    } finally {
      isLoading.value = false
    }
  }
  
  // 自动检测路径
  const autoDetectPaths = async () => {
    if(!window.pywebview) return
    const res = await window.pywebview.api.auto_detect_paths()
    if(res.status === 'success' && res.paths) {
        updateSetting('game_install_path', res.paths.game_install_path)
        updateSetting('workshop_mods_path', res.paths.workshop_mods_path)
        updateSetting('local_mods_path', res.paths.local_mods_path)
        updateSetting('game_config_path', res.paths.game_config_path)
    }
  }
  // 主题配置 CSS 变量注入
  const applyStyles = () => {
    const root = document.documentElement
    root.style.setProperty('--color-accent-primary', settings.value.primary_color)
    // 简单的字号换算
    root.style.setProperty('--app-font-size', settings.value.font_size + 'px')
  }

  return {
    activeIds, inactiveIds, tempIds, selectedIds, groupList, selectedMods,  
    isLoading, showSettings, isDirty, librarySearchQuery, settings, allModsMap,
    getModById, getAssetUrl, scanMods, saveLoadOrder,
    initialize, saveSettings, launchGame, markDirty, autoDetectPaths,
    selectMod, clearSelection,
  }
})
