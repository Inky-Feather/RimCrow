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

    
    <Teleport to="body">
      <!-- 中间：动态任务进度条 (扫描 OR 下载) -->
      <transition name="slide-up">
        <div v-if="activeTask" class="fixed bottom-0 z-9999 left-1/2 -translate-x-1/2 flex items-center gap-3 bg-bg-surface px-4 pt-1 pb-0.5 rounded-t-lg border-t border-accent-primary/30 shadow-[0_-4px_10px_rgba(0,0,0,0.3)] max-w-160 justify-center">
          
          <!-- 图标区 -->
          <template v-if="taskType === 'scan'">
            <Radar class="animate-spin animate-duration-2000 h-4 w-4 text-accent-primary" />
          </template>
          <template v-else-if="taskType === 'download'">
            <Download class="h-4 w-4 text-blue-400 animate-bounce" />
          </template>
          <template v-else-if="taskType === 'ai'">
            <Bot class="h-4 w-4 text-accent-special animate-pulse" />
          </template>

          <!-- 进度条背景 -->
          <div class="w-48 h-2 bg-text-main/10 rounded-full relative overflow-hidden">
            <div class="h-full transition-all duration-300 ease-out rounded-full"
              :class="{
                'bg-accent-primary': taskType === 'scan',
                'bg-blue-500': taskType === 'download',
                'bg-accent-special': taskType === 'ai'
              }"
              :style="{ width: taskPercent + '%' }">
            </div>
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
    </Teleport>
    
    <!-- 右侧：版本 -->
    <div class="flex items-center gap-2 hover:text-text-main" >
      <span>上次软件运行：{{ formatDate(appStore.settings.last_run_time) || '未运行' }}</span> |
      <span>上次游戏运行：{{ formatDate(profileStore.currentProfile?.last_played_time) || '未运行' }}</span> |
      <span>RimWorld {{profileStore.activeContext.game_version || '未知版本' }}</span>
    </div>

  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useModStore } from '../stores/modStore'
import { useAppStore } from '../stores/appStore'
import { useToast } from "vue-toastification";
import { Bot, Download, Radar } from 'lucide-vue-next';
import { useProfileStore } from '../stores/profileStore';
import { formatDate } from '../utils/uiHelper';

const toast = useToast();
const modStore = useModStore()
const appStore = useAppStore()
const profileStore = useProfileStore()

// 统一任务计算属性
// 优先级: 扫描 > 下载
const taskType = computed(() => {
  if (appStore.aiState.isLoading) return 'ai'
  if (appStore.scanProgress.scanning) return 'scan'
  if (appStore.activeDownloadTask) return 'download'
  return null
})

const activeTask = computed(() => {
  if (taskType.value === 'ai') return appStore.aiState
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