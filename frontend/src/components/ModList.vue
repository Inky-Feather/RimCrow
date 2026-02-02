<template>
  <div class="flex flex-col relative h-full bg-bg-surface/40 backdrop-blur-sm shadow-2xl"
       :class="`border-2 rounded-2xl border-accent-${listColor}/20 overflow-hidden`">
    <!-- 标题栏 -->
    <div :class="`px-3 h-8 border-b rounded-t-2xl border-white/5 flex justify-between items-center bg-accent-${listColor}/10`">
      <span :class="`text-sm font-bold text-accent-${listColor} uppercase tracking-wider flex items-center gap-1`">
        <div :class="`w-1.5 h-1.5 mr-1 rounded-full bg-accent-${listColor} shadow-lg shadow-accent-primary`"></div>
        <span class="mr-1">{{ title }}</span>
        <!-- 状态提示 -->
        <span v-if="isFiltered" v-tooltip="filterTooltip" @click="clearFilter"
          class="text-[10px] text-text-main/80 bg-accent-highlight/30 px-1 rounded-full ring-1 ring-accent-special/70 cursor-pointer hover:bg-accent-highlight/60 hover:text-text-main active:scale-95 transition-all">
          已筛选
        </span>
        <span v-if="sortMode !== 'default' || !isSortAsc" v-tooltip="sortTooltip" class="text-[10px] text-text-main/80 bg-accent-highlight/30 px-1 rounded-full">已排序</span>
      </span>

      <span class="flex items-center gap-1">
        <!-- 错误指示器 (仅当有错误时显示) -->
        <button v-if="issuesSummary.count > 0" v-tooltip="issueTooltip"
          @click="toggleIssueFilter"
          class="flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold transition-all border cursor-pointer hover:scale-105 active:scale-95"
          :class="[issuesSummary.errorCount > 0 ? 'bg-accent-danger/20 text-accent-danger border-accent-danger/30' 
              : 'bg-accent-warn/20 text-accent-warn border-accent-warn/30',
            isFilterByIssue ? 'ring-2 ring-accent-special/70' : '']"
        >
          <!-- 图标 -->
          <svg width="16" height="16" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-triangle-alert-icon lucide-triangle-alert">
            <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4"/><path d="M12 17h.01"/>
          </svg>
          
          <!-- 计数 -->
          <span>{{ issuesSummary.count }}</span>
        </button>

        <!-- 列表总数 / 筛选数 -->
        <span v-if="isFiltered" :class="`text-[10px] bg-black/30 px-2 py-0.5 rounded text-accent-${listColor}`">
          {{ displayList.length }} / {{ modelValue.length }}
        </span>
        <span v-else :class="`text-[10px] bg-black/30 px-2 py-0.5 rounded text-accent-${listColor}`">{{ modelValue.length }}</span>
      </span>

    </div>
    
    <!-- 工具栏 (搜索 & 筛选) -->
    <div class="px-2 py-1 w-full flex flex-col gap-1 shadow-xl bg-bg-deep/20 z-50">
      <div class="flex items-center justify-center gap-1 relative">
        <!-- 搜索定位 (Find) -->
        <TagsSearch :list-color="listColor" v-model="searchQuery" v-model:logic="searchLogic" 
          @search="executeSearch(true)" placeholder="输入关键词定位Mod位置……" class="z-10">
          <template #right>
            <!-- 定位按钮 -->
            <button @click="executeSearch(true)" v-tooltip="'搜索定位下一个符合条件的结果'"
              :class="`px-3 py-1 relative rounded-lg bg-accent-${listColor}/50 hover:bg-accent-${listColor} 
              text-text-dim hover:text-text-main text-xs font-bold shadow-lg shadow-accent-${listColor}/10 
              transition-all cursor-pointer hover:scale-105 active:scale-95`">定位
              <div v-if="currentSearchIndex !== -1 && searchQuery.length > 0" class="text-[8px] absolute -top-2 -left-1 text-text-main bg-accent-highlight px-1 rounded-lg">{{ currentSearchIndex + 1 }} / {{ searchResults.length }}</div>
            </button>
          </template>
        </TagsSearch>
        <!-- 搜索帮助按钮 -->
        <label v-tooltip="{content: searchHelpText, html:true}" class="absolute -top-1.5 -right-2.5 size-4 rounded-md text-sm text-center text-text-dim hover:text-text-main cursor-help">?</label>
        
        <!-- 视图切换按钮 -->
        <Motion :class="`p-1 rounded-md bg-accent-${listColor}/20 border border-accent-${listColor}/30 hover:bg-accent-${listColor}/50 text-accent-${listColor} hover:text-text-main text-xs font-bold shadow-lg shadow-accent-${listColor}/10 flex items-center justify-center cursor-pointer `"
          :initial="{ rotateX: 0, opacity: 1 }"
          :animate="{ rotateX: isSimpleView ? 180 : 0 /*切换时旋转180度*/}" 
          :transition="{ type: 'spring', /*弹性过渡动画*/ stiffness: 300, /*动画刚度*/ damping: 20 /*动画阻尼（回弹效果）*/}"
          @click="isSimpleView = !isSimpleView" v-tooltip="'切换列表视图'"
        >
          <svg v-if="!isSimpleView" width="15" height="15" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-layout-list-icon lucide-layout-list"><rect width="7" height="7" x="3" y="3" rx="1"/><rect width="7" height="7" x="3" y="14" rx="1"/><path d="M14 4h7"/><path d="M14 9h7"/><path d="M14 15h7"/><path d="M14 20h7"/></svg>
          <svg v-else width="15" height="15" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-list-icon lucide-list"><path d="M3 5h.01"/><path d="M3 12h.01"/><path d="M3 19h.01"/><path d="M8 5h13"/><path d="M8 12h13"/><path d="M8 19h13"/></svg>
        </Motion>
      </div>
        
      <div class="flex items-center justify-center gap-1">
        <!-- 筛选过滤 (Filter) -->
        <TagsSearch :list-color="listColor" v-model="filterQuery" v-model:logic="filterLogic"
          placeholder="输入关键词筛选Mod……" class="z-5">
          <template #icon>
            <svg class="w-3 h-3 text-text-dim" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2.586a1 1 0 01-.293.707l-6.414 6.414a1 1 0 00-.293.707V17l-4 4v-6.586a1 1 0 00-.293-.707L3.293 7.293A1 1 0 013 6.586V4z" /></svg>
          </template>

          <template #right>
              <!-- 排序切换按钮 -->
              <button @click="cycleSort" v-tooltip="sortMode"
                :class="`px-3 py-1 rounded-lg bg-accent-${listColor}/50 hover:bg-accent-${listColor} 
                text-text-dim hover:text-text-main text-xs font-bold shadow-lg shadow-accent-${listColor}/10 
                transition-all`">
                {{ sortIcon }}
              </button>
          </template>
        </TagsSearch>
        <!-- 排序切换按钮 -->
        <Motion :class="`p-1 rounded-md bg-accent-${listColor}/20 border border-accent-${listColor}/30 hover:bg-accent-${listColor}/50 text-accent-${listColor} hover:text-text-main text-xs font-bold shadow-lg shadow-accent-${listColor}/10 flex items-center justify-center cursor-pointer `"
          :initial="{ rotateX: 0, opacity: 1 }"
          :animate="{ rotateX: isSortAsc ? 0 : 180 /*切换时旋转180度*/}" 
          :transition="{ type: 'spring', /*弹性过渡动画*/ stiffness: 300, /*动画刚度*/ damping: 20 /*动画阻尼（回弹效果）*/}"
          @click="isSortAsc=!isSortAsc" v-tooltip="isSortAsc?'切换为降序排列':'切换为升序排列'"
        >
          <svg v-if="isSortAsc" width="15" height="15" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-arrow-down-narrow-wide-icon lucide-arrow-down-narrow-wide"><path d="m3 16 4 4 4-4"/><path d="M7 20V4"/><path d="M11 4h4"/><path d="M11 8h7"/><path d="M11 12h10"/></svg>
          <span v-else class="rotate-x-180">
            <svg width="15" height="15" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-arrow-up-narrow-wide-icon lucide-arrow-up-narrow-wide"><path d="m3 8 4-4 4 4"/><path d="M7 4v16"/><path d="M11 12h4"/><path d="M11 16h7"/><path d="M11 20h10"/></svg>
          </span>
        </Motion>
      </div>
    </div>
    <!-- (tabindex="0" @keydown.ctrl.a.prevent="selectAll") 非焦点容器需要 tabindex 才能响应键盘事件 -->
    <!-- 列表区（底部渐变隐藏） -->
    <div class="flex-1 flex pb-0.5 overflow-y-auto after:pointer-events-none 
        after:content-[''] after:absolute after:bottom-0 after:w-full after:h-10 
        after:bg-linear-to-t after:from-bg-deep/80 after:to-transparent"
	      @click.self="modStore.clearSelection()">
      
      <!-- 左侧辅助功能区( @wheel.passive 监听滚轮事件) -->
      <div v-if="hasSidebar" class="w-14 h-full flex-none"
        @wheel.passive="vListRef?.scrollToOffset(vListRef.getOffset()+$event.deltaY)">
        <DependencyGraph 
          v-if="allowSort || filterByLine" 
          :listIds="lineData" :isFilter="filterByLine.length>0"
          :itemHeight="isSimpleView ? 34 : 54" 
          :scrollElement="vListRef"
          @lineClick="handleLineClick"
        />
      </div>

      <!-- 列表主体部分 -->
      <div @click.self="modStore.clearSelection()" class="flex-1 h-full pl-1 pr-1 min-w-0 relative">
        <!-- 列表为空时的提示 -->
        <div v-show="modelValue.length === 0" class="absolute flex rounded-lg top-0 bottom-0 left-0 right-0 m-1 items-center justify-center border-2 border-dashed border-text-dim/60 text-gray-600 text-xs bg-bg-deep/90 select-none pointer-events-none">
            可拖拽模组到此
            <!-- 点阵背景 -->
            <div class="absolute inset-0 opacity-[0.05] pointer-events-none" style="background-image: radial-gradient(#fff 1px, transparent 1px); background-size: 20px 20px;"></div>
        </div>
        <!-- 列表 -->
        <virtual-list v-model="internalListProxy" ref="vListRef" :key="listKey" dataKey="id" :keeps="50" class="h-full p-1" placeholderClass="ghost" wrapClass="" 
          :fallbackOnBody="true" :appendToBody="true" :scrollSpeed="{x:0, y:10}" handle=".drag-handle" :sortable="allowSort" :delay="50"
          :group="{ name: 'mods', pull:'clone', put: allowSort ? ['mods','groups']:false, revertDrag: true }" :animation="150" :size="isSimpleView ? 34 : 54"
          @drop="updateChildren" @drag="startDrag"
          v-selectable-list="{ 
             data: displayList, 
             clickClass: 'select-trigger',
             swipeClass: 'swipe-trigger'
          }">
          <template v-slot:item="{ record, index, dataKey }">
            <ModItem :item_id="dataKey" :index="index" :key="dataKey" :list-color="listColor" 
              :is-selected="modStore.selectedIds.includes(dataKey)" :simple="isSimpleView" 
              :is-in-search="searchResults.includes(dataKey) && searchQuery.length > 0"
              :search-match="currentTargetId === dataKey">
            </ModItem>
          </template>
        </virtual-list>

      </div>

    </div>

  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch, onMounted, nextTick } from 'vue';
import VirtualList from 'vue-virtual-sortable';
import { useToast } from "vue-toastification";
import { Motion } from 'motion-v';
import { useModStore } from '../stores/modStore';
import { useSearchStore } from '../stores/searchStore';
import { generateHtmlHelp } from '../modules/search/SearchHelp'
import ModItem from './utils/ModItem.vue';
import TagsSearch from './common/TagsSearch/TagsSearch.vue';
import DependencyGraph from './utils/DependencyGraph.vue'
import { ISSUE_TITLE_MAP } from '@/utils/constants';

// 这里 modelValue 接收纯 ID 数组
const props = defineProps({
  title: { type: String, default: 'Default' },
  listId: { type: String, required: true },
  modelValue: { type: Array as () => string[], required: true }, // Array<string>
  hasSidebar: { type: Boolean, default: false },
  listColor: { type: String, default: 'primary' } // danger/highlight/special/cool/primary/success/tip/warn/secondary/warning
})

const emit = defineEmits(['update:modelValue'])
const modStore = useModStore()
const searchStore = useSearchStore()
const toast = useToast();
const vListRef = ref(null)  // 虚拟列表引用, 用于滚动到选中项
const listKey = ref(0)


// --- 1. 搜索与筛选逻辑 ---
// 状态
const isSimpleView = ref(true) // 是否简单视图
const isSortAsc = ref(true)   // 是否升序排序
const sortMode = ref<'default' | 'name' | 'author'>('default')  // 排序模式

const searchQuery = ref([]) // 存储搜索数组
const searchLogic = ref('AND') // 存储逻辑关系
const searchResults = ref<string[]>([]) // 搜索结果数组
const currentSearchIndex = ref(-1) // 当前搜索项在结果数组中的索引
const currentTargetId = computed(() => modStore.currentTargetId)   // 当前搜索定位项ID
const highlightTimer = ref<number>() // 定位高亮定时器

const filterQuery = ref([]) // 存储标签数组
const filterLogic = ref('AND') // 存储逻辑关系
const filterByLine = ref([])  // 存储筛选线路数组
const isFilterByIssue = ref(false)  // 是否筛选问题项

// 获取 Engine 实例 (computed 确保响应式)
const engine = computed(() => searchStore.engine)

// --- 2. 显示列表计算 (Filter -> Sort) ---
// 仅当允许拖拽排序时 (默认模式且无筛选) 为 True
// 注意：如果 filtered，禁止排序，因为无法映射回原数组的正确位置
const isFiltered = computed(() => filterQuery.value.length > 0 || isFilterByIssue.value || filterByLine.value?.length > 0)
const allowSort = computed(() => sortMode.value === 'default' && !isFiltered.value && isSortAsc.value)
const allMods = computed(() => modStore.allModsMap ? Array.from(modStore.allModsMap.values()) : [])


// ===== 问题项筛选及提示 =====
// 计算当前列表的错误概况
const issuesSummary = computed(() => modStore.getListIssues(props.listId))
// 切换问题项筛选
const toggleIssueFilter = () => {
    isFilterByIssue.value = !isFilterByIssue.value
    // 如果开启筛选，清空搜索框以免冲突，或者叠加逻辑
    if (isFilterByIssue.value) {
        // 可以在这里设置 filterQuery = 'has:issue' 之类的特殊标记
        // 或者直接修改 displayList 的计算逻辑
    }
}
// 清除筛选
const clearFilter = () => {
  filterQuery.value = []
  isFilterByIssue.value = false
  filterByLine.value = []
}

// 动态计算帮助文本
const searchHelpText = computed(() => {
  if (!engine.value) return 'Loading...';
  // 这里可以做一层缓存，避免每次 render 都生成字符串
  return generateHtmlHelp(engine.value);
})
// 构造问题详情 Tooltip
const issueTooltip = computed(() => {
  const summary = issuesSummary.value // Store 返回的对象
  // console.log('问题摘要:', summary)
  if (summary.count === 0) return null
  const errorInfo = summary.errorCount > 0 ? `!!${summary.errorCount} 个错误!!` : ''
  const warningInfo = summary.warnCount > 0 ? `^^${summary.warnCount} 个警告^^` : ''
  let text = `**发现 ${summary.count} 个问题**（${errorInfo} ${warningInfo}）`

  // 遍历 stats 对象生成详情
  // 格式: 
  // !!缺失前置(10):!!
  // ModA | ModB | ... | __及其他 7 项__
  
  for (const [type, ids] of Object.entries(summary.stats)) {
    if (ids.length === 0) continue
    
    const typeName = ISSUE_TITLE_MAP[type] || type
    const isError = ['missing_dependency', 'inactive_dependency', 'missing_file', 'incompatible','wrong_order'].includes(type)
    
    // 标题颜色: Error 用红(!!), Warn 用黄(^^)
    const titleMark = isError ? '!!' : '^^'
    text += `\n${titleMark}${typeName} (${ids.length}):${titleMark}`
    
    // 列出前 3 个
    const previewIds = ids.slice(0, 3)
    previewIds.forEach(id => {
      text += `\n  • ${modStore.displayModName(id)}`
    })
    
    // 剩余数量提示
    if (ids.length > 3) {
      text += `\n  __...及其他 ${ids.length - 3} 项__`
    }
  }
  
  text += isFilterByIssue.value ? '\n\n__[[(再次点击取消筛选)]]__' : '\n\n__[[(点击筛选以查看详情)]]__'
  return text
})
// 排序提示
const sortTooltip = computed(() => {
  let text = ''
  if (sortMode.value === 'default') {
    text = '默认排序'
  } else if (sortMode.value === 'name') {
    text = '按名称排序'
  } else if (sortMode.value === 'author') {
    text = '按作者排序'
  }
  text += `${isSortAsc.value ? '（升序）' : '（降序）'}`
  return text
})
// 筛选提示
const filterTooltip = computed(() => {
  let text = ''
  if (filterQuery.value.length > 0) {
    text += `已筛选检索关键词`
  }
  if (isFilterByIssue.value) {
    text += '\n已筛选问题项'
  }
  if (filterByLine.value.length > 0) {
    text += `\n已筛选依赖组`
  }
  text = text.trim()
  text += `\n\n__[[(点击清除所有筛选)]]__`
  return text
})

// 处理点击依赖图线路（筛选依赖组）
const handleLineClick = (lines) => {
  // 重复点击清空
  if (filterByLine.value.length > 0) {
    filterByLine.value = []
    return
  }
  filterByLine.value = lines
}
// 依赖线路数据
const lineData = computed(() => {
  return displayList.value
  return filterByLine.value.length === 0 ? props.modelValue : filterByLine.value
})

// ===== 显示数据计算 =====
// 显示列表：筛选 -> 排序
const displayList = computed(() => {
  let list = props.modelValue.slice() // 复制一份 ID 列表
  // 1. 优先处理错误筛选
  if (isFilterByIssue.value) {
      list = list.filter(id => {
          const issues = modStore.modIssues.get(id.toLowerCase())
          return issues && issues.length > 0
      })
  }
  // 2. 处理依赖图筛选
  if (filterByLine.value.length > 0) {
    list = list.filter(id => {
      return filterByLine.value.includes(id)
    })
  }
  // 3. 标签筛选
  if (filterQuery.value.length > 0 && engine.value) {
    // A. 全局搜索符合条件的对象
    // engine.search 返回的是 Mod 对象数组
    const matchedObjects = engine.value.search(filterQuery.value, filterLogic.value)
    // B. 提取 ID 并建立 Set 供快速查找
    const matchedSet = new Set(matchedObjects.map(m => m.package_id))
    // C. 取交集 (当前列表 AND 搜索结果)
    list = list.filter(id => matchedSet.has(id))
  }

  // 4. 排序 (仅视觉)
  if (sortMode.value !== 'default') {
    list.sort((a, b) => {
      const mA = modStore.takeModById(a)
      const mB = modStore.takeModById(b)
      if (sortMode.value === 'name') return (mA?.name || a).localeCompare(mB?.name || b)
      if (sortMode.value === 'author') return (mA?.author || '').localeCompare(mB?.author || '')
      return 0
    })
  }
  // 如果需要逆序，反转数组
  if (!isSortAsc.value) list.reverse()
  
  return list
})
// VueVirtualSortable 需要对象数组 {id: ...}
// 这里做一个中间层，处理 displayList 和 modelValue 之间的映射
const internalListProxy = computed({
    get() {
      return displayList.value.map(id => ({ id }))
    },
    set(val) {
    }
})

// ===== 排序模式切换 =====
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

// ===== 显示效果处理 =====
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
        }
    }, 50)
    // 延迟一段时间后移除高亮
    if (highlightTimer.value) {
      clearTimeout(highlightTimer.value)
    }
    highlightTimer.value = setTimeout(() => {
      modStore.currentTargetId = ''
    }, 2000)
  }
})
// 执行搜索
const executeSearch = (next = true) => {
  // 清空旧结果
  if (!searchQuery.value.length) {
    searchResults.value = []
    modStore.currentTargetId = ''
    currentSearchIndex.value = -1
    return
  }
  // 检查 Engine 是否存在
  if (!engine.value) return

   // 1. 全局搜索
  const matchedObjects = engine.value.search(searchQuery.value, searchLogic.value)
  const matchedSet = new Set(matchedObjects.map(m => m.package_id))

  // 2. 过滤结果：只定位 *当前可见列表(displayList)* 中的项
  const results = displayList.value.filter(id => matchedSet.has(id))
  
  if (JSON.stringify(results) !== JSON.stringify(searchResults.value)) {
    searchResults.value = results
    currentSearchIndex.value = -1
  }


  if (results.length === 0) return

  var index = currentSearchIndex.value

  if (next) {
    index++
    if (index >= results.length) {
      index = 0 // 循环
      toast.info("已到达最后一个搜索结果，循环回到第一个", { timeout: 2000 })
    }
  }
  // 定位
  const targetId = results[index]
  currentSearchIndex.value = index
  // 先确保目标 ID 在可见范围内
  if (results.includes(targetId)) {
    modStore.currentTargetId = targetId
  }
  
}

// 开始拖拽时，清空反选集合
const startDrag = (e) => {
  console.log("开始拖拽:", e)
}
// 更新子项的排序
const updateChildren = async (e) => {
  // 排序状态下禁止拖拽
  if (!allowSort.value) {
    // toast.warning("排序状态下禁止拖拽排序")
    return
  }
  // console.log("更新子项排序:", e)
  const oldIds = [...props.modelValue] // 原始数据（即 source of truth）
  // 这里的 newIds (脏数据) 仅用于计算相对位置，不参与数据重组
  const dirtyIds = internalListProxy.value.map(item => item.id) 
  
  // 1. 获取当前所有需要移动的 ID (处理分组或多选)
  let movingIds = []
  if (e.item?.mod_ids?.length) {
    // 拖动的是分组 -> 移动分组内的所有 Mod
    movingIds = [...e.item.mod_ids]
    // 顺便更新一下 Store 的选中状态，保持一致性
    modStore.selectMods([...movingIds], e.item?.key || null)
  } else {
    // 拖动的是列表项 -> 移动当前选中项
    movingIds = [...modStore.selectedIds]
    const draggedId = dirtyIds[e.newIndex] // 注意：这里用脏数据的索引获取当前拖拽的元素ID
    
    // 如果拖拽的项不在选中列表中（比如未选中时直接拖），则把它加入
    if (!movingIds.includes(draggedId) && draggedId) {
      movingIds.push(draggedId)
    }
  }

  // 2. 核心算法：计算“纯净插入点”
  // 我们需要知道在 e.newIndex 这个位置之前，有多少个“非移动项”
  // 这样我们就可以在剔除移动项后的 baseList 中找到正确的插入位置
  let validItemsAbove = 0
  for (let i = 0; i < e.newIndex; i++) {
    const idAtLoc = dirtyIds[i]
    if (!movingIds.includes(idAtLoc)) {
      validItemsAbove++
    }
  }
  
  // 如果是向下拖拽，Sortable 的 newIndex 包含了拖拽项本身的位置
  // 3. 构建新列表
  // 3.1 生成 BaseList：从原始列表中剔除所有移动项
  const baseList = oldIds.filter(id => !movingIds.includes(id))

  let correctedIndex = validItemsAbove
  // 只有当插入点不在头部也不在尾部时才需要检查
  if (correctedIndex > 0 && correctedIndex < baseList.length) {
    const prevId = baseList[correctedIndex - 1]
    // 检查前一个元素是否有向后的联锁
    let curr = prevId
    while (true) {
      const mod = modStore.takeModById(curr)
      if (!mod || !mod.lock_next_mod) break
      const nextId = mod.lock_next_mod.toLowerCase()
      // 关键判断：
      // 如果 lock_next 指向的 Mod 就在 baseList 中，
      // 说明链条在 baseList 中是连续存在的。
      // 我们必须跳过它，不能插在它前面。
      if (baseList.includes(nextId)) {
        // 找到 nextId 在 baseList 中的位置
        const nextIndexInBase = baseList.indexOf(nextId)
        // 如果 nextId 就在当前插入点或其后方，说明我们插在了链条中间
        // 将插入点顺延到 nextId 的后面
        if (nextIndexInBase >= correctedIndex) {
          correctedIndex = nextIndexInBase + 1
          curr = nextId // 继续检查 nextId 是否还有 next
        } else {
          // nextId 在更前面？说明链条已经乱序了，或者逻辑没问题，停止修正
          break
        }
      } else {
        // lock_next 指向的元素不在 baseList 中（可能在 movingIds 里，或者被删了）
        // 这种情况下，链条已经断了，插入在这里是安全的
        break
      }
    }
  }
  validItemsAbove = correctedIndex

  // 3.2 插入：在计算出的纯净位置插入移动项
  const finalList = [...baseList]
  finalList.splice(validItemsAbove, 0, ...movingIds)

  // 4. 检查是否有变化
  if (JSON.stringify(finalList) !== JSON.stringify(oldIds)) {
    // 同步 Store（移除旧位置的引用等，虽然这里逻辑上已经是新的了）
    modStore.removeIdsOnAllList(movingIds)
    // 发出更新
    emit('update:modelValue', finalList)
    // 更新移动时间
    modStore.takeModListByIds(movingIds).forEach(mod => {
      mod.last_moved_time = Date.now()
      if(e.event.target !== e.event.from) {
        mod.last_active_time = Date.now()
      }
    })
    // 强制重绘（连选拖拽第一项向下2倍选中范围内会导致排序异常，需要重绘）
    await nextTick()
    // 但直接通过key更新会导致列表重新渲染，导致滚动位置丢失，使用原版滚动定位不准
    // const offset = vListRef.value?.getOffset()
    // listKey.value++ // 触发列表重新渲染
    // nextTick(() => {
    //   vListRef.value?.scrollToOffset(offset)
    // })
  }
  // 通过翻转排序两次，实现软重绘
  isSortAsc.value=!isSortAsc.value
  await nextTick()
  isSortAsc.value=!isSortAsc.value
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