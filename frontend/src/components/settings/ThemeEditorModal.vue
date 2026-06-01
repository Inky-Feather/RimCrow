<template>
  <Teleport to="body">
    <transition name="panel-fade">
      <div v-if="isOpen" ref="panelRef"
        class="fixed z-140 flex max-h-1/2 max-w-1/4 flex-col overflow-hidden rounded-3xl border border-accent-primary/24 bg-glass-heavy shadow-[0_18px_70px_var(--shadow-color)] backdrop-blur-xl"
        :style="panelStyle" >
        <div class="absolute -left-16 -top-20 size-52 rounded-full bg-accent-primary/10 blur-3xl pointer-events-none"></div>
        <div class="absolute -bottom-20 -right-16 size-52 rounded-full bg-accent-special/10 blur-3xl pointer-events-none"></div>

        <header class="relative z-10 flex cursor-move select-none items-center justify-between gap-3 border-b border-border-base/10 px-4 py-3"
          @pointerdown="handleDragStart" >
          <div class="min-w-0">
            <h3 class="truncate text-base font-black text-text-main">{{ draft.id ? '编辑主题配色' : '创建主题配色' }}</h3>
            <p class="mt-0.5 text-xs text-text-dim">可随意拖动窗口，边看界面边调颜色。</p>
          </div>
          <div class="flex shrink-0 items-center gap-2" @pointerdown.stop>
            <button class="modal-close-button"
              aria-label="关闭"
              @click="$emit('close')" >
              <X class="size-4" />
          </button>
          </div>
        </header>

        <div class="relative z-10 flex-1 overflow-y-auto p-3 custom-scrollbar">
          <label>
            <span class="mb-1 block px-1 text-xs font-bold uppercase tracking-widest text-text-dim">主题名称</span>
            <input v-model="draft.name" class="input-glass h-9 w-full px-3 text-sm text-text-main focus:outline-none" placeholder="例如：我的主题">
          </label>

          <section v-for="group in THEME_TOKEN_GROUPS" :key="group.key" class="modal-section mt-2 p-2.5">
            <h4 class="mb-2 text-sm font-black text-text-main">{{ group.label }}</h4>
            <div class="grid gap-1" :style="{ gridTemplateColumns: groupGridTemplate(group.key) }">
              <div v-for="token in group.tokens" :key="`${group.key}-${token.key}`" class="rounded-xl bg-bg-inset/45 px-2 py-0.5">
                <div class="flex items-start gap-2.5">
                  <button type="button" class="relative mt-0.5 size-7.5 shrink-0 overflow-hidden rounded-md ring-2 ring-border-base/55 shadow-sm transition-transform hover:scale-105"
                    :class="activeColorKey === colorFieldKey(group.key, token.key) ? 'ring-accent-primary/70' : ''" v-tooltip="draft.tokens[group.key][token.key]"
                    @pointerdown.stop @click.stop="openColorPicker(group.key, token.key, $event)" >
                    <span class="absolute inset-0 theme-alpha-grid"></span>
                    <span class="absolute inset-0" :style="getSwatchStyle(group.key, token.key)"></span>
                  </button>
                  <div class="min-w-0 flex-1">
                    <div class="text-sm font-bold leading-tight text-text-main">{{ token.label }}</div>
                    <p class="text-xs leading-relaxed text-text-dim">{{ token.usage }}</p>
                  </div>
                </div>
                <p v-if="showColorValue" class="truncate text-[0.65rem] text-text-dim">{{ draft.tokens[group.key][token.key] }}</p>
              </div>
            </div>
          </section>
        </div>

        <footer class="modal-footer relative z-10 flex items-center justify-between gap-3 px-4 py-3">
          <p class="text-xs text-text-dim">保存后会保留为自定义主题。</p>
          <div class="flex shrink-0 gap-2">
            <button class="text-sm font-bold text-text-dim hover:text-text-main" @click="$emit('close')">取消</button>
            <button class="rounded-xl bg-accent-primary px-4 py-1.5 text-sm font-black text-on-accent-primary transition-all hover:bg-accent-primary/85"
              @click="handleSave"
            >保存</button>
          </div>
        </footer>
      </div>
    </transition>
  </Teleport>

  <GlobalColorPicker v-model="activeColorValue"
    :is-open="!!activeColorField"
    :anchor-rect="activeColorAnchorRect"
    :format="activeColorField ? getColorFormat(activeColorField.group.key) : 'hex'"
    :disable-alpha="activeColorField ? isAlphaDisabled(activeColorField.group.key) : true"
    @close="activeColorKey = ''"
  />
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import GlobalColorPicker from '../common/GlobalColorPicker.vue'
import { THEME_TOKEN_GROUPS, applyTheme, createEditableThemeFrom, normalizeTheme } from '../../modules/theme/themeManager'
import { X } from 'lucide-vue-next'

const props = defineProps({
  isOpen: { type: Boolean, default: false },
  theme: { type: Object, default: null },
  showColorValue: { type: Boolean, default: false },
})

const emit = defineEmits(['close', 'save'])

const draft = ref(createEditableThemeFrom())
const activeColorKey = ref('')
const activeColorAnchorRect = ref(null)
const panelRef = ref(null)
const panelPosition = ref({ x: 24, y: 72 })
const dragState = ref(null)

const panelStyle = computed(() => ({
  left: `${panelPosition.value.x}px`,
  top: `${panelPosition.value.y}px`,
}))

const colorFieldKey = (groupKey, tokenKey) => `${groupKey}.${tokenKey}`

const activeColorField = computed(() => {
  if (!activeColorKey.value) return null
  const [groupKey, tokenKey] = activeColorKey.value.split('.')
  const group = THEME_TOKEN_GROUPS.find(item => item.key === groupKey)
  const token = group?.tokens.find(item => item.key === tokenKey)
  return group && token ? { group, token } : null
})

const activeColorValue = computed({
  get: () => {
    const field = activeColorField.value
    return field ? draft.value.tokens[field.group.key][field.token.key] : ''
  },
  set: (value) => {
    const field = activeColorField.value
    if (!field) return
    draft.value.tokens[field.group.key][field.token.key] = value
  },
})

const clampPanelPosition = (x, y) => {
  if (typeof window === 'undefined') return { x, y }
  const rect = panelRef.value?.getBoundingClientRect?.()
  const width = rect?.width || 460
  const height = rect?.height || 620
  return {
    x: Math.min(Math.max(12, x), Math.max(12, window.innerWidth - width - 12)),
    y: Math.min(Math.max(12, y), Math.max(12, window.innerHeight - height - 12)),
  }
}

const setPanelPosition = (x, y) => {
  panelPosition.value = clampPanelPosition(x, y)
}

// 归位默认屏幕中央
const resetPanelPosition = async () => {
  await nextTick()
  if (typeof window === 'undefined') return
  const rect = panelRef.value?.getBoundingClientRect?.()
  const width = rect?.width || window.innerWidth / 4
  const height = rect?.height || window.innerHeight / 2
  setPanelPosition(window.innerWidth/2 - width / 2, window.innerHeight / 2 - height / 2)
}

const handleDragMove = (event) => {
  if (!dragState.value) return
  event.preventDefault()
  setPanelPosition(event.clientX - dragState.value.offsetX, event.clientY - dragState.value.offsetY)
}

const stopDragging = () => {
  dragState.value = null
  window.removeEventListener('pointermove', handleDragMove)
  window.removeEventListener('pointerup', stopDragging)
}

const handleDragStart = (event) => {
  if (event.button !== 0) return
  const rect = panelRef.value?.getBoundingClientRect?.()
  if (!rect) return
  activeColorKey.value = ''
  dragState.value = {
    offsetX: event.clientX - rect.left,
    offsetY: event.clientY - rect.top,
  }
  window.addEventListener('pointermove', handleDragMove)
  window.addEventListener('pointerup', stopDragging, { once: true })
}

const openColorPicker = (groupKey, tokenKey, event) => {
  const key = colorFieldKey(groupKey, tokenKey)
  if (activeColorKey.value === key) {
    activeColorKey.value = ''
    return
  }
  activeColorKey.value = key
  const rect = event.currentTarget.getBoundingClientRect()
  activeColorAnchorRect.value = {
    left: rect.left,
    right: rect.right,
    top: rect.top,
    bottom: rect.bottom,
    width: rect.width,
    height: rect.height,
  }
}

watch(() => props.theme, (theme) => {
  draft.value = normalizeTheme(theme || createEditableThemeFrom())
  activeColorKey.value = ''
}, { immediate: true, deep: true })

watch(() => props.isOpen, async (isOpen) => {
  if (!isOpen) {
    stopDragging()
    activeColorKey.value = ''
    return
  }
  await resetPanelPosition()
})

watch(draft, (theme) => {
  if (!props.isOpen) return
  applyTheme(theme)
}, { deep: true })

const getColorFormat = (groupKey) => groupKey === 'glass' ? 'rgb' : 'hex'
const isAlphaDisabled = (groupKey) => groupKey !== 'glass'
const getSwatchStyle = (groupKey, tokenKey) => ({
  backgroundColor: draft.value?.tokens?.[groupKey]?.[tokenKey] || '#000000',
})
const groupGridTemplate = (groupKey) => {
  if (groupKey === 'accent') return 'repeat(auto-fit, minmax(185px, 1fr))'
  if (groupKey === 'glass') return 'repeat(auto-fit, minmax(200px, 1fr))'
  return 'repeat(auto-fit, minmax(205px, 1fr))'
}

const handleSave = () => {
  emit('save', normalizeTheme(draft.value))
}

onBeforeUnmount(stopDragging)
</script>

<style scoped>
.theme-alpha-grid {
  background-color: #fff;
  background-image:
    linear-gradient(45deg, #cbd5e1 25%, transparent 25%),
    linear-gradient(-45deg, #cbd5e1 25%, transparent 25%),
    linear-gradient(45deg, transparent 75%, #cbd5e1 75%),
    linear-gradient(-45deg, transparent 75%, #cbd5e1 75%);
  background-position: 0 0, 0 4px, 4px -4px, -4px 0;
  background-size: 8px 8px;
}
</style>
