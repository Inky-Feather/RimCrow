<template>
  <div class="flex flex-col relative h-full bg-bg-surface/40  shadow-2xl"
      :data-key-scope="`mod-list:${listId}`"
      @pointerdown="setListKeyScope"
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
        <TagSearchInput :list-color="listColor" v-model="searchQuery" v-model:logic="searchLogic" ref="searchTagsRef" class="z-10"
          :controller="engine?.controller" @search="executeSearch(true)" placeholder="输入关键词定位Mod位置……">
          <template #right>
            <div class="flex gap-1 items-center justify-center">
              <!-- 定位按钮 -->
              <button @click="searchTagsRef?.addTag();executeSearch(true)" v-tooltip="'搜索定位下一个符合条件的结果'"
                :class="`px-2.5 py-1 m-0 relative rounded-lg bg-accent-${listColor}/50 hover:bg-accent-${listColor} 
                text-text-dim hover:text-text-main text-xs font-bold shadow-lg shadow-accent-${listColor}/10 
                transition-all cursor-pointer hover:scale-105 active:scale-95`">定位
                <div v-if="currentSearchIndex !== -1 && searchQuery.length > 0" class="text-[0.55rem] absolute -top-2 -left-1 text-text-main bg-accent-highlight px-1 rounded-lg">{{ currentSearchIndex + 1 }} / {{ searchResults.length }}</div>
              </button>
              <!-- 视图切换按钮 -->
              <Motion :class="`p-1 size-7 rounded-md bg-accent-${listColor}/20 border border-accent-${listColor}/30 hover:bg-accent-${listColor}/50 text-accent-${listColor} hover:text-text-main text-xs font-bold shadow-lg shadow-accent-${listColor}/10 flex items-center justify-center cursor-pointer `"
                :initial="{ rotateX: 0, opacity: 1 }" :animate="{ rotateX: isSimpleView ? 180 : 0 /*切换时旋转180度*/}" 
                :transition="{ type: 'spring', /*弹性过渡动画*/ stiffness: 300, /*动画刚度*/ damping: 20 /*动画阻尼（回弹效果）*/}"
                @click="isSimpleView = !isSimpleView" v-tooltip="'切换列表视图'" >
                <svg v-if="!isSimpleView" class="size-4" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" ><rect width="7" height="7" x="3" y="3" rx="1"/><rect width="7" height="7" x="3" y="14" rx="1"/><path d="M14 4h7"/><path d="M14 9h7"/><path d="M14 15h7"/><path d="M14 20h7"/></svg>
                <svg v-else class="size-4" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" ><path d="M3 5h.01"/><path d="M3 12h.01"/><path d="M3 19h.01"/><path d="M8 5h13"/><path d="M8 12h13"/><path d="M8 19h13"/></svg>
              </Motion>
            </div>
          </template>
        </TagSearchInput>
      </div>
        
      <div class="flex items-center justify-center gap-1">
        <!-- 筛选过滤 (Filter) -->
        <TagSearchInput :list-color="listColor" v-model="filterQuery" v-model:logic="filterLogic" class="z-5"
          :controller="engine?.controller" search-help-text="" placeholder="输入关键词筛选Mod……">
          <template #icon>
            <svg class="w-3 h-3 text-text-dim" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2.586a1 1 0 01-.293.707l-6.414 6.414a1 1 0 00-.293.707V17l-4 4v-6.586a1 1 0 00-.293-.707L3.293 7.293A1 1 0 013 6.586V4z" /></svg>
          </template>

          <template #right>
            <div class="flex gap-1 items-center justify-center">
              <!-- 排序切换按钮 -->
              <button @click="isSortChange = !isSortChange" @blur="isSortChange = false" v-tooltip="sortTooltip"
                :class="`px-2.5 py-1 m-0 rounded-lg bg-accent-${listColor}/50 hover:bg-accent-${listColor} 
                text-text-dim hover:text-text-main text-xs font-bold shadow-lg shadow-accent-${listColor}/10 transition-all relative`">
                {{ sortIcon }}
                <div v-show="isSortChange" class="absolute min-w-20 h-auto p-0.5 top-full mt-1 right-1/2 left-1/2 transform -translate-x-1/2 size-4 rounded-md bg-bg-highlight/80 border border-border-base/10 shadow-2xl backdrop-blur-sm text-xs text-center text-text-dim flex flex-col gap-0.5">
                  <div v-for="(icon, mode) in SORT_MODE_MAP" :key="mode" @click="sortMode = mode" class="w-full rounded-md hover:bg-bg-overlay/10 hover:text-text-main">{{ icon }}</div>
                </div>
              </button>
              <!-- 逆序切换按钮 -->
              <Motion :class="`p-1 size-7 rounded-md bg-accent-${listColor}/20 border border-accent-${listColor}/30 hover:bg-accent-${listColor}/50 text-accent-${listColor} hover:text-text-main text-xs font-bold shadow-lg shadow-accent-${listColor}/10 flex items-center justify-center cursor-pointer `"
                :initial="{ rotateX: 0, opacity: 1 }" :animate="{ rotateX: isSortAsc ? 0 : 180 /*切换时旋转180度*/}" 
                :transition="{ type: 'spring', /*弹性过渡动画*/ stiffness: 300, /*动画刚度*/ damping: 20 /*动画阻尼（回弹效果）*/}"
                @click="isSortAsc=!isSortAsc" v-tooltip="isSortAsc?'切换为降序排列':'切换为升序排列'" >
                <svg v-if="isSortAsc" class="size-4 rotate-x-180" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" ><path d="m3 16 4 4 4-4"/><path d="M7 20V4"/><path d="M11 4h4"/><path d="M11 8h7"/><path d="M11 12h10"/></svg>
                <svg v-else class="size-4" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" ><path d="m3 8 4-4 4 4"/><path d="M7 4v16"/><path d="M11 12h4"/><path d="M11 16h7"/><path d="M11 20h10"/></svg>
              </Motion>
            </div>
          </template>
        </TagSearchInput>
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
        <DependencyGraph v-if="showDependencyGraph" :listIds="lineData" :line-filter-ids="filterByLine" :isFilter="filterByLine.length>0"
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
                :move-menu="moveMenuContext"
                :current-split-group="getCurrentSplitGroupMeta(dataKey)"
                :section-feature-enabled="sectionFeatureEnabled"
                :section-header="isSectionHeaderId(dataKey)"
                :section-collapsed="isSectionCollapsed(dataKey)"
                :section-child-count="getSectionChildCount(dataKey)"
                @toggle-section="toggleSection"
                @expand-selected-sections="expandSections"
                @collapse-selected-sections="collapseSections"
                @expand-all-sections="expandAllSections"
                @collapse-all-sections="collapseAllSections"
                @move-selected="handleMoveSelected">
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
          :model-value="props.modelValue"
          :refresh-virtual-list="refreshVirtualList"
        />

      </div>

    </div>

    <div v-if="appStore.isLoading" class="absolute inset-0 flex items-center justify-center bg-bg-deep/50 z-50">
      <div class="animate-spin size-8 border-4 border-accent-primary border-t-transparent rounded-full"></div>
    </div>

  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import VirtualDragList from '../../../shared/components/list/VirtualDragList.vue';
import { useToast } from "vue-toastification";
import { Motion } from 'motion-v';
import { useAppStore } from '../../../app/stores/appStore';
import { useModStore } from '../stores/modStore';
import { useSearchStore } from '../stores/searchStore';
import { ISSUE_TITLE_MAP } from '../../../shared/lib/constants';
import ModItem from '../ModItem.vue';
import ModListQuickActions from './ModListQuickActions.vue';
import TagSearchInput from '../../../shared/components/tag-search/TagSearchInput.vue';
import DependencyGraph from '../DependencyGraph.vue'
import { useContextMenuStore } from '../../../shared/components/context-menu/contextMenuStore';
import { useProfileStore } from '../../profiles/profileStore';
import { useGuideStore } from '../../guide/guideStore'
import { normalizePackageId, normalizePackageToken } from '../lib/modIdentity';
import { useModListQuery } from './useModListQuery'
import { useModListSections } from './useModListSections'
import { useModListDrag } from './useModListDrag'
import { setActiveKeyScope } from '../../../shared/commands/keyScopeStore'
import { registerModListActions } from '../../../app/commands/modListActions'
import { Megaphone, MegaphoneOff, SearchAlert } from 'lucide-vue-next'

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
const toast = useToast();
const vListRef = ref(null)  // 虚拟列表引用, 用于滚动到选中项

const searchTagsRef = ref(null)
const listContainerRef = ref(null)
// 最近交互过的列表作为键盘作用域兜底；焦点不在列表 DOM 内时也能继续处理列表级快捷键。
const setListKeyScope = () => setActiveKeyScope(`mod-list:${props.listId}`)

const normalizeId = (value: string) => String(value ?? '').trim().toLowerCase()
const selectedIdSet = computed(() => new Set((modStore.selectedIds || []).map(id => normalizeId(id)).filter(Boolean)))
const normalizeTokenId = (value: string) => normalizePackageToken(value)
const normalizeCanonicalId = (value: string) => normalizePackageId(value)
const {
  SORT_MODE_MAP,
  // 视图与排序
  isSimpleView, isSortAsc, sortMode, allowSort, sortIcon, isSortChange,
  // 搜索定位
  searchQuery, searchLogic, searchResults, currentSearchIndex, searchResultSet, resolvedCurrentTargetId, executeSearch, bindTargetReveal,
  // 筛选状态
  filterQuery, filterLogic, filterByLine, isFilterByIssue, isFiltered, toggleIssueFilter, toggleIssueTypeFilter, clearFilter, clearSort, handleLineClick,
  // 展示与提示
  itemHeight, engine, sortTooltip, filterTooltip, showDependencyGraph, displayList,
} = useModListQuery({ 
  props, appStore,  modStore, searchStore, toast, normalizeTokenId, normalizeCanonicalId,
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
const issueTooltip = computed(() => {
  const summary = issuesSummary.value
  if (summary.count === 0) return null
  const errorInfo = summary.errorCount > 0 ? `!!${summary.errorCount} 个错误!!` : ''
  const warningInfo = summary.warnCount > 0 ? `^^${summary.warnCount} 个警告^^` : ''
  let text = `**发现 ${summary.count} 个问题Mod**（${errorInfo} ${warningInfo}）`
  for (const [type, ids] of Object.entries(summary.stats)) {
    if ((ids as string[]).length === 0) continue
    const typeName = ISSUE_TITLE_MAP[type] || type
    const isError = ['missing_dependency', 'inactive_dependency', 'missing_file', 'incompatible', 'wrong_order', 'multiplayer_incompatible'].includes(type)
    const titleMark = isError ? '!!' : '^^'
    text += `\n${titleMark}${typeName} (${(ids as string[]).length}):${titleMark}`
    ;(ids as string[]).slice(0, 3).forEach(id => {
      text += `\n  • ${modStore.displayModName(id)}`
    })
    if ((ids as string[]).length > 3) {
      text += `\n  __...及其他 ${(ids as string[]).length - 3} 项__`
    }
  }
  text += isFilterByIssue.value ? '\n\n__[[(再次点击取消筛选)]]__' : '\n\n__[[(点击筛选查看全部问题项)]]__'
  text += '\n__[[(可从^^右键菜单^^筛选单项问题)]]__'
  text += appStore.settings.check_language_support ? '\n__(可在设置中关闭语言支持检查)__' : ''
  return text
})
const issueContextMenu = async (event) => {
  const allSelectedIssues = props.modelValue.flatMap(id => modStore.modIssues.get(normalizeTokenId(id)) || [])
  const uniqueIssueTypes = [...new Set(allSelectedIssues.map(i => i.type))]
  const anyModHasIgnored = props.modelValue.some(id => {
    const mod = modStore.takeModById(id)
    return mod && mod.ignored_issues && mod.ignored_issues.length > 0
  })
  const issueManagementItems = []
  if (uniqueIssueTypes.length > 0) {
    issueManagementItems.push({
      label: props.modelValue.length > 1 ? `筛选单项问题 (${uniqueIssueTypes.length})...` : '筛选单项问题...',
      icon: SearchAlert,
      children: uniqueIssueTypes.map(type => ({
        label: `单独筛选：${ISSUE_TITLE_MAP[type] || type}`,
        level: allSelectedIssues.find(i => i.type === type)?.level || 'warn',
        action: () => toggleIssueTypeFilter(type)
      }))
    })
    issueManagementItems.push({ divider: true })
    issueManagementItems.push({
      label: props.modelValue.length > 1 ? `忽略所有问题 (${uniqueIssueTypes.length})...` : '忽略问题...',
      icon: MegaphoneOff,
      children: uniqueIssueTypes.map(type => ({
        label: `忽略：${ISSUE_TITLE_MAP[type] || type}`,
        level: allSelectedIssues.find(i => i.type === type)?.level || 'warn',
        action: () => modStore.batchIgnoreIssues(props.modelValue, type)
      }))
    })
  }
  if (anyModHasIgnored) {
    if (issueManagementItems.length === 0) issueManagementItems.push({ divider: true })
    issueManagementItems.push({
      label: props.modelValue.length > 1 ? '恢复所有警告' : '恢复警告',
      icon: Megaphone,
      level: 'warn',
      action: () => modStore.batchIgnoreIssues(props.modelValue, null)
    })
  }
  menuStore.open(event, issueManagementItems)
}

const {
  // 分割组状态
  sectionFeatureEnabled, splitGroupFeatureEnabled, currentSectionGroups, takeSectionGroupsByListId,
  isSectionHeaderId, isSectionCollapsed, getSectionChildCount, collapsedSectionCount, expandableSectionCount,
  // 折叠操作
  toggleSection, expandSections, collapseSections, expandAllSections, collapseAllSections,
  // 可见列表与定位
  visibleList, revealCollapsedSectionFor, findCurrentSectionGroupById,
  // 拖拽与移动
  getSectionMemberIds, resolveInsertionIndex, correctInterlockInsertIndex, internalListProxy,
  moveIdsToListBoundary, moveIdsToCurrentSectionBoundary, moveIdsToSectionGroup,
} = useModListSections({
  props, appStore, modStore, profileStore, displayList, allowSort, normalizeId, normalizeCanonicalId,
})

const canMoveListItems = computed(() => !appStore.isLoading && allowSort.value)
const selectedHasSplitHeader = computed(() => (
  sectionFeatureEnabled.value
  && (modStore.selectedIds || []).some(id => isSectionHeaderId(id))
))
const currentSplitGroupId = computed(() => {
  if (!sectionFeatureEnabled.value || selectedHasSplitHeader.value) return ''
  const groupIds = [...new Set(
    (modStore.selectedIds || [])
      .map(id => findCurrentSectionGroupById(id)?.groupId || '')
      .filter(Boolean)
  )]
  return groupIds.length === 1 ? groupIds[0] : ''
})
const canMoveWithinSplitGroup = computed(() => (
  splitGroupFeatureEnabled.value
  && canMoveListItems.value
  && !selectedHasSplitHeader.value
  && !!currentSplitGroupId.value
))
const SECTION_TARGET_MENU_LABEL_MAP = {
  active: '启用列表分割组...',
  inactive: '停用列表分割组...',
}
const splitGroupTargets = computed(() => {
  if (!canMoveListItems.value || selectedHasSplitHeader.value) return []
  const targets = []
  const currentGroups = splitGroupFeatureEnabled.value
    ? currentSectionGroups.value.filter(group => !currentSplitGroupId.value || group.groupId !== currentSplitGroupId.value)
    : []
  if (currentGroups.length) {
    targets.push({
      listId: props.listId,
      label: props.listId === 'active' ? '其他分割组...' : '当前列表其他分割组...',
      groups: currentGroups.map(group => ({
        groupId: group.groupId,
        label: group.label,
        count: group.modIds.length,
      })),
    })
  }
  ;['active', 'inactive'].forEach((listId) => {
    if (listId === props.listId) return
    const targetGroups = takeSectionGroupsByListId(listId)
    if (!targetGroups.length) return
    targets.push({
      listId,
      label: SECTION_TARGET_MENU_LABEL_MAP[listId] || '其它列表分割组...',
      groups: targetGroups.map(group => ({
        groupId: group.groupId,
        label: group.label,
        count: group.modIds.length,
      })),
    })
  })
  return targets.filter(target => target.groups.length > 0)
})
const moveMenuContext = computed(() => ({
  listId: props.listId,
  enabled: canMoveListItems.value,
  canMoveWithinSplitGroup: canMoveWithinSplitGroup.value,
  splitGroupTargets: splitGroupTargets.value,
  sectionGroupCount: expandableSectionCount.value,
  collapsedSectionGroupCount: collapsedSectionCount.value,
}))
const currentSplitGroupMetaById = computed(() => {
  const map = new Map<string, { headerId: string, label: string, collapsed: boolean }>()
  if (!splitGroupFeatureEnabled.value) return map
  currentSectionGroups.value.forEach(group => {
    const meta = {
      headerId: group.headerId,
      label: group.label,
      collapsed: !!isSectionCollapsed(group.headerId),
    }
    map.set(normalizeId(group.headerId), meta)
    group.modIds.forEach(id => map.set(normalizeId(id), meta))
  })
  return map
})
const getCurrentSplitGroupMeta = (id: string) => currentSplitGroupMetaById.value.get(normalizeId(id)) || null

// 处理移动菜单点击事件
const handleMoveSelected = async ({ action, targetGroupId, targetListId } = {}) => {
  const ids = [...(modStore.selectedIds || [])]
  if (!ids.length || !canMoveListItems.value) return

  let changed = false
  if (action === 'list-top' || action === 'list-bottom') {
    changed = await moveIdsToListBoundary({
      ids,
      position: action === 'list-top' ? 'top' : 'bottom',
    })
  } else if (action === 'group-top' || action === 'group-bottom') {
    changed = await moveIdsToCurrentSectionBoundary({
      ids,
      position: action === 'group-top' ? 'top' : 'bottom',
    })
  } else if (action === 'split-group' && targetGroupId) {
    changed = await moveIdsToSectionGroup({
      ids,
      targetGroupId,
      targetListId: targetListId || props.listId,
      position: 'bottom',
    })
  }

  if (changed) {
    await refreshVirtualList()
    // 复用现有搜索定位链路。先清空再设置，确保连续移动同一项时也会重新触发滚动。
    modStore.currentTargetId = ''
    await nextTick()
    modStore.currentTargetId = ids[0]
  }
}

const revealFirstSelected = async () => {
  const targetId = modStore.selectedIds?.[0]
  if (!targetId) return false
  modStore.currentTargetId = ''
  await nextTick()
  modStore.currentTargetId = targetId
  return true
}

const unregisterModListActions = registerModListActions(`mod-list:${props.listId}`, {
  moveSelectedToListBoundary: (position: 'top' | 'bottom') => handleMoveSelected({
    action: position === 'top' ? 'list-top' : 'list-bottom',
  }),
  revealFirstSelected,
})
onBeforeUnmount(unregisterModListActions)

bindTargetReveal({ vListRef, visibleList, revealCollapsedSectionFor })
// 依赖线路数据
const lineData = computed(() => {
  return visibleList.value
})

const {
  // 拖拽状态
  listKey, isDragging,
  // 会话控制
  finishDragSession, dispatchSyntheticDragEnd, refreshVirtualList, cancelActiveDrag,
  // 拖拽入口
  startDrag, updateChildren,
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
  correctInterlockInsertIndex,
  normalizeId,
})

const focusContainer = (event) => {
  event.currentTarget.focus()
}
const handleDirectiveNavigate = (nextId, nextIndex, direction) => {
  const vList = vListRef.value
  if (vList) {
    const currentOffset = vList.getOffset()
    vList.scrollToOffset(currentOffset + (direction * itemHeight.value))
  }
}
const savePosition = () => {
  if (vListRef.value) {
    const offset = vListRef.value.getOffset()
    if (offset > 0) appStore.recordScroll(props.listId, offset)
  }
}
const restorePosition = () => {
  const savedOffset = appStore.getScroll(props.listId)
  if (savedOffset > 0 && vListRef.value) {
    nextTick(() => {
      setTimeout(() => {
        vListRef.value?.scrollToOffset(savedOffset)
      }, 30)
    })
  }
}
onBeforeUnmount(() => {
  if (isDragging.value) {
    finishDragSession({ suppressDrop: true })
    dispatchSyntheticDragEnd()
  }
  savePosition()
})
onMounted(() => {
  if (!appStore.isLoading) restorePosition()
})
watch(() => appStore.isLoading, async (loading) => {
  if (loading) {
    await cancelActiveDrag()
    savePosition()
  } else {
    await nextTick()
    restorePosition()
    useGuideStore()
  }
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
