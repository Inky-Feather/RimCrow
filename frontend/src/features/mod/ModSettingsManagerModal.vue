<template>
  <CommonModalShell :show="visible" title="模组设置文件" description="按模组整理当前环境里的设置文件，处理重复配置和已卸载模组残留。"
    size="page" :z-index="120" accent="primary" content-class="h-full" @close="emit('close')">
    <template #header-actions>
      <button v-if="unknownCleanupPaths.length > 0"
        class="rounded-lg border border-accent-danger/35 bg-accent-danger/10 px-3 py-2 text-xs font-bold text-accent-danger transition-colors hover:bg-accent-danger/18 disabled:opacity-50"
        :disabled="loading || deleting" @click="deleteUnknownFiles">
        清理残留配置
      </button>
      <button class="rounded-lg border border-border-base/10 bg-bg-overlay/5 px-3 py-2 text-xs font-bold text-text-main transition-colors hover:bg-bg-overlay/10 disabled:opacity-50"
        :disabled="loading" @click="loadOverview()">
        刷新
      </button>
    </template>

    <div class="flex h-full min-h-0 flex-col overflow-hidden">
      <div class="grid grid-cols-5 border-b border-border-base/10 bg-bg-muted">
        <div class="col-span-3 px-4 py-3 text-[0.7rem] text-text-dim">
          <div class="truncate text-xs">配置目录: {{ overview?.config_path || '未知' }}</div>
          <div class="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1">
            <span>文件 {{ overview?.total_files || 0 }}</span>
            <span>已安装模组 {{ overview?.matched_mod_count || 0 }}</span>
            <span>残留/未知文件 {{ overview?.unknown_file_count || 0 }}</span>
            <span v-if="workshopDetailLoading">正在补全工坊信息...</span>
          </div>
        </div>
        <header class="col-span-2 flex items-center justify-end gap-2 px-5 py-3">
          <div class="text-sm font-black text-text-main">文件预览</div>
          <div class="max-w-[18rem] truncate text-[0.7rem] text-text-dim">
            {{ selectedInstance?.name || '未选择配置文件' }}
          </div>
        </header>
      </div>

      <div class="grid min-h-0 flex-1 grid-cols-5 overflow-hidden">
        <div class="col-span-2 overflow-y-auto border-r border-border-base/5 px-4 py-4">
          <div v-if="loading" class="flex h-full items-center justify-center gap-3 text-sm text-text-dim">
            <Loader2 class="size-5 animate-spin text-accent-primary" />
            正在读取设置文件...
          </div>

          <div v-else-if="modGroups.length === 0" class="flex h-full flex-col items-center justify-center text-sm text-text-dim">
            <Files class="mb-4 size-14 opacity-50" />
            当前环境里还没有可管理的模组设置文件
          </div>

          <div v-else class="space-y-4">
            <article v-for="modGroup in modGroups" :key="modGroup.group_key" class="overflow-hidden rounded-lg border"
              :class="selectedModGroupKey === modGroup.group_key ? 'border-accent-primary/50 bg-bg-surface' : 'border-border-base/10 bg-bg-muted/70'">
              <div class="flex w-full cursor-pointer items-start justify-between gap-3 border-b border-border-base/10 bg-bg-surface/80 px-4 py-3 text-left"
                role="button" tabindex="0" @click="selectModGroup(modGroup)" @keydown.enter.prevent="selectModGroup(modGroup)" @keydown.space.prevent="selectModGroup(modGroup)">
                <div class="flex min-w-0 gap-3">
                  <div v-if="workshopPreviewUrl(modGroup)" class="h-12 w-16 shrink-0 overflow-hidden rounded-md border border-border-base/10 bg-bg-muted">
                    <img :src="workshopPreviewUrl(modGroup)" class="h-full w-full object-cover" loading="lazy" />
                  </div>
                  <div class="min-w-0">
                  <div class="flex flex-wrap items-center gap-2">
                    <span class="truncate text-sm font-black text-text-main" v-tooltip="modDetailTooltip(modGroup)">{{ modDisplayName(modGroup) }}</span>
                    <span class="rounded px-2 py-0.5 text-[0.65rem] font-bold" :class="modStatusClass(modGroup)">
                      {{ modStatusText(modGroup) }}
                    </span>
                    <AlertTriangle v-if="modGroup.status === 'disabled'" class="size-3.5 text-accent-warning" v-tooltip="'该模组已安装但当前没有启用'" />
                  </div>
                  <div class="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[0.7rem] text-text-dim">
                    <span v-if="modGroup.package_id">包名: {{ modGroup.package_id }}</span>
                    <span v-if="modGroup.workshop_id">工坊 ID: {{ modGroup.workshop_id }}</span>
                    <span>设置 {{ modGroup.setting_count || 0 }}</span>
                    <span>文件 {{ modGroup.file_count || 0 }}</span>
                  </div>
                  </div>
                </div>
                <button v-if="modGroup.workshop_id" class="shrink-0 rounded-md border border-border-base/10 px-2 py-1 text-[0.65rem] font-bold text-text-dim hover:text-accent-primary"
                  @click.stop="appStore.openSteamWorkshopById(modGroup.workshop_id)">
                  工坊
                </button>
              </div>

              <div class="space-y-3 px-3 py-3">
                <section v-for="settingGroup in modGroup.setting_groups" :key="settingGroup.key" class="rounded-lg border border-border-base/5 bg-bg-deep/20">
                  <button class="flex w-full items-start justify-between gap-3 px-3 py-3 text-left"
                    @click="selectSettingGroup(modGroup, settingGroup)">
                    <div class="min-w-0">
                      <div class="flex flex-wrap items-center gap-2">
                        <span class="truncate text-sm font-bold text-text-dim">{{ settingGroup.label || '未识别设置' }}</span>
                        <span class="rounded bg-bg-overlay/10 px-2 py-0.5 text-[0.65rem] font-bold text-text-dim">
                          {{ settingGroup.identity === 'class' ? '设置类' : '文件名兜底' }}
                        </span>
                        <span v-if="settingGroup.duplicate_count > 0" class="rounded bg-accent-warning/15 px-2 py-0.5 text-[0.65rem] font-bold text-accent-warning">
                          重复 {{ settingGroup.duplicate_count }}
                        </span>
                      </div>
                      <div v-if="settingNotice(settingGroup)" class="mt-1 text-[0.7rem] text-accent-warning">
                        {{ settingNotice(settingGroup) }}
                      </div>
                    </div>
                  </button>

                  <div class="space-y-2 px-3 pb-3">
                    <div v-for="item in settingGroup.files" :key="item.key" class="relative rounded-lg border p-3 transition-colors"
                      :class="selectedInstanceKey === item.key ? 'border-accent-primary/45 bg-accent-primary/15' : 'border-border-base/10 bg-bg-surface/85'"
                      @click="selectInstance(modGroup, settingGroup, item)">
                      <div class="min-w-0 pr-1">
                        <div class="flex flex-wrap items-center gap-2">
                          <button class="min-w-0 truncate text-left text-sm font-bold text-text-main hover:text-accent-primary"
                            @click.stop="selectInstance(modGroup, settingGroup, item)">
                            {{ item.name }}
                          </button>
                          <span class="rounded bg-bg-overlay/10 px-2 py-0.5 text-[0.65rem] font-bold text-text-dim">{{ item.source_label }}</span>
                          <span v-if="item.active" class="rounded bg-accent-primary/15 px-2 py-0.5 text-[0.65rem] font-bold text-accent-primary">当前激活</span>
                          <span v-if="item.match_confidence && item.match_confidence !== 'high'" class="rounded bg-accent-warning/15 px-2 py-0.5 text-[0.65rem] font-bold text-accent-warning">
                            {{ confidenceText(item.match_confidence) }}
                          </span>
                        </div>
                        <div class="mt-2 space-y-1 text-[0.7rem] text-text-dim">
                          <div>来源文件夹: {{ item.folder_name || '未知' }}</div>
                          <div class="truncate">文件位置: {{ item.file_path }}</div>
                          <div>大小: {{ formatSize(item.file_size) }} | 修改时间: {{ formatTime(item.modified_time) }}</div>
                        </div>
                      </div>

                      <div class="mt-3 flex flex-wrap items-center justify-end gap-2">
                        <button class="rounded-lg border border-border-base/10 bg-bg-overlay/5 px-3 py-1.5 text-[0.7rem] font-bold text-text-main transition-colors hover:bg-bg-overlay/10"
                          @click.stop="appStore.openFile(item.file_path)">
                          打开文件
                        </button>
                        <button class="rounded-lg border border-border-base/10 bg-bg-overlay/5 px-3 py-1.5 text-[0.7rem] font-bold text-text-main transition-colors hover:bg-bg-overlay/10"
                          @click.stop="appStore.openPath(item.file_path)">
                          打开目录
                        </button>
                        <button v-if="canSyncItem(settingGroup, item)" class="rounded-lg border border-accent-warning/35 bg-accent-warning/10 px-3 py-1.5 text-[0.7rem] font-bold text-accent-warning transition-colors hover:bg-accent-warning/18 disabled:opacity-50"
                          :disabled="syncingTargetPath === settingGroup.active_file_path" :title="syncTooltip(settingGroup, item)"
                          @click.stop="syncToActive(settingGroup, item)">
                          {{ syncingTargetPath === settingGroup.active_file_path ? '覆盖中...' : '覆盖当前激活文件' }}
                        </button>
                        <button v-if="canDeleteItem(modGroup, settingGroup, item)" class="rounded-lg border border-accent-danger/35 bg-accent-danger/10 px-3 py-1.5 text-[0.7rem] font-bold text-accent-danger transition-colors hover:bg-accent-danger/18 disabled:opacity-50"
                          :disabled="deleting" @click.stop="deleteItem(item)">
                          删除
                        </button>
                      </div>
                    </div>
                  </div>
                </section>
              </div>
            </article>
          </div>
        </div>

        <div class="col-span-3 min-h-0 overflow-hidden">
          <div class="flex h-full min-h-0 flex-col">
            <div v-if="previewData?.truncated" class="border-b border-border-base/10 px-5 py-3 text-[0.7rem] text-accent-warning">内容过长，仅显示前 2 MB</div>
            <FileSearchPreviewEditor class="min-h-0 flex-1" :file-path="selectedInstance?.file_path || ''" :content="previewData?.content || ''"
              :loading="previewLoading" :wrap-lines="true" empty-text="点左侧文件即可在这里查看内容" />
          </div>
        </div>
      </div>
    </div>
  </CommonModalShell>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { AlertTriangle, Files, Loader2 } from 'lucide-vue-next'
import { useToast } from 'vue-toastification'
import { useAppStore } from '../../app/stores/appStore.js'
import { useConfirmStore } from '../../shared/components/modal/confirmStore.js'
import { formatFileSize } from '../../shared/lib/format.js'
import CommonModalShell from '../../shared/components/modal/CommonModalShell.vue'
import FileSearchPreviewEditor from '../file-search/FileSearchPreviewEditor.vue'

const props = defineProps({
  visible: { type: Boolean, default: false },
})

const emit = defineEmits(['close'])

const appStore = useAppStore()
const confirmStore = useConfirmStore()
const toast = useToast()

const loading = ref(false)
const deleting = ref(false)
const previewLoading = ref(false)
const workshopDetailLoading = ref(false)
const syncingTargetPath = ref('')
const overview = ref(null)
const selectedModGroupKey = ref('')
const selectedSettingKey = ref('')
const selectedInstanceKey = ref('')
const previewData = ref(null)

const modGroups = computed(() => overview.value?.mod_groups || [])
const unknownCleanupPaths = computed(() => overview.value?.cleanup_candidate_paths || [])
const selectedModGroup = computed(() => modGroups.value.find(group => group.group_key === selectedModGroupKey.value) || null)
const selectedSettingGroup = computed(() => selectedModGroup.value?.setting_groups?.find(group => group.key === selectedSettingKey.value) || null)
const selectedInstance = computed(() => selectedSettingGroup.value?.files?.find(item => item.key === selectedInstanceKey.value) || null)

const resetSelection = () => {
  selectedModGroupKey.value = ''
  selectedSettingKey.value = ''
  selectedInstanceKey.value = ''
  previewData.value = null
}

const setSelection = (modGroup, settingGroup, item) => {
  selectedModGroupKey.value = modGroup?.group_key || ''
  selectedSettingKey.value = settingGroup?.key || ''
  selectedInstanceKey.value = item?.key || ''
  if (item?.file_path) {
    void loadPreview(item.file_path)
  } else {
    previewData.value = null
  }
}

const selectFirstInstance = (modGroup, settingGroup = null) => {
  const nextSettingGroup = settingGroup || modGroup?.setting_groups?.[0]
  const nextItem = nextSettingGroup?.files?.[0]
  setSelection(modGroup, nextSettingGroup, nextItem)
}

watch(
  () => props.visible,
  (visible) => {
    if (visible) {
      loadOverview()
      return
    }
    overview.value = null
    resetSelection()
    syncingTargetPath.value = ''
  }
)

const ensureSelection = () => {
  if (!modGroups.value.length) {
    resetSelection()
    return
  }
  const nextModGroup = modGroups.value.find(group => group.group_key === selectedModGroupKey.value) || modGroups.value[0]
  const nextSettingGroup = nextModGroup.setting_groups?.find(group => group.key === selectedSettingKey.value) || nextModGroup.setting_groups?.[0]
  const nextInstance = nextSettingGroup?.files?.find(item => item.key === selectedInstanceKey.value) || nextSettingGroup?.files?.[0]
  setSelection(nextModGroup, nextSettingGroup, nextInstance)
}

const hydrateWorkshopDetails = async () => {
  const workshopIds = [...new Set(
    modGroups.value
      .filter(group => ['uninstalled', 'unknown'].includes(group.status))
      .map(group => String(group.workshop_id || '').trim())
      .filter(Boolean)
  )]
  if (!workshopIds.length || !window.pywebview?.api?.mod_config_workshop_details) return
  workshopDetailLoading.value = true
  try {
    const res = await window.pywebview.api.mod_config_workshop_details(workshopIds)
    if (res?.status !== 'success') return
    const details = res.data || {}
    modGroups.value.forEach((group) => {
      const detail = details[String(group.workshop_id || '').trim()]
      if (!detail) return
      group.workshop_detail = detail
      if (detail.package_id && !group.package_id) group.package_id = detail.package_id
      if (detail.title) group.mod_name = detail.title
      if (detail.available && detail.title) group.match_confidence = 'high'
    })
  } finally {
    workshopDetailLoading.value = false
  }
}

const loadOverview = async () => {
  overview.value = null
  previewData.value = null
  if (!window.pywebview) return
  loading.value = true
  try {
    const res = await window.pywebview.api.mod_config_get_overview()
    if (res?.status !== 'success') {
      toast.error(res?.message || '读取模组设置文件失败')
      return
    }
    overview.value = res.data || null
    ensureSelection()
    void hydrateWorkshopDetails()
  } finally {
    loading.value = false
  }
}

const loadPreview = async (path) => {
  previewLoading.value = true
  try {
    previewData.value = await appStore.readTextFile(path)
  } finally {
    previewLoading.value = false
  }
}

const selectModGroup = (modGroup) => {
  selectFirstInstance(modGroup)
}

const selectSettingGroup = (modGroup, settingGroup) => {
  selectFirstInstance(modGroup, settingGroup)
}

const selectInstance = (modGroup, settingGroup, item) => {
  setSelection(modGroup, settingGroup, item)
}

const canSyncItem = (settingGroup, item) => {
  return !!settingGroup?.can_cover_active && !!settingGroup.active_file_path && !item.active
}

const canDeleteItem = (modGroup, settingGroup, item) => {
  if (['uninstalled', 'unknown'].includes(modGroup?.status)) return true
  return !item?.active && Number(settingGroup?.file_count || 0) > 1
}

const syncTooltip = (settingGroup, item) => {
  const activeItem = settingGroup?.files?.find(entry => entry.active)
  if (!activeItem) return '当前没有激活文件，不能覆盖'
  return `用 ${item.name} 覆盖 ${activeItem.name}`
}

const syncToActive = async (settingGroup, sourceItem) => {
  if (!window.pywebview || !settingGroup?.active_file_path || sourceItem.active) return
  const activeItem = settingGroup.files?.find(item => item.active)
  if (!activeItem) return
  const confirmed = await confirmStore.confirmAction(
    '确认覆盖',
    `将用 ${sourceItem.name} 的内容替换当前激活文件 ${activeItem.name}。`,
    { confirmText: '覆盖激活文件', cancelText: '取消', type: 'warning' }
  )
  if (!confirmed) return

  syncingTargetPath.value = activeItem.file_path
  try {
    const res = await window.pywebview.api.mod_config_sync(sourceItem.file_path, activeItem.file_path)
    if (res?.status !== 'success') {
      toast.error(res?.message || '覆盖模组设置文件失败')
      return
    }
    toast.success(res?.message || '已覆盖当前激活文件')
    overview.value = res.data?.overview || overview.value
    selectedInstanceKey.value = activeItem.key
    ensureSelection()
    void hydrateWorkshopDetails()
  } finally {
    syncingTargetPath.value = ''
  }
}

const deleteItem = async (item) => {
  const deleted = await appStore.deletePath(item.file_path, false)
  if (!deleted) return
  await loadOverview()
}

const deleteUnknownFiles = async () => {
  const paths = unknownCleanupPaths.value
  if (!paths.length || !window.pywebview) return
  deleting.value = true
  try {
    const ok = await appStore.deletePaths(paths, {
      title: '清理残留配置',
      message: `确定要删除 ${paths.length} 个已卸载或未知模组的设置文件吗？`,
      checkLabel: '清理残留配置',
      successMessage: ({ paths, force }) => `${force ? '已彻底删除' : '已移入回收站'} ${paths.length} 个设置文件`,
      reScan: false,
      allowWarning: true,
    })
    if (!ok) return
    await loadOverview()
  } finally {
    deleting.value = false
  }
}

const modDisplayName = (modGroup) => {
  return modGroup?.workshop_detail?.title || modGroup?.mod_name || '未知模组'
}

const modStatusText = (modGroup) => {
  return {
    enabled: '已启用',
    disabled: '已停用',
    uninstalled: '已卸载',
    unknown: '未知',
  }[modGroup?.status] || '未知'
}

const modStatusClass = (modGroup) => {
  return {
    enabled: 'bg-accent-success/15 text-accent-success',
    disabled: 'bg-accent-warning/15 text-accent-warning',
    uninstalled: 'bg-accent-danger/15 text-accent-danger',
    unknown: 'bg-bg-overlay/10 text-text-dim',
  }[modGroup?.status] || 'bg-bg-overlay/10 text-text-dim'
}

const settingNotice = (settingGroup) => {
  if (settingGroup?.parse_status === 'ok') return ''
  return settingGroup?.parse_message || ''
}

const workshopPreviewUrl = (modGroup) => {
  const rawUrl = modGroup?.workshop_detail?.preview_url
  return rawUrl ? appStore.getRemoteUrl(rawUrl) : ''
}

const modDetailTooltip = (modGroup) => {
  const lines = [modDisplayName(modGroup), `状态: ${modStatusText(modGroup)}`]
  if (modGroup?.package_id) lines.push(`包名: ${modGroup.package_id}`)
  if (modGroup?.workshop_id) lines.push(`工坊 ID: ${modGroup.workshop_id}`)
  if (Array.isArray(modGroup?.workshop_detail?.author) && modGroup.workshop_detail.author.length) {
    lines.push(`作者: ${modGroup.workshop_detail.author.join(', ')}`)
  }
  if (modGroup?.workshop_detail?.detail_source === 'database') lines.push('详情来源: 本地工坊数据库')
  if (modGroup?.workshop_detail?.detail_source === 'unavailable') lines.push('工坊详情不可用')
  return lines.join('\n')
}

const confidenceText = (confidence) => {
  return {
    medium: '中置信度',
    low: '低置信度',
    unknown: '未知来源',
  }[String(confidence || '').toLowerCase()] || '辅助识别'
}

const formatTime = (timestamp) => {
  const value = Number(timestamp || 0)
  if (!value) return '未知'
  try {
    return new Date(value).toLocaleString('zh-CN')
  } catch {
    return '未知'
  }
}

const formatSize = (size) => formatFileSize(size, 2)
</script>
