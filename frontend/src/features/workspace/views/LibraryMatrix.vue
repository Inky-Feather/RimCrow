<!-- src/components/workspace/views/LibraryMatrix.vue -->
<template>
  <div class="h-full flex flex-col relative">
    
    <div class="flex-1 px-4 py-2 flex gap-4 overflow-hidden relative">
      <!-- 遮罩 Loading -->
      <div v-if="workspaceStore.isFetching && !workspaceStore.librariesMods.local.length" class="absolute inset-0 z-50 flex flex-col items-center justify-center bg-bg-deep/50 backdrop-blur-sm">
        <div class="size-10 border-4 border-accent-primary border-t-transparent rounded-full animate-spin mb-4"></div>
        <span class="text-sm font-bold text-accent-primary animate-pulse">正在扫描所有存储位置...</span>
      </div>
      <!-- 左：Steam工坊目录 (Workshop) -->
      <MatrixColumn v-if="hasWorkshopLibrary" title="Steam 创意工坊" iconColor="text-accent-primary" storeType="workshop" data-tour="workspace-workshop-list"
        :mods="workspaceStore.librariesMods.workshop" @open-timeline="handleOpenTimeline"
        tooltip="由 Steam 客户端管理和自动更新的模组。" />
      <!-- 中：管理器目录 (SteamCMD) -->
      <MatrixColumn title="管理器 (SteamCMD)" iconColor="text-accent-success" storeType="self" data-tour="workspace-self-list"
        :mods="workspaceStore.librariesMods.self" @open-timeline="handleOpenTimeline"
        :disabled="managerColumnDisabled"
        tooltip="由 RimCrow 通过 SteamCMD/Git 下载管理的模组库。" />
      <!-- 中：游戏本地目录 (Local) -->
      <MatrixColumn title="游戏本地模组" iconColor="text-accent-warn" storeType="local"
        :mods="localMatrixMods" v-model:show-official-local-mods="showOfficialLocalMods" @open-timeline="handleOpenTimeline"
        tooltip="游戏本体所在的 Mods 目录。此处的变动会直接影响游戏。" />
    </div>

    <!-- 顶部控制栏 -->
    <div class="modal-footer flex h-12 shrink-0 items-center justify-between px-6">
      <div class="text-xs font-mono text-text-disabled uppercase tracking-widest">
        总计数量: {{ visibleTotalCount }} 
        | 总计大小：{{ formatFileSize(visibleTotalSize) }}
        | 状态: {{ workspaceStore.isFetching ? '扫描中...' : '就绪' }}
      </div>
      <button @click="workspaceStore.fetchLibrariesMods" :disabled="workspaceStore.isFetching" v-tooltip="'重新读取当前三域矩阵数据'"
        class="flex items-center gap-2 px-3 py-2 bg-bg-overlay/5 hover:bg-bg-overlay/10 rounded-lg text-xs font-bold transition-all"
        :class="{'opacity-50 cursor-not-allowed': workspaceStore.isFetching}">
        <RefreshCw class="size-3.5" :class="{'animate-spin': workspaceStore.isFetching}" />
        刷新数据
      </button>
    </div>

    <!-- 变动轨迹抽屉 (Teleport挂载到外层保证层级最高) -->
    <TimelineDrawer 
      :is-open="workspaceStore.timeline.isOpen" 
      :workshop-id="workspaceStore.timeline.workshopId" 
      :mod-name="workspaceStore.timeline.modName"
      :logs="workspaceStore.timeline.logs"
      :is-loading="workspaceStore.timeline.isLoading"
      @close="workspaceStore.timeline.isOpen = false" 
    />
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { RefreshCw } from 'lucide-vue-next'
import { useToast } from 'vue-toastification'
import MatrixColumn from './MatrixColumn.vue'
import TimelineDrawer from '../components/TimelineDrawer.vue'
import { useWorkspaceStore } from '../workspaceStore'
import { useAppStore } from '../../../app/stores/appStore'
import { useProfileStore } from '../../profiles/profileStore'
import { formatFileSize } from '../../../shared/lib/format'

const toast = useToast()
const workspaceStore = useWorkspaceStore()
const appStore = useAppStore()
const profileStore = useProfileStore()
const hasWorkshopLibrary = computed(() => !!appStore.settings.workshop_mods_path)
const normalizePath = (path = '') => String(path || '').replace(/\\/g, '/').replace(/\/+$/, '').toLowerCase()
const managerColumnDisabled = computed(() => {
  const localPath = normalizePath(profileStore.activeContext?.local_mods_path)
  const selfPath = normalizePath(appStore.settings.self_mods_path)
  return !!localPath && !!selfPath && localPath === selfPath
})
const showOfficialLocalMods = ref(false)
const OFFICIAL_LOCAL_SOURCES = new Set(['core', 'dlc'])
const isOfficialLocalMod = (mod = {}) => {
  const source = String(mod?.source || '').trim().toLowerCase()
  return OFFICIAL_LOCAL_SOURCES.has(source)
}
// 本地列默认不接收 Core/DLC 数据，避免隐藏项参与多选、全选或右键批量操作。
const localMatrixMods = computed(() => (
  showOfficialLocalMods.value
    ? workspaceStore.librariesMods.local
    : workspaceStore.librariesMods.local.filter(mod => !isOfficialLocalMod(mod))
))
const sumModsSize = (mods = []) => mods.reduce((acc, mod) => acc + (mod.file_size || 0), 0)
const visibleTotalCount = computed(() => (
  workspaceStore.librariesMods.self.length
  + localMatrixMods.value.length
  + (hasWorkshopLibrary.value ? workspaceStore.librariesMods.workshop.length : 0)
))
const visibleTotalSize = computed(() => (
  sumModsSize(workspaceStore.librariesMods.self)
  + sumModsSize(localMatrixMods.value)
  + (hasWorkshopLibrary.value ? sumModsSize(workspaceStore.librariesMods.workshop) : 0)
))
const getPathTail = (path = '') => {
  const parts = String(path || '').replace(/\\/g, '/').split('/').filter(Boolean)
  return parts.length ? parts[parts.length - 1] : ''
}
const isGitRepositoryMod = (mod = {}) => {
  if (String(mod?.source || '').toLowerCase() === 'github') return true
  return getPathTail(mod?.path).toLowerCase().startsWith('_gh_')
}

const handleOpenTimeline = (mod) => {
  if (!mod) return
  if (isGitRepositoryMod(mod)) {
    return workspaceStore.openTimelineGithub(mod)
  }
  if (mod.store === 'local') {
    toast.warning("该 Mod 位于游戏本地目录中，无法获取变动轨迹")
    return
  }
  if (!mod.workshop_id) {
    toast.warning("该 Mod 没有绑定工坊 ID，无法获取变动轨迹")
    return
  }
  return workspaceStore.openTimeline(mod.workshop_id, mod.name || mod.package_id, (mod.store === 'self'))
}

</script>
