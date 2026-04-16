import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { createToastInterface } from 'vue-toastification'
import { useAppStore } from './appStore'
import { useGroupStore } from './groupStore'
import { ISSUE_LEVEL, ISSUE_TYPE, ISSUE_TITLE_MAP } from '../utils/constants'
import { useConfirmStore } from './confirmStore'
import { useProfileStore } from './profileStore'

export const useModStore = defineStore('mods', () => {
  const toast = createToastInterface()
  const appStore = useAppStore()
  const confirmStore = useConfirmStore()
  const checkResult = appStore.checkResult
  
  // === State ===
  const allModsMap = ref(new Map())   // 核心数据，使用 Map 加速查找
  const dataVersion = ref(0)          // 数据版本，用于响应式刷新触发器

  const inactiveIds = ref([])         // 未激活Mod列表
  const tempIds = ref([])             // 临时Mod列表
  const activeIds = ref([])           // 已激活Mod列表
  
  const interlocksMap = ref(new Map()) // 联锁字典: Map<String(interlock_id), Array<String(package_ids)>>
  const savedInactiveIds = ref([])   // 从后端拉取的历史停用顺序
  const savedActiveIds = ref([])      // 原始已激活列表快照（用于判断 列表变化）
  const activeLoadModifyTime = ref(0) // 已激活列表最后修改时间戳

  const conflictList = ref([])        // 重复包名冲突列表
  const coexistenceList = ref([])     // 共存Mod列表

  
  // 选择状态
  const selectedIds = ref([])         // 已选中的 Mod ID
  const lastSelectedMod = ref(null)   // 最后选中的 Mod 对象
  const currentTargetId = ref('')     // 当前目标 ID (查找定位用)

  // 列表历史（仅当前会话内存态）
  const LIST_HISTORY_LIMIT = 100
  const listHistoryUndoStack = ref([])
  const listHistoryRedoStack = ref([])
  const isApplyingListHistory = ref(false)

  // === Getters ===
  // 检查列表变化
  const isDirty = computed(() => {
    // 简单数组比较：长度不同，或内容/顺序不同
    if (activeIds.value.length !== savedActiveIds.value.length) return true
    // 逐个比较
    return activeIds.value.some((id, i) => id !== savedActiveIds.value[i])
  })
  // 获取选中的所有模组对象
  const selectedMods = computed(() => {
    // 利用Boolean()转换规则，剔除数组中所有假值（undefined/null/0/''/false/NaN）
    return selectedIds.value.map(id => takeModById(id)).filter(Boolean)
  })
  // 计算选中项的共有属性
  /* 返回结构：{
      tags: { 'Core': 'all', 'Lib': 'some' }, // all=全有, some=部分有
      groups: { 'g1': 'all', 'g2': 'some' },
      color: '#ff0000' (如果全都一样), 'mixed' (如果不一样), null (全无)
    } */
  const selectedStats = computed(() => {
    const ids = selectedIds.value
    if (ids.length === 0) return { tags: {}, groups: {}, color: null }
    // 检查是否存在有效模组
    const firstMod = takeModById(ids[0])
    if (!firstMod) return {}

    // 1. 初始化统计 (以第一个为基准，或者全量统计)，只统计“拥有该属性的Mod数量”
    const tagCounts = {} // { 'Core': 10, 'Lib': 5 }
    const groupCounts = {}
    const colors = new Set()

    const groupStore = useGroupStore()
    ids.forEach(id => {
      const mod = takeModById(id)
      if (!mod) return
      // 统计 Tags 出现的次数
      mod.tags?.forEach(t => tagCounts[t] = (tagCounts[t] || 0) + 1)
      // 统计 Groups 出现的次数
      const modGroups = groupStore.takeGroupsByModId(id)
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
  // 获取所有模组的所有标签（去重）
  const allModTags = computed(() => {
    return [...new Set(Array.from(allModsMap.value.values()).flatMap(mod => mod.tags || []))]
  })
  // 获取所有模组的所有创意工坊ID（去重）
  const allModWorkshopIds = computed(() => {
    return new Set(Array.from(allModsMap.value.values()).filter(mod => mod.store === 'workshop').map(mod => mod.workshop_id))
  })
  // 获取所有模组的所有包名ID（去重）
  const allModPackageIds = computed(() => {
    return new Set(Array.from(allModsMap.value.values()).map(mod => mod.package_id))
  })
  const listHistoryTotal = computed(() => listHistoryUndoStack.value.length + listHistoryRedoStack.value.length)
  const listHistoryPosition = computed(() => listHistoryUndoStack.value.length)
  const canUndoListHistory = computed(() => listHistoryUndoStack.value.length > 0)
  const canRedoListHistory = computed(() => listHistoryRedoStack.value.length > 0)


  // === Actions ===
  const normalizeHistoryModIds = (ids = []) => {
    const source = Array.isArray(ids) ? ids : [ids]
    return [...new Set(
      source
        .map(id => String(id || '').trim().toLowerCase())
        .filter(Boolean)
    )]
  }
  const createModTimeSnapshot = (ids = []) => {
    const snapshot = {}
    normalizeHistoryModIds(ids).forEach(id => {
      const mod = allModsMap.value.get(id)
      if (!mod) return
      snapshot[id] = {
        last_active_time: mod.last_active_time || 0,
        last_moved_time: mod.last_moved_time || 0
      }
    })
    return snapshot
  }
  const createListHistorySnapshot = (trackedModIds = []) => ({
    activeIds: [...activeIds.value],
    inactiveIds: [...inactiveIds.value],
    tempIds: [...tempIds.value],
    savedActiveIds: [...savedActiveIds.value],
    activeLoadModifyTime: activeLoadModifyTime.value || 0,
    modTimes: createModTimeSnapshot(trackedModIds)
  })
  const restoreModTimeSnapshot = (modTimes = {}) => {
    Object.entries(modTimes || {}).forEach(([id, times]) => {
      const mod = allModsMap.value.get(String(id).toLowerCase())
      if (!mod) return
      mod.last_active_time = times?.last_active_time || 0
      mod.last_moved_time = times?.last_moved_time || 0
    })
  }
  const setListIds = (listId, ids = []) => {
    const nextIds = Array.isArray(ids) ? [...ids] : []
    if (listId === 'active') activeIds.value = nextIds
    else if (listId === 'inactive') inactiveIds.value = nextIds
    else if (listId === 'temp') tempIds.value = nextIds
  }
  const clearListHistory = () => {
    listHistoryUndoStack.value = []
    listHistoryRedoStack.value = []
  }
  const isSameArray = (left = [], right = []) => {
    if (left.length !== right.length) return false
    return left.every((item, index) => item === right[index])
  }
  const didListHistorySnapshotChange = (before, after) => {
    if (!before || !after) return false
    if (!isSameArray(before.activeIds, after.activeIds)) return true
    if (!isSameArray(before.inactiveIds, after.inactiveIds)) return true
    if (!isSameArray(before.tempIds, after.tempIds)) return true
    if (!isSameArray(before.savedActiveIds, after.savedActiveIds)) return true
    return (before.activeLoadModifyTime || 0) !== (after.activeLoadModifyTime || 0)
  }
  const pushListHistoryEntry = (entry) => {
    listHistoryUndoStack.value.push(entry)
    if (listHistoryUndoStack.value.length > LIST_HISTORY_LIMIT) {
      listHistoryUndoStack.value.shift()
    }
    listHistoryRedoStack.value = []
  }
  const recordListHistory = ({ before, trackedModIds = [], type = 'list-edit', label = '' } = {}) => {
    if (isApplyingListHistory.value || !before) return false
    const after = createListHistorySnapshot(trackedModIds)
    if (!didListHistorySnapshotChange(before, after)) return false
    pushListHistoryEntry({
      type,
      label,
      at: Date.now(),
      before,
      after
    })
    return true
  }
  const runListHistoryTransaction = async (meta = {}, handler) => {
    if (typeof handler !== 'function') return false
    if (isApplyingListHistory.value) {
      return await handler()
    }
    const trackedModIds = normalizeHistoryModIds(meta.trackedModIds || [])
    const before = createListHistorySnapshot(trackedModIds)
    const result = await handler()
    recordListHistory({ ...meta, before, trackedModIds })
    return result
  }
  const restoreListHistorySnapshot = (snapshot) => {
    if (!snapshot) return false
    activeIds.value = [...(snapshot.activeIds || [])]
    inactiveIds.value = [...(snapshot.inactiveIds || [])]
    tempIds.value = [...(snapshot.tempIds || [])]
    savedActiveIds.value = [...(snapshot.savedActiveIds || [])]
    activeLoadModifyTime.value = snapshot.activeLoadModifyTime || 0
    restoreModTimeSnapshot(snapshot.modTimes)
    dataVersion.value++
    return true
  }
  const undoListHistory = () => {
    const entry = listHistoryUndoStack.value.pop()
    if (!entry) return false
    isApplyingListHistory.value = true
    try {
      restoreListHistorySnapshot(entry.before)
      listHistoryRedoStack.value.push(entry)
      return true
    } finally {
      isApplyingListHistory.value = false
    }
  }
  const redoListHistory = () => {
    const entry = listHistoryRedoStack.value.pop()
    if (!entry) return false
    isApplyingListHistory.value = true
    try {
      restoreListHistorySnapshot(entry.after)
      listHistoryUndoStack.value.push(entry)
      return true
    } finally {
      isApplyingListHistory.value = false
    }
  }
  // 获取 Mod 对象
  const takeModById = (id, defaultName = '未知模组') => {
    if (!id) return null
    const lowerId = id.toLowerCase()
    if (allModsMap.value.has(lowerId)) return allModsMap.value.get(lowerId)
    // 构造缺失模组的“幽灵对象”
    return {
      package_id: id,
      name: `⚠ ${defaultName} (${id})`,
      path: null,
      description: '该模组在本地未找到，可能未下载，或已被手动删除。',
      isMissing: true,
    }
  }
  const hasRealModById = (id) => {
    if (!id) return false
    const lowerId = String(id).toLowerCase()
    if (!allModsMap.value.has(lowerId)) return false
    const mod = allModsMap.value.get(lowerId)
    // ghost 项虽然会被塞进 allModsMap，但它们不应该被当成“真实已安装模组”。
    return !!mod && !mod.isMissing && !!mod.path
  }
  // 获取 Mod 对象列表
  const takeModListByIds = (ids) => {
    return Array.from(allModsMap.value.values()).filter(mod => ids.includes(mod.package_id))
  }
  // 显示 Mod 名称（优先 alias_name -> display_name -> name -> package_id）
  const displayModName = (modOrId, defaultName = '未知模组') => {
    // 处理输入：Mod 对象或 ID 字符串统统转为Mod对象
    let mod = null
    if(typeof modOrId === 'string') mod = takeModById(modOrId, defaultName)
    else if(modOrId?.package_id) mod = modOrId
    // 构造显示名称
    const res = mod?.alias_name || mod?.display_name || mod?.name || mod?.package_id
    return res || `⚠ ${defaultName} (${modOrId})`
  }
  // 显示 Mod 类型（优先 user_mod_type -> mod_type -> Unknown）
  const displayModType = (modOrId) => {
    // 处理输入：Mod 对象或 ID 字符串统统转为Mod对象
    let mod = null
    if(typeof modOrId === 'string') mod = takeModById(modOrId)
    else if(modOrId?.package_id) mod = modOrId
    // 构造显示类型
    const res = mod?.user_mod_type || mod?.mod_type || 'Unknown'
    return res
  }
  // 显示 Mod 图标（优先 icon_url -> thumb_url -> preview_url）
  const displayModIcon = (id) => {
    const mod = takeModById(id)
    if (mod && mod.icon_url) return mod.icon_url // 列表图标
    if (mod && mod.thumb_url) return mod.thumb_url // 缩略图
    if (mod && mod.preview_url) return mod.preview_url // 详情大图
    return '' // 返回空或默认图路径
  }

  // --- 列表数据处理 ---
  // 刷新未激活Mod列表 (实现“新Mod置顶，旧Mod持久，联锁聚拢”)
  const updateInactiveIds = () => {
    // 清理临时列表 (Temp - Active) （Temp列表 是前端的临时列表，防止与刷新后的 Active列表 出现重复项）
    const activeSet = new Set(activeIds.value)
    tempIds.value = tempIds.value.filter(id => !activeSet.has(id.toLowerCase()))
    inactiveIds.value = takeInactiveIds()
  }
  // 获取未激活Mod ID 列表 (全集 - 活跃 - 临时)
  const takeInactiveIds = () => {
    const activeSet = new Set(activeIds.value.map(id => id.toLowerCase()))
    const tempSet = new Set(tempIds.value.map(id => id.toLowerCase()))
    // 1. 获取所有没在 active 和 temp 里的 Mod
    const newMods = [] // 收集"新" Mod（未在保存的 inactive 列表中出现过）
    // 建立旧顺序的查找索引 O(1)
    const savedIndexMap = new Map()
    savedInactiveIds.value.forEach((id, idx) => savedIndexMap.set(id.toLowerCase(), idx))
    for (const mod of allModsMap.value.values()) {
      const pid = mod.package_id.toLowerCase()
      if (!activeSet.has(pid) && !tempSet.has(pid)) {
        if (!savedIndexMap.has(pid)) {
          newMods.push(mod)
        }
      }
    }
    // 2. 将 "新 Mod" 按照文件创建时间/修改时间降序排列 (最新的在最前面)
    newMods.sort((a, b) => {
      const timeA = Math.max(a.file_create_time || 0, a.file_modify_time || 0)
      const timeB = Math.max(b.file_create_time || 0, b.file_modify_time || 0)
      return timeB - timeA
    })
    const newModIds = newMods.map(m => m.package_id)
    // 3. 将 "旧 Mod" 按照 savedInactiveIds 中的原始顺序排列
    const oldModIds = savedInactiveIds.value.filter(id => {
      const pid = id.toLowerCase()
      return !activeSet.has(pid) && !tempSet.has(pid) && hasRealModById(pid)
    })
    // 4. 基础合并
    const baseInactive = [...newModIds, ...oldModIds]
    const finalInactive = []
    const processed = new Set()
    // 建立查找表提升性能
    const baseInactiveSet = new Set(baseInactive.map(id => id.toLowerCase()))
    for (const id of baseInactive) {
      const pid = id.toLowerCase()
      if (processed.has(pid)) continue

      const mod = allModsMap.value.get(pid)
      // 如果属于某个联锁序列
      if (mod && mod.interlock_id && interlocksMap.value[mod.interlock_id]) {
        const chain = interlocksMap.value[mod.interlock_id]
        // 遍历该链条，把所有属于 inactive 列表的兄弟姐妹都拉过来，按链条固有顺序排列
        for (const chainId of chain) {
          const cid = chainId.toLowerCase()
          if (baseInactiveSet.has(cid) && !processed.has(cid)) {
            // 找到原始大小写格式的 ID 并存入
            finalInactive.push(chainId)
            processed.add(cid)
          }
        }
      } else {
        // 独立 Mod，直接推入
        finalInactive.push(id)
        processed.add(pid)
      }
    }

    return finalInactive
  }
  // 批量查询未知 PackageID 并将其作为幽灵项存入 Map
  const fetchAndCacheGhostMods = async (ids = []) => {
    if (!ids || ids.length === 0 || !window.pywebview) return
    
    // 筛选出本地缺失(完全未知或本身就是 isMissing )的 ID
    const unknownIds = ids.map(id => id.toLowerCase()).filter(id => {
      const existing = allModsMap.value.get(id)
      return !existing || existing.isMissing
    })
    if (unknownIds.length === 0) return
    try {
      const res = await window.pywebview.api.get_workshop_details_by_package_ids(unknownIds)
      if (res?.status === 'success' && res.data) {
        let changed = false
        const metaMap = res.data
        unknownIds.forEach(id => {
          const meta = metaMap[id]
          // 1. 尝试获取现有对象引用，如果没有则创建一个基础对象
          let ghostMod = allModsMap.value.get(id) || { package_id: id }
          if (meta) {
            // 2. 【核心改进】：全量合并 meta 信息 (包含 author, workshop_id, preview_url, is_replacement_derived 等)
            Object.assign(ghostMod, meta)
            // 3. 强制修正/补充显示名称
            ghostMod.name = `⚠ ${meta.name || id} (${id})`
            ghostMod.display_name = meta.name
            
            changed = true
          } else if (!allModsMap.value.has(id)) {
            // 数据库也没查到，设置为最简未知幽灵
            ghostMod.name = `⚠ 未知模组 (${id})`
            changed = true
          }
          // 4. 【最后设防】：无论 meta 里有什么，强制确保这四个幽灵项核心属性不变
          ghostMod.path = null
          ghostMod.isMissing = true
          ghostMod.description = '该模组在本地未找到，可能未下载，或已被手动删除。'
          // 确保 package_id 始终是请求时的那个，防止 meta 里的 package_id 大小写不一致
          ghostMod.package_id = id 
          // 存入/更新 Map
          allModsMap.value.set(id, ghostMod)
        })
        if (changed) {
          dataVersion.value++ // 触发响应式计算
        }
      }
    } catch (e) {
      console.error("加载幽灵模组缓存信息失败:", e)
    }
  }
  // 设置 Mod 数据
  const setMods = (data) => {
    clearListHistory()
    activeIds.value = (data.active_load_order || []).map(id => id.toLowerCase())
    savedActiveIds.value = [...data.active_load_order] || []  // 保存原始顺序，用于判定排序变动
    savedInactiveIds.value = [...data.inactive_load_order] || [] // 接收持久化停用顺序
    interlocksMap.value = data.interlocks || {}             // 接收联锁字典
    activeLoadModifyTime.value = data.active_load_modify_time  // 排序文件修改时间（更新时间）
    // 创建一个 Set 用于 O(1) 快速查找
    const activeSet = new Set(activeIds.value);
    // 直接重建 Map，确保删除的 Mod 能被移除，新增的能被加入
    const tempMap = new Map()
    data.all_mods.forEach(mod => {
      // 初始化启用时间（如果 Mod 是 Active 但没有启用时间，则记录为排序文件更新时间，若仍有问题则记录为当前时间）
      if (mod.package_id && activeSet.has(mod.package_id.toLowerCase()) && !mod.last_active_time) {
        mod.last_active_time = data.active_load_modify_time || Date.now()
      }
      // 强制保证列表字段存在且格式正确
      if (!Array.isArray(mod.author) && !mod.author) mod.author = ['Unknown'] 
      if (!Array.isArray(mod.supported_versions)) mod.supported_versions = []
      if (!Array.isArray(mod.supported_languages)) mod.supported_languages = []
      if (!Array.isArray(mod.gallery_paths)) mod.gallery_paths = []
      if (!Array.isArray(mod.load_after_mods)) mod.load_after_mods = []
      if (!Array.isArray(mod.load_before_mods)) mod.load_before_mods = []
      if (!Array.isArray(mod.incompatible_mods)) mod.incompatible_mods = []
      if (!Array.isArray(mod.tags)) mod.tags = []
      if (!Array.isArray(mod.ignored_issues)) mod.ignored_issues = []
      tempMap.set(mod.package_id.toLowerCase(), mod)
    })
    allModsMap.value = tempMap
    // 重新计算 Inactive列表 (排除 Active 和 Temp)（本质上 Temp列表 与 Inactive列表 一样，但在前端分出差异方便整理）
    updateInactiveIds()
    dataVersion.value++    // 更新数据版本号（刷新标记）
    // 初始化获取完所有模组后，如果 activeIds 中存在未知项，批量缓存它们！
    fetchAndCacheGhostMods(activeIds.value)
  }
  // 重置 Mod 数据
  const reset = () => {
    clearListHistory()
    allModsMap.value.clear()
    activeIds.value = []
    inactiveIds.value = []
    tempIds.value = []
    savedActiveIds.value = []
    dataVersion.value++
  }
  // 从所有列表中移除指定 IDs
  const removeIdsOnAllList = (ids) => {
    if(typeof ids === 'string') ids = [ids]
    const lowerIdsSet = new Set(ids.map(id => id.toLowerCase()))
    activeIds.value = activeIds.value.filter(i => !lowerIdsSet.has(i))
    inactiveIds.value = inactiveIds.value.filter(i => !lowerIdsSet.has(i))
    tempIds.value = tempIds.value.filter(i => !lowerIdsSet.has(i))
  }
  // 批量启用/停用Mod
  const changeModsActive = async (ids, active) => {
    if(typeof ids === 'string') ids = [ids]
    const nextIds = Array.isArray(ids) ? [...ids] : []
    if (nextIds.length === 0) return false
    return await runListHistoryTransaction({
      type: active ? 'change-active-enable' : 'change-active-disable',
      label: active ? `启用 ${nextIds.length} 个 Mod` : `停用 ${nextIds.length} 个 Mod`,
      trackedModIds: nextIds
    }, async () => {
      removeIdsOnAllList(nextIds)
      if(active) {
        await smartInsertMods(nextIds)
      } else {
        inactiveIds.value.push(...nextIds)
      }
      takeModListByIds(nextIds).forEach(mod => {
        mod.last_moved_time = Date.now()
        mod.last_active_time = Date.now()
      })
    })
  }
  // 智能插入 Mod 到 Active 列表
  const smartInsertMods = async (ids) => {
    if (!ids || ids.length === 0) return
    if (!window.pywebview) return
    if(typeof ids === 'string') ids = [ids]
    console.log(ids)
    
    const res = await window.pywebview.api.smart_insert_mod_in_actives(ids, activeIds.value)
    if(checkResult(res, '智能插入 Mod 到 Active 列表') && res.data){
      activeIds.value = [...res.data]
    }
  }
  // 清除选择
  const clearSelection = () => {
    selectedIds.value = []
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
      // 如果这个 Mod 有 interlock_id，直接从全局字典里拿整个数组
      if (mod && mod.interlock_id && interlocksMap.value[mod.interlock_id]) {
        const chainItems = interlocksMap.value[mod.interlock_id];
        let anchorIndex = -1;
        // 遍历整个链条，找出第一个在用户点击/圈选范围内的项，作为锚点位置
        for (const chainId of chainItems) {
          const pid = chainId.toLowerCase();
          processed.add(pid); // 把整条链上的 ID 都标记为已处理
          if (anchorIndex === -1 && inputMap.has(pid)) {
            anchorIndex = inputMap.get(pid);
          }
        }
        // 加入块中
        finalChunks.push({ 
          index: anchorIndex !== -1 ? anchorIndex : i, 
          items: chainItems 
        });
      } else {
        // 普通 Mod，无联锁
        finalChunks.push({ index: i, items: [inputIds[i]] }); 
        processed.add(currentId);
      }
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

  // --- 扫描处理 ---
  // 扫描 Mod 文件
  const scanMods = async (path_list=null, forced_update=false) => {
    if (appStore.isScanRunning || !window.pywebview) return
    try {
      // 调用 API，会立即返回 { status: 'started' }
      const res = await window.pywebview.api.scan_mods(path_list, forced_update)
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
  // 扫描完成事件处理
  const scanComplete = async (detail) => {
    coexistenceList.value = Array.isArray(detail.coexistences) ? detail.coexistences : []
    conflictList.value = Array.isArray(detail.conflicts) ? detail.conflicts : []

    let totalCount = 0
    if (coexistenceList.value.length > 0) {
      if (appStore.settings.show_coexistence_message){
        console.warn("发现共存:", coexistenceList.value)
        totalCount += coexistenceList.value.length
      }
    }
    // 处理扫描结果，检测冲突提示 (包含可共存Mod)
    if (conflictList.value.length > 0) {
      console.warn("发现冲突:", conflictList.value)
      totalCount += conflictList.value.length
    }
    if (totalCount > 0) {
      // 注意：有冲突时暂不提示 "扫描完成" 的 Toast，以免遮挡，或者提示 Warning
      toast.warning(`扫描完成，发现 ${totalCount} 个包名重复冲突需要处理！`, {timeout: 10000})
    } else {
      toast.success(`扫描完成，共计扫描${detail.total}个模组，新增${detail.stats.added}个，\n更新${detail.stats.updated}个，删除${detail.stats.removed}个，已知${detail.stats.skipped}个。`,{position: "top-center",timeout: 5000})
    }
    // 扫描结束后，主动拉取一次最新数据刷新界面
    console.log("扫描统计:", detail)
    await appStore.refreshData()
    // 状态注入
    if (coexistenceList.value.length > 0){
      // 处理可共存Mod，标记为 is_coexistence = true
      coexistenceList.value.forEach(item => {
        takeModById(item.package_id)['is_coexistence'] = true
      })
    }
  }
  // 自动排序 Mod
  const autoSortMods = async (mod_ids) => {
    if (!window.pywebview) return
    // 处理空输入，默认使用当前活动项
    if (!mod_ids || mod_ids.length === 0) mod_ids = activeIds.value 
    try {
      const res = await window.pywebview.api.auto_sort_mods(mod_ids)
      if (checkResult(res, "自动排序Mod")) {
        await runListHistoryTransaction({
          type: 'auto-sort',
          label: `自动排序 ${mod_ids.length} 个 Mod`
        }, async () => {
          activeIds.value = res.data.sorted_ids || []
          updateInactiveIds()
        })
        toast.success("自动排序完成")
        // 处理警告信息
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
            console.log("自动排序警告:",warnModRule)
            let msg = '请检查以下Mod规则是否正确：\n'
            warnModRule.forEach(item => {
              msg += `${displayModName(item.mod_id)} 的 ${item.type.name} 规则 可能存在问题：（${displayModName(item.target_id)}）\n`
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
  // 创建本地共存
  const localizeSelectedMods = async (store='workshop') => {
    if (selectedIds.value.length === 0) return;
    // 过滤出选中的工坊模组（如果是本地模组则没必要转换）
    const workshopIds = selectedMods.value
      .filter(m => m.store === store)
      .map(m => m.package_id);
    if (workshopIds.length === 0) {
      toast.info("选中的模组中没有来自工坊的项");
      return;
    }
    await localizeMods(workshopIds, store)
  }
  const localizeMods = async (workshopIds, store='workshop') => {
    const confirm = await confirmStore.confirmAction(
      '本地化确认',
      `确定要将选中的 ${workshopIds.length} 个${store}模组复制到本地目录吗？\n复制后将独立占用磁盘空间，Steam / 管理器 的更新将不再影响这些本地副本。`,
      { type: 'info' }
    );
    if (confirm) {
      appStore.isLoading = true;
      const res = await window.pywebview.api.localize_workshop_mods(workshopIds, store);
      if (appStore.checkResult(res, '模组本地化')) {
        // 成功后会在完成时刷新数据
      }
      appStore.isLoading = false;
    }
  }
  const disableMods = async (path_hashs, disabled = true) => {
    if (!path_hashs || path_hashs.length === 0) return;
    if(disabled) {
      const confirm = await confirmStore.confirmAction(
        '禁用确认',
        `确定要禁用该模组吗？\n禁用后将无法在游戏中使用，直到重新启用。`,
        { type: 'warning' }
      );
      if(!confirm) return
    }
    appStore.isLoading = true;
    const res = await window.pywebview.api.mods_disable(path_hashs, disabled);
    if (appStore.checkResult(res, '禁用选中的模组')) {
      // 成功后会在完成时刷新数据
      scanMods()
    }
    appStore.isLoading = false;
  }
  // 批量删除Mod文件及数据记录
  const deleteMods = async (path_hashes) => {
    if(!window.pywebview) return
    const confirmStore = useConfirmStore()
    const confirm = await confirmStore.confirmAction(
      '删除确认', `确定要删除这 ${path_hashes.length} 个Mod吗？\n这些Mod将被移至回收站。`,
      { type: 'error' }
    );
    if(!confirm) return
    const res = await window.pywebview.api.mods_delete(path_hashes)
    scanMods()
    if (checkResult(res, "批量删除Mod")) {
      toast.success(`已删除 ${res.data.success_count} 个Mod`)
      // 刷新Mod列表
      return true
    }
  }

  // --- Mod数据操作 ---
  // 更新Mod用户数据
  const updateModUserData = async (modId, userData) => {
    if (!window.pywebview) return
    try {
      // 更新本地 Map
      const mod = allModsMap.value.get(modId.toLowerCase())
      if (mod) Object.assign(mod, userData)
      const res = await window.pywebview.api.mod_user_data_update(modId, userData)
      if (!checkResult(res, "更新Mod用户数据", true)) {
        await appStore.refreshData();
        return false
      }
      return true
    } catch (e) {
      console.error("更新Mod用户数据异常:", e)
      toast.error(`更新Mod用户数据异常: \n${e.message}`)
      await appStore.refreshData();
      return false
    }
  }
  // 更新Mod最后操作时间
  const updateModTime = async () => {
    if (!window.pywebview) return
    appStore.isLoading = true
    try {
      // 提取所有对象的时间属性 {package_id:xxxx, last_active_time:xxxx, last_moved_time:xxxx}
      const all_mods = Array.from(allModsMap.value.values(), mod => ({
        path_hash: mod.path_hash,
        package_id: mod.package_id,
        last_active_time: mod.last_active_time,
        last_moved_time: mod.last_moved_time
      }));
      console.log("更新Mod最后操作时间:", {all_mods_time:all_mods})
      const res = await window.pywebview.api.mod_time_update(all_mods)
      if (!checkResult(res, "更新Mod最后操作时间")) {
        await appStore.refreshData();
        return false
      }
      return true
    } catch (e) {
      console.error("更新Mod最后操作时间异常:", e)
      toast.error(`更新Mod最后操作时间异常: \n${e.message}`)
      await appStore.refreshData();
      return false
    }
  }

  // --- 批量数据操作 ---
  // 批量设置颜色
  const setModsColor = async (modIds, color) => {
    if (!window.pywebview) return
    try {
      // 立即更新本地状态
      modIds.forEach(id => {
        const mod = takeModById(id)
        if (mod) mod.sign_color = color
      })
      // 发送请求给后端
      const res = await window.pywebview.api.mods_sign_color_update(modIds, color)
      if (!checkResult(res, "批量设置 Mod 颜色", true)) {
        await appStore.refreshData();
        return false
      } 
      return true
    } catch (e) {
      toast.error(`批量设置颜色失败: ${e}`)
      await appStore.refreshData() 
      return false
    }
  }
  // 批量设置类型
  const setModsType = async (modIds, type) => {
    if (!window.pywebview) return
    try {
      // 立即更新本地状态
      modIds.forEach(id => {
        const mod = takeModById(id)
        if (mod) mod.user_mod_type = type
      })
      // 发送请求给后端
      const res = await window.pywebview.api.mods_user_mod_type_update(modIds, type)
      if (!checkResult(res, "批量设置 Mod 类型", true)) {
        await appStore.refreshData();
        return false
      } 
      return true
    } catch (e) {
      toast.error(`批量设置类型失败: ${e}`)
      await appStore.refreshData() 
      return false
    }
  }
  // 批量添加标签
  const addModsTags = async (modIds, tags) => {
    if (!window.pywebview) return
    try {
      // 立即更新本地状态
      modIds.forEach(id => {
        const mod = takeModById(id)
        if (mod) mod.tags = [...new Set([...(mod.tags || []), ...tags])]  // 自动去重
      })
      // 发送请求给后端
      const res = await window.pywebview.api.mods_add_tags(modIds, tags)
      if (!checkResult(res, "批量添加 Mod 标签", true)) {
        await appStore.refreshData();
        return false
      } 
      return true
    } catch (e) {
      toast.error(`批量添加标签失败: ${e}`)
      await appStore.refreshData() 
      return false
    }
  }
  // 批量移除标签
  const removeModsTags = async (modIds, tags) => {
    if (!window.pywebview) return
    try {
      // 立即更新本地状态
      modIds.forEach(id => {
        const mod = takeModById(id)
        if (mod) mod.tags = (mod.tags || []).filter(t => !tags.includes(t))
      })
      // 发送请求给后端
      const res = await window.pywebview.api.mods_remove_tags(modIds, tags)
      if (!checkResult(res, "批量移除 Mod 标签", true)) {
        await appStore.refreshData();
        return false
      } 
      return true
    } catch (e) {
      toast.error(`批量移除标签失败: ${e}`)
      await appStore.refreshData() 
      return false
    }
  }
  // 智能切换标签
  // 如果所有选中项都有该 Tag -> 移除，如果部分有或都没有 -> 添加 (补全)
  const selectModsTag = async (tag) => {
    // 检查当前状态
    const stats = selectedStats.value.tags[tag] // 'all', 'some', undefined
    if (stats === 'all') {  // 全都有 -> 移除
      await removeModsTags(selectedIds.value, [tag]) // 需实现 removeModsTags
    } else {  // 部分有或全无 -> 添加
      await addModsTags(selectedIds.value, [tag])
    }
  }
  // 智能切换分组 (Toggle Group)
  const selectModsGroup = async (groupId) => {
    const stats = selectedStats.value.groups[groupId]
    const groupStore = useGroupStore()
    if (stats === 'all') {
      await groupStore.groupRemoveMods(groupId, selectedIds.value)
    } else {
      await groupStore.groupAddMods(groupId, selectedIds.value)
    }
  }
  // 获取 Mod 联锁链
  const getModInterlockChain = (modId) => {
    const mod = takeModById(modId);
    if (!mod || !mod.interlock_id) return null;
    return interlocksMap.value.get(mod.interlock_id) || null;
  }
  // 批量设置 Mod 联锁
  const linkMods = async (modIds) => {
    if (!window.pywebview) return
    try {
      // 发送请求给后端
      const res = await window.pywebview.api.mods_link(modIds)
      if (checkResult(res, "设置 Mod 联锁", true)) {
        await appStore.refreshData();
        dataVersion.value++ // 数据版本+1，确保问题判断刷新
        return true
      }
    } catch (e) {
      console.error("设置 Mod 联锁异常:", e)
      toast.error(`设置 Mod 联锁异常: \n${e.message}`)
      return false
    }
  }
  // 批量解除 Mod 联锁
  const unlinkMods = async (modIds) => {
    if (!window.pywebview) return
    try {
      const res = await window.pywebview.api.mods_unlink(modIds)
      if (checkResult(res, "解除 Mod 联锁", true)) {
        await appStore.refreshData();
        dataVersion.value++ // 数据版本+1，确保问题判断刷新
        return true
      } 
    } catch (e) {
      return false
    }
  }
  // 修复断裂联锁
  const healInterlock = async (interlock_id) => {
    if (!window.pywebview || !interlock_id) return
    appStore.isLoading = true
    try {
      const res = await window.pywebview.api.mods_interlock_heal(interlock_id)
      if (checkResult(res, "修复断裂联锁", true)) {
        await appStore.refreshData(); // 全局刷新数据
        return true
      }
    } finally {
      appStore.isLoading = false
    }
  }
  // 获取断裂联锁的缺失成员
  const getInterlockMissingDetails = async (interlock_id) => {
    if (!window.pywebview || !interlock_id) return []
    try {
      const res = await window.pywebview.api.mods_interlock_missing_get(interlock_id)
      if (checkResult(res, "获取联锁缺失项")) return res.data
    } catch (e) {
      console.error("获取联锁缺失项失败:", e)
    }
    return []
  }
  // 批量更新Mod用户数据
  const batchUpdateModsUserData = async (updatesList) => {
    if (!window.pywebview) return
    appStore.isLoading = true
    try {
      // 1. 乐观更新：立即更新本地 Map 状态
      updatesList.forEach(u => {
        const mod = allModsMap.value.get(u.mod_id.toLowerCase())
        if (mod) {
          Object.assign(mod, u)
        }
      })
      // 2. 发送请求给后端
      const res = await window.pywebview.api.mods_user_data_update(updatesList)
      if (!checkResult(res, "批量更新Mod数据", true)) {
        await appStore.refreshData()
        return false
      }
      return true
    } catch (e) {
      console.error("批量更新Mod数据异常:", e)
      toast.error(`批量更新失败: \n${e.message}`)
      await appStore.refreshData()
      return false
    } finally {
      appStore.isLoading = false
      dataVersion.value++ // 触发响应式重新计算
    }
  }

  const interlockDetailsMap = ref({}) // { "interlock_id": [ {package_id, workshop_id, reason} ] }
  const loadingInterlocks = new Set() // 记录当前正在请求中的 ID，防止并发风暴
  const loadInterlockDetails = async (interlockId) => {
    if (!interlockId || !window.pywebview) return
    // 1. 如果已经缓存过，直接返回
    if (interlockDetailsMap.value[interlockId]) return
    // 2. 如果当前正在请求中，直接屏蔽
    if (loadingInterlocks.has(interlockId)) return

    loadingInterlocks.add(interlockId)
    try {
      const res = await window.pywebview.api.mods_interlock_missing_get(interlockId)
      if (res.status === 'success') {
        interlockDetailsMap.value[interlockId] = res.data
        dataVersion.value++ // 驱动视图层重绘
      }
    } catch (e) {
      console.error("加载联锁详情失败:", e)
    } finally {
      loadingInterlocks.delete(interlockId) // 请求结束，释放锁
    }
  }
  // --- 实时问题分析 ---
  // 排序问题检测器
  const modIssues = computed(() => {
    const issuesMap = new Map() // Key: modId, Value: Array<Issue>
    dataVersion.value // 依赖触发器
    const profileStore = useProfileStore()

    // 辅助函数：添加问题
    const _add = (id, type, level, message, targetId = null) => {
      const mod = takeModById(id)
      if (!mod) return
      // 忽略检查
      if (mod.ignored_issues && mod.ignored_issues.includes(type)) return
      if (!issuesMap.has(id)) issuesMap.set(id, [])
      issuesMap.get(id).push({ type, level, message, targetId })
    }

    // -------------------------------------------------
    // 1. 全局检查 (Global Checks) - 针对每个个体
    // 范围：所有已加载的 Mod (无论是否启用)
    // -------------------------------------------------
    for (const mod of allModsMap.value.values()) {
      const id = mod.package_id.toLowerCase()

      // A. 文件缺失
      if (!mod.path || mod.isMissing) {
        _add(id, ISSUE_TYPE.ERROR_MISSING_FILE, ISSUE_LEVEL.ERROR, '本地文件缺失或无法解析', id)
        continue // 文件都没了，没必要查别的
      }

      // B. 版本支持检查
      if (profileStore.activeContext.game_version) {
        const gameVerMajor = profileStore.activeContext.game_version.substring(0, 3)
        if (mod.supported_versions && mod.supported_versions.length > 0 && !mod.supported_versions.includes(gameVerMajor)) {
          _add(id, ISSUE_TYPE.WARN_VERSION_MISMATCH, ISSUE_LEVEL.WARN, 
            `^^${ISSUE_TITLE_MAP[ISSUE_TYPE.WARN_VERSION_MISMATCH]}^^：不支持当前游戏版本··[[${gameVerMajor}]]·· \n __(支持: ··${(mod.supported_versions || []).join('··, ··')}··)__`)
        }
      }
    }

    // 1.5 预处理语言包映射 (Language Packs Mapping)
    // 如果用户开启了语言检测，提前找出所有语言包并映射到它们的目标 Mod
    const checkLangEnabled = appStore.settings.check_language_support
    const targetLang = appStore.settings.language // 当前软件语言 (例如 'zh-cn', 'ChineseSimplified' 等)
    const langPackMap = new Map() // 数据结构: { targetModId: [ LangPackMod1, LangPackMod2 ] }
    if (checkLangEnabled && targetLang) {
      for (const mod of allModsMap.value.values()) {
        const isLangPack = (mod.user_mod_type || mod.mod_type) === 'LanguagePack'
        // 匹配语言 (忽略大小写)
        const supportsLang = mod.supported_languages?.some(l => l.toLowerCase() === targetLang.toLowerCase())
        if (isLangPack && supportsLang) {
          // 获取该语言包所指向的目标 Mod (通常在依赖或 load_after 中)
          const rules = mod.rules || { dependencies: [], load_after: [] }
          const targetIds = new Set()
          rules.dependencies?.forEach(d => targetIds.add(d.target_id.toLowerCase()))
          rules.load_after?.forEach(r => targetIds.add(r.target_id.toLowerCase()))
          targetIds.forEach(tId => {
            if (!langPackMap.has(tId)) langPackMap.set(tId, [])
            langPackMap.get(tId).push(mod)
          })
        }
      }
    }

    // -------------------------------------------------
    // 2. 启用列表检查 (Active List Checks)
    // 范围：activeIds 列表
    // -------------------------------------------------
    // 构建 Map 以实现 O(1) 查找 active 列表中的索引
    const activeIndexMap = new Map()
    const len = activeIds.value.length
    for (let i = 0; i < len; i++) {
        activeIndexMap.set(activeIds.value[i].toLowerCase(), i)
    }
    // 快速判定任意两个 Mod 之间的合法顺序
    // isMustBefore.get(A)?.has(B) 为 true，表示规则要求 A 必须在 B 之前
    const isMustBefore = new Map() 
    const addMustBeforeRule = (beforeId, afterId) => {
        if (!isMustBefore.has(beforeId)) isMustBefore.set(beforeId, new Set())
        isMustBefore.get(beforeId).add(afterId)
    }
    for (let i = 0; i < len; i++) {
        const currentId = activeIds.value[i].toLowerCase()
        const mod = takeModById(currentId)
        if (!mod || mod.isMissing || !mod.rules) continue
        const rules = mod.rules || {}
        // 我必须在别人之后 -> 别人必须在我之前
        const afterTargets = [...(rules.load_after || []), ...(rules.dependencies || [])]
        afterTargets.forEach(r => {
            const tid = r.target_id.toLowerCase()
            addMustBeforeRule(tid, currentId) // tid 必须在 currentId 之前
        })
        // 我必须在别人之前 -> 我必须在别人之前
        const beforeTargets = rules.load_before || []
        beforeTargets.forEach(r => {
            const tid = r.target_id.toLowerCase()
            addMustBeforeRule(currentId, tid) // currentId 必须在 tid 之前
        })
    }
    
    for (let i = 0; i < len; i++) {
      const currentId = activeIds.value[i].toLowerCase()
      const mod = takeModById(currentId)
      if (!mod || mod.isMissing) continue // X. 文件缺失已在全局检查中处理，这里简单跳过
      if(!mod.rules) continue // 如果没有 rules 数据（可能未初始化），跳过

      // const rules = mod.rules ，这是后端计算好的 { dependencies, load_after, incompatible ... }
      // 兼容性处理：如果后端还没刷新，rules可能为空
      const rules = mod.rules || { dependencies: [], load_after: [], load_before: [], incompatible: [] }

      const wInfo = rules.weight_info || {}
      // 直接使用后端统一提供的 final_weight，兜底为 500
      const finalWeight = wInfo.final_weight !== undefined ? wInfo.final_weight : 500
      const sourceName = wInfo.absolute_source || '未知规则'
      
      // 1. 置顶检查 (<= 0)
      if (finalWeight <= 0 && i > 0) { // 只检查非首位元素
        const prevId = activeIds.value[i - 1].toLowerCase()
        const prevMod = takeModById(prevId)
        const prevW = prevMod?.rules?.weight_info?.final_weight ?? 500
        // 如果紧邻的前一个模组不是置顶的
        if (prevW > 0) {
          // 【关键豁免】：检查是否存在规则要求 prevId 必须在 currentId 之前
          const isAllowedByRule = isMustBefore.get(prevId)?.has(currentId)
          if (!isAllowedByRule) {
            _add(currentId, ISSUE_TYPE.WARN_WRONG_ORDER, ISSUE_LEVEL.WARN, 
              `^^排序警告^^：根据 ${sourceName} 要求置顶，但被排在了非前置依赖的常规模组 [[${displayModName(prevId)}]] 之后`, prevId)
          }
        }
      }
      // 2. 置底检查 (>= 10000)
      if (finalWeight >= 10000 && i < len - 1) { // 只检查非末位元素
        const nextId = activeIds.value[i + 1].toLowerCase()
        const nextMod = takeModById(nextId)
        const nextW = nextMod?.rules?.weight_info?.final_weight ?? 500
        // 如果紧邻的后一个模组不是置底的
        if (nextW < 10000) {
          // 【关键豁免】：检查是否存在规则要求 currentId 必须在 nextId 之前
          const isAllowedByRule = isMustBefore.get(currentId)?.has(nextId)
          if (!isAllowedByRule) {
            _add(currentId, ISSUE_TYPE.WARN_WRONG_ORDER, ISSUE_LEVEL.WARN, 
              `^^排序警告^^：根据 ${sourceName} 要求置底，但前方拦截了非后置依赖的常规模组 [[${displayModName(nextId)}]]`, nextId)
          }
        }
      }

      // 记录已经作为“硬依赖”处理过的目标
      const processedDependencies = new Set()

      // A. 依赖检查 (Dependencies) - 必须存在且启用
      // 这里的 rules.dependencies 来源于 Native (About.xml)
      for (const dep of rules.dependencies || []) {
        const baseTargetId = dep.target_id.toLowerCase()
        let activeTargetId = baseTargetId
        let usedAlternative = null

        // 1. 检查基础目标是否激活
        if (!activeIndexMap.has(baseTargetId)) {
          // 寻找是否有被激活的备选项 (Alternatives)
          const alts = dep.alternatives || []
          usedAlternative = alts.find(alt => activeIndexMap.has(alt.toLowerCase()))

          if (usedAlternative) {
            activeTargetId = usedAlternative.toLowerCase()
            // 提示备选项生效 (仅作 INFO 级提示，不报红错)
            const baseName = displayModName(baseTargetId)
            const altName = displayModName(activeTargetId)
            _add(currentId, ISSUE_TYPE.INFO_ALTERNATIVE_USED, ISSUE_LEVEL.INFO, 
              `__${ISSUE_TITLE_MAP[ISSUE_TYPE.INFO_ALTERNATIVE_USED]}__：前置依赖 [[${baseName}]] 已由备选模组 [[${altName}]] 替代`, activeTargetId)
          } else {
            // 缺失或未启用
            const baseMod = allModsMap.value.get(baseTargetId)
            const baseName = baseMod ? displayModName(baseMod) : baseTargetId
            
            if (!baseMod) {
              // 主包不在本地，找找备选包在不在本地！
              const localAlt = alts.find(alt => hasRealModById(alt))
              if (localAlt) {
                _add(currentId, ISSUE_TYPE.ERROR_INACTIVE_DEPENDENCY, ISSUE_LEVEL.ERROR, 
                  `!!${ISSUE_TITLE_MAP[ISSUE_TYPE.ERROR_INACTIVE_DEPENDENCY]}!!：未启用备选前置模组 [[${displayModName(localAlt)}]]`, localAlt.toLowerCase())
              } else {
                // 全都不在本地，彻底缺失
                _add(currentId, ISSUE_TYPE.ERROR_MISSING_DEPENDENCY, ISSUE_LEVEL.ERROR, 
                  `!!${ISSUE_TITLE_MAP[ISSUE_TYPE.ERROR_MISSING_DEPENDENCY]}!!：缺少前置模组 [[${baseName}]]`, baseTargetId)
              }
            } else {
              _add(currentId, ISSUE_TYPE.ERROR_INACTIVE_DEPENDENCY, ISSUE_LEVEL.ERROR, 
                `!!${ISSUE_TITLE_MAP[ISSUE_TYPE.ERROR_INACTIVE_DEPENDENCY]}!!：未启用前置模组 [[${baseName}]]`, baseTargetId)
            }
            continue // 基础依赖和备选依赖都没满足，不用查排序了
          }
        }

        // 2. 标记已处理，防止被下方的 load_after 重复检查
        processedDependencies.add(activeTargetId)
        
        // 3. 排序检查：依赖项必须在当前 Mod 之前
        if (activeIndexMap.get(activeTargetId) > i) {
          _add(currentId, ISSUE_TYPE.WARN_WRONG_ORDER, ISSUE_LEVEL.ERROR, 
            `!!依赖后置!!：必须在依赖 [[${displayModName(activeTargetId)}]] 之后加载`, activeTargetId)
        }
      }

      // B. 排序规则 (Load After) - 仅当目标存在且激活时检查
      for (const rule of rules.load_after || []) {
        const targetId = rule.target_id.toLowerCase()
        if (processedDependencies.has(targetId)) continue
        if (!activeIndexMap.has(targetId)) continue
        
        const targetName = displayModName(targetId)
        const sourceName = rule.source?.name || '未知规则'
        const level = rule.is_force ? ISSUE_LEVEL.ERROR : ISSUE_LEVEL.WARN
        const prefix = rule.is_force ? '!!排序错误!!' : '^^排序警告^^'
        
        if (activeIndexMap.get(targetId) > i) {
          _add(currentId, ISSUE_TYPE.WARN_WRONG_ORDER, level, 
            `${prefix}：根据 __${sourceName}__，应在 [[${targetName}]] 之后加载`, targetId)
        }
      }

      // C. 排序规则 (Load Before) - 仅当目标存在且激活时检查
      for (const rule of rules.load_before || []) {
        const targetId = rule.target_id.toLowerCase()
        if (processedDependencies.has(targetId)) continue
        if (!activeIndexMap.has(targetId)) continue
        
        const targetName = displayModName(targetId)
        const sourceName = rule.source?.name || '未知规则'
        const level = rule.is_force ? ISSUE_LEVEL.ERROR : ISSUE_LEVEL.WARN
        const prefix = rule.is_force ? '!!排序错误!!' : '^^排序警告^^'
        
        if (activeIndexMap.get(targetId) < i) {
          _add(currentId, ISSUE_TYPE.WARN_WRONG_ORDER, level, 
            `${prefix}：根据 __${sourceName}__，应在 [[${targetName}]] 之前加载`, targetId)
        }
      }

      // D. 冲突检查 (Incompatible) - 目标存在且激活即报错
      for (const rule of rules.incompatible || []) {
        const targetId = rule.target_id.toLowerCase()
        if (activeIndexMap.has(targetId)) {
          const targetName = displayModName(targetId)
          const sourceName = rule.source?.name || '未知规则'
          const extra = rule.source?.detail?.comment ? ` (${rule.source.detail.comment})` : ''
          _add(currentId, ISSUE_TYPE.ERROR_INCOMPATIBLE, ISSUE_LEVEL.ERROR, 
            `!!${ISSUE_TITLE_MAP[ISSUE_TYPE.ERROR_INCOMPATIBLE]}!!：__${sourceName}__ 指出与 [[${targetName}]] 不兼容${extra}`, targetId)
        }
      }

      // E. 联锁检查 (Chain Check - Active)
      // 检查当前列表的前后是否符合 lock 要求
      // if (mod.interlock_id && interlocksMap.value[mod.interlock_id]) {
      //   const chain = interlocksMap.value[mod.interlock_id]
      //   // 查找自己在这个联锁链条中的位置
      //   const myChainIndex = chain.findIndex(id => id.toLowerCase() === currentId)
      //   if (myChainIndex !== -1) {
      //     // 检查前一个
      //     if (myChainIndex > 0) {
      //       const prevExpected = chain[myChainIndex - 1].toLowerCase()
      //       if (i === 0 || activeIds.value[i - 1].toLowerCase() !== prevExpected) {
      //         _add(currentId, ISSUE_TYPE.WARN_LINK_WRONG_ORDER, ISSUE_LEVEL.WARN, 
      //           `^^联锁断裂^^：必须紧跟在 [[${displayModName(prevExpected)}]] 之后`, prevExpected)
      //       }
      //     }
      //     // 检查后一个
      //     if (myChainIndex < chain.length - 1) {
      //       const nextExpected = chain[myChainIndex + 1].toLowerCase()
      //       if (i === len - 1 || activeIds.value[i + 1].toLowerCase() !== nextExpected) {
      //         _add(currentId, ISSUE_TYPE.WARN_LINK_WRONG_ORDER, ISSUE_LEVEL.WARN, 
      //           `^^联锁断裂^^：必须紧接 [[${displayModName(nextExpected)}]] 之前`, nextExpected)
      //       }
      //     }
      //   }
      // }

      // F. 语言支持检查 (Language Support) - 仅当开关开启时
      if (checkLangEnabled && targetLang) {
        const isSelfLangPack = (mod.user_mod_type || mod.mod_type) === 'LanguagePack'
        // 如果 Mod 本身就没有声明支持的语言列表（通常意味着没有文本或是框架），直接跳过检查
        if (!mod.supported_languages || mod.supported_languages.length === 0) {
          // pass
        } else {
          // 检查自身是否直接支持当前语言
          const modSupportsLang = mod.supported_languages?.some(l => l.toLowerCase() === targetLang.toLowerCase())
          // 如果自身不支持，且自身不是语言包本体
          if (!modSupportsLang && !isSelfLangPack) {
            const availablePacks = langPackMap.get(currentId) || []
            // 检查是否有被激活的适配语言包
            const activePack = availablePacks.find(p => activeIndexMap.has(p.package_id.toLowerCase()))
            if (!activePack) {
              // 没有被激活的语言包！检查本地是否有未激活的
              if (availablePacks.length > 0) {
                const localPack = availablePacks[0] // 取第一个本地找到的语言包
                const packName = displayModName(localPack.package_id)
                _add(currentId, ISSUE_TYPE.WARN_INACTIVE_LANGUAGE_PACK, ISSUE_LEVEL.WARN,
                  `^^${ISSUE_TITLE_MAP[ISSUE_TYPE.WARN_INACTIVE_LANGUAGE_PACK]}^^：不支持当前语言，但本地存在语言包 [[${packName}]]`, localPack.package_id.toLowerCase())
              } else {
                // 本地彻底没有相关语言包
                _add(currentId, ISSUE_TYPE.WARN_MISSING_LANGUAGE, ISSUE_LEVEL.WARN,
                  `^^${ISSUE_TITLE_MAP[ISSUE_TYPE.WARN_MISSING_LANGUAGE]}^^：不支持当前语言，且未在本地发现相关语言包`)
              }
            }
          } // 自身是语言包，检查是否存在前置或依赖，且目标Mod是否启用
          else if(isSelfLangPack) {
            // 检查是否存在依赖或前置，如果都不存在，提示语言包指向对象未知，用户可手动指定前置对象
            const modDependencies = mod.rules.dependencies?.map(d => d.target_id.toLowerCase()) || []
            const modLoadAfter = mod.rules.load_after?.map(d => d.target_id.toLowerCase()) || []
            const allRelatedModIds = [...modDependencies, ...modLoadAfter]
            if(allRelatedModIds.length === 0) {
              _add(currentId, ISSUE_TYPE.WARN_UNKNOWN_TARGET, ISSUE_LEVEL.WARN,
                `^^${ISSUE_TITLE_MAP[ISSUE_TYPE.WARN_UNKNOWN_TARGET]}^^：语言包指向对象未知，请检查该语言包是否多余，或者可在规则编辑器手动指定前置对象`)
            }
            // 如果存在依赖或前置，检测是否有任意一个启用(部分语言包支持多个Mod，只要有一个启用即可)，
            // 如果未启用则提示用户存在多余的语言包，或者提示指向对象未启用
            else {
              const anyActive = allRelatedModIds.some(id => activeIndexMap.has(id))
              if(!anyActive) {
                _add(currentId, ISSUE_TYPE.WARN_INACTIVE_TARGET, ISSUE_LEVEL.WARN,
                  `^^${ISSUE_TITLE_MAP[ISSUE_TYPE.WARN_INACTIVE_TARGET]}^^：语言包指向对象未启用，请检查该语言包是否多余，或者可在规则编辑器手动指定前置对象`)
              }
            }

          }
        }
      }

    }

    

    // 辅助：检查整个列表的联锁
    const _checkListChain = (list) => {
      const len = list.length
      for (let i = 0; i < len; i++) {
        const id = list[i].toLowerCase()
        const mod = allModsMap.value.get(id)
        if (mod && mod.interlock_id && interlocksMap.value[mod.interlock_id]) {
          const chain = interlocksMap.value[mod.interlock_id]
          const myIdx = chain.findIndex(cid => cid.toLowerCase() === id)
          if (myIdx !== -1) {
            // A. 检查向上断裂 (期待的前一个元素不在我紧挨着的上方)
            if (myIdx > 0) {
              const prevExpected = chain[myIdx - 1].toLowerCase()
              if (i === 0 || list[i-1].toLowerCase() !== prevExpected) {
                // targetId 传入 prevExpected，方便组件识别这是 "前驱断裂"
                _add(id, ISSUE_TYPE.WARN_LINK_WRONG_ORDER, ISSUE_LEVEL.WARN, 
                  `^^联锁断裂^^：必须紧跟在 [[${displayModName(prevExpected)}]] 之后`, prevExpected)
              }
            }
            // B. 检查向下断裂 (期待的后一个元素不在我紧挨着的下方)
            if (myIdx < chain.length - 1) {
              const nextExpected = chain[myIdx + 1].toLowerCase()
              if (i === len - 1 || list[i+1].toLowerCase() !== nextExpected) {
                // targetId 传入 nextExpected，方便组件识别这是 "后继断裂"
                _add(id, ISSUE_TYPE.WARN_LINK_WRONG_ORDER, ISSUE_LEVEL.WARN, 
                  `^^联锁断裂^^：必须紧接 [[${displayModName(nextExpected)}]] 之前`, nextExpected)
              }
            }
          }
        }
      }
    }
    // -------------------------------------------------
    // 3. 停用列表/临时列表 (Inactive/Temp Checks)
    // 范围：仅检查联锁完整性
    // -------------------------------------------------
    _checkListChain(activeIds.value)
    _checkListChain(inactiveIds.value)
    _checkListChain(tempIds.value)
    return issuesMap
  })


  // 获取问题项目目标ID
  const getIssusTargetIds = (targetIds, issueType) => {
    const toActivate = new Set()
    targetIds.forEach(id => {
      const issues = modIssues.value.get(id.toLowerCase())
      if (issues) {
        issues.forEach(issue => {
          if (issue.type === issueType && issue.targetId) {
            toActivate.add(issue.targetId)
          }
        })
      }
    })
    return Array.from(toActivate)
  }
  // 提取当前列表所有未启用的有效依赖项 ID
  const getMissingLocalDependencies = (targetIds) => {
    const toActivate = new Set()
    targetIds.forEach(id => {
      const issues = modIssues.value.get(id.toLowerCase())
      if (issues) {
        issues.forEach(issue => {
          if (issue.type === ISSUE_TYPE.ERROR_INACTIVE_DEPENDENCY && issue.targetId) {
            toActivate.add(issue.targetId)
          }
        })
      }
    })
    return Array.from(toActivate)
  }
  // 提取当前列表所有未启用的有效语言包 ID
  const getMissingLanguagePacks = (targetIds) => {
    const toActivate = new Set()
    targetIds.forEach(id => {
      const issues = modIssues.value.get(id.toLowerCase())
      if (issues) {
        issues.forEach(issue => {
          if (issue.type === ISSUE_TYPE.WARN_INACTIVE_LANGUAGE_PACK && issue.targetId) {
            toActivate.add(issue.targetId)
          }
        })
      }
    })
    return Array.from(toActivate)
  }
  // 获取某个 Mod 问题的最高级别
  const getModIssueState = (id) => {
    const issues = modIssues.value.get(id.toLowerCase())
    if (!issues || issues.length === 0) return null
    // 优先级: ERROR > WARN > INFO
    if (issues.some(i => i.level === 'error')) return 'error'
    if (issues.some(i => i.level === 'warn')) return 'warn'
    if (issues.some(i => i.level === 'info')) return 'info'
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
      mod.ignored_issues = currentIgnored
      const res = await updateModUserData(modId, { ignored_issues: currentIgnored })
      if (res.status !== 'success') {
        toast.error(`忽略问题失败：${res.message}`)
      } else{
        dataVersion.value++ // 数据版本+1，确保问题判断刷新
      }
  }
  // 批量忽略/取消忽略问题
  const batchIgnoreIssues = async (modIds, type = null) => {
    if (!window.pywebview) return
    appStore.isLoading = true;
    const updates = []; // 准备发送给后端的批量数据
    try {
      modIds.forEach((id) => {
        const mod = takeModById(id);
        if (!mod || !mod.path) return;
        let currentIgnored = Array.isArray(mod.ignored_issues) ? [...mod.ignored_issues] : [];
        let needsUpdate = false;
        if (!type) {
          // - 模式 A: 恢复所有警告
          if (currentIgnored.length > 0) {
            currentIgnored = [];
            needsUpdate = true;
          }
        } else {
          // - 模式 B: 忽略特定问题
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
      const res = await window.pywebview.api.mods_ignore_issues_update(updates);
      if (checkResult(res, "批量忽略/取消忽略问题")) {
        toast.success(type ? `已忽略 ${updates.length} 项问题` : `已恢复 ${updates.length} 项警告`);
      } else {
        await appStore.refreshData();
      }
    } catch (e) {
      console.error("批量忽略操作失败:", e);
      toast.error(`操作失败: ${e.message}`);
      // 如果失败了，重新刷新列表以保证数据一致性
      await appStore.refreshData();
    } finally {
      appStore.isLoading = false;
      dataVersion.value++ // 数据版本+1，确保问题判断刷新
    }
  }
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
      infoCount: 0,  // 提示数
      stats: {}      // 动态存放 { [type]: [modId1, modId2...] }
    }
    // 3. 遍历统计
    targetIds.forEach(id => {
      const issues = modIssues.value.get(id.toLowerCase())
      if (!issues || issues.length === 0) return
      // result.count += issues.length // 累加总问题数
      result.count++  // 累加出问题的Mod数
      // 统计严重程度 (只要有一个 error 就算 error 级)
      if (issues.some(i => i.level === 'error')) result.errorCount++
      else result.warnCount++
      // 按类型聚合 Mod 名称，统计所有出现的错误类型
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
  

  return {
    // State
    allModsMap, dataVersion, inactiveIds, tempIds, activeIds, interlocksMap, savedInactiveIds, interlockDetailsMap, 
    savedActiveIds, activeLoadModifyTime, conflictList, coexistenceList,
    selectedIds, lastSelectedMod, currentTargetId, 
    listHistoryUndoStack, listHistoryRedoStack, isApplyingListHistory,

    // Getters
    isDirty, selectedMods, selectedStats, allModTags, modIssues, allModWorkshopIds, allModPackageIds,
    listHistoryTotal, listHistoryPosition,
    canUndoListHistory, canRedoListHistory,

    // Actions
    setMods, reset, takeModById, hasRealModById, takeModListByIds, displayModName, displayModType, displayModIcon, fetchAndCacheGhostMods,
    updateInactiveIds, takeInactiveIds, setListIds, removeIdsOnAllList, selectMods, clearSelection, changeModsActive, getModInterlockChain, loadInterlockDetails,
    scanMods, scanComplete, autoSortMods, localizeSelectedMods, localizeMods, disableMods, deleteMods, smartInsertMods,
    updateModUserData, updateModTime, linkMods, unlinkMods, healInterlock, getInterlockMissingDetails, batchUpdateModsUserData,
    setModsColor, setModsType, addModsTags, removeModsTags, selectModsTag, selectModsGroup, 
    getModIssueState, ignoreIssue, batchIgnoreIssues, getListIssues, getIssusTargetIds, getMissingLocalDependencies, getMissingLanguagePacks, 
    clearListHistory, runListHistoryTransaction, recordListHistory, undoListHistory, redoListHistory,
  }
})
