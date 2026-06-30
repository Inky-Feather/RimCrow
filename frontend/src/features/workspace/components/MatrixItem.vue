<!-- src/components/workspace/components/MatrixItem.vue -->
<template>
  <div class="relative py-1" :data-id="mod.path_hash">
    <!-- 主卡片 -->
    <div ref="itemRef" 
      @contextmenu.prevent="openContextMenu"
      @mouseenter="handleMouseEnter"
      @mouseleave="handleMouseLeave"
      class="matrix-select-trigger flex items-center gap-2 p-1.5 rounded-lg border transition-all cursor-pointer group bg-bg-overlay/5"
      :class="[
        mod.is_unavailable ? 'opacity-70 grayscale border-dashed border-accent-danger/50 bg-accent-danger/5 hover:bg-accent-danger/10 hover:border-accent-danger/30' :
        storeType === 'workshop' ? 'border-accent-primary/10 hover:bg-accent-primary/10 hover:border-accent-primary/30' :
        storeType === 'self' ? 'border-accent-success/10 hover:bg-accent-success/10 hover:border-accent-success/30' :
        'border-accent-warn/10 hover:bg-accent-warn/10 hover:border-accent-warn/30', 
        isSelected ? 'border-accent-tip/60 ring-1 ring-accent-tip/90 hover:bg-accent-tip/20 hover:border-accent-tip/90':''
      ]">
      
      <!-- 图标 -->
      <img v-if="mod.preview_path" :src="appStore.getThumbUrl(mod.package_id, mod.preview_path)" loading="lazy" class="size-10 rounded object-cover border border-border-base/10 shadow-sm opacity-80 group-hover:opacity-100" />
      <div v-else class="size-10 rounded bg-bg-inset/80 border border-border-base/10 flex items-center justify-center">
        <span class="text-[0.6rem] text-text-disabled font-bold uppercase">NO IMG</span>
      </div>

      <!-- 信息 -->
      <div class="flex-1 min-w-0">
        <div class="text-xs font-bold text-text-main truncate group-hover:text-text-inverse transition-colors">
          {{ mod.name || mod.package_id }}
        </div>
        <div v-if="mod.package_id" title="包名" class="text-[0.65rem] truncate text-text-dim font-mono mt-0.5 opacity-60">
          {{ mod.package_id }}
        </div>
        <div v-if="mod.workshop_id" title="创意工坊ID" class="text-[0.65rem] truncate text-text-dim font-mono mt-0.5 opacity-60">
          {{ mod.workshop_id }}
        </div>
      </div>

      <!-- 右侧时间与大小 -->
      <div class="shrink-0 flex flex-col items-end gap-1 pr-2">
        <span v-for="(entry, index) in summaryTimeEntries" :key="entry.key" class="text-[0.65rem] font-mono" :class="getSummaryTimeClass(entry, index)">
          {{ entry.label }}：{{ formatTime(entry.timestamp) }}
        </span>
        <span v-if="!summaryTimeEntries.length" class="text-[0.65rem] font-mono text-text-dim">
          时间：无记录
        </span>
        <span class="text-[0.6rem] font-mono text-text-dim opacity-50 bg-bg-inset/80 px-1 rounded">
          {{ formatFileSize(mod.file_size) }}
        </span>
      </div>

      <!-- 状态角标 -->
      <div class="absolute top-0 left-1 z-100 scale-90 flex items-center justify-center gap-1">
        <span v-if="matrixState.isNew" title="新增" class="px-1.5 py-0.5 rounded-md text-[0.6rem] font-black text-on-accent-primary bg-accent-primary animate-pulse">
          NEW
        </span>
        <span v-if="matrixState.isChange" title="变更" class="px-1.5 py-0.5 rounded-md text-[0.6rem] font-black text-on-accent-success bg-accent-success animate-pulse">
          CHANGE
        </span>
        <span v-if="matrixState.isUpdate" title="可更新" class="px-1.5 py-0.5 rounded-md text-[0.6rem] font-black text-on-accent-warn bg-accent-warn animate-pulse">
          UPDATE
        </span>
        <span v-if="matrixState.isSame" :title="sameItemsTooltip" class="px-1.5 py-0.5 rounded-md text-[0.6rem] font-black text-on-accent-special bg-accent-special animate-pulse">
          SAME
        </span>
        <span v-if="matrixState.isConflict" :title="conflictItemsTooltip" class="px-1.5 py-0.5 rounded-md text-[0.55rem] font-black text-on-accent-danger bg-accent-danger animate-pulse">
          CONFLICT
        </span>
        <span v-if="matrixState.isReplace" :title="replacementItemsTooltip" class="px-1.5 py-0.5 rounded-md text-[0.6rem] font-black text-on-accent-tip bg-accent-tip animate-pulse">
          REPLACE
        </span>
        <span v-if="matrixState.isDisabled" title="已禁用" class="px-1.5 py-0.5 rounded-md text-[0.6rem] font-black text-on-accent-warn bg-accent-warning animate-pulse">
          DISABLED
        </span>
        <span v-if="matrixState.isMissing" title="工坊记录存在，但本地没有有效模组文件" class="px-1.5 py-0.5 rounded-md text-[0.6rem] font-black text-on-accent-danger bg-accent-danger animate-pulse">
          MISSING
        </span>
        <span v-if="matrixState.isDeleted" title="库存记录存在，但本地模组目录已删除或失效" class="px-1.5 py-0.5 rounded-md text-[0.6rem] font-black text-on-accent-danger bg-accent-danger animate-pulse">
          DELETED
        </span>
        <span v-if="matrixState.isWorkshopUnavailable" title="Steam 已无法获取该工坊项目详情，可能已下架或不可访问" class="px-1.5 py-0.5 rounded-md text-[0.6rem] font-black text-on-accent-danger bg-accent-danger animate-pulse">
          失效
        </span>
      </div>
    </div>

    <!-- 智能悬浮/弹出层 (Smart Popover) -->
    <Teleport to="body">
      <Transition :name="popoverDirection === 'right' ? 'slide-right' : 'slide-left'">

        <div v-if="showPopover" 
          @mouseenter="clearHideTimer"
          @mouseleave="hidePopover"
          class="fixed z-9999 flex max-h-[calc(100vh-2rem)] w-72 max-w-[calc(100vw-2rem)] flex-col gap-3 overflow-y-auto overscroll-contain rounded-xl border border-border-base/10 bg-glass-heavy p-4 shadow-2xl backdrop-blur-3xl custom-scrollbar"
          :style="popoverStyle">
          
          <!-- 详细内容区 -->
          <div class="flex items-center gap-3 border-b border-border-base/10 pb-2">
            <component :is="sourceIcon" class="size-5" :class="sourceColor" />
            <div class="min-w-0">
              <div class="text-sm font-black text-text-main truncate">{{ mod.name }}</div>
              <div class="text-xs text-text-dim font-mono">v {{ mod.version || 'Unknown' }}</div>
            </div>
          </div>
          
            <div class="space-y-1.5 text-xs text-text-dim font-mono">
              <div v-for="entry in detailTimeEntries" :key="entry.key" class="flex justify-between gap-3">
                <span class="opacity-60">{{ entry.label }}:</span>
                <span class="text-right">{{ formatTime(entry.timestamp, true) || '无记录' }}</span>
              </div>
              <div class="flex justify-between"><span class="opacity-60">储存占用:</span> <span>{{ formatFileSize(mod.file_size) }}</span></div>
              <div class="flex justify-between"><span class="opacity-60">跨库同项:</span> <span>{{ sameTargets.length || '无' }}</span></div>
              <div class="flex justify-between"><span class="opacity-60">同库冲突:</span> <span>{{ conflictTargets.length || '无' }}</span></div>
              <div class="flex justify-between"><span class="opacity-60">替代项:</span> <span>{{ replacementTargets.length || '无' }}</span></div>
            </div>

          <div v-if="mod.path" class="mt-2 p-2 bg-bg-inset/80 rounded-lg border border-border-base/5 text-[0.7rem] text-text-dim break-all cursor-text select-text">
            {{ mod.path }}
          </div>
          
          <div class="text-[0.65rem] text-text-disabled mt-1 italic text-center">右键点击卡片可查看变动时间线与更多操作</div>
        </div>

      </Transition>
    </Teleport>

  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { Folder, CloudDownload, Disc } from 'lucide-vue-next'
import { formatFileSize } from '../../../shared/lib/format'
import { useAppStore } from '../../../app/stores/appStore'
import { useWorkspaceStore } from '../workspaceStore'
import { SOURCE_TYPE_MAP } from '../../../shared/lib/constants'
import { getMatrixItemState, normalizeMatrixTimestamp } from '../lib/matrixItemState'

const appStore = useAppStore()
const workspaceStore = useWorkspaceStore()

const props = defineProps({
  mod: Object,
  storeType: String,
  lastPlayedTime: Number,
  lastRunTime: Number,
  isSelected: Boolean,
})

const emit = defineEmits(['contextmenu'])

const itemRef = ref(null)
const showPopover = ref(false)
const popoverStyle = ref({})
const popoverDirection = ref('right')
let hideTimer = null
let showTimer = null

// --- 状态计算 ---
const matrixState = computed(() => getMatrixItemState(props.mod, props.lastPlayedTime, workspaceStore, props.lastRunTime))

const sourceIcon = computed(() => {
  if (props.storeType === 'workshop') return CloudDownload
  if (props.storeType === 'self') return Disc
  return Folder
})

const sourceColor = computed(() => {
  if (props.storeType === 'workshop') return 'text-accent-primary'
  if (props.storeType === 'self') return 'text-accent-success'
  return 'text-accent-warn'
})
const sameTargets = computed(() => matrixState.value.sameTargets)
const conflictTargets = computed(() => matrixState.value.conflictTargets)
const replacementTargets = computed(() => matrixState.value.replacementTargets)
const formatRelationTooltip = (title, items) => {
  if (!items?.length) return null
  return `${title}：\n${items.map(item => {
    const storeLabel = SOURCE_TYPE_MAP[item.store] || item.store || '未知'
    const nameLabel = item.name || item.package_id || '未命名模组'
    const pathLabel = item.path || '缺失记录'
    return `${storeLabel} · ${nameLabel}\n${pathLabel}`
  }).join('\n')}`
}
const sameItemsTooltip = computed(() => formatRelationTooltip('其它库存在相同项', sameTargets.value))
const conflictItemsTooltip = computed(() => formatRelationTooltip('当前库存在同包名冲突项', conflictTargets.value))
const replacementItemsTooltip = computed(() => formatRelationTooltip('已检测到替代项', replacementTargets.value))

const formatTime = (value, full = false) => {
  const timestamp = normalizeMatrixTimestamp(value)
  if (!timestamp) return ''
  const date = new Date(timestamp)
  if (full) {
    return date.toLocaleString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    })
  }
  return date.toLocaleDateString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  })
}

const buildTimeEntry = (key, label, value) => ({ key, label, timestamp: normalizeMatrixTimestamp(value) })
const appendUniqueTimeEntry = (entries, entry) => {
  if (!entry?.timestamp || entries.some(item => item.key === entry.key)) return
  entries.push(entry)
}
const appendLatestVersionTimeEntry = (entries, latestVersionTime, installedVersionTime) => {
  const latestTimestamp = normalizeMatrixTimestamp(latestVersionTime)
  const installedTimestamp = normalizeMatrixTimestamp(installedVersionTime)
  if (!latestTimestamp || latestTimestamp === installedTimestamp) return
  appendUniqueTimeEntry(entries, { key: 'latest', label: '可用版本', timestamp: latestTimestamp })
}
const appendWorkshopActionTimeEntry = (entries, steamStatus) => {
  const subscribedTimestamp = normalizeMatrixTimestamp(steamStatus.time_subscribed)
  const unsubscribedTimestamp = normalizeMatrixTimestamp(steamStatus.time_unsubscribed)
  if (!subscribedTimestamp && !unsubscribedTimestamp) return
  if (unsubscribedTimestamp > subscribedTimestamp) {
    appendUniqueTimeEntry(entries, { key: 'unsubscribed', label: '取消订阅', timestamp: unsubscribedTimestamp })
    return
  }
  appendUniqueTimeEntry(entries, { key: 'subscribed', label: '订阅时间', timestamp: subscribedTimestamp })
}
const appendDownloadTimeEntry = (entries, mod) => {
  appendUniqueTimeEntry(entries, {
    key: 'download',
    label: '下载时间',
    timestamp: normalizeMatrixTimestamp(mod.download_status?.download_time)
  })
}
const detailTimeEntries = computed(() => {
  const mod = props.mod || {}
  const steamStatus = mod.steam_status || {}
  const entries = []

  if (props.storeType === 'workshop') {
    appendDownloadTimeEntry(entries, mod)
    appendUniqueTimeEntry(entries, buildTimeEntry('installed', '当前版本', steamStatus.installed_version_time))
    appendLatestVersionTimeEntry(entries, steamStatus.latest_version_time, steamStatus.installed_version_time)
    appendWorkshopActionTimeEntry(entries, steamStatus)
  } else if (props.storeType === 'self') {
    appendDownloadTimeEntry(entries, mod)
    appendUniqueTimeEntry(entries, buildTimeEntry('installed', '当前版本', steamStatus.installed_version_time))
    appendLatestVersionTimeEntry(entries, steamStatus.latest_version_time, steamStatus.installed_version_time)
  }

  appendUniqueTimeEntry(entries, buildTimeEntry('modify', '文件修改', mod.file_modify_time))
  appendUniqueTimeEntry(entries, buildTimeEntry('create', '文件创建', mod.file_create_time))
  return entries
})
const summaryTimeEntries = computed(() => {
  const summaryKeys = props.storeType === 'local'
    ? ['modify', 'create']
    : matrixState.value.isUpdate
      ? ['latest', 'download', 'installed', 'modify', 'create']
      : ['download', 'installed', 'modify', 'create']

  const summary = []
  summaryKeys.forEach(key => {
    const entry = detailTimeEntries.value.find(item => item.key === key)
    if (entry && !summary.some(item => item.key === entry.key) && summary.length < 2) {
      summary.push(entry)
    }
  })
  return summary
})
const getSummaryTimeClass = (entry, index) => {
  if (!entry) return 'text-text-dim'
  if (entry.key === 'create') return matrixState.value.isNew ? 'text-accent-primary font-black' : 'text-text-dim'
  if (entry.key === 'latest' && matrixState.value.isUpdate) return 'text-accent-warn font-black'
  if (index === 0 && matrixState.value.isChange) return 'text-accent-tip font-black'
  return 'text-text-dim'
}

// --- 智能悬浮层逻辑 ---
const handleMouseEnter = () => {
  clearHideTimer()
  // 延迟 400ms 弹出，防止鼠标划过时闪烁
  showTimer = setTimeout(() => {
    calculatePosition()
    showPopover.value = true
  }, 400)
}
const handleMouseLeave = () => {
  if (showTimer) clearTimeout(showTimer)
  hideTimer = setTimeout(() => {
    showPopover.value = false
  }, 200) // 给 200ms 时间让鼠标可以移到 popover 上
}
const clearHideTimer = () => {
  if (hideTimer) clearTimeout(hideTimer)
}
const hidePopover = () => {
  handleMouseLeave()
}
const getRootFontSize = () => {
  if (typeof window === 'undefined') return 16
  return Number.parseFloat(getComputedStyle(document.documentElement).fontSize) || 16
}
const calculatePosition = () => {
  if (!itemRef.value) return
  const rect = itemRef.value.getBoundingClientRect()
  const vw = window.innerWidth
  const vh = window.innerHeight
  const rootFontSize = getRootFontSize()
  const gap = rootFontSize
  const margin = rootFontSize
  const panelWidth = Math.min(rootFontSize * 18, Math.max(rootFontSize * 10, vw - margin * 2))
  const panelHeight = Math.min(rootFontSize * 22, Math.max(rootFontSize * 10, vh - margin * 2))

  const rightSpace = vw - rect.right - margin
  const leftSpace = rect.left - margin
  const opensRight = rightSpace >= panelWidth || rightSpace >= leftSpace

  // 设置弹出层方向
  popoverDirection.value = opensRight ? 'right' : 'left'

  let left = opensRight
    ? rect.right + gap
    : rect.left - panelWidth - gap
  left = Math.min(Math.max(margin, left), Math.max(margin, vw - panelWidth - margin))

  let top = rect.top - margin
  top = Math.min(Math.max(margin, top), Math.max(margin, vh - panelHeight - margin))

  popoverStyle.value = {
    left: `${Math.round(left)}px`,
    top: `${Math.round(top)}px`,
  }
}

// 代理右键事件给父组件
const openContextMenu = (e) => {
  emit('contextmenu', e, props.mod)
  hidePopover() // 打开菜单时隐藏详情
}


</script>

<style scoped>
.slide-right-enter-active, .slide-right-leave-active,
.slide-left-enter-active, .slide-left-leave-active {
  transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
}
.slide-right-enter-from, .slide-right-leave-to { opacity: 0; transform: translateX(-0.9375rem) scale(0.95); }
.slide-left-enter-from, .slide-left-leave-to { opacity: 0; transform: translateX(0.9375rem) scale(0.95); }
</style>
