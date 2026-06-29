<!-- src/components/utils/DependencyGraph.vue -->
<template>
  <div ref="containerRef" class="relative h-full w-full overflow-visible"
    @contextmenu.prevent="handleCanvasContextMenu">
    <div class="absolute inset-0 overflow-hidden border-r border-border-base/5 bg-bg-deep/20"
      @mousedown="handleCanvasClick"
      @mousemove="handleMouseMove"
      @mouseleave="handleMouseLeave">
      <canvas ref="canvasRef" class="block"></canvas>
    </div>

    <button class="group absolute left-0.5 top-1 z-20 flex items-center gap-0 rounded-xl border border-accent-primary/22 bg-bg-deep/82 px-1 py-1 text-[0.62rem] font-black text-accent-primary shadow-lg backdrop-blur-sm transition-all duration-300 hover:border-accent-primary/34 hover:pr-2.5 hover:text-text-main"
      v-tooltip="managerButtonTooltip"
      @mousedown.stop
      @click.stop="toggleManagerPanel">
      <FolderTree class="size-4 shrink-0 transition-transform duration-300 group-hover:scale-105" />
      <span class="grid max-w-0 grid-cols-[1fr] overflow-hidden whitespace-nowrap opacity-0 transition-all duration-300 group-hover:ml-1.5 group-hover:max-w-36 group-hover:opacity-100">
        <span class="text-[0.6rem] font-bold text-text-dim">{{ currentVisibleCount }} / {{ currentEffectiveCount }}</span>
      </span>
    </button>

    <DependencyGraphManagerPanel v-if="isManagerOpen"
      :panel-style="managerPanelStyle"
      :visible-count="currentVisibleCount"
      :effective-total="currentEffectiveCount"
      :focus-source-id="focusSourceId"
      :current-groups="currentVisibleGroupItems"
      :hidden-groups="hiddenGroupItems"
      @close="isManagerOpen = false"
      @toggle-source="toggleHiddenSource"
      @restore-all="restoreAllHiddenSources" />
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useToast } from 'vue-toastification'
import { useAppStore } from '../../app/stores/appStore'
import { useContextMenuStore } from '../../shared/components/context-menu/contextMenuStore'
import { useHoverStore } from '../../shared/components/popover/hoverStore'
import DependencyGraphManagerPanel from './DependencyGraphManagerPanel.vue'
import { useModStore } from './stores/modStore'
import { CornerUpRight, Eye, EyeOff, Filter, FilterX, Focus, FolderTree, Settings2, Undo2 } from 'lucide-vue-next'

const props = defineProps({
  // 当前显示列表的 ID 数组（必须是有序的 modelValue）
  listIds: { type: Array, required: true },
  // 当前列表是否正处在依赖线筛选状态，用于保持左右轨道方向和旧体验一致。
  lineFilterIds: { type: Array, default: () => [] },
  // 列表项高度（必须固定，与 CSS 一致，例如 50）
  itemHeight: { type: Number, required: true },
  // 虚拟列表的滚动容器 DOM（用于同步滚动）
  scrollElement: { type: Object, default: null },
  // 是否筛选显示
  isFilter: { type: Boolean, default: false },
})

const emit = defineEmits(['lineClick'])

const appStore = useAppStore()
const modStore = useModStore()
const hoverStore = useHoverStore()
const contextMenuStore = useContextMenuStore()
const toast = useToast()

const containerRef = ref(null)
const canvasRef = ref(null)
const hoveredGroupId = ref('')
const manualActiveGroupId = ref('')
const focusSourceId = ref('')
const isManagerOpen = ref(false)
const managerPanelStyle = ref({})

const CONFIG = {
  maxLanes: 4,
  laneWidth: 9,
  baseX: 6,

  nodeRadius: 3,
  rootRadius: 4,
  curveRadius: 10,

  lineWidthActive: 2.5,
  lineWidthDimmed: 1.5,

  alphaActive: 1.0,
  alphaDimmed: 0.3,
  alphaHidden: 0.1,

  colors: [
    '#0ea5e9', '#f59e0b', '#8b5cf6', '#10b981',
    '#ec4899', '#d946ef', '#f97316', '#3b82f6',
    '#616161', '#f46f6e', '#25D366', '#7B1FA2',
    '#FDD835', '#1565C0', '#90CAF9', '#9E9E9E',
    '#CE93D8', '#81C784', '#CCDC38', '#84cc16',
  ],
  colorError: '#ef4444',
  panelHistoryColor: '#64748b',
}

const normalizeSourceId = (value) => String(value || '').trim().toLowerCase()

const getThemeColor = (name, fallback) => {
  if (typeof window === 'undefined') return fallback
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback
}

const hashSourceColor = (sourceId) => {
  const normalized = normalizeSourceId(sourceId)
  if (!normalized) return CONFIG.panelHistoryColor
  let hash = 0
  for (let index = 0; index < normalized.length; index += 1) {
    hash = ((hash << 5) - hash) + normalized.charCodeAt(index)
    hash |= 0
  }
  return CONFIG.colors[Math.abs(hash) % CONFIG.colors.length]
}

const listIndexMap = computed(() => (
  new Map(props.listIds.map((id, index) => [normalizeSourceId(id), index]))
))

const hiddenSourceIds = computed(() => (
  Array.isArray(appStore.settings.ui?.hidden_dependency_graph_source_ids)
    ? appStore.settings.ui.hidden_dependency_graph_source_ids.map(normalizeSourceId).filter(Boolean)
    : []
))
const hiddenSourceIdSet = computed(() => new Set(hiddenSourceIds.value))
const hiddenSourceIdsKey = computed(() => hiddenSourceIds.value.join('|'))

const lastSelectedId = computed(() => modStore.lastSelectedMod?.package_id || '')
const selectedIndicesSet = computed(() => {
  const set = new Set()
  ;(modStore.selectedIds || []).forEach(id => {
    const idx = listIndexMap.value.get(normalizeSourceId(id))
    if (idx != null && idx !== -1) set.add(idx)
  })
  return set
})

const isSameLineFilter = (lineIds = []) => {
  const currentIds = Array.isArray(props.lineFilterIds) ? props.lineFilterIds.map(normalizeSourceId).filter(Boolean) : []
  const nextIds = Array.isArray(lineIds) ? lineIds.map(normalizeSourceId).filter(Boolean) : []
  if (currentIds.length !== nextIds.length) return false
  return currentIds.every((id, index) => id === nextIds[index])
}

const rawGroups = ref([])
const drawableGroups = ref([])
const drawGroups = ref([])
let childOffsetMap = new Map()

const currentEffectiveCount = computed(() => rawGroups.value.length)
const currentVisibleCount = computed(() => drawableGroups.value.length)

const currentVisibleGroupItems = computed(() => (
  [...drawableGroups.value]
    .sort((a, b) => a.parentIndex - b.parentIndex || a.id.localeCompare(b.id))
    .map(group => ({
      id: group.id,
      name: modStore.displayModName(group.parentId) || group.parentId,
      color: group.color,
      childCount: group.childIndices.length,
    }))
))

const hiddenGroupItems = computed(() => {
  const currentGroupMap = new Map(rawGroups.value.map(group => [group.id, group]))
  return hiddenSourceIds.value
    .map(sourceId => {
      const currentGroup = currentGroupMap.get(sourceId)
      return {
        id: sourceId,
        name: modStore.displayModName(sourceId) || sourceId,
        color: currentGroup?.isError ? CONFIG.colorError : currentGroup?.color || hashSourceColor(sourceId),
        childCountLabel: currentGroup ? `${currentGroup.childIndices.length}项` : '历史项',
        inCurrentList: !!currentGroup,
      }
    })
    .sort((a, b) => {
      if (a.inCurrentList !== b.inCurrentList) return a.inCurrentList ? -1 : 1
      return a.name.localeCompare(b.name, 'zh-CN')
    })
})

const managerButtonTooltip = computed(() => {
  let text = `依赖线：${currentVisibleCount.value} / ${currentEffectiveCount.value}`
  if (hiddenSourceIds.value.length > 0) text += `\n已隐藏 ${hiddenSourceIds.value.length} 条依赖线`
  if (focusSourceId.value) text += '\n当前仅绘制 1 条依赖线'
  text += '\n\n__[[(点击打开依赖线管理面板)]]__'
  return text
})

const updateManagerPanelPosition = () => {
  if (!isManagerOpen.value) return
  if (typeof window === 'undefined' || !containerRef.value) return
  const rect = containerRef.value.getBoundingClientRect()
  const rootFontSize = Number.parseFloat(getComputedStyle(document.documentElement).fontSize) || 16
  const margin = rootFontSize * 0.75
  const gap = rootFontSize * 0.75
  const panelWidth = Math.min(rootFontSize * 25, Math.max(rootFontSize * 12, window.innerWidth - margin * 2))
  const panelHeight = Math.min(window.innerHeight * 0.76, window.innerHeight - margin * 2)

  let left = rect.left - panelWidth - gap
  if (left < margin) {
    left = rect.right + gap
  }
  left = Math.min(Math.max(margin, left), Math.max(margin, window.innerWidth - panelWidth - margin))

  let top = rect.top
  if (top + panelHeight > window.innerHeight - margin) {
    top = Math.max(margin, window.innerHeight - panelHeight - margin)
  }

  managerPanelStyle.value = {
    left: `${left}px`,
    top: `${top}px`,
  }
}

const toggleManagerPanel = () => {
  isManagerOpen.value = !isManagerOpen.value
  updateManagerPanelPosition()
}

const closeHover = () => {
  if (hoveredGroupId.value) hoveredGroupId.value = ''
  hoverStore.hide()
  if (canvasRef.value) canvasRef.value.style.cursor = 'default'
}

const getLinePayload = (group) => {
  if (!group) return []
  const childIds = group.childIndices.map(index => props.listIds[index]).filter(Boolean)
  return [group.parentId, ...childIds]
}

const getGroupById = (groupId) => drawGroups.value.find(group => group.id === groupId) || null

const isGroupActive = (group) => {
  if (!group) return false
  if (manualActiveGroupId.value === group.id) return true
  if (selectedIndicesSet.value.size === 0) return false
  for (const idx of group.allIndices) {
    if (selectedIndicesSet.value.has(idx)) return true
  }
  return false
}

const getHitGroup = (event) => {
  if (!canvasRef.value || !containerRef.value) return null

  const rect = containerRef.value.getBoundingClientRect()
  const x = event.clientX - rect.left
  const y = event.clientY - rect.top
  const scrollTop = getScrollOffset()
  const absoluteY = y + scrollTop
  const rowIndex = Math.floor(absoluteY / props.itemHeight)
  const laneXRaw = (x - CONFIG.baseX) / CONFIG.laneWidth
  const clickLane = Math.round(laneXRaw)

  if (Math.abs(clickLane - laneXRaw) > 0.6) return null
  if (clickLane < 0 || clickLane >= CONFIG.maxLanes) return null

  const geometricHits = drawGroups.value.filter(group => (
    group.visualLane === clickLane
    && rowIndex >= group.minIndex
    && rowIndex <= group.maxIndex
  ))
  if (geometricHits.length === 0) return null

  const activeHits = []
  const normalHits = []
  geometricHits.forEach(group => {
    if (isGroupActive(group)) activeHits.push(group)
    else normalHits.push(group)
  })

  if (activeHits.length > 0) return activeHits[activeHits.length - 1]
  if (normalHits.length > 0) return normalHits[normalHits.length - 1]
  return null
}

const assignDrawableGroups = (groupList) => {
  const lanes = []
  return groupList.map(group => {
    let logicalLane = -1
    for (let laneIndex = 0; laneIndex < lanes.length; laneIndex += 1) {
      if (lanes[laneIndex] < group.minIndex) {
        logicalLane = laneIndex
        lanes[laneIndex] = group.maxIndex
        break
      }
    }
    if (logicalLane === -1) {
      logicalLane = lanes.length
      lanes.push(group.maxIndex)
    }

    const visualLane = props.isFilter
      ? (CONFIG.maxLanes - 1) - (logicalLane % CONFIG.maxLanes)
      : logicalLane % CONFIG.maxLanes

    return {
      ...group,
      logicalLane,
      visualLane,
      color: group.isError ? CONFIG.colorError : CONFIG.colors[logicalLane % CONFIG.colors.length],
    }
  })
}

const rebuildChildOffsets = (groupsToDraw) => {
  childOffsetMap = new Map()
  const connectionMap = new Map()

  groupsToDraw.forEach(group => {
    group.childIndices.forEach(childIndex => {
      if (!connectionMap.has(childIndex)) connectionMap.set(childIndex, [])
      connectionMap.get(childIndex).push(group)
    })
  })

  connectionMap.forEach((groupArr, childIndex) => {
    groupArr.sort((a, b) => a.visualLane - b.visualLane)
    if (groupArr.length <= 1) return

    const step = 4
    const startY = -((groupArr.length - 1) * step) / 2
    const offsetLookup = new Map()

    groupArr.forEach((group, index) => {
      offsetLookup.set(group.id, startY + index * step)
    })
    childOffsetMap.set(childIndex, offsetLookup)
  })
}

const processGraph = () => {
  if (!props.listIds.length) {
    rawGroups.value = []
    drawableGroups.value = []
    drawGroups.value = []
    childOffsetMap = new Map()
    closeHover()
    manualActiveGroupId.value = ''
    return
  }

  const tempGroups = new Map()
  props.listIds.forEach((childId, childIndex) => {
    const mod = modStore.takeModById(childId)
    if (!mod || !Array.isArray(mod.dependencies_mods)) return

    mod.dependencies_mods.forEach(parentMod => {
      const parentId = normalizeSourceId(parentMod.package_id)
      if (!parentId || !listIndexMap.value.has(parentId)) return

      const parentIndex = listIndexMap.value.get(parentId)
      if (!tempGroups.has(parentId)) {
        tempGroups.set(parentId, {
          id: parentId,
          parentId,
          parentIndex,
          childIndices: [],
          allIndices: new Set([parentIndex]),
          isError: false,
        })
      }

      const group = tempGroups.get(parentId)
      group.childIndices.push(childIndex)
      group.allIndices.add(childIndex)
    })
  })

  const normalizedGroups = Array.from(tempGroups.values()).map(group => {
    group.childIndices.sort((a, b) => a - b)
    const allIndices = [group.parentIndex, ...group.childIndices]
    group.minIndex = Math.min(...allIndices)
    group.maxIndex = Math.max(...allIndices)
    if (group.minIndex < group.parentIndex) group.isError = true
    return group
  })

  normalizedGroups.sort((a, b) => {
    if (a.minIndex !== b.minIndex) return a.minIndex - b.minIndex
    const spanA = a.maxIndex - a.minIndex
    const spanB = b.maxIndex - b.minIndex
    return spanB - spanA
  })

  rawGroups.value = normalizedGroups
  drawableGroups.value = assignDrawableGroups(
    normalizedGroups.filter(group => !hiddenSourceIdSet.value.has(group.parentId))
  )
  drawGroups.value = focusSourceId.value
    ? drawableGroups.value.filter(group => group.id === focusSourceId.value)
    : drawableGroups.value

  if (focusSourceId.value && drawGroups.value.length === 0) {
    focusSourceId.value = ''
    drawGroups.value = drawableGroups.value
  }

  if (manualActiveGroupId.value && !drawGroups.value.some(group => group.id === manualActiveGroupId.value)) {
    manualActiveGroupId.value = ''
  }
  if (hoveredGroupId.value && !drawGroups.value.some(group => group.id === hoveredGroupId.value)) {
    closeHover()
  }

  rebuildChildOffsets(drawGroups.value)
}

const saveHiddenSourceIds = async (sourceIds) => {
  const normalizedIds = [...new Set((sourceIds || []).map(normalizeSourceId).filter(Boolean))]
  await appStore.saveSetting('ui', {
    ...appStore.settings.ui,
    hidden_dependency_graph_source_ids: normalizedIds,
  })
}

const toggleHiddenSource = async (sourceId) => {
  const normalizedId = normalizeSourceId(sourceId)
  if (!normalizedId) return

  const wasHidden = hiddenSourceIdSet.value.has(normalizedId)
  const nextIds = wasHidden
    ? hiddenSourceIds.value.filter(id => id !== normalizedId)
    : [...hiddenSourceIds.value, normalizedId]

  if (focusSourceId.value === normalizedId) focusSourceId.value = ''
  if (manualActiveGroupId.value === normalizedId) manualActiveGroupId.value = ''
  closeHover()

  await saveHiddenSourceIds(nextIds)
  toast.success(
    wasHidden
      ? `已恢复依赖线：${modStore.displayModName(normalizedId) || normalizedId}`
      : `已隐藏依赖线：${modStore.displayModName(normalizedId) || normalizedId}`,
    { timeout: 2000 }
  )
}

const restoreAllHiddenSources = async () => {
  if (hiddenSourceIds.value.length === 0) return
  await saveHiddenSourceIds([])
  toast.success('已恢复全部隐藏依赖线', { timeout: 2000 })
}

const jumpToSourceMod = async (group) => {
  if (!group?.parentId) return
  manualActiveGroupId.value = group.id
  modStore.currentTargetId = ''
  await nextTick()
  modStore.currentTargetId = group.parentId
}

const clearFocusSource = () => {
  focusSourceId.value = ''
  requestDraw()
}

const handleCanvasClick = (event) => {
  if (event.button !== 0) return

  const targetGroup = getHitGroup(event)
  if (targetGroup) {
    const active = isGroupActive(targetGroup)
    if (active) {
      emit('lineClick', getLinePayload(targetGroup))
      return
    }
    manualActiveGroupId.value = manualActiveGroupId.value === targetGroup.id ? '' : targetGroup.id
    return
  }

  manualActiveGroupId.value = ''
  emit('lineClick', [])
}

const handleMouseMove = (event) => {
  const group = getHitGroup(event)
  if (group) {
    if (canvasRef.value) canvasRef.value.style.cursor = 'pointer'
    if (hoveredGroupId.value !== group.id) {
      hoveredGroupId.value = group.id
      let content = `{{${group.color}|依赖源:}} ${modStore.displayModName(group.parentId)}\n包含 ${group.childIndices.length} 个子模组`
      if (group.isError) {
        content += '\n!!(⚠ 依赖源后置，依赖源应在所有需求模组前加载)!!'
      }
      content += '\n\n__[[(左键可筛选该依赖线，右键可隐藏或查看更多操作)]]__'
      hoverStore.show(content, event)
      return
    }
    hoverStore.updatePosition(event)
    return
  }

  closeHover()
}

const handleMouseLeave = () => {
  closeHover()
}

const openLineContextMenu = (event, group) => {
  const linePayload = getLinePayload(group)
  const lineFilterActive = isSameLineFilter(linePayload)
  const onlyThisLine = focusSourceId.value === group.id

  contextMenuStore.open(event, [
    {
      label: '隐藏该依赖线',
      icon: EyeOff,
      tooltip: '按依赖源模组全局隐藏这组依赖线。',
      action: () => toggleHiddenSource(group.id),
    },
    {
      label: '跳转到源头模组',
      icon: CornerUpRight,
      tooltip: '滚动并定位到当前依赖线的源头模组。',
      action: () => jumpToSourceMod(group),
    },
    {
      label: lineFilterActive ? '取消筛选该依赖线' : '筛选该依赖线',
      icon: lineFilterActive ? FilterX : Filter,
      tooltip: lineFilterActive ? '清除当前依赖线筛选。' : '只在列表中显示这组依赖线相关模组。',
      action: () => emit('lineClick', lineFilterActive ? [] : linePayload),
    },
    {
      label: onlyThisLine ? '显示全部线' : '仅显示该依赖线',
      icon: onlyThisLine ? Eye : Focus,
      tooltip: onlyThisLine ? '恢复绘制全部未隐藏依赖线。' : '临时只绘制这组依赖线，不影响列表内容。',
      action: () => { focusSourceId.value = onlyThisLine ? '' : group.id },
    },
    { divider: true },
    {
      label: '管理依赖线',
      icon: Settings2,
      tooltip: '打开依赖线管理面板，查看当前依赖线与已隐藏历史项。',
      action: () => {
        isManagerOpen.value = true
        updateManagerPanelPosition()
      },
    },
  ], {
    type: 'dependency-line',
    sourceId: group.id,
  })
}

const openCanvasContextMenu = (event) => {
  contextMenuStore.open(event, [
    {
      label: '管理依赖线',
      icon: Settings2,
      tooltip: '打开依赖线管理面板。',
      action: () => {
        isManagerOpen.value = true
        updateManagerPanelPosition()
      },
    },
    {
      label: '显示全部线',
      icon: Eye,
      hidden: !focusSourceId.value,
      tooltip: '清除“仅显示该依赖线”状态，恢复绘制全部未隐藏依赖线。',
      action: clearFocusSource,
    },
    {
      label: '恢复全部隐藏依赖线',
      icon: Undo2,
      hidden: hiddenSourceIds.value.length === 0,
      tooltip: '一次恢复当前已隐藏的全部依赖线。',
      action: restoreAllHiddenSources,
    },
  ], { type: 'dependency-canvas' })
}

const handleCanvasContextMenu = (event) => {
  const targetGroup = getHitGroup(event)
  if (targetGroup) {
    openLineContextMenu(event, targetGroup)
    return
  }
  openCanvasContextMenu(event)
}

let animationFrameId = 0
let scrollCleanup = null
const requestDraw = () => {
  if (animationFrameId) return
  animationFrameId = requestAnimationFrame(() => {
    animationFrameId = 0
    draw()
  })
}

const resolveScrollElement = () => {
  const target = props.scrollElement?.value || props.scrollElement
  const exposedEl = target?.$el?.value || target?.$el
  if (exposedEl?.addEventListener) return exposedEl
  if (target?.addEventListener) return target
  return null
}

const getScrollOffset = () => {
  const target = props.scrollElement?.value || props.scrollElement
  if (typeof target?.getOffset === 'function') return Number(target.getOffset() || 0)
  return Number(resolveScrollElement()?.scrollTop || 0)
}

const bindScrollListener = async () => {
  scrollCleanup?.()
  scrollCleanup = null
  await nextTick()
  const el = resolveScrollElement()
  if (!el?.addEventListener) {
    requestDraw()
    return
  }
  const handleScroll = () => requestDraw()
  el.addEventListener('scroll', handleScroll, { passive: true })
  scrollCleanup = () => el.removeEventListener('scroll', handleScroll)
  requestDraw()
}

const draw = () => {
  const canvas = canvasRef.value
  const ctx = canvas?.getContext('2d')
  if (!ctx) return

  const activeNodeBg = getThemeColor('--color-bg-inset', '#1e1e1e')
  // Canvas 内部存的是物理像素，但绘制和命中都按 CSS 像素计算，避免高分屏下线条与热点错位。
  const width = canvas.clientWidth || containerRef.value?.clientWidth || 0
  const height = canvas.clientHeight || containerRef.value?.clientHeight || 0
  if (!width || !height) return
  const scrollTop = getScrollOffset()
  const viewportStart = Math.floor(scrollTop / props.itemHeight)
  const viewportEnd = viewportStart + Math.ceil(height / props.itemHeight) + 1

  ctx.clearRect(0, 0, width, height)
  ctx.lineCap = 'round'
  ctx.lineJoin = 'round'

  const selectedIdLower = normalizeSourceId(lastSelectedId.value)
  const groupStates = drawGroups.value.map(group => {
    if (group.maxIndex < viewportStart - 1 || group.minIndex > viewportEnd + 1) {
      return { group, visible: false, isActive: false }
    }

    let isActive = false
    if (manualActiveGroupId.value === group.id) {
      isActive = true
    } else if (selectedIdLower) {
      if (group.parentId === selectedIdLower) isActive = true
      const selectedIndex = listIndexMap.value.get(selectedIdLower) ?? -1
      if (group.allIndices.has(selectedIndex)) isActive = true
    }

    return { group, visible: true, isActive }
  })

  const activeLanes = new Set()
  groupStates.forEach(state => {
    if (state.visible && state.isActive) activeLanes.add(state.group.visualLane)
  })

  const drawPass = (onlyActive) => {
    groupStates.forEach(state => {
      if (!state.visible) return
      if (onlyActive && !state.isActive) return
      if (!onlyActive && state.isActive) return

      const group = state.group
      const laneX = CONFIG.baseX + (group.visualLane * CONFIG.laneWidth)

      let alpha = CONFIG.alphaDimmed
      let lineWidth = CONFIG.lineWidthDimmed
      if (state.isActive) {
        alpha = CONFIG.alphaActive
        lineWidth = CONFIG.lineWidthActive
      } else if (activeLanes.has(group.visualLane)) {
        alpha = CONFIG.alphaHidden
      }

      ctx.globalAlpha = alpha
      ctx.strokeStyle = group.color
      ctx.fillStyle = group.color
      ctx.lineWidth = lineWidth

      const getY = (index) => (index * props.itemHeight + props.itemHeight / 2) - scrollTop
      const nodeX = width - 2

      if (group.maxIndex > group.minIndex) {
        const yMin = getY(group.minIndex)
        const yMax = getY(group.maxIndex)
        ctx.beginPath()
        ctx.moveTo(laneX, yMin + CONFIG.curveRadius)
        ctx.lineTo(laneX, yMax - CONFIG.curveRadius)
        ctx.stroke()
      }

      const yParent = getY(group.parentIndex)
      if (state.isActive) {
        ctx.fillStyle = activeNodeBg
        ctx.beginPath()
        ctx.arc(nodeX - CONFIG.rootRadius * 2, yParent, CONFIG.rootRadius + 2, 0, Math.PI * 2)
        ctx.fill()
        ctx.fillStyle = group.color
      }

      ctx.strokeStyle = group.color
      ctx.beginPath()
      ctx.arc(nodeX - CONFIG.rootRadius * 2 + 2, yParent, CONFIG.rootRadius, 0, Math.PI * 2)
      ctx.stroke()

      ctx.beginPath()
      ctx.moveTo(nodeX - CONFIG.rootRadius * 3, yParent)
      const radius = CONFIG.curveRadius
      if (group.isError && group.parentIndex > group.minIndex) {
        ctx.lineTo(laneX + radius, yParent)
        ctx.quadraticCurveTo(laneX, yParent, laneX, yParent - radius)
      } else {
        ctx.lineTo(laneX + radius, yParent)
        ctx.quadraticCurveTo(laneX, yParent, laneX, yParent + radius)
      }
      ctx.stroke()

      group.childIndices.forEach(childIndex => {
        if (childIndex < viewportStart - 1 || childIndex > viewportEnd + 1) return

        let yOffset = 0
        const offsets = childOffsetMap.get(childIndex)
        if (offsets?.has(group.id)) yOffset = offsets.get(group.id)

        const yChild = getY(childIndex) + yOffset

        ctx.beginPath()
        ctx.fillStyle = group.color
        ctx.arc(nodeX - CONFIG.nodeRadius * 2, yChild, CONFIG.nodeRadius, 0, Math.PI * 2)
        ctx.fill()

        ctx.beginPath()
        if (group.isError && childIndex < group.parentIndex) {
          ctx.moveTo(laneX, yChild + radius)
          ctx.quadraticCurveTo(laneX, yChild, laneX + radius, yChild)
        } else {
          ctx.moveTo(laneX, yChild - radius)
          ctx.quadraticCurveTo(laneX, yChild, laneX + radius, yChild)
        }
        ctx.lineTo(nodeX - CONFIG.nodeRadius * 3, yChild)
        ctx.stroke()
      })
    })
  }

  drawPass(false)
  drawPass(true)
  ctx.globalAlpha = 1
}

const resizeObserver = new ResizeObserver(entries => {
  const { width, height } = entries[0].contentRect
  const dpr = window.devicePixelRatio || 1
  if (canvasRef.value) {
    const ctx = canvasRef.value.getContext('2d')
    canvasRef.value.width = width * dpr
    canvasRef.value.height = height * dpr
    canvasRef.value.style.width = `${width}px`
    canvasRef.value.style.height = `${height}px`
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    requestDraw()
  }
  updateManagerPanelPosition()
})

watch(() => props.listIds, () => {
  manualActiveGroupId.value = ''
  processGraph()
  requestDraw()
}, { deep: true, immediate: true })

watch(
  () => [props.isFilter, hiddenSourceIdsKey.value, focusSourceId.value],
  () => {
    processGraph()
    requestDraw()
    updateManagerPanelPosition()
  }
)

watch(() => props.scrollElement, () => {
  bindScrollListener()
}, { immediate: true })

watch(
  () => [
    props.itemHeight,
    lastSelectedId.value,
    Array.isArray(modStore.selectedIds) ? modStore.selectedIds.join('|') : '',
    manualActiveGroupId.value,
  ],
  () => requestDraw()
)

watch(isManagerOpen, () => {
  updateManagerPanelPosition()
})

onMounted(() => {
  if (containerRef.value) resizeObserver.observe(containerRef.value)
  bindScrollListener()
  window.addEventListener('resize', updateManagerPanelPosition)
  requestDraw()
})

onUnmounted(() => {
  if (animationFrameId) cancelAnimationFrame(animationFrameId)
  scrollCleanup?.()
  resizeObserver.disconnect()
  window.removeEventListener('resize', updateManagerPanelPosition)
  closeHover()
})
</script>
