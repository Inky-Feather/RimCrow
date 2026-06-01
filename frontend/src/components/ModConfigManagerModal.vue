<template>
  <CommonModalShell :show="visible" title="模组配置" description="查看当前环境里的官方模组配置，区分不同配置，并在同一种配置之间手动覆盖内容。"
    size="wide" :z-index="120" accent="primary" content-class="h-full"
    @close="emit('close')" >
    <template #header-actions>
      <button class="rounded-lg border border-border-base/10 bg-bg-overlay/5 px-3 py-2 text-xs font-bold text-text-main transition-colors hover:bg-bg-overlay/10 disabled:opacity-50"
        @click="loadOverview()" :disabled="loading" >
        刷新
      </button>
    </template>

      <div class="flex flex-col h-full flex-1 overflow-hidden">
        <!-- 标题信息 -->
        <div class="grid grid-cols-5 bg-bg-muted shadow-md">
          <!-- 配置目录信息 -->
          <div class=" col-span-3 px-4 py-2 text-[0.7rem] text-text-dim ">
            <span class="text-xs">配置目录: {{ overview?.config_path || '未知' }}</span>
            <div class="flex items-center gap-x-2 mt-2">
              <span>文件 {{ overview?.total_files || 0 }}</span>
              <span>已识别 {{ overview?.matched_group_count || 0 }} 组</span>
              <span>未识别 {{ overview?.orphan_file_count || 0 }}</span>
            </div>
          </div>
          <!-- 配置文件预览 -->
          <header class="col-span-2 px-5 py-4 flex items-center justify-end gap-2">
            <div class="text-sm font-black text-text-main">文件预览</div>
            <div class="mt-1 text-[0.7rem] text-text-dim">
              {{ selectedInstance?.file_name || '未选择配置文件' }}
            </div>
          </header>
        </div>

        <!-- 结果列表与文件预览 -->
        <div class="flex-1 overflow-hidden grid grid-cols-5">
          <!-- 结果列表 -->
          <div class="col-span-2 overflow-y-auto px-4 py-4 border-r border-border-base/5">
            <div v-if="loading" class="flex h-full items-center justify-center gap-3 text-sm text-text-dim">
              <Loader2 class="size-5 animate-spin text-accent-primary" />
              正在读取配置...
            </div>

            <div v-else-if="groups.length === 0" class="flex h-full flex-col items-center justify-center text-sm text-text-dim">
              <Files class="mb-4 size-14 opacity-50" />
              当前环境里还没有可识别的模组配置
            </div>

            <div v-else class="space-y-4">
              <article v-for="group in groups" :key="group.group_key" class="overflow-hidden rounded-2xl border transition-colors"
                :class="selectedGroupKey === group.group_key ? 'border-accent-primary/50 bg-accent-primary/5' : 'border-border-base/10 bg-bg-muted/70'" >
                <button class="flex w-full items-start justify-between gap-4 border-b border-border-base/10 px-5 py-4 text-left"
                  @click="selectGroup(group)" >
                  <div class="min-w-0">
                    <div class="flex flex-wrap items-center gap-2">
                      <span class="text-sm font-black text-text-main">{{ group.mod_name }}</span>
                      <span class="rounded px-2 py-0.5 text-[0.65rem] font-bold"
                        :class="group.status === 'matched' ? 'bg-accent-success/15 text-accent-success' : 'bg-accent-danger/15 text-accent-danger'" >
                        {{ group.status === 'matched' ? '已识别' : '未识别文件' }}
                      </span>
                      <span v-if="group.is_active_group" class="rounded bg-accent-primary/15 px-2 py-0.5 text-[0.65rem] font-bold text-accent-primary">
                        含当前使用的文件
                      </span>
                    </div>
                    <div class="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[0.7rem] text-text-dim">
                      <span>模组标识: {{ group.package_id || '未知' }}</span>
                      <span>配置名称: {{ group.settings_class_name || '未知' }}</span>
                      <span>文件 {{ group.instance_count }}</span>
                      <span v-if="group.can_sync">可在同一种配置之间互相覆盖</span>
                    </div>
                  </div>
                </button>

                <div class="space-y-3 px-4 py-4">
                  <div v-for="item in group.instances" :key="item.instance_key" class="relative rounded-xl border p-4 transition-colors group"
                    :class="selectedInstanceKey === item.instance_key ? 'border-accent-primary/45 bg-accent-primary/20' : 'border-border-base/10 bg-bg-surface'"
                    @click="selectInstance(group, item)">

                      <div class="min-w-0">
                        <div class="flex flex-wrap items-center gap-2">
                          <button class="truncate text-left text-sm font-bold text-text-main hover:text-accent-primary" @click="selectInstance(group, item)">
                            {{ item.file_name }}
                          </button>
                          <span class="rounded bg-bg-overlay/10 px-2 py-0.5 text-[0.65rem] font-bold text-text-dim">
                            {{ item.source_label }}
                          </span>
                          <span v-if="item.is_active_instance" class="rounded bg-accent-primary/15 px-2 py-0.5 text-[0.65rem] font-bold text-accent-primary">
                            当前激活
                          </span>
                          <span v-if="group.can_sync && currentSourceKey(group.group_key) === item.instance_key"
                            class="rounded bg-accent-secondary/15 px-2 py-0.5 text-[0.65rem] font-bold text-accent-secondary" >
                            基准文件
                          </span>
                        </div>
                        <div class="mt-2 space-y-1 text-[0.7rem] text-text-dim">
                          <div>配置名称: {{ item.settings_class_name || '未知' }}</div>
                          <div>来源文件夹: {{ item.folder_name || '未知' }}</div>
                          <div class="truncate">文件位置: {{ item.file_path }}</div>
                          <div>大小: {{ formatSize(item.file_size) }} | 修改时间: {{ formatTime(item.modified_time) }}</div>
                        </div>
                      </div>

                      <!-- 操作按钮 -->
                      <div class="absolute bottom-0 right-0 left-0 z-100 flex flex-wrap items-center justify-end gap-2 backdrop-blur-2xl border border-border-base/5 p-2 rounded-b-xl opacity-0 transition-opacity duration-200 group-hover:opacity-100">
                        <button class="rounded-lg border border-border-base/10 bg-bg-overlay/5 px-3 py-1.5 text-[0.7rem] font-bold text-text-main transition-colors hover:bg-bg-overlay/10"
                          @click="appStore.openFile(item.file_path)" >
                          打开文件
                        </button>
                        <button class="rounded-lg border border-border-base/10 bg-bg-overlay/5 px-3 py-1.5 text-[0.7rem] font-bold text-text-main transition-colors hover:bg-bg-overlay/10"
                          @click="appStore.openPath(item.file_path)" >
                          打开目录
                        </button>
                        <button v-if="group.can_sync" class="rounded-lg border px-3 py-1.5 text-[0.7rem] font-bold transition-colors"
                          :class="currentSourceKey(group.group_key) === item.instance_key ? 'border-accent-secondary/35 bg-accent-secondary/15 text-accent-secondary' : 'border-border-base/10 bg-bg-overlay/5 text-text-main hover:bg-bg-overlay/10'"
                          v-tooltip="currentSourceKey(group.group_key) === item.instance_key ? '当前以这个文件为准' : '把这个文件设为基准，之后可用它覆盖同组里的其它文件'"
                          @click="setSource(group.group_key, item.instance_key)" >
                          {{ currentSourceKey(group.group_key) === item.instance_key ? '当前基准' : '设为基准' }}
                        </button>
                        <button v-if="group.can_sync && currentSourceKey(group.group_key) && currentSourceKey(group.group_key) !== item.instance_key"
                          class="rounded-lg border border-accent-warning/35 bg-accent-warning/10 px-3 py-1.5 text-[0.7rem] font-bold text-accent-warning transition-colors hover:bg-accent-warning/18"
                          :disabled="syncingTargetPath === item.file_path" v-tooltip="buildSyncTooltip(group, item)"
                          @click="syncTo(group, item)" >
                          {{ syncingTargetPath === item.file_path ? '覆盖中...' : '用基准文件覆盖当前文件' }}
                        </button>
                      </div>

                  </div>
                </div>
              </article>
            </div>
          </div>

          <!-- 文件预览区域 -->
          <div class="col-span-3 flex-1 overflow-hidden">
            <div v-if="previewLoading" class="flex h-full items-center justify-center gap-3 text-sm text-text-dim">
              <Loader2 class="size-5 animate-spin text-accent-primary" />
              正在读取内容...
            </div>
            <div v-else-if="!previewData" class="flex h-full items-center justify-center text-sm text-text-dim">
              点左侧文件即可在这里查看内容
            </div>
            <div v-else class="flex h-full min-h-0 flex-col">
              <div v-if="previewData.truncated" class="px-5 py-3 border-b border-border-base/10 text-[0.7rem] text-accent-warning">内容过长，仅显示前 2 MB</div>
              <pre class="min-h-0 flex-1 overflow-auto whitespace-pre-wrap break-all px-5 py-4 text-xs leading-6 text-text-main select-text">{{ previewData.content || '' }}</pre>
            </div>
          </div>
        </div>
      </div>

        <section class="grid grid-cols-5 h-full flex-1 overflow-hidden">
          <div class=" col-span-2 h-full flex flex-col overflow-hidden border-r border-border-base/10">
            

          </div>

          <!-- 文件预览区域 -->
          <aside class="col-span-3 flex shrink-0 flex-col">

            
          </aside>

        </section>
  </CommonModalShell>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { ChevronRight, Files, Loader2 } from 'lucide-vue-next'
import { useToast } from 'vue-toastification'
import { useAppStore } from '../stores/appStore'
import { useConfirmStore } from '../stores/confirmStore'
import { formatFileSize } from '../utils/format'
import CommonModalShell from './common/CommonModalShell.vue'

const props = defineProps({
  visible: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits(['close'])

const appStore = useAppStore()
const confirmStore = useConfirmStore()
const toast = useToast()

const loading = ref(false)
const previewLoading = ref(false)
const syncingTargetPath = ref('')
const overview = ref(null)
const selectedGroupKey = ref('')
const selectedInstanceKey = ref('')
const previewData = ref(null)
const groupSourceMap = reactive({})

const groups = computed(() => overview.value?.groups || [])
const selectedGroup = computed(() => groups.value.find(group => group.group_key === selectedGroupKey.value) || null)
const selectedInstance = computed(() => {
  if (!selectedGroup.value) return null
  return selectedGroup.value.instances.find(item => item.instance_key === selectedInstanceKey.value) || null
})

watch(
  () => props.visible,
  (visible) => {
    if (visible) {
      loadOverview()
      return
    }
    overview.value = null
    previewData.value = null
    selectedGroupKey.value = ''
    selectedInstanceKey.value = ''
    syncingTargetPath.value = ''
  }
)

const resetGroupSources = (nextGroups = []) => {
  const previousSources = Object.fromEntries(
    Object.entries(groupSourceMap).map(([key, value]) => [key, String(value || '')])
  )
  Object.keys(groupSourceMap).forEach(key => delete groupSourceMap[key])
  nextGroups.forEach((group) => {
    const previousItem = group.instances.find(item => item.instance_key === previousSources[group.group_key])
    const activeItem = group.instances.find(item => item.is_active_instance)
    const fallbackItem = previousItem || activeItem || group.instances[0]
    groupSourceMap[group.group_key] = fallbackItem?.instance_key || ''
  })
}

const ensureSelection = () => {
  if (!groups.value.length) {
    selectedGroupKey.value = ''
    selectedInstanceKey.value = ''
    previewData.value = null
    return
  }

  const fallbackGroup = groups.value[0]
  const nextGroup = groups.value.find(group => group.group_key === selectedGroupKey.value) || fallbackGroup
  selectedGroupKey.value = nextGroup.group_key

  const nextInstance = nextGroup.instances.find(item => item.instance_key === selectedInstanceKey.value) || nextGroup.instances[0]
  selectedInstanceKey.value = nextInstance?.instance_key || ''
  if (nextInstance?.file_path) {
    void loadPreview(nextInstance.file_path)
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
      toast.error(res?.message || '读取模组配置总览失败')
      return
    }
    overview.value = res.data || null
    resetGroupSources(groups.value)
    ensureSelection()
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

const selectGroup = (group) => {
  selectedGroupKey.value = group.group_key
  const nextInstance = group.instances[0]
  if (!nextInstance) return
  selectedInstanceKey.value = nextInstance.instance_key
  void loadPreview(nextInstance.file_path)
}

const selectInstance = (group, item) => {
  selectedGroupKey.value = group.group_key
  selectedInstanceKey.value = item.instance_key
  void loadPreview(item.file_path)
}

const currentSourceKey = (groupKey = '') => String(groupSourceMap[groupKey] || '')

const currentSourceItem = (group) => group?.instances?.find(item => item.instance_key === currentSourceKey(group.group_key)) || null

const buildSyncTooltip = (group, targetItem) => {
  const sourceItem = currentSourceItem(group)
  if (!sourceItem) return '还没有选择基准文件'
  return `用 ${sourceItem.file_name} 覆盖 ${targetItem.file_name}`
}

const setSource = (groupKey, instanceKey) => {
  groupSourceMap[groupKey] = instanceKey
}

const syncTo = async (group, targetItem) => {
  if (!window.pywebview) return
  const sourceItem = currentSourceItem(group)
  if (!sourceItem || sourceItem.instance_key === targetItem.instance_key) return

  const confirmed = await confirmStore.confirmAction(
    '确认覆盖',
    `将用 ${sourceItem.file_name} 的内容替换 ${targetItem.file_name} 当前内容。`,
    { confirmText: '开始覆盖', cancelText: '取消', type: 'warning' }
  )
  if (!confirmed) return

  syncingTargetPath.value = targetItem.file_path
  try {
    const res = await window.pywebview.api.mod_config_sync(sourceItem.file_path, targetItem.file_path)
    if (res?.status !== 'success') {
      toast.error(res?.message || '同步模组配置失败')
      return
    }
    toast.success(res?.message || '模组配置已同步')
    overview.value = res.data?.overview || overview.value
    resetGroupSources(groups.value)
    selectedGroupKey.value = group.group_key
    selectedInstanceKey.value = targetItem.instance_key
    await loadPreview(targetItem.file_path)
  } finally {
    syncingTargetPath.value = ''
  }
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

const formatSize = (size) => {
  return formatFileSize(size, 2)
}
</script>

<style scoped>
.mod-config-fade-enter-active,
.mod-config-fade-leave-active {
  transition: opacity 0.24s ease;
}

.mod-config-fade-enter-from,
.mod-config-fade-leave-to {
  opacity: 0;
}

.custom-scrollbar::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}

.custom-scrollbar::-webkit-scrollbar-thumb {
  background: var(--color-border-strong);
  border-radius: 999px;
}

.custom-scrollbar::-webkit-scrollbar-thumb:hover {
  background: var(--color-border-strong);
}
</style>
