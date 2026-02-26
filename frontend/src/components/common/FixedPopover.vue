<!-- src/components/common/FixedPopover.vue -->
<template>
  <Teleport to="body">
    <Transition name="popover-fade">
      <div 
        v-if="isOpen"
        ref="popoverRef"
        class="fixed z-8000" 
        :style="containerStyle"
      >
        <!-- 核心修复：阴影在外层，裁剪和滚动在内层 -->
        <div class="w-full h-full rounded-xl overflow-hidden shadow-[0_20px_50px_rgba(0,0,0,0.5)] backdrop-blur-2xl" :style="contentStyle">
          <div class="h-full w-full overflow-y-auto custom-scrollbar">
            <slot></slot>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
import { ref, watch, nextTick, onUnmounted, computed } from 'vue'
import { useAppStore } from '../../stores/appStore'

const props = defineProps({
  isOpen: Boolean,
  triggerRef: Object,      // 触发按钮的 DOM
  minWidth: { type: Number, default: 100 }, // 默认 100
  maxWidth: { type: Number, default: 0 },   // 0 表示自动限制
  maxHeight: { type: Number, default: 450 },
  offset: { type: Number, default: 8 }
})

const appStore = useAppStore()
const popoverRef = ref(null)
const positionState = ref({
  left: 0,
  top: 0,
  width: 0,
  maxH: 400,
  isFlipped: false
})

// --- 核心定位算法 ---
const updatePosition = () => {
  const triggerEl = props.triggerRef
  if (!triggerEl || !props.isOpen) return

  const rect = triggerEl.getBoundingClientRect()
  const viewW = window.innerWidth
  const viewH = window.innerHeight
  const margin = appStore.scalePx(12) // 距离窗口边缘的硬性安全距离
  const scaledOffset = appStore.scalePx(props.offset)

  // --- 1. 确定水平位置与最大宽度 ---
  let left = rect.left
  // 基础最小宽度（用户设定或等于触发器宽）
  const baseMinWidth = props.minWidth > 0 ? appStore.scalePx(Number(props.minWidth)) : rect.width
  
  // 防溢出：如果左对齐会导致右侧出界，则尝试右对齐或向左平移
  if (left + baseMinWidth > viewW - margin) {
    left = viewW - baseMinWidth - margin
  }
  left = Math.max(margin, left) // 确保左侧不超出

  // 【核心修改】：最大宽度 = 窗口总宽 - 当前 Left - 右边距
  const availableWidth = viewW - left - margin
  const finalMaxWidth = props.maxWidth > 0 
    ? Math.min(appStore.scalePx(props.maxWidth), availableWidth) 
    : availableWidth

  // --- 2. 确定垂直位置与最大高度 ---
  const spaceBelow = viewH - rect.bottom - scaledOffset - margin
  const spaceAbove = rect.top - scaledOffset - margin
  const preferredMaxH = appStore.scalePx(props.maxHeight)

  let isFlipped = false
  let finalMaxH = 0
  let top = 0

  // 翻转逻辑：下方空间不足且上方空间更大
  if (spaceBelow < Math.min(preferredMaxH, 200) && spaceAbove > spaceBelow) {
    isFlipped = true
    top = rect.top - scaledOffset
    // 【核心修改】：向上展开时，最大高度就是当前 Top 到窗口顶部的距离
    finalMaxH = Math.min(preferredMaxH, spaceAbove)
  } else {
    isFlipped = false
    top = rect.bottom + scaledOffset
    // 【核心修改】：向下展开时，最大高度就是当前 Top 到窗口底部的距离
    finalMaxH = Math.min(preferredMaxH, spaceBelow)
  }

  // --- 3. 原子化更新状态 ---
  positionState.value = {
    left,
    top,
    width: baseMinWidth,
    maxWidth: finalMaxWidth,
    maxH: finalMaxH,
    isFlipped
  }
}

// 样式计算属性
const containerStyle = computed(() => ({
  left: `${positionState.value.left}px`,
  top: `${positionState.value.top}px`,
  minWidth: `${positionState.value.width}px`,
  maxWidth: `${positionState.value.maxWidth}px`,
  transform: positionState.value.isFlipped ? 'translateY(-100%)' : 'none',
  zIndex: 8000
}))

const contentStyle = computed(() => ({
  maxHeight: `${positionState.value.maxH}px`
}))

// 监听与事件
watch(() => props.isOpen, async (val) => {
  if (val) {
    await nextTick()
    updatePosition()
    // 使用 requestAnimationFrame 代替 setTimeout，防止布局抖动产生的递归
    requestAnimationFrame(updatePosition)
    
    // 关键修复：不要在 scroll 使用 capture，且仅在 window 滚动时更新
    window.addEventListener('scroll', handleScroll, { passive: true })
    window.addEventListener('resize', updatePosition)
  } else {
    stopListeners()
  }
})

const handleScroll = (e) => {
  // 如果滚动发生在 Popover 内部，不触发重新定位，防止死循环
  if (popoverRef.value?.contains(e.target)) return
  updatePosition()
}

const stopListeners = () => {
  window.removeEventListener('scroll', handleScroll)
  window.removeEventListener('resize', updatePosition)
}

onUnmounted(stopListeners)
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

/* 兼容软件的背景模糊质感（可选，也可在 slot 内容里写） */
:deep(.fixed) {
  background: rgba(15, 23, 42, 0.9);
  backdrop-filter: blur(16px);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 0.75rem;
  box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.4), 0 8px 10px -6px rgba(0, 0, 0, 0.4);
}
</style>