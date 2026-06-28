import { computed, ref } from 'vue'
import { useGroupStore } from '../groupStore'

export const useModSelection = ({
  interlocksMap,
  normalizeListToken,
  takeModById,
} = {}) => {
  const selectedIds = ref([])         // 已选中的 Mod ID
  const lastSelectedMod = ref(null)   // 最后选中的 Mod 对象
  const currentTargetId = ref('')     // 当前目标 ID (查找定位用)
  const isDraggingMod = ref(false)    // 是否正在拖动模组项

  // 获取选中的所有模组对象
  const selectedMods = computed(() => {
    // 利用 Boolean() 转换规则，剔除数组中所有假值（undefined/null/0/''/false/NaN）。
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

    // 1. 初始化统计，只统计“拥有该属性的 Mod 数量”。
    const tagCounts = {}
    const groupCounts = {}
    const colors = new Set()
    const groupStore = useGroupStore()

    ids.forEach(id => {
      const mod = takeModById(id)
      if (!mod) return
      // 统计 Tags 出现的次数
      mod.tags?.forEach(t => tagCounts[t] = (tagCounts[t] || 0) + 1)
      // 统计 Groups 出现的次数
      groupStore.takeGroupsByModId(id).forEach(g => groupCounts[g.group_id] = (groupCounts[g.group_id] || 0) + 1)
      // 统计 Color
      colors.add(mod.sign_color)
    })

    // 2. 生成状态
    const total = ids.length
    // Tags 状态
    const tagState = {}
    for (const [tag, count] of Object.entries(tagCounts)) {
      tagState[tag] = count === total ? 'all' : 'some'
    }

    // Group 状态
    const groupState = {}
    for (const [gid, count] of Object.entries(groupCounts)) {
      groupState[gid] = count === total ? 'all' : 'some'
    }

    // Color 状态
    let colorState = null
    if (colors.size === 1) colorState = [...colors][0]
    else if (colors.size > 1) colorState = 'mixed'

    return { tags: tagState, groups: groupState, color: colorState }
  })

  // 清除选择
  const clearSelection = () => {
    selectedIds.value = []
  }

  // 选择 Mod（支持联锁自动多选 & 智能排序）
  const selectMods = (ids, lastId) => {
    // 1. 边界与归一化处理
    if (!ids) {
      clearSelection()
      return
    }

    const inputIds = Array.isArray(ids) ? ids : [ids]
    if (inputIds.length === 0) {
      selectedIds.value = []
      lastSelectedMod.value = null
      return
    }

    // 2. 建立索引映射（ID -> 原始输入位置），同时作为快速查找表。
    const inputMap = new Map()
    inputIds.forEach((id, idx) => inputMap.set(normalizeListToken(id), idx))
    const finalChunks = [] // 存储 { index: number, items: string[] }
    const processed = new Set() // 记录已处理过的输入 ID

    // 3. 遍历输入列表
    for (let i = 0; i < inputIds.length; i++) {
      const currentId = normalizeListToken(inputIds[i])
      // 如果该 ID 已经被包含在之前的某个链条中处理过，直接跳过。
      if (processed.has(currentId)) continue
      const mod = takeModById(currentId)

      // 如果这个 Mod 有 interlock_id，直接从全局字典里拿整个数组。
      if (mod && mod.interlock_id && interlocksMap.value[mod.interlock_id]) {
        const chainItems = interlocksMap.value[mod.interlock_id]
        let anchorIndex = -1
        // 遍历整个链条，找出第一个在用户点击/圈选范围内的项，作为锚点位置。
        for (const chainId of chainItems) {
          const pid = normalizeListToken(chainId)
          processed.add(pid) // 把整条链上的 ID 都标记为已处理
          if (anchorIndex === -1 && inputMap.has(pid)) {
            anchorIndex = inputMap.get(pid)
          }
        }
        // 加入块中
        finalChunks.push({
          index: anchorIndex !== -1 ? anchorIndex : i,
          items: chainItems
        })
      } else {
        // 普通 Mod，无联锁
        finalChunks.push({ index: i, items: [inputIds[i]] })
        processed.add(currentId)
      }
    }

    // 4. 根据锚点索引重新排序块并展平
    finalChunks.sort((a, b) => a.index - b.index)
    const result = finalChunks.flatMap(chunk => chunk.items)
    // 5. 更新状态
    selectedIds.value = result

    // 处理最后选中项高亮
    if (lastId) {
      // 检查 lastId 是否在最终结果中。
      const target = result.find(id => normalizeListToken(id) === normalizeListToken(lastId))
      lastSelectedMod.value = target ? takeModById(target) : takeModById(result[result.length - 1])
    } else {
      lastSelectedMod.value = takeModById(result[result.length - 1])
    }
  }

  return {
    selectedIds,
    lastSelectedMod,
    currentTargetId,
    isDraggingMod,
    selectedMods,
    selectedStats,
    clearSelection,
    selectMods,
  }
}
