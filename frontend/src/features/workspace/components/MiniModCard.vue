<!-- src/components/workspace/components/MiniModCard.vue -->
<template>
  <div class="relative w-36 shrink-0 bg-bg-inset/80 rounded-xl border border-border-base/10 overflow-hidden group hover:border-accent-primary/50 transition-all"
    v-tooltip="descriptionTooltip"
    @click="$emit('navigate', mod.workshop_id)">
    <!-- 封面图 -->
    <div class="h-24 w-full bg-bg-inset relative overflow-hidden">
      <img v-if="mod.preview_url" :src="appStore.getRemoteUrl(mod.preview_url)" class="w-full h-full object-cover opacity-80 group-hover:opacity-100 transition-opacity" />
      <div v-else class="absolute inset-0 flex items-center justify-center text-text-dim text-xs">无封面</div>
      
      <!-- 悬浮操作层 -->
      <div class="absolute inset-0 rounded-t-xl bg-bg-inset/20 opacity-0 group-hover:opacity-100 transition-all duration-300 flex items-center justify-center gap-2 backdrop-blur-sm" @click.stop>
        <WorkshopItemActions :workshop-id="props.mod.workshop_id" :show-unsubscribe="isSubscribed" colorful size="xs" class="pointer-events-auto transition-all duration-300" />
      </div>
      
      <div v-if="isSubscribed" class="absolute top-0 left-0 bg-accent-primary/80 text-on-accent-primary text-xs px-1 rounded-full">
        已订阅
      </div>
    </div>

    <!-- 文本信息 -->
    <div class="p-2 cursor-pointer">
      <div v-if="showsTranslatedTitle" class="truncate text-[0.62rem] font-bold leading-none text-text-dim">
        {{ originalTitle }}
      </div>
      <div class="mt-1 truncate text-xs font-bold text-text-main group-hover:text-accent-primary">
        {{ displayTitle }}
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useAppStore } from '../../../app/stores/appStore'
import { useWorkspaceStore } from '../workspaceStore'
import { cleanRichText } from '../../../shared/lib/text'
import WorkshopItemActions from '../../../shared/components/WorkshopItemActions.vue'

const props = defineProps({
  mod: { type: Object, required: true }
})
const emit = defineEmits(['navigate'])

const appStore = useAppStore()
const workspaceStore = useWorkspaceStore()

const isSubscribed = computed(() => workspaceStore.subscribedWorkshopIds.has(String(props.mod.workshop_id)))
const originalTitle = computed(() => String(props.mod.original_title || props.mod.title || props.mod.name || props.mod.workshop_id || '').trim())
const displayTitle = computed(() => String(props.mod.display_title || props.mod.title || props.mod.name || props.mod.workshop_id || '').trim())
const showsTranslatedTitle = computed(() => !!(props.mod.shows_translated_title && originalTitle.value && displayTitle.value !== originalTitle.value))
const descriptionTooltip = computed(() => {
  const text = String(props.mod.display_description || props.mod.short_description || props.mod.description || '').trim()
  return text ? cleanRichText(text, 220).replace(/\n+/g, '\n').trim() : '点击查看详情'
})
</script>
