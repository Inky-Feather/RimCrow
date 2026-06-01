<template>
  <CommonModalShell :show="appStore.uiState.showFileSearchWorkbench" title="文件内容搜索" size="custom" :z-index="120" accent="primary"
    panel-class="h-19/20 w-19/20 border-accent-primary/18" content-class="h-full flex flex-col"
    @close="fileSearchStore.closeWorkbench()" >
        <template #icon>
          <Search class="size-5" />
        </template>

        <div class=" bg-bg-muted relative z-10 px-4 py-3">
          <div class="flex items-center gap-2">
            <div class="max-w-1/3">
              <CommonSelect v-model="fileSearchStore.form.scope" :options="scopeOptions" label="范围:" mini />
            </div>
            <div class="text-xs mx-1.5">
              <label class="flex items-center gap-1 whitespace-nowrap">
                <input :checked="fileSearchStore.form.use_regex" type="checkbox" class="size-3.5 rounded border border-border-base/18 bg-bg-muted/70 accent-accent-primary"
                  @change="fileSearchStore.form.use_regex = $event.target.checked" >
                正则表达式
              </label>
              <label class="inline-flex items-center gap-1 whitespace-nowrap">
                <input :checked="fileSearchStore.form.case_sensitive" type="checkbox" class="size-3.5 rounded border border-border-base/18 bg-bg-muted/70 accent-accent-primary"
                  @change="fileSearchStore.form.case_sensitive = $event.target.checked" >
                大小写敏感
              </label>
            </div>
            <input ref="queryInputRef" v-model="fileSearchStore.form.query" type="text" placeholder="输入搜索词或正则表达式进行搜索"
              class="h-10 min-w-0 flex-1 rounded-xl border border-border-base/10 bg-bg-inset/70 px-3 text-sm text-text-main outline-none transition-all focus:border-accent-primary/45 focus:shadow-[0_0_0_1px_rgba(var(--rgb-accent-primary),0.25)]"
              @keydown.enter.prevent="fileSearchStore.startSearch()" >

            <button v-show="!fileSearchStore.isBusy" class="flex shrink-0 px-2 py-1.5 items-center justify-center gap-2 rounded-xl bg-accent-primary text-sm font-black text-on-accent-primary transition-colors hover:bg-accent-primary/85 disabled:cursor-not-allowed disabled:opacity-55"
              :disabled="fileSearchStore.isBusy" @click="fileSearchStore.startSearch()" >
              <Search class="size-4" />搜索
            </button>
            <button v-show="fileSearchStore.isRunning" class="flex shrink-0 px-2 py-1.5 items-center justify-center gap-2 rounded-xl border border-accent-danger/28 bg-accent-danger/10 text-sm font-bold text-accent-danger transition-colors hover:bg-accent-danger/16 disabled:cursor-not-allowed disabled:opacity-45"
              :disabled="!fileSearchStore.isRunning" @click="fileSearchStore.cancelSearch()" >
              <Square class="size-3.5" />取消
            </button>
          </div>

          <div class="mt-2 flex items-center gap-x-4 ml-1 text-xs text-text-dim">
            <div class="flex items-center gap-3">
              <label class="inline-flex items-center gap-1 whitespace-nowrap" v-tooltip="'部分模组会按照游戏版本或DLC加载不同的文件，开启后仅会搜索当前有效的文件'">
                <input class="size-3.5 rounded border border-border-base/18 bg-bg-muted/70 accent-accent-primary"
                  :checked="fileSearchStore.form.effective_only" type="checkbox" @change="fileSearchStore.form.effective_only = $event.target.checked" >
                  只限当前有效文件
              </label>
              <label class="inline-flex items-center gap-1 whitespace-nowrap" v-tooltip="'仅搜索 XML 文件'">
                <input class="size-3.5 rounded border border-border-base/18 bg-bg-muted/70 accent-accent-primary"
                  :checked="isFileTypeEnabled('.xml')" type="checkbox" @change="toggleFileType('.xml')" >
                XML 文件
              </label>
            </div>

            <div class="flex items-center gap-1 whitespace-nowrap">
              <span class="text-text-dim" v-tooltip="'可自定义搜索限定文件，直接输入文件后缀名即可.号表示全部文件，多文件类型可用英文,;|号分割'">限定文件类型：</span>
              <input :value="fileSearchStore.form.custom_file_types_text" type="text" class="input-glass h-8 min-w-80 px-3 text-sm text-text-main outline-none"
                placeholder="例如 cs, txt; json | yaml，输入 . 表示全部文件"
                @input="fileSearchStore.setCustomFileTypesText($event.target.value)" >
            </div>

            <div class="flex flex-wrap items-center gap-3">
              <label v-for="option in excludeOptions" :key="option.key" class="inline-flex items-center gap-1 whitespace-nowrap" v-tooltip="option.desc" >
                <input :checked="isExcludeEnabled(option.key)" type="checkbox" class="size-3.5 rounded border border-border-base/18 bg-bg-muted/70 accent-accent-cool"
                  @change="toggleExcludeOption(option.key)" >
                {{ option.label }}
              </label>
            </div>
          </div>
          
        </div>

        <div class="relative z-10 flex min-h-0 flex-1 flex-col px-4 py-3">

          <div class="modal-section min-h-0 flex-1 overflow-hidden rounded-md">
            <div class="grid h-full min-h-0 grid-cols-[390px_minmax(0,1fr)]">
              <div class="sidebar-surface flex min-h-0 flex-col overflow-hidden">
                <!-- 搜索结果筛选 -->
                <div class="flex gap-1.5 items-center justify-between bg-bg-surface px-3 py-2 shadow-md/30">
                  <div class="text-sm font-black uppercase tracking-[0.18em] text-text-disabled">搜索结果</div>
                  <input v-model="fileSearchStore.resultFilter" type="text" placeholder="筛选模组、文件名、路径、命中内容" class="input-glass h-8 min-w-0 flex-1 px-3 text-sm text-text-main outline-none" >
                  <span class="rounded-full border border-border-base/10 bg-bg-overlay/5 px-2 py-0.5 text-xs text-text-dim">
                    {{ fileSearchStore.filteredResults.length }} / {{ fileSearchStore.results.length }}
                  </span>
                </div>

                <div v-if="flatRows.length === 0" class="flex h-full items-center justify-center px-6 text-center text-sm text-text-dim">
                  <div>
                    <div class="text-base font-bold text-text-soft">{{ emptyTitle }}</div>
                    <div class="mt-2 leading-6">{{ emptyDescription }}</div>
                  </div>
                </div>

                <div v-else class="relative min-h-0 flex-1 bg-bg-inset overflow-hidden">
                  <RecycleScroller ref="treeScrollerRef" :items="flatRows" key-field="id" :item-size="TREE_ROW_HEIGHT" class="h-full custom-scrollbar" >
                    <template #default="{ item }">
                      <button v-if="item.type === 'mod'" class="flex h-8 w-full items-center gap-1 px-2 bg-bg-surface/40 text-left text-sm transition-colors hover:brightness-125"
                        @click="toggleMod(item.group.id)" @contextmenu="openModMenu($event, item.group)" >
                        <component :is="isExpandedMod(item.group.id) ? ChevronDown : ChevronRight" class="size-3.5 shrink-0 text-text-dim" />
                        <span class="min-w-0 truncate font-semibold text-text-main" v-tooltip="buildModTooltip(item.group)">
                          {{ item.group.mod_name }}
                        </span>
                        <span class="ml-auto inline-flex items-center gap-1 shrink-0">
                          <span class="rounded border border-border-base/10 bg-bg-overlay/5 px-1.5 py-0 text-[0.65rem] leading-4" :class="storeBadgeClass(item.group.store)">
                            {{ storeLabel(item.group.store) }}
                          </span>
                          <span class="text-xs text-text-dim">{{ item.group.count }}</span>
                        </span>
                      </button>

                      <button v-else-if="item.type === 'file'" class="flex h-7 w-full items-center gap-1 px-2 bg-bg-muted/30 text-left text-sm transition-colors hover:brightness-125" :style="{ paddingLeft: `${12 + item.depth * 16}px` }"
                        @click="openFileNode(item.file)" @contextmenu="openFileMenu($event, item.group, item.file)" >
                        <component :is="isExpandedFile(item.file.id) ? ChevronDown : ChevronRight" class="size-3 shrink-0 text-text-dim" @click.stop="toggleFile(item.file.id)" />
                        <FileCode2 class="size-3.5 shrink-0 text-accent-primary" />
                        <span class="min-w-0 truncate font-mono text-text-main" v-tooltip="buildFileTooltip(item.group, item.file)">
                          {{ item.file.file_name }}
                        </span>
                        <span class="ml-auto shrink-0 text-xs text-text-dim">{{ item.file.count }}</span>
                      </button>

                      <button v-else class="flex h-6 w-full items-center gap-2 px-2 text-left text-[0.7rem] transition-colors"
                        :style="{ paddingLeft: `${12 + item.depth * 16}px` }" :class="fileSearchStore.activeMatchId === item.row._row_id ? 'bg-accent-highlight/18 text-text-main' : 'bg-bg-inset text-text-dim hover:brightness-125'"
                        @click="selectTreeMatch(item.row)" >
                        <span class="shrink-0 font-mono text-xs" :class="fileSearchStore.activeMatchId === item.row._row_id ? 'text-accent-highlight' : 'text-accent-cool'">{{ item.row.line_number }}</span>
                        <span class="min-w-0 truncate font-mono" v-html="formatInlineMatch(item.row.matched_line)"></span>
                      </button>
                    </template>
                  </RecycleScroller>

                  <div v-if="stickyTreeRows.mod || stickyTreeRows.file" class="pointer-events-none absolute inset-x-0 top-0 z-20 overflow-hidden"
                    :style="{ height: `${stickyTreeOverlayHeight}px` }" >
                    <button v-if="stickyTreeRows.mod" :style="stickyTreeRows.mod.style" class="pointer-events-auto absolute inset-x-0 z-20 flex h-8 items-center gap-1 bg-bg-muted px-2 text-left text-sm shadow-[0_3px_5px_var(--shadow-color)] transition-colors hover:bg-bg-deep"
                      @click="toggleMod(stickyTreeRows.mod.group.id)" @contextmenu="openModMenu($event, stickyTreeRows.mod.group)" >
                      <component :is="isExpandedMod(stickyTreeRows.mod.group.id) ? ChevronDown : ChevronRight" class="size-3.5 shrink-0 text-text-dim" />
                      <span class="min-w-0 truncate font-semibold text-text-main" v-tooltip="buildModTooltip(stickyTreeRows.mod.group)">
                        {{ stickyTreeRows.mod.group.mod_name }}
                      </span>
                      <span class="ml-auto inline-flex items-center gap-1 shrink-0">
                        <span class="rounded border border-border-base/10 bg-bg-overlay/5 px-1.5 py-0 text-[0.65rem] leading-4" :class="storeBadgeClass(stickyTreeRows.mod.group.store)">
                          {{ storeLabel(stickyTreeRows.mod.group.store) }}
                        </span>
                        <span class="text-xs text-text-dim">{{ stickyTreeRows.mod.group.count }}</span>
                      </span>
                    </button>

                    <button v-if="stickyTreeRows.file"
                      class="pointer-events-auto absolute inset-x-0 z-10 flex h-7 items-center gap-1 bg-bg-deep px-2 text-left text-sm shadow-[0_3px_5px_var(--shadow-color)] backdrop-blur-sm transition-colors hover:bg-bg-inset/96"
                      :style="{
                        ...stickyTreeRows.file.style,
                        paddingLeft: `${12 + stickyTreeRows.file.depth * 16}px`,
                      }"
                      @click="openFileNode(stickyTreeRows.file.file)"
                      @contextmenu="openFileMenu($event, stickyTreeRows.file.group, stickyTreeRows.file.file)" >
                      <component :is="isExpandedFile(stickyTreeRows.file.file.id) ? ChevronDown : ChevronRight" class="size-3 shrink-0 text-text-dim" @click.stop="toggleFile(stickyTreeRows.file.file.id)" />
                      <FileCode2 class="size-3.5 shrink-0 text-accent-primary" />
                      <span class="min-w-0 truncate font-mono text-text-main" v-tooltip="buildFileTooltip(stickyTreeRows.file.group, stickyTreeRows.file.file)">
                        {{ stickyTreeRows.file.file.file_name }}
                      </span>
                      <span class="ml-auto shrink-0 text-xs text-text-dim">{{ stickyTreeRows.file.file.count }}</span>
                    </button>
                  </div>
                </div>
              </div>

              <div class="content-surface flex min-h-0 flex-col overflow-hidden bg-bg-deep">
                <!-- 文件预览操作栏 -->
                <div class="flex items-center justify-between gap-3 shadow-md/30 px-4 py-2 bg-bg-surface">
                  <div class="min-w-0">
                    <div class="truncate font-mono text-sm text-text-main" v-tooltip="viewerTitleTooltip">
                      {{ fileSearchStore.viewerState.fileName || '未选择文件' }}
                    </div>
                  </div>
                  <div class="flex shrink-0 items-center gap-2">
                    <div class="flex items-center gap-1">
                      <input v-model="viewerSearchQuery" type="text" placeholder="在当前文件中搜索定位" @keydown.enter.prevent="goToNextViewerMatch()"
                        class="h-8 min-w-50 rounded-lg border border-border-base/10 bg-bg-inset/60 px-3 text-sm text-text-main outline-none transition-all focus:border-accent-cool/40 focus:shadow-[0_0_0_1px_rgba(var(--rgb-accent-cool),0.18)]" >
                      <button class="rounded-lg border border-border-base/10 bg-bg-overlay/5 px-0.5 py-0.5 text-text-dim transition-colors hover:bg-bg-overlay/10 hover:text-text-main disabled:opacity-40"
                        :disabled="viewerMatchEntries.length === 0" @click="goToPreviousViewerMatch()" v-tooltip="'上一个搜索结果'" ><ChevronUp class="size-5" />
                      </button>
                      <button class="rounded-lg border border-border-base/10 bg-bg-overlay/5 px-0.5 py-0.5 text-text-dim transition-colors hover:bg-bg-overlay/10 hover:text-text-main disabled:opacity-40"
                        :disabled="viewerMatchEntries.length === 0" @click="goToNextViewerMatch()" v-tooltip="'下一个搜索结果'" ><ChevronDown class="size-5" />
                      </button>
                      <span class="rounded-xl border border-border-base/10 bg-bg-overlay/5 px-2 py-0.5 text-xs text-text-dim">
                        {{ viewerMatchCounterLabel }}
                      </span>
                    </div>
                    
                    <label class="inline-flex h-8 items-center gap-1 px-1 text-xs text-text-dim transition-colors hover:text-text-main">
                      <input v-model="wrapViewerLines" type="checkbox" class="size-3.5 rounded border border-border-base/18 bg-bg-muted/70 accent-accent-cool" >
                      自动换行
                    </label>
                    <span v-if="fileSearchStore.viewerState.truncated" class="rounded-full border border-accent-warn/20 bg-accent-warn/10 px-2 py-0.5 text-xs text-accent-warn" >
                      文件过大已截断
                    </span>
                    <button class="flex items-center justify-center text-xs transition-colors text-text-dim hover:text-text-main disabled:opacity-40"
                      :disabled="!fileSearchStore.viewerState.filePath" @click="openCurrentFolder" v-tooltip="'打开文件所在目录'" >
                      <FolderInput class="size-5" />
                    </button>
                    <button class="flex items-center justify-center text-xs text-text-dim transition-colors hover:text-text-main disabled:opacity-40"
                      :disabled="!fileSearchStore.viewerState.filePath" @click="openCurrentFile" v-tooltip="'打开文件'" >
                      <FileSymlink class="size-5" />
                    </button>
                  </div>
                </div>
                <!-- 文件预览 -->
                <FileSearchPreviewEditor ref="previewEditorRef"
                  :file-path="fileSearchStore.viewerState.filePath"
                  :content="fileSearchStore.viewerState.content"
                  :loading="fileSearchStore.viewerState.loading"
                  :error="fileSearchStore.viewerState.error"
                  :wrap-lines="wrapViewerLines"
                  :search-query="viewerSearchQuery"
                  :use-regex="fileSearchStore.form.use_regex"
                  :case-sensitive="fileSearchStore.form.case_sensitive"
                  :line-number="fileSearchStore.viewerState.lineNumber"
                  :active-match="currentViewerMatch"
                />
              </div>
            </div>
          </div>
        </div>
  </CommonModalShell>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, shallowRef, watch } from 'vue'
import { ChevronDown, ChevronRight, ChevronUp, FileCode2, FileInput, FileSymlink, FolderInput, FolderOpen, Search, Square } from 'lucide-vue-next'
import { RecycleScroller } from 'vue-virtual-scroller'

import CommonSelect from './common/input/CommonSelect.vue'
import FileSearchPreviewEditor from './utils/FileSearchPreviewEditor.vue'
import CommonModalShell from './common/CommonModalShell.vue'
import { FILE_SEARCH_EXCLUDE_OPTIONS, FILE_SEARCH_SCOPE_OPTIONS, useFileSearchStore, } from '../stores/fileSearchStore'
import { useContextMenuStore } from '../stores/contextMenuStore'
import { useAppStore } from '../stores/appStore'
import { buildSearchRegExp, escapeHtml } from '../utils/text'

const appStore = useAppStore()
const fileSearchStore = useFileSearchStore()
const contextMenuStore = useContextMenuStore()
const queryInputRef = ref(null)
const treeScrollerRef = ref(null)
const previewEditorRef = ref(null)
const scopeOptions = FILE_SEARCH_SCOPE_OPTIONS
const excludeOptions = FILE_SEARCH_EXCLUDE_OPTIONS

const expandedModIds = ref(new Set())
const expandedFileIds = ref(new Set())
const didInitializeExpansion = ref(false)
const viewerSearchQuery = ref('')
const wrapViewerLines = ref(false)
const currentViewerMatchIndex = ref(0)
const pendingSelectedTreeMatch = ref(null)
const treeScrollTop = ref(0)
const treeScrollCleanup = ref(null)

const TREE_ROW_HEIGHT = 26

const emptyTitle = computed(() => {
  if (fileSearchStore.isBusy) return '正在搜索中'
  if (fileSearchStore.results.length === 0) return '还没有搜索结果'
  return '过滤后没有可见结果'
})

const emptyDescription = computed(() => {
  if (fileSearchStore.isBusy) return '结果会随着后台扫描流式追加到这里。'
  if (fileSearchStore.results.length === 0) return '输入搜索词并执行搜索后，这里会显示命中结果。'
  return '尝试清空筛选词，或调整搜索条件后重新执行。'
})

const storeLabel = (store) => {
  const value = String(store || '').toLowerCase()
  if (value === 'local') return '本地'
  if (value === 'self') return '管理器'
  if (value === 'workshop') return '工坊'
  if (value === 'core') return 'Core'
  if (value === 'dlc') return 'DLC'
  return '未知'
}

const storeBadgeClass = (store) => {
  const value = String(store || '').toLowerCase()
  if (value === 'local') return 'text-accent-success'
  if (value === 'self') return 'text-accent-primary'
  if (value === 'workshop') return 'text-accent-warn'
  if (value === 'core' || value === 'dlc') return 'text-accent-cool'
  return 'text-text-dim'
}

const isFileTypeEnabled = (value) => fileSearchStore.form.file_types.includes(value)
const toggleFileType = (value) => fileSearchStore.toggleFileType(value)
const isExcludeEnabled = (key) => !!fileSearchStore.form.exclude_options?.[key]
const toggleExcludeOption = (key) => fileSearchStore.setExcludeOption(key, !isExcludeEnabled(key))

const handleResultsEvent = (event) => {
  fileSearchStore.handleResultsEvent(event?.detail || {})
}

const viewerLines = computed(() => String(fileSearchStore.viewerState.content || '').split(/\r?\n/))

const normalizedResultFilter = computed(() => String(fileSearchStore.resultFilter || '').trim().toLowerCase())
const treeCache = shallowRef(createEmptyTreeCache())
const flatRows = shallowRef([])
const treeSyncSignal = computed(() => {
  const rows = fileSearchStore.filteredResults
  const firstRowId = rows.length > 0 ? String(rows[0]?._row_id || '') : ''
  const lastRowId = rows.length > 0 ? String(rows[rows.length - 1]?._row_id || '') : ''
  return `${normalizedResultFilter.value}::${rows.length}::${firstRowId}::${lastRowId}`
})

const isExpandedMod = (id) => expandedModIds.value.has(id)
const isExpandedFile = (id) => expandedFileIds.value.has(id)

// 树形结果是固定行高，所以吸顶只需要根据滚动偏移做几何计算。
// 规则保持很直接：
// 1. 模组行进入顶端后吸顶。
// 2. 文件行只有在所属模组已经吸顶后，才允许吸在模组行下方。
// 3. 下一个同级节点到来时，上一项被顶走；低级节点只会被更高级节点遮住，不会越级盖上去。
const stickyTreeRows = computed(() => {
  const rows = flatRows.value
  if (!rows.length) return { mod: null, file: null }
  const visibleIndex = Math.min(rows.length - 1, Math.max(0, Math.floor(treeScrollTop.value / TREE_ROW_HEIGHT)))

  let modIndex = -1
  let fileIndex = -1
  for (let index = visibleIndex; index >= 0; index -= 1) {
    const row = rows[index]
    if (fileIndex < 0 && row.type === 'file') {
      fileIndex = index
    }
    if (row.type === 'mod') {
      modIndex = index
      break
    }
  }

  const modRow = modIndex >= 0 ? rows[modIndex] : null
  const fileRow = fileIndex >= 0 && rows[fileIndex]?.group?.id === modRow?.group?.id
    ? rows[fileIndex]
    : null
  const modSticky = buildStickyModRow(rows, modRow, modIndex)

  return {
    mod: modSticky,
    file: buildStickyFileRow(rows, fileRow, fileIndex, !!modSticky),
  }
})

// 吸顶层本身也要有明确高度，否则绝对定位子项不会撑开父容器，`overflow-hidden` 会把整层裁掉。
const stickyTreeOverlayHeight = computed(() => {
  if (stickyTreeRows.value.file) return TREE_ROW_HEIGHT * 2
  if (stickyTreeRows.value.mod) return TREE_ROW_HEIGHT
  return 0
})

function createEmptyTreeCache(filterKey = '') {
  return {
    filterKey,
    lastLength: 0,
    lastRowId: '',
    groups: [],
    groupMap: new Map(),
    rowLocationMap: new Map(),
  }
}

const createGroupNode = (row) => ({
  id: `${row.package_id}::${row.store}`,
  mod_name: row.mod_name,
  package_id: row.package_id,
  store: row.store,
  mod_path: row.mod_path,
  count: 0,
  files: [],
  fileMap: new Map(),
})

const createFileNode = (group, row) => ({
  id: `${group.id}::${row.file_path}`,
  file_name: row.file_name,
  file_path: row.file_path,
  mod_path: row.mod_path,
  count: 0,
  rows: [],
  rowIds: new Set(),
})

const appendResultToTreeCache = (cache, row) => {
  const groupId = `${row.package_id}::${row.store}`
  let group = cache.groupMap.get(groupId)
  if (!group) {
    group = createGroupNode(row)
    cache.groupMap.set(groupId, group)
    cache.groups.push(group)
  }
  group.count += 1

  const fileId = `${group.id}::${row.file_path}`
  let file = group.fileMap.get(fileId)
  if (!file) {
    file = createFileNode(group, row)
    group.fileMap.set(fileId, file)
    group.files.push(file)
  }

  if (file.rowIds.has(row._row_id)) return
  file.rowIds.add(row._row_id)
  file.rows.push(row)
  file.count += 1
  cache.rowLocationMap.set(row._row_id, {
    groupId: group.id,
    fileId: file.id,
  })
}

const rebuildFlatRows = (cache = treeCache.value) => {
  const rows = []
  for (const group of cache.groups) {
    rows.push({
      id: `mod:${group.id}`,
      type: 'mod',
      depth: 0,
      group,
    })
    if (!isExpandedMod(group.id)) continue
    for (const file of group.files) {
      rows.push({
        id: `file:${file.id}`,
        type: 'file',
        depth: 1,
        group,
        file,
      })
      if (!isExpandedFile(file.id)) continue
      for (const row of file.rows) {
        rows.push({
          id: `match:${row._row_id}`,
          type: 'match',
          depth: 2,
          group,
          file,
          row,
        })
      }
    }
  }
  flatRows.value = rows
}

// 模组行只负责自己这一层的吸顶与同级替换，不混入文件层规则。
const buildStickyModRow = (rows, row, rowIndex) => {
  if (!row || rowIndex < 0) return null
  const naturalTop = rowIndex * TREE_ROW_HEIGHT
  if (treeScrollTop.value <= naturalTop) {
    return null
  }
  const nextModIndex = findNextRowIndex(rows, rowIndex, item => item.type === 'mod')
  const nextModViewportTop = nextModIndex >= 0
    ? nextModIndex * TREE_ROW_HEIGHT - treeScrollTop.value
    : Number.POSITIVE_INFINITY
  const top = nextModViewportTop < TREE_ROW_HEIGHT
    ? nextModViewportTop - TREE_ROW_HEIGHT
    : 0
  return {
    ...row,
    style: {
      top: `${top}px`,
    },
  }
}

// 文件行的吸顶受模组行约束，只能出现在模组行下方；被下一文件或下一模组顶走时则向上退出。
const buildStickyFileRow = (rows, row, rowIndex, hasStickyMod) => {
  if (!row || rowIndex < 0 || !hasStickyMod) return null
  const naturalTop = rowIndex * TREE_ROW_HEIGHT
  const baseTop = TREE_ROW_HEIGHT
  if (treeScrollTop.value <= naturalTop - baseTop) {
    return null
  }
  const nextFileBoundaryIndex = findNextRowIndex(
    rows,
    rowIndex,
    item => item.type === 'file' || item.type === 'mod'
  )
  const nextBoundaryViewportTop = nextFileBoundaryIndex >= 0
    ? nextFileBoundaryIndex * TREE_ROW_HEIGHT - treeScrollTop.value
    : Number.POSITIVE_INFINITY
  const top = nextBoundaryViewportTop < baseTop + TREE_ROW_HEIGHT
    ? nextBoundaryViewportTop - TREE_ROW_HEIGHT
    : baseTop
  return {
    ...row,
    style: {
      top: `${top}px`,
    },
  }
}

const findNextRowIndex = (rows, rowIndex, predicate) => {
  for (let index = rowIndex + 1; index < rows.length; index += 1) {
    if (predicate(rows[index])) return index
  }
  return -1
}

const buildTreeCacheFromRows = (rows, filterKey) => {
  const cache = createEmptyTreeCache(filterKey)
  for (const row of rows) {
    appendResultToTreeCache(cache, row)
  }
  cache.lastLength = rows.length
  cache.lastRowId = String(rows.length > 0 ? rows[rows.length - 1]?._row_id || '' : '')
  return cache
}

const canReuseTreeCacheIncrementally = (cache, rows, filterKey) => {
  if (!cache) return false
  if (cache.filterKey !== filterKey) return false
  if (rows.length < cache.lastLength) return false
  if (cache.lastLength === 0) return true
  return String(rows[cache.lastLength - 1]?._row_id || '') === cache.lastRowId
}

const syncTreeCache = () => {
  const rows = fileSearchStore.filteredResults
  const filterKey = normalizedResultFilter.value
  let cache = treeCache.value

  if (!canReuseTreeCacheIncrementally(cache, rows, filterKey)) {
    cache = buildTreeCacheFromRows(rows, filterKey)
  } else if (rows.length > cache.lastLength) {
    for (let index = cache.lastLength; index < rows.length; index += 1) {
      appendResultToTreeCache(cache, rows[index])
    }
    cache.lastLength = rows.length
    cache.lastRowId = String(rows.length > 0 ? rows[rows.length - 1]?._row_id || '' : '')
    cache = {
      ...cache,
      groups: [...cache.groups],
      groupMap: new Map(cache.groupMap),
      rowLocationMap: new Map(cache.rowLocationMap),
    }
  }

  treeCache.value = cache
  rebuildFlatRows(cache)
}

const syncExpansionState = () => {
  const modIds = new Set()
  const fileIds = new Set()
  for (const group of treeCache.value.groups) {
    modIds.add(group.id)
    for (const file of group.files) {
      fileIds.add(file.id)
    }
  }

  const nextExpandedMods = new Set([...expandedModIds.value].filter(id => modIds.has(id)))
  const nextExpandedFiles = new Set([...expandedFileIds.value].filter(id => fileIds.has(id)))

  if (!didInitializeExpansion.value || nextExpandedMods.size === 0) {
    for (const modId of modIds) {
      nextExpandedMods.add(modId)
    }
    didInitializeExpansion.value = true
  }

  const activeRowId = String(fileSearchStore.activeMatchId || '')
  if (activeRowId) {
    const activeLocation = treeCache.value.rowLocationMap.get(activeRowId)
    if (activeLocation) {
      nextExpandedMods.add(activeLocation.groupId)
      nextExpandedFiles.add(activeLocation.fileId)
    }
  }

  const modsChanged = nextExpandedMods.size !== expandedModIds.value.size || [...nextExpandedMods].some(id => !expandedModIds.value.has(id))
  const filesChanged = nextExpandedFiles.size !== expandedFileIds.value.size || [...nextExpandedFiles].some(id => !expandedFileIds.value.has(id))
  expandedModIds.value = nextExpandedMods
  expandedFileIds.value = nextExpandedFiles
  return modsChanged || filesChanged
}

const toggleMod = (id) => {
  const next = new Set(expandedModIds.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  expandedModIds.value = next
  rebuildFlatRows()
}

const toggleFile = (id) => {
  const next = new Set(expandedFileIds.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  expandedFileIds.value = next
  rebuildFlatRows()
}

const openFileNode = async (file) => {
  if (isExpandedFile(file.id)) {
    toggleFile(file.id)
    return
  }
  toggleFile(file.id)
  const firstRow = file.rows?.[0]
  if (!firstRow) return
  await selectTreeMatch(firstRow)
}

const buildViewerPattern = () => {
  return buildSearchRegExp(viewerSearchQuery.value, {
    useRegex: fileSearchStore.form.use_regex,
    caseSensitive: fileSearchStore.form.case_sensitive,
  })
}

const viewerMatchEntries = computed(() => {
  const pattern = buildViewerPattern()
  if (!pattern) return []
  const entries = []
  for (let lineIndex = 0; lineIndex < viewerLines.value.length; lineIndex += 1) {
    const line = String(viewerLines.value[lineIndex] || '')
    const regex = new RegExp(pattern.source, pattern.flags)
    for (const match of line.matchAll(regex)) {
      const text = String(match[0] || '')
      if (!text) continue
      entries.push({
        id: `${lineIndex + 1}:${match.index ?? 0}:${text.length}:${entries.length}`,
        lineNumber: lineIndex + 1,
        start: match.index ?? 0,
        end: (match.index ?? 0) + text.length,
      })
    }
  }
  return entries
})

const currentViewerMatch = computed(() => viewerMatchEntries.value[currentViewerMatchIndex.value] || null)

const viewerMatchCounterLabel = computed(() => {
  if (!viewerSearchQuery.value.trim()) return '0/0'
  const total = viewerMatchEntries.value.length
  if (total <= 0) return '0/0'
  return `${currentViewerMatchIndex.value + 1}/${total}`
})

const viewerTitleTooltip = computed(() => {
  const parts = [
    fileSearchStore.viewerState.fileName,
    fileSearchStore.viewerState.filePath,
  ].filter(Boolean)
  return parts.join('\n')
})

const treeHighlightPattern = computed(() => {
  return buildSearchRegExp(fileSearchStore.form.query, {
    useRegex: fileSearchStore.form.use_regex,
    caseSensitive: fileSearchStore.form.case_sensitive,
  })
})

const highlightTreeText = (value = '') => {
  const pattern = treeHighlightPattern.value
  if (!pattern) return escapeHtml(value)
  const source = String(value || '')
  let lastIndex = 0
  let html = ''
  const matches = [...source.matchAll(new RegExp(pattern.source, pattern.flags))]
  if (matches.length === 0) return escapeHtml(source)
  for (const match of matches) {
    const index = match.index ?? 0
    const text = match[0] || ''
    html += escapeHtml(source.slice(lastIndex, index))
    html += `<mark class="rounded-sm bg-accent-highlight/50 px-0.5 text-text-main">${escapeHtml(text)}</mark>`
    lastIndex = index + text.length
  }
  html += escapeHtml(source.slice(lastIndex))
  return html
}

const formatInlineMatch = (value = '') => highlightTreeText(value)

const buildModTooltip = (group) => [
  group.mod_name,
  group.package_id,
  group.mod_path,
].filter(Boolean).join('\n')

const buildFileTooltip = (group, file) => [
  group.mod_name,
  file.file_name,
  file.file_path,
].filter(Boolean).join('\n')

const resolveViewerMatchIndexForRow = (row) => {
  if (!row) return false
  const lineNumber = Number(row.line_number || 0)
  if (lineNumber <= 0) return false
  const entries = viewerMatchEntries.value
  if (!entries.length) return false
  const exactLineIndex = entries.findIndex(item => item.lineNumber === lineNumber)
  if (exactLineIndex >= 0) {
    currentViewerMatchIndex.value = exactLineIndex
    return true
  }
  const fallbackIndex = entries.findIndex(item => item.lineNumber >= lineNumber)
  if (fallbackIndex >= 0) {
    currentViewerMatchIndex.value = fallbackIndex
    return true
  }
  currentViewerMatchIndex.value = Math.max(0, entries.length - 1)
  return true
}

const syncPreviewToCurrentMatch = async (options = {}) => {
  const preview = previewEditorRef.value
  if (!preview) return false
  await nextTick()

  const match = options.match || currentViewerMatch.value
  if (match) {
    return await preview.jumpToMatch(match)
  }

  const lineNumber = Number(options.lineNumber || fileSearchStore.viewerState.lineNumber || 0)
  if (lineNumber > 0) {
    return await preview.jumpToLine(lineNumber)
  }
  return false
}

const selectTreeMatch = async (row) => {
  pendingSelectedTreeMatch.value = row
  viewerSearchQuery.value = String(fileSearchStore.form.query || '')
  await fileSearchStore.selectMatch(row)
  resolveViewerMatchIndexForRow(row)
  await syncPreviewToCurrentMatch({
    lineNumber: row?.line_number,
  })
}

const openModMenu = (event, group) => {
  contextMenuStore.open(event, [
    { label: '打开模组目录', icon: FolderOpen, action: () => fileSearchStore.openResultModFolder(group) },
  ], group)
}

const openFileMenu = (event, group, file) => {
  const firstRow = file.rows?.[0]
  contextMenuStore.open(event, [
    { label: '打开文件', icon: FileCode2, disabled: !firstRow, action: () => fileSearchStore.openResultFile(firstRow) },
    { label: '打开所在目录', icon: FolderOpen, disabled: !firstRow, action: () => fileSearchStore.openResultFolder(firstRow) },
    { label: '打开模组目录', icon: FolderOpen, action: () => fileSearchStore.openResultModFolder(group) },
  ], { group, file })
}

const openCurrentFile = async () => {
  if (!fileSearchStore.viewerState.filePath) return
  await fileSearchStore.openResultFile({ file_path: fileSearchStore.viewerState.filePath })
}

const openCurrentFolder = async () => {
  if (!fileSearchStore.viewerState.filePath) return
  await fileSearchStore.openResultFolder({ file_path: fileSearchStore.viewerState.filePath })
}

const goToPreviousViewerMatch = () => {
  const total = viewerMatchEntries.value.length
  if (total <= 0) return
  currentViewerMatchIndex.value = (currentViewerMatchIndex.value - 1 + total) % total
  syncPreviewToCurrentMatch()
}

const goToNextViewerMatch = () => {
  const total = viewerMatchEntries.value.length
  if (total <= 0) return
  currentViewerMatchIndex.value = (currentViewerMatchIndex.value + 1) % total
  syncPreviewToCurrentMatch()
}

const resolveScrollerElement = (scrollerRef) => scrollerRef?.$el || scrollerRef || null

// `RecycleScroller` 的真实滚动容器在组件根元素上，这里手动绑定监听供吸顶层计算当前层级。
const bindTreeScrollListener = async () => {
  treeScrollCleanup.value?.()
  treeScrollCleanup.value = null
  await nextTick()
  const element = resolveScrollerElement(treeScrollerRef.value)
  if (!element) {
    treeScrollTop.value = 0
    return
  }

  const handleScroll = () => {
    treeScrollTop.value = Number(element.scrollTop || 0)
  }

  handleScroll()
  element.addEventListener('scroll', handleScroll, { passive: true })
  treeScrollCleanup.value = () => {
    element.removeEventListener('scroll', handleScroll)
  }
}

watch(
  () => appStore.uiState.showFileSearchWorkbench,
  async (visible) => {
    if (!visible) return
    await nextTick()
    queryInputRef.value?.focus?.()
  },
  { immediate: false }
)

watch(
  treeSyncSignal,
  () => {
    syncTreeCache()
    if (syncExpansionState()) {
      rebuildFlatRows()
    }
  },
  { immediate: true, deep: false }
)

watch(
  () => [appStore.uiState.showFileSearchWorkbench, flatRows.value.length],
  async ([visible, rowCount]) => {
    if (!visible || rowCount <= 0) {
      treeScrollCleanup.value?.()
      treeScrollCleanup.value = null
      treeScrollTop.value = 0
      return
    }
    await bindTreeScrollListener()
  },
  { immediate: true, deep: false }
)

watch(
  () => fileSearchStore.activeMatchId,
  () => {
    if (syncExpansionState()) {
      rebuildFlatRows()
    }
  }
)

watch(viewerSearchQuery, () => {
  currentViewerMatchIndex.value = 0
})

watch(viewerMatchEntries, (entries) => {
  if (entries.length <= 0) {
    currentViewerMatchIndex.value = 0
    return
  }
  if (pendingSelectedTreeMatch.value) {
    const resolved = resolveViewerMatchIndexForRow(pendingSelectedTreeMatch.value)
    if (resolved) {
      syncPreviewToCurrentMatch({
        lineNumber: pendingSelectedTreeMatch.value?.line_number,
      })
      pendingSelectedTreeMatch.value = null
      return
    }
  }
  if (currentViewerMatchIndex.value >= entries.length) {
    currentViewerMatchIndex.value = entries.length - 1
  }
})

onMounted(() => {
  window.addEventListener('file-search-results', handleResultsEvent)
})

onUnmounted(() => {
  window.removeEventListener('file-search-results', handleResultsEvent)
  treeScrollCleanup.value?.()
  treeScrollCleanup.value = null
})
</script>

<style scoped>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.24s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
