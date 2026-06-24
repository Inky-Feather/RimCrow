<!-- frontend/src/components/StatusBar.vue -->
<template>
  <div class="h-6 w-full flex items-center px-3 justify-between text-xs text-text-dim select-none relative z-40 ">
    <div class="flex items-center gap-4">
      <div class="flex items-center gap-1.5 hover:text-text-main transition-colors cursor-pointer">
        <div :class="['w-1.5 h-1.5 rounded-full', modStore.isDirty ? 'bg-accent-warn' : 'bg-accent-success']"></div>
        <span>{{ modStore.isDirty ? t('ui.unsavedChanges') : t('ui.ready') }}</span>
      </div>

      <div>
        {{ t('ui.totalMods') }} <span class="text-text-main">{{ modStore.allModsMap.size }}</span>
      </div>

      <div>
        {{ t('ui.enabled') }} <span class="text-accent-success font-bold">{{ modStore.activeIds.length }}</span>
      </div>

      <div v-tooltip="historyStateTooltip">
        {{ t('ui.historyState') }}
        <template v-if="modStore.listHistoryTotal > 0">
          <span class="text-text-main font-bold">{{ modStore.listHistoryPosition }}</span>/<span class="text-text-dim">{{ modStore.listHistoryTotal }}</span>
        </template>
        <span v-else class="text-text-disabled">{{ t('ui.none') }}</span>
      </div>

      <div v-show="modStore.selectedIds.length > 0">
        {{ t('ui.selected') }} <span class="text-accent-primary font-bold">{{ modStore.selectedIds.length }}</span>
      </div>
    </div>

    <Teleport to="body">
      <transition name="slide-up">
        <div v-if="activeTask" class="fixed bottom-0 left-1/2 z-9999 -translate-x-1/2 group/status">
          <div class="flex items-center gap-2 bg-bg-surface px-2 pt-1 pb-0.5 rounded-t-lg border-t shadow-[0_-4px_10px_var(--shadow-color)] min-w-90 max-w-190 justify-center"
            :class="taskAccentBorder(activeTask)">
            <component :is="taskIcon(activeTask)" class="h-4 w-4 shrink-0" :class="taskAccentText(activeTask, true)" />

            <div class="w-52 h-2 bg-bg-overlay/10 rounded-full relative overflow-hidden">
              <div class="h-full transition-all duration-300 ease-out rounded-full"
                :class="taskAccentBar(activeTask)"
                :style="{ width: `${taskPercent(activeTask)}%` }">
              </div>
            </div>

            <div class="min-w-0 flex items-center gap-1 text-[0.7rem] font-mono">
              <span class="font-bold shrink-0" :class="taskAccentText(activeTask)">{{ taskPercent(activeTask) }}%</span>
              <span class="shrink-0 text-text-dim">{{ taskTitle(activeTask) }}</span>
              <span class="truncate max-w-90 text-text-dim" :title="taskMessage(activeTask)">{{ taskMessage(activeTask) }}</span>
              <span v-if="taskExtra(activeTask)" class=" text-text-disabled text-[0.62rem]">{{ taskExtra(activeTask) }}</span>
            </div>

            <div v-if="taskStore.tasks.length > 1" class="shrink-0 rounded-full px-1.5 py-0.5 bg-bg-overlay/10 text-xs text-text-dim font-bold">
              +{{ taskStore.tasks.length - 1 }}
            </div>

            <button v-if="appStore.supportsTaskCancellation(activeTask)"
              class="shrink-0 rounded-md p-1 transition-colors disabled:cursor-wait"
              :class="appStore.canCancelTask(activeTask) ? 'text-text-disabled hover:text-accent-danger hover:bg-accent-danger/15' : 'text-accent-warning/70 bg-accent-warning/10'"
              :disabled="!appStore.canCancelTask(activeTask)"
              :title="appStore.isTaskCancelPending(activeTask?.id) ? t('statusBar.cancellingTask') : t('statusBar.cancelTask')"
              @click.stop="cancelTask(activeTask)"
            >
              <component :is="appStore.isTaskCancelPending(activeTask?.id) ? LoaderCircle : X" class="h-3.5 w-3.5" :class="{ 'animate-spin': appStore.isTaskCancelPending(activeTask?.id) }" />
            </button>
          </div>

          <div class="absolute bottom-full left-1/2 mb-2 w-120 max-w-[90vw] -translate-x-1/2 rounded-2xl border border-border-base/10 bg-glass-heavy backdrop-blur-md shadow-2xl p-3 opacity-0 invisible transition-all duration-200 group-hover/status:opacity-100 group-hover/status:visible group-hover/status:translate-y-0">
            <div class="mb-2 flex items-center justify-between">
              <div class="text-[0.7rem] font-bold tracking-wider text-text-soft">{{ t('statusBar.taskQueue') }}</div>
              <div class="text-[0.65rem] text-text-disabled">{{ t('statusBar.taskCount', { count: taskStore.tasks.length }) }}</div>
            </div>

            <div class="max-h-80 overflow-y-auto custom-scrollbar space-y-2">
              <div v-for="task in taskStore.tasks" :key="task.id" class="modal-section-subtle px-3 py-2">
                <div class="flex items-center gap-2">
                  <component :is="taskIcon(task)" class="h-4 w-4 shrink-0" :class="taskAccentText(task, true)" />
                  <div class="min-w-0 flex-1">
                    <div class="flex items-center justify-between gap-1">
                      <span class="truncate font-bold text-text-main">{{ taskTitle(task) }}</span>
                      
                      <div class="flex shrink-0 items-center gap-2">
                        <button v-if="appStore.supportsTaskCancellation(task)"
                          class="rounded-md p-1 transition-colors disabled:cursor-wait"
                          :class="appStore.canCancelTask(task) ? 'text-text-disabled hover:text-accent-danger hover:bg-accent-danger/15' : 'text-accent-warning/70 bg-accent-warning/10'"
                          :disabled="!appStore.canCancelTask(task)"
                          :title="appStore.isTaskCancelPending(task?.id) ? t('statusBar.cancellingTask') : t('statusBar.cancelTask')"
                          @click.stop="cancelTask(task)"
                        >
                          <component :is="appStore.isTaskCancelPending(task?.id) ? LoaderCircle : X" class="h-3.5 w-3.5" :class="{ 'animate-spin': appStore.isTaskCancelPending(task?.id) }" />
                        </button>
                      </div>
                    </div>
                    <div class="mt-1 flex items-center justify-between gap-1 text-[0.65rem] text-text-dim">
                      <span class="truncate" :title="taskMessage(task)">{{ taskMessage(task) }}</span>
                      <span v-if="taskExtra(task)" class="shrink-0 text-text-disabled">{{ taskExtra(task) }}</span>
                    </div>
                  </div>
                </div>

                <div class="mt-2 h-1.5 flex items-center gap-1 overflow-hidden w-full">
                  <div class="flex-1 w-full h-full rounded-full bg-bg-overlay/10">
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
      <span>{{ t('ui.lastAppRun') }}{{ formatDate(appStore.settings.last_run_time) || t('ui.neverRun') }}</span> |
      <span>{{ t('ui.lastGameRun') }}{{ formatDate(profileStore.currentProfile?.last_played_time) || t('ui.neverRun') }}</span> |
      <span>RimWorld {{ profileStore.activeContext.game_version || t('ui.unknownVersion') }}</span>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { Bot, Download, Image, LoaderCircle, Radar, X, Flag, FlagOff, ScanSearch, Box, Search, Package } from 'lucide-vue-next'
import { useModStore } from '../../features/mod/stores/modStore'
import { useAppStore } from '../stores/appStore'
import { useProfileStore } from '../../features/profiles/profileStore'
import { useTaskStore } from '../stores/taskStore'
import { formatDate } from '../../shared/lib/format'
import { useI18n } from 'vue-i18n'

const modStore = useModStore()
const appStore = useAppStore()
const profileStore = useProfileStore()
const taskStore = useTaskStore()
const { t } = useI18n()

const activeTask = computed(() => taskStore.latestTask)

const taskTypeMeta = {
  scan: { titleKey: 'statusBar.taskScan', icon: Radar, text: 'text-accent-primary', bar: 'bg-accent-primary', border: 'border-accent-primary/30' },
  download: { titleKey: 'statusBar.taskDownload', icon: Download, text: 'text-accent-cool', bar: 'bg-accent-cool', border: 'border-accent-cool/30' },
  update: { titleKey: 'statusBar.taskUpdate', icon: Download, text: 'text-accent-primary', bar: 'bg-accent-primary', border: 'border-accent-primary/30' },
  'steamcmd-download': { titleKey: 'statusBar.taskSteamcmdDownload', icon: Download, text: 'text-accent-cool', bar: 'bg-accent-cool', border: 'border-accent-cool/30' },
  'steam-subscribe': { titleKey: 'statusBar.taskSteamSubscribe', icon: Flag, text: 'text-accent-success', bar: 'bg-accent-success', border: 'border-accent-success/30' },
  'steam-unsubscribe': { titleKey: 'statusBar.taskSteamUnsubscribe', icon: FlagOff, text: 'text-accent-danger', bar: 'bg-accent-danger', border: 'border-accent-danger/30' },
  'texture-opt': { titleKey: 'statusBar.taskTextureOpt', icon: Image, text: 'text-accent-secondary', bar: 'bg-accent-secondary', border: 'border-accent-secondary/30' },
  'texture-opt-analyze': { titleKey: 'statusBar.taskTextureOptAnalyze', icon: ScanSearch, text: 'text-accent-secondary', bar: 'bg-accent-secondary', border: 'border-accent-secondary/30' },
  'ai-task': { titleKey: 'statusBar.taskAiTask', icon: Bot, text: 'text-accent-special', bar: 'bg-accent-special', border: 'border-accent-special/30' },
  localize: { titleKey: 'statusBar.taskLocalize', icon: Box, text: 'text-accent-success', bar: 'bg-accent-success', border: 'border-accent-success/30' },
  'mod-import': { titleKey: 'statusBar.taskModImport', icon: Package, text: 'text-accent-primary', bar: 'bg-accent-primary', border: 'border-accent-primary/30' },
  'mod-export': { titleKey: 'statusBar.taskModExport', icon: Package, text: 'text-accent-special', bar: 'bg-accent-special', border: 'border-accent-special/30' },
  'steamcmd-init': { titleKey: 'statusBar.taskSteamcmdInit', icon: Download, text: 'text-accent-warning', bar: 'bg-accent-warning', border: 'border-accent-warning/30' },
  'file-search': { titleKey: 'statusBar.taskFileSearch', icon: Search, text: 'text-accent-cool', bar: 'bg-accent-cool', border: 'border-accent-cool/30' },
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
  if (type === 'download') return t('common.download')
  if (type === 'update') return t('common.update')
  return String(task?.metrics?.title || t(resolveTaskMeta(task).titleKey))
}

const taskMessage = (task) => {
  const raw = String(task?.message || '')
  if (!raw) return t('common.processing')
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
  if (appStore.isTaskCancelPending(task?.id) || phase === 'cancelling') return t('common.cancelling')
  if (phase === 'verifying') return t('common.verifying')
  const parts = []
  const sizeProgress = taskSizeProgress(task)
  if (sizeProgress) parts.push(sizeProgress)
  const speed = String(task?.metrics?.speed || '').trim()
  if (speed) parts.push(speed)
  return parts.join(' ')
}

const historyStateTooltip = computed(() => t('statusBar.historyStateTooltip'))
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
