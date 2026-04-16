<!-- frontend/src/components/StatusBar.vue -->
<template>
  <div class="h-6 w-full flex items-center px-3 justify-between text-xs text-text-dim select-none relative z-40 bg-bg-deep border-t border-text-main/5">
    <div class="flex items-center gap-4">
      <div class="flex items-center gap-1.5 hover:text-text-main transition-colors cursor-pointer">
        <div :class="['w-1.5 h-1.5 rounded-full', modStore.isDirty ? 'bg-yellow-500' : 'bg-green-500']"></div>
        <span>{{ modStore.isDirty ? '未保存更改' : '就绪' }}</span>
      </div>

      <div>
        模组总数: <span class="text-text-main">{{ modStore.allModsMap.size }}</span>
      </div>

      <div>
        已启用: <span class="text-accent-success font-bold">{{ modStore.activeIds.length }}</span>
      </div>

      <div v-tooltip="historyStateTooltip">
        历史状态:
        <template v-if="modStore.listHistoryTotal > 0">
          <span class="text-text-main font-bold">{{ modStore.listHistoryPosition }}</span>/<span class="text-text-main/70">{{ modStore.listHistoryTotal }}</span>
        </template>
        <span v-else class="text-text-main/60">无</span>
      </div>

      <div v-show="modStore.selectedIds.length > 0">
        已选择: <span class="text-accent-primary font-bold">{{ modStore.selectedIds.length }}</span>
      </div>
    </div>

    <Teleport to="body">
      <transition name="slide-up">
        <div v-if="activeTask" class="fixed bottom-0 left-1/2 z-9999 -translate-x-1/2 group/status">
          <div class="flex items-center gap-2 bg-bg-surface px-2 pt-1 pb-0.5 rounded-t-lg border-t shadow-[0_-4px_10px_rgba(0,0,0,0.3)] min-w-90 max-w-190 justify-center"
            :class="taskAccentBorder(activeTask)">
            <component :is="taskIcon(activeTask)" class="h-4 w-4 shrink-0" :class="taskAccentText(activeTask, true)" />

            <div class="w-52 h-2 bg-text-main/10 rounded-full relative overflow-hidden">
              <div class="h-full transition-all duration-300 ease-out rounded-full"
                :class="taskAccentBar(activeTask)"
                :style="{ width: `${taskPercent(activeTask)}%` }">
              </div>
            </div>

            <div class="min-w-0 flex items-center gap-1 text-[0.7rem] font-mono">
              <span class="font-bold shrink-0" :class="taskAccentText(activeTask)">{{ taskPercent(activeTask) }}%</span>
              <span class="shrink-0 text-text-main/75">{{ taskTitle(activeTask) }}</span>
              <span class="truncate max-w-90 text-text-dim" :title="taskMessage(activeTask)">{{ taskMessage(activeTask) }}</span>
              <span v-if="taskExtra(activeTask)" class="shrink-0 text-text-main/50 text-[0.62rem]">{{ taskExtra(activeTask) }}</span>
            </div>

            <div v-if="taskStore.tasks.length > 1" class="shrink-0 rounded-full px-1.5 py-0.5 bg-text-main/8 text-xs text-text-main/70 font-bold">
              +{{ taskStore.tasks.length - 1 }}
            </div>

            <button v-if="appStore.supportsTaskCancellation(activeTask)"
              class="shrink-0 rounded-md p-1 transition-colors disabled:cursor-wait"
              :class="appStore.canCancelTask(activeTask) ? 'text-text-main/55 hover:text-accent-danger hover:bg-accent-danger/15' : 'text-accent-warning/70 bg-accent-warning/10'"
              :disabled="!appStore.canCancelTask(activeTask)"
              :title="appStore.isTaskCancelPending(activeTask?.id) ? '正在尝试取消任务' : '取消任务'"
              @click.stop="cancelTask(activeTask)"
            >
              <component :is="appStore.isTaskCancelPending(activeTask?.id) ? LoaderCircle : X" class="h-3.5 w-3.5" :class="{ 'animate-spin': appStore.isTaskCancelPending(activeTask?.id) }" />
            </button>
          </div>

          <div class="absolute bottom-full left-1/2 mb-2 w-120 max-w-[90vw] -translate-x-1/2 rounded-2xl border border-text-main/10 bg-bg-surface/95 backdrop-blur-md shadow-2xl p-3 opacity-0 invisible transition-all duration-200 group-hover/status:opacity-100 group-hover/status:visible group-hover/status:translate-y-0">
            <div class="mb-2 flex items-center justify-between">
              <div class="text-[0.7rem] font-bold tracking-wider text-text-main/80">任务队列</div>
              <div class="text-[0.65rem] text-text-main/50">{{ taskStore.tasks.length }} 个任务</div>
            </div>

            <div class="max-h-80 overflow-y-auto custom-scrollbar space-y-2">
              <div v-for="task in taskStore.tasks" :key="task.id" class="rounded-xl border border-text-main/8 bg-black/15 px-3 py-2">
                <div class="flex items-center gap-2">
                  <component :is="taskIcon(task)" class="h-4 w-4 shrink-0" :class="taskAccentText(task, true)" />
                  <div class="min-w-0 flex-1">
                    <div class="flex items-center justify-between gap-1">
                      <span class="truncate font-bold text-text-main">{{ taskTitle(task) }}</span>
                      
                      <div class="flex shrink-0 items-center gap-2">
                        <button v-if="appStore.supportsTaskCancellation(task)"
                          class="rounded-md p-1 transition-colors disabled:cursor-wait"
                          :class="appStore.canCancelTask(task) ? 'text-text-main/45 hover:text-accent-danger hover:bg-accent-danger/15' : 'text-accent-warning/70 bg-accent-warning/10'"
                          :disabled="!appStore.canCancelTask(task)"
                          :title="appStore.isTaskCancelPending(task?.id) ? '正在尝试取消任务' : '取消任务'"
                          @click.stop="cancelTask(task)"
                        >
                          <component :is="appStore.isTaskCancelPending(task?.id) ? LoaderCircle : X" class="h-3.5 w-3.5" :class="{ 'animate-spin': appStore.isTaskCancelPending(task?.id) }" />
                        </button>
                      </div>
                    </div>
                    <div class="mt-1 flex items-center justify-between gap-1 text-[0.65rem] text-text-dim">
                      <span class="truncate" :title="taskMessage(task)">{{ taskMessage(task) }}</span>
                      <span v-if="taskExtra(task)" class="shrink-0 text-text-main/45">{{ taskExtra(task) }}</span>
                    </div>
                  </div>
                </div>

                <div class="mt-2 h-1.5 flex items-center gap-1 overflow-hidden w-full">
                  <div class="flex-1 w-full h-full rounded-full bg-text-main/10">
                    <div class="h-full rounded-full transition-all duration-300" :class="taskAccentBar(task)" :style="{ width: `${taskPercent(task)}%` }"></div>
                  </div>
                  <span class="text-[0.65rem] font-mono w-5 text-center flex items-center justify-center" :class="taskAccentText(task)">{{ taskPercent(task) }}%</span>
                </div>

              </div>
            </div>
          </div>
        </div>
      </transition>
    </Teleport>

    <div class="flex items-center gap-2 hover:text-text-main">
      <span>上次软件运行：{{ formatDate(appStore.settings.last_run_time) || '未运行' }}</span> |
      <span>上次游戏运行：{{ formatDate(profileStore.currentProfile?.last_played_time) || '未运行' }}</span> |
      <span>RimWorld {{ profileStore.activeContext.game_version || '未知版本' }}</span>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { Bot, Download, Image, LoaderCircle, Radar, X } from 'lucide-vue-next'
import { useModStore } from '../stores/modStore'
import { useAppStore } from '../stores/appStore'
import { useProfileStore } from '../stores/profileStore'
import { useTaskStore } from '../stores/taskStore'
import { formatDate } from '../utils/uiHelper'

const modStore = useModStore()
const appStore = useAppStore()
const profileStore = useProfileStore()
const taskStore = useTaskStore()

const activeTask = computed(() => taskStore.latestTask)

const taskTypeMeta = {
  scan: { title: '模组扫描', icon: Radar, text: 'text-accent-primary', bar: 'bg-accent-primary', border: 'border-accent-primary/30' },
  download: { title: '下载任务', icon: Download, text: 'text-blue-400', bar: 'bg-blue-500', border: 'border-blue-400/30' },
  update: { title: '软件更新', icon: Download, text: 'text-cyan-400', bar: 'bg-cyan-500', border: 'border-cyan-400/30' },
  'texture-opt': { title: '贴图优化', icon: Image, text: 'text-amber-400', bar: 'bg-amber-500', border: 'border-amber-400/30' },
  'texture-opt-analyze': { title: '贴图分析', icon: Image, text: 'text-amber-400', bar: 'bg-amber-500', border: 'border-amber-400/30' },
  'ai-batch': { title: 'AI 批量处理', icon: Bot, text: 'text-accent-special', bar: 'bg-accent-special', border: 'border-accent-special/30' },
  localize: { title: '本地化模组', icon: Download, text: 'text-emerald-400', bar: 'bg-emerald-500', border: 'border-emerald-400/30' },
  'steamcmd-init': { title: 'SteamCMD 初始化', icon: Download, text: 'text-orange-400', bar: 'bg-orange-500', border: 'border-orange-400/30' },
}

const resolveTaskMeta = (task) => taskTypeMeta[task?.type] || taskTypeMeta.download

const taskIcon = (task) => resolveTaskMeta(task).icon
const taskAccentText = (task, animated = false) => `${resolveTaskMeta(task).text}${animated && task?.status === 'running' ? ' animate-pulse' : ''}`
const taskAccentBar = (task) => resolveTaskMeta(task).bar
const taskAccentBorder = (task) => resolveTaskMeta(task).border
const taskPercent = (task) => Math.max(0, Math.min(100, Number(task?.progress || 0)))

const cancelTask = async (task) => {
  await appStore.cancelTaskByProgress(task)
}

const taskTitle = (task) => {
  const type = String(task?.type || '')
  if (type === 'download') return '下载'
  if (type === 'update') return '更新'
  return String(task?.metrics?.title || resolveTaskMeta(task).title)
}

const taskMessage = (task) => {
  const raw = String(task?.message || '')
  if (!raw) return '处理中...'
  if (task?.type === 'scan' && (raw.includes('/') || raw.includes('\\'))) {
    return raw.split(/[/\\]/).pop() || raw
  }
  return raw
}

const taskSizeProgress = (task) => {
  if (!['download', 'update'].includes(String(task?.type || ''))) return ''
  const current = Number(task?.metrics?.current || 0)
  const total = Number(task?.metrics?.total || 0)
  if (total <= 0) return ''
  const units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']
  const safeTotal = Math.max(total, 1)
  const unitIndex = Math.min(units.length - 1, Math.floor(Math.log(safeTotal) / Math.log(1024)))
  const divisor = Math.pow(1024, unitIndex)
  const currentValue = (current / divisor).toFixed(2)
  const totalValue = (total / divisor).toFixed(2)
  return `(${currentValue}/${totalValue} ${units[unitIndex]})`
}

const taskExtra = (task) => {
  const phase = String(task?.metrics?.phase || '')
  if (appStore.isTaskCancelPending(task?.id) || phase === 'cancelling') return '正在取消'
  if (phase === 'verifying') return '校验中'
  const parts = []
  const sizeProgress = taskSizeProgress(task)
  if (sizeProgress) parts.push(sizeProgress)
  const speed = String(task?.metrics?.speed || '').trim()
  if (speed) parts.push(speed)
  return parts.join(' ')
}

const historyStateTooltip = `当前会话内的列表历史位置。\n显示格式为“当前位置 / 总历史数”。\n\n仅统计用户主动触发的列表变更，例如：\n- 列表间移动\n- 列表内排序\n- 批量添加或移除\n- 自动排序\n- 导入或应用列表结果\n\n不统计搜索、筛选、滚动、折叠等视图状态。\n快捷键：Ctrl+Z 撤销，Ctrl+Y 重做。`
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
