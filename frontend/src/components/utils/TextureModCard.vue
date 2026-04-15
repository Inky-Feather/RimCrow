<template>
  <div class="group flex min-h-24 flex-col justify-between border-b border-text-main/5 px-3 py-2 transition-colors hover:bg-text-main/4">
    <div class="flex min-w-0 items-center justify-between gap-4">
      <div class="flex min-w-0 items-center gap-2">
        <span class="truncate text-sm font-bold text-text-main">{{ mod.mod_name }}</span>
        <span v-if="mod.skip_mask_count > 0" v-tooltip="'生成时需要忽略的贴图如法线贴图、遮罩贴图等'" tabindex="0" class="shrink-0 cursor-help rounded border border-accent-special/20 bg-accent-special/10 px-1.5 py-0.5 text-xs font-bold text-accent-special">忽略 {{ mod.skip_mask_count }}</span>
        <span v-if="mod.unsupported_source_count > 0" v-tooltip="unsupportedTooltip"
          class="shrink-0 rounded border border-accent-warning/20 bg-accent-warning/10 px-1.5 py-0.5 text-xs font-bold text-accent-warning">
          无效 PNG {{ mod.unsupported_source_count }}
        </span>
        <span v-if="mod.external_orphan_output_count > 0" class="shrink-0 rounded border border-accent-primary/20 bg-accent-primary/10 px-1.5 py-0.5 text-xs font-bold text-accent-primary">无源 DDS {{ mod.external_orphan_output_count }}</span>
      </div>

      <div class="flex shrink-0 items-center gap-2">
        <div class="text-right text-xs font-mono text-text-dim">
          <span>待生成 {{ mod.generate_required_count || 0 }}</span>
          <span class="mx-2 opacity-40">|</span>
          <span>已完成 {{ mod.managed_output_count || 0 }}</span>
        </div>
        <button
          class="rounded-lg p-1.5 text-text-dim transition-colors hover:bg-text-main/10 hover:text-text-main"
          v-tooltip="mod.mod_path || '打开模组路径'"
          @click.stop="openModPath"
        >
          <FolderOpen class="w-4 h-4" />
        </button>
      </div>
    </div>

    <div class="items-center text-xs">
      <div class="flex items-center gap-2">
        <div v-show="viewMode === 'ALL' || viewMode === 'PNG'" class="shrink-0 font-bold text-accent-tip/80">PNG</div>
        <div v-show="viewMode === 'ALL' || viewMode === 'PNG'" class="flex-1 relative h-1.5 overflow-hidden rounded-full bg-black/40">
          <div class="absolute left-0 top-0 h-full rounded-full bg-linear-to-r from-accent-tip/60 to-accent-tip transition-all duration-500 ease-out" :style="{ width: pngWidth }"></div>
        </div>
        <div v-show="viewMode === 'ALL' || viewMode === 'PNG'" class="text-right font-mono text-text-dim">总占比：{{ formatPercent(mod.source_bytes_share_pct || 0) }}</div>
      </div>

      <div class="flex items-center gap-2">
        <div v-show="viewMode === 'ALL' || viewMode === 'DDS'" class="shrink-0 font-bold text-accent-primary/80">DDS</div>
        <div v-show="viewMode === 'ALL' || viewMode === 'DDS'" class="flex-1 relative h-1.5 overflow-hidden rounded-full bg-black/40">
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
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { FolderOpen } from 'lucide-vue-next'
import { useAppStore } from '../../stores/appStore'

const props = defineProps({
  mod: { type: Object, required: true },
  viewMode: { type: String, default: 'ALL' },
  maxBytes: { type: Number, default: 1 }
})

const appStore = useAppStore()

const unsupportedTooltip = computed(() => {
  const preview = Array.isArray(props.mod?.engine_unsupported_preview) ? props.mod.engine_unsupported_preview : []
  if (!preview.length) {
    return '发现扩展名为 PNG、但文件内容并不是 PNG 的伪装源图，todds 无法处理。'
  }
  return [
    '以下伪装 PNG 已自动跳过：',
    ...preview.map(item => `${item.rel_path}${item.reason ? ` - ${item.reason}` : ''}`),
  ].join('\n')
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
