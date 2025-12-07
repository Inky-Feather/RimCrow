<template>
  <div class="overflow-hidden flex flex-col h-full ">
    <!-- 光圈 -->
    <div :class="`absolute inset-0 border-2 border-accent-${listColor}/20 rounded-2xl pointer-events-none z-0`"></div>
    <!-- 标题栏 -->
    <div :class="`px-3 py-2 border-b border-white/5 flex justify-between items-center bg-accent-${listColor}/10`">
        <span :class="`text-xs font-bold text-accent-${listColor} uppercase tracking-wider flex items-center gap-2`">
            <div :class="`w-1.5 h-1.5 rounded-full bg-accent-${listColor} shadow-lg shadow-accent-primary`"></div>
            {{ title }}
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
    
    <!-- 列表区（底部渐变隐藏） -->
    <div class="overflow-y-auto flex-1 flex pb-0.5 after:pointer-events-none 
        after:content-[''] after:absolute after:bottom-0 after:w-full after:h-10 
        after:bg-linear-to-t after:from-bg-deep/80 after:to-transparent">
      
      <!-- 左侧辅助功能区 -->
      <div v-if="hasSidebar" class="size-14 flex-none">

      </div>

      <!-- 列表主体 -->
      <div class="flex-1 overflow-auto h-full pl-1 pr-1 relative" @click.self="store.clearSelection()">
        <!-- Active 模式背景线 -->
        <!-- <div v-if="variant === 'inactive'" class="absolute left-[-6px] top-4 bottom-4 w-0.5 bg-white/5 rounded z-[-1]"></div> -->
        
        <div v-if="proxyList.length === 0" class="absolute flex rounded-lg top-0 bottom-0 left-0 right-0 m-2 items-center justify-center border-2 border-dashed text-gray-600 text-xs bg-bg-deep/90 select-none pointer-events-none">
            可拖拽模组到此
            <!-- 点阵背景 -->
            <div class="absolute inset-0 opacity-[0.05] pointer-events-none" style="background-image: radial-gradient(#fff 1px, transparent 1px); background-size: 20px 20px;"></div>
        </div>

        <VueDraggable v-model="proxyList" ref="div" ghostClass="ghost" :delay="300"
          :group="{ name: 'mods', pull: 'mods', put: true, revertOnSpill: true }" :animation="150"
          class="h-full gap-0.5 p-1 space-y-1 overflow-y-scroll"
          @choose="onChoose"
          @unchoose="onUnchoose"
          @add="onAdd"
          @start="onDragStart"
          @update="onDragUpdate"
          @end="onDragEnd">

          <ModItem v-for="(id, index) in proxyList" :id="id" :index="index" :key="id" 
            @click.stop="handleClick($event, id, self)" 
            :is-selected="store.selectedIds.has(id)">
          </ModItem>

        </VueDraggable>

      </div>

    </div>

  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { type DraggableEvent, type UseDraggableReturn, VueDraggable } from 'vue-draggable-plus'
import { useModStore } from '../stores/modStore'
import ModItem from './ModItem.vue'



// 这里 modelValue 接收纯 ID 数组
const props = defineProps({
  modelValue: { type: Array, required: true }, // Array<string>
  title: { type: String, default: '启用' }, // 'active' | 'inactive' | 'temp'
  hasSidebar: { type: Boolean, default: false }, // 'active' | 'inactive' | 'temp'
  listColor: { type: String, default: 'primary' } // danger/highlight/special/cool/primary/success/tip/warm/secondary/warning
})

const emit = defineEmits(['update:modelValue'])
const store = useModStore()

// --- 1. 核心数据代理 ---
// VueDraggable 需要操作数组，我们在这里做 ID <-> Object 的双向转换
// 其实 VueDraggable 如果绑定的是 ID 数组，它的 slot scope 给出的也是 ID。
// 所以我们可以直接绑定 ID 数组，只在 v-for 渲染时转换对象。
// 但为了能在拖拽时看到预览图，draggable 内部最好还是持有 ID。

const proxyList = computed({
  get() { return props.modelValue },
  set(val) { emit('update:modelValue', val as string[]) }
})

// --- 3. 选中与样式 ---
const handleClick = (event, id) => {
  // 按住 Ctrl 键进行多选
  const isMulti = event.ctrlKey || event.metaKey
  store.selectMod(id, isMulti)
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

/* .fade-move,
.fade-enter-active,
.fade-leave-active {
  transition: all 0.5s cubic-bezier(0.55, 0, 0.1, 1);
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
  transform: scaleY(0.01) translate(30px, 0);
}

.fade-leave-active {
  position: absolute;
} */

.ghost {
  opacity: 0.5;
  border: 2px dashed var(--drag-color);
  scale: 90%;
  padding: 5px;
  border-radius: 10px;
  /* transform: scale(0.9);
  transition: none; */
}

</style>