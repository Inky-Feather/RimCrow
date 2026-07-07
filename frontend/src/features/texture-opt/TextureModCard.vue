<template>
  <div class="group flex min-h-24 flex-col justify-between rounded-lg border border-border-base/2 px-3 py-2 transition-colors hover:bg-bg-overlay/5"
    @contextmenu.prevent="emit('open-mod-menu', $event, mod)">
    <div class="flex min-w-0 items-center justify-between gap-4">
      <div class="flex min-w-0 flex-wrap items-center gap-2">
        <span class="truncate text-sm font-bold text-text-main">{{ mod.mod_name }}</span>
        <span v-if="storeLabel" class="shrink-0 rounded border border-border-base/10 bg-bg-overlay/5 px-1.5 py-0.5 text-xs font-bold text-text-dim">
          {{ storeLabel }}
        </span>
        <span v-if="mod.unsupported_source_count > 0" v-tooltip="unsupportedTooltip"
          class="shrink-0 rounded border border-accent-warning/20 bg-accent-warning/10 px-1.5 py-0.5 text-xs font-bold text-accent-warning">
          {{ t('ui.texture_opt.card.invalid_png_count', '无效 PNG {count}', { count: mod.unsupported_source_count }) }}
        </span>
        <span v-for="tag in scaleTags" :key="`${tag.kind}-${tag.label}`" v-tooltip="tag.tooltip"
          class="shrink-0 rounded border px-1.5 py-0.5 text-xs font-bold" :class="tag.className" >
          {{ tag.text }}
        </span>
      </div>

      <div class="flex shrink-0 items-center gap-2">
        <div class="text-right text-xs font-mono text-text-dim">
          <span>{{ t('ui.texture_opt.card.pending_generate_count', '待生成 {count}', { count: mod.generate_required_count || 0 }) }}</span>
          <span class="mx-2 opacity-40">|</span>
          <span>{{ t('ui.texture_opt.card.existing_dds_count', '现有 DDS {count}', { count: mod.dds_output_count || 0 }) }}</span>
          <span v-if="mod.zstd_output_count" class="mx-2 opacity-40">|</span>
          <span v-if="mod.zstd_output_count">ZSTD {{ mod.zstd_output_count }}</span>
        </div>
        <button v-if="mod.package_id" class="rounded-lg border px-1 py-0.5 text-xs font-bold transition-colors"
          :class="isExcluded ? 'border-accent-danger/30 bg-accent-danger/10 text-accent-danger' : 'border-border-base/10 bg-bg-overlay/5 text-text-dim hover:text-text-main'"
          @click.stop="emit('toggle-mod-exclusion', mod)" >
          {{ isExcluded ? t('ui.texture_opt.card.excluded_label', '已排除') : t('ui.texture_opt.card.exclude_mod_label', '排除模组') }}
        </button>
        <button class="rounded-lg p-1.5 text-text-dim transition-colors hover:bg-bg-overlay/10 hover:text-text-main"
          @click.stop="emit('open-mod-menu', $event, mod)" v-tooltip="t('ui.texture_opt.card.mod_texture_actions', '模组贴图操作')">
          <MoreVertical class="w-4 h-4" />
        </button>
        <button class="rounded-lg p-1.5 text-text-dim transition-colors hover:bg-bg-overlay/10 hover:text-text-main"
          @click.stop="openModPath" v-tooltip="mod.mod_path || t('ui.texture_opt.card.open_mod_path', '打开模组路径')" >
          <FolderOpen class="w-4 h-4" />
        </button>
      </div>
    </div>

    <div class="my-1 space-y-1 text-xs">
      <div v-show="viewMode === 'ALL' || viewMode === 'PNG'" class="grid grid-cols-[2rem_minmax(0,1fr)_3rem] items-center gap-2">
        <div class="font-bold text-accent-tip/80">PNG</div>
        <div class="relative h-1.5 overflow-hidden rounded-full bg-bg-inset/80">
          <div class="absolute left-0 top-0 h-full rounded-full bg-linear-to-r from-accent-tip/60 to-accent-tip transition-all duration-500 ease-out" :style="{ width: pngWidth }"></div>
        </div>
        <div class="text-right font-mono text-text-dim">{{ formatPercent(mod.source_bytes_share_pct || 0) }}</div>
      </div>

      <div v-show="viewMode === 'ALL' || viewMode === 'DDS'" class="grid grid-cols-[2rem_minmax(0,1fr)_3rem] items-center gap-2">
        <div class="font-bold text-accent-primary/80">DDS</div>
        <div class="relative h-1.5 overflow-hidden rounded-full bg-bg-inset/80">
          <div class="absolute left-0 top-0 h-full rounded-full bg-linear-to-r from-accent-primary/60 to-accent-primary transition-all duration-500 ease-out" :style="{ width: ddsWidth }"></div>
        </div>
        <div class="text-right font-mono text-text-dim">{{ formatPercent(mod.dds_output_bytes_share_pct || 0) }}</div>
      </div>

      <div v-show="viewMode === 'ALL' || viewMode === 'ZSTD'" class="grid grid-cols-[2rem_minmax(0,1fr)_3rem] items-center gap-2">
        <div class="font-bold text-accent-secondary/80">ZSTD</div>
        <div class="relative h-1.5 overflow-hidden rounded-full bg-bg-inset/80">
          <div class="absolute left-0 top-0 h-full rounded-full bg-linear-to-r from-accent-secondary/60 to-accent-secondary transition-all duration-500 ease-out" :style="{ width: zstdWidth }"></div>
        </div>
        <div class="text-right font-mono text-text-dim">{{ formatPercent(mod.zstd_output_bytes_share_pct || 0) }}</div>
      </div>
    </div>


    <div class="grid grid-cols-4 items-center gap-x-4 text-xs text-text-dim">
      <div class="truncate"><span class="font-bold text-text-main">PNG</span> {{ formatBytes(mod.source_total_bytes) }} / {{ t('ui.texture_opt.card.image_count', '{count}张', { count: mod.source_total_count || 0 }) }}</div>
      <div class="truncate">
        <span class="font-bold text-text-main">DDS</span> {{ formatBytes(mod.dds_output_bytes) }} / {{ t('ui.texture_opt.card.image_count', '{count}张', { count: mod.dds_output_count || 0 }) }}
        <span v-if="mod.zstd_output_count" class="ml-2"><span class="font-bold text-text-main">ZSTD</span> {{ formatBytes(mod.zstd_output_bytes) }} / {{ t('ui.texture_opt.card.image_count', '{count}张', { count: mod.zstd_output_count }) }}</span>
      </div>
      <div class="truncate"><span class="font-bold text-text-main">{{ t('ui.texture_opt.card.combined_share', '综合体积占比') }}</span> {{ formatPercent(mod.combined_bytes_share_pct || 0) }}</div>
      <div class="truncate"><span class="font-bold text-text-main">{{ t('ui.texture_opt.card.vram_estimate', '显存预估') }}</span> {{ formatBytes(mod.source_vram_bytes_est) }} → {{ formatBytes(mod.output_vram_bytes_est) }}</div>
    </div>
    <div class="truncate text-[0.8rem] text-text-subtle">{{ mod.mod_path }}</div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { FolderOpen, MoreVertical } from 'lucide-vue-next'
import { useAppStore } from '../../app/stores/appStore'
import { t } from '../../shared/i18n'
import { getStoreTypeLabel } from '../../shared/lib/constants'

const props = defineProps({
  mod: { type: Object, required: true },
  viewMode: { type: String, default: 'ALL' },
  maxBytes: { type: Number, default: 1 },
  isExcluded: { type: Boolean, default: false },
})

const emit = defineEmits(['toggle-mod-exclusion', 'open-mod-menu'])

const appStore = useAppStore()

const unsupportedTooltip = computed(() => {
  const preview = Array.isArray(props.mod?.engine_unsupported_preview) ? props.mod.engine_unsupported_preview : []
  if (!preview.length) {
    return t('ui.texture_opt.card.unsupported_no_preview', '有些文件虽然名字是 PNG，但内容不是正常图片，已经自动跳过。')
  }
  return [
    t('ui.texture_opt.card.unsupported_preview_title', '以下伪装 PNG 已自动跳过：'),
    ...preview.map(item => `${item.rel_path}${item.reason ? ` - ${item.reason}` : ''}`),
  ].join('\n')
})

const storeLabel = computed(() => {
  const store = String(props.mod?.store || '').trim().toLowerCase()
  return store ? getStoreTypeLabel(store) : ''
})

const scaleTags = computed(() => {
  const breakdown = Array.isArray(props.mod?.scale_breakdown) ? props.mod.scale_breakdown : []
  return breakdown
    .filter(item => Number(item?.count || 0) > 0)
    .map(item => {
      const kind = String(item?.kind || 'keep_original')
      const label = String(item?.label || t('ui.texture_opt.card.scale.original_size', '原尺寸'))
      const count = Number(item?.count || 0)
      if (kind === 'fallback') {
        return {
          kind,
          label,
          text: t('ui.texture_opt.card.scale.fallback_text', '回退{label} ({count})', { label, count }),
          tooltip: t('ui.texture_opt.card.scale.fallback_tooltip', '这些图片不适合当前比例，会自动回退到 {label} 处理。', { label }),
          className: 'border-accent-secondary/20 bg-accent-secondary/10 text-accent-secondary',
        }
      }
      if (kind === 'scaled') {
        return {
          kind,
          label,
          text: t('ui.texture_opt.card.scale.scaled_text', '当前{label} ({count})', { label, count }),
          tooltip: t('ui.texture_opt.card.scale.scaled_tooltip', '这些图片会按 {label} 缩放生成。', { label }),
          className: 'border-accent-tip/20 bg-accent-tip/10 text-accent-tip',
        }
      }
      return {
        kind,
        label,
        text: t('ui.texture_opt.card.scale.keep_text', '不缩放 ({count})', { count }),
        tooltip: t('ui.texture_opt.card.scale.keep_tooltip', '这些图片会保留原来的大小。'),
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
  const percent = (Number(props.mod.dds_output_bytes || 0) / Number(props.maxBytes || 1)) * 100
  return `${Math.min(100, Math.max(0.5, percent))}%`
})

const zstdWidth = computed(() => {
  const percent = (Number(props.mod.zstd_output_bytes || 0) / Number(props.maxBytes || 1)) * 100
  return `${Math.min(100, Math.max(0.5, percent))}%`
})

const openModPath = async () => {
  if (!props.mod?.mod_path) return
  await appStore.openPath(props.mod.mod_path)
}
</script>
