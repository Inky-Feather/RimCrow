<template>
  <CommonModalShell
    :show="appStore.uiState.showResetActiveListManager"
    size="compact"
    accent="warn"
    :title="t('dialog.reset_active_list_manager.title', '预设列表管理')"
    :description="t('dialog.reset_active_list_manager.description', '管理预设的基底启用列表，重置列表时会直接按以下列表重置。点击官方 DLC 或衍生补充项可切换排除状态。')"
    :show-close="!saving"
    :close-on-backdrop="!saving"
    :close-on-esc="!saving"
    @close="close"
  >
    <div class="flex max-h-[70vh] flex-col gap-3 overflow-y-auto px-5 py-2 custom-scrollbar">
      <section class="rounded-xl border border-border-base/10 bg-bg-inset/55 p-3">
        <h3 class="mb-2 text-xs font-black text-text-main">{{ t('dialog.reset_active_list_manager.required', '必要项（不可编辑）') }}</h3>
        <div class="flex flex-wrap gap-1.5">
          <span v-for="id in preview.requiredIds" :key="`required:${id}`" v-tooltip="formatPresetTooltip(id)" class="rounded border border-accent-danger/25 bg-accent-danger/10 px-2 py-1 text-xs text-accent-danger">
            {{ formatPresetId(id) }}
          </span>
          <span v-if="preview.requiredIds.length === 0" class="text-xs text-text-dim">{{ t('dialog.reset_active_list_manager.empty_required', '当前没有可显示的必要项。') }}</span>
        </div>
      </section>

      <section class="rounded-xl border border-border-base/10 bg-bg-inset/55 p-3">
        <h3 class="mb-2 text-xs font-black text-text-main">{{ t('dialog.reset_active_list_manager.official_dlc', '官方 DLC（可点击排除）') }}</h3>
        <div class="flex flex-wrap gap-1.5">
          <button v-for="id in preview.builtinIds" :key="`builtin:${id}`" v-tooltip="formatPresetTooltip(id)" type="button" class="cursor-pointer rounded border px-2 py-1 text-xs transition-colors"
            :class="isBuiltinExcluded(id) ? EXCLUDED_TAG_CLASS : 'border-accent-primary/25 bg-accent-primary/10 text-accent-primary hover:bg-accent-primary/20'"
            @click="toggleExcluded('builtin', id)">
            {{ formatPresetId(id) }}
          </button>
          <span v-if="preview.builtinIds.length === 0" class="text-xs text-text-dim">{{ t('dialog.reset_active_list_manager.empty_builtin', '当前没有可显示的官方 DLC。') }}</span>
        </div>
      </section>

      <section class="rounded-xl border border-border-base/10 bg-bg-inset/55 p-3">
        <CommonTagInput :label="t('dialog.reset_active_list_manager.custom_items', '自定义项')" v-model="draft.user_ids" :all-tags="packageIdTags" :description="t('dialog.reset_active_list_manager.custom_items_desc', '可输入名称或包名查找模组，或直接输入包名后回车加入预设。')" />
      </section>

      <section class="rounded-xl border border-border-base/10 bg-bg-inset/55 p-3">
        <h3 class="mb-2 text-xs font-black text-text-main">{{ t('dialog.reset_active_list_manager.supplement_dependencies', '补充依赖（根据上方模组项自动补充可点击排除）') }}</h3>
        <div class="flex flex-wrap gap-1.5">
          <button v-for="id in preview.derivedIds" :key="`derived:${id}`" v-tooltip="formatPresetTooltip(id)" type="button" class="cursor-pointer rounded border px-2 py-1 text-xs transition-colors"
            :class="isDerivedExcluded(id) ? EXCLUDED_TAG_CLASS : 'border-accent-warn/25 bg-accent-warn/10 text-accent-warn hover:bg-accent-warn/20'"
            @click="toggleExcluded('derived', id)">
            {{ formatPresetId(id) }}
          </button>
          <span v-if="preview.derivedIds.length === 0" class="text-xs text-text-dim">{{ t('dialog.reset_active_list_manager.empty_supplement_dependencies', '当前没有自动补充的依赖项。') }}</span>
        </div>
      </section>
    </div>

    <template #footer>
      <div class="flex items-center justify-end gap-2">
        <button type="button" class="rounded-xl border border-border-base/10 bg-bg-overlay/5 px-4 py-2 text-xs font-bold text-text-main transition-all hover:bg-bg-overlay/10 disabled:opacity-50" :disabled="saving" @click="close">
          {{ t('common.action.cancel', '取消') }}
        </button>
        <button type="button" class="rounded-xl bg-accent-warn px-5 py-2 text-sm font-black text-on-accent-warn transition-all hover:bg-accent-warn/85 disabled:cursor-not-allowed disabled:opacity-50" :disabled="saving" @click="save">
          {{ saving ? t('common.status.processing', '处理中') : t('common.action.save', '保存') }}
        </button>
      </div>
    </template>
  </CommonModalShell>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import CommonModalShell from '../../shared/components/modal/CommonModalShell.vue'
import CommonTagInput from '../../shared/components/input/CommonTagInput.vue'
import { useAppStore } from '../../app/stores/appStore'
import { useModStore } from './stores/modStore'
import { normalizePackageId, normalizePackageToken } from './lib/modIdentity'
import { t } from '../../shared/i18n.js'

const EXCLUDED_TAG_CLASS = 'cursor-pointer border-border-base/10 bg-bg-overlay/5 text-text-disabled line-through hover:bg-bg-overlay/10'

const appStore = useAppStore()
const modStore = useModStore()
const saving = ref(false)
const draft = reactive({
  user_ids: [],
  excluded_builtin_ids: [],
  excluded_derived_ids: [],
})
const preview = ref({ requiredIds: [], builtinIds: [], derivedIds: [] })
let previewSeq = 0

const normalizeIds = (ids = []) => [...new Set((ids || []).map(normalizePackageToken).filter(Boolean))]
const normalizeCanonicalIds = (ids = []) => [...new Set((ids || []).map(normalizePackageId).filter(Boolean))]
const buildConfig = () => ({
  user_ids: normalizeIds(draft.user_ids),
  excluded_builtin_ids: normalizeCanonicalIds(draft.excluded_builtin_ids),
  excluded_derived_ids: normalizeCanonicalIds(draft.excluded_derived_ids),
})
const buildRawConfig = () => ({ ...buildConfig(), excluded_builtin_ids: [], excluded_derived_ids: [] })

const loadDraft = () => {
  const config = appStore.settings.reset_active_list || {}
  draft.user_ids = normalizeIds(config.user_ids || [])
  draft.excluded_builtin_ids = normalizeCanonicalIds(config.excluded_builtin_ids || [])
  draft.excluded_derived_ids = normalizeCanonicalIds(config.excluded_derived_ids || [])
}

const refreshPreview = async () => {
  const seq = ++previewSeq
  const nextPreview = await modStore.resolveResetActiveListPreview({ config: buildRawConfig(), enableToolMods: appStore.settings.enable_tool_mods })
  if (seq !== previewSeq) return
  preview.value = nextPreview || { requiredIds: [], builtinIds: [], derivedIds: [] }
}

watch(draft, () => { void refreshPreview() }, { deep: true })
onMounted(() => {
  loadDraft()
  void refreshPreview()
})

const packageIdTags = computed(() => {
  const seen = new Set()
  return modStore.getAvailableModInstances()
    .map(mod => {
      const value = normalizePackageToken(mod?.active_package_token || mod?.package_id)
      if (!value || seen.has(value)) return null
      seen.add(value)
      return { label: modStore.displayModName(mod), value }
    })
    .filter(Boolean)
})
watch(() => packageIdTags.value.map(tag => tag.value).join('\n'), () => { void refreshPreview() })

const formatPresetId = (id = '') => {
  const name = modStore.displayModName(id, id)
  return name || id
}
const formatPresetTooltip = (id = '') => {
  const name = modStore.displayModName(id, id)
  return name && name !== id ? `${name}\n${id}` : id
}
const isBuiltinExcluded = (id = '') => draft.excluded_builtin_ids.includes(normalizePackageId(id))
const isDerivedExcluded = (id = '') => draft.excluded_derived_ids.includes(normalizePackageId(id))
const toggleExcluded = (type, id = '') => {
  const key = type === 'builtin' ? 'excluded_builtin_ids' : 'excluded_derived_ids'
  const normalizedId = normalizePackageId(id)
  if (!normalizedId) return
  draft[key] = draft[key].includes(normalizedId)
    ? draft[key].filter(item => item !== normalizedId)
    : [...draft[key], normalizedId]
}
const save = async () => {
  if (saving.value) return
  saving.value = true
  try {
    const config = buildConfig()
    const saved = await appStore.saveSetting('reset_active_list', config)
    if (saved) appStore.uiState.showResetActiveListManager = false
  } finally {
    saving.value = false
  }
}
const close = () => {
  if (saving.value) return
  appStore.uiState.showResetActiveListManager = false
}
</script>
