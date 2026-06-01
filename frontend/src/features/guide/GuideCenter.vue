<template>
  <transition name="guide-fade">
    <div v-if="hasGuides" ref="rootRef" class="fixed top-19 right-4 z-40 flex flex-col items-end pointer-events-none" :style="rootStyle" >
      <!-- 1. 收起状态 (默认胶囊条) -->
      <div class="guide-capsule relative px-4 py-1 w-max whitespace-nowrap flex items-center gap-2 rounded-full cursor-pointer transition-all duration-300 pointer-events-auto select-none touch-none"
        @pointerdown="handleCapsulePointerDown" @click.stop="togglePanel" >
        <!-- 内部流光层 -->
        <div class="capsule-shimmer"></div>
        <span class="relative flex h-2.5 w-2.5 z-10">
          <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-bg-overlay/10 opacity-75"></span>
          <span class="relative inline-flex rounded-full h-2.5 w-2.5 bg-bg-contrast"></span>
        </span>
        <!-- 给文字加上跳动类 -->
        <span class="guide-text text-sm font-black text-on-accent-primary z-10 uppercase tracking-tight">
          {{ uncompletedCount > 0 ? `使用指引 (${uncompletedCount})` : '教程中心' }}
        </span>
      </div>

      <transition name="guide-panel-fade">
        <!-- 2. 展开状态 (教程列表) -->
        <div v-if="isPanelOpen" ref="panelRef"
          class="absolute w-80 p-2 rounded-xl bg-glass-medium/90 backdrop-blur-lg border border-border-base/10 shadow-2xl pointer-events-auto"
          :class="panelPositionClass" >
          <!-- Header -->
          <div class="px-2 pb-2 mb-2 border-b border-border-base/10">
            <h4 class="font-bold text-text-main">使用引导中心</h4>
            <p class="text-xs text-text-dim">点击下方条目开始了解软件操作。</p>
          </div>

          <!-- 教程列表 -->
          <div class="space-y-0.5 max-h-80 overflow-y-auto custom-scrollbar overscroll-contain">
            <!-- 未完成的教程 -->
            <div v-for="guide in uncompletedGuides" :key="guide.key" class="flex items-center gap-3 p-2 rounded-lg hover:bg-accent-primary/10 transition-colors" >
              <div @click="startGuide(guide.key)" class="flex-1 flex items-start gap-3 cursor-pointer">
                <div class="mt-0.5 p-1.5 rounded-md bg-accent-primary/20 text-accent-primary">
                  <Play class="size-4" />
                </div>
                <div>
                  <p class="font-bold text-sm text-text-main">{{ guide.title }}</p>
                  <p class="text-xs text-text-dim">{{ guide.description }}</p>
                </div>
              </div>

              <!-- 跳过按钮 -->
              <button class="shrink-0 px-2 py-1 rounded-md text-xs font-bold text-text-dim hover:bg-accent-warn/15 hover:text-accent-warn transition-colors" 
                @click.stop="skipGuide(guide.key)" >
                跳过
              </button>
            </div>

            <!-- 折叠的已完成教程 -->
            <div v-if="completedGuides.length > 0">
              <button class="w-full text-left text-xs text-text-dim px-2 py-1.5 mt-2 flex items-center gap-1 hover:text-text-main"
                @click="showCompleted = !showCompleted" >
                <ChevronRight class="size-3 transition-transform" :class="{ 'rotate-90': showCompleted }" />
                已完成 ({{ completedGuides.length }})
              </button>

              <transition name="list-fade">
                <div v-if="showCompleted" class="pl-4 space-y-1 mt-1">
                  <div v-for="guide in completedGuides" :key="guide.key" class="flex items-center gap-2 p-1.5 rounded-lg hover:bg-accent-secondary/10 text-text-dim cursor-pointer transition-colors"
                    @click="startGuide(guide.key, true)" >
                    <Check class="size-3 text-accent-success" />
                    <span class="text-xs">{{ guide.title }}</span>
                  </div>
                </div>
              </transition>
            </div>
          </div>

          <!-- Footer (可选) -->
          <div class="mt-2 pt-2 border-t border-border-base/10 flex items-center justify-between gap-3">
            <button class="text-xs text-text-dim hover:text-accent-warn transition-colors"
              @click="skipAllGuides" >
              全部跳过
            </button>
            <button class="text-xs text-text-dim hover:text-accent-danger transition-colors"
              @click="resetAllGuides" v-tooltip="'重置所有引导记录，它们将重新出现'" >
              全部重置
            </button>
          </div>
        </div>
      </transition>
    </div>
  </transition>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, reactive, ref } from 'vue'
import { onClickOutside } from '@vueuse/core'
import { useGuideStore, allGuides } from './guideStore'
import { useAppStore } from '../../app/stores/appStore'
import { Check, Play, ChevronRight } from 'lucide-vue-next'
import { GUIDE_VERSION } from './guideConfig'

const DRAG_THRESHOLD = 4
const PANEL_WIDTH = 320
const PANEL_ESTIMATED_HEIGHT = 360
const PANEL_EDGE_GAP = 12

const guideStore = useGuideStore()
const appStore = useAppStore()

const rootRef = ref(null)
const panelRef = ref(null)
const isPanelOpen = ref(false)
const showCompleted = ref(false)
const dragOffset = ref({ x: 0, y: 0 })
const panelPosition = reactive({
  horizontal: 'right',
  vertical: 'bottom',
})
const dragState = reactive({
  active: false,
  moved: false,
  startX: 0,
  startY: 0,
  offsetX: 0,
  offsetY: 0,
})
const suppressToggle = ref(false)

// --- 计算属性 ---

const isGuideCompleted = (guideKey) => {
  const uniqueKey = `${guideKey}_${GUIDE_VERSION}`
  return appStore.settings.completed_guides?.[uniqueKey] === 'done'
}

const uncompletedGuides = computed(() => allGuides.filter(g => !isGuideCompleted(g.key)))
const completedGuides = computed(() => allGuides.filter(g => isGuideCompleted(g.key)))
const hasGuides = computed(() => uncompletedGuides.value.length > 0)
const uncompletedCount = computed(() => uncompletedGuides.value.length)
const rootStyle = computed(() => ({
  transform: `translate3d(${dragOffset.value.x}px, ${dragOffset.value.y}px, 0)`,
}))
const panelPositionClass = computed(() => ({
  'top-full mt-2': panelPosition.vertical === 'bottom',
  'bottom-full mb-2': panelPosition.vertical === 'top',
  'right-0': panelPosition.horizontal === 'right',
  'left-0': panelPosition.horizontal === 'left',
}))

const updatePanelPosition = () => {
  const rect = rootRef.value?.getBoundingClientRect()
  if (!rect) return

  const panelHeight = panelRef.value?.offsetHeight || PANEL_ESTIMATED_HEIGHT
  const canOpenLeft = rect.right >= PANEL_WIDTH + PANEL_EDGE_GAP
  const canOpenRight = window.innerWidth - rect.left >= PANEL_WIDTH + PANEL_EDGE_GAP
  const canOpenBottom = window.innerHeight - rect.bottom >= panelHeight + PANEL_EDGE_GAP
  const canOpenTop = rect.top >= panelHeight + PANEL_EDGE_GAP

  if (canOpenLeft) panelPosition.horizontal = 'right'
  else if (canOpenRight) panelPosition.horizontal = 'left'
  else panelPosition.horizontal = rect.right >= window.innerWidth - rect.left ? 'right' : 'left'

  if (canOpenBottom) panelPosition.vertical = 'bottom'
  else if (canOpenTop) panelPosition.vertical = 'top'
  else panelPosition.vertical = rect.bottom <= window.innerHeight - rect.top ? 'bottom' : 'top'
}

const stopDragging = () => {
  dragState.active = false
  window.removeEventListener('pointermove', handlePointerMove)
  window.removeEventListener('pointerup', handlePointerUp)
  window.removeEventListener('pointercancel', handlePointerUp)
}

const handlePointerMove = (event) => {
  if (!dragState.active) return
  const deltaX = event.clientX - dragState.startX
  const deltaY = event.clientY - dragState.startY
  if (!dragState.moved && Math.hypot(deltaX, deltaY) < DRAG_THRESHOLD) return

  dragState.moved = true
  dragOffset.value = {
    x: dragState.offsetX + deltaX,
    y: dragState.offsetY + deltaY,
  }
  if (isPanelOpen.value) updatePanelPosition()
}

const handlePointerUp = () => {
  if (dragState.moved) {
    suppressToggle.value = true
    window.setTimeout(() => {
      suppressToggle.value = false
    }, 0)
  }
  stopDragging()
}

const handleCapsulePointerDown = (event) => {
  if (event.button !== undefined && event.button !== 0) return

  dragState.active = true
  dragState.moved = false
  dragState.startX = event.clientX
  dragState.startY = event.clientY
  dragState.offsetX = dragOffset.value.x
  dragState.offsetY = dragOffset.value.y

  window.addEventListener('pointermove', handlePointerMove)
  window.addEventListener('pointerup', handlePointerUp)
  window.addEventListener('pointercancel', handlePointerUp)
}

const togglePanel = () => {
  if (suppressToggle.value) return
  isPanelOpen.value = !isPanelOpen.value
  if (isPanelOpen.value) nextTick(updatePanelPosition)
}

// --- 方法 ---

const startGuide = (guideKey, force = false) => {
  isPanelOpen.value = false
  guideStore.startGuideByKey(guideKey, force)
}

const skipGuide = (guideKey) => {
  guideStore.skipGuideByKey(guideKey)
}

const skipAllGuides = () => {
  guideStore.skipAllGuides()
}

const resetAllGuides = () => {
  guideStore.resetAllGuides()
}

onClickOutside(rootRef, () => {
  if (!dragState.active) isPanelOpen.value = false
})

onBeforeUnmount(() => {
  stopDragging()
})
</script>

<style scoped>
.guide-fade-enter-active,
.guide-fade-leave-active {
  transition: opacity 0.35s ease;
}

.guide-fade-enter-from,
.guide-fade-leave-to {
  opacity: 0;
}

.guide-panel-fade-enter-active,
.guide-panel-fade-leave-active {
  transition: opacity 0.22s ease, transform 0.22s ease;
}

.guide-panel-fade-enter-from,
.guide-panel-fade-leave-to {
  opacity: 0;
  transform: scale(0.96);
}

.list-fade-enter-active,
.list-fade-leave-active {
  transition: all 0.3s ease;
  max-height: 200px;
}

.list-fade-enter-from,
.list-fade-leave-to {
  opacity: 0;
  transform: translateY(-10px);
  max-height: 0;
}
/* 胶囊主体：背景流光与呼吸光晕 */
.guide-capsule {
  position: relative;
  overflow: hidden;
  width: max-content;
  min-width: 0;
  background-size: 200% auto;
  background-image: linear-gradient(325deg, var(--color-accent-warn) 0%, var(--color-accent-tip) 45%, var(--color-accent-secondary) 90%);
  /* 动态光晕效果 (外阴影呼吸) */
  animation:
    gradient-flow 3s ease infinite,
    halo-breathe 2s ease-in-out infinite alternate;
  border: none;
}

/* 内部流光扫过效果 */
.capsule-shimmer {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  background: linear-gradient(
    to right,
    transparent 0%,
    rgba(var(--rgb-text-main),0.4) 50%,
    transparent 100%
  );
  transform: translateX(-100%) skewX(-30deg);
  animation: shimmer-sweep 4s infinite;
  z-index: 5;
}

/* 文字跳动效果 */
.guide-text {
  display: inline-block;
  animation: text-jump 2.5s ease-in-out infinite;
}

/* 关键帧动画定义 */
@keyframes gradient-flow {
  0% { background-position: 0% 50%; }
  50% { background-position: 100% 50%; }
  100% { background-position: 0% 50%; }
}

@keyframes halo-breathe {
  from {
    box-shadow: 0 0 10px rgba(var(--rgb-accent-warn), 0.4), 0 5px 15px var(--shadow-color);
  }
  to {
    box-shadow: 0 0 25px rgba(var(--rgb-accent-warn), 0.7), 0 5px 20px var(--shadow-color);
    transform: translateY(-1px);
  }
}

@keyframes shimmer-sweep {
  0% { transform: translateX(-150%) skewX(-30deg); }
  20%, 100% { transform: translateX(150%) skewX(-30deg); }
}

@keyframes text-jump {
  0%, 100% { transform: translateY(0); }
  10% { transform: translateY(-3px); }
  20% { transform: translateY(1px); }
  25% { transform: translateY(0); }
}
</style>
