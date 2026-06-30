<template>
  <div class="flex h-full flex-col overflow-hidden rounded-b-none rounded-t-2xl border-2 border-accent-danger/20 bg-bg-surface/40 shadow-2xl">
    <div class="flex h-8 items-center justify-between border-b border-border-base/5 bg-accent-danger/10 px-3">
      <span class="flex items-center gap-1 text-sm font-bold uppercase tracking-wider text-accent-danger">
        <div class="mr-1 h-1.5 w-1.5 rounded-full bg-accent-danger shadow-lg shadow-accent-danger"></div>
        已禁用
      </span>
      <span class="rounded bg-bg-inset/70 px-2 py-0.5 text-xs text-accent-danger">
        {{ displayMods.length }} / {{ modStore.disabledMods.length }}
      </span>
    </div>

    <div class="flex flex-col gap-2 bg-bg-deep/20 px-2 py-2 shadow-xl">
      <input v-model="searchQuery" placeholder="筛选名称、包名、工坊 ID、路径..."
        class="w-full rounded-lg border border-border-base/10 bg-bg-inset px-3 py-1.5 text-xs text-text-main outline-none transition-colors focus:border-accent-danger" />
      <div class="flex items-center justify-end gap-2">
        <CommonSelect v-model="sourceFilter" mini :options="sourceOptions" />
        <CommonSelect v-model="sortBy" mini :options="sortOptions" />
        <Motion class="flex size-7 cursor-pointer items-center justify-center rounded-md border border-border-base/10 bg-bg-overlay/5 p-1 text-xs font-bold hover:bg-bg-overlay/10 hover:text-text-main"
          :initial="{ rotateX: 0, opacity: 1 }"
          :animate="{ rotateX: isSortDesc ? 0 : 180 }"
          :transition="{ type: 'spring', stiffness: 300, damping: 20 }"
          @click="isSortDesc = !isSortDesc"
          v-tooltip="isSortDesc ? '切换为升序排列' : '切换为降序排列'">
          <span v-if="isSortDesc" class="rotate-x-180">
            <svg class="size-4" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m3 8 4-4 4 4"/><path d="M7 4v16"/><path d="M11 12h4"/><path d="M11 16h7"/><path d="M11 20h10"/></svg>
          </span>
          <span v-else>
            <svg class="size-4" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m3 16 4 4 4-4"/><path d="M7 20V4"/><path d="M11 4h4"/><path d="M11 8h7"/><path d="M11 12h10"/></svg>
          </span>
        </Motion>
      </div>
    </div>

    <div class="relative min-h-0 flex-1 p-1">
      <div v-if="displayMods.length > 0" ref="scrollRef"
        class="custom-scrollbar h-full overflow-auto pb-10"
        v-selectable-list="{
          data: displayPathHashes,
          selectedIds: selectedPathHashes,
          onSelect: handleSelect,
          onClear: clearSelection,
          clickClass: 'matrix-select-trigger',
          swipeClass: 'matrix-select-trigger',
          idAttribute: 'data-id'
        }">
        <div :style="{ height: `${totalSize}px`, position: 'relative' }">
          <div v-for="virtualRow in virtualRows" :key="displayMods[virtualRow.index]?.path_hash || virtualRow.index"
            class="absolute left-0 right-0"
            :style="{ transform: `translateY(${virtualRow.start}px)`, height: `${virtualRow.size}px` }">
            <div class="py-[3px]" :data-id="displayMods[virtualRow.index]?.path_hash">
              <div class="matrix-select-trigger relative flex h-full items-center gap-2 rounded-lg border p-1.5 text-text-soft transition-all hover:bg-bg-overlay/10 hover:brightness-125"
                :class="selectedPathHashes.includes(displayMods[virtualRow.index]?.path_hash)
                  ? 'border-accent-special/70 ring-1 ring-accent-special bg-accent-special/10'
                  : 'border-accent-danger/25 bg-bg-surface/20'"
                @contextmenu.prevent="handleContextMenu($event, displayMods[virtualRow.index])">
                <div class="relative shrink-0">
                  <img v-if="displayMods[virtualRow.index]?.preview_path"
                    :src="appStore.getThumbUrl(displayMods[virtualRow.index]?.package_id, displayMods[virtualRow.index]?.preview_path)"
                    loading="lazy"
                    class="h-9 w-11 rounded object-cover border border-accent-danger/30 pointer-events-none opacity-80" />
                  <div v-else class="h-9 w-11 rounded border-2 border-dashed border-border-base/10 flex items-center justify-center">
                    <svg class="size-6 opacity-20" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"></path></svg>
                  </div>
                  <div class="absolute -left-1 -top-2 flex items-center gap-0.5">
                    <span class="flex items-center justify-center rounded-sm bg-glass-medium/70" v-tooltip="`类型：${getModType(displayMods[virtualRow.index])}`">
                      <component :is="getTypeIcon(displayMods[virtualRow.index])" class="size-4" />
                    </span>
                    <span class="flex items-center justify-center rounded-sm bg-glass-medium/70" v-tooltip="`储存位置：${getSourceLabel(displayMods[virtualRow.index])}`">
                      <IconSteam v-if="isWorkshopMod(displayMods[virtualRow.index])" class="size-4 fill-current" />
                      <IconSelf v-else-if="isManagerMod(displayMods[virtualRow.index])" class="size-4 grayscale-20" />
                      <Folder v-else class="size-4" />
                    </span>
                  </div>
                  <span v-if="getLatestSupportedVersion(displayMods[virtualRow.index])"
                    class="absolute -bottom-2 left-0 rounded-sm bg-glass-medium/75 px-0.5 font-mono text-[0.65rem] text-text-dim">
                    {{ getLatestSupportedVersion(displayMods[virtualRow.index]) }}
                  </span>
                </div>

                <div class="min-w-0 flex-1">
                  <div class="flex items-center gap-1 text-sm font-medium text-text-main">
                    <span class="truncate">{{ displayMods[virtualRow.index]?.alias_name || displayMods[virtualRow.index]?.name || displayMods[virtualRow.index]?.package_id }}</span>
                    <AlertTriangle v-if="getStrictDisableRestoreTooltip(displayMods[virtualRow.index])" class="size-3.5 shrink-0 text-accent-warning" v-tooltip="getStrictDisableRestoreTooltip(displayMods[virtualRow.index])" />
                  </div>
                  <div class="mt-0.5 truncate font-mono text-[0.65rem] text-text-dim">
                    {{ displayMods[virtualRow.index]?.package_id }}
                  </div>
                  <div class="mt-0.5 truncate text-[0.65rem] text-text-disabled">
                    {{ displayMods[virtualRow.index]?.path }}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div v-else class="absolute inset-1 flex flex-col items-center justify-center rounded-lg border-2 border-dashed border-border-base/18 bg-bg-deep/90 text-xs text-text-subtle/70">
        <span>{{ modStore.disabledMods.length ? '没有符合筛选条件的禁用 Mod' : '当前环境没有已禁用 Mod' }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { useVirtualizer } from '@tanstack/vue-virtual'
import { Motion } from 'motion-v'
import { AlertTriangle, Copy, FlagOff, Folder, FolderInput, LockOpen, Trash2 } from 'lucide-vue-next'
import CommonSelect from '../../shared/components/input/CommonSelect.vue'
import { useAppStore } from '../../app/stores/appStore'
import { useContextMenuStore } from '../../shared/components/context-menu/contextMenuStore'
import { useModStore } from './stores/modStore'
import { IconSelf, IconSteam, MOD_TYPE_ICON_MAP, SOURCE_TYPE_MAP } from '../../shared/lib/constants'
import { formatFileSize } from '../../shared/lib/format'
import { buildModExternalMenuItem, copyTextToClipboard } from './lib/modContextMenuItems'

const appStore = useAppStore()
const menuStore = useContextMenuStore()
const modStore = useModStore()

const searchQuery = ref('')
const sourceFilter = ref('all')
const sortBy = ref('mtime')
const isSortDesc = ref(true)
const selectedPathHashes = ref([])
const scrollRef = ref(null)

const sourceOptions = [
  { label: '全部来源', value: 'all' },
  { label: '游戏本地', value: 'local' },
  { label: '创意工坊', value: 'workshop' },
  { label: '管理器库', value: 'self' },
]
const sortOptions = [
  { label: '按修改时间', value: 'mtime' },
  { label: '按创建时间', value: 'ctime' },
  { label: '按文件体积', value: 'size' },
  { label: '按名称 A-Z', value: 'name' },
]
const getStoreType = (mod = {}) => {
  const domain = String(mod?.runtime_domain || mod?.store || '').toLowerCase()
  if (domain === 'workshop') return 'workshop'
  if (domain === 'self' || domain === 'tool') return 'self'
  return 'local'
}
const isWorkshopMod = (mod = {}) => getStoreType(mod) === 'workshop'
const isManagerMod = (mod = {}) => getStoreType(mod) === 'self'
const getSourceLabel = (mod = {}) => {
  const domain = String(mod?.runtime_domain || mod?.store || '').toLowerCase()
  if (domain === 'dlc') return 'DLC'
  if (domain === 'tool') return '管理器库'
  return SOURCE_TYPE_MAP[getStoreType(mod)] || domain || '未知来源'
}
const getModType = (mod = {}) => modStore.displayModType(mod)
const getTypeIcon = (mod = {}) => MOD_TYPE_ICON_MAP[getModType(mod)] || MOD_TYPE_ICON_MAP.Unknown
const getLatestSupportedVersion = (mod = {}) => {
  const versions = Array.isArray(mod?.supported_versions) ? mod.supported_versions.filter(Boolean) : []
  return versions.length ? versions[versions.length - 1] : ''
}
const getStrictDisableRestoreTooltip = (mod = {}) => {
  const failure = modStore.strictDisableRestoreFailures?.[mod?.path_hash]
  if (!failure) return ''
  const reason = String(failure.message || '').trim() || '文件操作失败'
  return `严格禁用恢复失败：${reason}。该 Mod 仍按禁用记录保留，请检查文件权限或是否被占用。`
}
const formatTime = (ts) => {
  if (!ts) return 'N/A'
  return new Date(ts).toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' })
}
const matchesSearch = (mod = {}) => {
  const query = searchQuery.value.trim().toLowerCase()
  if (!query) return true
  return [
    mod.name,
    mod.package_id,
    mod.workshop_id,
    mod.path,
  ].some(value => String(value || '').toLowerCase().includes(query))
}
const matchesSource = (mod = {}) => {
  if (sourceFilter.value === 'all') return true
  const domain = String(mod?.runtime_domain || mod?.store || '').toLowerCase()
  if (sourceFilter.value === 'local') return domain === 'local' || domain === 'dlc'
  if (sourceFilter.value === 'self') return domain === 'self' || domain === 'tool'
  return domain === sourceFilter.value
}
const displayMods = computed(() => {
  const list = (modStore.disabledMods || [])
    .filter(mod => mod?.path_hash && matchesSearch(mod) && matchesSource(mod))
    .sort((left, right) => {
      if (sortBy.value === 'name') return String(left.name || left.package_id || '').localeCompare(String(right.name || right.package_id || ''), 'zh-CN')
      if (sortBy.value === 'size') return Number(right.file_size || 0) - Number(left.file_size || 0)
      if (sortBy.value === 'ctime') return Number(right.file_create_time || 0) - Number(left.file_create_time || 0)
      return Number(right.file_modify_time || 0) - Number(left.file_modify_time || 0)
    })
  return isSortDesc.value ? list : [...list].reverse()
})
const displayPathHashes = computed(() => displayMods.value.map(mod => mod.path_hash).filter(Boolean))

const rowHeight = computed(() => appStore.scalePx(62))
const virtualizer = useVirtualizer(computed(() => ({
  count: displayMods.value.length,
  getScrollElement: () => scrollRef.value,
  estimateSize: () => rowHeight.value,
  overscan: 10,
})))
const virtualRows = computed(() => virtualizer.value.getVirtualItems())
const totalSize = computed(() => virtualizer.value.getTotalSize())

const clearSelection = () => {
  selectedPathHashes.value = []
}
const handleSelect = (pathHashes) => {
  selectedPathHashes.value = Array.isArray(pathHashes) ? pathHashes : [pathHashes].filter(Boolean)
}
const getSelectedMods = () => {
  const selectedSet = new Set(selectedPathHashes.value)
  return (modStore.disabledMods || []).filter(mod => selectedSet.has(mod.path_hash))
}
const enableSelectedMods = async () => {
  await modStore.disableMods(selectedPathHashes.value, false, { preserveListState: true })
  clearSelection()
}
const unsubscribeSelectedMods = async () => {
  const selectedMods = getSelectedMods()
  const workshopIds = [...new Set(selectedMods.map(mod => mod.workshop_id).filter(Boolean))]
  if (!workshopIds.length) return
  const pathHashes = selectedMods.map(mod => mod.path_hash).filter(Boolean)
  const ok = await appStore.unsubscribeWorkshopIds(workshopIds, pathHashes)
  if (ok) {
    clearSelection()
    await appStore.requestModScan({ preserveListState: true, forceCoreRefresh: true })
  }
}
const deleteSelectedMods = async () => {
  const ok = await modStore.deleteMods(selectedPathHashes.value)
  if (ok) clearSelection()
}
const buildSelectedDisabledCopyMenuItem = (selectedMods) => {
  const selectedCountText = selectedMods.length > 1 ? ` (${selectedMods.length} 项)` : ''
  const copyField = (label, getter) => {
    const lines = selectedMods.map(mod => String(getter(mod) || '').trim()).filter(Boolean)
    return {
      label: `复制${label}${selectedCountText}`,
      icon: Copy,
      disabled: lines.length === 0,
      action: () => copyTextToClipboard(lines.join('\n'), label),
    }
  }
  return {
    label: '复制模组信息' + selectedCountText,
    icon: Copy,
    disabled: selectedMods.length === 0,
    children: [
      copyField('名称', mod => mod.alias_name || mod.display_name || mod.name || mod.package_id),
      copyField('包名', mod => mod.package_id),
      copyField('工坊 ID', mod => mod.workshop_id),
      copyField('路径', mod => mod.path),
    ],
  }
}
const handleContextMenu = (event, targetMod) => {
  event.preventDefault()
  if (!targetMod?.path_hash) return
  if (!selectedPathHashes.value.includes(targetMod.path_hash)) {
    selectedPathHashes.value = [targetMod.path_hash]
  }

  const selectedMods = getSelectedMods()
  const selectedCountText = selectedMods.length > 1 ? ` (${selectedMods.length} 项)` : ''
  const hasPath = selectedMods.some(mod => !!mod.path)
  const hasWorkshop = selectedMods.some(mod => !!mod.workshop_id)
  menuStore.open(event, [
    { label: '解除禁用' + selectedCountText, icon: LockOpen, level: 'success', action: enableSelectedMods },
    { label: '打开文件夹', icon: FolderInput, disabled: !targetMod.path, action: () => appStore.openPath(targetMod.path) },
    { divider: true },
    buildSelectedDisabledCopyMenuItem(selectedMods),
    buildModExternalMenuItem(targetMod, appStore, { label: '访问页面' }),
    { divider: true },
    { label: '取消订阅' + selectedCountText, icon: FlagOff, level: 'danger', disabled: !hasWorkshop, action: unsubscribeSelectedMods },
    { label: '删除文件' + selectedCountText, icon: Trash2, level: 'danger', disabled: !hasPath, action: deleteSelectedMods },
  ])
}

watch([rowHeight, () => displayMods.value.length], async () => {
  await nextTick()
  virtualizer.value.measure()
})
watch(
  () => modStore.disabledPathHashes,
  (pathHashes) => {
    const validSet = new Set(pathHashes)
    selectedPathHashes.value = selectedPathHashes.value.filter(pathHash => validSet.has(pathHash))
  },
  { deep: true }
)
</script>
