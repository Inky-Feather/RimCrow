<template>
  <div class="flex flex-col relative h-full bg-bg-surface/40 backdrop-blur-sm shadow-2xl"
       :class="`border-2 rounded-2xl border-accent-${listColor}/20 overflow-hidden`">
    <!-- 标题栏 -->
    <div :data-tour="listId=='active'?'list-header':null" :class="`px-3 h-8 border-b rounded-t-2xl border-text-main/5 flex justify-between items-center bg-accent-${listColor}/10`">
      <span :class="`text-sm font-bold text-accent-${listColor} uppercase tracking-wider flex items-center gap-1`">
        <div :class="`w-1.5 h-1.5 mr-1 rounded-full bg-accent-${listColor} shadow-lg shadow-accent-primary`"></div>
        <span class="mr-1">{{ title }}</span>
        <!-- 状态提示 -->
        <span v-if="isFiltered" v-tooltip="filterTooltip" @click="clearFilter"
          class="text-xs text-text-main/80 bg-accent-highlight/30 px-1 rounded-full ring-1 ring-accent-special/70 cursor-pointer hover:bg-accent-highlight/60 hover:text-text-main active:scale-95 transition-all">
          已筛选
        </span>
        <span v-if="sortMode !== 'default' || !isSortAsc" v-tooltip="sortTooltip" class="text-xs text-text-main/80 bg-accent-highlight/30 px-1 rounded-full">
          已排序
        </span>
      </span>

      <span class="flex items-center gap-1">
        <!-- 错误指示器 (仅当有错误时显示) -->
        <button v-if="issuesSummary.count > 0" v-tooltip="issueTooltip"
          @click="toggleIssueFilter" @contextmenu="issueContextMenu"
          class="flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-bold transition-all border cursor-pointer hover:scale-105 active:scale-95"
          :class="[issuesSummary.errorCount > 0 ? 'bg-accent-danger/20 text-accent-danger border-accent-danger/30' 
              : 'bg-accent-warn/20 text-accent-warn border-accent-warn/30',
            isFilterByIssue ? 'ring-2 ring-accent-special/70' : '']"
        >
          <!-- 图标 -->
          <svg class="size-4" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" >
            <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4"/><path d="M12 17h.01"/>
          </svg>
          <!-- 计数 -->
          <span>{{ issuesSummary.count }}</span>
        </button>

        <!-- 列表总数 / 筛选数 -->
        <span v-if="isFiltered" :class="`text-xs bg-black/30 px-2 py-0.5 rounded text-accent-${listColor}`">
          {{ displayList.length }} / {{ modelValue.length }}
        </span>
        <span v-else :class="`text-xs bg-black/30 px-2 py-0.5 rounded text-accent-${listColor}`">{{ modelValue.length }}</span>
      </span>

    </div>
    
    <!-- 工具栏 (搜索 & 筛选) -->
    <div :data-tour="listId=='active'?'list-toolbar':null" class="px-2 py-1 w-full flex flex-col gap-1 shadow-xl bg-bg-deep/20 z-50">
      <div class="flex items-center justify-center gap-1 relative">
        <!-- 搜索定位 (Find) -->
        <TagsSearch :list-color="listColor" v-model="searchQuery" v-model:logic="searchLogic" ref="searchTagsRef"
          @search="executeSearch(true)" placeholder="输入关键词定位Mod位置……" class="z-10">
          <template #right>
            <!-- 定位按钮 -->
            <button @click="searchTagsRef?.addTag();executeSearch(true)" v-tooltip="'搜索定位下一个符合条件的结果'"
              :class="`px-3 py-1 relative rounded-lg bg-accent-${listColor}/50 hover:bg-accent-${listColor} 
              text-text-dim hover:text-text-main text-xs font-bold shadow-lg shadow-accent-${listColor}/10 
              transition-all cursor-pointer hover:scale-105 active:scale-95`">定位
              <div v-if="currentSearchIndex !== -1 && searchQuery.length > 0" class="text-[0.55rem] absolute -top-2 -left-1 text-text-main bg-accent-highlight px-1 rounded-lg">{{ currentSearchIndex + 1 }} / {{ searchResults.length }}</div>
            </button>
          </template>
        </TagsSearch>
        <!-- 搜索帮助按钮 -->
        <label v-tooltip="{content: searchHelpText, html:true}" class="absolute -top-1.5 -right-2.5 size-4 rounded-md text-sm text-center text-text-dim hover:text-text-main cursor-help">?</label>
        
        <!-- 视图切换按钮 -->
        <Motion :class="`p-1 size-7 rounded-md bg-accent-${listColor}/20 border border-accent-${listColor}/30 hover:bg-accent-${listColor}/50 text-accent-${listColor} hover:text-text-main text-xs font-bold shadow-lg shadow-accent-${listColor}/10 flex items-center justify-center cursor-pointer `"
          :initial="{ rotateX: 0, opacity: 1 }"
          :animate="{ rotateX: isSimpleView ? 180 : 0 /*切换时旋转180度*/}" 
          :transition="{ type: 'spring', /*弹性过渡动画*/ stiffness: 300, /*动画刚度*/ damping: 20 /*动画阻尼（回弹效果）*/}"
          @click="isSimpleView = !isSimpleView" v-tooltip="'切换列表视图'"
        >
          <svg v-if="!isSimpleView" class="size-4" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" ><rect width="7" height="7" x="3" y="3" rx="1"/><rect width="7" height="7" x="3" y="14" rx="1"/><path d="M14 4h7"/><path d="M14 9h7"/><path d="M14 15h7"/><path d="M14 20h7"/></svg>
          <svg v-else class="size-4" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" ><path d="M3 5h.01"/><path d="M3 12h.01"/><path d="M3 19h.01"/><path d="M8 5h13"/><path d="M8 12h13"/><path d="M8 19h13"/></svg>
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
              <button @click="isSortChange = !isSortChange" @blur="isSortChange = false" v-tooltip="sortTooltip"
                :class="`px-3 py-1 rounded-lg bg-accent-${listColor}/50 hover:bg-accent-${listColor} 
                text-text-dim hover:text-text-main text-xs font-bold shadow-lg shadow-accent-${listColor}/10 
                transition-all relative`">
                {{ sortIcon }}
                <div v-show="isSortChange" class="absolute min-w-20 h-auto p-0.5 top-full mt-1 right-1/2 left-1/2 transform -translate-x-1/2 size-4 rounded-md bg-bg-highlight/80 border border-text-main/10 shadow-2xl backdrop-blur-sm text-xs text-center text-text-dim flex flex-col gap-0.5">
                  <div v-for="(icon, mode) in SORT_MODE_MAP" :key="mode" @click="sortMode = mode" class="w-full rounded-md hover:bg-text-dim/30 hover:text-text-main">{{ icon }}</div>
                </div>
              </button>
          </template>
        </TagsSearch>
        <!-- 排序切换按钮 -->
        <Motion :class="`p-1 size-7 rounded-md bg-accent-${listColor}/20 border border-accent-${listColor}/30 hover:bg-accent-${listColor}/50 text-accent-${listColor} hover:text-text-main text-xs font-bold shadow-lg shadow-accent-${listColor}/10 flex items-center justify-center cursor-pointer `"
          :initial="{ rotateX: 0, opacity: 1 }"
          :animate="{ rotateX: isSortAsc ? 0 : 180 /*切换时旋转180度*/}" 
          :transition="{ type: 'spring', /*弹性过渡动画*/ stiffness: 300, /*动画刚度*/ damping: 20 /*动画阻尼（回弹效果）*/}"
          @click="isSortAsc=!isSortAsc" v-tooltip="isSortAsc?'切换为降序排列':'切换为升序排列'"
        >
          <svg v-if="isSortAsc" class="size-4" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" ><path d="m3 16 4 4 4-4"/><path d="M7 20V4"/><path d="M11 4h4"/><path d="M11 8h7"/><path d="M11 12h10"/></svg>
          <span v-else class="rotate-x-180">
            <svg class="size-4" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" ><path d="m3 8 4-4 4 4"/><path d="M7 4v16"/><path d="M11 12h4"/><path d="M11 16h7"/><path d="M11 20h10"/></svg>
          </span>
        </Motion>
      </div>
    </div>
    
    <!-- 如果正在加载中，不渲染虚拟列表，防止 DOM 引擎崩溃 -->
    <div v-if="appStore.isLoading" class="w-full h-full flex items-center justify-center bg-bg-deep/50 z-50">
        <div class="animate-spin size-8 border-4 border-accent-primary border-t-transparent rounded-full"></div>
    </div>
    <!-- (tabindex="0" @keydown.ctrl.a.prevent="selectAll") 非焦点容器需要 tabindex 才能响应键盘事件 -->
    <!-- 列表区（底部渐变隐藏） -->
    <div v-else ref="listContainerRef" class="flex-1 flex pb-0.5 overflow-y-auto after:pointer-events-none 
        after:content-[''] after:absolute after:bottom-0 after:w-full after:h-10 
        after:bg-linear-to-t after:from-bg-deep/80 after:to-transparent focus:outline-none"
	      @click.self="modStore.clearSelection()">
      
      <!-- 左侧辅助功能区( @wheel.passive 监听滚轮事件) -->
      <div v-if="hasSidebar && appStore.settings.ui.show_dependency_graph" :data-tour="listId=='active'?'list-dependency':null" class="w-[55px] h-full flex-none"
        @wheel.passive="vListRef?.scrollToOffset(vListRef.getOffset()+$event.deltaY)">
        <DependencyGraph v-if="allowSort || filterByLine" 
          :listIds="lineData" :isFilter="filterByLine.length>0"
          :itemHeight="itemHeight" 
          :scrollElement="vListRef"
          @lineClick="handleLineClick"
        />
      </div>
      <!-- 列表主体部分 -->
      <div @click.self="modStore.clearSelection()" class="flex-1 h-full pl-1 pr-1 min-w-0 relative" :data-tour="listId=='active'?'list-modItem':null">
        <!-- 列表为空时的提示 -->
        <div v-show="modelValue.length === 0" class="absolute flex rounded-lg top-0 bottom-0 left-0 right-0 m-1 items-center justify-center border-2 border-dashed border-text-dim/60 text-gray-600 text-xs bg-bg-deep/90 select-none pointer-events-none">
            可拖拽模组到此
            <!-- 点阵背景 -->
            <div class="absolute inset-0 opacity-[0.05] pointer-events-none" style="background-image: radial-gradient(#fff 1px, transparent 1px); background-size: 20px 20px;"></div>
        </div>
        <!-- 列表 -->
          <!-- :size="isSimpleView ? 34 : 54" -->
        <VirtualList v-model="internalListProxy" ref="vListRef" :key="listKey" dataKey="id" :keeps="50" class="h-full p-1 pb-10" placeholderClass="ghost" wrapClass="" 
          :fallbackOnBody="true" :appendToBody="true" :scrollSpeed="{x:0, y:10}" handle=".drag-handle" :sortable="allowSort" :delay="appStore.settings.ui.drag_delay"
          :group="{ name: 'mods', pull:'clone', put: allowSort ? ['mods','groups']:false, revertDrag: true }" :animation="150" 
          :size="itemHeight"
          @drop="updateChildren" @drag="startDrag"
          @click="focusContainer"
          v-selectable-list="{ 
            data: displayList, 
            selectedIds: modStore.selectedIds, 
            onSelect: (ids, anchor) => modStore.selectMods(ids, anchor),
            onClear: () => modStore.clearSelection(),
            enableKeyboardNav: true,
            onNavigate: handleDirectiveNavigate,
            clickClass: 'select-trigger',
            swipeClass: 'swipe-trigger',
            idAttribute: 'data-id'
          }">
          <template v-slot:item="{ record, index, dataKey }">
            <ModItem :item_id="dataKey" :index="index" :key="dataKey" :list-color="listColor" 
              :is-selected="modStore.selectedIds.includes(dataKey)" :simple="isSimpleView"
              :is-in-search="searchResults.includes(dataKey) && searchQuery.length > 0" 
              :show-icon="appStore.settings.ui.show_list_icon" 
              :show-mod-icon="appStore.settings.ui.show_list_mod_icon" 
              :show-type-icon="appStore.settings.ui.show_list_modtype_icon"
              :show-index="appStore.settings.ui.show_list_index"
              :search-match="currentTargetId === dataKey">
            </ModItem>
          </template>
        </VirtualList>

        <div class="absolute bottom-2 right-2 flex items-center justify-end gap-2">
          <!-- 一键订阅缺失的模组 -->
          <div v-if="missingModIds.length > 0" @click.stop="appStore.subscribePackageIds(missingModIds)" 
            v-tooltip="`[[一键订阅共计 ${missingModIds.length} 个缺失的模组]]\n^^注意：部分创意工坊已经下架的模组将自动忽略！^^`"
            class="px-1 py-1 group relative bg-accent-danger/80 text-text-main/50 rounded-md hover:bg-accent-danger hover:text-text-main transition-all" >
            <Flag />

            <button @click.stop="appStore.downloadPackageIds(missingModIds)" 
              v-tooltip="`##一键下载共计 ${missingModIds.length} 个缺失的模组##\n^^注意：部分创意工坊已经下架的模组将自动忽略！^^`"
              class="px-1 py-1 right-1/2 translate-x-1/2 absolute bottom-full mb-2 opacity-0 group-hover:pointer-events-auto group-hover:opacity-100 bg-accent-danger/80 text-text-main/50 rounded-md hover:bg-accent-danger hover:text-text-main transition-all duration-200" >
              <Download />
            </button>
          </div>
          <!-- 一键订阅缺失的依赖项 -->
          <div v-if="missingDependencies.length > 0" @click.stop="appStore.subscribePackageIds(missingDependencies)" 
            v-tooltip="`[[一键订阅共计 ${missingDependencies.length} 个缺失的依赖项]]\n^^注意：部分创意工坊已经下架的模组将自动忽略！^^`"
            class="px-1 py-1 group relative bg-accent-danger/80 text-text-main/50 rounded-md hover:bg-accent-danger hover:text-text-main transition-all" >
            <Flag />

            <button @click.stop="appStore.downloadPackageIds(missingDependencies)" 
              v-tooltip="`##一键下载共计 ${missingDependencies.length} 个缺失的依赖项##\n^^注意：部分创意工坊已经下架的模组将自动忽略！^^`"
              class="px-1 py-1 right-1/2 translate-x-1/2 absolute bottom-full mb-2 opacity-0 group-hover:pointer-events-auto group-hover:opacity-100 bg-accent-danger/80 text-text-main/50 rounded-md hover:bg-accent-danger hover:text-text-main transition-all duration-200" >
              <Download />
            </button>
          </div>
          <!-- 添加未启用的依赖项 -->
          <button v-if="inactiveDependenciesToAdd.length > 0" @click="addInactiveMods(inactiveDependenciesToAdd)" 
            v-tooltip="`^^一键添加共计 ${inactiveDependenciesToAdd.length} 个未启用的依赖项^^`"
            class="px-1 py-1 bg-accent-secondary/80 text-text-main/50 rounded-md hover:bg-accent-secondary hover:text-text-main transition-all" >
            <GitPullRequestCreate />
          </button>
          <button v-if="inactiveLanguageModsToAdd.length > 0" @click="addInactiveMods(inactiveLanguageModsToAdd)" 
            v-tooltip="`^^一键添加共计 ${inactiveLanguageModsToAdd.length} 个未启用的语言包^^`"
            class="px-1 py-1 bg-accent-secondary/80 text-text-main/50 rounded-md hover:bg-accent-secondary hover:text-text-main transition-all" >
            <MessageSquarePlus />
          </button>
          <!-- 移除所有无效Mod -->
          <button v-if="invalidModsToRemove.length > 0" @click="removeInvalidMod" 
            v-tooltip="`^^一键移除共计 ${invalidModsToRemove.length} 个无效Mod^^`"
            class="px-1 py-1 bg-accent-danger/80 text-text-main/50 rounded-md hover:bg-accent-danger hover:text-text-main transition-all" >
            <Trash2 />
          </button>
        </div>

      </div>

    </div>

  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch, onMounted, nextTick, onBeforeUnmount } from 'vue';
import VirtualList from 'vue-virtual-sortable';
import { useToast } from "vue-toastification";
import { Motion } from 'motion-v';
import { useAppStore } from '../stores/appStore';
import { useModStore } from '../stores/modStore';
import { useSearchStore } from '../stores/searchStore';
import { generateHtmlHelp } from '../modules/search/SearchHelp'
import { ISSUE_TITLE_MAP, ISSUE_TYPE } from '../utils/constants';
import ModItem from './utils/ModItem.vue';
import TagsSearch from './common/TagsSearch/TagsSearch.vue';
import DependencyGraph from './utils/DependencyGraph.vue'
import { Download, Flag, GitPullRequestCreate, Megaphone, MegaphoneOff, MessageSquarePlus, SearchAlert, Trash2 } from 'lucide-vue-next';
import { useContextMenuStore } from '../stores/contextMenuStore';
import { useWorkspaceStore } from '../stores/workspaceStore';
import { useGuideStore } from '../stores/guideStore';

// 这里 modelValue 接收纯 ID 数组
const props = defineProps({
  title: { type: String, default: 'Default' },
  listId: { type: String, required: true },
  modelValue: { type: Array as () => string[], required: true }, // Array<string>
  hasSidebar: { type: Boolean, default: false },
  listColor: { type: String, default: 'primary' } // danger/highlight/special/cool/primary/success/tip/warn/secondary/warning
})

const emit = defineEmits(['update:modelValue'])
const appStore = useAppStore()
const modStore = useModStore()
const searchStore = useSearchStore()
const menuStore = useContextMenuStore()
const toast = useToast();
const vListRef = ref(null)  // 虚拟列表引用, 用于滚动到选中项
const listKey = ref(0)

const searchTagsRef = ref(null)
const listContainerRef = ref(null)

// --- 1. 搜索与筛选逻辑 ---
// 状态
const isSimpleView = ref(true) // 是否简单视图
const isSortAsc = ref(true)   // 是否升序排序
const sortMode = ref('default')  // 排序模式

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
const filterIssueType = ref('')   // 筛选问题项类型

const isSortChange = ref(false) // 是否排序切换

// 获取 Engine 实例 (computed 确保响应式)
const engine = computed(() => searchStore.engine)

// --- 2. 显示列表计算 (Filter -> Sort) ---
// 仅当允许拖拽排序时 (默认模式且无筛选) 为 True
// 注意：如果 filtered，禁止排序，因为无法映射回原数组的正确位置
const isFiltered = computed(() => filterQuery.value.length > 0 || isFilterByIssue.value || filterByLine.value?.length > 0)
const allowSort = computed(() => sortMode.value === 'default' && !isFiltered.value && isSortAsc.value)
const allMods = computed(() => modStore.allModsMap ? Array.from(modStore.allModsMap.values()) : [])
const itemHeight = computed(() => isSimpleView.value ? appStore.scalePx(30)+4 : appStore.scalePx(50)+4 )

// ===== 问题项筛选及提示 =====
// 计算当前列表的错误概况
const issuesSummary = computed(() => modStore.getListIssues(props.listId))

// 切换问题项筛选
const toggleIssueFilter = () => {
  isFilterByIssue.value = !isFilterByIssue.value
  filterIssueType.value = ''  // 整体筛选时，清空问题项类型筛选
  // 如果开启筛选，清空搜索框以免冲突，或者叠加逻辑
  if (isFilterByIssue.value) {
    // 可以在这里设置 filterQuery = 'has:issue' 之类的特殊标记
    // 或者直接修改 displayList 的计算逻辑
  }
}
const toggleIssueTypeFilter = (type: string) => {
  console.log('toggleIssueTypeFilter', type)
  // 检查类型是否符合ISSUE_TYPE
  if (!Object.values(ISSUE_TYPE).includes(type)) {
    isFilterByIssue.value = false
    filterIssueType.value = ''
    return
  }
  if (!filterIssueType.value) {
    isFilterByIssue.value = true
  }
  // 切换选中状态
  filterIssueType.value = filterIssueType.value === type ? '' : type
}
// 清除筛选
const clearFilter = () => {
  filterQuery.value = []
  isFilterByIssue.value = false
  filterByLine.value = []
  filterIssueType.value = ''
}

// 动态计算帮助文本
const searchHelpText = computed(() => {
  if (!engine.value) return 'Loading...';
  // 这里可以做一层缓存，避免每次 render 都生成字符串
  return generateHtmlHelp(engine.value);
})

// 提取缺失模组列表
const missingModIds = computed(() => {
  const missingModIdsByPath = modStore.getIssusTargetIds(props.modelValue, ISSUE_TYPE.ERROR_MISSING_FILE)
  const missingModIdsByOrder = props.modelValue.filter(package_id => !modStore.allModsMap.has(package_id.toLowerCase()))
  return [...missingModIdsByPath, ...missingModIdsByOrder]  
})
// 提取完全缺失的依赖项列表
const missingDependencies = computed(() => {
  if (!issuesSummary.value.stats[ISSUE_TYPE.ERROR_MISSING_DEPENDENCY]?.length) return []
  return modStore.getIssusTargetIds(props.modelValue, ISSUE_TYPE.ERROR_MISSING_DEPENDENCY)
})
// 提取真正需要被添加的、去重后的依赖项列表
const inactiveDependenciesToAdd = computed(() => {
  // 仅当当前列表真的有依赖报错时，才去执行精准提取（性能优化）
  if (!issuesSummary.value.stats[ISSUE_TYPE.ERROR_INACTIVE_DEPENDENCY]?.length) return []
  return modStore.getMissingLocalDependencies(props.modelValue)
})
// 提取真正需要被添加的、去重后的语言包项列表
const inactiveLanguageModsToAdd = computed(() => {
  if (!issuesSummary.value.stats[ISSUE_TYPE.WARN_INACTIVE_LANGUAGE_PACK]?.length) return []
  return modStore.getMissingLanguagePacks(props.modelValue)
})
// 提取需要被移除的无效 Mod 列表（这个其实是一一对应的，为了模板整洁也包装一下）
const invalidModsToRemove = computed(() => {
  return issuesSummary.value.stats[ISSUE_TYPE.ERROR_MISSING_FILE] || []
})
// 构造问题详情 Tooltip
const issueTooltip = computed(() => {
  const summary = issuesSummary.value // Store 返回的对象
  // console.log('问题摘要:', summary)
  if (summary.count === 0) return null
  const errorInfo = summary.errorCount > 0 ? `!!${summary.errorCount} 个错误!!` : ''
  const warningInfo = summary.warnCount > 0 ? `^^${summary.warnCount} 个警告^^` : ''
  let text = `**发现 ${summary.count} 个问题Mod**（${errorInfo} ${warningInfo}）`
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
  text += isFilterByIssue.value ? '\n\n__[[(再次点击取消筛选)]]__' : '\n\n__[[(点击筛选查看全部问题项)]]__'
  text += '\n__[[(可从^^右键菜单^^筛选单项问题)]]__'
  text += appStore.settings.check_language_support ? '\n__(可在设置中关闭语言支持检查)__' : ''
  return text
})
// 排序提示
const sortTooltip = computed(() => {
  let text = `按${SORT_MODE_MAP[sortMode.value]}排序`
  text += `${isSortAsc.value ? '（升序）' : '（降序）'}`
  text += "\n__筛选和排序只供视觉检阅，^^不影响实际顺序^^，\n并且此状态下^^禁止拖拽排序或插入^^__"
  return text
})
// 筛选提示
const filterTooltip = computed(() => {
  let text = ''
  if (filterQuery.value.length > 0) { text += `已筛选检索关键词` }
  if (isFilterByIssue.value) { text += '\n已筛选问题项' }
  if (filterByLine.value.length > 0) { text += `\n已筛选依赖组` }
  text = text.trim()
  text += "\n__筛选和排序只供视觉检阅，^^不影响实际顺序^^，\n并且此状态下^^禁止拖拽排序或插入^^__"
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
      // 从所有问题项中检测是否有该 Mod 的问题
      const issues = modStore.modIssues.get(id.toLowerCase())
      // 有问题项且符合筛选类型
      if (filterIssueType.value) {
        return issues && issues.some(issue => issue.type === filterIssueType.value)
      }
      // 有问题项但未指定类型，默认显示
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
      if (sortMode.value === 'author') return (mA?.author?.[0] || '').localeCompare(mB?.author?.[0] || '')
      if (sortMode.value === 'package_id') return (mA?.package_id || a).localeCompare(mB?.package_id || b)
      if (sortMode.value === 'last_active_time') return (mA?.last_active_time || 0) - (mB?.last_active_time || 0)
      if (sortMode.value === 'last_moved_time') return (mA?.last_moved_time || 0) - (mB?.last_moved_time || 0)
      if (sortMode.value === 'file_create_time') return (mA?.file_create_time || 0) - (mB?.file_create_time || 0)
      if (sortMode.value === 'file_modify_time') return (mA?.file_modify_time || 0) - (mB?.file_modify_time || 0)
      if (sortMode.value === 'file_size') return (mA?.file_size || 0) - (mB?.file_size || 0)

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
const SORT_MODE_MAP = {
  'default': '默认',
  'name': '名称',
  'package_id': '包名',
  'author': '作者',
  'last_active_time': '启用时间',
  'last_moved_time': '移动时间',
  'file_create_time': '创建时间',
  'file_modify_time': '修改时间',
  'file_size': '文件大小',
}
const sortIcon = computed(() => {
  return SORT_MODE_MAP[sortMode.value] || '默认'
})

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
  // 需要知道在 e.newIndex 这个位置之前，有多少个“非移动项”
  // 在剔除移动项后的 baseList 中找到正确的插入位置
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
      // 说明链条在 baseList 中是连续存在的。 必须跳过，不能插在它前面。
      if (baseList.includes(nextId)) {
        // 找到 nextId 在 baseList 中的位置
        const nextIndexInBase = baseList.indexOf(nextId)
        // 如果 nextId 就在当前插入点或其后方，说明插在了链条中间
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

// 添加缺失的依赖项
const addInactiveMods = async (missingIds) => {
  if (missingIds.length === 0) return
  // console.log('添加缺失的依赖项:', uniqueInactiveDependencies)
  const oldIds = [...props.modelValue]
  modStore.removeIdsOnAllList(missingIds)
  oldIds.push(...missingIds)
  emit('update:modelValue', oldIds)
  // 更新移动时间
  modStore.takeModListByIds(missingIds).forEach(mod => {
    mod.last_moved_time = Date.now()
    mod.last_active_time = Date.now()
  })
  // 强制重绘（连选拖拽第一项向下2倍选中范围内会导致排序异常，需要重绘）
  await nextTick()
  // 通过翻转排序两次，实现软重绘
  isSortAsc.value=!isSortAsc.value
  await nextTick()
  isSortAsc.value=!isSortAsc.value
}
// 移除无效的mod
const removeInvalidMod = async () => {
  const invalidMods = invalidModsToRemove.value
  if (invalidMods.length === 0) return
  // console.log('移除无效的Mod:', invalidMods)
  modStore.removeIdsOnAllList(invalidMods)
  // 强制重绘（连选拖拽第一项向下2倍选中范围内会导致排序异常，需要重绘）
  await nextTick()
  // 通过翻转排序两次，实现软重绘
  isSortAsc.value=!isSortAsc.value
  await nextTick()
  isSortAsc.value=!isSortAsc.value
}

// 问题提示右键菜单
const issueContextMenu = async (event) => {
  // console.log(issueState,issueState.value)
  // 通用菜单
  const commnMenuItems = [
    // { label: '修改类型', icon: ChessPawn,
    //   children: [...Object.entries(MOD_TYPE_MAP).map(([key, value]) => ({ 
    //     icon: MOD_TYPE_ICON_MAP[key],
    //     label: value, action: () => modStore.setModsType(selectedIds, key)
    //   })),{ label: '恢复默认', level: 'warn', action: () => modStore.setModsType(selectedIds, null) }]
    // },
  ]
  // 1. 获取所有选中 Mod 的当前问题并集
  const allSelectedIssues = props.modelValue.flatMap(id => modStore.modIssues.get(id.toLowerCase()) || []);
  // 2. 提取唯一的错误类型 (Type Unique Set)
  const uniqueIssueTypes = [...new Set(allSelectedIssues.map(i => i.type))];

  // 3. 检查选中项中是否有人已经设置了忽略 (用于显示“恢复警告”)
  const anyModHasIgnored = props.modelValue.some(id => {
    const m = modStore.takeModById(id);
    return m && m.ignored_issues && m.ignored_issues.length > 0;
  });
  // 统一的问题菜单组
  const issueManagementItems = [];
  // 如果并集不为空，显示“筛选...”子菜单
  if (uniqueIssueTypes.length > 0) {
    issueManagementItems.push({
      label: props.modelValue.length > 1 ? `筛选单项问题 (${uniqueIssueTypes.length})...` : '筛选单项问题...',
      icon: SearchAlert,
      children: uniqueIssueTypes.map(type => ({
        label: `单独筛选：${ISSUE_TITLE_MAP[type] || type}`,
        // 这里的 level 可以取该类型在所有 Mod 中的最高级别
        level: allSelectedIssues.find(i => i.type === type)?.level || 'warn',
        action: () => toggleIssueTypeFilter(type)
      }))
    });
  }
  // A. 如果并集不为空，显示“忽略...”子菜单
  if (uniqueIssueTypes.length > 0) {
    issueManagementItems.push({ divider: true });
    issueManagementItems.push({
      label: props.modelValue.length > 1 ? `忽略所有问题 (${uniqueIssueTypes.length})...` : '忽略问题...',
      icon: MegaphoneOff,
      children: uniqueIssueTypes.map(type => ({
        label: `忽略：${ISSUE_TITLE_MAP[type] || type}`,
        // 这里的 level 可以取该类型在所有 Mod 中的最高级别
        level: allSelectedIssues.find(i => i.type === type)?.level || 'warn',
        action: () => modStore.batchIgnoreIssues(props.modelValue, type)
      }))
    });
  }
  // B. 如果有选项被忽略了，显示“恢复警告”
  if (anyModHasIgnored) {
    // 如果之前没加 divider，补一个
    if (issueManagementItems.length === 0) issueManagementItems.push({ divider: true });
    issueManagementItems.push({
      label: props.modelValue.length > 1 ? '恢复所有警告' : '恢复警告',
      icon: Megaphone,
      level: 'warn',
      action: () => modStore.batchIgnoreIssues(props.modelValue, null)
    });
  }

  // 合并菜单
  const menuItems = [
  ...commnMenuItems,
  ...issueManagementItems, // 插入批量忽略逻辑
];

  menuStore.open(event, menuItems)
}

// 点击列表区域时自动获取焦点，确保按键生效
const focusContainer = (e) => {
  e.currentTarget.focus()
}
/**
 * 3. 键盘导航核心函数
 * @param {number} direction -1 为向上，1 为向下
 */
const handleKeyNav = (direction) => {
  const list = displayList.value // 当前经过筛选/排序后的 ID 数组
  if (!list.length) return
  // 确定当前选中的索引
  const currentId = modStore.lastSelectedMod?.package_id
  const currentIndex = list.indexOf(currentId)
  // 计算下一个索引
  let nextIndex = currentIndex + direction
  // 边界保护：循环选择或停止
  if (nextIndex < 0) nextIndex = 0
  if (nextIndex >= list.length) nextIndex = list.length - 1
  if (nextIndex === currentIndex) return
  const nextId = list[nextIndex]
  // 4. 更新 Store 选中状态
  // 建议：键盘导航通常视为单选，所以传入 [nextId]
  modStore.selectMods([nextId], nextId)
  // 5. 同步滚动 (关键点)
  const vList = vListRef.value
  if (vList) {
    const currentOffset = vList.getOffset()
    const viewHeight = vList.$el.clientHeight // 视口高度
    // 计算目标项的像素区间
    const itemTop = nextIndex * itemHeight.value
    const itemBottom = itemTop + itemHeight.value
    // 策略 A: 保持相对位置不变 (最丝滑)
    // 逻辑：直接按位移滚动。如果向上移，offset 就减一个 itemHeight
    vList.scrollToOffset(currentOffset + (direction * itemHeight.value))
    // 策略 B: 只有当超出视口时才滚动 (标准做法)
    /*
    if (itemTop < currentOffset) {
      // 超出顶部
      vList.scrollToOffset(itemTop)
    } else if (itemBottom > currentOffset + viewHeight) {
      // 超出底部
      vList.scrollToOffset(itemBottom - viewHeight)
    }
    */
  }
}

const handleDirectiveNavigate = (nextId, nextIndex, direction) => {
  const vList = vListRef.value
  if (vList) {
    const currentOffset = vList.getOffset()
    // 策略 A: 保持相对位置不变的无缝滚动（推荐，因为 itemHeight 计算精确）
    vList.scrollToOffset(currentOffset + (direction * itemHeight.value))
    // 如果你喜欢系统原生那种“到底部才滚动页面”的感觉，可以使用策略 B：
    /*
    const viewHeight = vList.$el.clientHeight
    const itemTop = nextIndex * itemHeight.value
    const itemBottom = itemTop + itemHeight.value
    
    if (itemTop < currentOffset) {
      vList.scrollToOffset(itemTop)
    } else if (itemBottom > currentOffset + viewHeight) {
      vList.scrollToOffset(itemBottom - viewHeight)
    }
    */
  }
}

// --- 记录滚动位置 ---
// v-if 切换到 loading 时，该组件内部的 v-else 块会触发卸载
// 这是抓取当前滚动位置的最后机会
onBeforeUnmount(() => {
  savePosition();
});
const savePosition = () => {
  // 只有当虚拟列表存在且不在加载状态时才记录
  if (vListRef.value) {
    const offset = vListRef.value.getOffset();
    if (offset > 0) {
      appStore.recordScroll(props.listId, offset);
      // console.log(`[Scroll] Saved ${props.listId}: ${offset}`);
    }
  }
};
// --- 恢复滚动位置 ---
onMounted(() => {
  // 如果组件挂载时不是加载状态，说明数据已经在那了，直接尝试恢复
  if (!appStore.isLoading) {
    restorePosition();
  }
});
// --- 监听加载状态变化 ---
watch(() => appStore.isLoading, async (loading) => {
  // console.log(`[Scroll] Loading state changed to ${loading}`);
  if (loading) {
    // 刚开始加载：如果在外面手动触发加载，这里也是一个记录点
    // 但注意：如果是 v-if 切换，组件可能已经开始销毁流程了
    savePosition();
  } else {
    // 加载完成：等待 DOM 渲染
    await nextTick();
    restorePosition();
    const guideStore = useGuideStore();
  }
});
const restorePosition = () => {
  const savedOffset = appStore.getScroll(props.listId);
  if (savedOffset > 0 && vListRef.value) {
    // 虚拟列表恢复位置的“黄金组合”：nextTick + 微小延迟
    nextTick(() => {
      setTimeout(() => {
        vListRef.value?.scrollToOffset(savedOffset);
        // console.log(`[Scroll] Restored ${props.listId}: ${savedOffset}`);
      }, 30); // 30ms 足够让大部分虚拟列表完成初始化计算
    });
  }
};
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