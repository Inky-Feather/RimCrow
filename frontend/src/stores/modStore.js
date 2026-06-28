import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { createToastInterface } from 'vue-toastification'
import { useAppStore } from './appStore'
import { useGroupStore } from './groupStore'
import { ISSUE_LEVEL, ISSUE_TYPE, ISSUE_TITLE_MAP } from '../utils/constants'
import { useConfirmStore } from './confirmStore'

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
  
  const savedActiveIds = ref([])      // 原始已激活列表快照（用于判断 列表变化）
  const activeLoadModifyTime = ref(0) // 已激活列表最后修改时间戳

  const conflictList = ref([])        // 重复包名冲突列表
  const coexistenceList = ref([])     // 共存Mod列表
  
  // 选择状态
  const selectedIds = ref([])         // 已选中的 Mod ID
  const lastSelectedMod = ref(null)   // 最后选中的 Mod 对象
  const currentTargetId = ref('')     // 当前目标 ID (查找定位用)

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


  // === Actions ===
  // 获取 Mod 对象
  const takeModById = (id, defaultName = '未知模组') => {
    if (!id) return null
    const lowerId = id.toLowerCase()
    if (allModsMap.value.has(lowerId)) return allModsMap.value.get(lowerId)
    // 构造缺失模组的“幽灵对象”
    return {
      package_id: id,
      name: `⚠ ${defaultName} (${id})`,
      is_missing: true,
      description: '该模组在本地未找到，可能未下载，或已被手动删除。'
    }
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
  // 刷新未激活Mod列表
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
  // 设置 Mod 数据
  const setMods = (data) => {
    activeIds.value = (data.active_load_order || []).map(id => id.toLowerCase())
    savedActiveIds.value = [...data.active_load_order] || []  // 保存原始顺序，用于判定排序变动
    activeLoadModifyTime.value = data.active_load_modify_time  // 排序文件修改时间（更新时间）
    
    // 直接重建 Map，确保删除的 Mod 能被移除，新增的能被加入
    const tempMap = new Map()
    data.all_mods.forEach(mod => {
      // 初始化启用时间（如果 Mod 是 Active 但没有启用时间，则记录为排序文件更新时间，若仍有问题则记录为当前时间）
      if (mod.package_id && activeIds.value.includes(mod.package_id.toLowerCase()) && !mod.last_active_time) {
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
  }
  // 重置 Mod 数据
  const reset = () => {
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
      // - 情况 A: 独立 Mod (无联锁)
      // 快速路径，无需图遍历
      if (!mod || (!mod.lock_previous_mod && !mod.lock_next_mod)) {
        finalChunks.push({ index: i, items: [inputIds[i]] }); // 保持原ID大小写
        processed.add(currentId);
        continue;
      }
      // - 情况 B: 联锁 Mod
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
        const originalInputId = inputIds[inputMap.get(curr)];
        chainItems.push(originalInputId || curr); // 优先用输入列表里的原始格式
        // 【核心逻辑】：寻找锚点
        // 从头到尾遍历链条，使用遇到的第一个“在输入列表中存在”的成员的位置作为锚点。
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

  // --- 扫描处理 ---
  // 扫描 Mod 文件
  const scanMods = async (path) => {
    if (appStore.scanProgress.scanning || !window.pywebview) return
    try {
      const paths = path ? [path] : null
      // 调用 API，会立即返回 { status: 'started' }
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
  // 扫描完成事件处理
  const scanComplete = async (detail) => {
    let totalCount = 0
    if (detail.coexistences && detail.coexistences.length > 0) {
      coexistenceList.value = detail.coexistences
      if (appStore.settings.show_coexistence_message){
        console.warn("发现共存:", detail.coexistences)
        totalCount += detail.coexistences.length
      }
    }
    // 处理扫描结果，检测冲突提示 (包含可共存Mod)
    if ((detail.conflicts && detail.conflicts.length > 0)) {
      console.warn("发现冲突:", detail.conflicts)
      conflictList.value = detail.conflicts
      totalCount += detail.conflicts.length
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
        activeIds.value = res.data.sorted_ids || []
        updateInactiveIds()
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
  // 创建本地共存
  const localizeSelectedMods = async () => {
    if (selectedIds.value.length === 0) return;
    // 过滤出选中的工坊模组（如果是本地模组则没必要转换）
    const workshopIds = selectedMods.value
      .filter(m => m.source === 'workshop')
      .map(m => m.package_id);
    if (workshopIds.length === 0) {
      toast.info("选中的模组中没有来自工坊的项");
      return;
    }
    const confirm = await confirmStore.confirmAction(
      '本地化确认',
      `确定要将选中的 ${workshopIds.length} 个工坊模组复制到本地目录吗？\n复制后将独立占用磁盘空间，Steam 的更新将不再影响这些本地副本。`,
      { type: 'info' }
    );
    if (confirm) {
      appStore.isLoading = true;
      const res = await window.pywebview.api.localize_workshop_mods(workshopIds);
      if (appStore.checkResult(res, '模组本地化')) {
        // 成功后会在完成时刷新数据
      }
      appStore.isLoading = false;
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
      const res = await window.pywebview.api.update_mod_user_data(modId, userData)
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
        package_id: mod.package_id,
        last_active_time: mod.last_active_time,
        last_moved_time: mod.last_moved_time
      }));
      console.log("更新Mod最后操作时间:", {all_mods_time:all_mods})
      const res = await window.pywebview.api.update_mod_time(all_mods)
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
      const res = await window.pywebview.api.set_mods_color(modIds, color)
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
      const res = await window.pywebview.api.set_user_mods_type(modIds, type)
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
      const res = await window.pywebview.api.add_tags_to_mods(modIds, tags)
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
      const res = await window.pywebview.api.remove_tags_from_mods(modIds, tags)
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
  // 批量设置 Mod 联锁
  const linkMods = async (modIds) => {
    if (!window.pywebview) return
    try {
      // 更新本地状态
      modIds.forEach((id, index) => {
        const mod = takeModById(id)
        if (mod) {
          mod.lock_previous_mod = modIds[index-1] || null
          mod.lock_next_mod = modIds[index+1] || null
        }
      })
      // 发送请求给后端
      const res = await window.pywebview.api.link_mods(modIds)
      if (!checkResult(res, "批量设置 Mod 联锁", true)) {
        await appStore.refreshData();
        return false
      }
      dataVersion.value++ // 数据版本+1，确保问题判断刷新
      return true
    } catch (e) {
      console.error("批量设置 Mod 联锁异常:", e)
      toast.error(`批量设置 Mod 联锁异常: \n${e.message}`)
      await appStore.refreshData()
      return false
    }
  }
  // 批量解除 Mod 联锁
  const unlinkMods = async (modIds) => {
    if (!window.pywebview) return
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
      if (!checkResult(res, "批量解除 Mod 联锁", true)) {
        await appStore.refreshData();
        return false
      } 
      dataVersion.value++ // 数据版本+1，确保问题判断刷新
      return true
    } catch (e) {
      console.error("批量解除 Mod 联锁异常:", e)
      toast.error(`批量解除 Mod 联锁异常: \n${e.message}`)
      await appStore.refreshData()
      return false
    }
  }


  // --- 实时问题分析 ---
  // 排序问题检测器
  const modIssues = computed(() => {
    const issuesMap = new Map() // Key: modId, Value: Array<Issue>
    const activeSet = new Set(activeIds.value)
    dataVersion.value // 根据数据版本，确保最新
    
    // 添加问题（id: 模组ID, type: 问题类型, level: 问题等级, message: 问题描述, targetId: 关联的 Mod ID (如果有)）
    const _addIssue = (id, type, level, message, targetId = null) => {
      const mod = takeModById(id)
      // 确保 ignored_issues 存在且是一个数组
      const ignoredList = mod?.ignored_issues || []
      if (ignoredList.includes(type)) return
      // 确保 issuesMap 存在该模组的记录位置
      if (!issuesMap.has(id)) issuesMap.set(id, [])
      issuesMap.get(id).push({ type, level, message, targetId })
    }

    // 1. 全局检查，检查通用问题 (遍历所有 Mod)
    // 包括 inactive 的也要检查版本和文件完整性
    for (const mod of allModsMap.value.values()) {
      const id = mod.package_id.toLowerCase()

      // A. 文件丢失检查
      if (mod.is_missing || !mod.path) {
        _addIssue(id, ISSUE_TYPE.ERROR_MISSING_FILE, ISSUE_LEVEL.ERROR, '本地文件缺失或无法解析')
        continue // 文件都没了，后面的检查没意义
      }

      // B. 游戏版本支持检查
      // 检查 supported_versions 是否包含当前游戏主版本号（前三位）
      // 例如：mod.supported_versions 是 ["1.4", "1.5"]，游戏版本 settings.game_version 是 "1.5.4104"
      if (appStore.settings.game_version) {
        const gameVerMajor = appStore.settings.game_version.substring(0, 3) // 获取当前游戏主版本号（前三位）
        if (mod.supported_versions && !mod.supported_versions.includes(gameVerMajor)) {
           _addIssue(id, ISSUE_TYPE.WARN_VERSION_MISMATCH, ISSUE_LEVEL.WARN, 
             `^^版本问题^^：不支持当前游戏版本··[[${gameVerMajor}]]·· \n __(支持: ··${(mod.supported_versions || []).join('··, ··')}··)__`)
        }
      }

      // C. 联锁检查 (Link Mods)
      if (mod.lock_next_mod || mod.lock_previous_mod) {
        const allModIds = new Set(allModsMap.value.keys())
        // 缺失检查
        if (mod.lock_next_mod && !allModIds.has(mod.lock_next_mod)) {
          _addIssue(id, ISSUE_TYPE.WARN_LINK_MOD_MISSING, ISSUE_LEVEL.WARN, 
            `^^后置联锁模组缺失^^：${displayModName(mod.lock_next_mod)}`, mod.lock_next_mod)
          continue
        }
        if (mod.lock_previous_mod && !allModIds.has(mod.lock_previous_mod)) {
          _addIssue(id, ISSUE_TYPE.WARN_LINK_MOD_MISSING, ISSUE_LEVEL.WARN, 
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
        _addIssue(id, ISSUE_TYPE.ERROR_MISSING_FILE, ISSUE_LEVEL.ERROR, '本地文件缺失或无法解析')
        return
      }

      // C. 依赖检查 (Dependencies)
      if (mod.dependencies_mods) {
        mod.dependencies_mods.forEach(dep => {
          const depId = dep.package_id.toLowerCase()
          // C1. 是否完全缺失
          if (!allModsMap.value.has(depId)) {
            _addIssue(id, ISSUE_TYPE.ERROR_MISSING_DEPENDENCY, ISSUE_LEVEL.ERROR, 
              `!!依赖缺失!!：${displayModName(dep)}`, depId)
            return
          }
          // C2. 是否未启用
          if (!activeSet.has(depId)) {
            _addIssue(id, ISSUE_TYPE.ERROR_INACTIVE_DEPENDENCY, ISSUE_LEVEL.ERROR, 
              `!!依赖未启用!!：${displayModName(dep)}`, depId)
            return
          }
          // C3. 排序检查 (依赖必须在当前 Mod 之前)
          const depIndex = activeIds.value.indexOf(depId)
          if (depIndex > index) {
            _addIssue(id, ISSUE_TYPE.WARN_WRONG_ORDER, ISSUE_LEVEL.WARN, 
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
            _addIssue(id, ISSUE_TYPE.WARN_WRONG_ORDER, ISSUE_LEVEL.WARN, 
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
            _addIssue(id, ISSUE_TYPE.WARN_WRONG_ORDER, ISSUE_LEVEL.WARN, 
              `!!排序错误!!：必须在 [[${displayModName(depId)}]] 之前加载`, depId)
          }
        })
      }
      
      // E. 不兼容检查 (incompatible_mods)
      if (mod.incompatible_mods) {
        mod.incompatible_mods.forEach(badId => {
          const lowerBad = badId.toLowerCase()
          if (activeSet.has(lowerBad)) {
            _addIssue(id, ISSUE_TYPE.ERROR_INCOMPATIBLE, ISSUE_LEVEL.ERROR, 
              `!!模组冲突!!：与 ${displayModName(lowerBad)} 不兼容`, lowerBad)
          }
        })
      }

      // F. 联锁排序检查
      if(mod.lock_previous_mod && activeIds.value[index-1] !== mod.lock_previous_mod) {
        _addIssue(id, ISSUE_TYPE.WARN_LINK_WRONG_ORDER, ISSUE_LEVEL.WARN, 
          `^^联锁排序错误^^：前一个模组应为 [[${displayModName(mod.lock_previous_mod)}]]`, mod.lock_previous_mod)
      }
      if(mod.lock_next_mod && activeIds.value[index+1] !== mod.lock_next_mod) {
        _addIssue(id, ISSUE_TYPE.WARN_LINK_WRONG_ORDER, ISSUE_LEVEL.WARN, 
          `^^联锁排序错误^^：后一个模组应为 [[${displayModName(mod.lock_next_mod)}]]`, mod.lock_next_mod)
      }
    })

    // 3. 禁用列表检查 (遍历 inactiveIds)
    inactiveIds.value.forEach((id, index) => {
      const mod = allModsMap.value.get(id)
      if (!mod) return
      // 联锁排序检查
      if(mod.lock_previous_mod && inactiveIds.value[index-1] !== mod.lock_previous_mod) {
        _addIssue(id, ISSUE_TYPE.WARN_LINK_WRONG_ORDER, ISSUE_LEVEL.WARN, 
          `^^联锁排序错误^^：前一个模组应为 [[${displayModName(mod.lock_previous_mod)}]]`, mod.lock_previous_mod)
      }
      if(mod.lock_next_mod && inactiveIds.value[index+1] !== mod.lock_next_mod) {
        _addIssue(id, ISSUE_TYPE.WARN_LINK_WRONG_ORDER, ISSUE_LEVEL.WARN, 
          `^^联锁排序错误^^：后一个模组应为 [[${displayModName(mod.lock_next_mod)}]]`, mod.lock_next_mod)
      }
    })

    // 4. 临时列表检查 (遍历 tempIds)
    tempIds.value.forEach((id, index) => {
      const mod = allModsMap.value.get(id)
      if (!mod) return
      // 联锁排序检查
      if(mod.lock_previous_mod && tempIds.value[index-1] !== mod.lock_previous_mod) {
        _addIssue(id, ISSUE_TYPE.WARN_LINK_WRONG_ORDER, ISSUE_LEVEL.WARN, 
          `^^联锁排序错误^^：前一个模组应为 [[${displayModName(mod.lock_previous_mod)}]]`, mod.lock_previous_mod)
      }
      if(mod.lock_next_mod && tempIds.value[index+1] !== mod.lock_next_mod) {
        _addIssue(id, ISSUE_TYPE.WARN_LINK_WRONG_ORDER, ISSUE_LEVEL.WARN, 
          `^^联锁排序错误^^：后一个模组应为 [[${displayModName(mod.lock_next_mod)}]]`, mod.lock_next_mod)
      }
    })

    return issuesMap
  })
  // 辅助：获取某个 Mod 问题的最高级别
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
        if (!mod || mod.is_missing) return;
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
      const res = await window.pywebview.api.set_mods_ignore_issues(updates);
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
    allModsMap, dataVersion, inactiveIds, tempIds, activeIds, 
    savedActiveIds, activeLoadModifyTime, conflictList, coexistenceList,
    selectedIds, lastSelectedMod, currentTargetId, 

    // Getters
    isDirty, selectedMods, selectedStats, allModTags, modIssues, 

    // Actions
    setMods, reset, takeModById, takeModListByIds, displayModName, displayModType, displayModIcon, 
    updateInactiveIds, takeInactiveIds, removeIdsOnAllList, selectMods, clearSelection, 
    scanMods, scanComplete, autoSortMods, localizeSelectedMods,
    updateModUserData, updateModTime, linkMods, unlinkMods, 
    setModsColor, setModsType, addModsTags, removeModsTags, selectModsTag, selectModsGroup, 
    getModIssueState, ignoreIssue, batchIgnoreIssues, getListIssues, 
  }
})