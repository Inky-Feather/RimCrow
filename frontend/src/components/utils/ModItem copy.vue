<!-- ModItem.vue -->
<template>
  <div class="flex items-center gap-1.5 p-1 rounded-lg border border-white/5 group shadow-sm"
    :class="getCardClass(id)" :style="{ '--drag-color': `var(--color-accent-${listColor})` }"
    @click.stop="$emit('toggle-select')"
    @mouseenter="handleMouseEnter"
    @mouseleave="handleMouseLeave"
    @mousemove="handleMouseMove"
    :data-id="id"
  >
    <!-- 内容区域 -->
    <!-- 序号（通过位数计算动态调整字体大小） -->
    <div :style="{ fontSize: 18-(index+1).toString().length*3 + 'px' }" 
      :class="`w-5 h-5 flex items-center justify-center rounded text-accent-${listColor}/50 bg-accent-${listColor}/10 hover:text-text-main hover:bg-accent-${listColor}/50`">
      {{ index+1 }}
    </div>
    
      
    <!-- 图标 -->
    <img v-if="!modData.is_missing && modData.preview_path" :src="modIcon" loading="lazy"
      :class="`w-8 h-8 rounded bg-black/50 object-cover border border-accent-${listColor}/30 pointer-events-none`">
    <div v-else-if="modData.is_missing" class="w-8 h-8 rounded flex items-center justify-center text-red-500 font-bold text-lg bg-red-900/50 border border-red-500/30">!</div>
    <div v-else class="w-8 h-8 rounded border-2 border-dashed border-white/10 flex items-center justify-center">
      <svg class="w-6 h-6 opacity-20" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"></path></svg>
    </div>

    <!-- 文字信息 -->
    <div class="flex-1 min-w-0 ">
      <div v-if="modData.alias" class="text-[10px] text-text-dim truncate font-mono ">
        {{ modData.name }}
      </div>

      <div class="text-[12px] font-medium truncate" :class="modData.is_missing ? 'text-red-400' : 'text-text-main'">
        {{ modData.alias ? modData.alias : (modData.name ? modData.name : id) }}
      </div>

      <div class="flex w-full overflow-hidden overflow-x-scroll scroll-hide gap-0.5 mt-1" v-if="modData?.tags && modData.tags.length">
        <span v-for="tag in modData.tags" :key="tag" class="font-mono px-0.5 py-0 my-0 rounded-md bg-accent-primary/10 text-accent-primary text-[10px] font-bold border border-accent-primary/10 drop-shadow-xl/25">
          {{ tag }}
        </span>
      </div>
    </div>
    
    <!-- 缺失警告 -->
    <button v-if="modData.is_missing" :class="`rounded-4xl p-1 cursor-help 
      text-accent-danger hover:scale-110 text-xs font-bold text-shadow-2xs text-shadow-black hover:shadow-bg-deep/50 
      transition-all`">
      <svg width="16" height="16" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path fill-rule="evenodd" clip-rule="evenodd" d="M24 5L2 43H46L24 5Z" fill="none" stroke="currentColor" stroke-width="4" stroke-linejoin="round"/>
        <path d="M24 35V36" stroke="currentColor" stroke-width="4" stroke-linecap="round"/><path d="M24 19.0005L24.0083 29" stroke="currentColor" stroke-width="4" stroke-linecap="round"/>
      </svg>
    </button>
    
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useModStore } from '../../stores/modStore'

const props = defineProps({
  id: { type: String, required: true },
  index: { type: Number, required: true },
  listColor: { type: String, default: 'primary'}, // 用于不同列表的颜色区分
  isSelected: { type: Boolean, default: false },
  isDragging: { type: Boolean, default: false } // 用于外部控制样式
})

defineEmits(['toggle-select'])

const store = useModStore()

// 使用 computed 缓存，只有当 id 变化时才重新获取对象
// 极大地减少了父组件重绘时的计算量
const modData = computed(() => store.getModById(props.id))
const modIcon = computed(() => store.getAssetUrl(props.id))

const getCardClass = (id) => {
  const isSelected = store.selectedIds.has(id)
  const base = isSelected 
    ? 'ring-1 ring-accent-success z-10' 
    : 'bg-bg-surface hover:border-white/10 hover:bg-[#2d3a4f]'
  
  const missing = store.getModById(id).is_missing ? 'bg-red-900/20 border-red-500/30' : ''
  
  return `${base} ${missing}`
}

// 这两个函数目前没有实际用处，如果你有悬停效果或拖拽提示，可以实现它们
const handleMouseEnter = () => { /* console.log('enter', props.id); */ };
const handleMouseLeave = () => { /* console.log('leave', props.id); */ };
const handleMouseMove = () => { /* console.log('move', props.id); */ };
</script>

<style scoped>
  
</style>