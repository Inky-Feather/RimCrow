<template>
  <div class="overflow-hidden flex flex-col h-full">
    <!-- 光圈 -->
    <!-- <div class="absolute inset-0 border-2 border-accent-success/10 rounded-2xl pointer-events-none z-0"></div> -->
    <!-- 标题栏 -->
    <div :class="`px-3 py-2 border-b border-white/5 flex justify-between items-center bg-accent-${listColor}/10`">
        <span :class="`text-xs font-bold text-accent-${listColor} uppercase tracking-wider flex items-center gap-2`">
            <div :class="`w-1.5 h-1.5 rounded-full bg-accent-${listColor} shadow-lg shadow-accent-${listColor}`"></div>
            {{ variant }}
        </span>
        <span :class="`text-[10px] bg-black/30 px-2 py-0.5 rounded text-accent-${listColor}`">{{ modelValue.length }}</span>
    </div>
    <!-- 搜索栏 -->
    <div class="px-2 py-1 w-full items-center shadow-xl">
      <div class="inline-flex w-full items-center py-0.5" >
        <input type="text" placeholder="搜索模组名称或包 ID..." 
          :class="`flex-1 px-2 py-1 rounded-lg transition-all bg-bg-deep/30 border border-white/10 text-sm 
          text-white placeholder:text-text-dim focus:border-accent-${listColor} focus:outline-none 
          focus:bg-bg-deep/90`" />
        <button :class="`ml-2 px-3 py-1 rounded-lg bg-accent-${listColor}/50 hover:bg-accent-${listColor} 
          text-text-dim hover:text-text-main text-xs font-bold shadow-lg shadow-accent-${listColor}/10 
          transition-all`">定位</button>
      </div>
      <div class="inline-flex w-full items-center py-1" >
        <input type="text" placeholder="搜索模组名称或包 ID..." 
          :class="`flex-1 px-2 py-1 rounded-lg transition-all bg-bg-deep/30 border border-white/10 text-sm 
          text-white placeholder:text-text-dim focus:border-accent-${listColor} focus:outline-none 
          focus:bg-bg-deep/90`" />
        <button :class="`ml-2 px-3 py-1 rounded-lg bg-accent-${listColor}/50 hover:bg-accent-${listColor} 
          text-text-dim hover:text-text-main text-xs font-bold shadow-lg shadow-accent-${listColor}/10 
          transition-all`">筛选</button>
      </div>
    </div>
    
    <!-- 列表区 -->
    <div class="overflow-y-auto flex-1 flex pb-0.5 after:pointer-events-none 
        after:content-[''] after:absolute after:bottom-0 after:w-full after:h-10 
        after:bg-linear-to-t after:from-bg-deep/80 after:to-transparent">
      <!-- 左侧辅助功能区 -->
      <div v-if="variant === 'active'" class="size-14 flex-none">

      </div>

      <!-- 列表主体 -->
      <div class="flex-1 h-full px-2 relative" @click.self="store.clearSelection()">

        <VueDraggable :group="{ name: 'groups', pull: true, put: 'groups' }" :animation="150" handle=".drag-handle" 
          class="h-full p-1 space-y-1.5 overflow-y-scroll" ghostClass="ghost" tag="div" v-model="store.groupList">
          
          <!-- 折叠组 -->
          <!-- 始终保持 <details> 为 open 状态（防止组件收起时瞬间隐藏内容display: none） -->
          <details open v-for="item in store.groupList" :key="item.groupId" :style="{ '--drag-color': `var(--color-accent-${listColor})`, '--rgb-components': getRgbComponents(item.color)}" 
            class="group overflow-hidden [&amp;_summary::-webkit-details-marker]:hidden">
            <!-- 标题区 -->
            <summary @click.prevent="toggle(item)" :aria-expanded="expandedIds.has(item.groupId)" 
              :class="['list-none select-none px-2 flex text-text-dim hover:text-text-main items-center justify-between gap-1 rounded-lg font-medium', 
                'bg-[rgba(var(--rgb-components),0.2)] hover:bg-[rgba(var(--rgb-components),0.4)]']">
              <!-- 抓取图标 -->
              <div class="drag-handle cursor-move p-1 text-text-dim hover:text-text-main hover:scale-130 transition-all">
                <svg width="18" height="18" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
                  <path d="M24 44C35.0457 44 44 35.0457 44 24C44 12.9543 35.0457 4 24 4C12.9543 4 4 12.9543 4 24C4 35.0457 12.9543 44 24 44Z" fill="none" stroke="currentColor" stroke-width="4" stroke-linejoin="round"/>
                  <path d="M20 20L24 16L28 20" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>
                  <path d="M20 28L24 32L28 28" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
              </div>
              <!-- 颜色选择与展开显示 -->
              <button @click.stop="" :class="`w-4 h-4 rounded-full bg-[rgba(var(--rgb-components),1)] shadow-lg cursor-pointer text-text-main transition-all 
                hover:text-transparent hover:bg-[rgba(var(--rgb-components),1)] hover:drop-shadow-xl hover:drop-shadow-accent-${listColor} hover:scale-130`">
                <svg :class="expandedIds.has(item.groupId) ? '-rotate-180' : ''" class="transition-transform duration-300" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"></path>
                </svg>
              </button>
              <!-- 标题 -->
              <span :class="`flex-1 text-ms px-2 text-text-main font-bold uppercase tracking-wider flex items-center gap-2`">
                  {{ item.name }}
              </span>
              <span :class="`text-[10px] bg-black/30 px-2 py-0.5 rounded text-[rgba(var(--rgb-components),1)]`">{{ item.modIds.length }}</span>
              
              <!-- 编辑/删除 -->
              <span class="flex items-center">
                <button @click.stop="editItem(item)" :class="`rounded-lg p-1 hover:bg-accent-secondary/10 cursor-pointer 
                  text-text-dim hover:text-accent-secondary text-xs font-bold shadow-lg hover:shadow-bg-deep/50 
                  transition-all`">
                  <svg width="18" height="18" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path d="M7 42H43" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>
                    <path d="M11 26.7199V34H18.3172L39 13.3081L31.6951 6L11 26.7199Z" fill="none" stroke="currentColor" stroke-width="4" stroke-linejoin="round"/>
                  </svg>
                  <!-- <svg v-if="" width="18" height="18" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path d="M24 44C29.5228 44 34.5228 41.7614 38.1421 38.1421C41.7614 34.5228 44 29.5228 44 24C44 18.4772 41.7614 13.4772 38.1421 9.85786C34.5228 6.23858 29.5228 4 24 4C18.4772 4 13.4772 6.23858 9.85786 9.85786C6.23858 13.4772 4 18.4772 4 24C4 29.5228 6.23858 34.5228 9.85786 38.1421C13.4772 41.7614 18.4772 44 24 44Z" fill="none" stroke="currentColor" stroke-width="4" stroke-linejoin="round"/>
                    <path d="M16 24L22 30L34 18" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>
                  </svg> -->
                </button>
                <button @click.stop="deleteGroup(item)" :class="`rounded-lg p-1 hover:bg-accent-danger/10 cursor-pointer 
                  text-text-dim hover:text-accent-danger text-xs font-bold shadow-lg hover:shadow-bg-deep/50 
                  transition-all`">
                  <svg width="18" height="18" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path d="M8 11L40 11" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>
                    <path d="M18 5L30 5" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>
                    <path d="M12 17H36V40C36 41.6569 34.6569 43 33 43H15C13.3431 43 12 41.6569 12 40V17Z" fill="none" stroke="currentColor" stroke-width="4" stroke-linejoin="round"/>
                    <path d="M20 25L28 33" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>
                    <path d="M28 25L20 33" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>
                  </svg>
                </button>
              </span>
            </summary>

            <!-- 内容区 -->
            <div class="grid transition-[grid-template-rows] duration-200 ease"
              :class="expandedIds.has(item.groupId) ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]'">
              <div class="overflow-hidden h-full">
                <div :class="`p-1 mx-1 min-h-15 bg-[rgba(var(--rgb-components),0.1)] rounded-b-lg shadow-2xsl relative`">
                  

                  <!-- 分组内层模组列表 -->
                  <VueDraggable v-model="item.modIds" ref="div" ghostClass="ghost" 
                    :group="{ name: 'mods', pull: 'clone', put: 'mods' }" :animation="150"
                    class="h-full min-h-15 gap-0.5 p-1 space-y-1"
                    @choose="onChoose"
                    @unchoose="onUnchoose"
                    @add="onAdd"
                    @start="onDragStart"
                    @update="onDragUpdate"
                    @end="onDragEnd"
                  >

                    <div v-for="(id, index) in item.modIds"
                      :key="id"
                      :id="id"
                      @click.stop="handleClick($event, id, self)"
                      :style="`background-image: url(${store.getAssetUrl(id)}); background-size: cover;background-position: center;position: relative;`"
                      class=" relative flex items-center overflow-hidden gap-1.5 p-1 cursor-move rounded-lg border group shadow-sm select-none"
                      :class="getCardClass(id)"
                    >
                      <!-- 序号 -->
                      <div :style="{ fontSize: 18-index.toString().length*3 + 'px' }" :class="`w-5 h-5 flex items-center justify-center rounded 
                        text-[rgba(var(--rgb-components),0.6)] bg-[rgba(var(--rgb-components),0.1)]`">{{ index+1 }}</div>
                      
                      <!-- 图标 -->
                      <img v-if="!store.getModById(id).is_missing && store.getModById(id).preview_path" :src="store.getAssetUrl(id)" 
                        :class="`w-8 h-8 rounded bg-black/50 object-cover border border-[rgba(var(--rgb-components),0.3)] pointer-events-none`">
                      <div v-else-if="store.getModById(id).is_missing" class="w-8 h-8 rounded flex items-center justify-center text-red-500 font-bold text-lg bg-red-900/50 border border-red-500/30">!</div>
                      <div v-else class="w-8 h-8 rounded border-2 border-dashed border-white/10 flex items-center justify-center">
                        <svg class="w-6 h-6 opacity-20" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"></path>
                        </svg>
                      </div>
                      

                      <!-- 文字信息 -->
                      <div class="flex-1 min-w-0 ">
                        <div v-if="store.getModById(id).alias" class="text-[10px] text-text-dim truncate font-mono ">
                          {{ store.getModById(id).name }}
                        </div>

                        <div class="text-xm font-medium truncate" :class="store.getModById(id).is_missing ? 'text-red-400' : 'text-text-main'">
                          {{ store.getModById(id).alias ? store.getModById(id).alias : (store.getModById(id).name ? store.getModById(id).name : id) }}
                        </div>

                        <div class="flex w-full overflow-hidden overflow-x-scroll scroll-hide gap-0.5 mt-1" v-if="store.getModById(id)?.tags && store.getModById(id).tags.length">
                          <span v-for="tag in store.getModById(id).tags" :key="tag" class="font-mono px-0.5 py-0 my-0 rounded-md bg-accent-primary/10 text-accent-primary text-[10px] font-bold border border-accent-primary/10 drop-shadow-xl/25">
                            {{ tag }}
                          </span>
                        </div>
                      </div>

                      <span class="">
                        <button :class="`rounded-4xl p-1 cursor-help 
                          text-accent-danger hover:scale-110 text-xs font-bold text-shadow-2xs text-shadow-black hover:shadow-bg-deep/50 
                          transition-all`">
                          <svg width="18" height="18" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
                            <path fill-rule="evenodd" clip-rule="evenodd" d="M24 5L2 43H46L24 5Z" fill="none" stroke="currentColor" stroke-width="4" stroke-linejoin="round"/>
                            <path d="M24 35V36" stroke="currentColor" stroke-width="4" stroke-linecap="round"/><path d="M24 19.0005L24.0083 29" stroke="currentColor" stroke-width="4" stroke-linecap="round"/>
                          </svg>
                        </button>
                        <!-- 删除按钮 -->
                        <button @click.stop="removeMod(item,index)" :class="`rounded-4xl p-1 hover:bg-accent-danger/10 cursor-pointer 
                          text-text-dim hover:text-accent-danger text-xs font-bold shadow-lg hover:shadow-bg-deep/50 
                          transition-all`">
                          <svg width="18" height="18" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
                            <path d="M14 14L34 34" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>
                            <path d="M14 34L34 14" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>
                          </svg>
                        </button>
                      </span>
                      
                    </div>
                  </VueDraggable>

                </div>
              </div>

            </div>

          </details>

        </VueDraggable>
        
        
        <!-- 悬浮功能按钮 -->
        <div class="absolute bottom-0 left-0 right-0 h-10 pointer-events-none 
            bg-linear-to-t from-bg-deep/80 to-transparent z-50">
          <div class="absolute bottom-2 right-2 pointer-events-auto flex gap-2">
            <button :class="`px-3 py-1 rounded-lg bg-accent-${listColor}/50 hover:bg-accent-${listColor} 
              text-text-dim hover:text-text-main text-xs font-bold shadow-lg shadow-accent-${listColor}/10 
              transition-all`">全部展开</button>
            <button :class="`px-3 py-1 rounded-lg bg-accent-${listColor}/50 hover:bg-accent-${listColor} 
              text-text-dim hover:text-text-main text-xs font-bold shadow-lg shadow-accent-${listColor}/10 
              transition-all`">全部折叠</button>
            <button :class="`px-3 py-1 rounded-lg bg-accent-${listColor}/50 hover:bg-accent-${listColor} 
              text-text-dim hover:text-text-main text-xs font-bold shadow-lg shadow-accent-${listColor}/10 
              transition-all`" @click="addGroup">+</button>
          </div>
        </div>

      </div>

    </div>

  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useModStore } from '../stores/modStore'
import { type DraggableEvent, type UseDraggableReturn, VueDraggable } from 'vue-draggable-plus'


// 这里 modelValue 接收纯 ID 数组
const props = defineProps({
  modelValue: { type: Array, required: true }, // Array<string>
  variant: { type: String, default: '启用' }, // 'active' | 'inactive' | 'temp'
  listColor: { type: String, default: 'primary' } // danger/highlight/special/cool/primary/success/tip/warm/secondary/warning
})

// 用一个 Set 存储所有被展开的 ID
const expandedIds = ref(new Set())
const toggle = (item) => {
  const id = item.groupId
  if (expandedIds.value.has(id)) {
    expandedIds.value.delete(id)
  } else {
    expandedIds.value.add(id)
  }
}

// 删除
const deleteGroup = (item) =>{
  store.groupList.splice(store.groupList.indexOf(item),1)
}
const removeMod = (group,index) =>{
  group.modIds.splice(index,1)
}
// 新建分组
const addGroup = () => {
  store.groupList.push({
    groupId: `group_${Date.now()}`,
    name: '新分组',
    color: `#${Math.floor(Math.random() * 16777216).toString(16).padStart(6, '0')}`,
    modIds: []
  })
}

const hexToRgb = (hex) => {
  if (!hex || typeof hex !== 'string') return `rgba(0, 0, 0)`;
  // 移除 # 符号
  let cleanHex = hex.replace('#', '');
  // 处理三位简写（如 #F00 转换为 #FF0000）
  if (cleanHex.length === 3) {
    cleanHex = cleanHex
      .split('')
      .map(char => char + char)
      .join('');
  }
  // 确保是六位
  if (cleanHex.length !== 6) {
    console.error(`Invalid hex color: ${hex}`);
    return `rgba(0, 0, 0)`; 
  }
  // 提取 R, G, B 分量，并从十六进制转换为十进制
  const r = parseInt(cleanHex.substring(0, 2), 16);
  const g = parseInt(cleanHex.substring(2, 4), 16);
  const b = parseInt(cleanHex.substring(4, 6), 16);
  return {r, g, b};
};
const hexToRgba = (hex, alpha = 0.5) => {
  if (!hex || typeof hex !== 'string') return `rgba(0, 0, 0, ${alpha})`;
  rgb=hexToRgb(hex)
  return `rgba(${rgb.r}, ${rgb.g}, ${rgb.b}, ${alpha})`;
};
const getRgbComponents = (hex) => {
    // 确保你的 hexToRgb 函数在这里被调用并返回 { r, g, b }
    const rgb = hexToRgb(hex);
    return `${rgb.r}, ${rgb.g}, ${rgb.b}`;
};

const emit = defineEmits(['update:modelValue'])
const store = useModStore()

// --- 1. 核心数据代理 ---
// VueDraggable 需要操作数组，我们在这里做 ID <-> Object 的双向转换
// 其实 VueDraggable 如果绑定的是 ID 数组，它的 slot scope 给出的也是 ID。
// 所以我们可以直接绑定 ID 数组，只在 v-for 渲染时转换对象。
// 但为了能在拖拽时看到预览图，draggable 内部最好还是持有 ID。

const proxyList = computed({
  get() { return props.modelValue },
  set(val) { emit('update:modelValue', val) }
})

// --- 2. 渲染列表 ---
// 只有在渲染层，我们才把 ID 变成 Object
const renderList = computed(() => {
  return props.modelValue.map(id => store.getModById(id))
})

// --- 3. 选中与样式 ---
const handleClick = (event, id) => {
  // 按住 Ctrl 键进行多选
  const isMulti = event.ctrlKey || event.metaKey
  store.selectMod(id, isMulti)
}

const getCardClass = (id) => {
  const isSelected = store.selectedIds.has(id)
  const base = isSelected 
    ? 'ring-1 ring-[#06b6d4] z-10' 
    : 'bg-[#1e293b] border-white/5 hover:border-white/10 hover:bg-[#2d3a4f]'
  
  const missing = store.getModById(id).is_missing ? 'bg-red-900/20 border-red-500/30' : ''
  
  return `${base} ${missing}`
}


// --- 4. 拖拽处理 (预留给成组拖拽) ---

const el = ref<UseDraggableReturn>()
function pause() {
  el.value?.pause()
}

function start() {
  el.value?.start()
}

// 拖拽开始时触发
const onDragStart = (e: DraggableEvent) => {
  console.log('start', e)
}
// 拖拽结束时触发
const onDragEnd = (e: DraggableEvent) => {
  console.log('onEnd', e)
}
// 跨列表拖拽添加时触发
function onAdd(e: DraggableEvent) {
  console.log('add', e)
}
// 拖拽更新时触发，仅限当前列表内排序变化
const onDragUpdate = (e: DraggableEvent) => {
  console.log('update', e)
}
const onChoose = (e: DraggableEvent) => {
  console.log('Choose', e)
}
const onUnchoose = (e: DraggableEvent) => {
  console.log('Unchoose', e)
}
</script>

<style scoped>

.ghost {
  opacity: 0.5;
  border: 2px dashed var(--drag-color);
  scale: 90%;
  padding: 5px;
  border-radius: 10px;
  /* transform: scale(0.9); */
  /* transition: none; */
}

</style>