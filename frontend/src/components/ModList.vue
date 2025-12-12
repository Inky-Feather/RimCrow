<template>
  <div class="flex flex-col relative h-full bg-bg-surface/40 backdrop-blur-sm shadow-2xl"
       :class="`border-2 rounded-2xl border-accent-${listColor}/20 overflow-hidden`">
    <!-- 标题栏 -->
    <div :class="`px-3 py-2 border-b rounded-t-2xl border-white/5 flex justify-between items-center bg-accent-${listColor}/10`">
        <span :class="`text-xs font-bold text-accent-${listColor} uppercase tracking-wider flex items-center gap-2`">
            <div :class="`w-1.5 h-1.5 rounded-full bg-accent-${listColor} shadow-lg shadow-accent-primary`"></div>
            {{ title }}
        </span>
        <span :class="`text-[10px] bg-black/30 px-2 py-0.5 rounded text-accent-${listColor}`">{{ proxyList.length }}</span>
    </div>
    <!-- 搜索栏 -->
    <div class="px-2 py-1 w-full items-center shadow-xl">
      <div class="inline-flex w-full items-center py-0.5" >
        <input type="text" placeholder="搜索模组名称或包 ID..." 
          :class="`flex-1 px-2 py-1 rounded-lg transition-all bg-bg-deep/30 border border-white/10 text-sm 
          text-white placeholder:text-text-dim focus:border-accent-${listColor} focus:outline-none 
          focus:bg-bg-deep/90 min-w-0`" />
        <button :class="`ml-2 px-3 py-1 rounded-lg bg-accent-${listColor}/50 hover:bg-accent-${listColor} 
          text-text-dim hover:text-text-main text-xs font-bold shadow-lg shadow-accent-${listColor}/10 
          transition-all`">定位</button>
      </div>
      <div class="inline-flex w-full items-center py-1" >
        <input type="text" placeholder="搜索模组名称或包 ID..." 
          :class="`flex-1 px-2 py-1 rounded-lg transition-all bg-bg-deep/30 border border-white/10 text-sm 
          text-white placeholder:text-text-dim focus:border-accent-${listColor} focus:outline-none 
          focus:bg-bg-deep/90 min-w-0`" />
        <button :class="`ml-2 px-3 py-1 rounded-lg bg-accent-${listColor}/50 hover:bg-accent-${listColor} 
          text-text-dim hover:text-text-main text-xs font-bold shadow-lg shadow-accent-${listColor}/10 
          transition-all`">筛选</button>
      </div>
    </div>
    
    <!-- 列表区（底部渐变隐藏） -->
    <div class="flex-1 flex pb-0.5 overflow-y-auto after:pointer-events-none 
        after:content-[''] after:absolute after:bottom-0 after:w-full after:h-10 
        after:bg-linear-to-t after:from-bg-deep/80 after:to-transparent">
      
      <!-- 左侧辅助功能区 -->
      <div v-show="hasSidebar" class="size-14 flex-none">

      </div>

      <!-- 列表主体 -->
      <div class="flex-1 h-full pl-1 pr-1 min-w-0 relative" @click.self="store.clearSelection()">

        <div v-show="proxyList.length === 0" class="absolute flex rounded-lg top-0 bottom-0 left-0 right-0 m-1 items-center justify-center border-2 border-dashed text-gray-600 text-xs bg-bg-deep/90 select-none pointer-events-none">
            可拖拽模组到此
            <!-- 点阵背景 -->
            <div class="absolute inset-0 opacity-[0.05] pointer-events-none" style="background-image: radial-gradient(#fff 1px, transparent 1px); background-size: 20px 20px;"></div>
        </div>

        <!-- <VirtualList v-model="proxyList1" dataKey="id" :keeps="50" class="h-full p-1" placeholderClass="ghost" wrapClass="space-y-1" 
          :fallbackOnBody="true" :scrollSpeed="{x:0, y:10}"
          :group="{ name: 'mods', pull: 'mods', put: true, revertDrag: true }" :animation="150">
          <template v-slot:item="{ record, index, dataKey }">
            <ModItem :id="dataKey" :index="index" :key="dataKey" :list-color="listColor"
              @click.stop="handleClick($event, dataKey)" >
            </ModItem>
          </template>
        </VirtualList> -->

        <VirtualList v-model="proxyList1" dataKey="id" :keeps="50" class="h-full p-1" placeholderClass="ghost" wrapClass="space-y-1" 
          :fallbackOnBody="true" :scrollSpeed="{x:0, y:10}" handle=".drag-handle"
          :group="{ name: 'mods', pull: 'mods', put: true, revertDrag: true }" :animation="150"
          @mousedown.left="handleMousePressed(true)" @mouseup.left="handleMousePressed(false)" @mouseleave="handleMousePressed(false)">
          <template v-slot:item="{ record, index, dataKey }">
            <ModItem :id="dataKey" :index="index" :key="dataKey" :list-color="listColor" 
              :is-selected="store.selectedIds.has(dataKey)"
               @toggle-select="handleClick" >
            </ModItem>
          </template>
        </VirtualList>

      </div>

    </div>

  </div>
</template>

<script setup lang="ts">
import { computed, ref} from 'vue'
import VirtualList from 'vue-virtual-sortable';
import { useModStore } from '../stores/modStore'
import ModItem from './utils/ModItem.vue'



// 这里 modelValue 接收纯 ID 数组
const props = defineProps({
  title: { type: String, default: 'Default' },
  modelValue: { type: Array as () => string[], required: true }, // Array<string>
  hasSidebar: { type: Boolean, default: false },
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
  set(val) { 
    emit('update:modelValue', val) 
    store.markDirty() // 任何对列表的修改都标记为未保存
  }
})

const proxyList1 = computed({
  get() {
    // 将 ID 数组转换为 { id: string } 对象数组供 VirtualList 使用
    return props.modelValue.map(id => ({ id: id }));
  },
  set(val: any[]) { // val 将是 { id: string }[]
    // 将 { id: string } 数组转换回 ID 数组，并发送给父组件
    const idList = val.map(item => item.id);
    emit('update:modelValue', idList);
    store.markDirty();
  }
});

// 用于记录拖拽开始时的原始状态，以支持取消拖拽返回原位
interface DragOriginInfo {
  list: string[]; // 原始列表的引用 (activeIds, tempIds 等)
  index: number; // 原始索引
  ids: string[]; // 拖拽的ID（单选或多选）
}
const dragOrigin = ref<DragOriginInfo | null>(null);

const mousePressed = ref(false);
const handleMousePressed = (state:boolean) => {
  mousePressed.value = state;
  
}
// --- 3. 选中与样式 ---
const handleClick = (event: MouseEvent, id: string, isPull=false) => {
  // 只响应左键点击或拖拽中的进入
  const isLeftButton = event.button === 0 && !isPull;
  const isFromDrag = mousePressed.value && isPull;
  if (!(isLeftButton || isFromDrag)) {
    return
  }
  // if (!((event.button == 0 && !isPull)||(mousePressed.value && isPull))) return; // 只响应左键点击或左键拖拽
  const isMulti = event.ctrlKey || event.metaKey
  const isRange = event.shiftKey
  store.selectMod(id, isMulti, isRange)
}

// 拖拽开始时触发
const onDragStart = (e: DraggableEvent) => {
  console.log('start', e)
  store.clearSelection() // 拖拽开始时，清空当前选择，只选中被拖拽的元素
  // Sortable.js 会自动选中被拖拽的元素并为其添加 `chosen` 和 `selected` 类
  // 但为了 Store 的 `selectedIds` 也能反映，我们手动添加
  const draggedIds: string[] = (e.items || [e.item]).map(el => el.dataset.id || el.id || ''); // e.items 可能是多选，e.item 是单选
  
  // 对于多选拖拽，Sortable.js 会在开始时将 `selected` 的元素也添加到 `e.items`
  // 如果是多选，且 `e.item` 是 `selectedIds` 中的一个，则拖拽的是整个 `selectedIds`
  if (draggedIds.length === 1 && store.selectedIds.has(draggedIds[0])) {
    // 单独拖拽一个已选中的项，此时应该拖拽所有选中的项
    dragOrigin.value = {
      list: proxyList.value,
      index: e.oldIndex,
      ids: Array.from(store.selectedIds.values())
    };
  } else {
    // 否则只拖拽 e.item
    dragOrigin.value = {
      list: proxyList.value,
      index: e.oldIndex,
      ids: draggedIds.filter(Boolean)
    };
  }

  // 确保拖拽的元素也被选中，这样 `selected-mod` 样式会生效
  dragOrigin.value.ids.forEach(id => store.selectedIds.add(id));
}
// 拖拽结束时触发
const onDragEnd = (e: DraggableEvent) => {
  console.log('onEnd', e)
  store.clearSelection(); // 拖拽结束后清除选择

  if (!dragOrigin.value) {
    console.warn("dragOrigin is null on drag end.");
    return;
  }

  // 判断是否是取消拖拽（即没有被放入有效位置或返回原列表原位）
  const isCanceled = e.to === e.from && e.oldIndex === e.newIndex; // 拖回原位
  const isDroppedOutside = !e.to; // 拖到外部区域，Sortable.js 通常会自动处理返回

  if (isCanceled) {
    console.log("Drag cancelled, returning to original position.");
    // 理论上 VueDraggable 会自行处理，但为了严谨，可以在这里做一些手动插入
    // 如果 proxyList 已经更新，那就不需要再动了
  } else if (isDroppedOutside && e.pullMode !== 'clone') {
    // 拖拽到外部且不是克隆模式，可能需要手动恢复原始列表
    console.log("Drag dropped outside, trying to revert.");
    // 找到原始列表，将拖拽项插入回原始位置
    const originalList = dragOrigin.value.list;
    const originalIndex = dragOrigin.value.index;
    const draggedIds = dragOrigin.value.ids;

    // 移除已从 `from` 列表中删除的项 (如果它们被 Sortable.js 移除了)
    // 然后将它们插入回原始位置
    // 注意：这里的 proxyList 已经是 VueDraggable 自动更新后的状态
    // 我们需要的是 `modelValue` 的变更
    
    // 重新获取当前 proxyList 的值 (因为 Sortable.js 可能已经自动更新了)
    const currentList = props.modelValue as string[];
    
    // 移除所有拖拽项在当前列表中的实例（如果存在）
    let tempCurrentList = [...currentList];
    for (const id of draggedIds) {
      const indexToRemove = tempCurrentList.indexOf(id);
      if (indexToRemove !== -1) {
        tempCurrentList.splice(indexToRemove, 1);
      }
    }
    
    // 将拖拽项插入回原始位置
    const finalIds = [...tempCurrentList.slice(0, originalIndex), ...draggedIds, ...tempCurrentList.slice(originalIndex)];
    emit('update:modelValue', finalIds);
    store.markDirty();
  } else {
    // 成功拖拽，VueDraggable 会自动更新 modelValue
    store.markDirty();
  }

  dragOrigin.value = null; // 清空记录
}


// 跨列表拖拽添加时触发
function onAdd(e: DraggableEvent) {
  console.log('add', e)
  // 当元素从其他列表拖拽到当前列表时
  // Sortable.js 会自动将元素从源列表移除，并添加到目标列表的 DOM 和数据中
  // 如果是多选，e.item 是第一个被拖拽的元素，e.items 是所有被拖拽的元素
  // 但 proxyList 的 setter 已经处理了 update:modelValue
  store.markDirty()
}

// 拖拽更新时触发，仅限当前列表内排序变化
const onDragUpdate = (e: DraggableEvent) => {
  console.log('update', e)
  store.markDirty()
}

const onChoose = (e: DraggableEvent) => {
  console.log('Choose', e)
  // Sortable.js 内部会将 `chosen` 类添加到被选中的元素
  // 对于多选，`selected` 类会添加到所有选中的元素
}
const onUnchoose = (e: DraggableEvent) => {
  console.log('Unchoose', e)
  // `unchoose` 在选择被取消时触发
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