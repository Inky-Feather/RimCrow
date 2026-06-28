<template>
  <div class="py-[2px] flex items-center gap-1 select-none relative" :data-id="selectionId || itemId">
    <!-- 分组列表只需要选择/拖拽/预览，不承载主列表的右键菜单、规则提示、联锁检测等重逻辑。 -->
    <button v-if="showIndex" type="button"
      class="swipe-trigger w-6 h-6 flex items-center justify-center rounded transition-all"
      :class="isSelected
        ? `text-text-main bg-accent-${listColor}/50`
        : `text-accent-${listColor}/50 bg-accent-${listColor}/10 hover:text-text-main hover:bg-accent-${listColor}/50`"
      :style="{ width: appStore.scalePx(25) + 'px', height: appStore.scalePx(25) + 'px' }">
      {{ index + 1 }}
    </button>

    <!-- 分组展开后可能一次出现很多行。行级 backdrop-filter 会放大合成成本，
      因此只使用半透明背景和边框表达层次，把毛玻璃限制在更少的外层面板上。 -->
    <div class="select-trigger drag-handle flex-1 flex items-center min-w-0 gap-1.5 p-1 rounded-lg border relative group hover:brightness-150 shadow-sm text-text-soft transition-colors duration-150"
      :class="[searchMatch ? 'ring-2 ring-accent-highlight scale-[1.02] z-20' : '', cardClass]"
      :style="cardStyle"
      v-preview="modData">
      <!-- 缩略图只在用户开启分组图标时渲染；图片懒加载，避免展开大分组时一次性解码大量资源。 -->
      <div v-if="showIcon" class="shrink-0">
        <img v-if="modData?.path && modData?.preview_path" :src="appStore.getThumbUrl(modData.package_id, modData.preview_path)" loading="lazy"
          :class="`size-6 rounded object-cover border border-accent-${listColor}/30 pointer-events-none`">
        <div v-else-if="!modData?.path" class="size-6 rounded flex items-center justify-center text-accent-danger font-bold text-lg bg-accent-danger/15 border border-accent-danger/30">!</div>
        <div v-else :class="`size-6 rounded border-2 border-dashed border-border-base/10 flex items-center justify-center`">
          <component :is="typeIcon" class="size-5 opacity-50" />
        </div>
      </div>

      <div class="flex-1 min-w-0">
        <div class="text-sm font-medium truncate">{{ displayName }}</div>
      </div>
      <div class="absolute top-0 left-0 -z-100 w-full rounded-lg h-full group-hover:bg-bg-overlay/10"></div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useAppStore } from '../../app/stores/appStore'
import { useModStore } from './stores/modStore'
import { MOD_TYPE_ICON_MAP } from '../../shared/lib/constants'
import { hexToRgba } from '../../shared/lib/color'

const props = defineProps({
  itemId: { type: String, required: true },
  selectionId: { type: String, default: '' },
  index: { type: Number, required: true },
  listColor: { type: String, default: 'primary' },
  isSelected: { type: Boolean, default: false },
  searchMatch: { type: Boolean, default: false },
  showIndex: { type: Boolean, default: true },
  showIcon: { type: Boolean, default: true },
})

const appStore = useAppStore()
const modStore = useModStore()

const modData = computed(() => modStore.takeModById(props.itemId))
const displayName = computed(() => modData.value?.alias_name || modData.value?.name || props.itemId)
const modType = computed(() => modStore.displayModType(modData.value))
const typeIcon = computed(() => MOD_TYPE_ICON_MAP[modType.value] || MOD_TYPE_ICON_MAP.Unknown)
const cardClass = computed(() => {
  const selected = props.isSelected ? 'ring-2 ring-accent-special ' : ''
  return `${selected} bg-bg-surface/20 border-border-base/10 hover:border-border-base/18 hover:bg-bg-overlay/10`
})
const cardStyle = computed(() => {
  const base = { height: appStore.scalePx(30) + 'px', backgroundColor: 'rgba(var(--rgb-bg-highlight),0.3)'  }
  const color = modData.value?.sign_color
  if (!color) return base
  // 分组行保留签名色提示，但不计算主列表的问题状态，避免每个分组实例订阅大量额外状态。
  return {
    ...base,
    backgroundColor: hexToRgba(color, 0.1),
    borderColor: hexToRgba(color, 0.3),
    color,
  }
})
</script>
