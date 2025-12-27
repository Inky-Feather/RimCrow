<template>
  <div class="flex flex-col relative h-full bg-bg-surface/40 backdrop-blur-sm shadow-2xl"
       :class="`border-2 rounded-2xl border-accent-${listColor}/20 overflow-hidden`">
    <!-- 标题栏 -->
    <div :class="`px-3 py-2 border-b rounded-t-2xl border-white/5 flex justify-between items-center bg-accent-${listColor}/10`">
        <span :class="`text-xs font-bold text-accent-${listColor} uppercase tracking-wider flex items-center gap-2`">
            <div :class="`w-1.5 h-1.5 rounded-full bg-accent-${listColor} shadow-lg shadow-accent-primary`"></div>
            {{ title }}
            <!-- 状态提示 -->
            <span v-if="isFiltered" class="text-[10px] text-text-dim">(已筛选)</span>
            <span v-if="sortMode !== 'default'" class="text-[10px] text-text-dim">(已排序)</span>
        </span>
        <span v-if="isFiltered" :class="`text-[10px] bg-black/30 px-2 py-0.5 rounded text-accent-${listColor}`">
          {{ displayList.length }} / {{ modelValue.length }}
        </span>
        <span v-else :class="`text-[10px] bg-black/30 px-2 py-0.5 rounded text-accent-${listColor}`">{{ modelValue.length }}</span>
    </div>
    
    <!-- 工具栏 (搜索 & 筛选) -->
    <div class="px-2 py-1 w-full flex flex-col gap-1 shadow-xl bg-bg-deep/20 z-50">
      <!-- 搜索定位 (Find) -->
      <TagsInput :suggestionData="allMods" :suggestionSchema="modSchema" 
        v-model="searchQuery" v-model:logic="searchLogic" :cacheKey="store.dataVersion || allMods.length"
        @search="" class="z-10">
        <template #right>
          <!-- 定位按钮 -->
          <button @click="executeSearch(true)" 
            :class="`px-3 py-1 rounded-lg bg-accent-${listColor}/50 hover:bg-accent-${listColor} 
            text-text-dim hover:text-text-main text-xs font-bold shadow-lg shadow-accent-${listColor}/10 
            transition-all`">
            定位
          </button>
        </template>
      </TagsInput>
      <!-- 筛选过滤 (Filter) -->
      <TagsInput :suggestionData="allMods" :suggestionSchema="modSchema"
        v-model="filterQuery" v-model:logic="filterLogic" :cacheKey="store.dataVersion || allMods.length"
        @search="" class="z-5">
        <template #icon>
          <svg class="w-3 h-3 text-text-dim" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2.586a1 1 0 01-.293.707l-6.414 6.414a1 1 0 00-.293.707V17l-4 4v-6.586a1 1 0 00-.293-.707L3.293 7.293A1 1 0 013 6.586V4z" /></svg>
        </template>
        <template #right>
          <!-- 排序切换按钮 -->
          <button @click="cycleSort" :title="sortMode"
            :class="`px-3 py-1 rounded-lg bg-accent-${listColor}/50 hover:bg-accent-${listColor} 
            text-text-dim hover:text-text-main text-xs font-bold shadow-lg shadow-accent-${listColor}/10 
            transition-all`">
            {{ sortIcon }}
          </button>
        </template>
      </TagsInput>
    </div>
    
    <!-- 列表区（底部渐变隐藏） -->
    <div class="flex-1 flex pb-0.5 overflow-y-auto after:pointer-events-none 
        after:content-[''] after:absolute after:bottom-0 after:w-full after:h-10 
        after:bg-linear-to-t after:from-bg-deep/80 after:to-transparent"
	      @click.self="store.clearSelection()" >
      
      <!-- 左侧辅助功能区 -->
      <div v-show="hasSidebar" class="size-14 flex-none">

      </div>

      <!-- 列表主体 -->
      <div class="flex-1 h-full pl-1 pr-1 min-w-0 relative" @click.self="store.clearSelection()">

        <div v-show="modelValue.length === 0" class="absolute flex rounded-lg top-0 bottom-0 left-0 right-0 m-1 items-center justify-center border-2 border-dashed text-gray-600 text-xs bg-bg-deep/90 select-none pointer-events-none">
            可拖拽模组到此
            <!-- 点阵背景 -->
            <div class="absolute inset-0 opacity-[0.05] pointer-events-none" style="background-image: radial-gradient(#fff 1px, transparent 1px); background-size: 20px 20px;"></div>
        </div>

        <VirtualList v-model="internalListProxy" ref="vListRef" dataKey="id" :keeps="50" class="h-full p-1" placeholderClass="ghost" wrapClass="space-y-1" 
          :fallbackOnBody="true" :scrollSpeed="{x:0, y:10}" handle=".drag-handle" :sortable="allowSort"
          :group="{ name: 'mods', pull: true, put: allowSort, revertDrag: true }" :animation="150" 
          @mousedown.left="handleMousePressed(true)" @mouseup.left="handleMousePressed(false)" @mouseleave="handleMousePressed(false)">
          <template v-slot:item="{ record, index, dataKey }">
            <ModItem :item_id="dataKey" :index="index" :key="dataKey" :list-color="listColor" 
              :is-selected="store.selectedIds.has(dataKey)"
              :search-match="currentTargetId === dataKey"
               @toggle-select="handleClick" v-preview="store.getModById(dataKey)">
            </ModItem>
          </template>
        </VirtualList>

      </div>

    </div>

  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import VirtualList from 'vue-virtual-sortable';
import { useModStore } from '../stores/modStore'
import ModItem from './utils/ModItem.vue'
import TagsInput from './utils/TagsInput.vue';
import { useToast } from "vue-toastification";

const toast = useToast();

// 这里 modelValue 接收纯 ID 数组
const props = defineProps({
  title: { type: String, default: 'Default' },
  modelValue: { type: Array as () => string[], required: true }, // Array<string>
  hasSidebar: { type: Boolean, default: false },
  listColor: { type: String, default: 'primary' } // danger/highlight/special/cool/primary/success/tip/warm/secondary/warning
})

const emit = defineEmits(['update:modelValue'])
const store = useModStore()

// --- 1. 搜索与筛选逻辑 ---

const vListRef = ref(null)  // 虚拟列表引用, 用于滚动到选中项
const sortMode = ref<'default' | 'name' | 'author'>('default')

// 状态
const searchQuery = ref([])
const searchLogic = ref('AND') // 存储逻辑关系
const filterQuery = ref([]) // 存储标签数组
const filterLogic = ref('AND') // 存储逻辑关系

// 模组搜索字段 schema
const modSchema = {
  'tags': 'list', 
  'name': 'string', 
  'alias_name': 'string',
  'author': 'list', 
  'package_id': 'string',
}
// 默认搜索范围
const defaultSearchScope = ['name', 'alias_name', 'notes', 'description']

// --- 2. 显示列表计算 (Filter -> Sort) ---
// 仅当允许拖拽排序时 (默认模式且无筛选) 为 True
// 注意：如果 filtered，禁止排序，因为无法映射回原数组的正确位置
const isFiltered = computed(() => filterQuery.value.length > 0)
const allowSort = computed(() => sortMode.value === 'default' && !isFiltered.value)
const allMods = computed(() => store.allModsMap ? Array.from(store.allModsMap.values()) : [])
const currentTargetId = computed(() => store.currentTargetId)
const currentTragetIndex = ref(-1)

// 显示列表：筛选 -> 排序
const displayList = computed(() => {
  let list = props.modelValue.slice() // 复制一份 ID 列表
  
  // 1. 筛选
  if (filterQuery.value.length > 0) {
    list = list.filter(id => {
      const mod = store.getModById(id)
      return checkMatch(mod, filterQuery.value, filterLogic.value)
    })
  }

  // 2. 排序 (仅视觉)
  if (sortMode.value !== 'default') {
    list.sort((a, b) => {
      const mA = store.getModById(a)
      const mB = store.getModById(b)
      if (sortMode.value === 'name') return (mA?.name || a).localeCompare(mB?.name || b)
      if (sortMode.value === 'author') return (mA?.author || '').localeCompare(mB?.author || '')
      return 0
    })
  }
  
  return list
})

// 检查模组是否匹配所有 检索Tag
const checkMatch = (mod: any, tags: any[], logic: string) => {
  if (!mod || tags.length === 0) return true

  // 对每个 Tag 进行判断
  const results = tags.map(tag => {
    let isMatch = false
    const isExactMatch = tag.value.endsWith('$')
    const tagValLower = isExactMatch ? tag.value.toLowerCase().slice(0, -1) : tag.value.toLowerCase()
    
    // console.log('tag', tagValLower)
    // console.log(tagValLower.endsWith('$'),'tagValLower', tagValLower.slice(0, -1))

    if (tag.type === 'rule') {
      // 结构化匹配 (如 t:Core)
      // 直接查字段，不再转换 Mod 内容的大小写
      const fieldVal = mod[tag.key]
      // 列表匹配
      if (Array.isArray(fieldVal)) {
          // 如果字段是 tags，利用预处理的 Set (O(1) 复杂度)
          if (tag.key === 'tags' && mod._tagsLower) {
            // 包含匹配（模糊匹配）
            if (isExactMatch) {
              // 精确匹配
              isMatch = fieldVal.some(v => String(v).toLowerCase() === tagValLower)
            } else {
              // 包含匹配（模糊匹配）
              isMatch = fieldVal.some(v => v.toLowerCase().includes(tagValLower))
            }
          } else {
            if (isExactMatch) {
              // 精确匹配
              isMatch = fieldVal.some(v => String(v).toLowerCase() === tagValLower)
            } else {
              // 包含匹配（模糊匹配）
              isMatch = fieldVal.some(v => String(v).toLowerCase().includes(tagValLower))
            }
          }
      // 字符串匹配
      } else if (fieldVal) {
        if (isExactMatch) {
          // 精确匹配
          isMatch = String(fieldVal).toLowerCase() === tagValLower
        } else {
          // 包含匹配（模糊匹配）
          isMatch = String(fieldVal).toLowerCase().includes(tagValLower)
        }
        // console.log('value',tagValLower,'isExactMatch',isExactMatch,'fieldVal',fieldVal)
      }
    } else {
      // 纯文本匹配：直接检查预处理的索引字符串 (极快)
      if (mod._searchStr) {
          isMatch = mod._searchStr.includes(tagValLower)
      } else {
          // 兜底逻辑
           isMatch = defaultSearchScope.some(key => String(mod[key] || '').toLowerCase().includes(tagValLower))
      }
    }

    // 处理排除逻辑
    return tag.exclude ? !isMatch : isMatch
  })

  // 根据逻辑组合结果
  if (logic === 'AND') {
    return results.every(r => r === true)
  } else {
    // OR 逻辑：只要有一个为 True 即可 (注意：排除项通常是强制的，这里简单处理为普通 OR)
    // 更好的 OR 逻辑通常是：(条件A OR 条件B) AND (非条件C)
    // 但为了 UI 简单，这里全量 OR
    return results.some(r => r === true)
  }
}


// VueVirtualSortable 需要对象数组 {id: ...}
// 这里做一个中间层，处理 displayList 和 modelValue 之间的映射
// 注意：当处于 Filter/Sort 模式时，Set 操作需要小心，我们只允许"拖出"，
const internalListProxy = computed({
    get() {
        return displayList.value.map(id => ({ id }))
    },
    set(val: any[]) {
        // 当发生拖拽变化时
        if (!allowSort.value) {
            // 如果处于筛选/排序模式，VirtualList 可能会尝试更新列表
            // 简单处理：如果长度变短了(被拖出)，我们需要在原始 modelValue 中移除对应项
            const newIds = new Set(val.map(v => v.id))
            const removedIds = displayList.value.filter(id => !newIds.has(id))
            
            if (removedIds.length > 0) {
                const newList = props.modelValue.filter(id => !removedIds.includes(id))
                emit('update:modelValue', newList)
                store.markDirty()
            }
            return
        }

        // 正常模式：直接更新
        const newIds = val.map(v => v.id)
        emit('update:modelValue', newIds)
        store.markDirty()
    }
})

// --- 3. 搜索定位逻辑 (Find) ---
const searchResults = ref<string[]>([])

// 监听 currentTargetId 变化
watch(currentTargetId, async (newVal, oldVal) => {
  if (!newVal || newVal === oldVal) return
  // 1. 检查目标是否在当前所有的 modelValue 中（不仅是 displayList）
  if (!props.modelValue.includes(newVal)) {
    // 如果这个 ID 根本不在当前传进来的列表里（比如它在另一个分组，或者被彻底移除了）
    console.info(`Item ${newVal} not found in ${props.title} list model.`)
    // toast.warning(`Item ${newVal} not found in ${props.title} list model.`)
    return
  } 

  // 2. 检查是否被当前的筛选器过滤掉了
  if (!displayList.value.includes(newVal)) {
    console.info(`Item ${newVal} is filtered out by current ${props.title} filter.`)
    toast.warning(`搜索项 ${newVal} 已被 ${props.title} 列表筛选器过滤，请清除筛选后重试。`)
    // 策略 A: 自动清除筛选 (推荐)
    // searchQuery.value = [] // 清空搜索 Tag
    // filterQuery.value = [] // 清空筛选 Tag
    // // 等待 Vue 重新计算 displayList
    // await nextTick()
  }

  // 3. 执行定位
  const index = displayList.value.indexOf(newVal)
  if (index !== -1) {
    // 稍微延迟一下确保虚拟列表渲染就绪
    setTimeout(() => {
        if (vListRef.value) {
            vListRef.value.scrollToKey(newVal)
            // 可选：添加一个高亮闪烁效果
            // store.flashItem(newVal) 
        }
    }, 50)
    // 延迟一段时间后移除高亮
    setTimeout(() => {
      store.currentTargetId = ''
    }, 2000)
  }
})

// 执行搜索
const executeSearch = (next = true) => {
  // 清空旧结果
  if (!searchQuery.value.length) {
    searchResults.value = []
    store.currentTargetId = ''
    currentTragetIndex.value = -1
    return
  }

  // 在当前的 displayList 中查找，这样只能找到可见的
  const results = displayList.value.filter(id => checkMatch(store.getModById(id), searchQuery.value, searchLogic.value))
  
  // 如果结果列表变了，重置
  if (JSON.stringify(results) !== JSON.stringify(searchResults.value)) {
    searchResults.value = results
    currentTragetIndex.value = -1
  }

  if (results.length === 0) return

  var index = currentTragetIndex.value

  if (next) {
    index++
    if (index >= results.length) {
      index = 0 // 循环
      // 可以加个 Toast 提示 "回到第一个"

    }
  }
  // 定位
  const targetId = results[index]
  currentTragetIndex.value = index
  // 先确保目标 ID 在可见范围内
  if (results.includes(targetId)) {
    store.currentTargetId = targetId
  }
  
}

// --- 4. 排序切换 ---
const sortIcon = computed(() => {
    switch(sortMode.value) {
        case 'name': return 'A-Z'
        case 'author': return 'User'
        default: return 'Def'
    }
})
const cycleSort = () => {
    if (sortMode.value === 'default') sortMode.value = 'name'
    else if (sortMode.value === 'name') sortMode.value = 'author'
    else sortMode.value = 'default'
}
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
// --- 选中与样式 ---
const handleClick = (event: MouseEvent, id: string, isPull=false) => {
  // 修正输入框不会对列表项失焦，强制失焦逻辑
  // 如果当前有获得焦点的元素，且它是一个输入框，则强制让它失焦
  if (document.activeElement instanceof HTMLElement && 
     (document.activeElement.tagName === 'INPUT' || document.activeElement.tagName === 'TEXTAREA')) {
      document.activeElement.blur()
  }

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

</script>

<style scoped>

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