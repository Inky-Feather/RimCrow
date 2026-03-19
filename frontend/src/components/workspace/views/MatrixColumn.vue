<!-- src/components/workspace/views/MatrixColumn.vue -->
<template>
  <div class="flex-1 flex flex-col bg-black/30 border border-text-main/10 rounded-2xl overflow-hidden shadow-2xl relative">
    <div class="px-4 py-3 bg-text-main/5 border-b border-text-main/10 flex flex-col gap-3" :data-tour="'workspace-'+storeType + '-toolbar'">
      <div class="flex items-center justify-between">
        <h3 class="text-sm font-bold text-text-main flex items-center gap-2 cursor-help" v-tooltip="tooltip">
          <div class="w-2.5 h-2.5 rounded-full shadow-lg" :class="iconColor.replace('text-', 'bg-')"></div>
          {{ title }}
        </h3>
        <div class="flex gap-2">
          <span class="text-[0.65rem] font-mono text-text-dim bg-black/40 px-2 py-0.5 rounded-md border border-text-main/5">
            {{ formatFileSize(workspaceStore.librariesSize[storeType]) }}
          </span>
          <span class="text-[0.65rem] font-mono text-text-main bg-black/40 px-2 py-0.5 rounded-md border border-text-main/5">
            {{ mods.length }} 项
          </span>
        </div>
      </div>

      <div class="flex flex-col items-center gap-2">
        <div class="relative w-full">
          <input v-model="searchQuery" placeholder="在此域检索..."
            class="w-full bg-black/60 border border-text-main/10 rounded-lg pl-3 pr-2 py-1.5 text-xs text-text-main focus:border-accent-primary outline-none transition-colors"
          />
        </div>
        <div class="flex items-center w-full justify-end gap-2">
          <CommonSelect v-model="filterState" mini :options="MATRIX_FILTER_STATE_OPTIONS" />

          <CommonSelect v-model="sortBy" mini
            :options="[
              { label: '按变动时间', value: 'change' },
              { label: '按修改时间', value: 'mtime' },
              { label: '按创建时间', value: 'ctime' },
              { label: '按文件体积', value: 'size' },
              { label: '按名称 A-Z', value: 'name' }
            ]"
          />

          <Motion :class="`p-1 size-7 rounded-md bg-text-dim/10 border border-text-main/10 hover:text-text-main hover:bg-text-dim/20 text-xs font-bold flex items-center justify-center cursor-pointer `"
            :initial="{ rotateX: 0, opacity: 1 }"
            :animate="{ rotateX: isSortDsc ? 0 : 180 }"
            :transition="{ type: 'spring', stiffness: 300, damping: 20 }"
            @click="isSortDsc=!isSortDsc"
            v-tooltip="isSortDsc ? '切换为升序排列' : '切换为降序排列'"
          >
            <span v-if="isSortDsc" class="rotate-x-180">
              <svg class="size-4" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m3 8 4-4 4 4"/><path d="M7 4v16"/><path d="M11 12h4"/><path d="M11 16h7"/><path d="M11 20h10"/></svg>
            </span>
            <span v-else>
              <svg class="size-4" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m3 16 4 4 4-4"/><path d="M7 20V4"/><path d="M11 4h4"/><path d="M11 8h7"/><path d="M11 12h10"/></svg>
            </span>
          </Motion>
        </div>
      </div>
    </div>

    <div class="flex-1 overflow-hidden relative p-1">
      <VirtualList v-if="displayMods.length > 0" ref="vListRef" v-model="displayMods"
        dataKey="path_hash" class="h-full custom-scrollbar pb-10" :keeps="40"
        :sortable="false" group="none" :disabled="true"
        v-selectable-list="{
          data: displayMods.map(m => m.path_hash),
          selectedIds: localSelectedIds,
          onSelect: handleSelect,
          onClear: clearSelection,
          clickClass: 'matrix-select-trigger',
          swipeClass: 'matrix-select-trigger',
          idAttribute: 'data-id'
        }"
      >
        <template v-slot:item="{ record, dataKey }">
          <div class="relative group">
            <MatrixItem class="timeline-trigger" :mod="record" :storeType="storeType"
              :lastPlayedTime="lastPlayedTime" :isSelected="localSelectedIds.includes(dataKey)"
              @contextmenu="handleContextMenu" @click="$emit('open-timeline', record)"
            />
          </div>
        </template>
      </VirtualList>

      <div v-else class="absolute inset-0 flex flex-col items-center justify-center text-text-dim/30">
        <svg class="size-12 mb-2 opacity-20" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4" /></svg>
        <span class="text-xs font-bold tracking-widest uppercase">库内暂无数据</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import VirtualList from 'vue-virtual-sortable'
import { Motion } from 'motion-v'
import { Activity, ArrowRightLeft, Cable, Copy, CornerUpRight, DownloadCloud, Flag, FlagOff, FolderInput, Lock, LockOpen, Trash2, Upload } from 'lucide-vue-next'
import CommonSelect from '../../common/input/CommonSelect.vue'
import MatrixItem from '../components/MatrixItem.vue'
import { useAppStore } from '../../../stores/appStore'
import { useConfirmStore } from '../../../stores/confirmStore'
import { useContextMenuStore } from '../../../stores/contextMenuStore'
import { useModStore } from '../../../stores/modStore'
import { useProfileStore } from '../../../stores/profileStore'
import { useWorkspaceStore } from '../../../stores/workspaceStore'
import { IconSteam, SOURCE_TYPE_MAP } from '../../../utils/constants'
import { formatFileSize } from '../../../utils/uiHelper'
import { getMatrixItemState, getMatrixReplacementTargets, matchesMatrixFilter, MATRIX_FILTER_STATE_OPTIONS } from '../utils/matrixItemState'

const props = defineProps({
  title: String,
  iconColor: String,
  storeType: String,
  mods: {
    type: Array,
    default: () => []
  },
  tooltip: String
})

const emit = defineEmits(['open-timeline'])
const appStore = useAppStore()
const profileStore = useProfileStore()
const menuStore = useContextMenuStore()
const modStore = useModStore()
const workspaceStore = useWorkspaceStore()
const confirmStore = useConfirmStore()

const searchQuery = ref('')
const sortBy = ref('change')
const isSortDsc = ref(true)
const filterState = ref('default')
const localSelectedIds = ref([])
const vListRef = ref(null)

const lastPlayedTime = computed(() => profileStore.currentProfile?.last_played_time || 0)

const clearSelection = () => {
  localSelectedIds.value = []
}

const getModsData = (pathHashes, type = null) => {
  const ids = new Set((Array.isArray(pathHashes) ? pathHashes : [pathHashes]).filter(Boolean))
  const selectedMods = (props.mods || []).filter(mod => ids.has(mod.path_hash))
  if (!type) return selectedMods
  if (type === 'workshop_id') return selectedMods.map(mod => mod.workshop_id).filter(Boolean)
  if (type === 'path') return selectedMods.map(mod => mod.path).filter(Boolean)
  if (type === 'package_id') return selectedMods.map(mod => mod.package_id).filter(Boolean)
  return []
}

const getShortPathLabel = (path, fallback = '缺失记录') => {
  if (!path) return fallback
  const parts = String(path).split(/[\\/]/).filter(Boolean)
  return parts.slice(-2).join('\\') || path
}

const buildJumpMenuItem = (label, icon, targets) => {
  if (!targets.length) return null
  if (targets.length === 1) {
    return {
      label,
      icon,
      action: () => workspaceStore.jumpToMatrixItem(targets[0].path_hash)
    }
  }
  return {
    label: `${label} (${targets.length} 项)`,
    icon,
    children: targets.map(target => ({
      label: `${SOURCE_TYPE_MAP[target.store] || target.store} · ${getShortPathLabel(target.path, target.name || target.package_id)}`,
      icon: CornerUpRight,
      action: () => workspaceStore.jumpToMatrixItem(target.path_hash)
    }))
  }
}

const focusMatrixItem = async (pathHash) => {
  const existsInColumn = (props.mods || []).some(mod => mod.path_hash === pathHash)
  if (!existsInColumn) return

  if (!displayMods.value.some(mod => mod.path_hash === pathHash)) {
    searchQuery.value = ''
    filterState.value = 'default'
  }

  localSelectedIds.value = [pathHash]
  await nextTick()
  vListRef.value?.scrollToKey?.(pathHash)
  requestAnimationFrame(() => {
    vListRef.value?.scrollToKey?.(pathHash)
  })
}

const modsWithState = computed(() => {
  return (props.mods || []).map(mod => ({
    mod,
    state: getMatrixItemState(mod, lastPlayedTime.value, workspaceStore)
  }))
})

const displayMods = computed(() => {
  let list = [...modsWithState.value]

  if (searchQuery.value) {
    const q = searchQuery.value.toLowerCase()
    list = list.filter(({ mod }) =>
      (mod.name || '').toLowerCase().includes(q) ||
      (mod.package_id || '').toLowerCase().includes(q)
    )
  }

  if (filterState.value !== 'default') {
    list = list.filter(({ state }) => matchesMatrixFilter(state, filterState.value))
  }

  list.sort((a, b) => {
    const left = a.mod
    const right = b.mod
    if (sortBy.value === 'name') return (left.name || '').localeCompare(right.name || '')
    if (sortBy.value === 'size') return (right.file_size || 0) - (left.file_size || 0)
    if (sortBy.value === 'mtime') return (right.file_modify_time || 0) - (left.file_modify_time || 0)
    if (sortBy.value === 'ctime') return (right.file_create_time || 0) - (left.file_create_time || 0)
    if (sortBy.value === 'change') {
      if (props.storeType === 'workshop') return (right.steam_status?.time_last_sync || 0) - (left.steam_status?.time_last_sync || 0)
      if (props.storeType === 'self') return (right.steam_status?.time_downloaded || 0) - (left.steam_status?.time_downloaded || 0)
      return (right.file_modify_time || 0) - (left.file_modify_time || 0)
    }
    return 0
  })

  const sortedList = isSortDsc.value ? list : list.reverse()
  return sortedList.map(({ mod }) => mod)
})

watch(
  () => (props.mods || []).map(mod => mod.path_hash),
  (pathHashes) => {
    const validIds = new Set(pathHashes)
    localSelectedIds.value = localSelectedIds.value.filter(pathHash => validIds.has(pathHash))
  },
  { immediate: true }
)

watch(
  () => workspaceStore.matrixFocusTarget,
  async (target) => {
    if (!target || target.store !== props.storeType) return
    await focusMatrixItem(target.pathHash)
  },
  { deep: true }
)

const handleSelect = (pathHashes) => {
  localSelectedIds.value = Array.isArray(pathHashes) ? pathHashes : [pathHashes].filter(Boolean)
}

const unsubscribeMod = async (pathHashes, deleteFile = false) => {
  const paths = getModsData(pathHashes, 'path')
  const workshopIds = getModsData(pathHashes, 'workshop_id')
  if (!workshopIds.length) return

  const check = await confirmStore.confirmAction(
    '警告',
    `确定要取消订阅选中项${deleteFile ? '并删除文件' : ''}（${workshopIds.length} 项）吗？${deleteFile ? '软件将主动删除Mod文件' : 'Steam 会自动删除已取消订阅的文件！'}`,
    { type: 'error' }
  )
  if (!check) return

  const res = await appStore.unsubscribeMod(workshopIds)
  if (res && deleteFile && paths.length) {
    appStore.deletePaths(paths)
  }
}

const downloadMods = async (pathHashes) => {
  const workshopIds = getModsData(pathHashes, 'workshop_id')
  if (!workshopIds.length) return
  await appStore.downloadWorkshopItems(workshopIds)
}

const handleContextMenu = async (event, targetMod) => {
  event.preventDefault()
  if (!targetMod) return

  if (!localSelectedIds.value.includes(targetMod.path_hash)) {
    handleSelect([targetMod.path_hash])
  }

  const selectedMods = getModsData(localSelectedIds.value)
  const selectedWorkshopIds = selectedMods.map(mod => mod.workshop_id).filter(Boolean)
  const selectedPaths = selectedMods.map(mod => mod.path).filter(Boolean)
  const selectedPackageIds = selectedMods.map(mod => mod.package_id).filter(Boolean)
  const selectedNumStr = selectedMods.length > 1 ? ` (${selectedMods.length} 项)` : ''
  const isMissing = !!targetMod.is_missing
  const sameTargets = workspaceStore.getMatrixSameItems(targetMod.path_hash)
  const replacementTargets = getMatrixReplacementTargets(targetMod, workspaceStore)

  const menuItems = []

  // 1. 常规信息操作
  if (!isMissing) {
    menuItems.push({ label: '查看变动', icon: Activity, action: () => emit('open-timeline', targetMod) })
    menuItems.push({ label: '打开文件夹', icon: FolderInput, action: () => appStore.openPath(targetMod.path) })
  }

  const sameJumpItem = buildJumpMenuItem('跳转到相同项', CornerUpRight, sameTargets)
  if (sameJumpItem) menuItems.push(sameJumpItem)

  const replacementJumpItem = buildJumpMenuItem('跳转到替代项', Cable, replacementTargets)
  if (replacementJumpItem) menuItems.push(replacementJumpItem)

  menuItems.push({ divider: true })
  // 2. 跨库物理转移 (Copy / Move)
  if (!isMissing) {
    menuItems.push({
      label: '转移...' + selectedNumStr,
      icon: ArrowRightLeft,
      children: [
        { label: '复制到 游戏本地库', disabled: props.storeType === 'local', icon: Copy, action: () => workspaceStore.modTransfer(localSelectedIds.value, 'local', 'copy') },
        { label: '复制到 管理器库', disabled: props.storeType === 'self', icon: Copy, action: () => workspaceStore.modTransfer(localSelectedIds.value, 'self', 'copy') },
        { label: '复制到 创意工坊库', disabled: props.storeType === 'workshop', icon: Copy, action: () => workspaceStore.modTransfer(localSelectedIds.value, 'workshop', 'copy') },
        { divider: true },
        // 移动操作 (如果是工坊则不可移动)
        { label: '移动到 游戏本地库', disabled: props.storeType === 'local' || props.storeType === 'workshop', icon: FolderInput, action: () => workspaceStore.modTransfer(localSelectedIds.value, 'local', 'move') },
        { label: '移动到 管理器库', disabled: props.storeType === 'self' || props.storeType === 'workshop', icon: FolderInput, action: () => workspaceStore.modTransfer(localSelectedIds.value, 'self', 'move') },
        { label: '移动到 创意工坊库', disabled: props.storeType === 'workshop', icon: FolderInput, action: () => workspaceStore.modTransfer(localSelectedIds.value, 'workshop', 'move') },
      ]
    })
  }
  // 更新
  if (targetMod.steam_status?.needs_update || targetMod.has_update) {
    if (targetMod.store === 'workshop') {
      menuItems.push({ label: '更新模组[再次订阅]' + selectedNumStr, disabled: selectedWorkshopIds.length === 0, icon: Upload, action: () => appStore.subscribeMod(selectedWorkshopIds)
      })
    } else {
      menuItems.push({ label: '更新模组[再次下载]' + selectedNumStr, disabled: selectedWorkshopIds.length === 0, icon: Upload, action: () => downloadMods(localSelectedIds.value)
      })
    }
  }
  menuItems.push({ label: '下载到管理器' + selectedNumStr, disabled: selectedWorkshopIds.length === 0, icon: DownloadCloud, action: () => downloadMods(localSelectedIds.value) })
  // 3. Steam API 相关操作
  menuItems.push({ label: 'Steam操作', icon: IconSteam,
    children: [
      { label: '访问创意工坊', disabled: !targetMod.workshop_id, icon: IconSteam, action: () => appStore.openSteamWorkshopById(targetMod.workshop_id) },
      { label: '订阅模组' + selectedNumStr, disabled: selectedWorkshopIds.length === 0 || (!!targetMod.steam_status?.is_subscribed && selectedWorkshopIds.length === 1), icon: Flag, action: () => appStore.subscribeMod(selectedWorkshopIds) },
      { label: '取消订阅' + selectedNumStr, disabled: props.storeType !== 'workshop' || selectedWorkshopIds.length === 0, icon: FlagOff, level: 'danger', action: () => unsubscribeMod(localSelectedIds.value, false) },
    ]
  })

  // 4. 破坏性操作
  menuItems.push({ divider: true })
  if(!isMissing) {
    menuItems.push({ label: targetMod.disabled ? '解禁' : '禁用' + selectedNumStr, icon: targetMod.disabled ? LockOpen : Lock, level: 'warn', action: () => modStore.disableMods(localSelectedIds.value, !targetMod.disabled) })
    menuItems.push({ label: '删除文件' + selectedNumStr, icon: Trash2, level: 'danger', action: () => appStore.deletePaths(getModsData(localSelectedIds.value, 'path')) })
  } else {
    // 对于缺失项，提供一键清除幽灵记录的功能（取消订阅）
    menuItems.push({ label: '清理此失效订阅' + selectedNumStr, icon: Trash2, level: 'danger', action: () => unsubscribeMod(localSelectedIds.value, false) })
  }

  menuStore.open(event, menuItems)
}
</script>
