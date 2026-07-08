<template>
  <CommonModalShell :show="appStore.uiState.showModResidueCleanup" :title="t('dialog.mod_residue.title', '卸载残留清理')"
    :description="t('dialog.mod_residue.description', '这里会列出已卸载模组留下的文件夹和设置文件。勾选后可移入回收站或彻底删除。')"
    size="page" :z-index="125" accent="danger" content-class="h-full" @close="closeModal">
    <template #header-actions>
      <button class="rounded-lg border border-border-base/10 bg-bg-overlay/5 px-3 py-2 text-xs font-bold text-text-main transition-colors hover:bg-bg-overlay/10 disabled:opacity-50"
        :disabled="store.loading" v-tooltip="t('dialog.mod_residue.recheck_tip', '重新检查当前环境的卸载残留')" @click="store.loadOverview()">
        <RefreshCw class="mr-1 inline size-3.5" />
        {{ t('dialog.mod_residue.recheck', '重新检查') }}
      </button>
      <button class="rounded-lg border border-border-base/10 bg-bg-overlay/5 px-3 py-2 text-xs font-bold text-text-main transition-colors hover:bg-bg-overlay/10"
        v-tooltip="t('dialog.mod_residue.whitelist_tip', '查看不会再提示的残留，也可以从白名单移除')" @click="showWhitelist = !showWhitelist">
        <Shield class="mr-1 inline size-3.5" />
        {{ t('dialog.mod_residue.whitelist_count', '白名单 {count}', { count: store.summary.whitelist_count || 0 }) }}
      </button>
      <button class="rounded-lg border border-accent-danger/35 bg-accent-danger/10 px-3 py-2 text-xs font-bold text-accent-danger transition-colors hover:bg-accent-danger/18 disabled:opacity-50"
        :disabled="selectedItems.length === 0 || cleaning" v-tooltip="t('dialog.mod_residue.clean_selected_tip', '清理已勾选的残留文件夹和设置文件')" @click="cleanSelected">
        <Trash2 class="mr-1 inline size-3.5" />
        {{ t('dialog.mod_residue.clean_selected_count', '清理已选 {count}', { count: selectedItems.length }) }}
      </button>
    </template>

    <div class="grid h-full min-h-0 overflow-hidden" :class="showWhitelist ? 'grid-cols-[minmax(0,1fr)_22rem]' : 'grid-cols-1'">
      <section class="flex min-h-0 flex-col overflow-hidden">
        <div class="flex flex-wrap items-center justify-between gap-3 border-b border-border-base/10 bg-bg-muted px-5 py-3">
          <div class="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-text-dim">
            <span>{{ t('dialog.mod_residue.mod_count', '模组 {count}', { count: store.summary.group_count || 0 }) }}</span>
            <span>{{ t('dialog.mod_residue.pending_count', '待清理 {count}', { count: store.summary.item_count || 0 }) }}</span>
            <span>{{ t('dialog.mod_residue.folder_count', '文件夹 {count}', { count: store.summary.directory_count || 0 }) }}</span>
            <span>{{ t('dialog.mod_residue.settings_file_count', '设置文件 {count}', { count: store.summary.settings_file_count || 0 }) }}</span>
            <span>{{ t('dialog.mod_residue.file_count', '文件 {count}', { count: store.summary.file_count || 0 }) }}</span>
            <span>{{ t('dialog.mod_residue.size_total', '占用 {size}', { size: formatFileSize(store.summary.total_size || 0) }) }}</span>
          </div>
          <div class="flex items-center gap-2">
            <button class="rounded-md border border-border-base/10 px-3 py-1.5 text-xs font-bold text-text-dim hover:text-text-main disabled:opacity-50"
              :disabled="flatItems.length === 0" v-tooltip="t('dialog.mod_residue.select_all_tip', '勾选当前列表里的所有残留')" @click="selectAll">
              {{ t('common.action.select_all', '全选') }}
            </button>
            <button class="rounded-md border border-border-base/10 px-3 py-1.5 text-xs font-bold text-text-dim hover:text-text-main disabled:opacity-50"
              :disabled="selectedItems.length === 0" v-tooltip="t('dialog.mod_residue.clear_selection_tip', '取消当前选择')" @click="clearSelection">
              {{ t('common.action.clear_selection', '取消选择') }}
            </button>
          </div>
        </div>

        <div v-if="store.loading" class="flex min-h-0 flex-1 items-center justify-center gap-3 text-sm text-text-dim">
          <Loader2 class="size-5 animate-spin text-accent-primary" />
          {{ t('dialog.mod_residue.loading', '正在检查卸载残留...') }}
        </div>

        <div v-else-if="store.groups.length === 0" class="flex min-h-0 flex-1 flex-col items-center justify-center text-sm text-text-dim">
          <PackageCheck class="mb-4 size-14 opacity-50" />
          {{ t('dialog.mod_residue.empty', '当前已扫描目录内没有发现可清理的卸载残留') }}
        </div>

        <div v-else class="min-h-0 flex-1 overflow-y-auto px-5 py-4">
          <div class="space-y-3">
            <article v-for="group in store.groups" :key="group.key" class="overflow-hidden rounded-lg border border-border-base/10 bg-bg-muted/60">
              <header class="flex items-center justify-between w-full gap-4 border-b border-border-base/10 bg-bg-surface/80 px-4 py-3">
                <div class="flex items-center min-w-0 gap-2">
                  <button class="flex flex-1 items-center justify-start text-left text-sm font-black min-w-0 text-text-main hover:text-accent-primary"
                    v-tooltip="t('dialog.mod_residue.toggle_group_tip', '勾选或取消这个模组下的全部残留')" @click="toggleGroup(group)">
                    <CheckSquare v-if="isGroupFullySelected(group)" class="shrink-0 mr-2 inline size-4 text-accent-primary" />
                    <Square v-else class="shrink-0 mr-2 inline size-4 text-text-dim" />
                    <div class="truncate min-w-0">{{ groupTitle(group) }}</div>
                  </button>
                  <span class="rounded bg-accent-danger/15 px-2 py-0.5 text-[0.65rem] font-bold text-accent-danger">{{ t('dialog.mod_residue.pending_count', '待清理 {count}', { count: group.item_count || 0 }) }}</span>
                  <span v-if="group.workshop_id" class="rounded bg-bg-overlay/10 px-2 py-0.5 text-[0.65rem] font-bold text-text-dim">{{ t('dialog.mod_residue.workshop_badge', '工坊 {workshopId}', { workshopId: group.workshop_id }) }}</span>
                  <span v-if="group.package_id" class="rounded bg-bg-overlay/10 px-2 py-0.5 text-[0.65rem] font-bold text-text-dim">{{ t('dialog.mod_residue.package_badge', '包名 {packageId}', { packageId: group.package_id }) }}</span>
                </div>
                <div class="shrink-0 flex items-center gap-2 text-[0.7rem] text-text-dim">
                  <span>{{ t('dialog.mod_residue.folder_count', '文件夹 {count}', { count: group.directory_count || 0 }) }}</span>
                  <span>{{ t('dialog.mod_residue.settings_file_count', '设置文件 {count}', { count: group.settings_file_count || 0 }) }}</span>
                  <span>{{ t('dialog.mod_residue.file_count', '文件 {count}', { count: group.file_count || 0 }) }}</span>
                  <span>{{ t('dialog.mod_residue.size_total', '占用 {size}', { size: formatFileSize(group.total_size || 0) }) }}</span>
                  <span>{{ confidenceText(group.match_confidence) }}</span>
                  <button v-if="group.workshop_id" class="shrink-0 rounded-md border border-border-base/10 px-2 py-1 text-[0.65rem] font-bold text-text-dim hover:text-accent-primary"
                    v-tooltip="t('dialog.mod_residue.open_workshop_tip', '打开这个模组的 Steam 创意工坊页面')"
                    @click="appStore.openSteamWorkshopById(group.workshop_id)">
                    {{ t('common.action.open_workshop', '打开工坊') }}
                  </button>
                </div>
              </header>

              <div class="space-y-2 px-2 py-2">
                <div v-for="item in group.items" :key="item.id" class="flex items-start gap-2 rounded-lg border p-2 transition-colors"
                  :class="isSelected(item) ? 'border-accent-primary/10 bg-accent-primary/8' : 'border-border-base/5 bg-bg-surface/80'">

                    <button class="mt-0.5 text-text-dim hover:text-accent-primary" v-tooltip="t('dialog.mod_residue.toggle_item_tip', '勾选或取消这个残留')" @click="toggleItem(item)">
                      <CheckSquare v-if="isSelected(item)" class="shrink-0 size-4" />
                      <Square v-else class="shrink-0 size-4" />
                    </button>
                    <div class="min-w-0 flex-1" @click="toggleItem(item)">
                      <div class="flex items-center justify-between">
                        <div class="flex items-center gap-2">
                          <component :is="item.type === 'directory' ? FolderX : FileCog" class="size-4 shrink-0 text-accent-danger" />
                          <span class="truncate text-sm font-bold text-text-main">{{ item.name }}</span>
                          <span class="rounded bg-bg-overlay/10 px-2 py-0.5 text-[0.65rem] font-bold text-text-dim">{{ item.type_label }}</span>
                        </div>
                        <div class="flex items-center gap-2 text-xs text-text-dim">
                          <span>{{ t('dialog.mod_residue.file_count', '文件 {count}', { count: item.file_count || 0 }) }}</span>
                          <span>{{ t('dialog.mod_residue.size', '大小 {size}', { size: formatFileSize(item.total_size || 0) }) }}</span>
                          <span>{{ t('dialog.mod_residue.modified_time', '修改 {time}', { time: formatTime(item.modified_time) }) }}</span>
                        </div>
                      </div>
                      <div class="mt-1 space-y-1 text-[0.7rem] truncate text-text-dim" v-tooltip="itemPathTooltip(item)" :title="item.path">
                        {{ t('dialog.mod_residue.path', '路径：{path}', { path: item.path }) }}
                      </div>
                    </div>

                    <div class="flex flex-wrap items-end justify-center gap-2">
                      <button class="flex items-center rounded-lg border border-border-base/10 bg-bg-overlay/5 px-2 py-1 text-[0.7rem] font-bold text-text-main transition-colors hover:bg-bg-overlay/10"
                        v-tooltip="openPathTooltip(item)" @click="openItemPath(item)">
                        <FolderOpen class="mr-1 inline size-3.5" />
                        {{ t('common.action.open_path', '打开路径') }}
                      </button>
                      <button v-if="item.can_whitelist" class="flex items-center rounded-lg border border-accent-warning/35 bg-accent-warning/10 px-2 py-1 text-[0.7rem] font-bold text-accent-warning transition-colors hover:bg-accent-warning/18"
                        v-tooltip="t('dialog.mod_residue.add_whitelist_tip', '加入后，之后扫描不会再提示这个路径')" @click="addWhitelist(item)">
                        <ShieldPlus class="mr-1 inline size-3.5" />
                        {{ t('dialog.mod_residue.add_whitelist', '加入白名单') }}
                      </button>
                    </div>

                </div>
              </div>
            </article>
          </div>
        </div>
      </section>

      <aside v-if="showWhitelist" class="min-h-0 overflow-hidden border-l border-border-base/10 bg-bg-muted/70">
        <div class="flex h-full min-h-0 flex-col">
          <header class="border-b border-border-base/10 px-4 py-3">
            <div class="text-sm font-black text-text-main">{{ t('dialog.mod_residue.whitelist_title', '白名单') }}</div>
            <div class="mt-1 text-xs leading-relaxed text-text-dim">{{ t('dialog.mod_residue.whitelist_desc', '白名单里的路径会被跳过，不会再出现在卸载残留列表里。') }}</div>
            <input v-model="whitelistQuery" class="mt-3 w-full rounded-lg border border-border-base/10 bg-bg-surface px-3 py-2 text-xs text-text-main outline-none focus:border-accent-primary/50"
              :placeholder="t('dialog.mod_residue.whitelist_search_placeholder', '搜索名称或完整路径')" />
          </header>
          <div v-if="filteredWhitelist.length === 0" class="flex flex-1 items-center justify-center px-4 text-center text-xs text-text-dim">
            {{ t('dialog.mod_residue.whitelist_empty', '白名单里还没有项目') }}
          </div>
          <div v-else class="min-h-0 flex-1 overflow-y-auto p-3">
            <div v-for="item in filteredWhitelist" :key="item.path" class="mb-2 rounded-lg border border-border-base/10 bg-bg-surface/80 p-3">
              <div class="truncate text-sm font-bold text-text-main">{{ item.name || pathName(item.path) }}</div>
              <div class="mt-1 truncate text-[0.7rem] text-text-dim">{{ item.path }}</div>
              <div class="mt-3 flex justify-end gap-2">
                <button class="rounded-md border border-border-base/10 px-2 py-1 text-[0.65rem] font-bold text-text-dim hover:text-text-main"
                  v-tooltip="t('dialog.mod_residue.open_whitelist_tip', '打开这个白名单路径')" @click="openWhitelistPath(item)">
                  {{ t('common.action.open', '打开') }}
                </button>
                <button class="rounded-md border border-accent-danger/35 bg-accent-danger/10 px-2 py-1 text-[0.65rem] font-bold text-accent-danger hover:bg-accent-danger/18"
                  v-tooltip="t('dialog.mod_residue.remove_whitelist_tip', '从白名单移除，之后扫描会再次提示它')" @click="removeWhitelist(item)">
                  <ShieldX class="mr-1 inline size-3" />
                  {{ t('common.action.remove', '移除') }}
                </button>
              </div>
            </div>
          </div>
        </div>
      </aside>
    </div>
  </CommonModalShell>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { CheckSquare, FileCog, FolderOpen, FolderX, Loader2, PackageCheck, RefreshCw, Shield, ShieldPlus, ShieldX, Square, Trash2 } from 'lucide-vue-next'
import { useAppStore } from '../../app/stores/appStore'
import { formatFileSize } from '../../shared/lib/format'
import { getCurrentLocale, t } from '../../shared/i18n.js'
import CommonModalShell from '../../shared/components/modal/CommonModalShell.vue'
import { useModResidueStore } from './modResidueStore'

const appStore = useAppStore()
const store = useModResidueStore()

const selectedKeys = ref(new Set())
const showWhitelist = ref(false)
const whitelistQuery = ref('')
const cleaning = ref(false)

const flatItems = computed(() => store.groups.flatMap(group => group.items || []))
const selectedItems = computed(() => flatItems.value.filter(item => selectedKeys.value.has(item.id)))
const filteredWhitelist = computed(() => {
  const query = whitelistQuery.value.trim().toLowerCase()
  return store.whitelist.filter(item => {
    if (!query) return true
    return String(item.name || '').toLowerCase().includes(query) || String(item.path || '').toLowerCase().includes(query)
  })
})

watch(
  () => store.overview,
  () => {
    const validKeys = new Set(flatItems.value.map(item => item.id))
    selectedKeys.value = new Set([...selectedKeys.value].filter(key => validKeys.has(key)))
  },
  { deep: true }
)

const closeModal = () => {
  appStore.uiState.showModResidueCleanup = false
}

const isSelected = (item) => selectedKeys.value.has(item.id)

const toggleItem = (item) => {
  const next = new Set(selectedKeys.value)
  if (next.has(item.id)) next.delete(item.id)
  else next.add(item.id)
  selectedKeys.value = next
}

const isGroupFullySelected = (group) => {
  const items = group?.items || []
  return items.length > 0 && items.every(item => selectedKeys.value.has(item.id))
}

const toggleGroup = (group) => {
  const items = group?.items || []
  const next = new Set(selectedKeys.value)
  const shouldSelect = !isGroupFullySelected(group)
  items.forEach(item => {
    if (shouldSelect) next.add(item.id)
    else next.delete(item.id)
  })
  selectedKeys.value = next
}

const selectAll = () => {
  selectedKeys.value = new Set(flatItems.value.map(item => item.id))
}

const clearSelection = () => {
  selectedKeys.value = new Set()
}

const cleanSelected = async () => {
  const paths = selectedItems.value.map(item => item.path).filter(Boolean)
  if (!paths.length) return
  cleaning.value = true
  try {
    const ok = await appStore.deletePaths(paths, {
      title: t('dialog.mod_residue.clean_title', '清理卸载残留'),
      message: t('dialog.mod_residue.clean_message', '将清理 {count} 个已选残留。下一步可以选择移入回收站或彻底删除。', { count: paths.length }),
      forceOptionText: t('common.action.delete_permanently', '彻底删除'),
      checkLabel: t('dialog.mod_residue.clean_selected', '清理已选残留'),
      successMessage: ({ paths, force }) => cleanSuccessMessage(force, paths.length),
      reScan: false,
      allowWarning: true,
    })
    if (!ok) return
    clearSelection()
    const nextOverview = await store.loadOverview()
    if (Number(nextOverview?.summary?.item_count || 0) === 0) closeModal()
  } finally {
    cleaning.value = false
  }
}

const addWhitelist = async (item) => {
  if (!item?.path) return
  await store.addWhitelist([item.path])
}

const removeWhitelist = async (item) => {
  if (!item?.path) return
  await store.removeWhitelist([item.path])
}

const openItemPath = async (item) => {
  const targetPath = item?.type === 'settings_file' ? (item.parent_path || item.path) : item?.path
  if (!targetPath) return
  await appStore.openPath(targetPath)
}

const openWhitelistPath = async (item) => {
  const targetPath = String(item?.path || '')
  if (!targetPath) return
  const knownFile = flatItems.value.find(entry => entry.path === targetPath && entry.type === 'settings_file')
  const targetFolder = item?.type === 'file' ? pathDirName(targetPath) : targetPath
  await appStore.openPath(knownFile?.parent_path || targetFolder)
}

const openPathTooltip = (item) => {
  if (item?.type === 'settings_file') return t('dialog.mod_residue.open_settings_parent_tip', '打开设置文件所在目录')
  return t('dialog.mod_residue.open_residue_folder_tip', '打开残留文件夹')
}

const cleanSuccessMessage = (force, count) => (
  force
    ? t('dialog.mod_residue.clean_success_force', '已彻底删除 {count} 个残留', { count })
    : t('dialog.mod_residue.clean_success_recycle', '已移入回收站 {count} 个残留', { count })
)

const itemPathTooltip = (item) => {
  if (item?.type === 'settings_file' && item?.parent_path && item.parent_path !== item.path) {
    return t('dialog.mod_residue.settings_file_path_tip', '设置文件：{path}\n所在目录：{parentPath}', { path: item.path, parentPath: item.parent_path })
  }
  return item?.path || ''
}

const groupTitle = (group) => {
  return group?.workshop_detail?.title || group?.mod_name || group?.package_id || group?.workshop_id || t('common.entity.unknown_mod', '未知模组')
}

const confidenceText = (confidence) => {
  return {
    high: t('dialog.mod_residue.confidence.high', '已识别模组'),
    medium: t('dialog.mod_residue.confidence.medium', '可能匹配'),
    low: t('dialog.mod_residue.confidence.low', '仅供参考'),
    unknown: t('dialog.mod_residue.confidence.unknown', '未识别模组'),
  }[String(confidence || '').toLowerCase()] || t('dialog.mod_residue.confidence.medium', '可能匹配')
}

const formatTime = (timestamp) => {
  const value = Number(timestamp || 0)
  if (!value) return t('common.status.unknown', '未知')
  return new Date(value).toLocaleString(getCurrentLocale())
}

const pathName = (path) => String(path || '').split(/[\\/]/).filter(Boolean).pop() || path
const pathDirName = (path) => String(path || '').replace(/[\\/][^\\/]*$/, '') || path
</script>
