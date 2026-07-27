<template>
  <div v-if="pickerActive && hoverBox.visible" class="fixed pointer-events-none rounded-lg border border-accent-primary bg-accent-primary/10 shadow-[0_0_0_9999px_rgba(0,0,0,0.18),0_0_18px_rgba(var(--rgb-accent-primary),0.45)]"
    :style="hoverBoxStyle"
  ></div>

  <div v-if="enabled" ref="overlayRef" class="fixed pointer-events-auto select-none" :style="overlayStyle">
    <button v-if="!showPanel" class="size-12 rounded-full border border-accent-primary/35 bg-bg-surface/95 text-accent-primary shadow-2xl shadow-bg-deep/60 backdrop-blur-md flex items-center justify-center transition-all hover:scale-105"
      :class="pickerActive ? 'bg-accent-primary text-on-accent-primary' : ''"
      v-tooltip="pickerActive ? t('ui.i18n.translation_mode.cancel_pick', '取消拾取') : t('ui.i18n.translation_mode.pick_text', '拾取文本')"
      @mousedown="startDrag"
      @click="togglePicker"
      @contextmenu.prevent.stop="expandPanel"
    >
      <Languages class="size-5" />
    </button>

    <div v-else class="w-84 max-w-[calc(100vw-1rem)] rounded-xl border border-accent-primary/30 bg-bg-surface/95 shadow-2xl shadow-bg-deep/60 backdrop-blur-md overflow-hidden">
      <div class="flex items-center gap-2 px-3 py-2 bg-bg-overlay/8 cursor-move" @mousedown="startDrag">
        <Languages class="size-4 text-accent-primary shrink-0" />
        <div class="min-w-0 flex-1">
          <p class="text-xs font-black text-text-main truncate">{{ t('ui.i18n.translation_mode.title', '翻译模式') }}</p>
          <p class="text-[0.7rem] text-text-dim truncate">{{ pickerActive ? t('ui.i18n.translation_mode.picking', '点击界面文本进行翻译') : shortcutHint }}</p>
        </div>
        <button class="p-1 rounded-md text-text-dim hover:text-text-main hover:bg-bg-overlay/10" v-tooltip="t('tooltip.i18n.translation_mode.minimize', '缩小为悬浮球')" @mousedown.stop @click="minimizePanel">
          <Minimize2 class="size-4" />
        </button>
        <button class="p-1 rounded-md text-text-dim hover:text-text-main hover:bg-bg-overlay/10" v-tooltip="t('tooltip.i18n.translation_mode.close', '关闭翻译模式')" @click="setEnabled(false)">
          <X class="size-4" />
        </button>
      </div>

      <div class="p-3 space-y-3">
        <button class="w-full inline-flex items-center justify-center gap-2 rounded-lg px-3 py-2 text-xs font-bold transition-colors"
          :class="pickerActive ? 'bg-accent-primary text-on-accent-primary' : 'bg-bg-overlay/8 text-text-main hover:bg-bg-overlay/14'"
          @click="togglePicker"
        >
          <MousePointer2 class="size-4" />
          {{ pickerActive ? t('ui.i18n.translation_mode.cancel_pick', '取消拾取') : t('ui.i18n.translation_mode.pick_text', '重新拾取') }}
        </button>

        <div class="space-y-2">
          <CommonSelect
            v-if="selectedEntries.length > 1"
            v-model="selectedKey"
            class="w-full"
            :label="t('ui.i18n.translation_mode.candidate_key', '候选文本 key')"
            :options="candidateKeyOptions"
            :popover-z-index="translationPopoverZIndex"
            show-bottom
          />

          <div class="rounded-lg bg-bg-deep/70 border border-border-base/10 p-2 space-y-1">
            <p class="text-[0.7rem] text-text-disabled font-mono break-all">{{ selectedEntry?.key }}</p>
            <p class="text-xs text-text-dim">{{ t('ui.translation.controls.source_text', '中文原文') }}</p>
            <p class="text-sm text-text-main whitespace-pre-wrap wrap-break-words">{{ selectedEntry?.defaultText }}</p>
          </div>

          <label class="block text-xs font-bold text-text-dim">
            {{ t('ui.i18n.translation_mode.translation', '当前译文') }}
            <textarea v-model="draftText" rows="4"
              class="mt-1 w-full resize-y rounded-lg border border-border-base/12 bg-bg-deep px-3 py-2 text-sm text-text-main outline-none focus:border-accent-primary/60"
            ></textarea>
          </label>

          <CommonSelect
            v-model="selectedProvider"
            class="w-full"
            :label="t('ui.translation.controls.provider', '翻译器')"
            :options="providerOptions"
            :popover-z-index="translationPopoverZIndex"
            show-bottom
          />

          <div class="flex items-center gap-2">
            <button class="inline-flex items-center justify-center gap-2 rounded-lg bg-bg-overlay/8 px-3 py-2 text-xs font-bold text-text-main hover:bg-bg-overlay/14 disabled:opacity-50"
              :disabled="busy"
              @click="autoTranslate"
            >
              <WandSparkles class="size-4" />
              {{ t('ui.i18n.translation_mode.auto_translate', '自动翻译') }}
            </button>
            <button class="flex-1 inline-flex items-center justify-center gap-2 rounded-lg bg-accent-primary px-3 py-2 text-xs font-black text-on-accent-primary hover:bg-accent-primary/85 disabled:opacity-50"
              :disabled="busy || !selectedEntry"
              @click="saveTranslation"
            >
              <Save class="size-4" />
              {{ busy ? t('ui.i18n.translation_mode.saving', '保存中...') : t('common.action.save', '保存') }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onUnmounted, reactive, ref, watch } from 'vue'
import { Languages, Minimize2, MousePointer2, Save, WandSparkles, X } from 'lucide-vue-next'
import { useAppStore } from '../../../app/stores/appStore'
import CommonSelect from '../input/CommonSelect.vue'
import { DEFAULT_LOCALE, findTranslationEntriesForText, findTranslationEntryByKey, getCurrentLocale, getTranslationValidationIssue, setLocale, t, translateMessagePayload } from '../../i18n.js'
import { showUserErrorToast, toast } from '../../lib/common'

const appStore = useAppStore()
const overlayRef = ref(null)
const pickerActive = ref(false)
const selectedEntries = ref([])
const selectedKey = ref('')
const draftText = ref('')
const selectedProvider = ref('')
const panelMinimized = ref(false)
const busy = ref(false)
const position = reactive({ x: 24, y: 96 })
const dragState = reactive({ active: false, moved: false, startX: 0, startY: 0, originX: 0, originY: 0 })
const hoverBox = reactive({ visible: false, left: 0, top: 0, width: 0, height: 0 })
const translationOverlayZIndex = 2147483600
const translationPopoverZIndex = 2147483647

const enabled = computed(() => !!appStore.translationModeEnabled)
const hasSelection = computed(() => selectedEntries.value.length > 0)
const showPanel = computed(() => hasSelection.value && !pickerActive.value && !panelMinimized.value)
const selectedEntry = computed(() => selectedEntries.value.find(entry => entry.key === selectedKey.value) || selectedEntries.value[0] || null)
const shortcutHint = computed(() => t('ui.i18n.translation_mode.shortcut_hint', 'Ctrl + Shift + L 开关'))
const candidateKeyOptions = computed(() => selectedEntries.value.map(entry => ({ label: entry.key, value: entry.key })))
const providerOptions = computed(() => {
  const providers = Array.isArray(appStore.translationProviders) ? appStore.translationProviders : []
  return providers.map(item => ({
    label: item.label_key ? t(item.label_key, item.default_label || item.label || item.id) : (item.label || item.name || item.id),
    value: item.id || item.value,
    type: item.type || '',
  })).filter(item => item.label && item.value)
})
const panelWidth = 336
const ballSize = 30
const overlayStyle = computed(() => ({
  left: `${position.x}px`,
  top: `${position.y}px`,
  zIndex: translationOverlayZIndex,
}))
const hoverBoxStyle = computed(() => ({
  left: `${hoverBox.left}px`,
  top: `${hoverBox.top}px`,
  width: `${hoverBox.width}px`,
  height: `${hoverBox.height}px`,
  zIndex: translationOverlayZIndex - 1,
}))

const clampPosition = () => {
  const width = overlayRef.value?.offsetWidth || (showPanel.value ? panelWidth : ballSize)
  const height = overlayRef.value?.offsetHeight || (showPanel.value ? 320 : ballSize)
  position.x = Math.min(Math.max(8, position.x), Math.max(8, window.innerWidth - width - 8))
  position.y = Math.min(Math.max(8, position.y), Math.max(8, window.innerHeight - height - 8))
}

const setEnabled = (value) => {
  appStore.translationModeEnabled = !!value
  pickerActive.value = false
  panelMinimized.value = false
  selectedEntries.value = []
  selectedKey.value = ''
}

const ensureProviderSelection = async () => {
  await appStore.ensureTranslationProviders()
  if (!selectedProvider.value || !providerOptions.value.some(item => item.value === selectedProvider.value)) {
    selectedProvider.value = appStore.getTranslationFeatureSettings('default').provider || providerOptions.value[0]?.value || 'ai.default'
  }
}

const togglePicker = () => {
  if (dragState.moved) {
    dragState.moved = false
    return
  }
  pickerActive.value = !pickerActive.value
}

const minimizePanel = () => {
  panelMinimized.value = true
  nextTick(() => clampPosition())
}

const expandPanel = () => {
  if (!hasSelection.value) return
  pickerActive.value = false
  panelMinimized.value = false
  nextTick(() => clampPosition())
}

const getTooltipText = (node) => {
  const value = node?._tipValue
  if (!value) return ''
  if (typeof value === 'string' || typeof value === 'number') return String(value)
  if (typeof value === 'object') return String(value.content || value.label || value.title || '')
  return ''
}

const readElementTranslationTarget = (target) => {
  let node = target
  for (let depth = 0; node && node !== document.body && depth < 5; depth += 1) {
    const key = node.getAttribute?.('data-i18n-key') || node.closest?.('[data-i18n-key]')?.getAttribute?.('data-i18n-key')
    const text = [
      getTooltipText(node),
      node.getAttribute?.('aria-label'),
      node.getAttribute?.('title'),
      node.getAttribute?.('placeholder'),
      node.innerText,
      node.value,
    ].map(value => String(value || '').trim()).find(Boolean)
    if (key || text) return { key: String(key || '').trim(), text: text || '' }
    node = node.parentElement
  }
  return { key: '', text: '' }
}

const updateHoverBox = (target) => {
  if (!pickerActive.value || overlayRef.value?.contains(target)) {
    hoverBox.visible = false
    return
  }
  const element = target?.nodeType === Node.ELEMENT_NODE ? target : target?.parentElement
  if (!element || element === document.body || element === document.documentElement) {
    hoverBox.visible = false
    return
  }
  const rect = element.getBoundingClientRect()
  if (rect.width <= 0 || rect.height <= 0) {
    hoverBox.visible = false
    return
  }
  hoverBox.visible = true
  hoverBox.left = Math.max(0, rect.left - 3)
  hoverBox.top = Math.max(0, rect.top - 3)
  hoverBox.width = Math.min(window.innerWidth - hoverBox.left, rect.width + 6)
  hoverBox.height = Math.min(window.innerHeight - hoverBox.top, rect.height + 6)
}

const handlePickerMove = (event) => {
  updateHoverBox(event.target)
}

const cancelPicker = () => {
  pickerActive.value = false
  hoverBox.visible = false
  nextTick(() => clampPosition())
}

const handlePickerKeydown = (event) => {
  if (event.key !== 'Escape') return
  event.preventDefault()
  event.stopPropagation()
  cancelPicker()
}

const pickElement = (event) => {
  if (!pickerActive.value || overlayRef.value?.contains(event.target)) return
  event.preventDefault()
  event.stopPropagation()
  const target = readElementTranslationTarget(event.target)
  const keyEntry = target.key ? findTranslationEntryByKey(target.key) : null
  const entries = keyEntry ? [keyEntry] : findTranslationEntriesForText(target.text)
  if (!entries.length) {
    toast.warning(t('messages.i18n.translation_mode.no_match', '未找到可翻译文本。请确认该文本已经接入多语言结构。'))
    return
  }
  selectedEntries.value = entries
  selectedKey.value = entries[0].key
  panelMinimized.value = false
  cancelPicker()
  nextTick(() => clampPosition())
}

const saveTranslation = async () => {
  if (!selectedEntry.value) return
  if (!window.pywebview?.api?.locale_save_user_message) {
    toast.warning(t('messages.i18n.translation_mode.save_unavailable', '当前运行环境不支持保存用户语言文件。'))
    return
  }
  busy.value = true
  try {
    const locale = getCurrentLocale()
    const res = await window.pywebview.api.locale_save_user_message(locale, selectedEntry.value.key, draftText.value)
    if (res?.status !== 'success') {
      showUserErrorToast(res, t('messages.i18n.translation_mode.save_failed', '保存翻译失败。'))
      return
    }
    await setLocale(locale)
    toast.success(t('messages.i18n.translation_mode.saved', '翻译已保存并重新加载。'))
  } finally {
    busy.value = false
  }
}

const autoTranslate = async () => {
  if (!selectedEntry.value) return
  const locale = getCurrentLocale()
  if (locale === DEFAULT_LOCALE) {
    toast.warning(t('messages.i18n.translation_mode.default_locale_skip', '当前已经是默认中文，不需要自动翻译。'))
    return
  }
  if (!window.pywebview?.api?.translation_translate_document) {
    toast.warning(t('messages.i18n.translation_mode.auto_translate_unavailable', '当前运行环境不支持自动翻译。'))
    return
  }
  await ensureProviderSelection()
  const provider = selectedProvider.value || 'ai.default'
  const providerInfo = providerOptions.value.find(item => item.value === provider)
  if (providerInfo?.type === 'ai' && !appStore.settings.ai?.enabled) {
    toast.warning(t('messages.i18n.translation_mode.ai_not_configured', '请先在设置中启用并配置 AI 翻译。'))
    return
  }
  busy.value = true
  try {
    const res = await window.pywebview.api.translation_translate_document({
      format: 'plain_text',
      context: 'RimCrow interface text',
      segments: [{ key: 'value', text: selectedEntry.value.defaultText, role: 'ui' }],
    }, locale, provider)
    if (res?.status !== 'success') {
      showUserErrorToast(res, t('messages.i18n.translation_mode.auto_translate_failed', '自动翻译失败。'))
      return
    }
    const segment = Array.isArray(res.data?.segments) ? res.data.segments.find(item => item.key === 'value') : null
    const text = String(segment?.text || '').trim()
    const issue = text ? getTranslationValidationIssue(selectedEntry.value.defaultText, text) : ''
    if (issue === 'placeholders') {
      toast.error(t('dialog.translation_manager.workfile_param_mismatch', '参数不一致：{key}', { key: selectedEntry.value.key }))
      return
    }
    if (issue === 'markers') {
      toast.error(t('dialog.translation_manager.workfile_marker_mismatch', '格式标记不一致：{key}', { key: selectedEntry.value.key }))
      return
    }
    draftText.value = text || draftText.value
  } finally {
    busy.value = false
  }
}

const startDrag = (event) => {
  if (event.button !== 0) return
  dragState.active = true
  dragState.moved = false
  dragState.startX = event.clientX
  dragState.startY = event.clientY
  dragState.originX = position.x
  dragState.originY = position.y
  window.addEventListener('mousemove', onDragMove)
  window.addEventListener('mouseup', stopDrag)
}

const onDragMove = (event) => {
  if (!dragState.active) return
  if (Math.abs(event.clientX - dragState.startX) > 3 || Math.abs(event.clientY - dragState.startY) > 3) {
    dragState.moved = true
  }
  position.x = dragState.originX + event.clientX - dragState.startX
  position.y = dragState.originY + event.clientY - dragState.startY
  clampPosition()
}

const stopDrag = () => {
  dragState.active = false
  window.removeEventListener('mousemove', onDragMove)
  window.removeEventListener('mouseup', stopDrag)
}

watch(selectedEntry, (entry) => {
  draftText.value = entry?.currentText || entry?.defaultText || ''
})

watch(pickerActive, async (active) => {
  document.body.style.cursor = active ? 'crosshair' : ''
  if (active) {
    await nextTick()
    document.addEventListener('click', pickElement, true)
    document.addEventListener('mousemove', handlePickerMove, true)
    document.addEventListener('keydown', handlePickerKeydown, true)
  } else {
    document.removeEventListener('click', pickElement, true)
    document.removeEventListener('mousemove', handlePickerMove, true)
    document.removeEventListener('keydown', handlePickerKeydown, true)
    hoverBox.visible = false
    nextTick(() => clampPosition())
  }
})

watch(enabled, async (value) => {
  if (!value) pickerActive.value = false
  if (value) void ensureProviderSelection()
  await nextTick()
  clampPosition()
}, { immediate: true })

watch(showPanel, (visible) => {
  if (visible) void ensureProviderSelection()
})

window.addEventListener('resize', clampPosition)

onUnmounted(() => {
  stopDrag()
  document.removeEventListener('click', pickElement, true)
  document.removeEventListener('mousemove', handlePickerMove, true)
  document.removeEventListener('keydown', handlePickerKeydown, true)
  document.body.style.cursor = ''
  window.removeEventListener('resize', clampPosition)
})
</script>
