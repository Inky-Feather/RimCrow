<!-- src/components/common/FixedPopover.vue -->
<template>
  <Teleport :to="portalTarget">
    <Transition name="popover-fade">
      <!-- 定位壳只负责摆放，不应挡住壳外的页面点击；实际内容层单独恢复命中。 -->
      <div v-if="isOpen && scopeActive" ref="popoverRef" class="pointer-events-none" data-fixed-popover :style="containerStyle">
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
          <div :class="surfaceWrapperClass" :style="[contentStyle, { overflowY: scrollable ? 'auto' : undefined }]">
            <slot></slot>
          </div>
        </template>
        <div ref="childHost" class="pointer-events-none absolute inset-0 z-10 overflow-visible"></div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
import { ref, watch, nextTick, onUnmounted, onDeactivated, computed, inject, provide } from 'vue'
import { useAppStore } from '../../../app/stores/appStore'
import { UI_Z_INDEX } from '../../lib/constants.js'
import { POPOVER_PORTAL_KEY, openPopovers } from './popoverContext.js'

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
  placement: { type: String, default: 'auto' },       // auto | bottom | top；空间不足时允许反向展开。
  align: { type: String, default: 'start' },          // start | center | end
  zIndex: { type: [Number, String], default: null },
  // 下拉/浮层的大多数场景都需要默认可关闭，特殊场景再由调用方显式关闭。
  closeOnOutside: { type: Boolean, default: true },
  closeOnEscape: { type: Boolean, default: true },
  closeOnOtherPopover: { type: Boolean, default: false },
})

const appStore = useAppStore()
const portalContext = inject(POPOVER_PORTAL_KEY, null)
const portalTarget = computed(() => portalContext?.target?.value || 'body')
const scopeActive = computed(() => portalContext?.active?.value !== false)
const popoverRef = ref(null)
const childHost = ref(null)
provide(POPOVER_PORTAL_KEY, {
  target: childHost, active: computed(() => props.isOpen && scopeActive.value), boundary: portalContext?.boundary,
})
let frameId = 0
let lastGeometry = ''
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
  // 指定方向优先保留，但至少要容纳一行选项，不能只剩无法操作的细条。
  const minimumSpace = Math.min(preferredMaxHeight, appStore.scalePx(props.placement === 'auto' ? 200 : 48))
  if (props.placement === 'top') return spaceAbove >= minimumSpace || spaceAbove >= spaceBelow
  return spaceBelow < minimumSpace && spaceAbove > spaceBelow
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
  const boundary = portalContext?.boundary?.value?.getBoundingClientRect()
  const bounds = {
    left: Math.max(0, boundary?.left || 0), top: Math.max(0, boundary?.top || 0),
    right: Math.min(window.innerWidth, boundary?.right ?? window.innerWidth),
    bottom: Math.min(window.innerHeight, boundary?.bottom ?? window.innerHeight),
  }
  const viewW = bounds.right - bounds.left
  const viewH = bounds.bottom - bounds.top
  const margin = appStore.scalePx(12) // 距离窗口边缘的硬性安全距离
  const scaledOffset = resolveOffsetPx(props.offset)
  const widthPresets = { trigger: rect.width }

  // --- 1. 确定水平位置与最大宽度 ---
  // 基础最小宽度默认不绑定触发器，只在显式传入时才生效。
  const preferredMinWidth = resolveCssLengthToPx(props.minWidth, viewW, 0, {
    presets: widthPresets
  })
  const baseMinWidth = Math.max(0, Math.min(preferredMinWidth, viewW - margin * 2))
  const preferredWidth = resolveCssLengthToPx(props.width, viewW, 0, {
    presets: widthPresets
  })
  const requestedWidth = preferredWidth > 0 ? Math.max(baseMinWidth, preferredWidth) : null
  const resolveLeft = (width) => {
    let value = getHorizontalAnchor(rect, width)
    if (value + width > bounds.right - margin) {
      value = bounds.right - width - margin
    }
    return Math.max(bounds.left + margin, value)
  }

  let anchorWidth = requestedWidth || Math.max(baseMinWidth, popoverRef.value?.getBoundingClientRect().width || 0)
  let left = resolveLeft(anchorWidth)

  // 最大宽度会先按用户传入值解析，再被当前窗口剩余空间截断。
  let availableWidth = requestedWidth ? Math.max(0, bounds.right - left - margin) : Math.max(0, viewW - margin * 2)
  let preferredMaxWidth = resolveCssLengthToPx(props.maxWidth, viewW, availableWidth)
  let finalMaxWidth = Math.max(baseMinWidth, Math.min(preferredMaxWidth > 0 ? preferredMaxWidth : availableWidth, availableWidth))
  let finalWidth = requestedWidth ? Math.max(baseMinWidth, Math.min(requestedWidth, finalMaxWidth)) : null

  // 显式宽度被 maxWidth 或窗口空间截断后，重新按最终宽度对齐一次，避免居中/右对齐漂移。
  if (finalWidth && finalWidth !== anchorWidth) {
    anchorWidth = finalWidth
    left = resolveLeft(anchorWidth)
    availableWidth = Math.max(0, bounds.right - left - margin)
    preferredMaxWidth = resolveCssLengthToPx(props.maxWidth, viewW, availableWidth)
    finalMaxWidth = Math.max(baseMinWidth, Math.min(preferredMaxWidth > 0 ? preferredMaxWidth : availableWidth, availableWidth))
    finalWidth = Math.max(baseMinWidth, Math.min(requestedWidth, finalMaxWidth))
  }

  // --- 2. 确定垂直位置与最大高度 ---
  const spaceBelow = bounds.bottom - rect.bottom - scaledOffset - margin
  const spaceAbove = rect.top - bounds.top - scaledOffset - margin
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

  // shortcut: 当前主体只有平移与轴向缩放，支持旋转/倾斜布局时需改用矩阵换算。
  const host = portalContext?.target?.value
  const hostRect = host?.getBoundingClientRect()
  const scaleX = hostRect && host.clientWidth ? hostRect.width / host.clientWidth || 1 : 1
  const scaleY = hostRect && host.clientHeight ? hostRect.height / host.clientHeight || 1 : 1
  // --- 3. 原子化更新状态 ---
  positionState.value = {
    left: hostRect ? (left - hostRect.left) / scaleX : left,
    top: hostRect ? (top - hostRect.top) / scaleY : top,
    width: finalWidth ? finalWidth / scaleX : null,
    minWidth: baseMinWidth / scaleX,
    maxWidth: finalMaxWidth / scaleX,
    height: finalHeight ? finalHeight / scaleY : null,
    maxHeight: finalMaxHeight / scaleY,
    isFlipped
  }
}

// 样式计算属性
const containerStyle = computed(() => ({
  position: portalTarget.value === 'body' ? 'fixed' : 'absolute',
  left: `${positionState.value.left}px`,
  top: `${positionState.value.top}px`,
  width: positionState.value.width ? `${positionState.value.width}px` : 'max-content',
  minWidth: positionState.value.minWidth > 0 ? `${positionState.value.minWidth}px` : undefined,
  maxWidth: `${positionState.value.maxWidth}px`,
  transform: positionState.value.isFlipped ? 'translateY(-100%)' : 'none',
  overflow: 'visible',
  zIndex: portalTarget.value === 'body' ? UI_Z_INDEX.PAGE_POPOVER : (props.zIndex ?? 20)
}))

const surfaceWrapperClass = computed(() => ([
  'pointer-events-auto w-fit max-w-full',
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

// 打开期间只读取位置；布局移动或 transform 变化时才重新写入定位。
const followTrigger = () => {
  if (!props.isOpen || !scopeActive.value) return
  const rect = resolveTriggerEl()?.getBoundingClientRect()
  const hostRect = portalContext?.target?.value?.getBoundingClientRect()
  const boundary = portalContext?.boundary?.value?.getBoundingClientRect()
  const menu = popoverRef.value?.getBoundingClientRect()
  const geometry = [rect?.x, rect?.y, rect?.width, rect?.height,
    hostRect?.x, hostRect?.y, hostRect?.width, hostRect?.height,
    boundary?.x, boundary?.y, boundary?.width, boundary?.height, menu?.width, menu?.height].join(',')
  if (geometry !== lastGeometry) {
    lastGeometry = geometry
    updatePosition()
  }
  frameId = requestAnimationFrame(followTrigger)
}

const isInteractive = () => {
  const trigger = resolveTriggerEl()
  if (!props.isOpen || !scopeActive.value || !isTriggerVisible(trigger)) return false
  const rect = trigger.getBoundingClientRect()
  const hit = document.elementFromPoint(rect.left + rect.width / 2, rect.top + rect.height / 2)
  if (!hit) return false
  if (trigger.contains(hit) || popoverRef.value?.contains(hit)) return true
  // 高层弹窗覆盖触发器后，底层面板不能抢走 Esc。
  return hit.closest('[data-popover-scope]') === (portalContext?.target?.value?.closest('[data-popover-scope]') || null)
}
const stackEntry = { isInteractive }
defineExpose({ isInteractive })

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
  if (openPopovers.findLast(entry => entry.isInteractive()) !== stackEntry) return
  event.preventDefault()
  event.stopImmediatePropagation()
  emit('request-close', { reason: 'escape' })
}

const stopListeners = () => {
  cancelAnimationFrame(frameId)
  frameId = 0
  lastGeometry = ''
  const index = openPopovers.indexOf(stackEntry)
  if (index !== -1) openPopovers.splice(index, 1)
  scrollParents.value.forEach((target) => target.removeEventListener('scroll', handleScroll))
  scrollParents.value = []
  clipParents.value = []
  window.removeEventListener('resize', updatePosition)
  document.removeEventListener('pointerdown', handleDocumentPointerDown)
  document.removeEventListener('keydown', handleDocumentKeydown, true)
}

const syncListeners = () => {
  stopListeners()
  if (!props.isOpen || !scopeActive.value) return
  const triggerEl = resolveTriggerEl()
  scrollParents.value = collectScrollParents(triggerEl)
  clipParents.value = collectClipParents(triggerEl)
  scrollParents.value.forEach((target) => target.addEventListener('scroll', handleScroll, { passive: true }))
  window.addEventListener('resize', updatePosition)
  if (props.closeOnOutside) document.addEventListener('pointerdown', handleDocumentPointerDown)
  openPopovers.push(stackEntry)
  if (props.closeOnEscape) document.addEventListener('keydown', handleDocumentKeydown, true)
  updatePosition()
  frameId = requestAnimationFrame(followTrigger)
}

onUnmounted(stopListeners)
onDeactivated(() => {
  stopListeners()
  if (props.isOpen) emit('request-close', { reason: 'scope-hidden' })
})

watch(
  () => [props.isOpen, scopeActive.value, props.triggerRef, props.closeOnOutside, props.closeOnEscape],
  async (_value, _oldValue, onCleanup) => {
    let cancelled = false
    onCleanup(() => { cancelled = true; stopListeners() })
    stopListeners()
    if (props.isOpen && !scopeActive.value) emit('request-close', { reason: 'scope-hidden' })
    await nextTick()
    if (!cancelled) syncListeners()
  },
  { immediate: true, flush: 'post' }
)
</script>

<style scoped>
/* 只淡入，避免动画 transform 与向上展开定位互相覆盖。 */
.popover-fade-enter-active {
  transition: opacity 0.2s ease-out;
}
.popover-fade-leave-active {
  transition: opacity 0.15s ease-in;
}

.popover-fade-enter-from {
  opacity: 0;
}
.popover-fade-leave-to {
  opacity: 0;
}
</style>
