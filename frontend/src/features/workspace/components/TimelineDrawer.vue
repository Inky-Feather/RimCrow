<!-- src/components/workspace/components/TimelineDrawer.vue -->
<template>
  <Teleport to="body">
    <Transition name="slide-right">
      <div v-if="isOpen" ref="drawerRef" class="fixed top-18 bottom-0 right-0 w-96 bg-glass-heavy backdrop-blur-3xl border-l border-border-base/10 shadow-[-10px_0_30px_var(--shadow-color)] z-300 flex flex-col">
        
        <!-- Header -->
        <div class="toolbar-surface flex items-start justify-between px-6 py-5">
          <div>
            <h3 class="text-xl font-black italic tracking-wider flex items-center gap-2">
              <History class="size-5 text-accent-primary" />
              变动<span class="text-accent-primary">时间线</span>
            </h3>
            <p class="text-xs text-text-dim mt-1 max-w-50 truncate" v-tooltip="modName">{{ modName }}</p>
            <p class="text-[0.7rem] font-mono text-text-disabled mt-0.5">ID: {{ workshopId }}</p>
          </div>
          <button @click="$emit('close')" class="p-2 bg-bg-overlay/5 hover:bg-accent-danger/20 hover:text-accent-danger rounded-xl transition-colors">
            <X class="size-5"/>
          </button>
        </div>

        <!-- 骨架屏 Loading -->
        <div v-if="isLoading" class="flex-1 p-6 space-y-6">
          <div v-for="i in 4" :key="i" class="flex gap-4 animate-pulse">
            <div class="w-3 h-3 rounded-full bg-bg-overlay/10 mt-1 shrink-0"></div>
            <div class="space-y-2 flex-1">
              <div class="h-3 bg-bg-overlay/10 rounded w-1/3"></div>
              <div class="h-3 bg-bg-overlay/5 rounded w-full"></div>
            </div>
          </div>
        </div>

        <!-- Timeline 内容区 -->
        <div v-else class="flex-1 overflow-y-auto custom-scrollbar relative p-6 pl-8">
          <div v-if="!logs || logs.length === 0" class="h-full flex flex-col items-center justify-center text-text-disabled">
            <Activity class="size-12 mb-3 opacity-30" />
            <p class="text-sm font-bold">Steam 本地日志未记录该项目的变动</p>
          </div>

          <div v-else>
            <!-- 连线轨道 -->
            <div class="absolute left-[1.1rem] top-8 bottom-10 w-px bg-linear-to-b from-text-main/20 via-text-main/10 to-transparent"></div>

            <div v-for="(log, i) in logs" :key="i" class="mb-8 relative group">
              <!-- 节点指示器 -->
              <div class="absolute -left-5 top-1 size-3 rounded-full border-2 bg-bg-deep z-10 transition-transform group-hover:scale-150" 
                :class="getColorClass(log.color, 'border')"></div>
              
              <!-- 时间与徽章 -->
              <div class="flex items-center gap-3">
                <span class="text-xs font-mono font-bold" :class="getColorClass(log.color, 'text')">
                  {{ formatDate(log.time) }}
                </span>
                <span class="px-2 py-0.5 rounded-full text-[0.7rem] font-black uppercase tracking-wider bg-bg-overlay/5 border border-border-base/5"
                  :class="getColorClass(log.color, 'text')">
                  {{ log.title }}
                </span>
              </div>
              
              <!-- 具体描述 -->
              <div class="modal-section-subtle mt-2 break-all p-2.5 text-xs leading-relaxed text-text-dim">
                {{ log.desc }}
              </div>
            </div>
          </div>
        </div>

      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
import { ref, watch } from 'vue'
import { onClickOutside } from '@vueuse/core' 
import { X, History, Activity } from 'lucide-vue-next'
import { useToast } from 'vue-toastification'

const props = defineProps({
  isOpen: Boolean,
  workshopId: String,
  modName: String,
  isLoading: Boolean,
  logs: Array
})
const emit = defineEmits(['close'])
const toast = useToast()
const drawerRef = ref(null)

// 监听弹窗打开时拉取数据
watch(() => props.isOpen, (val) => {
  // if (val) fetchTimeline()
})

const formatDate = (ts) => {
  return new Date(ts).toLocaleString('zh-CN', {year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' })
}
// 监听点击外侧事件
onClickOutside(drawerRef, (event) => {
  if (props.isOpen && !event.target.closest('.timeline-trigger')) {
    emit('close')
  }
})

// 后端返回的 color 字段映射到 Tailwind
const getColorClass = (colorCode, target) => {
  const map = {
    'primary': `${target}-accent-primary`,
    'success': `${target}-accent-success`,
    'danger':  `${target}-accent-danger`,
    'warn':    `${target}-accent-warn `,
    'info':    `${target}-text-dim`,
    'text-dim': `${target}-text-dim`
  }
  return map[colorCode] || map['info']
}
</script>

<style scoped>
.slide-right-enter-active, .slide-right-leave-active { transition: transform 0.4s cubic-bezier(0.16, 1, 0.3, 1); }
.slide-right-enter-from, .slide-right-leave-to { transform: translateX(100%); }
</style>
