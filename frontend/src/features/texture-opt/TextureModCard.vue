<template>
  <div class="group flex min-h-24 flex-col justify-between rounded-lg border border-border-base/2 px-3 py-2 transition-colors hover:bg-bg-overlay/5"
    @contextmenu.prevent="emit('open-mod-menu', $event, mod)">
    <div class="flex min-w-0 items-center justify-between gap-4">
      <div class="flex min-w-0 flex-wrap items-center gap-2">
        <span class="truncate text-sm font-bold text-text-main">{{ mod.mod_name }}</span>
        <span v-if="storeLabel" class="shrink-0 rounded border border-border-base/10 bg-bg-overlay/5 px-1.5 py-0.5 text-xs font-bold text-text-dim">
          {{ storeLabel }}
        </span>
        <span v-if="mod.scan_status === 'failed'" class="shrink-0 rounded border border-accent-danger/20 bg-accent-danger/10 px-1.5 py-0.5 text-xs font-bold text-accent-danger">
          {{ t('tasks.texture.scan_failed_title', '贴图扫描失败') }}
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
          :class="isExcluded ? 'border-accent-danger/30 bg-accent-danger/10 text-accent-danger' : 'border-border-base/10 bg-bg-overlay/5 text-accent-warn/60 hover:text-text-main'"
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
import { t } from '../../shared/i18n.js'
import { getStoreTypeLabel } from '../../shared/lib/constants'
import { getTextureKeepOriginalReasonItems, getTextureScaleBreakdownItems, sumTextureScaleBreakdownItems } from './textureStore'

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
  const tags = []
  const buildDetailTooltip = (title, items) => [
    title,
    ...items.map(item => t('ui.texture_opt.detail_item', '{label}: {count} 张', {
      label: String(item?.label || t('ui.texture_opt.card.scale.original_size', '原尺寸')),
      count: Number(item?.count || 0),
    })),
  ].join('\n')

  const scaledItems = getTextureScaleBreakdownItems(props.mod, 'scaled')
  const scaledCount = Number(props.mod?.scaled_count || sumTextureScaleBreakdownItems(scaledItems))
  if (scaledCount > 0) {
    tags.push({
      kind: 'scaled',
      label: 'scaled',
      text: t('ui.texture_opt.card.scale.scaled_text', '当前比例 ({count})', { count: scaledCount }),
      tooltip: buildDetailTooltip(t('ui.texture_opt.card.scale.scaled_tooltip_title', '当前比例明细：'), scaledItems),
      className: 'border-accent-tip/20 bg-accent-tip/10 text-accent-tip',
    })
  }

  const fallbackItems = getTextureScaleBreakdownItems(props.mod, 'fallback')
  const fallbackCount = Number(props.mod?.fallback_scaled_count || sumTextureScaleBreakdownItems(fallbackItems))
  if (fallbackCount > 0) {
    tags.push({
      kind: 'fallback',
      label: 'fallback',
      text: t('ui.texture_opt.card.scale.fallback_text', '回退 ({count})', { count: fallbackCount }),
      tooltip: buildDetailTooltip(t('ui.texture_opt.card.scale.fallback_tooltip_title', '自动回退明细：'), fallbackItems),
      className: 'border-accent-secondary/20 bg-accent-secondary/10 text-accent-secondary',
    })
  }

  const keepCount = Number(props.mod?.keep_original_count || 0)
  if (keepCount > 0) {
    const keepItems = getTextureKeepOriginalReasonItems(props.mod, {
      normal: t('ui.texture_opt.card.scale.keep_normal_label', '不缩放'),
      mask: t('ui.texture_opt.card.scale.keep_mask_label', '遮罩贴图不缩放'),
      range: t('ui.texture_opt.card.scale.keep_range_label', '超范围不缩放'),
    })
    tags.push({
      kind: 'keep_original',
      label: 'keep_original',
      text: t('ui.texture_opt.card.scale.keep_text', '不缩放 ({count})', { count: keepCount }),
      tooltip: buildDetailTooltip(t('ui.texture_opt.card.scale.keep_tooltip_title', '不缩放明细：'), keepItems),
      className: 'border-border-base/10 bg-bg-overlay/5 text-text-dim',
    })
  }

  return tags
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
