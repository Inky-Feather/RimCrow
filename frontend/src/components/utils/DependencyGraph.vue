<!-- src/components/utils/DependencyGraph.vue -->
<template>
  <div class="relative w-full h-full bg-bg-deep/20 border-r border-text-main/5 overflow-hidden" 
    ref="containerRef"
    @mousedown="handleCanvasClick"
    @mousemove="handleMouseMove"
    @mouseleave="handleMouseLeave"
  >
    <!-- 只保留 Canvas -->
    <canvas ref="canvasRef" class="block"></canvas>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch, computed } from 'vue'
import { useModStore } from '../../stores/modStore'
import { useHoverStore } from '../../stores/hoverStore'

const props = defineProps({
  // 当前显示列表的 ID 数组（必须是有序的 modelValue）
  listIds: { type: Array, required: true },
  // 列表项高度（必须固定，与 CSS 一致，例如 50）
  itemHeight: { type: Number, required: true },
  // 虚拟列表的滚动容器 DOM（用于同步滚动）
  scrollElement: { type: Object, default: null },
  // 是否筛选显示
  isFilter: { type: Boolean, default: false }
})

const emit = defineEmits(['lineClick'])

const modStore = useModStore()
const hoverStore = useHoverStore()
const containerRef = ref(null)
const canvasRef = ref(null)
const hoveredGroup = ref(null)

// --- 配置参数 ---
const CONFIG = {
  maxLanes: 4,          // 限制最大显示轨道数为 5
  laneWidth: 9,        // 轨道间距
  baseX: 6,            // 起始 X 偏移
  
  nodeRadius: 3,        // 节点半径
  rootRadius: 4,        // 根节点半径
  curveRadius: 10,      // 拐弯半径
  
  lineWidthActive: 2.5, // 高亮线宽
  lineWidthDimmed: 1.5, // 普通线宽
  
  alphaActive: 1.0,     // 高亮不透明度
  alphaDimmed: 0.3,    // 普通不透明度
  alphaHidden: 0.1,    // 被遮挡时的不透明度

  colors: [
    '#0ea5e9', '#f59e0b', '#8b5cf6', '#10b981', 
    '#ec4899', '#d946ef', '#f97316', '#3b82f6', 
    "#616161", '#f46f6e', "#25D366", "#7B1FA2", 
    "#FDD835", "#1565C0", "#90CAF9", "#9E9E9E", 
    "#CE93D8", "#81C784", "#CCDC38", '#84cc16',
  ],
  colorError: '#ef4444'
}

// --- 状态数据 ---
let groups = [] // 所有依赖组数据
const manualActiveGroupId = ref(null) // 用户手动点击激活的组 ID

// 计算当前选中的最后一个 ID (作为自动高亮的依据)
const lastSelectedId = computed(() => {
  return modStore.lastSelectedMod?.package_id || null
})

// 缓存当前选中项对应的索引集合 (用于快速碰撞检测判定高亮)
const selectedIndicesSet = computed(() => {
  const set = new Set()
  modStore.selectedIds.forEach(id => {
    // 这里需要反查 id 在 listIds 中的索引
    // 注意：如果 listIds 很大，indexOf 可能稍慢，但通常 UI 响应够用
    // 极致优化可以依赖外部传入 map，但这里直接查即可
    const idx = props.listIds.indexOf(id) // 注意大小写，如果 listIds 是原始ID
    if (idx !== -1) set.add(idx)
  })
  return set
})

// 辅助函数：判断组是否处于高亮状态
const isGroupActive = (group) => {
  if (manualActiveGroupId.value === group.id) return true
  if (selectedIndicesSet.value.size > 0) {
     for (const idx of group.allIndices) {
       if (selectedIndicesSet.value.has(idx)) return true
     }
  }
  return false
}


// --- 公共碰撞检测函数 ---
const getHitGroup = (e) => {
  if (!canvasRef.value || !containerRef.value) return null

  // 1. 计算鼠标的物理坐标
  const rect = containerRef.value.getBoundingClientRect()
  const x = e.clientX - rect.left
  const y = e.clientY - rect.top
  // 加上滚动偏移
  const scrollTop = props.scrollElement?.getOffset() || 0
  const absoluteY = y + scrollTop
  
  // 转换为逻辑网格坐标
  const rowIndex = Math.floor(absoluteY / props.itemHeight)
  // 计算鼠标在格子内的相对位置 (0.0 - 1.0)
  // 用于解决边界重叠：鼠标偏上归属上一行，偏下归属下一行
  const laneXRaw = (x - CONFIG.baseX) / CONFIG.laneWidth
  const clickLane = Math.round(laneXRaw)
  
  // 增加一点点击宽容度，防止在轨道缝隙中失效
  if (Math.abs(clickLane - laneXRaw) > 0.6) return null

  // 筛选候选线路
  if (clickLane >= 0 && clickLane < CONFIG.maxLanes) {
    // 2. 第一轮筛选：几何物理碰撞 (Physical Hit Test)
    // 找出所有在视觉上经过当前点(Lane, Row)的线路
    // 这就是“穿透层级，直到碰到实际存在的线条”的关键
    const geometricHits = groups.filter(g => {
      // 必须在同一条视觉轨道
      if (g.visualLane !== clickLane) return false
      
      // 必须在垂直有效范围内 [minIndex, maxIndex]
      // 这里的逻辑保证了：如果你点击的位置超出了上层短线的范围，
      // 短线会被过滤掉，从而露出了下层的长线
      if (rowIndex < g.minIndex || rowIndex > g.maxIndex) return false
      
      return true
    })

    if (geometricHits.length === 0) return null

    // 3. 第二轮筛选：状态优先级 (Status Priority)
    // 规则：选中项线路 > 高亮线路 > 可见到的最高层线路
    
    // 分离 Active 和 Normal
    const activeHits = []
    const normalHits = []
    
    geometricHits.forEach(g => {
      if (isGroupActive(g)) {
        activeHits.push(g)
      } else {
        normalHits.push(g)
      }
    })

    // 4. 最终决策：
    // 因为 groups 数组是按绘制顺序(Z-Index)排序的(底层->顶层)，
    // 所以取数组的最后一个元素(pop/length-1)，就是视觉上的“最上层”。
    
    // 优先级 A: 存在有效的 Active 线路 (高亮优先)
    if (activeHits.length > 0) {
      // 取最上层的 Active 线
      return activeHits[activeHits.length - 1]
    }
    
    // 优先级 B: 只存在 Normal 线路 (视觉最上层优先)
    if (normalHits.length > 0) {
      // 取最上层的 Normal 线 (这就是你要求的“符合视觉直觉”)
      return normalHits[normalHits.length - 1]
    }
  }
  return null
}

// --- 1. 数据处理 (Process) ---
const processGraph = () => {
  if (!props.listIds.length) {
    groups = []
    childOffsetMap.clear()
    return
  }

  const ids = props.listIds
  const idToIndex = new Map(ids.map((id, index) => [id.toLowerCase(), index]))
  const tempGroups = new Map() // parentId -> group

  // 1.1 收集依赖关系 (反转 Child->Parent 为 Parent->Children)
  ids.forEach((childId, childIndex) => {
    const mod = modStore.takeModById(childId)
    if (!mod || !mod.dependencies_mods) return

    mod.dependencies_mods.forEach(parentMod => {
      const pidLower = parentMod.package_id.toLowerCase()
      // 只有当父项也在当前可视列表中时才绘制
      // 如果父项被筛选掉了，就不画这根线（或者画一半？这里选择不画）
      if (!idToIndex.has(pidLower)) return 

      const parentIndex = idToIndex.get(pidLower)
      // 生成唯一 GroupKey
      const groupKey = pidLower
      
      if (!tempGroups.has(groupKey)) {
        tempGroups.set(groupKey, {
          id: groupKey, // 组 ID
          parentId: pidLower,
          parentIndex: parentIndex,
          childIndices: [],
          // 核心修正：初始化时必须包含 parentIndex
          allIndices: new Set([parentIndex]), // 用于快速碰撞检测
          isError: false
        })
      }
      const group = tempGroups.get(groupKey)
      group.childIndices.push(childIndex)
      // 核心修正：必须将 childIndex 也加入集合，否则选中子项时该线路不会判定为高亮
      group.allIndices.add(childIndex)
    })
  })

  // 转换为数组并计算属性
  const groupList = Array.from(tempGroups.values()).map(g => {
    // 排序子项索引
    g.childIndices.sort((a, b) => a - b)
    // 计算该组依赖线的生命周期 [min, max]
    // 正常：Parent(Top) -> Children(Bottom)。范围 Parent -> LastChild
    // 错误：Parent(Bottom) -> Children(Top)。范围 LastChild -> Parent (或者混合)
    const all = [g.parentIndex, ...g.childIndices]
    g.minIndex = Math.min(...all)
    g.maxIndex = Math.max(...all)
    // 检测是否包含向上依赖（只要有一个子项在父项上面，或者全部在上面）
    // 简化处理：如果 min < parentIndex，说明有子项在父项上面，视为 Error（或者部分 Error）
    // 为了视觉清晰，我们将含有向上依赖的组标记为 Error
    if (g.minIndex < g.parentIndex) g.isError = true
    return g
  })

  // 排序优化：决定 Z-Index (堆叠顺序)
  // 1. minIndex 小的排前面 -> 先绘制 -> 在底层 (背景)
  // 2. minIndex 大的排后面 -> 后绘制 -> 在顶层 (覆盖)
  // 3. 如果 minIndex 相同，跨度大的排前面 (作为背景)，跨度小的排后面 (作为细节)
  groupList.sort((a, b) => {
    if (a.minIndex !== b.minIndex) {
      return a.minIndex - b.minIndex // 起点越靠上，越在底层
    }
    // 起点相同，长的在底，短的在顶
    const spanA = a.maxIndex - a.minIndex
    const spanB = b.maxIndex - b.minIndex
    return spanB - spanA 
  })

  // 贪心算法分配 *逻辑* 轨道
  // lanes 数组存储每个轨道当前被占用到哪个 Index
  const lanes = [] 
  groups = groupList.map(group => {
    let logicalLane = -1
    // 贪心算法：寻找空闲轨道（增加 1 的间隙防止紧贴）
    for (let i = 0; i < lanes.length; i++) {
      // 如果该轨道目前的占用结束位置 < 当前组的起始位置，则可用
      if (lanes[i] < group.minIndex) {
        logicalLane = i
        lanes[i] = group.maxIndex
        break
      }
    }
    // 没找到，开新轨道
    if (logicalLane === -1) {
      logicalLane = lanes.length
      lanes.push(group.maxIndex)
    }
    
    // 映射到 *视觉* 轨道 (0-4)
    // 默认 (从左往右) 筛选时 (从右往左)：
    const visualLane = props.isFilter? (CONFIG.maxLanes - 1) - (logicalLane % CONFIG.maxLanes) : logicalLane % CONFIG.maxLanes

    return {
      ...group,
      logicalLane,
      visualLane,
      color: group.isError ? CONFIG.colorError : CONFIG.colors[logicalLane % CONFIG.colors.length]
    }
  })

  // --- 新增步骤 4: 计算 Child 节点的垂直偏移 ---
  childOffsetMap.clear()
  
  // 临时映射：childIndex -> Array<Group>
  const connectionMap = new Map()
  
  groups.forEach(g => {
    g.childIndices.forEach(cIdx => {
      if (!connectionMap.has(cIdx)) connectionMap.set(cIdx, [])
      connectionMap.get(cIdx).push(g)
    })
  })

  // 对每个 Child 节点处的连线进行排序和偏移计算
  connectionMap.forEach((groupArr, cIdx) => {
    // 按 visualLane 排序，保证轨道靠左的偏移在上方(或下方)，视觉有序
    groupArr.sort((a, b) => a.visualLane - b.visualLane)
    
    const count = groupArr.length
    if (count <= 1) return // 只有一个连接，无需偏移

    // 设定偏移步长 (像素)
    const step = 4 
    // 计算起始偏移，使整体居中
    const startY = -((count - 1) * step) / 2
    
    const offsetLookup = new Map()
    groupArr.forEach((g, i) => {
      offsetLookup.set(g.id, startY + i * step)
    })
    
    childOffsetMap.set(cIdx, offsetLookup)
  })
}

// 用于存储每个 childIndex 上不同 group 的偏移量映射
// Map<childIndex, Map<groupId, offsetPixels>>
let childOffsetMap = new Map()

// --- 2. 交互逻辑 (Interaction) ---
const handleCanvasClick = (e) => {
  // 1. 获取命中的组 (getHitGroup 已经实现了：高亮优先 > 顶层优先)
  const targetGroup = getHitGroup(e)
  if (targetGroup) {
    const active = isGroupActive(targetGroup)
    // 情况 A: 该线路已经是激活状态 (通过选中项自动激活 或 之前手动点过)
    if (active) {
      // 构造 ID 列表: [父项ID, ...子项ID], 从 props.listIds 反查
      const childIds = targetGroup.childIndices.map(idx => props.listIds[idx])
      const payload = [targetGroup.parentId, ...childIds] // parentId 已经是 Mod ID 格式
      // 触发事件给父组件
      emit('lineClick', payload)
      return
    }
    // 情况 C: 全局无选中项，点击背景线路 -> 切换手动高亮
    if (manualActiveGroupId.value === targetGroup.id) {
      manualActiveGroupId.value = null
    } else {
      manualActiveGroupId.value = targetGroup.id
    }
  } else {
    // 点击空白处，清除手动高亮
    manualActiveGroupId.value = null
    emit('lineClick', [])
  }
}

// 2. 新增：鼠标移动处理 (悬停 & Tooltip位置)
const handleMouseMove = (e) => {
  const group = getHitGroup(e)
  
  // 状态 1: 鼠标在某条线路上
  if (group) {
    // console.log('Hit Line:', group.id)
    canvasRef.value.style.cursor = 'pointer'
    
    // 只有当切换了不同的组时，才调用 show (避免每一帧都重置内容)
    if (hoveredGroup.value !== group) {
      hoveredGroup.value = group
      
      // 构造显示内容 (根据你的全局组件支持纯文本还是HTML，这里以模版字符串为例)
      let content = `{{${group.color}|依赖源:}} ${modStore.displayModName(group.parentId)}\n包含 ${group.childIndices.length} 个子模组`
      if (group.isError) {
        content += `\n!!(⚠ 依赖源后置，依赖源应在所有需求模组前加载)!!`
      }
      content += '\n\n__[[(再次点击可筛选该依赖下所有模组)]]__'
      
      // 调用全局 Store 显示
      hoverStore.show(content, e)
    } 
    else {
      // 如果还在同一个组上，仅更新位置
      hoverStore.updatePosition(e)
    }
  } 
  // 状态 2: 鼠标在 Canvas 空白处
  else {
        // console.log('Hit Empty -> Force Hide')
    // 关键修正：确保只要离开线路，就重置状态并隐藏 Tooltip
    if (hoveredGroup.value !== null) {
      hoveredGroup.value = null
      canvasRef.value.style.cursor = 'default'
    }
    hoverStore.hide() // <--- 必须显式调用隐藏
    canvasRef.value.style.cursor = 'default'
  }
}

// 3. 鼠标离开处理
const handleMouseLeave = () => {
  hoverStore.hide() // 确保鼠标移出组件时隐藏
  // console.log('鼠标离开组件')
  if (hoveredGroup.value) {
    hoveredGroup.value = null
  }
  if (canvasRef.value) canvasRef.value.style.cursor = 'default'
}

// --- 3. 渲染循环 (Render) ---
let animationFrameId
const draw = () => {
  const canvas = canvasRef.value
  const ctx = canvas?.getContext('2d')
  if (!ctx ) return // 等待 DOM 就绪

  // 尺寸同步
  const width = canvas.width
  const height = canvas.height
  const scrollTop = props.scrollElement?.getOffset ? props.scrollElement.getOffset() : 0

  // 视口优化
  const viewportStart = Math.floor(scrollTop / props.itemHeight)
  const viewportEnd = viewportStart + Math.ceil(height / props.itemHeight) + 1

  ctx.clearRect(0, 0, width, height)
  ctx.lineCap = 'round'
  ctx.lineJoin = 'round'

  // --- 确定高亮组 ---
  // 1. 手动激活的优先
  // 2. 其次是包含选中项的
  const selectedIdLower = lastSelectedId.value?.toLowerCase()
  
  // 预计算每个组的状态
  const groupStates = groups.map(g => {
    // 剔除视口外的
    if (g.maxIndex < viewportStart - 1 || g.minIndex > viewportEnd + 1) {
      return { group: g, visible: false }
    }

    let isActive = false
    // 判定是否激活
    if (manualActiveGroupId.value === g.id) {
      isActive = true
    } else if (selectedIdLower) {
      // 检查当前选中项是否是该组的 Parent 或 Child
      if (g.parentId === selectedIdLower) isActive = true
      // 这里需要回溯原始数据比较快，或者直接用 index 判断（如果 listIds 没变）
      // 为准确性，用 index 判断是否命中 g.allIndices
      const selectedIndex = props.listIds.findIndex(id => id.toLowerCase() === selectedIdLower)
      if (g.allIndices.has(selectedIndex)) isActive = true
    }

    return { group: g, visible: true, isActive }
  })

  // 找出当前有哪些轨道被“激活组”占用了
  const activeLanes = new Set()
  groupStates.forEach(s => {
    if (s.visible && s.isActive) activeLanes.add(s.group.visualLane)
  })

  // 分两层绘制：先画 Dimmed，再画 Active
  // 这样 Active 会盖在上面
  const drawPass = (onlyActive) => {
    groupStates.forEach(state => {
      if (!state.visible) return
      if (onlyActive && !state.isActive) return
      if (!onlyActive && state.isActive) return // 第一遍不画 Active

      const g = state.group
      const laneX = CONFIG.baseX + (g.visualLane * CONFIG.laneWidth)
      
      // 透明度逻辑
      let alpha = CONFIG.alphaDimmed
      let lineWidth = CONFIG.lineWidthDimmed
      
      if (state.isActive) {
        alpha = CONFIG.alphaActive
        lineWidth = CONFIG.lineWidthActive
      } else {
        // 如果该轨道上有激活的组，且当前组与激活组在垂直方向有重叠，则大幅降低透明度（避让）
        // 这里简化为：只要该轨道有激活组，非激活组就变很淡
        if (activeLanes.has(g.visualLane)) {
            alpha = CONFIG.alphaHidden
        }
      }

      ctx.globalAlpha = alpha
      ctx.strokeStyle = g.color
      ctx.fillStyle = g.color
      ctx.lineWidth = lineWidth

      const getY = (idx) => (idx * props.itemHeight + props.itemHeight / 2) - scrollTop
      const nodeX = width - 2

      // --- 绘制逻辑 (复用之前的 F-Shape) ---
      
      // 1. 垂直主线
      if (g.maxIndex > g.minIndex) {
        const yMin = getY(g.minIndex)
        const yMax = getY(g.maxIndex)
        ctx.beginPath()
        ctx.moveTo(laneX, yMin + CONFIG.curveRadius)
        ctx.lineTo(laneX, yMax - CONFIG.curveRadius)
        ctx.stroke()
      }

      // 2. Root 节点 (╭)
      const yParent = getY(g.parentIndex)
      ctx.beginPath()
      // 如果高亮，画大一点的节点背景
      if (state.isActive) {
         ctx.fillStyle = '#1e1e1e' // 背景色
         ctx.beginPath()
         ctx.arc(nodeX - CONFIG.rootRadius*2, yParent, CONFIG.rootRadius + 2, 0, Math.PI*2)
         ctx.fill()
         ctx.fillStyle = g.color // 还原颜色
      }
      // 空心圆
      ctx.strokeStyle = g.color
      ctx.beginPath()
      ctx.arc(nodeX - CONFIG.rootRadius * 2 + 2, yParent, CONFIG.rootRadius, 0, Math.PI * 2)
      ctx.stroke()
      // 连线
      ctx.beginPath()
      // 从圆圈左侧开始
      ctx.moveTo(nodeX - CONFIG.rootRadius * 3, yParent)
      const r = CONFIG.curveRadius
      if (g.isError && g.parentIndex > g.minIndex) {
        // Error 情况：线向上走
        // 横线向左 -> 弧形向上
         ctx.lineTo(laneX + r, yParent)
         ctx.quadraticCurveTo(laneX, yParent, laneX, yParent - r)
      } else {
        // 正常情况：线向下走 (╭)
        // 横线向左 -> 弧形向下
         ctx.lineTo(laneX + r, yParent)
         ctx.quadraticCurveTo(laneX, yParent, laneX, yParent + r)
      }
      ctx.stroke()

      // 3. Children 节点 (╰)
      g.childIndices.forEach(cIdx => {
      // 视口优化
        if (cIdx < viewportStart - 1 || cIdx > viewportEnd + 1) return
        
        // --- 核心修改：应用 Y 轴偏移 ---
        let yOffset = 0
        if (childOffsetMap.has(cIdx)) {
          const offsets = childOffsetMap.get(cIdx)
          if (offsets.has(g.id)) {
            yOffset = offsets.get(g.id)
          }
        }

        const yChildBase = getY(cIdx)
        const yChild = yChildBase + yOffset // 应用偏移
        const r = CONFIG.curveRadius

        ctx.beginPath()
        
        // 节点实心圆
        ctx.fillStyle = g.color
        // 注意：节点圆心也需要偏移，保持对齐
        ctx.arc(nodeX - CONFIG.nodeRadius * 2, yChild, CONFIG.nodeRadius, 0, Math.PI * 2)
        ctx.fill()
        
        // 连线
        ctx.beginPath()
        if (g.isError && cIdx < g.parentIndex) {
        // Error 情况：线从下方垂直线分叉出来 -> 向右
        // (laneX, yChild + r) -> arc -> (laneX + r, yChild) -> node
            ctx.moveTo(laneX, yChild + r)
            ctx.quadraticCurveTo(laneX, yChild, laneX + r, yChild)
        } else {
        // 正常情况：线从上方垂直线分叉出来 -> 向右
        // (laneX, yChild - r) -> arc -> (laneX + r, yChild) -> node
            ctx.moveTo(laneX, yChild - r)
            ctx.quadraticCurveTo(laneX, yChild, laneX + r, yChild)
        }
        ctx.lineTo(nodeX - CONFIG.nodeRadius * 3, yChild)
        ctx.stroke()
      })
    })
  }

  // 第一次绘制：背景层 (Dimmed)
  drawPass(false)
  // 第二次绘制：高亮层 (Active) - 盖在上面
  drawPass(true)

  animationFrameId = requestAnimationFrame(draw)
}

// --- 生命周期 ---
// 监听 Canvas 容器尺寸变化 (ResizeObserver)
const resizeObserver = new ResizeObserver(entries => {
  const { width, height } = entries[0].contentRect
  const dpr = window.devicePixelRatio || 1
  if (canvasRef.value) {
    canvasRef.value.width = width * dpr
    canvasRef.value.height = height * dpr
    canvasRef.value.style.width = width + 'px'
    canvasRef.value.style.height = height + 'px'
    const ctx = canvasRef.value.getContext('2d')
    ctx.scale(dpr, dpr)
  }
})

watch(() => props.listIds, () => {
  manualActiveGroupId.value = null // 列表变动重置手动激活
  processGraph()
}, { deep: true, immediate: true })

onMounted(() => {
  if (containerRef.value) resizeObserver.observe(containerRef.value)
  animationFrameId = requestAnimationFrame(draw)
})
onUnmounted(() => {
  cancelAnimationFrame(animationFrameId)
  resizeObserver.disconnect()
})
</script>