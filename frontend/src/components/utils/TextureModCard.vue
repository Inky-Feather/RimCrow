<template>
  <div class="group flex min-h-24 flex-col justify-between rounded-lg border border-border-base/2 px-3 py-2 transition-colors hover:bg-bg-overlay/5">
    <div class="flex min-w-0 items-center justify-between gap-4">
      <div class="flex min-w-0 flex-wrap items-center gap-2">
        <span class="truncate text-sm font-bold text-text-main">{{ mod.mod_name }}</span>
        <span v-if="storeLabel" class="shrink-0 rounded border border-border-base/10 bg-bg-overlay/5 px-1.5 py-0.5 text-[11px] font-bold text-text-dim">
          {{ storeLabel }}
        </span>
        <span v-if="mod.unsupported_source_count > 0" v-tooltip="unsupportedTooltip"
          class="shrink-0 rounded border border-accent-warning/20 bg-accent-warning/10 px-1.5 py-0.5 text-xs font-bold text-accent-warning">
          无效 PNG {{ mod.unsupported_source_count }}
        </span>
        <span v-for="tag in scaleTags" :key="`${tag.kind}-${tag.label}`" v-tooltip="tag.tooltip"
          class="shrink-0 rounded border px-1.5 py-0.5 text-xs font-bold" :class="tag.className" >
          {{ tag.text }}
        </span>
      </div>

      <div class="flex shrink-0 items-center gap-2">
        <div class="text-right text-xs font-mono text-text-dim">
          <span>待生成 {{ mod.generate_required_count || 0 }}</span>
          <span class="mx-2 opacity-40">|</span>
          <span>现有 DDS {{ mod.output_total_count || 0 }}</span>
        </div>
        <button v-if="mod.package_id" class="rounded-lg border px-1 py-0.5 text-xs font-bold transition-colors"
          :class="isExcluded ? 'border-accent-danger/30 bg-accent-danger/10 text-accent-danger' : 'border-border-base/10 bg-bg-overlay/5 text-text-dim hover:text-text-main'"
          @click.stop="emit('toggle-mod-exclusion', mod)" >
          {{ isExcluded ? '已排除' : '排除模组' }}
        </button>
        <button class="rounded-lg p-1.5 text-text-dim transition-colors hover:bg-bg-overlay/10 hover:text-text-main"
          @click.stop="openModPath" v-tooltip="mod.mod_path || '打开模组路径'" >
          <FolderOpen class="w-4 h-4" />
        </button>
      </div>
    </div>

    <div class="items-center text-xs my-1">
      <div class="flex items-center gap-2">
        <div v-show="viewMode === 'ALL' || viewMode === 'PNG'" class="shrink-0 font-bold text-accent-tip/80">PNG</div>
        <div v-show="viewMode === 'ALL' || viewMode === 'PNG'" class="flex-1 relative h-1.5 overflow-hidden rounded-full bg-bg-inset/80">
          <div class="absolute left-0 top-0 h-full rounded-full bg-linear-to-r from-accent-tip/60 to-accent-tip transition-all duration-500 ease-out" :style="{ width: pngWidth }"></div>
        </div>
        <div v-show="viewMode === 'ALL' || viewMode === 'PNG'" class="text-right font-mono text-text-dim">总占比：{{ formatPercent(mod.source_bytes_share_pct || 0) }}</div>
      </div>

      <div class="flex items-center gap-2">
        <div v-show="viewMode === 'ALL' || viewMode === 'DDS'" class="shrink-0 font-bold text-accent-primary/80">DDS</div>
        <div v-show="viewMode === 'ALL' || viewMode === 'DDS'" class="flex-1 relative h-1.5 overflow-hidden rounded-full bg-bg-inset/80">
          <div class="absolute left-0 top-0 h-full rounded-full bg-linear-to-r from-accent-primary/60 to-accent-primary transition-all duration-500 ease-out" :style="{ width: ddsWidth }"></div>
        </div>
        <div v-show="viewMode === 'ALL' || viewMode === 'DDS'" class="text-right font-mono text-text-dim">总占比：{{ formatPercent(mod.output_bytes_share_pct || 0) }}</div>
      </div>
    </div>


    <div class="grid grid-cols-4 items-center gap-x-4 text-xs text-text-dim">
      <div class="truncate"><span class="font-bold text-text-main">PNG</span> {{ formatBytes(mod.source_total_bytes) }} / {{ mod.source_total_count || 0 }}张</div>
      <div class="truncate"><span class="font-bold text-text-main">DDS</span> {{ formatBytes(mod.output_total_bytes) }} / {{ mod.output_total_count || 0 }}张</div>
      <div class="truncate"><span class="font-bold text-text-main">综合体积占比</span> {{ formatPercent(mod.combined_bytes_share_pct || 0) }}</div>
      <div class="truncate"><span class="font-bold text-text-main">显存预估</span> {{ formatBytes(mod.source_vram_bytes_est) }} → {{ formatBytes(mod.output_vram_bytes_est) }}</div>
    </div>
    <div class="truncate text-[11px] text-text-dim">{{ mod.mod_path }}</div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { FolderOpen } from 'lucide-vue-next'
import { useAppStore } from '../../stores/appStore'

const props = defineProps({
  mod: { type: Object, required: true },
  viewMode: { type: String, default: 'ALL' },
  maxBytes: { type: Number, default: 1 },
  isExcluded: { type: Boolean, default: false },
})

const emit = defineEmits(['toggle-mod-exclusion'])

const appStore = useAppStore()

const unsupportedTooltip = computed(() => {
  const preview = Array.isArray(props.mod?.engine_unsupported_preview) ? props.mod.engine_unsupported_preview : []
  if (!preview.length) {
    return '有些文件虽然名字是 PNG，但内容不是正常图片，已经自动跳过。'
  }
  return [
    '以下伪装 PNG 已自动跳过：',
    ...preview.map(item => `${item.rel_path}${item.reason ? ` - ${item.reason}` : ''}`),
  ].join('\n')
})

const storeLabel = computed(() => {
  const store = String(props.mod?.store || '').trim().toLowerCase()
  if (store === 'workshop') return 'Steam'
  if (store === 'local') return 'Local'
  if (store === 'self') return 'Manager'
  return store ? store : ''
})

const scaleTags = computed(() => {
  const breakdown = Array.isArray(props.mod?.scale_breakdown) ? props.mod.scale_breakdown : []
  return breakdown
    .filter(item => Number(item?.count || 0) > 0)
    .map(item => {
      const kind = String(item?.kind || 'keep_original')
      const label = String(item?.label || '原尺寸')
      const count = Number(item?.count || 0)
      if (kind === 'fallback') {
        return {
          kind,
          label,
          text: `回退${label} (${count})`,
          tooltip: `这些图片不适合当前比例，会自动回退到 ${label} 处理。`,
          className: 'border-accent-secondary/20 bg-accent-secondary/10 text-accent-secondary',
        }
      }
      if (kind === 'scaled') {
        return {
          kind,
          label,
          text: `当前${label} (${count})`,
          tooltip: `这些图片会按 ${label} 缩放生成。`,
          className: 'border-accent-tip/20 bg-accent-tip/10 text-accent-tip',
        }
      }
      return {
        kind,
        label,
        text: `不缩放 (${count})`,
        tooltip: '这些图片会保留原来的大小。',
        className: 'border-border-base/10 bg-bg-overlay/5 text-text-dim',
      }
    })
})

const formatBytes = (bytes) => {
  const value = Number(bytes || 0)
  if (!value) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  let size = value
  let index = 0
  while (size >= 1024 && index < units.length - 1) {
    size /= 1024
    index += 1
  }
  const precision = size >= 100 || index === 0 ? 0 : size >= 10 ? 1 : 2
  return `${size.toFixed(precision)} ${units[index]}`
}

const formatPercent = (value) => `${Number(value || 0).toFixed(2)}%`

const pngWidth = computed(() => {
  const percent = (Number(props.mod.source_total_bytes || 0) / Number(props.maxBytes || 1)) * 100
  return `${Math.min(100, Math.max(0.5, percent))}%`
})

const ddsWidth = computed(() => {
  const percent = (Number(props.mod.output_total_bytes || 0) / Number(props.maxBytes || 1)) * 100
  return `${Math.min(100, Math.max(0.5, percent))}%`
})

const openModPath = async () => {
  if (!props.mod?.mod_path) return
  await appStore.openPath(props.mod.mod_path)
}
</script>
