<!-- src/components/workspace/views/MatrixColumn.vue -->
<template>
  <div class="flex-1 flex flex-col bg-bg-inset/70 border border-border-base/10 rounded-2xl overflow-hidden shadow-2xl relative"
    :class="{ 'brightness-60 grayscale pointer-events-none': disabled }">
    <div class="px-4 py-3 bg-bg-overlay/5 border-b border-border-base/10 flex flex-col gap-3" :data-tour="'workspace-'+storeType + '-toolbar'">
      <div class="flex items-center justify-between">
        <div class="flex gap-1">
          <h3 class="text-sm font-bold text-text-main flex items-center gap-2 cursor-help" v-tooltip="tooltip">
            <div class="w-2.5 h-2.5 rounded-full shadow-lg" :class="iconColor.replace('text-', 'bg-')"></div>
            {{ title }}
          </h3>
          <CommonSwitch v-if="storeType === 'workshop' && canToggleWorkshopMods" label="" mini class="text-text-dim" :disabled="workshopSwitchDisabled"
            v-model="use_workshop_mods" :description="t('ui.workspace.matrix.switch.workshop.description', '适用于非 Steam 版环境。为当前环境使用创意工坊模组，启用后将通过链接方式自动为游戏添加创意工坊模组。（前提是账号拥有游戏，或创意工坊内容本身可正常使用。）')" />
          <CommonSwitch v-else-if="storeType === 'self'" label=" " mini class="text-text-dim"
            v-model="use_self_mods" :description="t('ui.workspace.matrix.switch.self.description', '为当前环境使用管理器Mod，启用后将通过链接方式自动为游戏添加管理器 Mod。')" />
          <CommonSwitch v-if="storeType === 'local'" :label="t('ui.workspace.matrix.switch.show_official.label', '· 显示官方')" mini class="text-text-dim"
            v-model="showOfficialLocalModsModel" :description="t('ui.workspace.matrix.switch.show_official.description', '默认隐藏 Core/DLC 等官方项目；隐藏时不会进入本地列表和多选范围。')" />
        </div>

        <div class="flex gap-2">
          <span class="text-[0.65rem] font-mono text-text-dim bg-bg-inset/80 px-2 py-0.5 rounded-md border border-border-base/5">
            {{ formatFileSize(columnSize) }}
          </span>
          <span class="text-[0.65rem] font-mono text-text-main bg-bg-inset/80 px-2 py-0.5 rounded-md border border-border-base/5">
            {{ t('common.count.items', '{count} 项', { count: mods.length }) }}
          </span>
        </div>
      </div>

      <div class="flex flex-col items-center gap-2">
        <div class="relative w-full">
          <input v-model="searchQuery" :placeholder="t('ui.workspace.matrix.search.placeholder', '在此域检索...')"
            class="w-full bg-bg-inset border border-border-base/10 rounded-lg pl-3 pr-2 py-1.5 text-xs text-text-main focus:border-accent-primary outline-none transition-colors"
          />
        </div>
        <div class="flex items-center w-full justify-end gap-2">
          <CommonSelect v-model="filterState" mini :options="matrixFilterStateOptions" />

          <CommonSelect v-model="sortBy" mini
            :options="matrixSortOptions"
          />

          <Motion :class="`p-1 size-7 rounded-md bg-bg-overlay/5 border border-border-base/10 hover:text-text-main hover:bg-bg-overlay/10 text-xs font-bold flex items-center justify-center cursor-pointer `"
            :initial="{ rotateX: 0, opacity: 1 }"
            :animate="{ rotateX: isSortDsc ? 0 : 180 }"
            :transition="{ type: 'spring', stiffness: 300, damping: 20 }"
            @click="isSortDsc=!isSortDsc"
            v-tooltip="isSortDsc ? t('tooltip.common.sort_asc', '切换为升序排列') : t('tooltip.common.sort_desc', '切换为降序排列')"
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
      <div v-if="displayMods.length > 0" ref="scrollRef"
        class="relative h-full overflow-auto custom-scrollbar pb-10"
        v-selectable-list="{
          data: displayPathHashes,
          selectedIds: localSelectedPathHashes,
          onSelect: handleSelect,
          onClear: clearSelection,
          clickClass: 'matrix-select-trigger',
          swipeClass: 'matrix-select-trigger',
          idAttribute: 'data-id'
        }"
      >
        <!--
          矩阵列只需要虚拟滚动，不需要拖拽。
          这里直接使用 TanStack Virtual，避免为了“禁用拖拽”保留额外的列表库。
          外层总高度负责撑开滚动条，可见行用 translateY 放回真实位置；vSelection 仍绑定在滚动容器上。
        -->
        <div :style="{ height: `${totalSize}px`, position: 'relative' }">
          <div
            v-for="virtualRow in virtualRows"
            :key="displayMods[virtualRow.index]?.path_hash || virtualRow.index"
            class="absolute left-0 right-0"
            :style="{ transform: `translateY(${virtualRow.start}px)`, height: `${virtualRow.size}px` }"
          >
            <MatrixItem class="timeline-trigger h-full" :mod="displayMods[virtualRow.index]" :storeType="storeType"
              :lastPlayedTime="lastPlayedTime" :isSelected="localSelectedPathHashes.includes(displayMods[virtualRow.index]?.path_hash)"
              :lastRunTime="lastRunTime"
              @contextmenu="handleContextMenu" @click="$emit('open-timeline', displayMods[virtualRow.index])"
            />
          </div>
        </div>
      </div>

      <div v-else class="absolute inset-0 flex flex-col items-center justify-center text-text-disabled">
        <svg class="size-12 mb-2 opacity-20" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4" /></svg>
        <span class="text-xs font-bold tracking-widest uppercase">{{ t('ui.workspace.matrix.empty', '库内暂无数据') }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { useVirtualizer } from '@tanstack/vue-virtual'
import { Motion } from 'motion-v'
import { Activity, ArrowRightLeft, Cable, Copy, CornerUpRight, DownloadCloud, Flag, FlagOff, FolderInput, Lock, LockOpen, Download, Trash2, Upload } from 'lucide-vue-next'
import CommonSelect from '../../../shared/components/input/CommonSelect.vue'
import MatrixItem from '../components/MatrixItem.vue'
import { useAppStore } from '../../../app/stores/appStore'
import { useConfirmStore } from '../../../shared/components/modal/confirmStore'
import { useContextMenuStore } from '../../../shared/components/context-menu/contextMenuStore'
import { useModStore } from '../../mod/stores/modStore'
import { useProfileStore } from '../../profiles/profileStore'
import { useWorkspaceStore } from '../workspaceStore'
import { IconSteam, getSourceTypeLabel } from '../../../shared/lib/constants'
import { formatFileSize } from '../../../shared/lib/format'
import { checkResult, toast } from '../../../shared/lib/common'
import { getMatrixItemState, getMatrixMeaningfulChangeTime, getMatrixReplacementTargets, getMatrixFilterStateOptions, isMatrixModAvailable, isMatrixModUnavailable, matchesMatrixFilter } from '../lib/matrixItemState'
import CommonSwitch from '../../../shared/components/input/CommonSwitch.vue'
import { buildModExternalMenuItem, copyTextToClipboard } from '../../mod/lib/modContextMenuItems'
import { t } from '../../../shared/i18n'

const props = defineProps({
  title: String,
  iconColor: String,
  storeType: String,
  mods: {
    type: Array,
    default: () => []
  },
  showOfficialLocalMods: Boolean,
  tooltip: String,
  disabled: Boolean
})

const emit = defineEmits(['open-timeline', 'update:show-official-local-mods'])
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
const localSelectedPathHashes = ref([])
const scrollRef = ref(null)
const columnSize = computed(() => (props.mods || []).reduce((acc, mod) => acc + (mod.file_size || 0), 0))
const matrixFilterStateOptions = computed(() => getMatrixFilterStateOptions())
const matrixSortOptions = computed(() => [
  { label: t('ui.workspace.matrix.sort.change', '按变动时间'), value: 'change' },
  { label: t('ui.workspace.matrix.sort.mtime', '按修改时间'), value: 'mtime' },
  { label: t('ui.workspace.matrix.sort.ctime', '按创建时间'), value: 'ctime' },
  { label: t('ui.workspace.matrix.sort.size', '按文件体积'), value: 'size' },
  { label: t('ui.workspace.matrix.sort.name', '按名称 A-Z'), value: 'name' },
])

const lastPlayedTime = computed(() => profileStore.currentProfile?.last_played_time || 0)
const lastRunTime = computed(() => appStore.settings?.last_run_time || 0)
const hasWorkshopLibrary = computed(() => !!appStore.settings.workshop_mods_path)
const canToggleWorkshopMods = computed(() => hasWorkshopLibrary.value)
const workshopSwitchDisabled = computed(() => !!profileStore.currentProfile?.prefer_steam_launch)
const use_workshop_mods = computed({
  get() {
    return !!profileStore.currentProfile?.use_workshop_mods
  },
  set(val) {
    profileStore.updateProfile(profileStore.currentProfileId, { use_workshop_mods: val })
  }
})
const use_self_mods = computed({
  get() {
    return profileStore.currentProfile?.use_self_mods || false
  },
  set(val) {
    profileStore.updateProfile(profileStore.currentProfileId, { use_self_mods: val })
  }
})
const showOfficialLocalModsModel = computed({
  get() {
    return !!props.showOfficialLocalMods
  },
  set(val) {
    emit('update:show-official-local-mods', !!val)
  }
})

const clearSelection = () => {
  localSelectedPathHashes.value = []
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

const getShortPathLabel = (path, fallback = t('ui.workspace.matrix.path.missing_record', '缺失记录')) => {
  if (!path) return fallback
  const parts = String(path).split(/[\\/]/).filter(Boolean)
  return parts.slice(-2).join('\\') || path
}

const buildCountText = (count) => count > 1 ? t('common.count.suffix_spaced', ' ({count} 项)', { count }) : ''
const getUniquePathHashes = (mods) => [...new Set((mods || [])
  .map(mod => String(mod?.path_hash || '').trim())
  .filter(Boolean))]
const getUniqueWorkshopIds = (mods) => [...new Set((mods || [])
  .map(mod => String(mod?.workshop_id || '').trim())
  .filter(Boolean))]

const buildJumpMenuItem = (label, icon, targets) => {
  if (!targets.length) return null
  if (targets.length === 1) {
    return { label, icon, action: () => workspaceStore.jumpToMatrixItem(targets[0].path_hash) }
  }
  return { label: t('ui.workspace.matrix.menu.jump_group_label', '{label} ({count} 项)', { label, count: targets.length }), icon,
    children: targets.map(target => ({
      label: t('ui.workspace.matrix.menu.jump_target_label', '{source} · {path}', { source: getSourceTypeLabel(target.store), path: getShortPathLabel(target.path, target.name || target.package_id) }),
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

  localSelectedPathHashes.value = [pathHash]
  await nextTick()
  scrollToPathHash(pathHash)
  requestAnimationFrame(() => {
    scrollToPathHash(pathHash)
  })
}

const scrollToPathHash = (pathHash) => {
  const index = displayMods.value.findIndex(mod => mod.path_hash === pathHash)
  if (index === -1) return
  virtualizer.value.scrollToIndex(index, { align: 'center' })
}

const modsWithState = computed(() => {
  return (props.mods || []).map(mod => ({
    mod,
    state: getMatrixItemState(mod, lastPlayedTime.value, workspaceStore, lastRunTime.value)
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
      return getMatrixMeaningfulChangeTime(right) - getMatrixMeaningfulChangeTime(left)
    }
    return 0
  })

  const sortedList = isSortDsc.value ? list : list.reverse()
  return sortedList.map(({ mod }) => mod)
})
// vSelection 只需要有序 ID 列表；单独缓存避免每次模板渲染都重新 map。
const displayPathHashes = computed(() => displayMods.value.map(mod => mod.path_hash))

const matrixRowHeight = computed(() => appStore.scalePx(62))
const virtualizer = useVirtualizer(computed(() => ({
  count: displayMods.value.length,
  getScrollElement: () => scrollRef.value,
  estimateSize: () => matrixRowHeight.value,
  overscan: 10,
})))
const virtualRows = computed(() => virtualizer.value.getVirtualItems())
const totalSize = computed(() => virtualizer.value.getTotalSize())

watch([matrixRowHeight, () => displayMods.value.length], async () => {
  await nextTick()
  // 切换排序、筛选或全局缩放后刷新估算缓存，避免虚拟行高度沿用旧值造成半行裁切。
  virtualizer.value.measure()
})

watch(
  () => (props.mods || []).map(mod => mod.path_hash),
  (pathHashes) => {
    const validIds = new Set(pathHashes)
    localSelectedPathHashes.value = localSelectedPathHashes.value.filter(pathHash => validIds.has(pathHash))
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

watch(
  () => workspaceStore.matrixFilterTarget,
  async (target) => {
    if (!target || (target.store !== 'all' && target.store !== props.storeType)) return
    const pathHashes = Array.isArray(target.pathHashes) ? target.pathHashes.filter(Boolean) : []
    searchQuery.value = ''
    filterState.value = target.filterState || 'default'
    if (!pathHashes.length) return
    const targetIds = new Set(pathHashes)
    let visiblePathHashes = displayMods.value
      .filter(mod => targetIds.has(mod.path_hash))
      .map(mod => mod.path_hash)
    if (!visiblePathHashes.length && (props.mods || []).some(mod => targetIds.has(mod.path_hash))) {
      filterState.value = 'default'
      await nextTick()
      visiblePathHashes = displayMods.value
        .filter(mod => targetIds.has(mod.path_hash))
        .map(mod => mod.path_hash)
    }
    if (!visiblePathHashes.length) return
    localSelectedPathHashes.value = visiblePathHashes
    await nextTick()
    scrollToPathHash(visiblePathHashes[0])
    requestAnimationFrame(() => {
      scrollToPathHash(visiblePathHashes[0])
    })
  },
  { deep: true, immediate: true }
)

const handleSelect = (pathHashes) => {
  localSelectedPathHashes.value = Array.isArray(pathHashes) ? pathHashes : [pathHashes].filter(Boolean)
}

const refreshCoreAfterInventoryChange = async (label = t('ui.workspace.matrix.refresh_after_inventory_change', '库存变更后同步模组数据')) => {
  await appStore.refreshModCoreData(label, {
    preserveListState: true,
    refreshRules: false,
    refreshBackups: false,
    refreshWorkspaceLibraries: false,
  })
}

const unsubscribeWorkshopIds = async (pathHashes, deleteFile = false) => {
  const hashes = [...new Set((Array.isArray(pathHashes) ? pathHashes : [pathHashes])
    .map(pathHash => String(pathHash || '').trim())
    .filter(Boolean))]
  const workshopIds = [...new Set(getModsData(hashes, 'workshop_id')
    .map(workshopId => String(workshopId || '').trim())
    .filter(Boolean))]
  if (!workshopIds.length) return

  const ok = await appStore.unsubscribeWorkshopIds(workshopIds, hashes, { deleteFiles: !!deleteFile })
  if (ok) {
    await workspaceStore.fetchLibrariesMods()
    await refreshCoreAfterInventoryChange(t('ui.workspace.matrix.refresh_after_unsubscribe', '取消订阅后同步模组数据'))
  }
}

const unsubscribeAndClearMissingWorkshopRecords = async (mods) => {
  const targets = (mods || []).filter(mod => mod?.is_missing && mod?.workshop_id && mod?.steam_status?.is_subscribed === true)
  const workshopIds = getUniqueWorkshopIds(targets)
  if (!workshopIds.length) return false

  const check = await confirmStore.confirmAction(
    t('ui.workspace.matrix.cleanup_invalid_unsubscribe.title', '清理失效并取消订阅'),
    t('ui.workspace.matrix.cleanup_invalid_unsubscribe.message', '确定要取消订阅这些异常缺失的工坊项并清理本地记录吗？（{count} 项）', { count: workshopIds.length }),
    { type: 'error' }
  )
  if (!check) return false

  const ok = await appStore.unsubscribeWorkshopIds(workshopIds, null, { skipConfirm: true })
  if (!ok) return false

  const recordHashes = getUniquePathHashes(targets).filter(pathHash => !pathHash.startsWith('ghost_'))
  if (recordHashes.length > 0) {
    const res = await window.pywebview.api.mods_delete(recordHashes, false, false)
    if (!checkResult(res, t('ui.workspace.matrix.action.clean_missing_records', '清理缺失数据记录'))) return false
  }

  await workspaceStore.fetchLibrariesMods()
  await refreshCoreAfterInventoryChange(t('ui.workspace.matrix.refresh_after_clean_missing_records', '清理缺失记录后同步模组数据'))
  return true
}

const resubscribeMissingWorkshopItems = async (mods) => {
  const targets = (mods || []).filter(mod => mod?.is_missing && mod?.workshop_id && mod?.steam_status?.is_subscribed === true)
  const workshopIds = getUniqueWorkshopIds(targets)
  if (!workshopIds.length) return false

  const check = await confirmStore.confirmAction(
    t('ui.workspace.matrix.resubscribe_missing.title', '重新订阅缺失项'),
    t('ui.workspace.matrix.resubscribe_missing.message', '将处理 {count} 个仍处于订阅状态但本地文件缺失的工坊项。\n\n此操作会先向 Steam 发送取消订阅请求，并等待 Steam 返回成功；随后再重新发送订阅请求，让 Steam 重新拉取这些项目。\n\n由于 Steam 客户端和网络状态不可控，过程中可能出现取消订阅成功但重新订阅失败、Steam 下载排队较久、或列表刷新延迟。执行后请等待 Steam 下载完成，再刷新库存或重新扫描。', { count: workshopIds.length }),
    { type: 'warning', confirmText: t('ui.workspace.matrix.resubscribe_missing.confirm', '开始重新订阅'), cancelText: t('common.action.cancel', '取消') }
  )
  if (!check) return false

  const unsubscribeResult = await appStore.unsubscribeWorkshopIds(workshopIds, null, { skipConfirm: true })
  if (!unsubscribeResult) return false

  const subscribeResult = await appStore.subscribeWorkshopIds(workshopIds)
  if (!subscribeResult) return false

  toast.success(t('ui.workspace.matrix.resubscribe_missing.success', '已重新发送 {count} 个缺失项的订阅请求，请等待 Steam 下载完成', { count: workshopIds.length }))
  await workspaceStore.fetchLibrariesMods()
  return true
}

const downloadMissingWorkshopItemsViaSteam = async (mods) => {
  const targets = (mods || []).filter(mod => mod?.is_missing && mod?.workshop_id && mod?.steam_status?.is_subscribed === true)
  const workshopIds = getUniqueWorkshopIds(targets)
  if (!workshopIds.length) return false

  const check = await confirmStore.confirmAction(
    t('ui.workspace.matrix.download_missing.title', 'Steam 下载缺失项'),
    t('ui.workspace.matrix.download_missing.message', '将处理 {count} 个仍处于订阅状态但本地文件缺失的工坊项。\n\n此操作不会取消订阅，而是直接请求 Steam 客户端重新下载或校验这些项目，并在任务栏等待 Steam 确认本地文件已下载完成。\n\n如果 Steam 网络异常、下载排队过久或项目本身不可用，任务会显示失败。', { count: workshopIds.length }),
    { type: 'warning', confirmText: t('ui.workspace.matrix.download_missing.confirm', '请求 Steam 下载'), cancelText: t('common.action.cancel', '取消') }
  )
  if (!check) return false

  const result = await appStore.downloadWorkshopItemsViaSteam(workshopIds, { highPriority: true, waitSeconds: 30 })
  if (!result) return false

  await workspaceStore.fetchLibrariesMods()
  return true
}

const clearMissingRecords = async (pathHashes) => {
  if (!window.pywebview) return false
  const hashes = (Array.isArray(pathHashes) ? pathHashes : [pathHashes]).filter(Boolean)
  if (!hashes.length) return false

  const check = await confirmStore.confirmAction(
    t('ui.workspace.matrix.clean_records.title', '清理数据记录'),
    t('ui.workspace.matrix.clean_records.message', '确定要清理选中异常项的数据记录吗？（{count} 项）\n这不会取消 Steam 订阅，也不会删除任何仍存在的文件。', { count: hashes.length }),
    { type: 'warning' }
  )
  if (!check) return false

  const res = await window.pywebview.api.mods_delete(hashes, false, false)
  if (checkResult(res, t('ui.workspace.matrix.action.clean_records', '清理数据记录'))) {
    toast.success(t('ui.workspace.matrix.clean_records.success', '已清理 {count} 条数据记录', { count: res.data?.success_count || hashes.length }))
    await workspaceStore.fetchLibrariesMods()
    await refreshCoreAfterInventoryChange(t('ui.workspace.matrix.refresh_after_clean_records', '清理库存记录后同步模组数据'))
    return true
  }
  return false
}

const buildMatrixCopyMenuItem = (selectedMods) => {
  const selectedNumStr = buildCountText(selectedMods.length)
  const copyField = (label, getter) => {
    const lines = selectedMods.map(mod => String(getter(mod) || '').trim()).filter(Boolean)
    return {
      label: t('ui.workspace.matrix.menu.copy_field', '复制{field}{count}', { field: label, count: selectedNumStr }),
      icon: Copy,
      disabled: lines.length === 0,
      action: () => copyTextToClipboard(lines.join('\n'), label),
    }
  }
  return {
    label: t('ui.workspace.matrix.menu.copy_info', '复制信息{count}', { count: selectedNumStr }),
    icon: Copy,
    disabled: selectedMods.length === 0,
    children: [
      copyField(t('common.field.name', '名称'), mod => mod.alias_name || mod.display_name || mod.name || mod.package_id),
      copyField(t('common.field.package_id', '包名'), mod => mod.package_id),
      copyField(t('common.field.workshop_id', '工坊 ID'), mod => mod.workshop_id),
      copyField(t('common.field.path', '路径'), mod => mod.path),
    ],
  }
}

const handleContextMenu = async (event, targetMod) => {
  event.preventDefault()
  if (!targetMod) return

  if (!localSelectedPathHashes.value.includes(targetMod.path_hash)) {
    handleSelect([targetMod.path_hash])
  }

  const selectedMods = getModsData(localSelectedPathHashes.value)
  const selectedWorkshopIds = getUniqueWorkshopIds(selectedMods)
  const selectedWorkshopNumStr = buildCountText(selectedWorkshopIds.length)
  const selectedAvailableMods = selectedMods.filter(isMatrixModAvailable)
  const selectedAvailablePathHashes = getUniquePathHashes(selectedAvailableMods)
  const selectedAvailableNumStr = buildCountText(selectedAvailablePathHashes.length)
  const selectedUpdatedWorkshopIds = getUniqueWorkshopIds(selectedMods.filter(mod => (mod?.steam_status?.needs_update || mod?.has_update) && mod?.workshop_id))
  const selectedUpdatedNumStr = buildCountText(selectedUpdatedWorkshopIds.length)
  const selectedSubscribableWorkshopIds = getUniqueWorkshopIds(selectedMods.filter(mod => mod?.workshop_id && mod?.steam_status?.is_subscribed !== true))
  const selectedSubscribableNumStr = buildCountText(selectedSubscribableWorkshopIds.length)
  const selectedSubscribedWorkshopMods = selectedMods.filter(mod => isMatrixModAvailable(mod) && mod?.workshop_id && mod?.steam_status?.is_subscribed === true)
  const selectedSubscribedWorkshopIds = getUniqueWorkshopIds(selectedSubscribedWorkshopMods)
  const selectedSubscribedWorkshopPathHashes = getUniquePathHashes(selectedSubscribedWorkshopMods)
  const selectedSubscribedWorkshopNumStr = buildCountText(selectedSubscribedWorkshopIds.length)
  const targetUnavailable = isMatrixModUnavailable(targetMod)
  const selectedSubscribedMissingMods = selectedMods.filter(mod => mod?.is_missing && mod?.steam_status?.is_subscribed === true && mod?.workshop_id)
  const selectedSubscribedMissingWorkshopIds = getUniqueWorkshopIds(selectedSubscribedMissingMods)
  const selectedSubscribedMissingHashSet = new Set(getUniquePathHashes(selectedSubscribedMissingMods))
  const selectedRecordCleanupPathHashes = getUniquePathHashes(
    selectedMods.filter(mod => isMatrixModUnavailable(mod) && !selectedSubscribedMissingHashSet.has(String(mod?.path_hash || '').trim()))
  ).filter(pathHash => !pathHash.startsWith('ghost_'))
  const selectedRecordCleanupNumStr = buildCountText(selectedRecordCleanupPathHashes.length)
  const selectedSubscribedMissingNumStr = buildCountText(selectedSubscribedMissingWorkshopIds.length)
  const sameTargets = workspaceStore.getMatrixSameItems(targetMod.path_hash)
  const replacementTargets = getMatrixReplacementTargets(targetMod, workspaceStore)

  const menuItems = []
  const transferTargets = [
    { label: t('ui.workspace.matrix.menu.copy_to_local', '复制到 游戏本地库'), disabled: props.storeType === 'local', icon: Copy, action: () => workspaceStore.modTransfer(selectedAvailablePathHashes, 'local', 'copy') },
    { label: t('ui.workspace.matrix.menu.copy_to_self', '复制到 管理器库'), disabled: props.storeType === 'self', icon: Copy, action: () => workspaceStore.modTransfer(selectedAvailablePathHashes, 'self', 'copy') },
  ]
  const moveTargets = [
    { label: t('ui.workspace.matrix.menu.move_to_local', '移动到 游戏本地库'), disabled: props.storeType === 'local' || props.storeType === 'workshop', icon: ArrowRightLeft, action: () => workspaceStore.modTransfer(selectedAvailablePathHashes, 'local', 'move') },
    { label: t('ui.workspace.matrix.menu.move_to_self', '移动到 管理器库'), disabled: props.storeType === 'self' || props.storeType === 'workshop', icon: ArrowRightLeft, action: () => workspaceStore.modTransfer(selectedAvailablePathHashes, 'self', 'move') },
  ]
  if (hasWorkshopLibrary.value) {
    // 工坊库路径缺失时，这类入口会把用户带到一个并不存在的落点；
    // 因此这里直接不渲染“转入工坊库”的菜单项，避免出现隐藏列仍可操作的残留入口。
    transferTargets.push({ label: t('ui.workspace.matrix.menu.copy_to_workshop', '复制到 创意工坊库'), disabled: props.storeType === 'workshop', icon: Copy, action: () => workspaceStore.modTransfer(selectedAvailablePathHashes, 'workshop', 'copy') })
    moveTargets.push({ label: t('ui.workspace.matrix.menu.move_to_workshop', '移动到 创意工坊库'), disabled: props.storeType === 'workshop', icon: ArrowRightLeft, action: () => workspaceStore.modTransfer(selectedAvailablePathHashes, 'workshop', 'move') })
  }

  // 1. 常规信息操作
  if (!targetUnavailable) {
    menuItems.push({ label: t('ui.workspace.matrix.menu.view_timeline', '查看变动'), icon: Activity, action: () => emit('open-timeline', targetMod) })
    menuItems.push({ label: t('common.action.open_folder', '打开文件夹'), icon: FolderInput, action: () => appStore.openPath(targetMod.path) })
  }
  menuItems.push(buildMatrixCopyMenuItem(selectedMods))
  menuItems.push(buildModExternalMenuItem(targetMod, appStore, { label: t('common.action.visit_page', '访问页面') }))

  const sameJumpItem = buildJumpMenuItem(t('ui.workspace.matrix.menu.jump_same', '跳转到相同项'), CornerUpRight, sameTargets)
  if (sameJumpItem) menuItems.push(sameJumpItem)

  const replacementJumpItem = buildJumpMenuItem(t('ui.workspace.matrix.menu.jump_replacement', '跳转到替代项'), Cable, replacementTargets)
  if (replacementJumpItem) menuItems.push(replacementJumpItem)

  menuItems.push({ divider: true })
  // 2. 跨库物理转移 (Copy / Move)
  if (selectedAvailablePathHashes.length > 0) {
    menuItems.push({
      label: t('ui.workspace.matrix.menu.transfer', '转移...{count}', { count: selectedAvailableNumStr }),
      icon: ArrowRightLeft,
      children: [
        ...transferTargets,
        { divider: true },
        // 移动操作对工坊源本身仍保持禁用；这里只额外收口“目标工坊库不存在”的情况。
        ...moveTargets,
      ]
    })
  }
  // 更新
  if (selectedUpdatedWorkshopIds.length > 0) {
    if (props.storeType === 'workshop') {
      menuItems.push({ label: t('ui.workspace.matrix.menu.update_resubscribe', '更新模组[再次订阅]{count}', { count: selectedUpdatedNumStr }), icon: Upload, action: () => appStore.subscribeWorkshopIds(selectedUpdatedWorkshopIds)
      })
    } else {
      menuItems.push({ label: t('ui.workspace.matrix.menu.update_redownload', '更新模组[再次下载]{count}', { count: selectedUpdatedNumStr }), icon: Upload, action: () => appStore.downloadWorkshopItems(selectedUpdatedWorkshopIds)
      })
    }
  }
  menuItems.push({ label: t('ui.workspace.matrix.menu.download_to_self', '下载到管理器{count}', { count: selectedWorkshopNumStr }), disabled: selectedWorkshopIds.length === 0, icon: Download, action: () => appStore.downloadWorkshopItems(selectedWorkshopIds) })
  // 3. Steam API 相关操作
  const steamMenuChildren = [
    { label: t('ui.workspace.matrix.menu.open_workshop', '访问创意工坊'), disabled: !targetMod.workshop_id, icon: IconSteam, action: () => appStore.openSteamWorkshopById(targetMod.workshop_id) },
    { label: t('ui.workspace.matrix.menu.subscribe_mod', '订阅模组{count}', { count: selectedSubscribableNumStr }), disabled: selectedSubscribableWorkshopIds.length === 0, icon: Flag, action: () => appStore.subscribeWorkshopIds(selectedSubscribableWorkshopIds) },
  ]
  steamMenuChildren.push({ label: t('ui.workspace.matrix.menu.unsubscribe', '取消订阅{count}', { count: selectedSubscribedWorkshopNumStr }), disabled: props.storeType !== 'workshop' || selectedSubscribedWorkshopIds.length === 0, icon: FlagOff, level: 'danger', action: () => unsubscribeWorkshopIds(selectedSubscribedWorkshopPathHashes, false) })
  menuItems.push({ label: t('ui.workspace.matrix.menu.steam_actions', 'Steam操作'), icon: IconSteam, children: steamMenuChildren })

  // 4. 破坏性操作
  menuItems.push({ divider: true })
  if (selectedAvailablePathHashes.length > 0) {
    const shouldEnableSelected = selectedAvailableMods.every(mod => mod?.disabled)
    menuItems.push({ label: shouldEnableSelected ? t('ui.workspace.matrix.menu.activate', '解禁{count}', { count: selectedAvailableNumStr }) : t('ui.workspace.matrix.menu.deactivate', '禁用{count}', { count: selectedAvailableNumStr }), icon: shouldEnableSelected ? LockOpen : Lock, level: 'warn', action: () => modStore.disableMods(selectedAvailablePathHashes, !shouldEnableSelected) })
    menuItems.push({ label: t('ui.workspace.matrix.menu.delete_files', '删除文件{count}', { count: selectedAvailableNumStr }), icon: Trash2, level: 'danger', action: () => modStore.deleteMods(selectedAvailablePathHashes) })
  }
  if (props.storeType === 'workshop' && selectedSubscribedMissingMods.length > 0) {
    // 工坊列中仍处于订阅状态的缺失项，代表“订阅还在但文件异常丢失”。
    menuItems.push(
      {
        label: t('ui.workspace.matrix.menu.redownload_missing.label', '重新下载缺失项{count}', { count: selectedSubscribedMissingNumStr }), level: 'success', icon: DownloadCloud,
        tooltip: t('ui.workspace.matrix.menu.redownload_missing.tooltip', '直接请求 Steam 重新下载或校验这些缺失项。'),
        action: () => downloadMissingWorkshopItemsViaSteam(selectedSubscribedMissingMods),
      },
      {
        label: t('ui.workspace.matrix.menu.resubscribe_missing.label', '重新订阅缺失项{count}', { count: selectedSubscribedMissingNumStr }), level: 'warn', icon: Flag,
        tooltip: t('ui.workspace.matrix.menu.resubscribe_missing.tooltip', '先取消订阅，再重新订阅，让 Steam 重新排队获取这些缺失项。\n此操作会改变订阅状态，网络异常时可能出现取消成功但重新订阅失败，请谨慎使用。'),
        action: () => resubscribeMissingWorkshopItems(selectedSubscribedMissingMods),
      },
      { label: t('ui.workspace.matrix.menu.clean_invalid_unsubscribe', '清理失效并取消订阅{count}', { count: selectedSubscribedMissingNumStr }), icon: Trash2, level: 'danger', action: () => unsubscribeAndClearMissingWorkshopRecords(selectedSubscribedMissingMods) }
    )
  }
  if (selectedRecordCleanupPathHashes.length > 0) {
    menuItems.push({ label: t('ui.workspace.matrix.menu.clean_records', '清理数据记录{count}', { count: selectedRecordCleanupNumStr }), icon: Trash2, level: 'danger', action: () => clearMissingRecords(selectedRecordCleanupPathHashes) })
  }

  menuStore.open(event, menuItems)
}
</script>
