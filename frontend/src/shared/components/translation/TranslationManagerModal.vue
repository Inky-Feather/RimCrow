<template>
  <CommonModalShell
    :show="appStore.uiState.showTranslationManager"
    :title="t('dialog.translation_manager.title', '翻译管理')"
    :description="t('dialog.translation_manager.description', '浏览和修改当前语言的界面翻译；保存后只写入用户语言覆盖文件。')"
    size="page"
    :z-index="180"
    accent="primary"
    content-class="flex min-h-0 flex-col"
    @close="close"
  >
    <div class="grid grid-cols-12 gap-3 border-b border-border-base/8 p-4">
      <CommonSelect class="col-span-2" v-model="selectedLanguage" :label="t('ui.translation.controls.target_language', '目标语言')" :options="languageOptions" show-bottom />
      <CommonSelect class="col-span-2" v-model="selectedNamespace" :label="t('dialog.translation_manager.namespace', '分类')" :options="namespaceOptions" show-bottom />
      <CommonSelect class="col-span-2" v-model="statusFilter" :label="t('dialog.translation_manager.status', '状态')" :options="statusOptions" show-bottom />
      <CommonInput class="col-span-4" v-model="searchText" :label="t('common.action.search', '搜索')" :placeholder="t('dialog.translation_manager.search_placeholder', '搜索 key / 原文 / 译文')" />
      <CommonSelect class="col-span-2" v-model="selectedProvider" :label="t('ui.translation.controls.provider', '翻译器')" :options="providerOptions" show-bottom />
    </div>

    <div class="grid min-h-0 flex-1 grid-cols-[minmax(18rem,28rem)_1fr]">
      <aside class="flex min-h-0 flex-col border-r border-border-base/8">
        <div class="flex items-center justify-between pl-4 pr-4 pt-2 pb-2 text-xs text-text-dim">
          <span>{{ t('dialog.translation_manager.result_count', '{count} 条', { count: filteredRows.length }) }}</span>
          <div class="flex items-center gap-1">
            <button type="button" v-tooltip="t('dialog.language_pack.create_title', '创建语言包')" :aria-label="t('dialog.language_pack.create_title', '创建语言包')" :class="toolbarIconButtonClass" :disabled="busy" @click="openLanguageCreate">
              <Plus class="size-4" />
            </button>
            <button type="button" v-tooltip="t('dialog.translation_manager.auto_translate_batch', '翻译未译({count})', { count: batchTranslateRows.length })" :aria-label="t('dialog.translation_manager.auto_translate_batch', '翻译未译({count})', { count: batchTranslateRows.length })" :class="toolbarIconButtonClass" :disabled="busy || !batchTranslateRows.length" @click="autoTranslateBatch">
              <WandSparkles class="size-4" />
            </button>
            <button type="button" v-tooltip="t('tooltip.translation_manager.export_workfile', '导出当前目标语言的完整待翻译文件，包含中文原文和当前译文，适合交给外部翻译工具处理后再导入。')" :aria-label="t('dialog.translation_manager.export_workfile', '导出待翻译文件')" :class="toolbarIconButtonClass" :disabled="busy || !rows.length" @click="exportWorkfile">
              <Upload class="size-4" />
            </button>
            <button type="button" v-tooltip="t('tooltip.translation_manager.import_workfile', '导入外部翻译后的文件，并把有效译文写入当前目标语言的用户语言包。')" :aria-label="t('dialog.translation_manager.import_workfile', '导入翻译文件')" :class="toolbarIconButtonClass" :disabled="busy" @click="importWorkfile">
              <Download class="size-4" />
            </button>
            <button type="button" v-tooltip="t('common.action.refresh', '刷新')" :aria-label="t('common.action.refresh', '刷新')" :class="toolbarIconButtonClass" :disabled="busy" @click="loadMessages">
              <RefreshCw class="size-4" />
            </button>
          </div>
        </div>
        <div ref="listScrollRef" class="min-h-0 flex-1 overflow-y-auto pb-10 custom-scrollbar">
          <div :style="{ height: toRem(totalSize), position: 'relative' }">
            <button v-for="virtualRow in virtualRows" :key="filteredRows[virtualRow.index]?.key || virtualRow.index" type="button"
              class="absolute left-2 right-2 rounded-lg border pl-3 pr-3 pt-2 pb-2 text-left transition-colors"
              :style="{ transform: `translateY(${toRem(virtualRow.start)})`, height: toRem(Math.max(0, virtualRow.size - rowGap)) }"
              :class="selectedKey === filteredRows[virtualRow.index]?.key ? 'border-accent-primary/60 bg-accent-primary/12' : 'border-border-base/8 bg-bg-overlay/4 hover:bg-bg-overlay/8'"
              @click="selectedKey = filteredRows[virtualRow.index]?.key || ''"
            >
              <div class="flex min-w-0 items-center gap-2">
                <span class="shrink-0 rounded pl-1.5 pr-1.5 pt-0.5 pb-0.5 text-[0.62rem] font-black" :class="statusClass(filteredRows[virtualRow.index]?.status)">{{ statusLabel(filteredRows[virtualRow.index]?.status) }}</span>
                <span class="min-w-0 flex-1 truncate font-mono text-[0.68rem] text-text-dim">{{ filteredRows[virtualRow.index]?.key }}</span>
              </div>
              <div class="mt-1 truncate text-xs text-text-main">{{ filteredRows[virtualRow.index]?.currentText || filteredRows[virtualRow.index]?.sourceText }}</div>
            </button>
          </div>
        </div>
      </aside>

      <section class="min-h-0 overflow-y-auto p-5 custom-scrollbar">
        <div v-if="selectedRow" class="space-y-4">
          <div class="rounded-xl border border-border-base/10 bg-bg-overlay/4 p-3">
            <div class="mb-2 text-xs font-bold uppercase tracking-widest text-text-dim">{{ t('dialog.translation_manager.key', '文本 key') }}</div>
            <div class="break-all font-mono text-sm text-text-main">{{ selectedRow.key }}</div>
          </div>

          <div class="grid grid-cols-2 gap-4">
            <div class="rounded-xl border border-border-base/10 bg-bg-deep/60 p-3">
              <div class="mb-2 text-xs font-bold uppercase tracking-widest text-text-dim">{{ t('ui.translation.controls.source_text', '中文原文') }}</div>
              <p class="whitespace-pre-wrap wrap-break-words text-sm leading-6 text-text-main">{{ selectedRow.sourceText }}</p>
            </div>
            <div class="rounded-xl border border-border-base/10 bg-bg-deep/60 p-3">
              <div class="mb-2 text-xs font-bold uppercase tracking-widest text-text-dim">{{ t('dialog.translation_manager.current_builtin', '内置译文') }}</div>
              <p class="whitespace-pre-wrap wrap-break-words text-sm leading-6 text-text-main">{{ selectedRow.builtinText || '-' }}</p>
            </div>
          </div>

          <label class="block">
            <span class="mb-2 block text-xs font-bold uppercase tracking-widest text-text-dim">{{ t('dialog.translation_manager.edit_translation', '编辑译文') }}</span>
            <textarea v-model="draftText" rows="8" class="input-glass w-full resize-y rounded-xl pl-3 pr-3 pt-2 pb-2 text-sm leading-6 text-text-main outline-none"></textarea>
          </label>

          <div class="flex items-center justify-between gap-3">
            <div class="text-xs text-text-dim">
              {{ draftText.trim() ? (selectedRow.userText !== undefined ? t('dialog.translation_manager.user_override_hint', '当前 key 已有用户覆盖。') : t('dialog.translation_manager.no_user_override_hint', '保存后会写入用户语言覆盖文件。')) : t('dialog.translation_manager.blank_resets_hint', '留空保存会重置为内置译文。') }}
            </div>
            <div class="flex items-center gap-2">
              <button class="rounded-lg bg-bg-overlay/8 pl-3 pr-3 pt-2 pb-2 text-xs font-bold text-text-main hover:bg-bg-overlay/14 disabled:opacity-50" :disabled="busy" @click="autoTranslateSelected">
                {{ t('dialog.translation_manager.auto_translate_one', '自动翻译此项') }}
              </button>
              <button class="rounded-lg bg-accent-primary pl-4 pr-4 pt-2 pb-2 text-xs font-black text-on-accent-primary hover:bg-accent-primary/85 disabled:opacity-50" :disabled="busy || !selectedRow" @click="saveSelected">
                {{ busy ? t('ui.i18n.translation_mode.saving', '保存中...') : t('common.action.save', '保存') }}
              </button>
            </div>
          </div>
        </div>
        <div v-else class="flex h-full items-center justify-center text-sm text-text-dim">
          {{ t('dialog.translation_manager.empty', '没有可编辑的翻译项') }}
        </div>
      </section>
    </div>
  </CommonModalShell>
  <CommonModalShell :show="showLanguageCreate" :title="t('dialog.language_pack.create_title', '创建语言包')" size="custom" panel-class="!h-fit w-[min(28rem,94vw)]" content-class="!flex-none !basis-auto !grow-0 pl-5 pr-5 pb-5" :z-index="220" accent="primary" @close="showLanguageCreate = false">
    <div class="space-y-3">
      <CommonSelect v-model="languagePreset" :label="t('dialog.language_pack.select_language', '选择语言')" :options="createLanguageOptions" show-bottom />
      <CommonInput v-model="languageCode" :label="t('dialog.language_pack.language_code', '语言代码')" placeholder="ja" :readonly="!isCustomLanguage" />
      <CommonInput v-model="languageLabel" :label="t('dialog.language_pack.display_name', '显示名称')" placeholder="日本語" :readonly="!isCustomLanguage" />
      <p class="text-xs leading-5 text-text-dim">{{ t('dialog.language_pack.create_hint', '创建后会出现在界面语言和翻译管理中，但不会自动生成译文。你可以在翻译管理中逐条修改，也可以开启翻译模式，点选界面文本后实时翻译。') }}</p>
      <div class="flex justify-end gap-2 pt-2">
        <button type="button" class="rounded-lg bg-bg-overlay/8 pl-3 pr-3 pt-2 pb-2 text-xs font-bold text-text-main hover:bg-bg-overlay/14" @click="showLanguageCreate = false">
          {{ t('common.action.cancel', '取消') }}
        </button>
        <button type="button" class="rounded-lg bg-accent-primary pl-4 pr-4 pt-2 pb-2 text-xs font-black text-on-accent-primary hover:bg-accent-primary/85 disabled:opacity-50" :disabled="creatingLanguage || !languageCode.trim()" @click="createLanguagePack">
          {{ creatingLanguage ? t('common.status.processing', '处理中') : t('common.action.create', '创建') }}
        </button>
      </div>
    </div>
  </CommonModalShell>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useVirtualizer } from '@tanstack/vue-virtual'
import { Download, Plus, RefreshCw, Upload, WandSparkles } from 'lucide-vue-next'
import CommonInput from '../input/CommonInput.vue'
import CommonModalShell from '../modal/CommonModalShell.vue'
import CommonSelect from '../input/CommonSelect.vue'
import { useConfirmStore } from '../modal/confirmStore'
import { useAppStore } from '../../../app/stores/appStore'
import { DEFAULT_LOCALE, getCurrentLocale, getLocaleMessagesForManagement, setLocale, t, translateMessagePayload, UNTRANSLATED_PREFIX } from '../../i18n.js'
import { toast } from '../../lib/common'

const appStore = useAppStore()
const confirmStore = useConfirmStore()
const selectedLanguage = ref(getCurrentLocale())
const selectedProvider = ref('ai.default')
const selectedNamespace = ref('all')
const statusFilter = ref('all')
const searchText = ref('')
const selectedKey = ref('')
const draftText = ref('')
const busy = ref(false)
const showLanguageCreate = ref(false)
const creatingLanguage = ref(false)
const languagePreset = ref('')
const languageCode = ref('')
const languageLabel = ref('')
const flatBase = ref({})
const flatBuiltin = ref({})
const flatMerged = ref({})
const flatUser = ref({})
const listScrollRef = ref(null)
const BATCH_TRANSLATE_SIZE = 100
const CUSTOM_LANGUAGE_VALUE = '__custom__'
const toolbarIconButtonClass = 'flex size-10 shrink-0 items-center justify-center rounded-md text-accent-primary transition-colors hover:bg-bg-overlay/8 active:scale-[0.96] disabled:pointer-events-none disabled:opacity-50'
const toRem = (value) => `${Number(value || 0) / 16}rem`
const PLACEHOLDER_RE = /\{([A-Za-z_][\w.-]*)\}/g
const LOCALE_MARKER_RE = /\[\[|\]\]|\^\^|!!|__|··/g

const flattenMessages = (value, prefix = '', output = {}) => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    if (prefix) output[prefix] = String(value ?? '')
    return output
  }
  Object.entries(value).forEach(([key, child]) => {
    if (!prefix && key === '_meta') return
    flattenMessages(child, prefix ? `${prefix}.${key}` : key, output)
  })
  return output
}

const languageOptions = computed(() => {
  const seen = new Set()
  return appStore.uiLanguageOptions.filter((item) => {
    const value = String(item?.value || item?.code || '').trim()
    if (!value || seen.has(value)) return false
    seen.add(value)
    item.value = value
    return true
  })
})
const selectedLanguageLabel = computed(() => languageOptions.value.find(item => item.value === selectedLanguage.value)?.label || selectedLanguage.value)
const createLanguageOptions = computed(() => [
  ...appStore.translationLanguageOptions.filter(item => !languageOptions.value.some(option => option.value === item.value)),
  { label: t('dialog.language_pack.custom_language', '自定义语言'), value: CUSTOM_LANGUAGE_VALUE },
])
const isCustomLanguage = computed(() => languagePreset.value === CUSTOM_LANGUAGE_VALUE)

const providerOptions = computed(() => {
  const providers = Array.isArray(appStore.translationProviders) ? appStore.translationProviders : []
  return providers.map(item => ({
    label: item.label_key ? t(item.label_key, item.default_label || item.label || item.id) : (item.label || item.name || item.id),
    value: item.id || item.value,
    type: item.type || '',
  })).filter(item => item.label && item.value)
})

const namespaceOptions = computed(() => [
  { label: t('common.option.all', '全部'), value: 'all' },
  ...Object.keys(flatBase.value).reduce((items, key) => {
    const namespace = key.split('.')[0]
    if (!items.some(item => item.value === namespace)) items.push({ label: namespace, value: namespace })
    return items
  }, []),
])

const statusOptions = computed(() => [
  { label: t('common.option.all', '全部'), value: 'all' },
  { label: t('dialog.translation_manager.status_untranslated', '未翻译'), value: 'untranslated' },
  { label: t('dialog.translation_manager.status_overridden', '已覆盖'), value: 'overridden' },
  { label: t('dialog.translation_manager.status_builtin', '内置'), value: 'builtin' },
])

const isUntranslatedText = (value) => {
  const text = String(value ?? '').trim()
  return !text || text.startsWith(UNTRANSLATED_PREFIX)
}

const getRowStatus = (key, currentText) => {
  if (Object.prototype.hasOwnProperty.call(flatUser.value, key)) return 'overridden'
  if (isUntranslatedText(currentText)) return 'untranslated'
  return 'builtin'
}

const rows = computed(() => Object.entries(flatBase.value).map(([key, sourceText]) => {
  const currentText = flatMerged.value[key] ?? ''
  return {
    key,
    sourceText,
    builtinText: flatBuiltin.value[key] ?? '',
    currentText: String(currentText || '').startsWith(UNTRANSLATED_PREFIX) ? String(currentText).slice(UNTRANSLATED_PREFIX.length) : currentText,
    userText: flatUser.value[key],
    status: getRowStatus(key, currentText),
  }
}))

const filteredRows = computed(() => {
  const query = searchText.value.trim().toLocaleLowerCase()
  return rows.value.filter((row) => {
    if (selectedNamespace.value !== 'all' && !row.key.startsWith(`${selectedNamespace.value}.`)) return false
    if (statusFilter.value !== 'all' && row.status !== statusFilter.value) return false
    if (!query) return true
    return [row.key, row.sourceText, row.currentText].some(value => String(value || '').toLocaleLowerCase().includes(query))
  })
})
const batchTranslateRows = computed(() => filteredRows.value.filter(row => row.status === 'untranslated'))

const rowHeight = computed(() => appStore.scalePx(62))
const rowGap = computed(() => appStore.scalePx(4))
const virtualizer = useVirtualizer(computed(() => ({
  count: filteredRows.value.length,
  getScrollElement: () => listScrollRef.value,
  estimateSize: () => rowHeight.value,
  overscan: 10,
})))
const virtualRows = computed(() => virtualizer.value.getVirtualItems())
const totalSize = computed(() => virtualizer.value.getTotalSize())

const selectedRow = computed(() => rows.value.find(row => row.key === selectedKey.value) || filteredRows.value[0] || null)

const statusLabel = (status) => ({
  untranslated: t('dialog.translation_manager.status_untranslated', '未翻译'),
  overridden: t('dialog.translation_manager.status_overridden', '已覆盖'),
  builtin: t('dialog.translation_manager.status_builtin', '内置'),
}[status] || status)

const extractPlaceholders = (text) => new Set([...String(text ?? '').matchAll(PLACEHOLDER_RE)].map(item => item[1]))
const extractLocaleMarkers = (text) => String(text ?? '').match(LOCALE_MARKER_RE) || []
const sameSet = (left, right) => left.size === right.size && [...left].every(item => right.has(item))
const sameList = (left, right) => left.length === right.length && left.every((item, index) => item === right[index])

const validateImportedMessage = (key, text) => {
  const source = flatBase.value[key]
  if (source === undefined) return t('dialog.translation_manager.workfile_unknown_key', '未知 key：{key}', { key })
  const sourceParams = extractPlaceholders(source)
  const targetParams = extractPlaceholders(text)
  if (!sameSet(sourceParams, targetParams)) return t('dialog.translation_manager.workfile_param_mismatch', '参数不一致：{key}', { key })
  const sourceMarkers = extractLocaleMarkers(source)
  const targetMarkers = extractLocaleMarkers(text)
  if (!sameList(sourceMarkers, targetMarkers)) return t('dialog.translation_manager.workfile_marker_mismatch', '格式标记不一致：{key}', { key })
  return ''
}

const statusClass = (status) => ({
  untranslated: 'bg-accent-warn/15 text-accent-warn',
  overridden: 'bg-accent-success/15 text-accent-success',
  builtin: 'bg-bg-overlay/10 text-text-dim',
}[status] || 'bg-bg-overlay/10 text-text-dim')

const loadMessages = async () => {
  const data = await getLocaleMessagesForManagement(selectedLanguage.value)
  flatBase.value = flattenMessages(data.base)
  flatBuiltin.value = flattenMessages(data.builtin)
  flatMerged.value = flattenMessages(data.merged)
  flatUser.value = flattenMessages(data.user)
  if (!selectedRow.value) selectedKey.value = filteredRows.value[0]?.key || ''
}

const close = () => {
  showLanguageCreate.value = false
  appStore.uiState.showTranslationManager = false
}

const openLanguageCreate = async () => {
  await appStore.ensureLanguageOptions(true)
  const first = createLanguageOptions.value[0] || {}
  languagePreset.value = first.value || ''
  languageCode.value = first.value === CUSTOM_LANGUAGE_VALUE ? '' : (first.value || '')
  languageLabel.value = first.value === CUSTOM_LANGUAGE_VALUE ? '' : (first.label || '')
  showLanguageCreate.value = true
}

const createLanguagePack = async () => {
  if (!languageCode.value.trim()) return
  creatingLanguage.value = true
  try {
    const result = await appStore.createUserLocale(languageCode.value, languageLabel.value)
    if (!result) return
    selectedLanguage.value = result.language
    toast.success(t('dialog.language_pack.created', '已创建语言包：{label}', { label: result.label || result.language }))
    showLanguageCreate.value = false
  } finally {
    creatingLanguage.value = false
  }
}

const ensureProviderSelection = async () => {
  await appStore.ensureTranslationProviders()
  if (!selectedProvider.value || !providerOptions.value.some(item => item.value === selectedProvider.value)) {
    selectedProvider.value = appStore.getTranslationFeatureSettings('default').provider || providerOptions.value[0]?.value || 'ai.default'
  }
}

const getAutoTranslateProvider = async () => {
  if (selectedLanguage.value === DEFAULT_LOCALE) {
    toast.warning(t('messages.i18n.translation_mode.default_locale_skip', '当前已经是默认中文，不需要自动翻译。'))
    return ''
  }
  if (!window.pywebview?.api?.translation_translate_document) {
    toast.warning(t('messages.i18n.translation_mode.auto_translate_unavailable', '当前运行环境不支持自动翻译。'))
    return ''
  }
  await ensureProviderSelection()
  const provider = selectedProvider.value || 'ai.default'
  const providerInfo = providerOptions.value.find(item => item.value === provider)
  if (providerInfo?.type === 'ai' && !appStore.settings.ai?.enabled) {
    toast.warning(t('messages.i18n.translation_mode.ai_not_configured', '请先在设置中启用并配置 AI 翻译。'))
    return ''
  }
  return provider
}

const saveSelected = async () => {
  if (!selectedRow.value || !window.pywebview?.api?.locale_save_user_message) return
  busy.value = true
  try {
    const shouldReset = !draftText.value.trim()
    if (shouldReset && !window.pywebview?.api?.locale_delete_user_message) {
      toast.warning(t('dialog.translation_manager.reset_unavailable', '当前运行环境不支持重置翻译。'))
      return
    }
    const res = shouldReset
      ? await window.pywebview.api.locale_delete_user_message(selectedLanguage.value, selectedRow.value.key)
      : await window.pywebview.api.locale_save_user_message(selectedLanguage.value, selectedRow.value.key, draftText.value)
    if (res?.status !== 'success') {
      toast.error(translateMessagePayload(res, t('messages.i18n.translation_mode.save_failed', '保存翻译失败。')))
      return
    }
    await loadMessages()
    if (getCurrentLocale() === selectedLanguage.value) await setLocale(selectedLanguage.value)
    toast.success(shouldReset ? t('dialog.translation_manager.reset_saved', '翻译已重置并重新加载。') : t('messages.i18n.translation_mode.saved', '翻译已保存并重新加载。'))
  } finally {
    busy.value = false
  }
}

const autoTranslateSelected = async () => {
  if (!selectedRow.value) return
  const provider = await getAutoTranslateProvider()
  if (!provider) return
  busy.value = true
  try {
    const res = await window.pywebview.api.translation_translate_document({
      format: 'plain_text',
      context: 'RimCrow interface text',
      segments: [{ key: selectedRow.value.key, text: selectedRow.value.sourceText, role: 'ui' }],
    }, selectedLanguage.value, provider)
    if (res?.status !== 'success') {
      toast.error(translateMessagePayload(res, t('messages.i18n.translation_mode.auto_translate_failed', '自动翻译失败。')))
      return
    }
    const segment = Array.isArray(res.data?.segments) ? res.data.segments.find(item => item.key === selectedRow.value.key) : null
    draftText.value = segment?.text || draftText.value
  } finally {
    busy.value = false
  }
}

const autoTranslateBatch = async () => {
  const targets = batchTranslateRows.value
  if (!targets.length) {
    toast.warning(t('dialog.translation_manager.no_batch_targets', '当前筛选范围内没有未翻译项。'))
    return
  }
  if (!window.pywebview?.api?.locale_save_user_messages) {
    toast.warning(t('dialog.translation_manager.batch_save_unavailable', '当前运行环境不支持批量保存翻译。'))
    return
  }
  const provider = await getAutoTranslateProvider()
  if (!provider) return
  busy.value = true
  try {
    const messages = {}
    for (let index = 0; index < targets.length; index += BATCH_TRANSLATE_SIZE) {
      const batch = targets.slice(index, index + BATCH_TRANSLATE_SIZE)
      const res = await window.pywebview.api.translation_translate_document({
        format: 'plain_text',
        context: 'RimCrow interface text',
        segments: batch.map(row => ({ key: row.key, text: row.sourceText, role: 'ui' })),
      }, selectedLanguage.value, provider)
      if (res?.status !== 'success') {
        toast.error(translateMessagePayload(res, t('messages.i18n.translation_mode.auto_translate_failed', '自动翻译失败。')))
        return
      }
      for (const item of (res.data?.segments || [])) {
        if (item?.key && String(item?.text || '').trim()) messages[item.key] = item.text
      }
    }
    if (!Object.keys(messages).length) {
      toast.warning(t('dialog.translation_manager.batch_empty_result', '翻译器没有返回可保存的译文。'))
      return
    }
    const saveRes = await window.pywebview.api.locale_save_user_messages(selectedLanguage.value, messages)
    if (saveRes?.status !== 'success') {
      toast.error(translateMessagePayload(saveRes, t('messages.i18n.translation_mode.save_failed', '保存翻译失败。')))
      return
    }
    await loadMessages()
    if (getCurrentLocale() === selectedLanguage.value) await setLocale(selectedLanguage.value)
    toast.success(t('dialog.translation_manager.batch_saved', '已翻译并保存 {count} 条。', { count: Object.keys(messages).length }))
  } finally {
    busy.value = false
  }
}

const buildWorkfileMessages = () => Object.fromEntries(rows.value.map(row => [row.key, {
    source: row.sourceText,
    target: row.status === 'untranslated' ? '' : (row.userText ?? row.currentText ?? ''),
  }]))

const exportWorkfile = async () => {
  if (!window.pywebview?.api?.locale_export_workfile) {
    toast.warning(t('dialog.translation_manager.workfile_export_unavailable', '当前运行环境不支持导出翻译文件。'))
    return
  }
  busy.value = true
  try {
    const filename = `rimcrow-locale-${selectedLanguage.value}.work.json`
    const res = await window.pywebview.api.locale_export_workfile(selectedLanguage.value, buildWorkfileMessages(), filename)
    if (res?.status === 'success') {
      const targetPath = res.data?.path || ''
      const action = await confirmStore.confirmAction(
        t('dialog.translation_manager.workfile_exported', '待翻译文件已导出。'),
        targetPath ? t('common.message.export_path', '导出路径：{path}', { path: targetPath }) : '',
        {
          type: 'success',
          actionButtons: [
            { label: t('common.action.open_export_dir', '打开导出目录'), value: 'open', kind: 'primary' },
            { label: t('common.action.close', '关闭'), value: 'close', kind: 'secondary' },
          ],
        }
      )
      if (action === 'open' && targetPath) await appStore.openPath(targetPath)
    } else if (res?.status !== 'warning') {
      toast.error(translateMessagePayload(res, t('dialog.translation_manager.workfile_export_failed', '导出翻译文件失败。')))
    }
  } finally {
    busy.value = false
  }
}

const extractWorkfileMessages = (payload) => {
  const errors = []
  const messages = Object.fromEntries(Object.entries(payload || {}).map(([key, value]) => {
    const target = value && typeof value === 'object' ? value.target : value
    const text = String(target ?? '').trim()
    if (!key || isUntranslatedText(text)) return null
    const error = validateImportedMessage(key, target)
    if (error) {
      errors.push(error)
      return null
    }
    return [key, target]
  }).filter(Boolean))
  return { messages, errors }
}

const importWorkfile = async () => {
  if (!window.pywebview?.api?.locale_import_workfile || !window.pywebview?.api?.locale_save_user_messages) {
    toast.warning(t('dialog.translation_manager.workfile_import_unavailable', '当前运行环境不支持导入翻译文件。'))
    return
  }
  busy.value = true
  try {
    const importRes = await window.pywebview.api.locale_import_workfile()
    if (importRes?.status === 'warning') return
    if (importRes?.status !== 'success') {
      toast.error(translateMessagePayload(importRes, t('dialog.translation_manager.workfile_import_failed', '导入翻译文件失败。请确认文件格式正确。')))
      return
    }
    const fileLanguage = String(importRes.data?.language || '').trim()
    if (fileLanguage && fileLanguage !== selectedLanguage.value) {
      toast.warning(t('dialog.translation_manager.workfile_language_mismatch', '导入文件的目标语言是 {language}，请先切换到对应目标语言后再导入。', { language: fileLanguage }))
      return
    }
    if (!Object.keys(flatBase.value).length) await loadMessages()
    const { messages, errors } = extractWorkfileMessages(importRes.data?.messages || {})
    if (errors.length) {
      toast.error(t('dialog.translation_manager.workfile_invalid', '导入文件存在 {count} 个格式问题：{detail}', { count: errors.length, detail: errors.slice(0, 3).join('；') }))
      return
    }
    if (!Object.keys(messages).length) {
      toast.warning(t('dialog.translation_manager.workfile_empty', '没有可导入的有效译文。'))
      return
    }
    await appStore.createUserLocale(selectedLanguage.value, selectedLanguageLabel.value)
    const res = await window.pywebview.api.locale_save_user_messages(selectedLanguage.value, messages)
    if (res?.status !== 'success') {
      toast.error(translateMessagePayload(res, t('messages.i18n.translation_mode.save_failed', '保存翻译失败。')))
      return
    }
    await loadMessages()
    if (getCurrentLocale() === selectedLanguage.value) await setLocale(selectedLanguage.value)
    toast.success(t('dialog.translation_manager.workfile_imported', '已导入 {count} 条译文。', { count: Object.keys(messages).length }))
  } catch (error) {
    console.warn('导入翻译工作文件失败:', error)
    toast.error(t('dialog.translation_manager.workfile_import_failed', '导入翻译文件失败。请确认文件格式正确。'))
  } finally {
    busy.value = false
  }
}

watch(selectedRow, (row) => {
  draftText.value = row?.userText ?? row?.currentText ?? ''
}, { immediate: true })

watch(languagePreset, (value) => {
  if (value === CUSTOM_LANGUAGE_VALUE) {
    languageCode.value = ''
    languageLabel.value = ''
    return
  }
  const option = appStore.translationLanguageOptions.find(item => item.value === value)
  if (!option) return
  languageCode.value = option.value
  languageLabel.value = option.label
})

watch(selectedLanguage, () => {
  selectedKey.value = ''
  void loadMessages()
})

watch(() => appStore.uiState.showTranslationManager, async (visible) => {
  if (!visible) return
  selectedLanguage.value = getCurrentLocale()
  await Promise.all([appStore.ensureUiLanguageOptions(true), appStore.ensureTranslationLanguageOptions(), ensureProviderSelection()])
  await loadMessages()
}, { immediate: true })
</script>
