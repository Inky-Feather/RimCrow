<template>
  <div data-tour="group-list-panel" class="flex flex-col h-full bg-bg-surface/40 shadow-2xl"
    :class="`border-2 rounded-2xl border-accent-${listColor}/20`">
    <!-- 标题栏 -->
    <div data-tour="group-list-header" :class="`px-3 h-8 border-b rounded-t-2xl border-border-base/5 flex justify-between items-center bg-accent-${listColor}/10`">
      <span :class="`text-sm font-bold text-accent-${listColor} uppercase tracking-wider flex items-center gap-2`">
        <div :class="`w-1.5 h-1.5 rounded-full bg-accent-${listColor} shadow-[0_0_8px_var(--color-accent-${listColor})]`"></div>
        {{ title }}
      </span>
      <span :class="`text-xs bg-bg-inset/70 px-2 py-0.5 rounded text-accent-${listColor}`">
        {{ safeGroupList.length }}
      </span>
    </div>
    <!-- 搜索栏 -->
    <div class="px-2 py-1 shadow-xl" >
      <div data-tour="group-list-search" class="w-full inline-flex items-center gap-1">
        <input type="text" placeholder="搜索分组名称、模组名称/包名/作者..." v-model="searchText" @keyup.enter="executeSearch(true)"
          :class="`flex-1 px-2 py-1 rounded-lg transition-all bg-bg-deep/30 border border-border-base/10 text-sm
          text-text-main placeholder:text-text-dim focus:border-accent-${listColor} focus:outline-none focus:bg-bg-deep/90 min-w-0`" />
        <!-- 定位按钮 -->
        <button @click="executeSearch(true)" v-tooltip="'搜索定位下一个符合条件的结果'"
          :class="`px-3 py-1 relative rounded-lg bg-accent-${listColor}/50 hover:bg-accent-${listColor}
          text-text-dim hover:text-text-main text-xs font-bold shadow-lg shadow-accent-${listColor}/10
          transition-all cursor-pointer hover:scale-105 active:scale-95`">定位
          <div v-if="currentSearchIndex !== -1 && searchText" class="text-[0.55rem] absolute -top-2 -left-1 text-text-main bg-accent-highlight px-1 rounded-lg">{{ currentSearchIndex + 1 }} / {{ searchResults.length }}</div>
        </button>
      </div>
      <!-- 操作按钮 -->
      <div data-tour="group-list-actions" class="mt-1 flex items-center justify-between">
        <div class="pointer-events-auto flex gap-1.5">
          <button @click="expandAll" v-tooltip="`展开全部分组`" :class="`px-1 py-1 rounded-lg bg-accent-${listColor}/50 hover:bg-accent-${listColor} text-text-dim hover:text-text-main text-xs font-bold shadow-lg shadow-accent-${listColor}/10 transition-all`" >
            <svg class="size-4" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M6 9L42 9" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/><path d="M6 19L42 19" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/><path d="M6 26L24 40L42 26" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/></svg>
          </button>
          <button @click="collapseAll" v-tooltip="`收拢全部分组`" :class="`px-1 py-1 rounded-lg bg-accent-${listColor}/50 hover:bg-accent-${listColor} text-text-dim hover:text-text-main text-xs font-bold shadow-lg shadow-accent-${listColor}/10 transition-all`">
            <svg class="size-4" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M6 10L42 10" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/><path d="M6 20L42 20" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/><path d="M6 40L24 26L42 40" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/></svg>
          </button>
          <button @click="createGroup" v-tooltip="`新建分组`" :class="`px-1 py-1 rounded-lg bg-accent-${listColor}/50 hover:bg-accent-${listColor} text-text-dim hover:text-text-main text-xs font-bold shadow-lg shadow-accent-${listColor}/10 transition-all`">
            <svg class="size-4" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M24.0605 10L24.0239 38" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/><path d="M10 24L38 24" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/></svg>
          </button>
        </div>
        <!-- 帮助按钮 -->
        <CircleQuestionMarkIcon data-tour="group-list-help" v-tooltip="groupHelpTooltip" :class="`size-5 text-text-dim hover:text-accent-${listColor} cursor-help transition-all`" />
      </div>
    </div>

    <!-- 列表区：统一由外层虚拟列表滚动，避免分组内嵌套滚动和拖拽事件互相干扰。 -->
    <div data-tour="group-list-body" class="relative flex-1 min-h-0 overflow-hidden pb-0.5 after:pointer-events-none
        after:content-[''] after:absolute after:bottom-0 after:w-full after:h-10
        after:bg-linear-to-t after:from-bg-deep/80 after:to-transparent">
      <div class="h-full min-h-0 px-1 relative" @click.self="modStore.clearSelection()">
        <div v-if="safeGroupList.length === 0" class="absolute flex rounded-lg top-0 bottom-0 left-0 right-0 m-1 items-center justify-center text-text-subtle/70 text-xs select-none pointer-events-none">
            可点击 “ + ” 按钮新建分组
        </div>

        <VirtualDragList :model-value="flatRows" :key="listKey" dataKey="row_key" :keeps="40" class="h-full p-1"
          wrapClass="min-h-full" ref="vListRef"
          :draggable="!appStore.isLoading" :droppable="!appStore.isLoading" :sortable="!appStore.isLoading"
          :disabled="appStore.isLoading"
          :delay="appStore.settings.ui.drag_delay"
          :get-drag-meta="getFlatRowDragMeta"
          :group="{ name: 'groups', pull:'clone', put: ['mods','groups'], revertDrag: true, canPut: canDropFlatRow }"
          :size="modRowHeight"
          @drop="handleFlatDrop" @drag="startDrag" @dragend="finishDragSession"
          v-selectable-list="selectionConfig">
          <template v-slot:item="{ record, index }">
            <GroupItem v-if="record.row_type === 'group'" class="h-full pt-1" :id="record.group_id" :key="record.row_key" :index="index" :groupData="record.group" :list-color="listColor"
              :expanded="expandedIds.has(record.group_id)" :isHighlight="currentSearchGroupId === record.group_id"
              @contextmenu="event => openGroupContextMenu(event, record)"
              @toggle="toggle" @delete-group="deleteGroup" @update-group="updateGroup">
            </GroupItem>

            <div v-else-if="record.row_type === 'mod'" class="relative group h-full pr-3 pl-3 transition-[opacity,transform,background-color] duration-180 ease-out"
              :class="[
                record.is_expanding ? 'group-row-expanding' : '',
                record.is_collapsing ? 'group-row-collapsing' : ''
              ]"
              :style="{ '--rgb-components': hexToRgb(record.group?.color), '--group-row-delay': `${Math.min(record.mod_index || 0, 8) * 10}ms` }">
              <div class="absolute left-1.5 -top-1 bottom-1 w-1 bg-[rgba(var(--rgb-components),0.6)]"></div>
              <div class="h-full" @contextmenu="event => openGroupModContextMenu(event, record)">
              <GroupModRow :item-id="record.id" :selection-id="record.row_key" :index="record.mod_index" :key="record.row_key" :list-color="listColor"
                :is-selected="selectedGroupRowKeySet.has(record.row_key)"
                :search-match="currentSearchGroupId === record.group_id && currentSearchModId === normalizeGroupModId(record.id)"
                :show-index="appStore.settings.ui.show_group_index"
                :show-icon="appStore.settings.ui.show_group_icon">
              </GroupModRow>
              </div>
              <!-- 右上角移除按钮（阻止冒泡，避免触发选择） -->
              <button @click.stop="removeMod(record.group_id, [record.id])" @mousedown.stop v-tooltip="`移除`"
                class="absolute top-1 right-3 w-4 h-4 bg-accent-danger text-text-main rounded-full
                      opacity-0 group-hover:opacity-80 transition-opacity duration-200
                      flex items-center justify-center text-xs z-10 hover:scale-110">×
              </button>
              <div v-if="activeCanonicalIds.has(normalizeGroupModId(record.id))" v-tooltip="'已启用'" tabindex="0" class="absolute w-3 h-3 m-1 bg-accent-success text-text-main rounded-full
                      transition-opacity duration-200 flex items-center justify-center text-xs z-10 hover:scale-110"
                      :class="[appStore.settings.ui.show_group_index?'-top-1.5 left-8.5':'-top-1.5 left-1.5']">
              </div>
              <div class="absolute right-1.5 -top-1 bottom-1 w-1 bg-[rgba(var(--rgb-components),0.6)]"></div>

            </div>
            <div v-else class="bg-[rgba(var(--rgb-components),0.3)] h-full py-1 mx-1 rounded-b-md transition-[opacity,transform] duration-180 ease-out"
              :class="[
                record.is_expanding ? 'group-row-expanding' : '',
                record.is_collapsing ? 'group-row-collapsing' : ''
              ]"
              :style="{ '--rgb-components': hexToRgb(record.group?.color), '--group-row-delay': '0ms' }">
              <div class="mx-2 h-full rounded-lg border-2 border-dashed text-text-subtle/70 text-xs bg-bg-deep/80 select-none pointer-events-none flex items-center justify-center transition-colors duration-150 ease-out"
                :class="record.is_collapsing ? '' : ''">
                可拖拽模组到此
                <!-- 点阵背景 -->
                <div class="absolute inset-0 opacity-[0.05] pointer-events-none" style="background-image: radial-gradient(var(--color-text-main) 1px, transparent 1px); background-size: 20px 20px;"></div>
              </div>
            </div>
          </template>
        </VirtualDragList>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch, nextTick, onBeforeUnmount } from 'vue'
import { useModStore } from './stores/modStore'
import { useGroupStore } from './stores/groupStore'
import { useContextMenuStore } from '../../shared/components/context-menu/contextMenuStore'
import { useConfirmStore } from '../../shared/components/modal/confirmStore'
import VirtualDragList from '../../shared/components/list/VirtualDragList.vue'
import GroupItem from './GroupItem.vue'
import GroupModRow from './GroupModRow.vue'
import { ChevronsDownUp, ChevronsUpDown, MessageSquareHeart, CircleCheckBig, CircleQuestionMarkIcon, CircleSlash2, CopyCheck, Crosshair, Eraser, FolderInput, Package } from 'lucide-vue-next';
import { useAppStore } from '../../app/stores/appStore';
import { hexToRgbComponents } from '../../shared/lib/color'
import { normalizePackageId } from './lib/modIdentity'
import { toast } from '../../shared/lib/common'

const props = defineProps({
  title: { type: String, default: 'Groups' },
  modelValue: { type: Array, default: () => [] },
  listColor: { type: String, default: 'primary' } // danger/highlight/special/cool/primary/success/tip/warn/secondary/warning
})

const appStore = useAppStore()
const modStore = useModStore()
const groupStore = useGroupStore()
const menuStore = useContextMenuStore()
const confirmStore = useConfirmStore()

const vListRef = ref(null)
const listKey = ref(0)
const isDragging = ref(false)
const expandingIds = ref(new Set<string>())
const collapsingIds = ref(new Set<string>())
const expandTimers = new Map<string, number>()
const collapseTimers = new Map<string, number>()

type GroupSearchResult = {
  groupId: string,
  modId: string,
  matchType: 'group' | 'mod'
}

// 搜索文本
const searchText = ref('')
const oldSearchText = ref('')
const searchResults = ref<GroupSearchResult[]>([])
const currentSearchIndex = ref(-1)
const currentSearchGroupId = ref('')
const currentSearchModId = ref('')
const highlightTimer = ref<number>()
const activeSelectionGroupId = ref('')

const modRowHeight = computed(() => appStore.scalePx(30)+4)
// 分组面板不需要和主列表依赖线对齐，所以标题行可以拥有独立高度。
// 这部分空间专门留给“分组之间的视觉间隔”，不要挤占普通模组项行高。
const groupRowHeight = computed(() => appStore.scalePx(38))
const normalizeGroupModId = (value: string) => normalizePackageId(value)
const hexToRgb = hexToRgbComponents

const isValidGroupRecord = (item: any) => {
  return !!item && typeof item.group_id === 'string' && item.group_id.trim().length > 0
}
const safeGroupList = computed(() => props.modelValue.filter(item => isValidGroupRecord(item)))
// 用 Set 存储所有被展开的 ID
const expandedIds = computed(() => new Set(safeGroupList.value.filter(item => item.is_expanded).map(item => item.group_id)))
const visualExpandedIds = computed(() => new Set([...expandedIds.value, ...expandingIds.value, ...collapsingIds.value]))
const selectedCanonicalIds = computed(() => new Set(
  (modStore.selectedIds || []).map(id => normalizeGroupModId(id)).filter(Boolean)
))
const activeCanonicalIds = computed(() => new Set(
  (modStore.activeIds || []).map(id => normalizeGroupModId(id)).filter(Boolean)
))

// 外层虚拟列表使用扁平 row 流表达嵌套结构：
// group 行负责分组自身排序；mod 行负责组内排序和跨分组复制；empty 行负责空分组投放。
const flatRows = computed(() => {
  const rows = []
  safeGroupList.value.forEach(group => {
    const modIds = Array.isArray(group?.mod_ids) ? group.mod_ids.map(normalizeGroupModId).filter(Boolean) : []
    rows.push({
      row_key: `group:${group.group_id}`,
      row_type: 'group',
      id: group.group_id,
      group_id: group.group_id,
      group,
      mod_ids: modIds,
      dragGroup: 'groups',
      dragLabel: group?.name || '分组',
      rowSize: groupRowHeight.value,
    })
    if (!visualExpandedIds.value.has(group.group_id)) return
    const isExpanding = expandingIds.value.has(group.group_id) && expandedIds.value.has(group.group_id)
    const isCollapsing = collapsingIds.value.has(group.group_id) && !expandedIds.value.has(group.group_id)
    if (modIds.length === 0) {
      rows.push({
        row_key: `empty:${group.group_id}`,
        row_type: 'empty',
        id: `empty:${group.group_id}`,
        group_id: group.group_id,
        group,
        draggable: false,
        is_expanding: isExpanding,
        is_collapsing: isCollapsing,
        rowSize: modRowHeight.value,
      })
      return
    }
    modIds.forEach((id, modIndex) => {
      rows.push({
        row_key: `mod:${group.group_id}:${id}`,
        row_type: 'mod',
        id,
        group_id: group.group_id,
        group,
        mod_index: modIndex,
        dragGroup: 'mods',
        dragLabel: id,
        is_expanding: isExpanding,
        is_collapsing: isCollapsing,
        rowSize: modRowHeight.value,
      })
    })
  })
  return rows
})
const flatSelectableRows = computed(() => flatRows.value.filter(row => row.row_type === 'mod'))
const flatSelectableRowKeys = computed(() => flatSelectableRows.value.map(row => row.row_key))
const selectableRowKeyToModId = computed(() => new Map(
  flatSelectableRows.value.map(row => [row.row_key, row.id])
))
const selectableRowKeyToGroupId = computed(() => new Map(
  flatSelectableRows.value.map(row => [row.row_key, row.group_id])
))
const selectedGroupRowKeys = computed(() => {
  const selectedIds = selectedCanonicalIds.value
  return flatSelectableRows.value
    .filter(row => (!activeSelectionGroupId.value || row.group_id === activeSelectionGroupId.value) && selectedIds.has(normalizeGroupModId(row.id)))
    .map(row => row.row_key)
})
const selectedGroupRowKeySet = computed(() => new Set(selectedGroupRowKeys.value))
const resolveRowKeyGroupId = (rowKey?: string | null) => {
  return rowKey ? (selectableRowKeyToGroupId.value.get(rowKey) || '') : ''
}
const resolveSelectedRowKeys = (rowKeys: string[] = [], anchorRowKey?: string | null) => {
  // vSelection 需要唯一 ID 计算连续区间；分组允许同一模组出现在多个分组，所以不能直接用包名做行坐标。
  // 这里把唯一 row_key 还原为真实模组 ID，再交给 modStore，保持“选中的是模组”这条全局业务语义不变。
  const scopeGroupId = resolveRowKeyGroupId(anchorRowKey) || activeSelectionGroupId.value
  activeSelectionGroupId.value = scopeGroupId
  const previousRowKeys = new Set(selectedGroupRowKeys.value)
  const nextRowKeys = new Set(rowKeys)
  const removedAnchorId = previousRowKeys.has(String(anchorRowKey)) && !nextRowKeys.has(String(anchorRowKey))
    ? normalizeGroupModId(selectableRowKeyToModId.value.get(String(anchorRowKey)))
    : ''
  const ids: string[] = []
  const seen = new Set<string>()
  rowKeys.forEach(rowKey => {
    if (scopeGroupId && resolveRowKeyGroupId(rowKey) !== scopeGroupId) return
    const id = normalizeGroupModId(selectableRowKeyToModId.value.get(rowKey))
    // 同一模组可能在多个分组各出现一次。用户 Ctrl 取消其中一个副本时，业务上应取消这个模组本身，
    // 所以需要把所有同包名副本一起排除，否则其它副本的 row_key 会把它重新带回选中集合。
    if (!id || id === removedAnchorId || seen.has(id)) return
    seen.add(id)
    ids.push(id)
  })
  return ids
}
const resolveSelectionAnchor = (rowKey?: string | null) => {
  const id = normalizeGroupModId(rowKey ? selectableRowKeyToModId.value.get(rowKey) : '')
  return id || null
}
const selectionConfig = computed(() => ({
  // 配置对象集中在 computed 中，避免模板每次渲染都创建新对象。
  // vSelection 内部还会按 data 内容做二次保护，只有行顺序变化才重建索引表。
  data: flatSelectableRowKeys.value,
  selectedIds: selectedGroupRowKeys.value,
  onSelect: (rowKeys, anchor) => modStore.selectMods(resolveSelectedRowKeys(rowKeys, anchor), resolveSelectionAnchor(anchor)),
  onClear: () => {
    activeSelectionGroupId.value = ''
    modStore.clearSelection()
  },
  clickClass: 'select-trigger',
  swipeClass: 'swipe-trigger',
  getItemScope: rowKey => resolveRowKeyGroupId(rowKey),
  selectAllRequiresScope: true,
}))

// 获取下一个搜索结果索引
const getNextSearchIndex = (currentIndex: number, resultCount: number, forward: boolean) => {
  if (!Number.isInteger(resultCount) || resultCount <= 0) return -1
  const safeCurrentIndex = Number.isInteger(currentIndex) ? currentIndex : -1
  if (forward) {
    return (safeCurrentIndex + 1 + resultCount) % resultCount
  }
  if (safeCurrentIndex < 0) {
    return resultCount - 1
  }
  return (safeCurrentIndex - 1 + resultCount) % resultCount
}

const normalizeSearchText = (value: unknown) => String(value ?? '').trim().toLowerCase()
const isTextMatch = (value: unknown, query: string) => {
  if (!query) return false
  return normalizeSearchText(value).includes(query)
}
const buildSearchResults = (rawQuery: string) => {
  const query = normalizeSearchText(rawQuery)
  if (!query) return []
  const groupHits: GroupSearchResult[] = []
  const modHits: GroupSearchResult[] = []
  safeGroupList.value.forEach(group => {
    if (isTextMatch(group?.name, query)) {
      groupHits.push({ groupId: group.group_id, modId: '', matchType: 'group' })
    }
    const modIds = Array.isArray(group?.mod_ids) ? group.mod_ids : []
    modIds.forEach(modId => {
      const normalizedModId = normalizePackageId(modId)
      if (!normalizedModId) return
      const mod = modStore.takeModById(normalizedModId)
      const matches = [
        mod?.alias_name,
        mod?.display_name,
        mod?.name,
        mod?.package_id
      ].some(value => isTextMatch(value, query))
      if (!matches) return
      modHits.push({ groupId: group.group_id, modId: normalizedModId, matchType: 'mod' })
    })
  })
  return modHits.length > 0 ? [...modHits, ...groupHits] : groupHits
}

// 分组帮助提示
const groupHelpTooltip = computed(() => {
  return `**分组管理说明：**
支持直接将 Mod 从列表中拖拽至任意分组。
在列表上点击右键，可通过菜单快速将 Mod 移入或移出已有分组。
在 Mod 详情页面，可统一管理该 Mod 所属的所有分组。

分组功能类似剪贴板，移入、移出分组均为[[复制]]操作：
 - 无法通过^^移出^^分组来移除 Mod；
 - 分组之间拖拽 Mod 会执行[[复制]]，并自动跳过目标分组已有成员。

分组支持整体拖拽操作：
 - 将分组整体拖入启用列表，可一次性启用该分组下所有 Mod；
 - 将分组整体拖入停用列表，可一次性停用该分组下所有 Mod。`
})

const executeSearch = async (forward: boolean) => {
  if (!searchText.value) return
  // 搜索文本改变时更新结果
  if (searchText.value !== oldSearchText.value) {
    searchResults.value = buildSearchResults(searchText.value)
    currentSearchIndex.value = -1
  }
  // 搜索无结果时直接退出，避免出现 NaN 索引
  if (searchResults.value.length === 0) {
    currentSearchIndex.value = -1
    currentSearchGroupId.value = ''
    currentSearchModId.value = ''
    oldSearchText.value = searchText.value
    return
  }
  currentSearchIndex.value = getNextSearchIndex(currentSearchIndex.value, searchResults.value.length, forward)
  if (currentSearchIndex.value === -1) return
  const currentResult = searchResults.value[currentSearchIndex.value]
  currentSearchGroupId.value = currentResult.groupId
  currentSearchModId.value = currentResult.modId || ''
  if (currentResult.matchType === 'mod' && !expandedIds.value.has(currentResult.groupId)) {
    await groupStore.updateGroup(currentResult.groupId, { is_expanded: true })
    await nextTick()
  }
  const rowKey = currentResult.modId
    ? `mod:${currentResult.groupId}:${currentResult.modId}`
    : `group:${currentResult.groupId}`
  const index = flatRows.value.findIndex(item => item.row_key === rowKey)
  if (index !== -1) {
    setTimeout(() => {
      const scrollOptions = appStore.settings.ui.smooth_list_target_scroll !== false ? { behavior: 'smooth' } : {}
      vListRef.value?.scrollToIndex?.(index, scrollOptions)
    }, 50)
    if (highlightTimer.value) {
      clearTimeout(highlightTimer.value)
    }
    highlightTimer.value = setTimeout(() => {
      currentSearchGroupId.value = ''
      currentSearchModId.value = ''
    }, 2000)
  }
  oldSearchText.value = searchText.value
}

const stopCollapseTimer = (id: string) => {
  const timer = collapseTimers.get(id)
  if (timer) {
    clearTimeout(timer)
    collapseTimers.delete(id)
  }
}
const stopExpandTimer = (id: string) => {
  const timer = expandTimers.get(id)
  if (timer) {
    clearTimeout(timer)
    expandTimers.delete(id)
  }
}
const clearExpandingId = (id: string) => {
  stopExpandTimer(id)
  const next = new Set(expandingIds.value)
  next.delete(id)
  expandingIds.value = next
}
const animateExpandedRows = (ids: string[]) => {
  const next = new Set(expandingIds.value)
  ids.forEach(id => {
    stopExpandTimer(id)
    next.add(id)
    const timer = window.setTimeout(() => clearExpandingId(id), 220)
    expandTimers.set(id, timer)
  })
  expandingIds.value = next
}
const clearCollapsingId = (id: string) => {
  stopCollapseTimer(id)
  const next = new Set(collapsingIds.value)
  next.delete(id)
  collapsingIds.value = next
}
const keepRowsDuringCollapse = (ids: string[]) => {
  const next = new Set(collapsingIds.value)
  ids.forEach(id => {
    stopCollapseTimer(id)
    next.add(id)
    const timer = window.setTimeout(() => clearCollapsingId(id), 180)
    collapseTimers.set(id, timer)
  })
  collapsingIds.value = next
}

// 切换分组展开状态。收拢时先保留子行一小段时间，让虚拟列表有机会播放离场动画。
const toggle = async (id: string) => {
  if (expandedIds.value.has(id)) {
    clearExpandingId(id)
    keepRowsDuringCollapse([id])
    await groupStore.updateGroup(id, { is_expanded: false })
  } else {
    clearCollapsingId(id)
    await groupStore.updateGroup(id, { is_expanded: true })
    animateExpandedRows([id])
  }
}

// 全部展开
const expandAll = async () => {
  collapseTimers.forEach(timer => clearTimeout(timer))
  collapseTimers.clear()
  collapsingIds.value = new Set()
  await groupStore.changeAllGroupExpansion(true);
  animateExpandedRows(safeGroupList.value.map(group => group.group_id).filter(Boolean))
}

// 全部折叠
const collapseAll = async () => {
  expandTimers.forEach(timer => clearTimeout(timer))
  expandTimers.clear()
  expandingIds.value = new Set()
  keepRowsDuringCollapse([...expandedIds.value])
  await groupStore.changeAllGroupExpansion(false);
}

// 新建分组
const createGroup = async () => {
  await groupStore.createGroup();
}
// 删除分组
const deleteGroup = async (groupId: string, event?: Event) => {
  const group = groupStore.takeGroupById(groupId)
  const ok = await confirmStore.open({
    title: '删除分组',
    message: `确定要删除分组「${group?.name || '未命名分组'}」吗？\n分组记录会被移除，模组文件不会删除。`,
    mode: 'confirm',
    type: 'error',
    confirmText: '删除',
  }, event)
  if (!ok) return
  groupStore.deleteGroup(groupId);
}
// 更新分组信息
const updateGroup = (groupId: string, data = {}) => {
  groupStore.updateGroup(groupId, data);
}
// 移除模组
const removeMod =(groupId: string, modId: Array<string>) => {
  groupStore.groupRemoveMods(groupId, modId);
}

const finishDragSession = () => {
  isDragging.value = false
  groupStore.isDraggingGroup = false
  modStore.isDraggingMod = false
}
const cancelActiveDrag = async () => {
  if (!isDragging.value) return
  finishDragSession()
  await nextTick()
  listKey.value += 1
}
const startDrag = (e) => {
  isDragging.value = true
  groupStore.isDraggingGroup = e?.item?.row_type === 'group'
  modStore.isDraggingMod = e?.item?.row_type === 'mod'
}

const resolveMovingModIds = (draggedId = '') => {
  const normalizedDraggedId = normalizeGroupModId(draggedId)
  const selectedIds = [...new Set((modStore.selectedIds || []).map(normalizeGroupModId).filter(Boolean))]
  if (!normalizedDraggedId) return selectedIds
  if (!selectedIds.includes(normalizedDraggedId)) return [normalizedDraggedId]
  return selectedIds
}

const getGroupModCount = (groupId: string) => {
  const group = groupStore.takeGroupById(groupId)
  return Array.isArray(group?.mod_ids) ? group.mod_ids.length : 0
}
const getNormalizedGroupModIds = (group = {}) => (
  Array.isArray(group?.mod_ids) ? [...new Set(group.mod_ids.map(normalizeGroupModId).filter(Boolean))] : []
)
const resolveContextModIds = (clickedId = '', groupId = '') => {
  const normalizedClickedId = normalizeGroupModId(clickedId)
  const selectedIds = [...new Set((modStore.selectedIds || []).map(normalizeGroupModId).filter(Boolean))]
  if (!normalizedClickedId) return selectedIds
  if (groupId && activeSelectionGroupId.value && activeSelectionGroupId.value !== groupId) return [normalizedClickedId]
  return selectedIds.includes(normalizedClickedId) ? selectedIds : [normalizedClickedId]
}
const selectContextIds = async (ids: string[] = [], groupId = '') => {
  const normalizedIds = [...new Set(ids.map(normalizeGroupModId).filter(Boolean))]
  if (normalizedIds.length === 0) return []
  activeSelectionGroupId.value = groupId || activeSelectionGroupId.value
  modStore.selectMods(normalizedIds)
  await nextTick()
  return normalizedIds
}
const locateModInMainLists = (id = '') => {
  const normalizedId = normalizeGroupModId(id)
  if (!normalizedId) return
  modStore.currentTargetId = normalizedId
}
const openCustomExport = (ids: string[], title: string, description: string) => {
  appStore.openCustomModExportDialog({
    title,
    description,
    modIds: [...ids],
    summary: `共 ${ids.length} 个模组，导出时会自动按当前激活版本或最新版本解析共存项。`,
  })
}
const openRecommendationExport = (ids: string[]) => {
  const countText = ids.length > 1 ? ` (${ids.length}项)` : ''
  // 分组面板的推荐导出只沿用当前右键选中的模组，不把“分组本身”当成导出对象。
  appStore.openRecommendationExportDialog({
    title: `推荐导出已选模组${countText}`,
    sourceName: '已选模组',
    modIds: [...ids],
  })
}
const buildGroupModMenuItems = ({ ids, clickedId, groupId, groupName, groupSize = 0 }) => {
  const countText = ids.length > 1 ? ` (${ids.length}项)` : ''
  const clickedMod = modStore.takeModById(clickedId)
  return [
    { label: '启用' + countText, icon: CircleCheckBig, disabled: ids.length === 0, action: () => modStore.changeModsActive(ids, true) },
    { label: '停用' + countText, icon: CircleSlash2, disabled: ids.length === 0, action: () => modStore.changeModsActive(ids, false) },
    { divider: true },
    { label: '定位到主列表', icon: Crosshair, disabled: !clickedId, action: () => locateModInMainLists(clickedId) },
    { label: '打开文件夹', icon: FolderInput, disabled: !clickedMod?.path, action: () => appStore.openPath(clickedMod.path) },
    { divider: true },
    { label: expandedIds.value.has(groupId) ? '收缩分组' : '展开分组', icon: expandedIds.value.has(groupId) ? ChevronsDownUp : ChevronsUpDown, action: () => toggle(groupId) },
    { label: '选中整组', icon: CopyCheck, disabled: !groupId || groupSize === 0, action: async () => {
      const group = groupStore.takeGroupById(groupId)
      await selectContextIds(getNormalizedGroupModIds(group), groupId)
    }},
    // 推荐导出关注介绍信息；打包导出关注实际文件，两者在菜单里分开呈现。
    { label: '推荐导出' + countText, icon: MessageSquareHeart, disabled: ids.length === 0, action: () => openRecommendationExport(ids) },
    { label: '打包导出' + countText, icon: Package, disabled: ids.length === 1, action: () => openCustomExport(ids, `打包导出分组模组${countText}`, `来源分组：${groupName || '未命名分组'}。`) },
    { label: `从「${groupName || '分组'}」移除` + countText, icon: Eraser, level: 'warn', disabled: ids.length === 0 || !groupId, action: () => groupStore.groupRemoveMods(groupId, ids) },

  ]
}
const openGroupModContextMenu = async (event, row) => {
  event.preventDefault()
  event.stopPropagation()
  const clickedId = normalizeGroupModId(row?.id)
  const ids = await selectContextIds(resolveContextModIds(clickedId, row?.group_id), row?.group_id)
  const groupIds = getNormalizedGroupModIds(row?.group)
  modStore.lastSelectedMod = modStore.takeModById(clickedId)
  menuStore.open(event, buildGroupModMenuItems({
    ids,
    clickedId,
    groupId: row?.group_id,
    groupName: row?.group?.name,
    groupSize: groupIds.length,
  }))
}
const openGroupContextMenu = async (event, row) => {
  event.preventDefault()
  event.stopPropagation()
  const group = row?.group || groupStore.takeGroupById(row?.group_id)
  const ids = await selectContextIds(getNormalizedGroupModIds(group), row?.group_id)
  const groupName = group?.name || '未命名分组'
  menuStore.open(event, [
    { label: `启用整组 (${ids.length}项)`, icon: CircleCheckBig, disabled: ids.length === 0, action: () => modStore.changeModsActive(ids, true) },
    { label: `停用整组 (${ids.length}项)`, icon: CircleSlash2, disabled: ids.length === 0, action: () => modStore.changeModsActive(ids, false) },
    { divider: true },
    { label: expandedIds.value.has(row?.group_id) ? '收缩分组' : '展开分组', icon: expandedIds.value.has(row?.group_id) ? ChevronsDownUp : ChevronsUpDown, action: () => toggle(row.group_id) },
    { label: '打包整组', icon: Package, disabled: ids.length === 0, action: () => openCustomExport(ids, `打包导出分组: ${groupName}`, '可按需附带依赖、联锁项和语言包。') },
    { label: '推荐整组', icon: MessageSquareHeart, disabled: ids.length === 0, action: () => openRecommendationExport(ids) },
    { divider: true },
    { label: '清空分组', icon: Eraser, level: 'danger', disabled: ids.length === 0, action: async () => {
      const ok = await confirmStore.confirmAction(
        '清空分组模组',
        `确定要从「${groupName}」移除全部 ${ids.length} 个模组吗？\n只会清空分组内容，不会删除模组文件。`,
        { type: 'error', confirmText: '清空' }
      )
      if (ok) await groupStore.groupRemoveMods(row.group_id, ids)
    } },
  ], { groupId: row?.group_id })
}
const getFlatRowDragMeta = (row) => {
  // 多选数量只影响拖拽虚影，不应该写进 flatRows。
  // 否则每次选择变化都会重建整个分组虚拟列表，展开多个大分组时滚动会明显变重。
  if (row?.row_type === 'group') {
    return {
      dragCount: Math.max(1, getGroupModCount(row.group_id)),
      dragLabel: row.group?.name || '分组',
    }
  }
  if (row?.row_type === 'mod') {
    const id = normalizeGroupModId(row.id)
    const count = selectedCanonicalIds.value.has(id) ? selectedCanonicalIds.value.size : 1
    return {
      dragCount: Math.max(1, count),
      dragLabel: row.id,
    }
  }
  return {}
}

const canDropFlatRow = (session, targetRow, index: number) => {
  if (session?.sourceGroup !== 'groups') return true
  // 分组整体只能在分组标题之间排序，不能落入某个分组内部；底部空白允许表示“移动到最后”。
  if (index >= flatRows.value.length) return true
  return targetRow?.row_type === 'group'
}

const resolveDropPosition = (newIndex: number, options: { preferPreviousGroupGap?: boolean } = {}) => {
  const rows = flatRows.value
  const nextRow = rows[Math.max(0, Math.min(newIndex, rows.length - 1))]
  const prevRow = rows[newIndex - 1]
  if (!nextRow && prevRow?.group_id) {
    return { groupId: prevRow.group_id, index: getGroupModCount(prevRow.group_id) }
  }
  const targetRow = nextRow || prevRow
  if (!targetRow) return { groupId: '', index: 0 }
  if (targetRow.row_type === 'group') {
    // 模组落在两个分组之间的间隙时，用户更容易理解为“放到上一个分组末尾”；
    // 分组自身排序仍保留“标题前插入”的语义，因此通过参数区分。
    if (options.preferPreviousGroupGap && prevRow?.group_id && prevRow.group_id !== targetRow.group_id) {
      return { groupId: prevRow.group_id, index: getGroupModCount(prevRow.group_id) }
    }
    return { groupId: targetRow.group_id, index: 0 }
  }
  if (targetRow.row_type === 'empty') return { groupId: targetRow.group_id, index: 0 }
  if (nextRow?.row_type === 'mod') return { groupId: nextRow.group_id, index: nextRow.mod_index }
  if (prevRow?.row_type === 'mod') return { groupId: prevRow.group_id, index: prevRow.mod_index + 1 }
  return { groupId: targetRow.group_id, index: 0 }
}

const resolveGroupInsertIndex = (sourceGroupId: string, newIndex: number) => {
  const groupIds = safeGroupList.value.map(group => group.group_id).filter(Boolean)
  const nextIds = groupIds.filter(id => id !== sourceGroupId)
  // 拖到虚拟列表总高度以下时，明确表示插入到分组列表最底部。
  // 这里不能再向上寻找“下一个 group 行”，否则最后一个展开分组下面会无法排序到末尾。
  if (newIndex >= flatRows.value.length) return nextIds.length
  const nextGroupRow = flatRows.value.slice(newIndex).find(row => row.row_type === 'group')
  if (!nextGroupRow) return nextIds.length
  const targetIndex = nextIds.indexOf(nextGroupRow.group_id)
  return targetIndex === -1 ? nextIds.length : targetIndex
}

const reorderGroupsByDrop = async (sourceGroupId: string, newIndex: number) => {
  const groupIds = safeGroupList.value.map(group => group.group_id).filter(Boolean)
  if (!sourceGroupId || !groupIds.includes(sourceGroupId)) return
  const nextIds = groupIds.filter(id => id !== sourceGroupId)
  const targetIndex = resolveGroupInsertIndex(sourceGroupId, newIndex)
  nextIds.splice(targetIndex, 0, sourceGroupId)
  await groupStore.groupReorder(nextIds)
}

const copyOrReorderGroupMods = async (sourceRow, newIndex: number) => {
  const target = resolveDropPosition(newIndex, { preferPreviousGroupGap: true })
  if (!target.groupId) return
  const targetGroup = groupStore.takeGroupById(target.groupId)
  if (!targetGroup) return
  const movingIds = resolveMovingModIds(sourceRow.id)
  if (movingIds.length === 0) return
  const targetIds = (targetGroup.mod_ids || []).map(normalizeGroupModId).filter(Boolean)
  const movingSet = new Set(movingIds)
  const baseIds = sourceRow.group_id === target.groupId
    ? targetIds.filter(id => !movingSet.has(id))
    : [...targetIds]
  const insertIndex = Math.max(0, Math.min(target.index, baseIds.length))
  const idsToInsert = sourceRow.group_id === target.groupId
    ? movingIds
    : movingIds.filter(id => !baseIds.includes(id))
  const skippedCount = movingIds.length - idsToInsert.length
  if (idsToInsert.length === 0) {
    if (skippedCount > 0) toast.info(`目标分组已包含 ${skippedCount} 个模组，已跳过`)
    return
  }
  const nextIds = [...baseIds]
  nextIds.splice(insertIndex, 0, ...idsToInsert)
  await groupStore.groupContentReorder(target.groupId, nextIds)
  if (sourceRow.group_id !== target.groupId) {
    const targetName = targetGroup.name || '未命名分组'
    const suffix = skippedCount > 0 ? `，跳过 ${skippedCount} 个重复项` : ''
    toast.info(`已复制 ${idsToInsert.length} 项到「${targetName}」${suffix}`)
  }
}

const handleFlatDrop = async (e) => {
  finishDragSession()
  const item = e?.item
  if (!item || appStore.isLoading) return
  if (item.row_type === 'group') {
    // 分组整体排序按“用户看到的标题落点”处理。
    // 展开分组时标题下面会有子行，若使用删除源行后的 newIndex，可能会把目标标题前后的语义换错。
    await reorderGroupsByDrop(item.group_id, e.visualIndex ?? e.newIndex)
    return
  }
  if (item.row_type === 'mod' || item.id) {
    // 组内模组排序按实际插入点处理；VirtualDragList 已经修正了同列表向下拖拽时的索引左移。
    await copyOrReorderGroupMods(item, e.newIndex)
  }
}

watch(() => appStore.isLoading, async (loading) => {
  if (loading) {
    await cancelActiveDrag()
  }
})

onBeforeUnmount(() => {
  if (isDragging.value) {
    finishDragSession()
  }
  if (highlightTimer.value) {
    clearTimeout(highlightTimer.value)
  }
  expandTimers.forEach(timer => clearTimeout(timer))
  expandTimers.clear()
  collapseTimers.forEach(timer => clearTimeout(timer))
  collapseTimers.clear()
})
</script>

<style scoped>
.group-row-expanding {
  animation: group-row-expand 180ms cubic-bezier(0.16, 1, 0.3, 1);
  animation-delay: var(--group-row-delay, 0ms);
  animation-fill-mode: both;
  transform-origin: top center;
  will-change: opacity, transform;
}
.group-row-collapsing {
  opacity: 0;
  transform: translateY(-0.25rem) scaleY(0.96);
  transform-origin: top center;
  will-change: opacity, transform;
}
@keyframes group-row-expand {
  from {
    opacity: 0;
    transform: translateY(-0.35rem) scaleY(0.94);
  }
  to {
    opacity: 1;
    transform: translateY(0) scaleY(1);
  }
}
</style>
