<template>
  <!-- 底部固定状态栏 -->
  <div class="h-6 w-full flex items-center px-3 justify-between text-[10px] text-text-dim select-none relative z-40">
    
    <!-- 左侧：常规状态 -->
    <div class="flex items-center gap-4">
      <div class="flex items-center gap-1.5 hover:text-white transition-colors cursor-pointer">
        <div :class="['w-1.5 h-1.5 rounded-full', store.isDirty ? 'bg-yellow-500' : 'bg-green-500']"></div>
        <span>{{ store.isDirty ? '未保存更改' : '就绪' }}</span>
      </div>
      
      <div>
        模组总数: <span class="text-white">{{ store.allModsMap.size }}</span>
      </div>
      
      <div>
        已启用: <span class="text-accent-primary font-bold">{{ store.activeIds.length }}</span>
      </div>
    </div>

    <!-- 右侧/中间：扫描进度 (仅扫描时显示) -->
    <transition name="slide-up">
      <div v-show="showProgress" class="absolute bottom-0 left-1/2 -translate-x-1/2 flex items-center gap-3 bg-bg-deep px-4 pt-1 rounded-t-lg border-t border-accent-primary/30 shadow-[0_-4px_10px_rgba(0,0,0,0.3)]">
        
        <!-- 旋转图标 (扫描中显示，完成后变成对号) -->
        <svg v-if="store.scanProgress.scanning" class="animate-spin h-3 w-3 text-accent-primary" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
        </svg>
        <svg v-else class="h-3 w-3 text-green-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
           <path stroke-linecap="round" stroke-linejoin="round" stroke-width="3" d="M5 13l4 4L19 7" />
        </svg>
        
        <!-- 进度条 -->
         <div class="w-48 h-1.5 bg-white/10 rounded-full relative">
          <div class="h-full bg-accent-primary transition-all rounded-full duration-300 ease-out"
               :style="{ width: displayPercent + '%' }"></div>
        </div>
        
        <!-- 文字信息 -->
        <div class="flex items-center gap-2 min-w-[150px]">
          <span class="font-mono font-bold text-accent-primary">{{ displayPercent }}%</span>
          <span class="truncate max-w-[200px] text-[9px]" :class="{'text-accent-success': !store.scanProgress.scanning, 'text-text-dim': store.scanProgress.scanning}">
            {{ formatMessage(store.scanProgress.message) }}
          </span>
        </div>
      </div>
    </transition>

    <!-- 右侧：版本或设置入口 -->
    <div class="flex items-center gap-2 hover:text-white" >
       <span>RimWorld {{ store.settings.game_version || '未知版本' }}</span>
    </div>

  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useModStore } from '../stores/modStore'
const store = useModStore()

// 本地状态，用于控制显示延迟
const showProgress = ref(false)

// 监听 Store 的扫描状态
watch(() => store.scanProgress.scanning, (isScanning) => {
  if (isScanning) {
    showProgress.value = true
  } else {
    // 扫描结束时，不要立即隐藏
    // 延迟 800ms，让用户看到 100% 和对号，然后再收起
    setTimeout(() => {
      showProgress.value = false
    }, 800)
  }
})

// 显示的百分比：如果是扫描刚结束的瞬间，强制显示 100%
const displayPercent = computed(() => {
  if (!store.scanProgress.scanning && showProgress.value) {
    return 100
  }
  return Math.min(Math.max(store.scanProgress.percent, 0), 100)
})

// 优化显示：如果消息是路径，只显示文件名
const formatMessage = (msg) => {
    if (!msg) return ''
    if (msg.includes('/') || msg.includes('\\')) {
        // 简单提取文件名，让界面更清爽
        return msg.split(/[/\\]/).pop()
    }
    return msg
}
</script>

<style scoped>
.slide-up-enter-active,
.slide-up-leave-active {
  transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
}

.slide-up-enter-from,
.slide-up-leave-to {
  transform: translate(-50%, 100%);
  opacity: 0;
}
</style>