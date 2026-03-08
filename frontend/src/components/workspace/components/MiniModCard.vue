<!-- src/components/workspace/components/MiniModCard.vue -->
<template>
  <div class="relative w-36 shrink-0 bg-black/40 rounded-xl border border-text-main/10 overflow-hidden group cursor-pointer hover:border-accent-primary/50 transition-all"
       @click="$emit('navigate', mod.workshop_id)">
    
    <!-- 封面图 -->
    <div class="h-24 w-full bg-black/60 relative overflow-hidden">
      <img v-if="mod.preview_url" :src="appStore.getRemoteUrl(mod.preview_url)" class="w-full h-full object-cover opacity-80 group-hover:opacity-100 transition-opacity" />
      <div v-else class="absolute inset-0 flex items-center justify-center text-text-dim text-xs">无封面</div>
      
      <!-- 悬浮操作层 -->
      <div class="absolute inset-0 bg-black/60 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center gap-2 backdrop-blur-sm" @click.stop>
        <!-- 订阅 -->
        <button v-if="!isSubscribed" @click="subscribe" v-tooltip="'订阅'" class="p-1.5 rounded-full bg-accent-primary/80 hover:bg-accent-primary text-black transition-transform hover:scale-110">
          <Flag class="size-3.5" />
        </button>
        <!-- 取订 -->
        <button v-else @click="unsubscribe" v-tooltip="'取消订阅'" class="p-1.5 rounded-full bg-accent-danger/80 hover:bg-accent-danger text-black transition-transform hover:scale-110">
          <FlagOff class="size-3.5" />
        </button>
        <!-- 下载 -->
        <button @click="download" v-tooltip="'管理器下载'" class="p-1.5 rounded-full bg-accent-success/80 hover:bg-accent-success text-black transition-transform hover:scale-110">
          <Download class="size-3.5" />
        </button>
      </div>
    </div>

    <!-- 文本信息 -->
    <div class="p-2">
      <div class="text-xs font-bold text-text-main truncate group-hover:text-accent-primary" :title="mod.name">{{ mod.name }}</div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { Flag, FlagOff, Download } from 'lucide-vue-next'
import { useAppStore } from '../../../stores/appStore'
import { useWorkspaceStore } from '../../../stores/workspaceStore'

const props = defineProps({
  mod: { type: Object, required: true }
})
const emit = defineEmits(['navigate'])

const appStore = useAppStore()
const workspaceStore = useWorkspaceStore()

// 这里的状态可以利用你之前重构的 computed 集合
const isSubscribed = computed(() => workspaceStore.subscribedWorkshopIds.has(String(props.mod.workshop_id)))
const isInstalled = computed(() => workspaceStore.installedAllIds.has(String(props.mod.workshop_id)))

const subscribe = () => appStore.subscribeMod([props.mod.workshop_id])
const unsubscribe = () => appStore.unsubscribeMod([props.mod.workshop_id])
const download = () => appStore.downloadWorkshopItems([props.mod.workshop_id])
</script>