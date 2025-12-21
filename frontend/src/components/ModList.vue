<template>
  <div class="flex flex-col relative h-full bg-bg-surface/40 backdrop-blur-sm shadow-2xl"
       :class="`border-2 rounded-2xl border-accent-${listColor}/20 overflow-hidden`">
    <!-- 标题栏 -->
    <div :class="`px-3 py-2 border-b rounded-t-2xl border-white/5 flex justify-between items-center bg-accent-${listColor}/10`">
        <span :class="`text-xs font-bold text-accent-${listColor} uppercase tracking-wider flex items-center gap-2`">
            <div :class="`w-1.5 h-1.5 rounded-full bg-accent-${listColor} shadow-lg shadow-accent-primary`"></div>
            {{ title }}
            <!-- 状态提示 -->
            <span v-if="filterQuery" class="text-[10px] text-text-dim">(已筛选)</span>
            <span v-if="sortMode !== 'default'" class="text-[10px] text-text-dim">(已排序)</span>
        </span>
        <span v-if="filterQuery" :class="`text-[10px] bg-black/30 px-2 py-0.5 rounded text-accent-${listColor}`">
          {{ displayList.length }} / {{ modelValue.length }}
        </span>
        <span v-else :class="`text-[10px] bg-black/30 px-2 py-0.5 rounded text-accent-${listColor}`">{{ modelValue.length }}</span>
    </div>
    
    <!-- 工具栏 (搜索 & 筛选) -->
    <div class="px-2 py-1 w-full flex flex-col gap-1 shadow-xl bg-bg-deep/20 z-10">
      <!-- 搜索定位 (Find) -->
      <div class="flex w-full items-center gap-1">
        <div class="relative flex-1">
             <input type="text" v-model="searchQuery" @keyup.enter="executeSearch(true)"
              placeholder="查找: Name, packageId, n:Name, t:Tag..." 
              :class="`w-full px-2 py-1 pl-6 rounded-lg bg-bg-deep/30 border border-white/10 text-xs text-white 
              focus:border-accent-${listColor} focus:outline-none focus:bg-bg-deep/90 transition-all`" />
             <!-- 图标 -->
             <svg class="w-3 h-3 absolute left-1.5 top-1.5 text-white/30" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" /></svg>
        </div>
        <button @click="executeSearch(true)" 
	        :class="`ml-2 px-3 py-1 rounded-lg bg-accent-${listColor}/50 hover:bg-accent-${listColor} 
          text-text-dim hover:text-text-main text-xs font-bold shadow-lg shadow-accent-${listColor}/10 
          transition-all`">
          定位
        </button>
      </div>
      <!-- 筛选过滤 (Filter) -->
      <div class="flex w-full items-center gap-1">
        <div class="relative flex-1">
             <!-- <input type="text" v-model="filterQuery" 
              placeholder="筛选: Name, packageId, n:Name, t:Tag..." 
              :class="`w-full px-2 py-1 pl-6 rounded-lg bg-bg-deep/30 border border-white/10 text-xs text-white 
              focus:border-accent-${listColor} focus:outline-none focus:bg-bg-deep/90 transition-all`" /> -->
              
              <!-- <TagsInput 
                  v-model="filterTags" 
                  placeholder="筛选: t:Tag, n:Name..." 
              /> -->

              <TagsSearch
                :data="store.allModsMap ? Array.from(store.allModsMap.values()) : []"
                :schema="{ 
                  'tags': 'list', 
                  'name': 'string', 
                  'author': 'list', 
                  'package_id': 'string' 
                }"
                :default-scope="['name', 'package_id', 'author']"
                v-model="searchTags"
                v-model:logic="searchLogic"
                @search="executeSearch(true)"
              />
              
             <svg class="w-3 h-3 absolute left-1.5 top-1.5 text-white/30" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2.586a1 1 0 01-.293.707l-6.414 6.414a1 1 0 00-.293.707V17l-4 4v-6.586a1 1 0 00-.293-.707L3.293 7.293A1 1 0 013 6.586V4z" /></svg>
        </div>
        <!-- 排序切换按钮 -->
        <button @click="cycleSort" :title="sortMode"
	        :class="`ml-2 px-3 py-1 rounded-lg bg-accent-${listColor}/50 hover:bg-accent-${listColor} 
          text-text-dim hover:text-text-main text-xs font-bold shadow-lg shadow-accent-${listColor}/10 
          transition-all`">
	        {{ sortIcon }}
	      </button>
      </div>
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
          :fallbackOnBody="true" :scrollSpeed="{x:0, y:10}" handle=".drag-handle" :sortable="(sortMode == 'default' && !isFiltered)"
          :group="{ name: 'mods', pull: true, put: true, revertDrag: true }" :animation="150" :sort="allowSort" 
          @mousedown.left="handleMousePressed(true)" @mouseup.left="handleMousePressed(false)" @mouseleave="handleMousePressed(false)">
          <template v-slot:item="{ record, index, dataKey }">
            <ModItem :id="dataKey" :index="index" :key="dataKey" :list-color="listColor" 
              :is-selected="store.selectedIds.has(dataKey)"
              :search-match="currentSearchIndex !== -1 && searchResults[currentSearchIndex] === dataKey"
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
import TagsInput from './utils/TagsInput.vue'
import TagsSearch from './utils/TagsSearch.vue';


// 这里 modelValue 接收纯 ID 数组
const props = defineProps({
  title: { type: String, default: 'Default' },
  modelValue: { type: Array as () => string[], required: true }, // Array<string>
  hasSidebar: { type: Boolean, default: false },
  listColor: { type: String, default: 'primary' } // danger/highlight/special/cool/primary/success/tip/warm/secondary/warning
})

const emit = defineEmits(['update:modelValue'])
const store = useModStore()
const vListRef = ref(null)

// --- 1. 搜索与筛选逻辑 ---

const searchQuery = ref('')
const filterQuery = ref('')
const filterTags = ref([])
const sortMode = ref<'default' | 'name' | 'author'>('default')

// 状态
const searchTags = ref([]) // 存储标签数组
const searchLogic = ref('AND') // 存储逻辑关系

// --- 新的匹配逻辑 ---
const checkMatch = (mod: any, tags: any[], logic: string) => {
  if (!mod || tags.length === 0) return true

  // 对每个 Tag 进行判断
  const results = tags.map(tag => {
    let isMatch = false
    
    if (tag.type === 'rule') {
      // 结构化匹配 (如 t:Core)
      const fieldVal = mod[tag.key]
      if (Array.isArray(fieldVal)) {
        // 数组字段 (Tags, Author): 模糊匹配任一元素
        isMatch = fieldVal.some(v => v.toLowerCase().includes(tag.value.toLowerCase()))
      } else if (fieldVal) {
        // 字符串字段 (Name): 包含
        isMatch = String(fieldVal).toLowerCase().includes(tag.value.toLowerCase())
      }
    } else {
      // 纯文本匹配 (遍历 defaultScope)
      const scope = ['name', 'package_id', 'author'] // 或从 props 传
      isMatch = scope.some(key => {
        const val = mod[key]
        if (Array.isArray(val)) return val.some(v => v.toLowerCase().includes(tag.value.toLowerCase()))
        return String(val || '').toLowerCase().includes(tag.value.toLowerCase())
      })
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

// 解析查询字符串: "t:Core n:Rim" -> { tags: ['Core'], names: ['Rim'], groups: [] }
const parseQuery = (query: string) => {
    const parts = query.toLowerCase().split(/\s+/)
    const criteria = { tags: [], names: [], groups: [], authors: [] }
    parts.forEach(p => {
      if(!p) return
      if(p.startsWith('t:')) criteria.tags.push(p.slice(2))
      else if(p.startsWith('g:')) criteria.groups.push(p.slice(2))
      else if(p.startsWith('n:')) criteria.names.push(p.slice(2))
      else if(p.startsWith('a:')) criteria.authors.push(p.slice(2))
      else criteria.names.push(p) // 默认当作名称
    })
    return criteria
}

// --- 2. 显示列表计算 (Filter -> Sort) ---

// 仅当允许拖拽排序时 (默认模式且无筛选) 为 True
// 注意：如果 filtered，我们通常禁止排序，因为无法映射回原数组的正确位置
const isFiltered = computed(() => !!filterQuery.value.trim())
const allowSort = computed(() => sortMode.value === 'default' && !isFiltered.value)

const displayList = computed(() => {
    let list = props.modelValue.slice() // 复制一份 ID 列表
    
    // 1. 筛选
    // 使用新的 searchTags 判断
    if (searchTags.value.length > 0) {
        list = list.filter(id => {
            const mod = store.getModById(id)
            return checkMatch(mod, searchTags.value, searchLogic.value)
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

// VueVirtualSortable 需要对象数组 {id: ...}
// 这里做一个中间层，处理 displayList 和 modelValue 之间的映射
// 注意：当处于 Filter/Sort 模式时，Set 操作需要小心，我们只允许"拖出"，
// "拖入" 或 "重排" 在 Filter 模式下通常会很奇怪，建议此时禁用 put 或 sort。
const internalListProxy = computed({
    get() {
        return displayList.value.map(id => ({ id }))
    },
    set(val: any[]) {
        // 当发生拖拽变化时
        if (!allowSort.value) {
            // 如果处于筛选/排序模式，VirtualList 可能会尝试更新列表
            // 但我们要拒绝这种更新，或者只处理"移除"的情况
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
const currentSearchIndex = ref(-1)

const executeSearch = (next = true) => {
    if (!searchQuery.value.trim()) {
        searchResults.value = []
        currentSearchIndex.value = -1
        return
    }

    const criteria = parseQuery(searchQuery.value)
    // 在当前的 displayList 中查找，这样只能找到可见的
    const results = displayList.value.filter(id => checkMatch(store.getModById(id), criteria))
    
    // 如果结果列表变了，重置
    if (JSON.stringify(results) !== JSON.stringify(searchResults.value)) {
        searchResults.value = results
        currentSearchIndex.value = -1
    }

    if (results.length === 0) return

    if (next) {
        currentSearchIndex.value++
        if (currentSearchIndex.value >= results.length) {
            currentSearchIndex.value = 0 // 循环
            // 可以加个 Toast 提示 "回到第一个"
        }
    }
    
    // 定位
    const targetId = results[currentSearchIndex.value]
    if (vListRef.value) {
        vListRef.value.scrollToKey(targetId)
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