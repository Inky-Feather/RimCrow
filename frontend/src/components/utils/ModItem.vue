<!-- ModItem.vue -->
<template>
  <div class="flex items-center gap-1" @mousedown.left="$emit('toggle-select', $event, item_id)"
      @click.right="handleContextMenu">
      <!-- 序号（通过位数计算动态调整字体大小） -->
      <!-- :style="{ fontSize: 18-(index+1).toString().length*3 + 'px' }" -->
    <div 
      class="w-6 h-6 min-w-6 min-h-6 flex items-center justify-center rounded"
      :class="[props.isSelected ? `text-text-main bg-accent-${listColor}/50` : `text-accent-${listColor}/50 bg-accent-${listColor}/10 hover:text-text-main hover:bg-accent-${listColor}/50`,
        `digits-${(index+1).toString().length}`]"
      @mouseenter="$emit('toggle-select', $event, item_id, true)">
      {{ index+1 }}
    </div>
    
    <!-- 内容区域 -->
    <div class="drag-handle flex-1 flex items-center min-w-0 gap-1.5 p-1 rounded-lg border hover:opacity-80 backdrop-blur-sm border-white/5 group shadow-sm"
      :class="[getCardClass(item_id), searchMatch ? 'ring-2 ring-yellow-400 scale-[1.02] z-20' : '']" 
      :style="getCardStyle(item_id)"
      
      @mouseenter="handleMouseEnter"
      @mousemove="handleMouseMove"
      @mouseleave="handleMouseLeave"
      :data-id="item_id"
    >
      <!-- 图标 -->
      <img v-if="!modData.is_missing && modData.thumb_url" :src="modData.thumb_url"
        :class="`w-8 h-8 rounded object-cover border border-accent-${listColor}/30 pointer-events-none`">
      <div v-else-if="modData.is_missing" class="w-8 h-8 rounded flex items-center justify-center text-red-500 font-bold text-lg bg-red-900/50 border border-red-500/30">!</div>
      <div v-else class="w-8 h-8 rounded border-2 border-dashed border-white/10 flex items-center justify-center">
        <svg class="w-6 h-6 opacity-20" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"></path></svg>
      </div>

      <!-- 文字信息 -->
      <div class="flex-1 min-w-0 ">
        <div v-if="modData.alias_name" class="text-[10px] text-text-dim truncate font-mono ">
          {{ modData.name }}
        </div>

        <div class="text-[12px] font-medium truncate" :class="modData.is_missing ? 'text-red-400' : 'text-text-main'">
          {{ modData.alias_name ? modData.alias_name : (modData.name ? modData.name : item_id) }}
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
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useModStore } from '../../stores/modStore'
import { useContextMenuStore } from '../../stores/contextMenuStore'

const props = defineProps({
  item_id: { type: String, required: true },
  index: { type: Number, required: true },
  listColor: { type: String, default: 'primary'}, // 用于不同列表的颜色区分
  isSelected: { type: Boolean, default: false },
  isDragging: { type: Boolean, default: false }, // 用于外部控制样式
  searchMatch: { type: Boolean, default: false } // 是否是当前搜索焦点
})

defineEmits(['toggle-select'])

const store = useModStore()
const menuStore = useContextMenuStore()

// 使用 computed 缓存，只有当 id 变化时才重新获取对象
// 极大地减少了父组件重绘时的计算量
const modData = computed(() => store.getModById(props.item_id))
// const modIcon = computed(() => store.getIconUrl(props.id))

const getCardClass = (id) => {
  const base = props.isSelected 
    ? 'ring-1 ring-accent-success ' 
    : 'bg-bg-surface hover:border-white/10 hover:bg-[#2d3a4f]'
  
  const missing = store.getModById(id).is_missing ? 'bg-red-900/20 border-red-500/30' : ''
  return `${base} ${missing}`
}
const getCardStyle = (id) => {
  const base = {'--drag-color': `var(--color-accent-${props.listColor})`}
  const color = store.getModById(id).sign_color
  if (!color) return base
  base['--mod-color'] = hexToRgb(color)
  base['backgroundColor'] = `rgba(${hexToRgb(color)},0.2)`
  base['borderColor'] = `rgba(${hexToRgb(color)},0.3)`
  return base
}

// 颜色格式转换
const hexToRgb = (hex) => {
  if (!hex || typeof hex !== 'string') return `0, 0, 0`; // 返回纯组件字符串
  let cleanHex = hex.replace('#', '');
  if (cleanHex.length === 3) {
    cleanHex = cleanHex.split('').map(char => char + char).join('');
  }
  // 确保是六位
  if (cleanHex.length !== 6) {
    console.error(`Invalid hex color: ${hex}`);
    return `0, 0, 0`;
  }
  // 提取 R, G, B 分量，并从十六进制转换为十进制
  const r = parseInt(cleanHex.substring(0, 2), 16);
  const g = parseInt(cleanHex.substring(2, 4), 16);
  const b = parseInt(cleanHex.substring(4, 6), 16);
  return `${r}, ${g}, ${b}`;
};

// 这两个函数目前没有实际用处，如果你有悬停效果或拖拽提示，可以实现它们
const handleMouseEnter = (e) => { 
};

const handleMouseMove = (e) => { 
};

const handleMouseLeave = (e) => { 
};

const handleContextMenu = (event) => {
  menuStore.open(event, [
    { label: '打开文件夹', action: () => openFolder() },
    { divider: true },
    { label: '删除', danger: true, action: () => deleteMod() }
  ])
}

</script>

<style scoped>
.digits-1 { font-size: 18px; }
.digits-2 { font-size: 15px; }
.digits-3 { font-size: 12px; }
.digits-4 { font-size: 9px; }
</style>