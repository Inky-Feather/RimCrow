<!-- frontend/src/components/StatusBar.vue -->
<template>
  <!-- 底部固定状态栏 -->
  <div class="h-6 w-full flex items-center px-3 justify-between text-xs text-text-dim select-none relative z-40 bg-bg-deep border-t border-text-main/5">
    
    <!-- 左侧：常规状态 -->
    <div class="flex items-center gap-4">
      <!-- 状态指示灯 -->
      <div class="flex items-center gap-1.5 hover:text-text-main transition-colors cursor-pointer">
        <div :class="['w-1.5 h-1.5 rounded-full', modStore.isDirty ? 'bg-yellow-500' : 'bg-green-500']"></div>
        <span>{{ modStore.isDirty ? '未保存更改' : '就绪' }}</span>
      </div>
      
      <!-- 基础统计 -->
      <div>
        模组总数: <span class="text-text-main">{{ modStore.allModsMap.size }}</span>
      </div>
      
      <div>
        已启用: <span class="text-accent-success font-bold">{{ modStore.activeIds.length }}</span>
      </div>

      <div v-show="modStore.selectedIds.length > 0">
        已选择: <span class="text-accent-primary font-bold">{{ modStore.selectedIds.length }}</span>
      </div>
    </div>

    <!-- 中间：动态任务进度条 (扫描 OR 下载) -->
    <transition name="slide-up">
      <div v-if="activeTask" class="absolute bottom-0 left-1/2 -translate-x-1/2 flex items-center gap-3 bg-bg-surface px-4 pt-1 pb-0.5 rounded-t-lg border-t border-accent-primary/30 shadow-[0_-4px_10px_rgba(0,0,0,0.3)] max-w-160 justify-center">
        
        <!-- 图标区 -->
        <template v-if="taskType === 'scan'">
            <svg class="animate-spin h-3 w-3 text-accent-primary" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
            </svg>
        </template>
        <template v-else-if="taskType === 'download'">
            <svg class="h-3 w-3 text-blue-400 animate-bounce" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
            </svg>
        </template>

        <!-- 进度条背景 -->
        <div class="w-48 h-2 bg-text-main/10 rounded-full relative overflow-hidden">
          <div class="h-full transition-all duration-300 ease-out rounded-full"
               :class="taskType === 'scan' ? 'bg-accent-primary' : 'bg-blue-500'"
               :style="{ width: taskPercent + '%' }"></div>
        </div>
        
        <!-- 文字信息 -->
        <div class="flex items-center gap-2 text-[0.7rem] font-mono">
          <span :class="taskType === 'scan' ? 'text-accent-primary' : 'text-blue-400'" class="font-bold">
            {{ taskPercent }}%
          </span>
          <span class="truncate max-w-100 text-text-dim" :title="taskMessage">
            {{ taskMessage }}
          </span>
          <!-- 下载专属：速度 -->
          <span v-if="taskType === 'download'" class="text-text-main/50 scale-90">
             {{ activeTask.speed }}
          </span>
        </div>
      </div>
    </transition>

    <!-- 右侧：版本 -->
    <div class="flex items-center gap-2 hover:text-text-main" >
       <span>RimWorld {{ appStore.settings.game_version || '未知版本' }}</span>
    </div>

  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useModStore } from '../stores/modStore'
import { useAppStore } from '../stores/appStore'
import { useToast } from "vue-toastification";

const toast = useToast();
const modStore = useModStore()
const appStore = useAppStore()

// 统一任务计算属性
// 优先级: 扫描 > 下载
const taskType = computed(() => {
  if (appStore.scanProgress.scanning) return 'scan'
  if (appStore.activeDownloadTask) return 'download'
  return null
})

const activeTask = computed(() => {
  if (taskType.value === 'scan') return appStore.scanProgress
  if (taskType.value === 'download') return appStore.activeDownloadTask
  return null
})

const taskPercent = computed(() => {
  if (!activeTask.value) return 0
  return activeTask.value.percent || 0
})

const taskMessage = computed(() => {
  if (!activeTask.value) return ''
  if (taskType.value === 'scan') {
    const msg = activeTask.value.message || ''
    // 简化路径显示
    return msg.includes('/') || msg.includes('\\') ? msg.split(/[/\\]/).pop() : msg
  }
  if (taskType.value === 'download') {
    return activeTask.value.filename || 'Downloading...'
  }
  return ''
})

</script>

<style scoped>
.slide-up-enter-active,
.slide-up-leave-active {
  transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
}

.slide-up-enter-from,
.slide-up-leave-to {
  transform: translate(-50%, 100%); /* 从底部滑入 */
  opacity: 0;
}
</style>