<template>
  <transition name="guide-fade">
    <div v-if="hasGuides" class="fixed top-19 right-4 z-1000 flex flex-col items-end group pointer-events-none">

      <!-- 1. 收起状态 (默认胶囊条) -->
      <div class="guide-capsule relative px-4 py-1 w-max whitespace-nowrap flex items-center gap-2 rounded-full cursor-pointer transition-all duration-300 pointer-events-auto">
        <!-- 内部流光层 -->
        <div class="capsule-shimmer"></div>
        <span class="relative flex h-2.5 w-2.5 z-10">
          <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-white/80 opacity-75"></span>
          <span class="relative inline-flex rounded-full h-2.5 w-2.5 bg-white"></span>
        </span>
        <!-- 给文字加上跳动类 -->
        <span class="guide-text text-sm font-black text-black z-10 uppercase tracking-tight">
          {{ uncompletedCount > 0 ? `新手指引 (${uncompletedCount})` : '教程中心' }}
        </span>
      </div>

      <!-- 2. 展开状态 (教程列表) -->
      <div class="absolute top-full right-0 w-80 p-2 rounded-xl bg-glass-light/90 backdrop-blur-lg border border-text-main/10 shadow-2xl opacity-0 invisible -translate-y-4 group-hover:opacity-100 group-hover:visible group-hover:translate-y-0 transition-all duration-300 pointer-events-auto">
        <!-- Header -->
        <div class="px-2 pb-2 mb-2 border-b border-text-main/10">
          <h4 class="font-bold text-text-main">新手引导中心</h4>
          <p class="text-xs text-text-dim">点击下方条目开始了解软件操作。</p>
        </div>
        
        <!-- 教程列表 -->
        <div class="space-y-0.5 max-h-80 overflow-y-auto custom-scrollbar">
          <!-- 未完成的教程 -->
          <div v-for="guide in uncompletedGuides" :key="guide.key"
               class="flex items-center gap-3 p-2 rounded-lg hover:bg-accent-primary/10 cursor-pointer transition-colors group/item">
            
            <div @click="startGuide(guide.key)" class="flex-1 flex items-start gap-3">
              <div class="mt-0.5 p-1.5 rounded-md bg-accent-primary/20 text-accent-primary">
                <Play class="size-4" />
              </div>
              <div>
                <p class="font-bold text-sm text-text-main">{{ guide.title }}</p>
                <p class="text-xs text-text-dim">{{ guide.description }}</p>
              </div>
            </div>

            <!-- 跳过按钮 -->
            <button @click="skipGuide(guide.key)" v-tooltip="'跳过此项引导'"
                    class="p-1 rounded-md text-text-dim/50 hover:bg-accent-warn/20 hover:text-accent-warn opacity-0 group-hover/item:opacity-100 transition-opacity">
              <Forward class="size-4" />
            </button>
          </div>

          <!-- 折叠的已完成教程 -->
          <div v-if="completedGuides.length > 0">
            <button @click="showCompleted = !showCompleted" class="w-full text-left text-xs text-text-dim px-2 py-1.5 mt-2 flex items-center gap-1 hover:text-text-main">
              <ChevronRight class="size-3 transition-transform" :class="{'rotate-90': showCompleted}" />
              已完成 ({{ completedGuides.length }})
            </button>

            <transition name="list-fade">
              <div v-if="showCompleted" class="pl-4 space-y-1 mt-1">
                <div v-for="guide in completedGuides" :key="guide.key"
                     @click="startGuide(guide.key, true)"
                     class="flex items-center gap-2 p-1.5 rounded-lg hover:bg-accent-secondary/10 text-text-dim/70 cursor-pointer transition-colors">
                  <Check class="size-3 text-accent-success" />
                  <span class="text-xs">{{ guide.title }}</span>
                </div>
              </div>
            </transition>
          </div>

        </div>

        <!-- Footer (可选) -->
        <div class="mt-2 pt-2 border-t border-text-main/10 flex justify-end">
          <button @click="guideStore.resetAllGuides()" v-tooltip="'重置所有引导记录，它们将重新出现'"
                  class="text-xs text-text-dim hover:text-accent-danger transition-colors">
            全部重置
          </button>
        </div>
      </div>

    </div>
  </transition>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useGuideStore, allGuides } from '../stores/guideStore'
import { useAppStore } from '../stores/appStore'
import { Check, Play, Forward, ChevronRight } from 'lucide-vue-next'
import { GUIDE_VERSION } from '../modules/guide/guideConfig'

const guideStore = useGuideStore()
const appStore = useAppStore()

const showCompleted = ref(false)

// --- 计算属性 ---

const isGuideCompleted = (guideKey) => {
  const uniqueKey = `${guideKey}_${GUIDE_VERSION}`
  return appStore.settings.completed_guides?.[uniqueKey] === 'done'
}

const uncompletedGuides = computed(() => allGuides.filter(g => !isGuideCompleted(g.key)))
const completedGuides = computed(() => allGuides.filter(g => isGuideCompleted(g.key)))

const hasGuides = computed(() => uncompletedGuides.value.length > 0)
const uncompletedCount = computed(() => uncompletedGuides.value.length)


// --- 方法 ---

const startGuide = (guideKey, force = false) => {
  guideStore.startGuideByKey(guideKey, force)
}

const skipGuide = (guideKey) => {
  guideStore.skipGuideByKey(guideKey)
}
</script>

<style scoped>
.guide-fade-enter-active,
.guide-fade-leave-active {
  transition: opacity 0.5s ease;
}
.guide-fade-enter-from,
.guide-fade-leave-to {
  opacity: 0;
}

.list-fade-enter-active,
.list-fade-leave-active {
  transition: all 0.3s ease;
  max-height: 200px; /* 预设一个足够大的高度 */
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
  /* 使用 accent-secondary 及其深色版本 */
  background-image: linear-gradient(
    325deg,
    #eab308 0%, 
    #fde047 45%, 
    #ca8a04 90%
  );
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
    rgba(255, 255, 255, 0.4) 50%,
    transparent 100%
  );
  transform: translateX(-100%) skewX(-30deg);
  animation: shimmer-sweep 4s last-child infinite;
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
    box-shadow: 0 0 10px rgba(234, 179, 8, 0.4), 0 5px 15px rgba(0, 0, 0, 0.3);
  }
  to {
    box-shadow: 0 0 25px rgba(234, 179, 8, 0.7), 0 5px 20px rgba(0, 0, 0, 0.4);
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

/* 修改原有 transition */
.guide-fade-enter-active, .guide-fade-leave-active {
  transition: all 0.6s cubic-bezier(0.34, 1.56, 0.64, 1);
}
.guide-fade-enter-from, .guide-fade-leave-to {
  opacity: 0;
  transform: translateX(50px) scale(0.8);
}
</style>
