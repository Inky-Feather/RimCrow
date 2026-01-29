import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { createToastInterface } from 'vue-toastification'
import { useRuleStore } from '../stores/ruleStore'


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

// 错误严重等级
export const ISSUE_LEVEL = {
  ERROR: 'error',   // 红色：必须修复 (依赖缺失、版本不符)
  WARN: 'warn',     // 黄色：建议修复 (排序错误)
  INFO: 'info'      // 蓝色：提示
}

// 错误类型枚举
export const ISSUE_TYPE = {
  ERROR_MISSING_FILE: 'missing_file',      // 本地文件丢失
  ERROR_MISSING_DEPENDENCY: 'missing_dependency', // 缺前置 (完全没装)
  ERROR_INACTIVE_DEPENDENCY: 'inactive_dependency', // 前置没启用
  ERROR_INCOMPATIBLE: 'incompatible',     // 不兼容
  WARN_WRONG_ORDER: 'wrong_order',       // 顺序错了
  WARN_VERSION_MISMATCH: 'version_mismatch', // 版本不对
  WARN_LINK_MOD_MISSING: 'link_mod_missing', // 联锁模组缺失
  WARN_LINK_WRONG_ORDER: 'link_wrong_order', // 联锁排序错误
}
// 定义类型到中文标题的映射
const ISSUE_TITLE_MAP = {
  'missing_file': '文件丢失',
  'missing_dependency': '依赖缺失',
  'inactive_dependency': '依赖未启用',
  'incompatible': '模组冲突',
  'wrong_order': '排序错误',
  'version_mismatch': '版本不符',
  'link_mod_missing': '联锁模组缺失',
  'link_wrong_order': '联锁排序错误',
  'default': '其他问题'
}

// 模组类型映射
const MOD_TYPE_MAP = {
  'LanguagePack': '语言包',
  'XML': '纯XML',
  'Assembly': '含程序集',
  'Texture': '纹理包',
  'Audio': '音频包',
  'Mixed': '混合',
  'Unknown': '未知类型'
}

const modColorList = [
  '#ef4444',
  '#ec4899',
  '#8b5cf6',
  '#3b82f6',
  '#06b6d4',
  '#10b981',
  '#84cc16',
  '#eab308',
  '#f97316'
]

// 来源类型显示
const sourceTypeMap = {
  'core': '游戏本体',
  'dlc': 'DLC',
  'github': 'GitHub',
  'workshop': 'Steam 创意工坊',
  'local': '本地文件',
  'other': '其它来源'
}


// Mod 管理 Store
export const useModStore = defineStore('mods', () => {
  const toast = createToastInterface()
  // 数据状态
  const allModsMap = ref(new Map()) // 使用 Map 加速查找
  const dataVersion = ref(0) // 数据版本号
  const appVersion = ref('') // 应用版本号
  const build = ref('') // 构建类型

  const activeIds = ref([]) // 绑定的启用列表
  const savedActiveIds = ref([]) // 原始启用列表快照
  const activeLoadModifyTime = ref(0) // 启动加载顺序修改时间
  const inactiveIds = ref([]) // 绑定的禁用列表
  const tempIds = ref([])   // 临时列表
  const groupList = ref([]) // 分组列表

  const backups = ref(null) // 备份列表
  const backupIds = ref([]) // 备份文件列表
  const currentBackupFile = ref('') // 当前备份文件
  const backupLoadModifyTime = ref(0) // 备份加载顺序修改时间

  const conflictList = ref([]) // 重复包名冲突列表

  // 选择状态
  const currentTargetId = ref('') // 当前目标 ID (定位用)
  const selectedIds = ref([])     // 选中的 Mod ID 列表
  const lastSelectedMod = ref(null) // 最后选中的 Mod 对象
  const isDraggingGroup = ref(false) // 是否正在拖动分组

  const downloadTasks = ref(new Map()) // 使用 Map 存储 {id: taskObject}
  const ruleStore = useRuleStore()

  // 设置状态
  const showSettings = ref(false) // 是否显示设置弹窗
  const showDiffDrawer = ref(false)
  const showLogDrawer = ref(false)// 日志抽屉状态
  const showTestDrawer = ref(false)// 测试抽屉状态
  const showRuleDrawer = ref(false)// 规则抽屉状态
  const isLoading = ref(false)
  const settings = ref({
    game_install_path: '',
    workshop_mods_path: '',
    local_mods_path: '',
    game_config_path: '',
    home_path: '',
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
  const takeInactiveIds = () => {
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
  }
  // 当前列表是否与快照不一致
  const isDirty = computed(() => {
    // 简单数组比较：长度不同，或内容/顺序不同
    if (activeIds.value.length !== savedActiveIds.value.length) return true
    // 逐个比较 (比 JSON.stringify 快)
    for (let i = 0; i < activeIds.value.length; i++) {
      if (activeIds.value[i] !== savedActiveIds.value[i]) return true
    }
    return false
  })
  // 选中的模组对象列表
  const selectedMods = computed(() => {
    return Array.from(selectedIds.value).map(id => takeModById(id))
  })
  const allModTags = computed(() => {
    return [...new Set(Array.from(allModsMap.value.values()).flatMap(mod => mod.tags || []))]
  })
  // 计算选中项的共有属性
  // 返回结构：{
  //   tags: { 'Core': 'all', 'Lib': 'some' }, // all=全有, some=部分有
  //   groups: { 'g1': 'all', 'g2': 'some' },
  //   color: '#ff0000' (如果全都一样), 'mixed' (如果不一样), null (全无)
  // }
  const selectedStats = computed(() => {
    const ids = selectedIds.value
    if (ids.length === 0) return { tags: {}, groups: {}, color: null }

    const firstMod = takeModById(ids[0])
    if (!firstMod) return {}

    // 1. 初始化统计 (以第一个为基准，或者全量统计)
    // 为了性能，我们统计“拥有该属性的Mod数量”
    const tagCounts = {} // { 'Core': 10, 'Lib': 5 }
    const groupCounts = {}
    const colors = new Set()

    ids.forEach(id => {
      const mod = takeModById(id)
      if (!mod) return

      // 统计 Tags
      mod.tags?.forEach(t => tagCounts[t] = (tagCounts[t] || 0) + 1)
      
      // 统计 Groups (需配合 groupList)
      // 效率优化：不要在这里遍历 groupList，太慢。
      // 应该用 store.groupList 反查，或者 mod 对象里存了 groups。
      // 假设 mod 没有直接存 groups，需要用 store.takeGroupsByModId
      const modGroups = takeGroupsByModId(id)
      modGroups.forEach(g => groupCounts[g.group_id] = (groupCounts[g.group_id] || 0) + 1)

      // 统计 Color
      colors.add(mod.sign_color)
    })

    // 2. 生成状态
    const total = ids.length
    
    // Tags 状态
    const tagState = {}
    for (const [tag, count] of Object.entries(tagCounts)) {
      tagState[tag] = (count === total) ? 'all' : 'some'
    }

    // Group 状态
    const groupState = {}
    for (const [gid, count] of Object.entries(groupCounts)) {
      groupState[gid] = (count === total) ? 'all' : 'some'
    }

    // Color 状态
    let colorState = null
    if (colors.size === 1) colorState = [...colors][0]
    else if (colors.size > 1) colorState = 'mixed'

    return { tags: tagState, groups: groupState, color: colorState }
  })

  // 计算属性：当前是否有正在进行的下载
  const isDownloading = computed(() => {
    for (const task of downloadTasks.value.values()) {
      if (task.status === 'running' || task.status === 'pending') return true
    }
    return false
  })

  // 计算属性：获取最活跃的一个任务用于状态栏显示
  const activeDownloadTask = computed(() => {
    // 优先返回 Running 的，没有则返回 Pending，再没有返回 Error/Completed
    const tasks = Array.from(downloadTasks.value.values())
    return tasks.find(t => t.status === 'running') || 
           tasks.find(t => t.status === 'pending') || 
           null
  })


  // ==== 核心方法 ====
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
      getBackups()
    }
  }
  // 注册事件监听
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
      // 冲突处理
      if (e.detail.conflicts && e.detail.conflicts.length > 0) {
        console.warn("发现冲突:", e.detail.conflicts)
        conflictList.value = e.detail.conflicts
        // 注意：有冲突时暂不提示 "扫描完成" 的 Toast，以免遮挡，或者提示 Warning
        toast.warning(`扫描完成，发现 ${e.detail.conflicts.length} 个包名重复冲突需要处理！`, {timeout: 10000})
      } else {
        toast.success(`扫描完成，共计扫描${e.detail.total}个模组，新增${e.detail.stats.added}个，\n更新${e.detail.stats.updated}个，删除${e.detail.stats.removed}个，已知${e.detail.stats.skipped}个。`,{position: "top-center",timeout: 5000})
      }

      console.log("扫描统计:", e.detail)
      // [关键] 扫描结束后，主动拉取一次最新数据刷新界面
      await refreshModList()
    })
    // 监听下载进度
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
   // 单独抽离刷新列表的方法，用于初始化、扫描完成后、或手动刷新
  const refreshModList = async (isInit = false) => {
    try {
      isLoading.value = true
      // 调用后端获取全量数据
      const res = await window.pywebview.api.get_initial_data()
      ruleStore.fetchRules()  // 刷新动态规则
      if (res.status === 'success') {
        // 1. 更新设置 (仅初始化时，避免覆盖用户未保存的修改)
        if (isInit && res.data.settings) {
          settings.value = res.data.settings
        }
        if (res.data.is_first_db_init) {
          toast.warning("数据库正在进行首次初始化，此过程可能需要您等待一段时间，请您耐心等候。",{position: "top-center",timeout: 10000})
        }

        // 3. 更新分组 (防止分组内的 Mod 被删了但分组里还有 ID)
        groupList.value = res.data.groups || []
        // 4. 更新激活列表 (通常扫描不会变动 active list，但为了同步“缺失”状态，更新一下也好)
        activeIds.value = (res.data.active_load_order || []).map(id => id.toLowerCase())
        savedActiveIds.value = [...res.data.active_load_order] || []
        // 清理临时列表 (Temp - Active)
        const activeSet = new Set(res.data.active_load_order)
        tempIds.value = tempIds.value.filter(id => !activeSet.has(id.toLowerCase()))
        inactiveIds.value = takeInactiveIds()
        // 2. 更新 Mod Map
        // 直接重建 Map，确保删除的 Mod 能被移除，新增的能被加入
        const tempMap = new Map()
        res.data.all_mods.forEach(mod => {
          // // 预先生成搜索索引字符串
          // mod._searchStr = [
          //   mod.name,
          //   mod.alias_name,
          //   mod.package_id,
          //   ...(mod.tags || []),
          //   mod.author
          // ].filter(Boolean).join(' ').toLowerCase(); // 拼接成一个长字符串
          // // 预先将 Tags 转为小写 Set，加速精确匹配
          // mod._tagsLower = new Set((mod.tags || []).map(t => t.toLowerCase()));
          
          // 启用时间
          if (mod.package_id && activeIds.value.includes(mod.package_id.toLowerCase()) && !mod.last_active_time) {
            mod.last_active_time = res.data.active_load_modify_time || Date.now()
          }
          
          // 强制保证字段存在
          if (!Array.isArray(mod.ignored_issues)) mod.ignored_issues = []
          if (!Array.isArray(mod.tags)) mod.tags = []
          if (!Array.isArray(mod.author) && !mod.author) mod.author = ['Unknown'] 
          tempMap.set(mod.package_id.toLowerCase(), mod)
        })
        allModsMap.value = tempMap
        // 更新激活加载时间
        activeLoadModifyTime.value = res.data.active_load_modify_time
        // 更新版本信息
        appVersion.value = res.data.app_version || 'Unknown'
        build.value = res.data.build || ''

        // 5. 检查路径 (仅初始化时)
        if (isInit && !res.data.paths_configured) {
          showSettings.value = true
        }
      } 
      else { throw new Error(res.message) }
      // 6. 更新数据版本号
      dataVersion.value ++;
      isLoading.value = false

      console.log("刷新列表成功:", res)
    } catch (e) {
      console.error("刷新列表失败:\n", e)
      toast.error(`刷新列表失败: \n${e.message}`)
    }
  }
  // 检查后端操作结果
  const checkResult = (res, workname) => {
    console.log(workname, res)
    if (res.status === 'success'){
      return true
      toast.success(`${workname}成功`)
    }else if(res.status === 'warning'){
      toast.warning(`${workname}注意: \n${res.message}`,{timeout: 2000})
    }else toast.error(`${workname}失败: \n${res.message}`)
    return false
  }

  // ===== Mod操作 =====
  // 显示 Mod 名称（优先 alias_name -> display_name -> name -> package_id）
  const displayModName = (modOrId, defaultName = '未知模组') => {
    let mod = null
    if(typeof modOrId === 'string')
      mod = takeModById(modOrId, defaultName)
    else if(modOrId?.package_id)
      mod = modOrId

    const res = mod?.alias_name || mod?.display_name || mod?.name || mod?.package_id
    return res || `⚠ ${defaultName} (${modOrId})`
  }
  const displayModType = (modOrId) => {
    let mod = null
    if(typeof modOrId === 'string')
      mod = takeModById(modOrId)
    else if(modOrId?.package_id)
      mod = modOrId
    const res = mod?.user_mod_type || mod?.mod_type || 'Unknown'
    return res
  }
  // 获取 Mod 对象
  const takeModById = (id, defaultName = '未知模组') => {
    if (!id) return null
    const lowerId = id.toLowerCase()
    if (allModsMap.value.has(lowerId)) {
      return allModsMap.value.get(lowerId)
    }
    // 构造缺失模组的“幽灵对象”
    return {
      package_id: id,
      name: `⚠ ${defaultName} (${id})`,
      author: ['Unknown'],
      is_missing: true,
      description: '该模组在本地未找到，可能未下载，或已被手动删除。'
    }
  }
  // 获取 Mod 对象列表
  const takeModListByIds = (ids) => {
    return Array.from(allModsMap.value.values()).filter(mod => ids.includes(mod.package_id))
  }
  // 从所有列表中移除指定 IDs
  const removeIdsOnAllList = (ids) => {
    if(typeof ids === 'string') ids = [ids]
    const lowerIdsSet = new Set(ids.map(id => id.toLowerCase()))
    activeIds.value = activeIds.value.filter(i => !lowerIdsSet.has(i))
    inactiveIds.value = inactiveIds.value.filter(i => !lowerIdsSet.has(i))
    tempIds.value = tempIds.value.filter(i => !lowerIdsSet.has(i))
  }
  // 选择 Mod (支持联锁自动多选 & 智能排序)
  const selectMods = (ids, lastId) => {
    // 1. 边界与归一化处理
    if (!ids) { clearSelection(); return; }
    const inputIds = Array.isArray(ids) ? ids : [ids];
    if (inputIds.length === 0) {
      selectedIds.value = [];
      lastSelectedMod.value = null;
      return;
    }
    // 2. 建立索引映射 (ID -> 原始输入位置)
    // 同时也作为快速查找表
    const inputMap = new Map();
    inputIds.forEach((id, idx) => inputMap.set(id.toLowerCase(), idx));
    const finalChunks = []; // 存储 { index: number, items: string[] }
    const processed = new Set(); // 记录已处理过的输入ID
    // 3. 遍历输入列表
    for (let i = 0; i < inputIds.length; i++) {
      const currentId = inputIds[i].toLowerCase();
      // 如果该ID已经被包含在之前的某个链条中处理过了，直接跳过
      if (processed.has(currentId)) continue;
      const mod = takeModById(currentId);
      // --- 情况 A: 独立 Mod (无联锁) ---
      // 快速路径，无需图遍历
      if (!mod || (!mod.lock_previous_mod && !mod.lock_next_mod)) {
        finalChunks.push({ index: i, items: [inputIds[i]] }); // 保持原ID大小写
        processed.add(currentId);
        continue;
      }
      // --- 情况 B: 联锁 Mod ---
      // 1. 向前回溯找到链头 (Head)
      let curr = currentId;
      const visited = new Set(); // 防死锁
      while (true) {
        const m = takeModById(curr);
        if (!m?.lock_previous_mod) break;
        const prev = m.lock_previous_mod.toLowerCase();
        if (visited.has(prev)) break; // 环路检测
        visited.add(prev);
        curr = prev;
      }
      const head = curr;
      // 2. 从链头向后构建完整链条，并寻找“锚点”
      const chainItems = [];
      let anchorIndex = -1; // 整个链条将要插入的位置
      curr = head;
      visited.clear();
      while (true) {
        // 加入链条
        // 注意：这里我们存的是 ID 字符串，如果需要保持原始输入的大小写，
        // 可以去 inputIds 里找，或者直接用小写（取决于你的需求）
        // 这里为了简单统一用原始ID（如果存在）或数据库ID
        const originalInputId = inputIds[inputMap.get(curr)];
        chainItems.push(originalInputId || curr); // 优先用输入列表里的原始格式
        // 【核心逻辑】：寻找锚点
        // 因为我们是从头(Head)到尾遍历链条，所以遇到的第一个“在输入列表中存在”的成员，
        // 就是逻辑顺序最靠前的成员。我们直接使用它的位置作为锚点。
        if (anchorIndex === -1 && inputMap.has(curr)) {
          anchorIndex = inputMap.get(curr);
        }
        // 标记为已处理，防止外层循环重复处理
        if (inputMap.has(curr)) {
          processed.add(curr);
        }
        // 继续向后
        const m = takeModById(curr);
        if (!m?.lock_next_mod) break;
        const next = m.lock_next_mod.toLowerCase();
        if (visited.has(next)) break; // 环路检测
        visited.add(next);
        curr = next;
      }
      // 3. 将整个链条加入结果块
      // 理论上 anchorIndex 一定存在，因为 currentId 本身就在链条里且在输入里
      finalChunks.push({ 
        index: anchorIndex, 
        items: chainItems 
      });
    }
    // 4. 排序并展平
    // 根据锚点索引重新排序块
    finalChunks.sort((a, b) => a.index - b.index);
    const result = finalChunks.flatMap(chunk => chunk.items);
    // 5. 更新状态
    selectedIds.value = result;
    // 处理最后选中项高亮
    if (lastId) {
      // 检查 lastId 是否在最终结果中 (大小写敏感处理)
      const target = result.find(id => id.toLowerCase() === lastId.toLowerCase());
      lastSelectedMod.value = target ? takeModById(target) : takeModById(result[result.length - 1]);
    } else {
      lastSelectedMod.value = takeModById(result[result.length - 1]);
    }
  }
  // 清除选择
  const clearSelection = () => {
    selectedIds.value = []
  }
  // 获取图片 URL (基于后端 FileManager)
  const getIconUrl = (id) => {
    const mod = takeModById(id)
    if (mod && mod.icon_url) return mod.icon_url // 列表图标
    if (mod && mod.thumb_url) return mod.thumb_url // 缩略图
    if (mod && mod.preview_url) return mod.preview_url // 详情大图
    return '' // 返回空或默认图路径
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
        console.error("启动扫描失败:", res)
        toast.error(`扫描启动失败: \n${res.message}`)
        return
      }
    } catch (e) {
      console.error("扫描请求异常:", e)
      toast.error(`扫描请求异常: \n${e.message}`)
    }
  }
  // 自动排序 Mod
  const autoSortMods = async (mod_ids) => {
    if (!window.pywebview) return
    if (!mod_ids || mod_ids.length === 0) {
      mod_ids = activeIds.value
    }
    try {
      const res = await window.pywebview.api.auto_sort_mods(mod_ids)
      if (checkResult(res, "自动排序Mod")) {
        activeIds.value = res.data.sorted_ids || []
        inactiveIds.value = takeInactiveIds()
        toast.success("自动排序完成")
        if(res.data.warnings?.length > 0) {
          let warningMessages = ''
          let warnModRule= []
          res.data.warnings.forEach(warning => {
            warningMessages += warning.message + '\n'
            if(warning.source_id) {
              warnModRule.push({mod_id: warning.source_id, target_id: warning.target_id||null ,type: warning.rule_type})
            }
          })
          toast.warning(warningMessages,{position: "top-center",timeout: 5000})
          if (warnModRule.length > 0) {
            let msg = '请检查以下Mod规则是否正确：\n'
            warnModRule.forEach(item => {
              msg += `${displayModName(item.mod_id)} 的 ${item.type.name} 可能存在问题：（${displayModName(item.target_id)}）\n`
            })
            toast.warning(msg,{position: "top-center",timeout: 10000})
          }
        }
        return true
      } 
    } catch (e) {
      console.error("自动排序Mod异常:", e)
      toast.error(`自动排序Mod异常: \n${e.message}`)
    }
    return false
  }
  // 获取加载顺序
  const getLoadOrder = async (mods_config_file_path=null) => {
    const order = await getFileOrder(mods_config_file_path)
    if (order) {
      activeIds.value = order.active_ids || []
      activeLoadModifyTime.value = order.active_load_modify_time || 0
      toast.success("Mod序列已加载")
    }
  }
  // 获取备份加载顺序
  const getBackupOrder = async (mods_config_file_path=null) => {
    const order = await getFileOrder(mods_config_file_path)
    if (order) {
      backupIds.value = order.active_ids || []
      currentBackupFile.value = order.file || mods_config_file_path
      backupLoadModifyTime.value = order.modify_time || 0
      return {path: currentBackupFile.value, modify_time: backupLoadModifyTime.value}
      // toast.success("备份Mod序列已加载")
    }
  }
  // 保存Mod加载顺序
  const saveLoadOrder = async () => {
    if (!isDirty.value) {
      toast.info("Mod序列未修改")
      return true
    }
    if (!window.pywebview) return false
    isLoading.value = true
    try {
      // 使用默认路径
      const res = await window.pywebview.api.save_load_order(activeIds.value)
      if (checkResult(res, "保存Mod加载顺序")) {
        savedActiveIds.value = [...activeIds.value] || []
        inactiveIds.value = takeInactiveIds()
        // console.log("保存加载顺序成功:", res)
        toast.success("Mod序列已保存")
        getBackups()
        updateModTime() // 更新Mod最后操作时间
        return true
      }
    } catch (e) {
      console.error("保存Mod序列异常:", e)
      toast.error(`保存Mod序列异常: \n${e.message}`)
    } finally {
      isLoading.value = false
    }
    return false
  }
  // 导出Mod加载顺序
  const exportLoadOrder = async (target_path=null, trigger_dialog=true) => {
    if (!window.pywebview) return false
    try {
      // 使用默认路径
      const res = await window.pywebview.api.export_load_order(activeIds.value, target_path, trigger_dialog)
      if (checkResult(res, "导出Mod加载顺序")) {
        // console.log("导出加载顺序成功:", res)
        toast.success("Mod序列已导出")
        return true
      } 
    } catch (e) {
      console.error("导出Mod序列异常:", e)
      toast.error(`导出Mod序列异常: \n${e.message}`)
    } 
    return false
  }
  // 应用备份列表
  const applyBackup = () => {
    if (!backupIds.value) return
    activeIds.value = backupIds.value
    toast.success("已应用Mod序列")
  }
  // 更新Mod用户数据
  const updateModUserData = async (modId, userData) => {
    if (!window.pywebview) return
    isLoading.value = true
    try {
      const res = await window.pywebview.api.update_mod_user_data(modId, userData)
      if (checkResult(res, "更新Mod用户数据")) {
        // 更新本地 Map
        const mod = allModsMap.value.get(modId.toLowerCase())
        if (mod) {
          Object.assign(mod, userData)
        }
        toast.success("Mod用户数据已更新", {timeout: 1000})
        return true
      } 
    } catch (e) {
      console.error("更新Mod用户数据异常:", e)
      toast.error(`更新Mod用户数据异常: \n${e.message}`)
    } finally {
      isLoading.value = false
    }
    return false
  }
  // 更新Mod最后操作时间
  const updateModTime = async () => {
    if (!window.pywebview) return
    isLoading.value = true
    try {
      // 提取所有对象的时间属性 {package_id:xxxx, last_active_time:xxxx, last_moved_time:xxxx}
      const all_mods = Array.from(allModsMap.value.values(), mod => ({
        package_id: mod.package_id,
        last_active_time: mod.last_active_time,
        last_moved_time: mod.last_moved_time
      }));
      console.log("更新Mod最后操作时间:", {all_mods_time:all_mods})
      const res = await window.pywebview.api.update_mod_time(all_mods)
      if (checkResult(res, "更新Mod最后操作时间")) {
        toast.success("Mod最后操作时间已更新", {timeout: 1000})
        return true
      } 
    } catch (e) {
      console.error("更新Mod最后操作时间异常:", e)
      toast.error(`更新Mod最后操作时间异常: \n${e.message}`)
    } finally {
      isLoading.value = false
    }
    return false
  }

  // === 批量操作 ===
  // 批量设置颜色
  const setModsColor = async (modIds, color) => {
    // 1. 立即更新本地状态 (让用户马上看到变化)
    modIds.forEach(id => {
      const mod = takeModById(id)
      if (mod) mod.sign_color = color
    })
    
    // 2. 发送请求给后端 (持久化)
    try {
      const res = await window.pywebview.api.set_mods_color(modIds, color)
      if (checkResult(res, "批量设置 Mod 颜色")) {
        toast.success("Mod 颜色已更新", {timeout: 1000})
        return true
      } 
      // 成功了什么都不用做，因为界面已经是最新的了
    } catch (e) {
      toast.error(`批量设置颜色失败: ${e}`)
      await refreshModList() 
    }
  }
  // 批量设置类型
  const setModsType = async (modIds, type) => {
    // 1. 立即更新本地状态 (让用户马上看到变化)
    modIds.forEach(id => {
      const mod = takeModById(id)
      if (mod) mod.user_mod_type = type
    })
    
    // 2. 发送请求给后端 (持久化)
    try {
      const res = await window.pywebview.api.set_user_mods_type(modIds, type)
      if (checkResult(res, "批量设置 Mod 类型")) {
        toast.success("Mod 类型已更新", {timeout: 1000})
        return true
      } 
    } catch (e) {
      toast.error(`批量设置类型失败: ${e}`)
      await refreshModList() 
    }
  }
  // 批量添加标签
  const addModsTags = async (modIds, tags) => {
    // 1. 立即更新本地状态 (让用户马上看到变化)
    modIds.forEach(id => {
      const mod = takeModById(id)
      if (mod) mod.tags = [...new Set([...(mod.tags || []), ...tags])]  // 自动去重
    })
    
    // 2. 发送请求给后端 (持久化)
    try {
      const res = await window.pywebview.api.add_tags_to_mods(modIds, tags)
      if (checkResult(res, "批量添加 Mod 标签")) {
        toast.success("Mod 标签已添加", {timeout: 1000})
        return true
      } 
    } catch (e) {
      toast.error(`批量添加标签失败: ${e}`)
      await refreshModList() 
    }
  }
  // 批量移除标签
  const removeModsTags = async (modIds, tags) => {
    // 1. 立即更新本地状态 (让用户马上看到变化)
    modIds.forEach(id => {
      const mod = takeModById(id)
      if (mod) mod.tags = (mod.tags || []).filter(t => !tags.includes(t))
    })
    // 2. 发送请求给后端 (持久化)
    try {
      const res = await window.pywebview.api.remove_tags_from_mods(modIds, tags)
      if (checkResult(res, "批量移除 Mod 标签")) {
        toast.success("Mod 标签已移除", {timeout: 1000})
        return true
      } 
    } catch (e) {
      toast.error(`批量移除标签失败: ${e}`)
      await refreshModList() 
    }
  }
  // 智能切换标签
  // 如果所有选中项都有该 Tag -> 移除
  // 如果部分有或都没有 -> 添加 (补全)
  const selectModsTag = async (tag) => {
    // 1. 检查当前状态
    const stats = selectedStats.value.tags[tag] // 'all', 'some', undefined
    if (stats === 'all') {
      // 全都有 -> 移除
      await removeModsTags(selectedIds.value, [tag]) // 需实现 removeModsTags
    } else {
      // 部分有或全无 -> 添加
      await addModsTags(selectedIds.value, [tag])
    }
  }
  // 智能切换分组 (Toggle Group)
  const selectModsGroup = async (groupId) => {
    const stats = selectedStats.value.groups[groupId]
    if (stats === 'all') {
      await groupRemoveMods(groupId, selectedIds.value)
    } else {
      await groupAddMods(groupId, selectedIds.value)
    }
  }
  // 批量设置 Mod 联锁
  const linkMods = async (modIds) => {
    if (!window.pywebview) return
    isLoading.value = true
    try {
      // 更新本地状态
      modIds.forEach((id, index) => {
        const mod = takeModById(id)
        if (mod) {
          mod.lock_previous_mod = modIds[index-1] || null
          mod.lock_next_mod = modIds[index+1] || null
        }
      })
      const res = await window.pywebview.api.link_mods(modIds)
      if (checkResult(res, "批量设置 Mod 联锁")) {
        toast.success("Mod 已互联", {timeout: 1000})
        return true
      }
    } catch (e) {
      console.error("批量设置 Mod 联锁异常:", e)
      toast.error(`批量设置 Mod 联锁异常: \n${e.message}`)
      await refreshModList() 
    } finally {
      isLoading.value = false
    }
    return false
  }
  // 批量解除 Mod 联锁
  const unlinkMods = async (modIds) => {
    if (!window.pywebview) return
    isLoading.value = true
    try {
      // 更新本地状态
      modIds.forEach(id => {
        const mod = takeModById(id)
        if (mod) {
          mod.lock_previous_mod = null
          mod.lock_next_mod = null
        }
      })
      const res = await window.pywebview.api.unlink_mods(modIds)
      if (checkResult(res, "批量解除 Mod 联锁")) {
        toast.success("Mod 已解除互联", {timeout: 1000})
        return true
      } 
    } catch (e) {
      console.error("批量解除 Mod 联锁异常:", e)
      toast.error(`批量解除 Mod 联锁异常: \n${e.message}`)
      await refreshModList()
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
      if (checkResult(res, "获取分组")) {
        groupList.value = res.data.groups || []
      }
    } catch (e) {
      console.error("获取分组异常:", e)
      toast.error(`获取分组异常: \n${e.message}`)
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
      // console.log("创建分组:", res)
      if (checkResult(res, "创建分组")) {
        groupList.value.push(res.data.group)
        // 排序
        groupList.value.sort((a, b) => a.sort_index - b.sort_index)
      } 
    } catch (e) {
      console.error("创建分组异常:", e)
      toast.error(`创建分组异常: \n${e.message}\n正在还原...`)
      // 失败时才重新拉取数据进行还原
      await getGroups() 
    } finally {
      isLoading.value = false
    }
  }
  // 删除分组
  const deleteGroup = async (groupId) => {
    if (!window.pywebview) return
    try {
      // 从列表中移除
      groupList.value = groupList.value.filter(group => group.group_id !== groupId)
      const res = await window.pywebview.api.delete_group(groupId)
      // console.log("删除分组:", res)
      if (checkResult(res, "删除分组")) {
        toast.success("分组已删除", {timeout: 1000})
      } 
    } catch (e) {
      console.error("删除分组异常:", e)
      toast.error(`删除分组异常: \n${e.message}\n正在还原...`)
      // 失败时才重新拉取数据进行还原
      await getGroups() 
    } 
  }
  // 更新分组
  const updateGroup = async (groupId, updates) => {
    if (!window.pywebview) return
    try {
      // 更新本地列表
      const group = groupList.value.find(g => g.group_id === groupId)
      if (group) Object.assign(group, updates)
      const res = await window.pywebview.api.update_group(groupId, updates)
      // console.log("更新分组:", res)
      if (checkResult(res, "更新分组")) {
        // toast.success("分组已更新", {timeout: 1000})
      } 
    } catch (e) {
      console.error("更新分组异常:", e)
      toast.error(`更新分组异常: \n${e.message}\n正在还原...`)
      // 失败时才重新拉取数据进行还原
      await getGroups() 
    }
  }
  // 分组添加模组
  const groupAddMods = async (groupId, modIds) => {
    if (!window.pywebview) return
    try {
      // 更新本地分组
      const group = groupList.value.find(g => g.group_id === groupId)
      if (group) {
        group.mod_ids = [...group.mod_ids, ...modIds]
      }
      const res = await window.pywebview.api.group_add_mods(groupId, modIds)
      // console.log("分组添加模组:", res)
      if (checkResult(res, "分组添加模组")) {
        // toast.success("模组已添加到分组", {timeout: 1000})
      } 
    } catch (e) {
      console.error("分组添加模组异常:", e)
      toast.error(`分组添加模组异常: \n${e.message}\n正在还原...`)
      // 失败时才重新拉取数据进行还原
      await getGroups() 
    }
  }
  // 分组移除模组
  const groupRemoveMods = async (groupId, modIds) => {
    if (!window.pywebview) return
    try {
      // 更新本地分组
      const group = groupList.value.find(g => g.group_id === groupId)
      if (group) {
        group.mod_ids = group.mod_ids.filter(id => !modIds.includes(id))
      }
      const res = await window.pywebview.api.group_remove_mods(groupId, modIds)
      // console.log("分组移除模组:", res)
      if (checkResult(res, "分组移除模组")) {
        // toast.success("模组已从分组移除", {timeout: 1000})
      } 
    } catch (e) {
      console.error("分组移除模组异常:", e)
      toast.error(`分组移除模组异常: \n${e.message}\n正在还原...`)
      // 失败时才重新拉取数据进行还原
      await getGroups() 
    } 
  }
  // 分组批量展开切换
  const changeAllGroupExpansion = async (isExpanded) => {
    if (!window.pywebview) return
    try {
      // 更新本地分组
      groupList.value.forEach(group => group.is_expanded = isExpanded)
      const res = await window.pywebview.api.update_all_expansion_state(isExpanded)
      // console.log("批量展开切换:", res)
      if (checkResult(res, "批量展开切换")) {
        // toast.success("所有分组已切换展开状态", {timeout: 1000})
      } 
    } catch (e) {
      console.error("批量展开切换异常:", e)
      toast.error(`批量展开切换异常: \n${e.message}\n正在还原...`)
      // 失败时才重新拉取数据进行还原
      await getGroups() 
    }
  }
  // 分组排序
  const groupReorder = async (groupIds=groupList.value.map(g => g.group_id)) => {
    if (!window.pywebview) return
    try {
      // 更新本地分组排序
      groupList.value.sort((a, b) => groupIds.indexOf(a.group_id) - groupIds.indexOf(b.group_id))
      const res = await window.pywebview.api.group_reorder(groupIds)
      // console.log("分组排序:", res)
      if (checkResult(res, "分组排序")) {
        // toast.success("分组已排序", {timeout: 1000})
      } 
    } catch (e) {
      console.error("分组排序异常:", e)
      toast.error(`分组排序异常: \n${e.message}\n正在还原...`)
      // 失败时才重新拉取数据进行还原
      await getGroups() 
    }
  }
  // 分组内排序
  const groupContentReorder = async (groupId, modIds) => {
    if (!window.pywebview) return
    try {
      const res = await window.pywebview.api.group_content_reorder(groupId, modIds)
      // console.log("分组内排序:", res)
      if (checkResult(res, "分组内排序")) {
        // 更新本地分组
        const group = groupList.value.find(g => g.group_id === groupId)
        if (group) {
          group.mod_ids = modIds
        }
      } 
      else { throw new Error(res.message) }
    } catch (e) {
      console.error("分组内排序异常:", e)
      toast.error(`分组内排序异常: \n${e.message}\n正在还原...`)
      // 失败时才重新拉取数据进行还原
      await getGroups() 
    }
  }
  // 根据 Mod ID 获取所属分组列表
  const takeGroupsByModId = (modId) => {
    return groupList.value.filter(g => g.mod_ids.includes(modId))
  }
  // 根据分组 ID 获取分组数据
  const takeGroupById = (groupId) => {
    return groupList.value.find(g => g.group_id === groupId) || null
  }

  // ===== 实时问题分析器 =====
  const modIssues = computed(() => {
    const issuesMap = new Map() // Key: modId, Value: Array<Issue>
    const activeSet = new Set(activeIds.value)
    
    // 辅助函数：添加问题
    const addIssue = (id, type, level, message, targetId = null) => {
      const mod = takeModById(id)
      // 1. 安全检查：确保 ignored_issues 存在且是一个数组
      const ignoredList = mod?.ignored_issues || []
      if (ignoredList.includes(type)) return

      if (!issuesMap.has(id)) issuesMap.set(id, [])
      issuesMap.get(id).push({
        type,
        level,
        message,
        targetId       // 关联的 Mod ID (如果有)
      })
    }

    // 1. 全局检查 (遍历所有 Mod)
    // 包括 inactive 的也要检查版本和文件完整性
    for (const mod of allModsMap.value.values()) {
      const id = mod.package_id.toLowerCase()

      // A. 文件丢失检查
      if (mod.is_missing || !mod.path) {
        addIssue(id, ISSUE_TYPE.ERROR_MISSING_FILE, ISSUE_LEVEL.ERROR, '本地文件缺失或无法解析')
        continue // 文件都没了，后面的检查没意义
      }

      // B. 游戏版本检查
      // 假设 settings.game_version 是 "1.5.4104"
      // mod.supported_versions 是 ["1.4", "1.5"]
      if (settings.value.game_version) {
        const gameVerMajor = settings.value.game_version.substring(0, 3) // "1.5"
        if (mod.supported_versions && !mod.supported_versions.includes(gameVerMajor)) {
           addIssue(id, ISSUE_TYPE.WARN_VERSION_MISMATCH, ISSUE_LEVEL.WARN, 
             `^^版本问题^^：不支持当前游戏版本··[[${gameVerMajor}]]·· \n __(支持: ··${mod.supported_versions.join('··, ··')}··)__`)
        }
      }

      // C. 联锁检查 (Link Mods)
      if (mod.lock_next_mod || mod.lock_previous_mod) {
        const allModIds = new Set(allModsMap.value.keys())
        // 缺失检查
        if (mod.lock_next_mod && !allModIds.has(mod.lock_next_mod)) {
          addIssue(id, ISSUE_TYPE.WARN_LINK_MOD_MISSING, ISSUE_LEVEL.WARN, 
            `^^后置联锁模组缺失^^：${displayModName(mod.lock_next_mod)}`, mod.lock_next_mod)
          continue
        }
        if (mod.lock_previous_mod && !allModIds.has(mod.lock_previous_mod)) {
          addIssue(id, ISSUE_TYPE.WARN_LINK_MOD_MISSING, ISSUE_LEVEL.WARN, 
            `^^前置联锁模组缺失^^：${displayModName(mod.lock_previous_mod)}`, mod.lock_previous_mod)
          continue
        }
      }
    }

    // 2. 启用列表检查 (遍历 activeIds)
    // 这里的顺序很重要，activeIds 是有序数组
    activeIds.value.forEach((id, index) => {
      const mod = allModsMap.value.get(id)
      if (!mod || mod.is_missing || !mod.path) {
        addIssue(id, ISSUE_TYPE.ERROR_MISSING_FILE, ISSUE_LEVEL.ERROR, '本地文件缺失或无法解析')
        return
      }

      // C. 依赖检查 (Dependencies)
      if (mod.dependencies_mods) {
        mod.dependencies_mods.forEach(dep => {
          const depId = dep.package_id.toLowerCase()
          
          // C1. 是否完全缺失
          if (!allModsMap.value.has(depId)) {
            addIssue(id, ISSUE_TYPE.ERROR_MISSING_DEPENDENCY, ISSUE_LEVEL.ERROR, 
              `!!依赖缺失!!：${displayModName(dep)}`, depId)
            return
          }
          // C2. 是否未启用
          if (!activeSet.has(depId)) {
            addIssue(id, ISSUE_TYPE.ERROR_INACTIVE_DEPENDENCY, ISSUE_LEVEL.ERROR, 
              `!!依赖未启用!!：${displayModName(dep)}`, depId)
            return
          }
          // C3. 排序检查 (依赖必须在当前 Mod 之前)
          const depIndex = activeIds.value.indexOf(depId)
          if (depIndex > index) {
            addIssue(id, ISSUE_TYPE.WARN_WRONG_ORDER, ISSUE_LEVEL.WARN, 
              `!!依赖后置!!：必须在依赖 [[${displayModName(dep)}]] 之后加载`, depId)
          }
        })
      }

      // D. Load After / Load Before 检查
      if (mod.load_after_mods) {
        mod.load_after_mods.forEach(dep => {
          const depId = dep.toLowerCase()
          // 排序检查 (前置必须在当前 Mod 之前)
          const depIndex = activeIds.value.indexOf(depId)
          if (depIndex !== -1 && depIndex > index) {
            addIssue(id, ISSUE_TYPE.WARN_WRONG_ORDER, ISSUE_LEVEL.WARN, 
              `!!排序错误!!：必须在 [[${displayModName(depId)}]] 之后加载`, depId)
          }
        })
      }
      if (mod.load_before_mods) {
        mod.load_before_mods.forEach(dep => {
          const depId = dep.toLowerCase()
          // 排序检查 (前置必须在当前 Mod 之后)
          const depIndex = activeIds.value.indexOf(depId)
          if (depIndex !== -1 && depIndex < index) {
            addIssue(id, ISSUE_TYPE.WARN_WRONG_ORDER, ISSUE_LEVEL.WARN, 
              `!!排序错误!!：必须在 [[${displayModName(depId)}]] 之前加载`, depId)
          }
        })
      }
      // 联锁排序检查
      if(mod.lock_previous_mod && activeIds.value[index-1] !== mod.lock_previous_mod) {
        addIssue(id, ISSUE_TYPE.WARN_LINK_WRONG_ORDER, ISSUE_LEVEL.WARN, 
          `^^联锁排序错误^^：前一个模组应为 [[${displayModName(mod.lock_previous_mod)}]]`, mod.lock_previous_mod)
      }
      if(mod.lock_next_mod && activeIds.value[index+1] !== mod.lock_next_mod) {
        addIssue(id, ISSUE_TYPE.WARN_LINK_WRONG_ORDER, ISSUE_LEVEL.WARN, 
          `^^联锁排序错误^^：后一个模组应为 [[${displayModName(mod.lock_next_mod)}]]`, mod.lock_next_mod)
      }
      
      // E. 不兼容检查 (incompatible_mods)
      if (mod.incompatible_mods) {
        mod.incompatible_mods.forEach(badId => {
          const lowerBad = badId.toLowerCase()
          if (activeSet.has(lowerBad)) {
            addIssue(id, ISSUE_TYPE.ERROR_INCOMPATIBLE, ISSUE_LEVEL.ERROR, 
              `!!模组冲突!!：与 ${displayModName(lowerBad)} 不兼容`, lowerBad)
          }
        })
      }
    })
    // 3. 禁用列表检查 (遍历 inactiveIds)
    inactiveIds.value.forEach((id, index) => {
      const mod = allModsMap.value.get(id)
      if (!mod) return
      // 联锁排序检查
      if(mod.lock_previous_mod && inactiveIds.value[index-1] !== mod.lock_previous_mod) {
        addIssue(id, ISSUE_TYPE.WARN_LINK_WRONG_ORDER, ISSUE_LEVEL.WARN, 
          `^^联锁排序错误^^：前一个模组应为 [[${displayModName(mod.lock_previous_mod)}]]`, mod.lock_previous_mod)
      }
      if(mod.lock_next_mod && inactiveIds.value[index+1] !== mod.lock_next_mod) {
        addIssue(id, ISSUE_TYPE.WARN_LINK_WRONG_ORDER, ISSUE_LEVEL.WARN, 
          `^^联锁排序错误^^：后一个模组应为 [[${displayModName(mod.lock_next_mod)}]]`, mod.lock_next_mod)
      }
    })
    // 4. 临时列表检查 (遍历 tempIds)
    tempIds.value.forEach((id, index) => {
      const mod = allModsMap.value.get(id)
      if (!mod) return
      // 联锁排序检查
      if(mod.lock_previous_mod && tempIds.value[index-1] !== mod.lock_previous_mod) {
        addIssue(id, ISSUE_TYPE.WARN_LINK_WRONG_ORDER, ISSUE_LEVEL.WARN, 
          `^^联锁排序错误^^：前一个模组应为 [[${displayModName(mod.lock_previous_mod)}]]`, mod.lock_previous_mod)
      }
      if(mod.lock_next_mod && tempIds.value[index+1] !== mod.lock_next_mod) {
        addIssue(id, ISSUE_TYPE.WARN_LINK_WRONG_ORDER, ISSUE_LEVEL.WARN, 
          `^^联锁排序错误^^：后一个模组应为 [[${displayModName(mod.lock_next_mod)}]]`, mod.lock_next_mod)
      }
    })

    return issuesMap
  })
  // 辅助：获取某个 Mod 的最高级别问题
  const getModIssueState = (id) => {
    const issues = modIssues.value.get(id.toLowerCase())
    if (!issues || issues.length === 0) return null
    
    // 优先级: ERROR > WARN > INFO
    if (issues.some(i => i.level === 'error')) return 'error'
    if (issues.some(i => i.level === 'warn')) return 'warn'
    return 'info'
  }
  // 忽略/取消忽略问题
  // type: 传入错误类型字符串为忽略该问题；不传(null/undefined)为清空所有忽略(重置)
  const ignoreIssue = async (modId, type) => {
      const mod = takeModById(modId)
      // console.log('ignoreIssue', mod)
      if (!mod) return // 幽灵对象无法保存设置

      // 1. 安全获取当前列表 (创建副本，防止直接修改原引用)
      // 如果 mod.ignored_issues 不存在，默认为空数组
      let currentIgnored = Array.isArray(mod.ignored_issues) ? [...mod.ignored_issues] : []

      // console.log('ignoreIssue', modId, type, currentIgnored)
      if (!type) {
          // === 模式 A: 恢复所有警告 (清空忽略列表) ===
          if (currentIgnored.length === 0) return // 本来就是空的，无需操作
          currentIgnored = []
      } else {
          // === 模式 B: 忽略特定问题 ===
          if (currentIgnored.includes(type)) return // 已经忽略了，无需操作
          currentIgnored.push(type)
      }
      // 2. 调用后端保存
      // 注意：这里我们传入新的数组，后端保存成功后
      mod.ignored_issues = currentIgnored
      const res = await updateModUserData(modId, { ignored_issues: currentIgnored })
      if (!res.status==='success') {
        toast.error(`忽略问题失败：${res.message}`)
      }
  }
  // 批量忽略/取消忽略问题
  const batchIgnoreIssues = async (modIds, type = null) => {
    isLoading.value = true;
    const updates = []; // 准备发送给后端的批量数据
    try {
      modIds.forEach((id) => {
        const mod = takeModById(id);
        if (!mod || mod.is_missing) return;
        let currentIgnored = Array.isArray(mod.ignored_issues) ? [...mod.ignored_issues] : [];
        let needsUpdate = false;
        if (!type) {
          // === 模式 A: 恢复所有警告 ===
          if (currentIgnored.length > 0) {
            currentIgnored = [];
            needsUpdate = true;
          }
        } else {
          // === 模式 B: 忽略特定问题 ===
          const currentModIssues = modIssues.value.get(id.toLowerCase()) || [];
          const hasThisIssue = currentModIssues.some(i => i.type === type);
          if (hasThisIssue && !currentIgnored.includes(type)) {
            currentIgnored.push(type);
            needsUpdate = true;
          }
        }
        if (needsUpdate) {
          // 1. 先更新本地 UI 状态 (响应式)
          mod.ignored_issues = currentIgnored;
          // 2. 加入批量更新队列
          updates.push({
            mod_id: id,
            ignored_issues: currentIgnored
          });
        }
      });
      // 如果没有实质性变化，直接返回
      if (updates.length === 0) return;
      // 3. 一次性调用后端 API
      const res = await window.pywebview.api.set_mods_ignore_issues(updates);
      if (res.status === 'success') {
        toast.success(type ? `已忽略 ${updates.length} 项问题` : `已恢复 ${updates.length} 项警告`);
      } else {
        throw new Error(res.message);
      }
    } catch (e) {
      console.error("批量忽略操作失败:", e);
      toast.error(`操作失败: ${e.message}`);
      // 如果失败了，可能需要重新刷新列表以保证数据一致性
      await refreshModList();
    } finally {
      isLoading.value = false;
    }
  };

  // 获取指定列表的错误统计
  const getListIssues = (listType) => {
    // 1. 确定目标 ID 集合
    let targetIds = []
    if (listType === 'active') targetIds = activeIds.value
    else if (listType === 'inactive') targetIds = inactiveIds.value
    else if (listType === 'temp') targetIds = tempIds.value
    
    // 2. 初始化结果结构
    const result = {
      count: 0,      // 总问题 Mod 数
      errorCount: 0, // 严重错误数
      warnCount: 0,  // 警告数
      stats: {
        [ISSUE_TYPE.ERROR_MISSING_FILE]: [],
        [ISSUE_TYPE.ERROR_MISSING_DEPENDENCY]: [],
        [ISSUE_TYPE.ERROR_INACTIVE_DEPENDENCY]: [],
        [ISSUE_TYPE.ERROR_INCOMPATIBLE]: [],
        [ISSUE_TYPE.WARN_WRONG_ORDER]: [],
        [ISSUE_TYPE.WARN_VERSION_MISMATCH]: [],
      } 
    }

    // 3. 遍历统计
    targetIds.forEach(id => {
      const issues = modIssues.value.get(id.toLowerCase())
      if (!issues || issues.length === 0) return

      result.count++
      
      // 统计严重程度 (只要有一个 error 就算 error 级)
      if (issues.some(i => i.level === 'error')) result.errorCount++
      else result.warnCount++

      // 按类型聚合 Mod 名称
      // 一个 Mod 可能有多个错误类型，都需要记录
      // 为了避免重复，我们用 Set 辅助，或者只取第一个错误类型？
      // 建议：统计所有出现的错误类型
      issues.forEach(issue => {
        const typeKey = issue.type
        if (!result.stats[typeKey]) {
          result.stats[typeKey] = []
        }
        // 避免同一个 Mod 在同一个类型下重复 (虽然一般不会)
        if (!result.stats[typeKey].includes(id.toLowerCase())) {
          result.stats[typeKey].push(id.toLowerCase())
        }
      })
    })

    return result
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
        if (checkResult(res, "应用设置")) {
            // 更新本地 store
            Object.assign(settings.value, newSettings)
            // 如果路径变了，可能需要重新扫描，这里简单起见先关闭弹窗
            closeSettings()
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
  // 重置数据库
  const resetDatabase = async () => {
    if (!window.pywebview) return
    isLoading.value = true
    try {
      const res = await window.pywebview.api.reset_database()
      if (checkResult(res, "重置数据库")) {
        closeSettings()
        // 提示成功
        toast.success("数据库已重置！")
        // 清空本地状态
        allModsMap.value.clear()
        activeIds.value = []
        groupList.value = []
        
        // 重新初始化 (这会触发扫描)
        await initialize()
        // 或者直接触发扫描
        // scanMods()
      }
    } finally {
      isLoading.value = false
    }
  }

  // ===== 系统操作 =====
  // 启动游戏
  const launchGame = async () => {
    const res = await saveLoadOrder()
    if (!res) return
    if(settings.value.game_install_path?.includes("SteamLibrary\\steamapps\\common")){
      // 通过 steam 启动游戏
      openUrl("steam://rungameid/294100")
      toast.success("正在通过 steam 启动游戏……")
      console.log("通过 steam 启动游戏")
    }else if(settings.value.game_install_path){
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
  // 从文件获取加载顺序
  const getFileOrder = async (mods_config_file_path=null) => {
    if (!window.pywebview) return
    const res = mods_config_file_path ? 
      await window.pywebview.api.open_load_order_file(mods_config_file_path) : 
      await window.pywebview.api.get_load_order()
    
    if (checkResult(res, "打开加载顺序")) {
      console.log("打开加载顺序:", res)
      return res.data
    }
  }
  // 打开Url
  const openUrl = (url) => {
    if(url) window.open(url, '_blank')
  }
  const openSteamWorkshopUrl = (url) => {
    if(url) {
      const steamUrl = url.replace('https://steamcommunity.com/sharedfiles/filedetails/?id=', 'steam://url/CommunityFilePage/')
      window.open(steamUrl, '_blank')
    }
  }

  // 打开路径
  const openPath = async (path) => {
    if(!path) return
    if(!window.pywebview) return
    console.log("打开路径:", path)
    const res = await window.pywebview.api.open_path(path)
    checkResult(res, "打开路径")
  }
  const openBackupPath = async () => {
    openPath(settings.value.home_path+"\\backups")
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
  // 获取文件路径
  const getFilePath = async (home_path, file_types=('XML Files (*.xml;*.rws)', 'All Files (*.*)')) => {
      if(!window.pywebview) return
      // 调用后端 API
      const res = await window.pywebview.api.select_file_dialog(home_path, file_types)
      if (checkResult(res, "获取文件路径")) {
          return res.data
      }
  }
  // 获取所有备份文件路径 {today: [], earlier: [], other: []}
  const getBackups = async () => {
    if(!window.pywebview) return
    const res = await window.pywebview.api.get_all_backups()
    if (checkResult(res, "获取备份文件")) {
       // 更新本地 store
      backups.value = res.data
      console.log("获取备份文件:", backups.value)
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
  // 删除文件/文件夹
  const deletePath = async (path) => {
    if(!window.pywebview) return
    const res = await window.pywebview.api.delete_path(path)
    if (checkResult(res, "删除文件/文件夹")) {
      toast.success(`文件/文件夹已删除: \n${path}`)
      return true
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

  return {
    // 状态管理
    scanProgress, dataVersion, modIssues, ISSUE_TITLE_MAP, sourceTypeMap, MOD_TYPE_MAP, modColorList, backups, showDiffDrawer, currentBackupFile,
    conflictList, allModTags, selectedStats, activeLoadModifyTime, backupLoadModifyTime, ruleStore, 
    initialize, getLoadOrder, refreshModList, getModIssueState, ignoreIssue, batchIgnoreIssues, getListIssues, applyBackup, getBackupOrder, 
    selectModsTag, selectModsGroup, autoSortMods,

    // Mod 相关
    allModsMap, backupIds, activeIds, tempIds, inactiveIds, selectedIds, selectedMods, lastSelectedMod, currentTargetId, 
    takeModById, takeModListByIds, displayModName, displayModType, removeIdsOnAllList, getIconUrl, 
    selectMods, clearSelection, scanMods, saveLoadOrder, updateModUserData, 
    setModsColor, setModsType, addModsTags, removeModsTags, linkMods, unlinkMods,

    // 分组相关
    groupList, isDraggingGroup,
    getGroups, createGroup, deleteGroup, updateGroup, changeAllGroupExpansion, groupAddMods, 
    groupRemoveMods, groupReorder, groupContentReorder, takeGroupsByModId, takeGroupById,

    // 设置相关
    showSettings, isLoading, isDirty, settings, showLogDrawer, showTestDrawer, showRuleDrawer, 
    appVersion, build,
    openSettings, closeSettings, applySettings, saveSetting,

    // 下载相关
    downloadTasks, isDownloading, activeDownloadTask, startDownload,

    // 系统操作
    launchGame, openPath, openBackupPath, openUrl, openSteamWorkshopUrl, deletePath, getFileOrder,
    autoDetectPaths, getFolderPath, getFilePath, resetDatabase, getBackups, exportLoadOrder,
  }
})