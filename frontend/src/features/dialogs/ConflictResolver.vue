<template>
  <CommonModalShell :show="visible" :show-header="false" size="page" :z-index="100" accent="danger"
    panel-class="border-accent-danger/18" content-class="flex flex-col"
    @close="visible = false" >
        <div class="shrink-0 border-b border-border-base/10 bg-[linear-gradient(135deg,rgba(var(--rgb-bg-deep),0.94),rgba(var(--rgb-bg-inset),0.92))] px-4 py-3" data-tour="conflict-summary">
          <div class="flex items-start justify-between gap-3">
            <div class="min-w-0">
              <div class="flex flex-wrap items-center gap-2">
                <h2 class="text-lg font-black tracking-wide text-text-main">{{ t('conflictResolver.title') }}</h2>
                <span class="rounded-full border border-border-base/10 bg-bg-overlay/5 px-2 py-0.5 text-xs text-text-dim">
                  {{ t('conflictResolver.hardConflict') }} {{ summary.hardCount }}
                </span>
                <span class="rounded-full border border-border-base/10 bg-bg-overlay/5 px-2 py-0.5 text-xs text-text-dim">
                  {{ t('conflictResolver.coexistence') }} {{ summary.softCount }}
                </span>
                <span class="rounded-full border border-border-base/10 bg-bg-overlay/5 px-2 py-0.5 text-xs text-text-dim">
                  {{ t('conflictResolver.pending') }} {{ summary.pendingCount }}
                </span>
                <span class="rounded-full border border-accent-warn/22 bg-accent-warn/10 px-2 py-0.5 text-xs text-accent-warn">
                  {{ t('conflictResolver.disabled') }} {{ summary.disableCount }}
                </span>
                <span class="rounded-full border border-accent-danger/22 bg-accent-danger/10 px-2 py-0.5 text-xs text-accent-danger">
                  {{ t('conflictResolver.deleted') }} {{ summary.deleteCount }}
                </span>
              </div>
              <p class="mt-1 text-xs text-text-dim">
                {{ t('conflictResolver.subtitle') }}
              </p>
            </div>

            <div class="flex items-center gap-2">
              <CommonSwitch :model-value="appStore.settings.show_coexistence_message"
                @update:modelValue="handleCoexistenceToggle" :label="t('conflictResolver.showCoexistence')" mini
                :description="t('conflictResolver.showCoexistenceDesc')"
              />
              <button class="modal-close-button" :aria-label="t('common.close')" v-tooltip="t('conflictResolver.closeTooltip')" @click="visible = false" >
                <X class="size-4" />
              </button>
            </div>
          </div>
        </div>

        <div class="flex min-h-0 flex-1">
          <div class="min-w-0 flex-1 overflow-y-auto px-4 py-4" data-tour="conflict-list">
            <div class="space-y-3">
              <div v-for="group in localGroups" :key="group.key"
                class="overflow-hidden rounded-2xl border border-border-base/10 bg-[linear-gradient(180deg,rgba(var(--rgb-accent-primary),0.026),rgba(var(--rgb-accent-primary),0.015))]" >
                <div class="toolbar-surface flex flex-wrap items-center justify-between gap-2 px-3 py-2">
                  <div class="min-w-0 flex items-center gap-2">
                    <span class="truncate font-mono text-sm font-black text-accent-highlight">
                      {{ group.package_id }}
                    </span>
                    <span tabindex="0" class="rounded-full border px-2 py-0.5 text-[0.7rem] font-black uppercase tracking-[0.14em] cursor-help"
                      :class="group._type === 'hard'
                        ? 'border-accent-danger/28 bg-accent-danger/10 text-accent-danger'
                        : 'border-accent-primary/25 bg-accent-primary/10 text-accent-primary'"
                      v-tooltip="group._type === 'hard' ? t('conflictResolver.hardConflictTooltip') : t('conflictResolver.coexistenceTooltip')" >
                      {{ group._type === 'hard' ? t('conflictResolver.hardConflict') : t('conflictResolver.coexistence') }}
                    </span>
                    <span class="rounded-full border border-border-base/10 bg-bg-overlay/5 px-2 py-0.5 text-[0.7rem] text-text-dim">
                      {{ t('conflictResolver.copyCount', { count: group.items.length }) }}
                    </span>
                  </div>
                </div>

                <div class="space-y-2 p-3">
                  <div v-for="mod in group.items" :key="getItemKey(mod)"
                    class="flex items-center gap-2 rounded-xl border px-3 py-2 transition-all"
                    :class="isWinner(group, mod)
                      ? 'border-accent-success/30 bg-accent-success/8'
                      : 'border-border-base/10 bg-bg-inset/55 hover:border-border-base/18 hover:bg-bg-inset/80'"
                    @click="selectVersion(group.key, getItemKey(mod))" >
                    <div class="flex size-5 shrink-0 items-center justify-center rounded-full border text-[0.7rem] font-black"
                      :class="isWinner(group, mod)
                        ? 'border-accent-success bg-accent-success text-on-accent-success'
                        : 'border-border-base/18 text-text-dim'" >
                      <Check v-if="isWinner(group, mod)" class="size-3" />
                      <X v-else class="size-3" />
                    </div>

                    <div class="min-w-0 flex-1" tabindex="0" v-tooltip="getModTooltip(mod)">
                      <div class="flex flex-wrap items-center gap-1.5">
                        <span class="truncate text-sm font-bold text-text-main">
                          {{ mod.name || mod.package_id || t('conflictResolver.unknownMod') }}
                        </span>
                        <span class="rounded-full border px-2 py-0.5 text-[0.7rem] font-bold" :class="storeBadgeClass(mod.store)" >
                          {{ storeLabel(mod.store) }}
                        </span>
                        <span class="rounded-full border border-border-base/10 bg-bg-overlay/5 px-2 py-0.5 text-[0.7rem] font-mono text-text-dim">
                          {{ t('conflictResolver.supportsVersion', { version: getHighestSupportedVersion(mod) || '?' }) }}
                        </span>
                        <span class="rounded-full border border-border-base/10 bg-bg-overlay/5 px-2 py-0.5 text-[0.7rem] font-mono text-text-dim">
                          v{{ mod.version || '?' }}
                        </span>
                        <span v-if="isWinner(group, mod)" class="rounded-full border border-accent-success/25 bg-accent-success/10 px-2 py-0.5 text-[0.7rem] font-black text-accent-success" >
                          {{ t('conflictResolver.keep') }}
                        </span>
                      </div>
                      <div class="truncate font-mono text-xs text-text-dim" :title="mod.path">
                        {{ mod.path || '-' }}
                      </div>
                    </div>

                    <div class="flex shrink-0 items-center gap-1.5" @click.stop>
                      <button v-if="mod.workshop_id && ['workshop', 'self'].includes(normalizeStore(mod.store))"
                        class="rounded-full border border-border-base/10 bg-bg-overlay/5 px-2 py-1 text-[0.7rem] font-bold text-text-dim transition-colors hover:text-accent-primary"
                        v-tooltip="t('conflictResolver.localizeTooltip')"
                        @click="handleLocalize(mod)" >
                        {{ t('conflictResolver.localizeCoexistence') }}
                      </button>
                      <button v-if="mod.workshop_id && normalizeStore(mod.store) === 'workshop'" v-tooltip="t('conflictResolver.unsubscribeTooltip')"
                        class="rounded-full border border-border-base/10 bg-bg-overlay/5 px-2 py-1 text-[0.7rem] font-bold text-text-dim transition-colors hover:text-accent-danger"
                        @click="handleUnsubscribe(mod)" >
                        {{ t('conflictResolver.unsubscribeAndDelete') }}
                      </button>
                      <button class="rounded-full border border-border-base/10 bg-bg-overlay/5 p-1.5 text-text-dim transition-colors hover:border-accent-cool/30 hover:text-accent-cool"
                        v-tooltip="t('conflictResolver.openFolderTooltip')" @click="appStore.openPath(mod.path)" >
                        <Folder class="size-3.5" />
                      </button>

                      <div v-if="!isWinner(group, mod)" class="flex items-center gap-0.5 rounded-full border border-border-base/10 bg-bg-overlay/5 p-0.5">
                        <label class="cursor-pointer rounded-full px-2.5 py-1 text-xs font-bold transition-colors"
                          :class="actionMap[getItemKey(mod)] === 'disable'
                            ? 'bg-accent-warn text-on-accent-warn'
                            : 'text-text-dim hover:text-accent-warn'"
                          @click.stop v-tooltip="t('conflictResolver.disableTooltip')">
                          <input class="sr-only" type="radio" :name="`action-${getItemKey(mod)}`" :checked="actionMap[getItemKey(mod)] === 'disable'"
                            @change="setItemAction(group, mod, 'disable')" >
                          {{ t('conflictResolver.disabled') }}
                        </label>
                        <label class="cursor-pointer rounded-full px-2.5 py-1 text-xs font-bold transition-colors"
                          :class="actionMap[getItemKey(mod)] === 'delete' ? 'bg-accent-danger text-on-accent-danger'  : 'text-text-dim hover:text-accent-danger'" 
                          @click.stop v-tooltip="t('conflictResolver.deleteTooltip')" >
                          <input class="sr-only" type="radio" :name="`action-${getItemKey(mod)}`" :checked="actionMap[getItemKey(mod)] === 'delete'" @change="setItemAction(group, mod, 'delete')" >
                          {{ t('conflictResolver.deleted') }}
                        </label>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <aside class="w-75 shrink-0 overflow-y-auto border-l border-border-base/10 bg-[linear-gradient(180deg,rgba(var(--rgb-bg-deep),0.9),rgba(var(--rgb-bg-inset),0.92))] px-4 py-4">
            <div class="space-y-3">
              <section class="modal-section p-3" data-tour="conflict-batch">
                <div class="text-xs font-black uppercase tracking-[0.16em] text-text-dim">{{ t('conflictResolver.batchSelect') }}</div>
                <p class="mt-1 text-xs leading-5 text-text-dim">
                  {{ t('conflictResolver.batchSelectSubtitle') }}
                </p>

                <div class="mt-3 space-y-2.5">
                  <CommonSelect v-model="batchRule.scope" :options="SCOPE_OPTIONS" :label="t('conflictResolver.scope')" mini />
                  <CommonSelect v-model="batchRule.keepRule" :options="BATCH_KEEP_OPTIONS" :label="t('conflictResolver.keepRule')" mini />
                  <CommonSelect v-model="batchRule.loserAction" :options="ACTION_OPTIONS" :label="t('conflictResolver.loserAction')" mini />
                </div>

                <div class="mt-3 flex flex-wrap gap-1.5 text-xs">
                  <button class="rounded-full border border-accent-primary/24 bg-accent-primary/10 px-3 py-1 font-bold text-accent-primary transition-colors hover:bg-accent-primary/16"
                    v-tooltip="t('conflictResolver.applyBatchTooltip')" @click="applyBatchRule" >
                    {{ t('conflictResolver.applyBatch') }}
                  </button>
                  <button class="rounded-full border border-accent-success/24 bg-accent-success/10 px-3 py-1 font-bold text-accent-success transition-colors hover:bg-accent-success/16"
                    v-tooltip="t('conflictResolver.restoreRecommendedTooltip')" @click="restoreRecommended" >
                    {{ t('conflictResolver.restoreRecommended') }}
                  </button>
                  <button class="rounded-full border border-accent-warn/20 bg-accent-warn/10 px-3 py-1 font-bold text-accent-warn transition-colors hover:bg-accent-warn/16"
                    v-tooltip="t('conflictResolver.disableAllTooltip')" @click="setLoserActionForScope('disable')" >
                    {{ t('conflictResolver.disableAll') }}
                  </button>
                  <button class="rounded-full border border-border-base/10 bg-bg-overlay/5 px-3 py-1 font-bold text-text-dim transition-colors hover:text-accent-danger"
                    v-tooltip="t('conflictResolver.deleteAllTooltip')" @click="setLoserActionForScope('delete')" >
                    {{ t('conflictResolver.deleteAll') }}
                  </button>
                </div>
              </section>

              <section class="modal-section p-3 text-xs leading-5 text-text-dim">
                <div class="flex flex-wrap gap-x-2 gap-y-1">
                  <span>{{ t('conflictResolver.scopeGroups', { count: scopedGroups.length }) }}</span>
                  <span>{{ t('conflictResolver.scopePending', { count: countPendingForScope }) }}</span>
                  <span class="text-accent-warn">{{ t('conflictResolver.scopeDisable', { count: countDisableForScope }) }}</span>
                  <span class="text-accent-danger">{{ t('conflictResolver.scopeDelete', { count: countDeleteForScope }) }}</span>
                </div>
                <div class="mt-2">
                  {{ t('conflictResolver.tipRecommended') }}
                </div>
                <div v-if="summary.workshopDeleteCount > 0" class="mt-2 text-accent-warn">
                  {{ t('conflictResolver.tipWorkshop') }}
                </div>
                <br>
                <div>
                  <p class="text-accent-tip">{{ t('conflictResolver.tipCoexistence') }}</p>
                  <p class="text-accent-warn">{{ t('conflictResolver.tipConflict') }}</p>
                </div>
              </section>

              <section v-if="submitFeedback" class="rounded-2xl border p-3 text-xs"
                :class="submitFeedback.kind === 'error'
                  ? 'border-accent-danger/24 bg-accent-danger/10 text-accent-danger'
                  : 'border-accent-warn/24 bg-accent-warn/10 text-accent-warn'" >
                <div class="font-black">
                  {{ submitFeedback.kind === 'error' ? t('conflictResolver.submitFailed') : t('conflictResolver.submitWarning') }}
                </div>
                <p class="mt-1 leading-5 text-text-main">{{ submitFeedback.message }}</p>
                <div v-if="submitFeedback.details?.length" class="mt-2 space-y-1 text-text-dim">
                  <div v-for="line in submitFeedback.details" :key="line" class="truncate font-mono">
                    {{ line }}
                  </div>
                </div>
              </section>
            </div>
          </aside>
        </div>

        <div class="modal-footer flex shrink-0 items-center justify-between gap-3 px-4 py-3" data-tour="conflict-submit">
          <div class="text-xs text-text-dim">
            {{ t('conflictResolver.submitWarningDesc') }}
            <div class="text-accent-warn">{{ t('conflictResolver.submitWarningWorkshop') }}
              <span class="text-accent-warning">{{ t('conflictResolver.submitWarningDisable') }}</span>
            </div>
            
          </div>
          <div class="flex shrink-0 items-center gap-2">
            <button class="rounded-xl border border-border-base/10 bg-bg-overlay/5 px-4 py-2 text-xs font-bold text-text-dim transition-colors hover:border-border-base/18 hover:text-text-main"
              v-tooltip="t('conflictResolver.closeConfirmTooltip')" @click="visible = false"
            >
              {{ t('conflictResolver.resolveLater') }}
            </button>
            <button class="rounded-xl bg-accent-primary px-4 py-2 text-xs font-black text-on-accent-primary transition-colors hover:bg-accent-primary/85 disabled:cursor-not-allowed disabled:opacity-50"
              :disabled="processing" v-tooltip="t('conflictResolver.submitTooltip')" @click="submit"
            >
              {{ processing ? t('statusBar.processing') : t('conflictResolver.executeResolve') }}
            </button>
          </div>
        </div>
  </CommonModalShell>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { useToast } from 'vue-toastification'
import { Check, Folder, X, XCircle } from 'lucide-vue-next'
import CommonSwitch from '../../shared/components/input/CommonSwitch.vue'
import CommonSelect from '../../shared/components/input/CommonSelect.vue'
import CommonModalShell from '../../shared/components/modal/CommonModalShell.vue'
import { useAppStore } from '../../app/stores/appStore'
import { useModStore } from '../mod/stores/modStore'
import { useConfirmStore } from '../../shared/components/modal/confirmStore'
import { t } from '../../app/i18n'

const appStore = useAppStore()
const modStore = useModStore()
const confirmStore = useConfirmStore()
const toast = useToast()

const visible = ref(false)
const processing = ref(false)
const localGroups = ref([])
const submitFeedback = ref(null)

const selections = reactive({})
const actionMap = reactive({})

const batchRule = reactive({
  scope: 'all',
  keepRule: 'recommended',
  loserAction: 'disable',
})

const SCOPE_OPTIONS = computed(() => [
  { value: 'all', label: t('conflictResolver.scopeAll'), desc: t('conflictResolver.scopeAllDesc') },
  { value: 'hard', label: t('conflictResolver.scopeHard'), desc: t('conflictResolver.scopeHardDesc') },
  { value: 'soft', label: t('conflictResolver.scopeSoft'), desc: t('conflictResolver.scopeSoftDesc') },
])

const BATCH_KEEP_OPTIONS = computed(() => [
  { value: 'recommended', label: t('conflictResolver.keepRuleRecommended'), desc: t('conflictResolver.keepRuleRecommendedDesc') },
  { value: 'prefer_local', label: t('conflictResolver.keepRuleLocal'), desc: t('conflictResolver.keepRuleLocalDesc') },
  { value: 'prefer_self', label: t('conflictResolver.keepRuleSelf'), desc: t('conflictResolver.keepRuleSelfDesc') },
  { value: 'prefer_workshop', label: t('conflictResolver.keepRuleWorkshop'), desc: t('conflictResolver.keepRuleWorkshopDesc') },
  { value: 'latest_modified', label: t('conflictResolver.keepRuleLatestModified'), desc: t('conflictResolver.keepRuleLatestModifiedDesc') },
  { value: 'earliest_modified', label: t('conflictResolver.keepRuleEarliestModified'), desc: t('conflictResolver.keepRuleEarliestModifiedDesc') },
  { value: 'latest_created', label: t('conflictResolver.keepRuleLatestCreated'), desc: t('conflictResolver.keepRuleLatestCreatedDesc') },
  { value: 'earliest_created', label: t('conflictResolver.keepRuleEarliestCreated'), desc: t('conflictResolver.keepRuleEarliestCreatedDesc') },
  { value: 'highest_supported_version', label: t('conflictResolver.keepRuleHighestSupported'), desc: t('conflictResolver.keepRuleHighestSupportedDesc') },
  { value: 'highest_mod_version', label: t('conflictResolver.keepRuleHighestModVersion'), desc: t('conflictResolver.keepRuleHighestModVersionDesc') },
  { value: 'shortest_path', label: t('conflictResolver.keepRuleShortestPath'), desc: t('conflictResolver.keepRuleShortestPathDesc') },
  { value: 'longest_path', label: t('conflictResolver.keepRuleLongestPath'), desc: t('conflictResolver.keepRuleLongestPathDesc') },
])

const ACTION_OPTIONS = computed(() => [
  { value: 'disable', label: t('conflictResolver.actionDisable'), desc: t('conflictResolver.actionDisableDesc') },
  { value: 'delete', label: t('conflictResolver.actionDelete'), desc: t('conflictResolver.actionDeleteDesc') },
])

const STORE_PRIORITY = {
  local: 300,
  self: 200,
  workshop: 100,
}

const normalizeStore = (store) => {
  const value = String(store || '').toLowerCase()
  if (['local', 'self', 'workshop', 'any'].includes(value)) return value
  return 'unknown'
}

const storeLabel = (store) => {
  const value = normalizeStore(store)
  if (value === 'local') return t('conflictResolver.local')
  if (value === 'self') return t('conflictResolver.self')
  if (value === 'workshop') return t('conflictResolver.workshop')
  return store || t('conflictResolver.unknown')
}

const storeBadgeClass = (store) => {
  const value = normalizeStore(store)
  if (value === 'local') return 'border-accent-success/25 bg-accent-success/10 text-accent-success'
  if (value === 'self') return 'border-accent-primary/25 bg-accent-primary/10 text-accent-primary'
  if (value === 'workshop') return 'border-accent-warn/28 bg-accent-warn/10 text-accent-warn'
  return 'border-border-base/10 bg-bg-overlay/5 text-text-dim'
}

const compareTextAsc = (left, right) => String(left || '').localeCompare(String(right || ''), undefined, {
  numeric: true,
  sensitivity: 'base',
})

const compareTextDesc = (left, right) => compareTextAsc(right, left)
const compareNumberAsc = (left, right) => Number(left || 0) - Number(right || 0)
const compareNumberDesc = (left, right) => Number(right || 0) - Number(left || 0)

const normalizeTimestamp = (value) => {
  if (!value) return 0
  if (typeof value === 'number') {
    if (value > 1e12) return value
    if (value > 1e9) return value * 1000
    return value
  }
  const parsed = Date.parse(value)
  return Number.isFinite(parsed) ? parsed : 0
}

const formatTime = (value) => {
  const timestamp = normalizeTimestamp(value)
  if (!timestamp) return '-'
  return new Date(timestamp).toLocaleString(globalThis.__RMM_UI_FORMAT_LOCALE__ || 'zh-CN', { hour12: false })
}

const getPathLength = (mod) => String(mod?.path || '').length
const getItemKey = (mod) => String(mod?.path_hash || mod?.path || '')

const joinSupportedVersions = (mod) => {
  const versions = Array.isArray(mod?.supported_versions) ? mod.supported_versions.filter(Boolean) : []
  return versions.join(', ')
}

const getHighestSupportedVersion = (mod) => {
  const versions = Array.isArray(mod?.supported_versions) ? [...mod.supported_versions].filter(Boolean) : []
  if (!versions.length) return ''
  return versions.sort(compareTextDesc)[0] || ''
}

const getStorePriority = (mod) => STORE_PRIORITY[normalizeStore(mod?.store)] || 0

const compareStablePath = (left, right) => {
  const pathCompare = compareTextAsc(left?.path, right?.path)
  if (pathCompare !== 0) return pathCompare
  return compareTextAsc(left?.name || left?.package_id, right?.name || right?.package_id)
}

const compareEffectivePriority = (left, right) => compareNumberDesc(getStorePriority(left), getStorePriority(right))
const compareLatestModified = (left, right) => compareNumberDesc(normalizeTimestamp(left?.file_modify_time || left?.mtime), normalizeTimestamp(right?.file_modify_time || right?.mtime))
const compareEarliestModified = (left, right) => compareNumberAsc(normalizeTimestamp(left?.file_modify_time || left?.mtime), normalizeTimestamp(right?.file_modify_time || right?.mtime))
const compareLatestCreated = (left, right) => compareNumberDesc(normalizeTimestamp(left?.file_create_time || left?.ctime), normalizeTimestamp(right?.file_create_time || right?.ctime))
const compareEarliestCreated = (left, right) => compareNumberAsc(normalizeTimestamp(left?.file_create_time || left?.ctime), normalizeTimestamp(right?.file_create_time || right?.ctime))
const compareHighestSupportedVersion = (left, right) => compareTextDesc(getHighestSupportedVersion(left), getHighestSupportedVersion(right))
const compareHighestModVersion = (left, right) => compareTextDesc(left?.version, right?.version)
const compareShortestPath = (left, right) => compareNumberAsc(getPathLength(left), getPathLength(right))
const compareLongestPath = (left, right) => compareNumberDesc(getPathLength(left), getPathLength(right))

const RULE_COMPARATORS = {
  recommended: [compareEffectivePriority, compareHighestSupportedVersion, compareHighestModVersion, compareLatestModified, compareShortestPath, compareStablePath],
  effective_priority: [compareEffectivePriority, compareHighestSupportedVersion, compareHighestModVersion, compareLatestModified, compareShortestPath, compareStablePath],
  latest_modified: [compareLatestModified, compareEffectivePriority, compareHighestSupportedVersion, compareHighestModVersion, compareShortestPath, compareStablePath],
  earliest_modified: [compareEarliestModified, compareEffectivePriority, compareHighestSupportedVersion, compareHighestModVersion, compareShortestPath, compareStablePath],
  latest_created: [compareLatestCreated, compareEffectivePriority, compareHighestSupportedVersion, compareHighestModVersion, compareShortestPath, compareStablePath],
  earliest_created: [compareEarliestCreated, compareEffectivePriority, compareHighestSupportedVersion, compareHighestModVersion, compareShortestPath, compareStablePath],
  highest_supported_version: [compareHighestSupportedVersion, compareEffectivePriority, compareHighestModVersion, compareLatestModified, compareShortestPath, compareStablePath],
  highest_mod_version: [compareHighestModVersion, compareHighestSupportedVersion, compareEffectivePriority, compareLatestModified, compareShortestPath, compareStablePath],
  shortest_path: [compareShortestPath, compareEffectivePriority, compareHighestSupportedVersion, compareHighestModVersion, compareLatestModified, compareStablePath],
  longest_path: [compareLongestPath, compareEffectivePriority, compareHighestSupportedVersion, compareHighestModVersion, compareLatestModified, compareStablePath],
}

const compareByRule = (left, right, keepRule = 'recommended') => {
  const comparators = RULE_COMPARATORS[keepRule] || RULE_COMPARATORS.recommended
  for (const comparator of comparators) {
    const result = comparator(left, right)
    if (result !== 0) return result
  }
  return 0
}

const pickWinner = (items, { preferredStore = 'any', keepRule = 'recommended' } = {}) => {
  if (!Array.isArray(items) || items.length === 0) return null
  const normalizedStore = normalizeStore(preferredStore)
  let candidates = [...items]
  if (normalizedStore !== 'any' && normalizedStore !== 'unknown') {
    const preferredCandidates = candidates.filter((item) => normalizeStore(item.store) === normalizedStore)
    if (preferredCandidates.length > 0) candidates = preferredCandidates
  }
  return [...candidates].sort((left, right) => compareByRule(left, right, keepRule))[0] || items[0]
}

const resolvePickConfig = (strategy = 'recommended') => {
  if (strategy === 'prefer_local') return { preferredStore: 'local', keepRule: 'recommended' }
  if (strategy === 'prefer_self') return { preferredStore: 'self', keepRule: 'recommended' }
  if (strategy === 'prefer_workshop') return { preferredStore: 'workshop', keepRule: 'recommended' }
  return { preferredStore: 'any', keepRule: strategy }
}

const buildGroupKey = (type, group) => {
  const ids = [...(group?.items || [])]
    .map((item) => getItemKey(item))
    .sort(compareTextAsc)
  return `${type}:${group?.package_id || 'unknown'}:${ids.join('|')}`
}

const normalizeGroup = (rawGroup, type) => ({
  ...rawGroup,
  key: buildGroupKey(type, rawGroup),
  _type: type,
  items: [...(rawGroup?.items || [])].map((item) => ({ ...item })).sort((left, right) => compareByRule(left, right, 'recommended')),
})

const groupMatchesScope = (group, scope) => scope === 'all' || group?._type === scope

const rebuildGroups = () => {
  const groups = []

  if (Array.isArray(modStore.conflictList)) {
    modStore.conflictList.forEach((group) => {
      const normalized = normalizeGroup(group, 'hard')
      if (normalized.items.length > 1) groups.push(normalized)
    })
  }

  if (appStore.settings.show_coexistence_message && Array.isArray(modStore.coexistenceList)) {
    modStore.coexistenceList.forEach((group) => {
      const normalized = normalizeGroup(group, 'soft')
      if (normalized.items.length > 1) groups.push(normalized)
    })
  }

  groups.sort((left, right) => {
    if (left._type !== right._type) return left._type === 'hard' ? -1 : 1
    return compareTextAsc(left.package_id, right.package_id)
  })

  const activeGroupKeys = new Set(groups.map((group) => group.key))
  const activeItemKeys = new Set(groups.flatMap((group) => group.items.map((item) => getItemKey(item)).filter(Boolean)))

  Object.keys(selections).forEach((groupKey) => {
    if (!activeGroupKeys.has(groupKey)) delete selections[groupKey]
  })
  Object.keys(actionMap).forEach((itemKey) => {
    if (!activeItemKeys.has(itemKey)) delete actionMap[itemKey]
  })

  groups.forEach((group) => {
    const selectedItemKey = selections[group.key]
    const hasSelection = group.items.some((item) => getItemKey(item) === selectedItemKey)
    if (!hasSelection) {
      const winner = pickWinner(group.items, { keepRule: 'recommended' })
      selections[group.key] = getItemKey(winner) || getItemKey(group.items[0])
    }
    group.items.forEach((item) => {
      const itemKey = getItemKey(item)
      if (itemKey && !actionMap[itemKey]) actionMap[itemKey] = 'disable'
    })
  })

  localGroups.value = groups
  submitFeedback.value = null
  visible.value = groups.length > 0
}

watch(
  [
    () => modStore.conflictList,
    () => modStore.coexistenceList,
    () => appStore.settings.show_coexistence_message,
  ],
  rebuildGroups,
  { deep: true, immediate: true }
)

const scopedGroups = computed(() => localGroups.value.filter((group) => groupMatchesScope(group, batchRule.scope)))

const summarizeGroups = (groups) => {
  let pending = 0
  let disable = 0
  let deleteCount = 0
  groups.forEach((group) => {
    const keepKey = selections[group.key]
    group.items.forEach((item) => {
      if (getItemKey(item) === keepKey) return
      pending += 1
      if ((actionMap[getItemKey(item)] || 'disable') === 'delete') deleteCount += 1
      else disable += 1
    })
  })
  return { pending, disable, deleteCount }
}

const summary = computed(() => {
  const result = {
    groupCount: localGroups.value.length,
    hardCount: 0,
    softCount: 0,
    pendingCount: 0,
    disableCount: 0,
    deleteCount: 0,
    workshopDeleteCount: 0,
  }

  localGroups.value.forEach((group) => {
    if (group._type === 'hard') result.hardCount += 1
    else result.softCount += 1

    const keepKey = selections[group.key]
    group.items.forEach((item) => {
      if (getItemKey(item) === keepKey) return
      result.pendingCount += 1
      const action = actionMap[getItemKey(item)] || 'disable'
      if (action === 'delete') {
        result.deleteCount += 1
        if (normalizeStore(item.store) === 'workshop') result.workshopDeleteCount += 1
      } else {
        result.disableCount += 1
      }
    })
  })

  return result
})

const scopedSummary = computed(() => summarizeGroups(scopedGroups.value))
const countPendingForScope = computed(() => scopedSummary.value.pending)
const countDisableForScope = computed(() => scopedSummary.value.disable)
const countDeleteForScope = computed(() => scopedSummary.value.deleteCount)

const isWinner = (group, mod) => selections[group.key] === getItemKey(mod)

const getModTooltip = (mod) => {
  return [
    `${t('conflictResolver.tooltipSource')}${storeLabel(mod.store)}`,
    `${t('conflictResolver.tooltipModVersion')}${mod.version || '-'}`,
    `${t('conflictResolver.tooltipHighestSupported')}${getHighestSupportedVersion(mod) || '-'}`,
    `${t('conflictResolver.tooltipSupportedList')}${joinSupportedVersions(mod) || '-'}`,
    `${t('conflictResolver.tooltipCreateTime')}${formatTime(mod.file_create_time || mod.ctime)}`,
    `${t('conflictResolver.tooltipModifyTime')}${formatTime(mod.file_modify_time || mod.mtime)}`,
    `${t('conflictResolver.tooltipWorkshopId')}${mod.workshop_id || '-'}`,
    `${t('conflictResolver.tooltipPath')}${mod.path || '-'}`,
  ].join('\n')
}

const selectVersion = (groupKey, itemKey) => {
  selections[groupKey] = itemKey
  submitFeedback.value = null
}

const setItemAction = (group, mod, action) => {
  const itemKey = getItemKey(mod)
  if (!itemKey || isWinner(group, mod)) return
  actionMap[itemKey] = action
  submitFeedback.value = null
}

const applyBatchRule = () => {
  if (!scopedGroups.value.length) {
    toast.info(t('conflictResolver.noResolvableGroups'))
    return
  }

  scopedGroups.value.forEach((group) => {
    const winner = pickWinner(group.items, resolvePickConfig(batchRule.keepRule))
    if (!winner) return
    selections[group.key] = getItemKey(winner)
    group.items.forEach((item) => {
      const itemKey = getItemKey(item)
      if (itemKey && itemKey !== getItemKey(winner)) actionMap[itemKey] = batchRule.loserAction
    })
  })

  submitFeedback.value = null
  toast.success(t('conflictResolver.toastSuccess', { count: scopedGroups.value.length }))
}

const restoreRecommended = () => {
  if (!localGroups.value.length) return
  localGroups.value.forEach((group) => {
    const winner = pickWinner(group.items, { keepRule: 'recommended' })
    if (!winner) return
    selections[group.key] = getItemKey(winner)
    group.items.forEach((item) => {
      const itemKey = getItemKey(item)
      if (itemKey && itemKey !== getItemKey(winner)) actionMap[itemKey] = 'disable'
    })
  })
  submitFeedback.value = null
  toast.success(t('conflictResolver.restoredRecommended'))
}

const setLoserActionForScope = (action) => {
  if (!scopedGroups.value.length) {
    toast.info(t('conflictResolver.noResolvableGroups'))
    return
  }

  scopedGroups.value.forEach((group) => {
    const keepKey = selections[group.key]
    group.items.forEach((item) => {
      const itemKey = getItemKey(item)
      if (itemKey && itemKey !== keepKey) actionMap[itemKey] = action
    })
  })
  submitFeedback.value = null
}

const buildOperations = () => {
  const operations = []
  localGroups.value.forEach((group) => {
    const winner = group.items.find((item) => getItemKey(item) === selections[group.key]) || group.items[0]
    if (!winner) return
    group.items.forEach((item) => {
      if (getItemKey(item) === getItemKey(winner)) return
      operations.push({
        action: actionMap[getItemKey(item)] || 'disable',
        target_path: item.path,
        target_path_hash: item.path_hash,
        force_delete: false,
        keep_id: group.package_id,
        keep_path_hash: winner.path_hash,
      })
    })
  })
  return operations
}

const submit = async () => {
  if (processing.value || !window.pywebview) return

  const operations = buildOperations()
  if (!operations.length) {
    toast.info(t('conflictResolver.noPendingOps'))
    visible.value = false
    return
  }

  const confirmMessage = [
    t('conflictResolver.confirmMessageGroup', { groupCount: summary.value.groupCount, opCount: operations.length }),
    t('conflictResolver.confirmMessageCount', { disableCount: summary.value.disableCount, deleteCount: summary.value.deleteCount }),
    summary.value.workshopDeleteCount > 0
      ? t('conflictResolver.confirmMessageWorkshop', { count: summary.value.workshopDeleteCount })
      : null,
    t('conflictResolver.confirmMessageFooter'),
  ].filter(Boolean).join('\n')

  const deleteCount = summary.value.deleteCount || 0
  const confirmResult = deleteCount > 0
    ? await confirmStore.confirmDeleteAction(
        t('conflictResolver.confirmTitle'),
        confirmMessage,
        {
          confirmText: t('conflictResolver.confirmExecute'),
          cancelText: t('conflictResolver.confirmRecheck'),
          trashOptionText: t('conflictResolver.confirmTrashOption'),
          forceOptionText: t('conflictResolver.confirmForceOption'),
          deleteOptionsHint: t('conflictResolver.confirmDeleteHint'),
        }
      )
    : await confirmStore.confirmAction(
        t('conflictResolver.confirmTitle'),
        confirmMessage,
        {
          type: 'warning',
          confirmText: t('conflictResolver.confirmExecute'),
          cancelText: t('conflictResolver.confirmRecheck'),
        }
      )
  if (deleteCount > 0) {
    if (!confirmResult?.confirmed) return
    operations.forEach((item) => {
      if (item.action === 'delete') item.force_delete = !!confirmResult.force
    })
  } else if (!confirmResult) return

  processing.value = true
  submitFeedback.value = null

  try {
    const res = await window.pywebview.api.scan_conflicts_resolve(operations)
    const resultStats = res?.data?.stats || {}

    if (res?.status === 'success' || (res?.status === 'warning' && resultStats.success_count > 0)) {
      modStore.conflictList = []
      modStore.coexistenceList = []
      visible.value = false

      if (res.status === 'success') {
        toast.success(t('conflictResolver.toastSuccess', { count: resultStats.success_count || operations.length }))
      } else {
        toast.warning(t('conflictResolver.toastWarning', { successCount: resultStats.success_count || 0, errorCount: resultStats.error_count || 0 }), {
          timeout: 9000,
        })
      }

      await modStore.scanMods()
      return
    }

    const failedPaths = Array.isArray(res?.data?.failed_paths) ? res.data.failed_paths : []
    submitFeedback.value = {
      kind: 'error',
      message: res?.message || t('conflictResolver.submitError'),
      details: failedPaths.slice(0, 3),
    }
    toast.error(t('conflictResolver.toastError', { msg: res?.message || t('common.unknownError') }))
  } catch (error) {
    const message = error?.message || t('conflictResolver.submitException')
    submitFeedback.value = { kind: 'error', message, details: [] }
    toast.error(message)
  } finally {
    processing.value = false
  }
}

const handleCoexistenceToggle = async (value) => {
  appStore.settings.show_coexistence_message = value
  await appStore.saveSetting('show_coexistence_message', value)
}

const handleLocalize = async (mod) => {
  if (!mod?.path_hash) return
  const store = normalizeStore(mod.store)
  if (!['self', 'workshop'].includes(store)) return
  await modStore.localizeMods([mod.path_hash], store)
}

const handleUnsubscribe = async (mod) => {
  if (!mod?.workshop_id || !mod?.path_hash) return
  await appStore.unsubscribeWorkshopIds([mod.workshop_id], [mod.path_hash])
}
</script>
