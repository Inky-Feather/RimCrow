<template>
  <div
    ref="scrollRef"
    class="overflow-auto"
    @dragover="handleDragOver"
    @drop="handleDrop"
    @dragleave="handleDragLeave"
  >
    <!-- TanStack Virtual 只渲染视口附近的行。 外层占位高度必须等于虚拟总高度，内部每个可见行再用 translateY 放到真实位置。 -->
    <div :class="wrapClass" :style="{ height: `${totalSize}px`, position: 'relative' }">
      <div v-for="virtualRow in virtualItems" :key="getRowKey(virtualRow.index)" class="absolute left-0 right-0"
        :style="{ transform: `translateY(${virtualRow.start}px)`, height: `${virtualRow.size}px` }">
        <div :data-drag-list-id="listId" :data-drag-index="virtualRow.index" :draggable="false" class="h-full"
          @pointerdown.capture="event => armDrag(event, virtualRow.index)"
          @pointerup.capture="clearDragArm"
          @pointercancel.capture="clearDragArm"
          @dragstart="event => handleDragStart(event, virtualRow.index)"
        >
          <!-- 插槽只负责渲染行内容；拖拽、滚动、落点换算都在本组件统一处理。 业务组件需要把真正可拖拽的实体标为 .select-trigger 或 .drag-handle。 -->
          <slot name="item" :record="items[virtualRow.index]" :index="virtualRow.index"
            :dataKey="getRowKey(virtualRow.index)"
          />
        </div>
      </div>

      <div v-if="dropIndex !== -1"
        class="pointer-events-none absolute left-1 right-1 z-40 h-0.5 rounded-full bg-accent-special shadow-[0_0_8px_var(--color-accent-special)]"
        :style="{ top: `${dropIndicatorTop}px` }" >
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { useVirtualizer } from '@tanstack/vue-virtual'
import { cancelLongPressFeedback, completeLongPressFeedback, showLongPressFeedback } from '../../directives/vLongPressFeedback'
import { t } from '../../i18n.js'

const props = defineProps({
  modelValue: { type: Array, default: () => [] },
  dataKey: { type: String, required: true },
  size: { type: Number, default: 34 },
  keeps: { type: Number, default: 50 },
  wrapClass: { type: [String, Array, Object], default: '' },
  draggable: { type: Boolean, default: true },
  droppable: { type: Boolean, default: true },
  disabled: { type: Boolean, default: false },
  group: { type: [Object, String], default: null },
  // 允许父组件在拖拽真正开始时补充动态元数据。
  // 例如多选数量会频繁变化，如果把 dragCount 写进虚拟列表行数据，会导致整段 row 流随选择状态重算。
  getDragMeta: { type: Function, default: null },
  // 与旧拖拽库的 drag_delay 设置对齐。原生 HTML5 拖拽没有内建延迟，这里用 pointerdown 计时模拟。
  delay: { type: Number, default: 0 },
})

const emit = defineEmits(['drag', 'drop', 'dragend'])

const scrollRef = ref(null)
const dropIndex = ref(-1)
const listId = `vdl-${Math.random().toString(36).slice(2)}`
let dragFrame = 0
let dragClientY = null
const dragArmedIndex = ref(-1)
let dragArmTimer = 0
let armedTriggerEl = null
let dragPointerOffset = { x: 12, y: 12 }

const items = computed(() => Array.isArray(props.modelValue) ? props.modelValue : [])
const rowSize = computed(() => Number(props.size) || 34)
const canDrag = computed(() => !!props.draggable && !props.disabled)
const rowSizes = computed((previous) => {
  // 把每行高度集中缓存成简单数字数组。
  // TanStack Virtual 在滚动过程中会频繁询问 estimateSize；这里避免每次都重新访问 row 对象和响应式 props。
  const fallback = rowSize.value
  const sizes = items.value.map(item => {
    const itemSize = Number(item?.rowSize)
    return itemSize > 0 ? itemSize : fallback
  })
  // 等高行换序不改变尺寸，保留缓存，避免重新测量整份列表。
  return previous?.length === sizes.length && sizes.every((size, index) => size === previous[index]) ? previous : sizes
})
const getItemSize = (index) => {
  // 默认列表是固定行高；分组列表会给“分组标题行”单独传 rowSize，用于制造分组间距。
  return rowSizes.value[index] || rowSize.value
}
const isDragDelaySatisfied = (index) => Number(props.delay) <= 0 || dragArmedIndex.value === index

const virtualizer = useVirtualizer(computed(() => ({
  count: items.value.length,
  getScrollElement: () => scrollRef.value,
  estimateSize: getItemSize,
  overscan: Math.max(5, Math.ceil((Number(props.keeps) || 50) / 4)),
})))

const virtualItems = computed(() => virtualizer.value.getVirtualItems())
const rowOffsets = computed(() => {
  // drop 指示线和落点换算都依赖“行起点表”。
  // 这里把 O(n) 的行高累加集中到响应式缓存里，避免 dragover 每一帧都重新扫描 5000 行。
  const offsets = [0]
  const sizes = rowSizes.value
  for (let index = 0; index < sizes.length; index++) {
    offsets.push(offsets[index] + sizes[index])
  }
  return offsets
})
const totalSize = computed(() => rowOffsets.value[items.value.length] ?? virtualizer.value.getTotalSize())
const dropIndicatorTop = computed(() => {
  if (dropIndex.value < 0) return 0
  const index = Math.max(0, Math.min(dropIndex.value, items.value.length))
  return rowOffsets.value[index] ?? totalSize.value
})

const getRowKey = (index) => {
  const item = items.value[index]
  return item?.[props.dataKey] ?? item?.id ?? index
}

watch(rowSizes, async () => {
  await nextTick()
  // 行高由父组件传入；视图切换、全局缩放或分组标题间距变化后必须主动刷新 TanStack 的尺寸缓存。
  virtualizer.value.measure()
})

const getOffset = () => scrollRef.value?.scrollTop || 0
const scrollToOffset = (offset = 0, options = {}) => {
  if (!scrollRef.value) return
  const top = Math.max(0, Number(offset) || 0)
  if (options.behavior === 'smooth') {
    scrollRef.value.scrollTo({ top, behavior: 'smooth' })
    return
  }
  scrollRef.value.scrollTop = top
}
const scrollToIndex = (index = 0, options = {}) => {
  // 搜索/定位时默认把目标放到视口中央，用户更容易在上下文中确认目标位置。
  // TanStack Virtual 会自动夹住顶部/底部边界：目标靠近列表首尾时不会强行留出不存在的空白。
  const align = options.align || 'center'
  const targetIndex = Math.max(0, Number(index) || 0)
  if (options.behavior === 'smooth' && scrollRef.value) {
    const start = rowOffsets.value[targetIndex] || 0
    const size = getItemSize(targetIndex)
    const viewHeight = scrollRef.value.clientHeight || 0
    const rawOffset = align === 'start'
      ? start
      : align === 'end'
        ? start + size - viewHeight
        : start - ((viewHeight - size) / 2)
    const maxOffset = Math.max(0, totalSize.value - viewHeight)
    scrollToOffset(Math.max(0, Math.min(rawOffset, maxOffset)), { behavior: 'smooth' })
    return
  }
  virtualizer.value.scrollToIndex(targetIndex, { align })
}
const scrollToKey = async (key, options = {}) => {
  const index = items.value.findIndex(item => String(item?.[props.dataKey]) === String(key))
  if (index === -1) return
  await nextTick()
  scrollToIndex(index, options)
}
defineExpose({
  getOffset,
  scrollToOffset,
  scrollToIndex,
  scrollToKey,
  cancelDrag: () => handleDragEnd(),
  $el: scrollRef,
})

const normalizeGroupName = (group) => {
  if (!group) return ''
  if (typeof group === 'string') return group
  return String(group.name || '')
}

const canPutFrom = (sourceGroup) => {
  if (props.disabled || !props.droppable) return false
  const put = props.group?.put
  if (put === false) return false
  if (put === true || put == null) return true
  if (Array.isArray(put)) return put.includes(sourceGroup)
  return String(put) === sourceGroup
}

const canPutSessionAt = (session, index) => {
  // 第一层是跨列表组名判断，兼容 SortableJS 风格的 group.put。
  if (!session || !canPutFrom(session.sourceGroup)) return false
  const targetItem = items.value[Math.max(0, Math.min(index, items.value.length - 1))]
  // 第二层是业务落点判断，例如“分组整体只能落在分组标题之间，不能落入分组内容行”。
  if (typeof props.group?.canPut === 'function') {
    return !!props.group.canPut(session, targetItem, index, items.value)
  }
  return true
}

const buildDragEvent = (index) => ({
  item: window.__VIRTUAL_DRAG_SESSION__.item,
  // index 始终是源项尚未移除时的视觉插入点，业务层只换算一次。
  index,
  sameList: window.__VIRTUAL_DRAG_SESSION__.sourceListId === listId,
})

const createDragPreview = (event, item, sourceEl, pointerOffset = null) => {
  if (!event.dataTransfer || typeof document === 'undefined') return
  const count = Math.max(1, Number(item?.dragCount) || 1)
  const rect = sourceEl?.getBoundingClientRect?.()
  const el = document.createElement('div')
  const card = sourceEl?.cloneNode?.(true)
  // dragstart 事件在部分浏览器里会把 clientX/clientY 归零或做兼容修正；
  // 因此偏移量必须用 pointerdown 当下记录的“鼠标在卡片内的位置”，才能保证虚影不跳。
  const pointerOffsetX = pointerOffset?.x ?? (rect ? Math.max(0, Math.min(event.clientX - rect.left, rect.width)) : 12)
  const pointerOffsetY = pointerOffset?.y ?? (rect ? Math.max(0, Math.min(event.clientY - rect.top, rect.height)) : 12)
  el.style.cssText = [
    'position:fixed',
    'top:-1000px',
    'left:-1000px',
    `width:${Math.max(160, Math.min(rect?.width || 260, 420))}px`,
    `height:${Math.max(rect?.height || 34, 24)}px`,
    'pointer-events:none',
    'transform:translateZ(0)',
  ].join(';')
  if (card) {
    // 克隆用户实际点住的卡片实体
    card.removeAttribute('draggable')
    card.style.cssText = [
      'position:relative',
      'z-index:3',
      'width:100%',
      'opacity:0.99',
      'background:rgba(var(--rgb-text-dim),0.5)',
      'filter:drop-shadow(0 14px 22px var(--shadow-color))',
      'transform:scale(1)',
      'transform-origin:top left',
    ].join(';')
    el.appendChild(card)
  } else {
    el.textContent = String(item?.dragLabel || item?.name || item?.id || item?.[props.dataKey] || t('common.entity.drag_item', '拖拽项目'))
  }
  if (count > 1) {
    // 多选时保留触发拖拽的真实卡片作为最上层，底下用卡堆表示批量操作。
    for (let i = 0; i < 4; i++) {
      const inset = (i + 1) * 2
      const down = (i + 1) * 4
      const layer = document.createElement('div')
      layer.style.cssText = [
        'position:absolute',
        `left:${inset}px`,
        `right:${-inset}px`,
        `top:${down}px`,
        `bottom:${-down}px`,
        'z-index:' + (4 - i),
        'border-radius:5px',
        'background:var(--color-border-subtle)',
        'border:1px solid var(--color-border-strong)',
      ].join(';')
      el.insertBefore(layer, el.firstChild)
    }
    const badge = document.createElement('span')
    badge.textContent = String(count)
    badge.style.cssText = [
      'position:absolute',
      'right:-8px',
      'top:-8px',
      'z-index:4',
      'display:flex',
      'align-items:center',
      'justify-content:center',
      'min-width:22px',
      'height:22px',
      'padding:0 6px',
      'border-radius:999px',
      'background:var(--color-accent-special)',
      'color:var(--color-on-accent-special)',
      'font-weight:700',
      'font-size:12px',
      'line-height:22px',
      'box-shadow:0 4px 14px var(--shadow-color)',
    ].join(';')
    el.appendChild(badge)
  }
  document.body.appendChild(el)
  event.dataTransfer.setDragImage(el, pointerOffsetX, pointerOffsetY)
  setTimeout(() => el.remove(), 0)
}

const resolveDragTrigger = (event) => {
  const wrapper = event.currentTarget
  const target = event.target
  if (!wrapper?.contains?.(target)) return null
  const trigger = target.closest?.('.select-trigger')
  const handle = target.closest?.('.drag-handle')
  const interactive = target.closest?.('button,input,textarea,select,a,[contenteditable="true"],.no-drag')
  if (interactive && wrapper.contains(interactive) && (!handle || handle.contains(interactive))) {
    return null
  }
  // 拖拽柄只负责“允许启动拖拽”；虚影和偏移仍优先绑定到所在卡片，避免只拖出一个小图标。
  if (handle && wrapper.contains(handle)) {
    return trigger && wrapper.contains(trigger) ? trigger : handle
  }
  if (!trigger || !wrapper.contains(trigger)) return null
  return trigger
}

const clearDragArm = () => {
  const wasPending = !!dragArmTimer
  if (dragArmTimer) {
    clearTimeout(dragArmTimer)
    dragArmTimer = 0
  }
  if (armedTriggerEl) {
    armedTriggerEl.removeAttribute('draggable')
    armedTriggerEl = null
  }
  dragArmedIndex.value = -1
  if (wasPending) cancelLongPressFeedback()
}

const enableNativeDragOnTrigger = (triggerEl, index) => {
  // 原生 HTML5 拖拽只能从 draggable 元素启动。
  // 行容器本身不能设为 draggable，否则边距、序号列和空白背景也会进入拖拽判定。
  armedTriggerEl = triggerEl
  armedTriggerEl.setAttribute('draggable', 'true')
  dragArmedIndex.value = index
}

const armDrag = (event, index) => {
  const triggerEl = resolveDragTrigger(event)
  if (!canDrag.value || !triggerEl) {
    clearDragArm()
    return
  }
  const rect = triggerEl.getBoundingClientRect?.()
  dragPointerOffset = rect
    ? {
        x: Math.max(0, Math.min(event.clientX - rect.left, rect.width)),
        y: Math.max(0, Math.min(event.clientY - rect.top, rect.height)),
      }
    : { x: 12, y: 12 }
  const delay = Math.max(0, Number(props.delay) || 0)
  if (delay <= 0) {
    enableNativeDragOnTrigger(triggerEl, index)
    return
  }
  clearDragArm()
  showLongPressFeedback(event, delay)
  dragArmTimer = window.setTimeout(() => {
    enableNativeDragOnTrigger(triggerEl, index)
    completeLongPressFeedback()
    dragArmTimer = 0
  }, delay)
}

const handleDragStart = (event, index) => {
  if (!canDrag.value || !isDragDelaySatisfied(index)) {
    event.preventDefault()
    return
  }
  const item = items.value[index]
  const triggerEl = resolveDragTrigger(event)
  if (item?.draggable === false || !triggerEl) {
    event.preventDefault()
    return
  }
  const dragMeta = typeof props.getDragMeta === 'function' ? (props.getDragMeta(item, index) || {}) : {}
  // 会话项保持原业务行数据不变，只在拖拽开始的瞬间叠加数量、标签等展示元信息。
  // 这样选择状态变化不会反向污染虚拟列表结构，也能保证拖拽预览拿到最新状态。
  const sessionItem = { ...item, ...dragMeta }
  window.__VIRTUAL_DRAG_SESSION__ = {
    item: sessionItem,
    sourceListId: listId,
    sourceGroup: sessionItem?.dragGroup || normalizeGroupName(props.group),
    end: handleDragEnd,
  }
  event.dataTransfer.effectAllowed = 'copyMove'
  event.dataTransfer.setData('text/plain', String(sessionItem?.[props.dataKey] ?? sessionItem?.id ?? ''))
  createDragPreview(event, sessionItem, triggerEl, dragPointerOffset)
  emit('drag', buildDragEvent(index))
}

const resolveDropIndex = (clientY, rect) => {
  const el = scrollRef.value
  if (!el) return items.value.length
  const offsetY = clientY - rect.top + el.scrollTop
  if (offsetY <= 0) return 0
  const offsets = rowOffsets.value
  const itemCount = items.value.length
  const total = offsets[itemCount] ?? 0
  if (offsetY >= total) return itemCount
  // 支持逐行高度后不能再用 offset / rowSize。这里按半行位置决定“插到该行前”还是“该行后”。
  // 二分查找能把拖拽过程中的落点换算从 O(n) 降到 O(log n)，对 5000 行长列表更稳。
  let low = 0
  let high = itemCount
  while (low < high) {
    const mid = Math.floor((low + high) / 2)
    const midpoint = ((offsets[mid] ?? 0) + (offsets[mid + 1] ?? 0)) / 2
    if (offsetY < midpoint) high = mid
    else low = mid + 1
  }
  return low
}

const stopDragTracking = () => {
  if (dragFrame) cancelAnimationFrame(dragFrame)
  dragFrame = 0
  dragClientY = null
  dropIndex.value = -1
}

const runDragFrame = () => {
  dragFrame = 0
  const el = scrollRef.value
  const session = window.__VIRTUAL_DRAG_SESSION__
  if (!el || dragClientY === null || !session || !canPutFrom(session.sourceGroup)) {
    stopDragTracking()
    return
  }
  // 落点与边缘滚动共用一次布局读取；滚动后立即更新指示线。
  const rect = el.getBoundingClientRect()
  const threshold = Math.min(72, Math.max(28, rect.height / 4))
  let velocity = 0
  if (dragClientY < rect.top + threshold) {
    velocity = -Math.ceil(Math.min(1, 1 - (dragClientY - rect.top) / threshold) * 18)
  } else if (dragClientY > rect.bottom - threshold) {
    velocity = Math.ceil(Math.min(1, 1 - (rect.bottom - dragClientY) / threshold) * 18)
  }
  const previousScrollTop = el.scrollTop
  if (velocity) el.scrollTop += velocity
  const index = resolveDropIndex(dragClientY, rect)
  dropIndex.value = canPutSessionAt(session, index) ? index : -1
  if (el.scrollTop !== previousScrollTop) dragFrame = requestAnimationFrame(runDragFrame)
}

const handleDragOver = (event) => {
  const session = window.__VIRTUAL_DRAG_SESSION__
  if (!session || !canPutFrom(session.sourceGroup)) {
    stopDragTracking()
    return
  }
  event.preventDefault()
  dragClientY = event.clientY
  if (event.dataTransfer) {
    event.dataTransfer.dropEffect = session.sourceGroup === normalizeGroupName(props.group) ? 'move' : 'copy'
  }
  if (!dragFrame) dragFrame = requestAnimationFrame(runDragFrame)
}

const handleDragLeave = (event) => {
  if (!scrollRef.value?.contains(event.relatedTarget)) {
    stopDragTracking()
  }
}

const handleDrop = (event) => {
  const session = window.__VIRTUAL_DRAG_SESSION__
  event.preventDefault()
  if (session) event.stopPropagation()
  if (!session || !canPutFrom(session.sourceGroup)) return
  const el = scrollRef.value
  if (!el) {
    session.end()
    return
  }
  const index = resolveDropIndex(event.clientY, el.getBoundingClientRect())
  stopDragTracking()
  if (!canPutSessionAt(session, index)) {
    session.end()
    return
  }
  const payload = buildDragEvent(index)
  session.end()
  emit('drop', payload)
}

const handleDragEnd = () => {
  stopDragTracking()
  clearDragArm()
  if (window.__VIRTUAL_DRAG_SESSION__?.sourceListId !== listId) return
  window.__VIRTUAL_DRAG_SESSION__ = null
  emit('dragend')
}

onMounted(() => window.addEventListener('dragend', handleDragEnd))
onBeforeUnmount(() => {
  window.removeEventListener('dragend', handleDragEnd)
  handleDragEnd()
})
</script>
