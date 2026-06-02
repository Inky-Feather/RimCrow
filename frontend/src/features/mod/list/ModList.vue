<template>
  <div class="flex flex-col relative h-full bg-bg-surface/40  shadow-2xl"
      :class="`border-2 rounded-2xl border-accent-${listColor}/20 overflow-hidden`">
    <!-- 标题栏 -->
    <div :data-tour="listId=='active'?'list-header':null" :class="`px-3 h-8 border-b rounded-t-2xl border-border-base/5 flex justify-between items-center bg-accent-${listColor}/10`">
      <span :class="`text-sm font-bold text-accent-${listColor} uppercase tracking-wider flex items-center gap-1`">
        <div :class="`w-1.5 h-1.5 mr-1 rounded-full bg-accent-${listColor} shadow-lg shadow-accent-primary`"></div>
        <span class="mr-1">{{ title }}</span>
        <!-- 状态提示 -->
        <span v-if="isFiltered" v-tooltip="filterTooltip" @click="clearFilter"
          class="text-xs text-text-soft bg-accent-highlight/30 px-1 rounded-full ring-1 ring-accent-special/70 cursor-pointer hover:bg-accent-highlight/60 hover:text-text-main active:scale-95 transition-all">
          已筛选
        </span>
        <span v-if="sortMode !== 'default' || !isSortAsc" v-tooltip="sortTooltip" @click="clearSort"
          class="text-xs text-text-soft bg-accent-highlight/30 px-1 rounded-full ring-1 ring-accent-special/70 cursor-pointer hover:bg-accent-highlight/60 hover:text-text-main active:scale-95 transition-all">
          已排序
        </span>
      </span>

      <span class="flex items-center gap-1" :data-tour="listId=='active'?'list-status-summary':null">
        <!-- 错误指示器 (仅当有错误时显示) -->
        <button v-if="issuesSummary.count > 0" v-tooltip="issueTooltip"
          :data-tour="listId=='active'?'list-issues':null"
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
        <span v-if="isFiltered" :class="`text-xs bg-bg-inset/70 px-2 py-0.5 rounded text-accent-${listColor}`">
          {{ displayList.length }} / {{ modelValue.length }}
        </span>
        <span v-else :class="`text-xs bg-bg-inset/70 px-2 py-0.5 rounded text-accent-${listColor}`">{{ modelValue.length }}</span>
      </span>

    </div>
    
    <!-- 工具栏 (搜索 & 筛选) -->
    <div :data-tour="listId=='active'?'list-toolbar':null" class="px-2 py-1 w-full flex flex-col gap-1 shadow-xl bg-bg-deep/20">
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
                <div v-show="isSortChange" class="absolute min-w-20 h-auto p-0.5 top-full mt-1 right-1/2 left-1/2 transform -translate-x-1/2 size-4 rounded-md bg-bg-highlight/80 border border-border-base/10 shadow-2xl backdrop-blur-sm text-xs text-center text-text-dim flex flex-col gap-0.5">
                  <div v-for="(icon, mode) in SORT_MODE_MAP" :key="mode" @click="sortMode = mode" class="w-full rounded-md hover:bg-bg-overlay/10 hover:text-text-main">{{ icon }}</div>
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
    
    <!-- (tabindex="0" @keydown.ctrl.a.prevent="selectAll") 非焦点容器需要 tabindex 才能响应键盘事件 -->
    <!-- 列表区（底部渐变隐藏） -->
    <div ref="listContainerRef" class="flex-1 min-h-0 flex pb-0.5 overflow-y-auto after:pointer-events-none 
      after:content-[''] after:absolute after:bottom-0 after:w-full after:h-10 
      after:bg-linear-to-t after:from-bg-deep/80 after:to-transparent focus:outline-none"
      @click.self="modStore.clearSelection()">
      
      <!-- 左侧辅助功能区( @wheel.passive 监听滚轮事件) -->
      <div v-if="hasSidebar && appStore.settings.ui.show_dependency_graph" :data-tour="listId=='active'?'list-dependency':null" class="w-[55px] h-full flex-none"
        @wheel.passive="vListRef?.scrollToOffset(vListRef.getOffset()+$event.deltaY)">
        <DependencyGraph v-if="showDependencyGraph" :listIds="lineData" :isFilter="filterByLine.length>0"
          :itemHeight="itemHeight" :scrollElement="vListRef"
          @lineClick="handleLineClick"
        />
      </div>
      <!-- 列表主体部分 -->
      <div @click.self="modStore.clearSelection()" class="flex-1 h-full min-h-0 pl-1 pr-1 min-w-0 relative" :data-tour="listId=='active'?'list-modItem':null">
        <!-- 列表为空时的提示 -->
        <div v-show="modelValue.length === 0" class="absolute flex rounded-lg top-0 bottom-0 left-0 right-0 m-1 items-center justify-center border-2 border-dashed border-border-base/18 text-text-subtle/70 text-xs bg-bg-deep/90 select-none pointer-events-none">
          可拖拽模组到此
          <!-- 点阵背景 -->
          <div class="absolute inset-0 opacity-[0.05] pointer-events-none" style="background-image: radial-gradient(var(--color-text-main) 1px, transparent 1px); background-size: 20px 20px;"></div>
        </div>
        <!-- 列表 -->
          <!-- :size="isSimpleView ? 34 : 54" -->
        <VirtualDragList v-model="internalListProxy" ref="vListRef" :key="listKey" dataKey="id" :keeps="50" class="h-full p-1 pb-10" wrapClass="" 
          :draggable="!appStore.isLoading" :droppable="allowSort && !appStore.isLoading" :sortable="allowSort && !appStore.isLoading" :disabled="appStore.isLoading"
          :delay="appStore.settings.ui.drag_delay"
          :get-drag-meta="getModRowDragMeta"
          :group="{ name: 'mods', pull:'clone', put: allowSort ? ['mods','groups']:false, revertDrag: true }" :animation="150" 
          :size="itemHeight"
          @drop="updateChildren" @drag="startDrag" @dragend="finishDragSession"
          @click="focusContainer"
          v-selectable-list="{ 
            data: visibleList, 
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
            <div class=" relative">
              <ModItem :item_id="dataKey" :index="getRealIndex(dataKey)" :key="dataKey" :list-color="listColor" 
                :is-selected="selectedIdSet.has(normalizeId(dataKey))" :simple="isSimpleView"
                :is-in-search="searchResultSet.has(dataKey) && searchQuery.length > 0"
                :show-icon="appStore.settings.ui.show_list_icon" 
                :show-mod-icon="appStore.settings.ui.show_list_mod_icon" 
                :show-type-icon="appStore.settings.ui.show_list_modtype_icon"
                :show-index="appStore.settings.ui.show_list_index"
                :search-match="resolvedCurrentTargetId === dataKey"
                :section-feature-enabled="sectionFeatureEnabled"
                :section-header="isSectionHeaderId(dataKey)"
                :section-collapsed="isSectionCollapsed(dataKey)"
                :section-child-count="getSectionChildCount(dataKey)"
                @toggle-section="toggleSection"
                @expand-selected-sections="expandSections"
                @collapse-selected-sections="collapseSections">
              </ModItem>
              <div v-if="!isSectionHeaderId(dataKey) && modStore.takeModById(dataKey).last_active_time>appStore.settings.last_run_time && listId=='active'" v-tooltip="'最近启用（距上一次软件运行）'"
                class="absolute top-0 right-0 rounded-md bg-accent-primary text-text-main px-1 py-0.5 text-[0.6rem] text-center flex items-center justify-center">
                NEW
              </div>
            </div>
          </template>
        </VirtualDragList>

        <ModListQuickActions
          :list-id="props.listId"
          :missing-install-summary="missingInstallSummary"
          :missing-install-tooltip="missingInstallTooltip"
          :missing-install-button-class="missingInstallButtonClass"
          :supplement-summary="supplementSummary"
          :supplement-tooltip="supplementTooltip"
          :supplement-button-class="supplementButtonClass"
          :invalid-mods-to-remove="invalidModsToRemove"
          :open-missing-install-dialog="openMissingInstallDialog"
          :open-supplement-dialog="openSupplementDialog"
          :remove-invalid-mod="removeInvalidMod"
        />

      </div>

    </div>

    <div v-if="appStore.isLoading" class="absolute inset-0 flex items-center justify-center bg-bg-deep/50 z-50">
      <div class="animate-spin size-8 border-4 border-accent-primary border-t-transparent rounded-full"></div>
    </div>

  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import VirtualDragList from '../../../shared/components/list/VirtualDragList.vue';
import { useToast } from "vue-toastification";
import { Motion } from 'motion-v';
import { useAppStore } from '../../../app/stores/appStore';
import { useModStore } from '../store/modStore';
import { useSearchStore } from '../search/searchStore';
import { ISSUE_TYPE } from '../../../shared/lib/constants';
import ModItem from '../ModItem.vue';
import ModListQuickActions from './ModListQuickActions.vue';
import TagsSearch from '../search/TagsSearch.vue';
import DependencyGraph from '../DependencyGraph.vue'
import { useContextMenuStore } from '../../../shared/components/context-menu/contextMenuStore';
import { useProfileStore } from '../../profiles/profileStore';
import { useSupplementStore } from '../../supplement/supplementStore';
import { useMissingInstallStore } from '../../supplement/missingInstallStore';
import { normalizePackageId, normalizePackageToken } from '../lib/modIdentity';
import { useModListQuickActions } from './useModListQuickActions'
import { useModListQuery } from './useModListQuery'
import { useModListIssues } from './useModListIssues'
import { useModListSections } from './useModListSections'
import { useModListDrag } from './useModListDrag'
import { useModListViewport } from './useModListViewport'

// 这里 modelValue 接收纯 ID 数组
const props = defineProps({
  title: { type: String, default: 'Default' },
  listId: { type: String, required: true },
  modelValue: { type: Array as () => string[], required: true }, // Array<string>
  hasSidebar: { type: Boolean, default: false },
  listColor: { type: String, default: 'primary' } // danger/highlight/special/cool/primary/success/tip/warn/secondary/warning
})

const appStore = useAppStore()
const modStore = useModStore()
const searchStore = useSearchStore()
const menuStore = useContextMenuStore()
const profileStore = useProfileStore()
const supplementStore = useSupplementStore()
const missingInstallStore = useMissingInstallStore()
const toast = useToast();
const vListRef = ref(null)  // 虚拟列表引用, 用于滚动到选中项

const searchTagsRef = ref(null)
const listContainerRef = ref(null)

const normalizeId = (value: string) => String(value ?? '').trim().toLowerCase()
const selectedIdSet = computed(() => new Set((modStore.selectedIds || []).map(id => normalizeId(id)).filter(Boolean)))
const normalizeTokenId = (value: string) => normalizePackageToken(value)
const normalizeCanonicalId = (value: string) => normalizePackageId(value)
const {
  SORT_MODE_MAP,
  isSimpleView,
  isSortAsc,
  sortMode,
  searchQuery,
  searchLogic,
  searchResults,
  currentSearchIndex,
  filterQuery,
  filterLogic,
  filterByLine,
  isFilterByIssue,
  isSortChange,
  searchResultSet,
  resolvedCurrentTargetId,
  allowSort,
  isFiltered,
  itemHeight,
  toggleIssueFilter,
  toggleIssueTypeFilter,
  clearFilter,
  clearSort,
  searchHelpText,
  sortTooltip,
  filterTooltip,
  handleLineClick,
  showDependencyGraph,
  displayList,
  sortIcon,
  executeSearch,
  bindTargetReveal,
} = useModListQuery({
  props,
  appStore,
  modStore,
  searchStore,
  toast,
  normalizeTokenId,
  normalizeCanonicalId,
})
// 序号始终以真实列表顺序为准，而不是以当前可见列表顺序为准。
const realIndexMap = computed(() => {
  const map = new Map<string, number>()
  props.modelValue.forEach((id, index) => {
    map.set(normalizeId(id), index)
  })
  return map
})
const getRealIndex = (id: string) => realIndexMap.value.get(normalizeId(id)) ?? 0

// ===== 问题项筛选及提示 =====
// 计算当前列表的错误概况
const issuesSummary = computed(() => modStore.getListIssues(props.listId))

const {
  missingInstallSummary,
  missingInstallTooltip,
  missingInstallButtonClass,
  supplementSummary,
  supplementTooltip,
  supplementButtonClass,
  invalidModsToRemove,
  openMissingInstallDialog,
  openSupplementDialog,
} = useModListQuickActions({
  props,
  profileStore,
  supplementStore,
  missingInstallStore,
  issuesSummary,
  missingFileIssueType: ISSUE_TYPE.ERROR_MISSING_FILE,
})
const {
  sectionFeatureEnabled,
  isSectionHeaderId,
  isSectionCollapsed,
  getSectionChildCount,
  toggleSection,
  expandSections,
  collapseSections,
  visibleList,
  revealCollapsedSectionFor,
  getSectionMemberIds,
  resolveInsertionIndex,
  internalListProxy,
} = useModListSections({
  props,
  appStore,
  modStore,
  profileStore,
  displayList,
  allowSort,
  normalizeId,
})

bindTargetReveal({ vListRef, visibleList, revealCollapsedSectionFor })
// 依赖线路数据
const lineData = computed(() => {
  return visibleList.value
})

const {
  listKey,
  isDragging,
  finishDragSession,
  dispatchSyntheticDragEnd,
  refreshVirtualList,
  cancelActiveDrag,
  startDrag,
  updateChildren,
} = useModListDrag({
  props,
  appStore,
  modStore,
  vListRef,
  allowSort,
  internalListProxy,
  isSectionHeaderId,
  isSectionCollapsed,
  getSectionMemberIds,
  resolveInsertionIndex,
  normalizeId,
  normalizeCanonicalId,
})

const {
  issueTooltip,
  removeInvalidMod,
  issueContextMenu,
} = useModListIssues({
  props,
  appStore,
  modStore,
  menuStore,
  issuesSummary,
  invalidModsToRemove,
  refreshVirtualList,
  isFilterByIssue,
  toggleIssueTypeFilter,
  normalizeTokenId,
})

const {
  focusContainer,
  handleDirectiveNavigate,
} = useModListViewport({
  props,
  appStore,
  modStore,
  vListRef,
  visibleList,
  itemHeight,
  isDragging,
  finishDragSession,
  dispatchSyntheticDragEnd,
  cancelActiveDrag,
})

const getModRowDragMeta = (row) => {
  // 这段逻辑只在 dragstart 执行。选择集合可能频繁变化，但不应该反向污染虚拟列表 row 流。
  if (row?.mod_ids?.length) {
    return {
      dragCount: Math.max(1, row.mod_ids.length),
      dragLabel: row.id,
    }
  }
  const selectedSet = new Set((modStore.selectedIds || []).map(id => normalizeId(id)).filter(Boolean))
  const id = normalizeId(row?.id)
  return {
    dragCount: id && selectedSet.has(id) ? Math.max(1, selectedSet.size) : 1,
    dragLabel: row?.id,
  }
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
