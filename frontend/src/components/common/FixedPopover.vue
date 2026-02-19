<!-- src/components/common/FixedPopover.vue -->
<template>
  <Teleport to="body">
    <Transition name="fade">
      <div 
        v-if="isOpen"
        ref="popoverRef"
        class="fixed z-9999" 
        :style="positionStyle"
      >
        <slot></slot>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
import { ref, watch, nextTick, onUnmounted } from 'vue'

const props = defineProps({
  isOpen: Boolean,
  triggerRef: Object // 接收按钮的 DOM 引用
})

const popoverRef = ref(null)
const positionStyle = ref({})

// 核心定位逻辑 (与之前的指令逻辑一致)
const updatePosition = () => {
  const triggerEl = props.triggerRef
  const popoverEl = popoverRef.value
  
  if (!triggerEl || !popoverEl) return

  const rect = triggerEl.getBoundingClientRect()
  const viewportHeight = window.innerHeight
  const spaceBelow = viewportHeight - rect.bottom

  // 基础位置
  let style = {
    left: `${rect.left}px`,
    minWidth: '50px' // 可选，或者通过 props 传入
  }

  // 智能垂直翻转
  if (spaceBelow < 200 && rect.top > spaceBelow) {
    style.top = `${rect.top - 4}px`
    style.transform = `translateY(-100%)`
  } else {
    style.top = `${rect.bottom + 4}px`
    style.transform = `none`
  }
  
  positionStyle.value = style
}

// 监听打开状态
watch(() => props.isOpen, async (val) => {
  if (val) {
    await nextTick()
    updatePosition()
    // 开启滚动监听
    window.addEventListener('scroll', updatePosition, { capture: true, passive: true })
    window.addEventListener('resize', updatePosition)
  } else {
    // 关闭监听
    window.removeEventListener('scroll', updatePosition, { capture: true })
    window.removeEventListener('resize', updatePosition)
  }
})

onUnmounted(() => {
  window.removeEventListener('scroll', updatePosition, { capture: true })
  window.removeEventListener('resize', updatePosition)
})
</script>

<style scoped>
.fade-enter-active, .fade-leave-active { transition: opacity 0.2s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>