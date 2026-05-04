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
      <MatrixColumn title="Steam 创意工坊" iconColor="text-accent-primary" storeType="workshop" data-tour="workspace-workshop-list"
        :mods="workspaceStore.librariesMods.workshop" @open-timeline="handleOpenTimeline"
        tooltip="由 Steam 客户端管理和自动更新的模组。" />
      <!-- 中：管理器目录 (SteamCMD) -->
      <MatrixColumn title="管理器 (SteamCMD)" iconColor="text-accent-success" storeType="self" data-tour="workspace-self-list"
        :mods="workspaceStore.librariesMods.self" @open-timeline="handleOpenTimeline"
        tooltip="由 RimModManager 独立下载的模组库。" />
      <!-- 中：游戏本地目录 (Local) -->
      <MatrixColumn title="游戏本地" iconColor="text-accent-warn" storeType="local"
        :mods="workspaceStore.librariesMods.local" @open-timeline="handleOpenTimeline"
        tooltip="游戏本体所在的 Mods 目录。此处的变动会直接影响游戏。" />
    </div>

    <!-- 顶部控制栏 -->
    <div class="h-12 shrink-0 px-6 flex justify-between items-center bg-black/20 border-t border-text-main/5">
      <div class="text-xs font-mono text-text-dim/60 uppercase tracking-widest">
        总计数量: {{ workspaceStore.librariesMods.workshop.length + workspaceStore.librariesMods.self.length + workspaceStore.librariesMods.local.length }} 
        | 总计大小：{{ formatFileSize(workspaceStore.librariesSize.total) }}
        | 状态: {{ workspaceStore.isFetching ? '扫描中...' : '就绪' }}
      </div>
      <button @click="workspaceStore.fetchLibrariesMods" :disabled="workspaceStore.isFetching" v-tooltip="'重新读取当前三域矩阵数据'"
        class="flex items-center gap-2 px-3 py-2 bg-text-main/5 hover:bg-text-main/10 rounded-lg text-xs font-bold transition-all"
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
import { ref, reactive, onMounted } from 'vue'
import { RefreshCw } from 'lucide-vue-next'
import { useToast } from 'vue-toastification'
import MatrixColumn from './MatrixColumn.vue'
import TimelineDrawer from '../components/TimelineDrawer.vue'
import { checkResult } from '../../../utils/common'
import { useWorkspaceStore } from '../../../stores/workspaceStore'
import { formatFileSize } from '../../../utils/format'

const toast = useToast()
const workspaceStore = useWorkspaceStore()

const handleOpenTimeline = (mod) => {
  if (!mod) return
  console.log('handleOpenTimeline',mod)
  if (mod.path?.includes('_GH_')) {
    return workspaceStore.openTimelineGithub(mod.path)
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
