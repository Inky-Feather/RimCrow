<template>
  <div class="translation-feature-controls">
    <template v-if="mode === 'panel'">
      <div class="grid grid-cols-2 gap-2">
        <div v-if="title || description" class="col-span-2 px-1">
          <div v-if="title" class="text-xs font-black text-text-main">{{ title }}</div>
          <div v-if="description" class="mt-0.5 text-[0.68rem] text-text-dim">{{ description }}</div>
        </div>
        <CommonSelect class="col-span-1" label="目标语言" :model-value="targetLanguageValue" :options="targetLanguageOptions" showBottom mini @update:model-value="value => updateSetting({ target_language: value })" />
        <CommonSelect class="col-span-1" label="翻译器" :model-value="providerValue" :options="providerSelectOptions" showBottom mini @update:model-value="value => updateSetting({ provider: value })" />
        <CommonSwitch v-if="showFeatureSwitches" class="col-span-1" label="优先显示译文" :model-value="!!rawSettings.prefer_ui_language_translation" mini
          description="打开详情时，如果已有目标语言译文，会优先显示译文。" @update:model-value="value => updateSetting({ prefer_ui_language_translation: value })" />
        <CommonSwitch v-if="showFeatureSwitches" class="col-span-1" label="缺少译文自动翻译" :model-value="!!rawSettings.auto_translate_missing" mini
          description="当前没有目标语言译文时自动请求翻译。默认关闭，避免意外消耗请求。" @update:model-value="value => updateSetting({ auto_translate_missing: value })" />
        <CommonSwitch v-if="showFeatureSwitches" class="col-span-1" label="识别原文时跳过" :model-value="sourceDetection.enabled" mini
          description="自动翻译前检测原文，命中规则时不请求翻译。" @update:model-value="value => updateSourceDetection({ enabled: value })" />
        <CommonSelect v-if="showFeatureSwitches" class="col-span-1" label="识别逻辑" :model-value="sourceDetection.mode" :options="sourceDetectionModeOptions" showBottom mini @update:model-value="value => updateSourceDetection({ mode: value })" />
        <CommonTagInput v-if="showFeatureSwitches" class="col-span-2" label="原文识别词" :model-value="sourceDetection.terms" placeholder="输入并回车，例如：的、模组、。"
          description="这些字符或短语会按字面量匹配，命中后认为原文不需要自动翻译。" @update:model-value="value => updateSourceDetection({ terms: value })" />
      </div>
    </template>

    <template v-else>
      <div class="relative flex items-center gap-1.5">
        <button ref="settingsButtonRef" type="button" @click="panelOpen = !panelOpen" v-tooltip="resolvedSettingsTooltip"
          class="inline-flex h-7 items-center gap-1.5 rounded-lg border border-border-base/10 bg-bg-surface/80 px-2.5 text-[0.68rem] font-bold text-text-dim transition-all hover:border-accent-primary/30 hover:text-accent-primary">
          <SlidersHorizontal class="size-3.5" />
          <span class="max-w-28 truncate">{{ buttonLabel || title || '翻译设置' }}</span>
          <span v-if="isStale" class="size-1.5 rounded-full bg-accent-warn"></span>
        </button>
        <button v-if="showQuick" type="button" :disabled="isTranslating" @click="$emit('toggle')" v-tooltip="quickTooltip"
          v-long-press-feedback="{ duration: 650, disabled: isTranslating || !canRetranslate, onComplete: () => $emit('retranslate') }"
          class="inline-flex h-7 items-center gap-1.5 rounded-lg border border-accent-primary/25 bg-accent-primary/12 px-2.5 text-[0.68rem] font-extrabold text-accent-primary transition-all hover:bg-accent-primary hover:text-on-accent-primary disabled:cursor-not-allowed disabled:opacity-60">
          <LoaderCircle v-if="isTranslating" class="size-3.5 animate-spin" />
          <Languages v-else class="size-3.5" />
          <span>{{ quickLabel || (isTranslated ? '原文' : '翻译') }}</span>
        </button>
        <FixedPopover :is-open="panelOpen" :trigger-ref="settingsButtonRef" :min-width="300" :max-width="340" :max-height="420" :offset="6" @request-close="panelOpen = false">
          <div class="popover-surface w-80 rounded-xl border border-border-base/18 bg-bg-surface/98 p-3 text-xs">
            <div class="grid grid-cols-2 gap-3">
              <CommonSelect v-if="showDisplayLanguage" class="col-span-2" label="显示语言" :model-value="displayLanguage" :options="displayLanguageOptions" mini @update:model-value="value => $emit('update:displayLanguage', value)" />
              <CommonSelect class="col-span-1" label="目标语言" :model-value="targetLanguageValue" :options="targetLanguageOptions" mini @update:model-value="value => updateSetting({ target_language: value })" />
              <CommonSelect class="col-span-1" label="翻译器" :model-value="providerValue" :options="providerSelectOptions" mini @update:model-value="value => updateSetting({ provider: value })" />
              <CommonSwitch v-if="showFeatureSwitches" class="col-span-2" label="优先显示译文" :model-value="!!rawSettings.prefer_ui_language_translation" mini
                description="打开详情时，如果已有目标语言译文，会优先显示译文。" @update:model-value="value => updateSetting({ prefer_ui_language_translation: value })" />
              <CommonSwitch v-if="showFeatureSwitches" class="col-span-2" label="缺少译文自动翻译" :model-value="!!rawSettings.auto_translate_missing" mini
                description="当前没有目标语言译文时自动请求翻译。默认关闭，避免意外消耗请求。" @update:model-value="value => updateSetting({ auto_translate_missing: value })" />
              <CommonSwitch v-if="showFeatureSwitches" class="col-span-2" label="识别原文时跳过" :model-value="sourceDetection.enabled" mini
                description="自动翻译前检测原文，命中规则时不请求翻译。" @update:model-value="value => updateSourceDetection({ enabled: value })" />
              <CommonSelect v-if="showFeatureSwitches" class="col-span-2" label="识别逻辑" :model-value="sourceDetection.mode" :options="sourceDetectionModeOptions" mini @update:model-value="value => updateSourceDetection({ mode: value })" />
              <CommonTagInput v-if="showFeatureSwitches" class="col-span-2" label="原文识别词" :model-value="sourceDetection.terms" placeholder="输入并回车，例如：的、模组、。"
                description="这些字符或短语会按字面量匹配，命中后认为原文不需要自动翻译。" @update:model-value="value => updateSourceDetection({ terms: value })" />
              <div v-if="showActions" class="col-span-2 flex items-center justify-end gap-2 border-t border-border-base/10 pt-3">
                <button type="button" :disabled="isTranslating || !canRetranslate" @click="$emit('retranslate')"
                  class="inline-flex h-7 items-center gap-1.5 rounded-lg border border-accent-warn/30 bg-accent-warn/12 px-2.5 text-[0.68rem] font-extrabold text-accent-warn transition-colors hover:bg-accent-warn hover:text-on-accent-warn disabled:cursor-not-allowed disabled:opacity-50">
                  <LoaderCircle v-if="isTranslating" class="size-3.5 animate-spin" />
                  <RotateCcw v-else class="size-3.5" />
                  <span>重新翻译</span>
                </button>
                <button type="button" :disabled="isTranslating || !canClear" @click="$emit('clear')"
                  class="inline-flex h-7 items-center gap-1.5 rounded-lg border border-accent-danger/30 bg-accent-danger/12 px-2.5 text-[0.68rem] font-extrabold text-accent-danger transition-colors hover:bg-accent-danger hover:text-on-accent-danger disabled:cursor-not-allowed disabled:opacity-50">
                  <Trash2 class="size-3.5" />
                  <span>清理翻译</span>
                </button>
              </div>
            </div>
          </div>
        </FixedPopover>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { Languages, LoaderCircle, RotateCcw, SlidersHorizontal, Trash2 } from 'lucide-vue-next'
import { useAppStore } from '../../../app/stores/appStore'
import CommonSelect from '../input/CommonSelect.vue'
import CommonSwitch from '../input/CommonSwitch.vue'
import CommonTagInput from '../input/CommonTagInput.vue'
import FixedPopover from '../popover/FixedPopover.vue'
import { normalizeTranslationSourceDetection } from '../../lib/translationDetection'

const defaultLanguageOptions = [
  { label: '跟随界面语言', value: 'follow_ui' },
  { label: '简体中文', value: 'zh-CN' },
  { label: 'English', value: 'en' },
  { label: '日本語', value: 'ja' },
  { label: '한국어', value: 'ko' },
  { label: 'Deutsch', value: 'de' },
  { label: 'Français', value: 'fr' },
  { label: 'Español', value: 'es' },
  { label: 'Português do Brasil', value: 'pt-BR' },
  { label: 'Русский', value: 'ru' },
]

const props = defineProps({
  feature: { type: String, default: 'workshop_detail' },
  mode: { type: String, default: 'popover' },
  settings: { type: Object, default: null },
  title: { type: String, default: '' },
  description: { type: String, default: '' },
  buttonLabel: { type: String, default: '' },
  settingsTooltip: { type: String, default: '' },
  languageOptions: { type: Array, default: () => [] },
  providerOptions: { type: Array, default: () => [] },
  displayLanguage: { type: String, default: '' },
  displayLanguageOptions: { type: Array, default: () => [] },
  showDisplayLanguage: { type: Boolean, default: false },
  showFeatureSwitches: { type: Boolean, default: true },
  showActions: { type: Boolean, default: true },
  showQuick: { type: Boolean, default: false },
  quickLabel: { type: String, default: '' },
  quickTooltip: { type: String, default: '' },
  isTranslated: { type: Boolean, default: false },
  isTranslating: { type: Boolean, default: false },
  isStale: { type: Boolean, default: false },
  canRetranslate: { type: Boolean, default: true },
  canClear: { type: Boolean, default: false },
})

const emit = defineEmits(['update:displayLanguage', 'settings-change', 'toggle', 'retranslate', 'clear'])
const appStore = useAppStore()
const panelOpen = ref(false)
const settingsButtonRef = ref(null)

const rawSettings = computed(() => {
  if (props.settings && typeof props.settings === 'object') return props.settings
  return appStore.settings.translation?.[props.feature] || {}
})
const languageSelectOptions = computed(() => props.languageOptions.length ? props.languageOptions : defaultLanguageOptions)
const targetLanguageOptions = computed(() => (
  props.feature === 'default'
    ? languageSelectOptions.value
    : [{ label: '使用默认目标语言', value: 'default' }, ...languageSelectOptions.value]
))
const providerBaseOptions = computed(() => {
  const options = props.providerOptions.length
    ? props.providerOptions
    : appStore.translationProviders.map(item => ({ label: item.label || item.id, value: item.id }))
  return options.length ? options : [{ label: 'AI 翻译', value: 'ai.default' }]
})
const providerSelectOptions = computed(() => (
  props.feature === 'default'
    ? providerBaseOptions.value
    : [{ label: '使用默认翻译器', value: 'default' }, ...providerBaseOptions.value]
))
const sourceDetectionModeOptions = [
  { label: '任一命中（OR）', value: 'or' },
  { label: '全部命中（AND）', value: 'and' },
]
const targetLanguageValue = computed(() => String(rawSettings.value.target_language || (props.feature === 'default' ? 'follow_ui' : 'default')))
const providerValue = computed(() => String(rawSettings.value.provider || (props.feature === 'default' ? 'ai.default' : 'default')))
const sourceDetection = computed(() => normalizeTranslationSourceDetection(rawSettings.value.source_detection))
const resolvedSettingsTooltip = computed(() => props.settingsTooltip || '点击可设置翻译语言、翻译器和自动翻译策略。')

const updateSetting = (patch) => {
  if (!patch || typeof patch !== 'object') return
  if (props.settings && typeof props.settings === 'object') {
    Object.assign(props.settings, patch)
    emit('settings-change', patch)
    return
  }
  void appStore.saveTranslationFeatureSettings(props.feature, patch)
  emit('settings-change', patch)
}

const updateSourceDetection = (patch) => {
  updateSetting({ source_detection: { ...sourceDetection.value, ...(patch || {}) } })
}

onMounted(() => {
  void appStore.ensureTranslationProviders()
})
</script>
