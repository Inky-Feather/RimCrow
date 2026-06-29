<!-- src/components/common/FixedPopover.vue -->
<template>
  <Teleport to="body">
    <Transition name="popover-fade">
      <div v-if="isOpen" ref="popoverRef" class="fixed" data-fixed-popover :style="containerStyle">
        <template v-if="framed">
          <div :class="surfaceWrapperClass">
            <div class="min-h-0 overflow-hidden rounded-xl border border-border-base/10 bg-glass-medium backdrop-blur-xl" :style="contentStyle">
              <div class="min-h-0" :class="scrollable ? 'overflow-y-auto custom-scrollbar' : 'overflow-visible'" :style="scrollBodyStyle">
                <slot></slot>
              </div>
            </div>
          </div>
        </template>
        <template v-else>
          <div :class="surfaceWrapperClass">
            <slot></slot>
          </div>
        </template>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
import { ref, watch, nextTick, onUnmounted, computed } from 'vue'
import { useAppStore } from '../../../app/stores/appStore'

const emit = defineEmits(['request-close'])
const props = defineProps({
  isOpen: Boolean,
  triggerRef: Object,      // 触发按钮的 DOM
  width: { type: [Number, String], default: null }, // 传 trigger 时与触发器同宽；留空则由内容自适应。
  minWidth: { type: [Number, String], default: 0 }, // 默认按内容自然撑开，需要同宽时显式传 trigger。
  maxWidth: { type: [Number, String], default: 0 },   // 0 表示自动使用窗口剩余宽度。
  height: { type: [Number, String], default: null },  // 传 available/max/full 时填满当前可用高度，内部 h-full 才有确定父高度。
  maxHeight: { type: [Number, String], default: 450 },
  offset: { type: [Number, String], default: 8 },
  scrollable: { type: Boolean, default: true },
  framed: { type: Boolean, default: false },          // 默认只负责定位与关闭，视觉壳由调用处决定。
  placement: { type: String, default: 'auto' },       // auto | bottom | top
  align: { type: String, default: 'start' },          // start | center | end
  zIndex: { type: [Number, String], default: 8000 },
  // 下拉/浮层的大多数场景都需要默认可关闭，特殊场景再由调用方显式关闭。
  closeOnOutside: { type: Boolean, default: true },
  closeOnEscape: { type: Boolean, default: true },
  closeOnOtherPopover: { type: Boolean, default: false },
})

const appStore = useAppStore()
const popoverRef = ref(null)
const scrollParents = ref([])
const clipParents = ref([])
const positionState = ref({
  left: 0,
  top: 0,
  width: null,
  minWidth: 0,
  maxWidth: 0,
  height: null,
  maxHeight: 400,
  isFlipped: false
})

const getRootFontSize = () => Number.parseFloat(getComputedStyle(document.documentElement).fontSize || '16')

const resolveCssLengthToPx = (value, basisPx, fallbackPx = 0, options = {}) => {
  if (value === null || value === undefined || value === '') return fallbackPx
  if (typeof value === 'number') return appStore.scalePx(value)

  const raw = String(value).trim().toLowerCase()
  if (options.presets && Object.prototype.hasOwnProperty.call(options.presets, raw)) {
    return options.presets[raw]
  }
  if (!raw || raw === 'auto' || raw === 'none') return fallbackPx

  const numeric = Number.parseFloat(raw)
  if (!Number.isFinite(numeric)) return fallbackPx
  if (raw.endsWith('%')) return basisPx * numeric / 100
  if (raw.endsWith('vw')) return window.innerWidth * numeric / 100
  if (raw.endsWith('vh')) return window.innerHeight * numeric / 100
  if (raw.endsWith('rem')) return getRootFontSize() * numeric
  if (raw.endsWith('em')) return getRootFontSize() * numeric
  if (raw.endsWith('px')) return numeric
  if (/^-?\d+(\.\d+)?$/.test(raw)) return options.scaleBareNumber === false ? numeric : appStore.scalePx(numeric)
  return fallbackPx
}

const resolveOffsetPx = (value) => resolveCssLengthToPx(value, window.innerHeight, 8)

const resolveTriggerEl = () => {
  const trigger = props.triggerRef
  if (trigger && typeof trigger.getBoundingClientRect === 'function') return trigger
  const el = trigger?.value
  return el && typeof el.getBoundingClientRect === 'function' ? el : null
}

const isScrollableElement = (el) => {
  if (!(el instanceof HTMLElement)) return false
  const style = getComputedStyle(el)
  const overflowValue = `${style.overflow} ${style.overflowX} ${style.overflowY}`
  return /(auto|scroll|overlay)/.test(overflowValue)
}

const isClippingElement = (el) => {
  if (!(el instanceof HTMLElement)) return false
  const style = getComputedStyle(el)
  const overflowValue = `${style.overflow} ${style.overflowX} ${style.overflowY}`
  return /(auto|scroll|overlay|hidden|clip)/.test(overflowValue)
}

const collectScrollParents = (el) => {
  const parents = []
  let current = el?.parentElement || null
  while (current) {
    if (isScrollableElement(current)) parents.push(current)
    current = current.parentElement
  }
  parents.push(window)
  return parents
}

const collectClipParents = (el) => {
  const parents = []
  let current = el?.parentElement || null
  while (current) {
    if (isClippingElement(current)) parents.push(current)
    current = current.parentElement
  }
  return parents
}

const hasRectIntersection = (a, b) => a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top

const isTriggerVisible = (triggerEl) => {
  if (!triggerEl || !document.documentElement.contains(triggerEl)) return false

  const rect = triggerEl.getBoundingClientRect()
  if (rect.width <= 0 || rect.height <= 0) return false

  const viewportRect = { left: 0, top: 0, right: window.innerWidth, bottom: window.innerHeight }
  if (!hasRectIntersection(rect, viewportRect)) return false

  return clipParents.value.every((parent) => {
    const parentRect = parent.getBoundingClientRect()
    return hasRectIntersection(rect, parentRect)
  })
}

const getHorizontalAnchor = (rect, width) => {
  if (props.align === 'end') return rect.right - width
  if (props.align === 'center') return rect.left + (rect.width - width) / 2
  return rect.left
}

const shouldFlipToTop = (spaceBelow, spaceAbove, preferredMaxHeight) => {
  if (props.placement === 'top') return true
  if (props.placement === 'bottom') return false
  return spaceBelow < Math.min(preferredMaxHeight, 200) && spaceAbove > spaceBelow
}

// --- 核心定位算法 ---
const updatePosition = () => {
  const triggerEl = resolveTriggerEl()
  if (!triggerEl || !props.isOpen) return
  if (!isTriggerVisible(triggerEl)) {
    emit('request-close', { reason: 'trigger-out-of-view' })
    return
  }

  const rect = triggerEl.getBoundingClientRect()
  const viewW = window.innerWidth
  const viewH = window.innerHeight
  const margin = appStore.scalePx(12) // 距离窗口边缘的硬性安全距离
  const scaledOffset = resolveOffsetPx(props.offset)
  const widthPresets = { trigger: rect.width }

  // --- 1. 确定水平位置与最大宽度 ---
  // 基础最小宽度默认不绑定触发器，只在显式传入时才生效。
  const preferredMinWidth = resolveCssLengthToPx(props.minWidth, viewW, 0, {
    presets: widthPresets
  })
  const baseMinWidth = Math.max(0, Math.min(preferredMinWidth, viewW - margin * 2))
  const preferredWidth = resolveCssLengthToPx(props.width, viewW, rect.width, {
    presets: widthPresets
  })
  const requestedWidth = preferredWidth > 0 ? Math.max(baseMinWidth, preferredWidth) : null
  const resolveLeft = (width) => {
    let value = getHorizontalAnchor(rect, width)
    if (value + width > viewW - margin) {
      value = viewW - width - margin
    }
    return Math.max(margin, value)
  }

  let anchorWidth = requestedWidth || baseMinWidth
  let left = resolveLeft(anchorWidth)

  // 最大宽度会先按用户传入值解析，再被当前窗口剩余空间截断。
  let availableWidth = viewW - left - margin
  let preferredMaxWidth = resolveCssLengthToPx(props.maxWidth, viewW, availableWidth)
  let finalMaxWidth = Math.max(baseMinWidth, Math.min(preferredMaxWidth > 0 ? preferredMaxWidth : availableWidth, availableWidth))
  let finalWidth = requestedWidth ? Math.max(baseMinWidth, Math.min(requestedWidth, finalMaxWidth)) : null

  // 显式宽度被 maxWidth 或窗口空间截断后，重新按最终宽度对齐一次，避免居中/右对齐漂移。
  if (finalWidth && finalWidth !== anchorWidth) {
    anchorWidth = finalWidth
    left = resolveLeft(anchorWidth)
    availableWidth = viewW - left - margin
    preferredMaxWidth = resolveCssLengthToPx(props.maxWidth, viewW, availableWidth)
    finalMaxWidth = Math.max(baseMinWidth, Math.min(preferredMaxWidth > 0 ? preferredMaxWidth : availableWidth, availableWidth))
    finalWidth = Math.max(baseMinWidth, Math.min(requestedWidth, finalMaxWidth))
  }

  // --- 2. 确定垂直位置与最大高度 ---
  const spaceBelow = viewH - rect.bottom - scaledOffset - margin
  const spaceAbove = rect.top - scaledOffset - margin
  const preferredMaxH = Math.max(1, resolveCssLengthToPx(props.maxHeight, viewH, 450))

  let isFlipped = false
  let finalMaxHeight = 0
  let top = 0

  // 翻转逻辑：下方空间不足且上方空间更大
  if (shouldFlipToTop(spaceBelow, spaceAbove, preferredMaxH)) {
    isFlipped = true
    top = rect.top - scaledOffset
    finalMaxHeight = Math.max(1, Math.min(preferredMaxH, spaceAbove))
  } else {
    isFlipped = false
    top = rect.bottom + scaledOffset
    finalMaxHeight = Math.max(1, Math.min(preferredMaxH, spaceBelow))
  }

  const requestedHeight = String(props.height || '').trim().toLowerCase()
  const shouldUseAvailableHeight = ['available', 'max', 'full'].includes(requestedHeight)
  const preferredHeight = shouldUseAvailableHeight ? finalMaxHeight : resolveCssLengthToPx(props.height, viewH, 0)
  const finalHeight = props.height ? Math.max(1, Math.min(preferredHeight, finalMaxHeight)) : null

  // --- 3. 原子化更新状态 ---
  positionState.value = {
    left,
    top,
    width: finalWidth,
    minWidth: baseMinWidth,
    maxWidth: finalMaxWidth,
    height: finalHeight,
    maxHeight: finalMaxHeight,
    isFlipped
  }
}

// 样式计算属性
const containerStyle = computed(() => ({
  left: `${positionState.value.left}px`,
  top: `${positionState.value.top}px`,
  width: positionState.value.width ? `${positionState.value.width}px` : undefined,
  minWidth: positionState.value.minWidth > 0 ? `${positionState.value.minWidth}px` : undefined,
  maxWidth: `${positionState.value.maxWidth}px`,
  transform: positionState.value.isFlipped ? 'translateY(-100%)' : 'none',
  overflow: 'visible',
  zIndex: props.zIndex
}))

const surfaceWrapperClass = computed(() => ([
  'w-fit max-w-full',
  'rounded-xl shadow-[0_18px_50px_var(--shadow-color)]'
]))

const contentStyle = computed(() => ({
  height: positionState.value.height ? `${positionState.value.height}px` : undefined,
  maxHeight: `${positionState.value.maxHeight}px`
}))

const scrollBodyStyle = computed(() => ({
  height: positionState.value.height ? '100%' : undefined,
  maxHeight: `${positionState.value.maxHeight}px`
}))

// 监听与事件
watch(() => props.isOpen, async (val) => {
  if (val) {
    await nextTick()
    if (!resolveTriggerEl()) return
    updatePosition()
    // 使用 requestAnimationFrame 代替 setTimeout，防止布局抖动产生的递归
    requestAnimationFrame(updatePosition)
  }
})

const handleScroll = (e) => {
  // 如果滚动发生在 Popover 内部，不触发重新定位，防止死循环
  if (popoverRef.value?.contains(e.target)) return
  const triggerEl = resolveTriggerEl()
  if (!isTriggerVisible(triggerEl)) {
    emit('request-close', { reason: 'trigger-out-of-view' })
    return
  }
  updatePosition()
}

const handleDocumentPointerDown = (event) => {
  if (!props.closeOnOutside || !props.isOpen) return
  const target = event.target
  const triggerEl = resolveTriggerEl()
  if (popoverRef.value?.contains(target)) return
  if (triggerEl?.contains?.(target) || target === triggerEl) return
  if (target?.closest?.('[data-fixed-popover]') && !props.closeOnOtherPopover) return
  emit('request-close', { reason: 'outside-pointerdown' })
}

const handleDocumentKeydown = (event) => {
  if (!props.closeOnEscape || !props.isOpen) return
  if (event.key !== 'Escape') return
  emit('request-close', { reason: 'escape' })
}

const stopListeners = () => {
  scrollParents.value.forEach((target) => target.removeEventListener('scroll', handleScroll))
  scrollParents.value = []
  clipParents.value = []
  window.removeEventListener('resize', updatePosition)
  document.removeEventListener('pointerdown', handleDocumentPointerDown)
  document.removeEventListener('keydown', handleDocumentKeydown)
}

const syncListeners = () => {
  stopListeners()
  if (!props.isOpen) return
  const triggerEl = resolveTriggerEl()
  scrollParents.value = collectScrollParents(triggerEl)
  clipParents.value = collectClipParents(triggerEl)
  scrollParents.value.forEach((target) => target.addEventListener('scroll', handleScroll, { passive: true }))
  window.addEventListener('resize', updatePosition)
  if (props.closeOnOutside) document.addEventListener('pointerdown', handleDocumentPointerDown)
  if (props.closeOnEscape) document.addEventListener('keydown', handleDocumentKeydown)
}

onUnmounted(stopListeners)

watch(
  () => [props.isOpen, props.closeOnOutside, props.closeOnEscape],
  () => syncListeners()
)
</script>

<style scoped>
/* 细腻的进入动画：带有微小的位移偏移感 */
.popover-fade-enter-active {
  transition: opacity 0.2s ease-out, transform 0.25s cubic-bezier(0.16, 1, 0.3, 1);
}
.popover-fade-leave-active {
  transition: opacity 0.15s ease-in;
}

.popover-fade-enter-from {
  opacity: 0;
  transform: translateY(4px) scale(0.98) !important; /* 强制微调初始位置 */
}
.popover-fade-leave-to {
  opacity: 0;
}
</style>
