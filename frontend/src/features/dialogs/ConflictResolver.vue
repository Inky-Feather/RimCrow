<template>
  <CommonModalShell :show="visible" :show-header="false" size="page" :z-index="100" accent="danger"
    panel-class="border-accent-danger/18" content-class="flex flex-col"
    @close="visible = false" >
        <div class="shrink-0 border-b border-border-base/10 bg-[linear-gradient(135deg,rgba(var(--rgb-bg-deep),0.94),rgba(var(--rgb-bg-inset),0.92))] px-4 py-3" data-tour="conflict-summary">
          <div class="flex items-start justify-between gap-3">
            <div class="min-w-0">
              <div class="flex flex-wrap items-center gap-2">
                <h2 class="text-lg font-black tracking-wide text-text-main">{{ t('dialog.conflict.title', '处理重复模组') }}</h2>
                <span class="rounded-full border border-border-base/10 bg-bg-overlay/5 px-2 py-0.5 text-xs text-text-dim">
                  {{ t('dialog.conflict.badge.hard', '硬冲突 {count}', { count: summary.hardCount }) }}
                </span>
                <span class="rounded-full border border-border-base/10 bg-bg-overlay/5 px-2 py-0.5 text-xs text-text-dim">
                  {{ t('dialog.conflict.badge.soft', '共存 {count}', { count: summary.softCount }) }}
                </span>
                <span class="rounded-full border border-border-base/10 bg-bg-overlay/5 px-2 py-0.5 text-xs text-text-dim">
                  {{ t('dialog.conflict.badge.pending', '待处理 {count}', { count: summary.pendingCount }) }}
                </span>
                <span class="rounded-full border border-accent-warn/22 bg-accent-warn/10 px-2 py-0.5 text-xs text-accent-warn">
                  {{ t('dialog.conflict.badge.disable', '禁用 {count}', { count: summary.disableCount }) }}
                </span>
                <span class="rounded-full border border-accent-danger/22 bg-accent-danger/10 px-2 py-0.5 text-xs text-accent-danger">
                  {{ t('dialog.conflict.badge.delete', '删除 {count}', { count: summary.deleteCount }) }}
                </span>
                <span class="rounded-full border border-border-base/10 bg-bg-overlay/5 px-2 py-0.5 text-xs text-text-dim">
                  {{ t('dialog.conflict.badge.skip', '跳过 {count}', { count: summary.skipCount }) }}
                </span>
              </div>
              <p class="mt-1 text-xs text-text-dim">
                {{ t('dialog.conflict.subtitle', '先选要保留的副本，再决定其余副本是禁用还是删除。') }}
              </p>
            </div>

            <div class="flex items-center gap-2">
              <CommonSwitch :model-value="appStore.settings.show_coexistence_message"
                @update:modelValue="handleCoexistenceToggle" :label="t('dialog.conflict.show_coexistence', '显示共存提示')" mini
                :description="t('dialog.conflict.show_coexistence_desc', '关闭后只显示同级硬冲突')"
              />
              <button class="modal-close-button" :aria-label="t('common.action.close', '关闭')" v-tooltip="t('tooltip.conflict.close', '关闭冲突处理弹窗，稍后再处理这些重复副本')" @click="visible = false" >
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
                      v-tooltip="group._type === 'hard' ? t('tooltip.conflict.hard_group', '!!在同一个目录下发现重复文件，这可能会引起冲突，需要处理!!') : t('tooltip.conflict.soft_group', '不同目录下发现重复文件，这是正常现象，可选择处理，游戏会默认使用本地版本')" >
                      {{ group._type === 'hard' ? t('dialog.conflict.group_type.hard', '硬冲突') : t('dialog.conflict.group_type.soft', '共存') }}
                    </span>
                    <span class="rounded-full border border-border-base/10 bg-bg-overlay/5 px-2 py-0.5 text-[0.7rem] text-text-dim">
                      {{ t('dialog.conflict.copy_count', '{count} 个副本', { count: group.items.length }) }}
                    </span>
                  </div>
                </div>

                <div class="space-y-2 p-3">
                  <div v-for="mod in group.items" :key="getItemKey(mod)"
                    class="flex items-center gap-2 rounded-xl border px-3 py-2 transition-all"
                    :class="isWinner(group, mod)
                      ? 'border-accent-success/30 bg-accent-success/8'
                      : 'border-border-base/10 bg-bg-inset/55 hover:border-border-base/18 hover:bg-bg-inset/80'"
                    @click="selectVersion(group.key, getItemKey(mod))"
                    @contextmenu.prevent.stop="openConflictItemMenu($event, group, mod)" >
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
                          {{ mod.name || mod.package_id || t('common.entity.unknown_mod', '未知模组') }}
                        </span>
                        <span class="rounded-full border px-2 py-0.5 text-[0.7rem] font-bold" :class="storeBadgeClass(mod.store)" >
                          {{ storeLabel(mod.store) }}
                        </span>
                        <span class="rounded-full border border-border-base/10 bg-bg-overlay/5 px-2 py-0.5 text-[0.7rem] font-mono text-text-dim">
                          {{ t('dialog.conflict.supported_version', '支持 {version}', { version: getHighestSupportedVersion(mod) || '?' }) }}
                        </span>
                        <span class="rounded-full border border-border-base/10 bg-bg-overlay/5 px-2 py-0.5 text-[0.7rem] font-mono text-text-dim">
                          v{{ mod.version || '?' }}
                        </span>
                        <span v-if="isWinner(group, mod)" class="rounded-full border border-accent-success/25 bg-accent-success/10 px-2 py-0.5 text-[0.7rem] font-black text-accent-success" >
                          {{ t('dialog.conflict.keep', '保留') }}
                        </span>
                      </div>
                      <div class="truncate font-mono text-xs text-text-dim" :title="mod.path">
                        {{ mod.path || '-' }}
                      </div>
                    </div>

                    <div class="flex shrink-0 items-center gap-1.5" @click.stop>
                      <button class="rounded-full border border-border-base/10 bg-bg-overlay/5 p-1.5 text-text-dim transition-colors hover:border-accent-cool/30 hover:text-accent-cool"
                        v-tooltip="t('tooltip.conflict.open_copy_folder', '打开该副本所在目录')" @click="appStore.openPath(mod.path)" >
                        <Folder class="size-3.5" />
                      </button>
                      <button v-if="canOpenModPage(mod)"
                        class="rounded-full border border-border-base/10 bg-bg-overlay/5 p-1.5 text-text-dim transition-colors hover:border-accent-primary/30 hover:text-accent-primary"
                        v-tooltip="t('tooltip.conflict.visit_copy_page', '访问该副本页面')" @click="openModPage(mod)" >
                        <ExternalLink class="size-3.5" />
                      </button>
                      <button class="rounded-full border border-border-base/10 bg-bg-overlay/5 p-1.5 text-text-dim transition-colors hover:border-border-base/18 hover:text-text-main"
                        v-tooltip="t('common.action.more_actions', '更多操作')" @click="openConflictItemMenu($event, group, mod)" >
                        <EllipsisVertical class="size-3.5" />
                      </button>

                      <div v-if="!isWinner(group, mod)" class="flex items-center gap-0.5 rounded-full border border-border-base/10 bg-bg-overlay/5 p-0.5">
                        <label class="cursor-pointer rounded-full px-2.5 py-1 text-xs font-bold transition-colors"
                          :class="actionMap[getItemKey(mod)] === 'disable'
                            ? 'bg-accent-warn text-on-accent-warn'
                            : 'text-text-dim hover:text-accent-warn'"
                          @click.stop v-tooltip="t('tooltip.conflict.disable_copy', '保留文件，只把该副本改为禁用状态')">
                          <input class="sr-only" type="radio" :name="`action-${getItemKey(mod)}`" :checked="actionMap[getItemKey(mod)] === 'disable'"
                            @change="setItemAction(group, mod, 'disable')" >
                          {{ t('common.action.deactivate', '禁用') }}
                        </label>
                        <label class="cursor-pointer rounded-full px-2.5 py-1 text-xs font-bold transition-colors"
                          :class="actionMap[getItemKey(mod)] === 'delete' ? 'bg-accent-danger text-on-accent-danger'  : 'text-text-dim hover:text-accent-danger'" 
                          @click.stop v-tooltip="t('tooltip.conflict.delete_copy', '将该副本移到回收站，不再保留文件')" >
                          <input class="sr-only" type="radio" :name="`action-${getItemKey(mod)}`" :checked="actionMap[getItemKey(mod)] === 'delete'" @change="setItemAction(group, mod, 'delete')" >
                          {{ t('common.action.delete', '删除') }}
                        </label>
                        <label class="cursor-pointer rounded-full px-2.5 py-1 text-xs font-bold transition-colors"
                          :class="actionMap[getItemKey(mod)] === 'skip'
                            ? 'bg-bg-overlay/20 text-text-main'
                            : 'text-text-dim hover:text-text-main'"
                          @click.stop v-tooltip="t('tooltip.conflict.skip_copy', '本次不处理该副本，重新扫描后可能仍会提示冲突')" >
                          <input class="sr-only" type="radio" :name="`action-${getItemKey(mod)}`" :checked="actionMap[getItemKey(mod)] === 'skip'" @change="setItemAction(group, mod, 'skip')" >
                          {{ t('common.action.skip', '跳过') }}
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
                <div class="text-xs font-black uppercase tracking-[0.16em] text-text-dim">{{ t('dialog.conflict.batch_title', '批量选择') }}</div>
                <p class="mt-1 text-xs leading-5 text-text-dim">
                  {{ t('dialog.conflict.batch_desc', '选范围，选保留谁，再选其余副本怎么处理。') }}
                </p>

                <div class="mt-3 space-y-2.5">
                  <CommonSelect v-model="batchRule.scope" :options="scopeOptions" :label="t('dialog.conflict.scope_label', '范围')" mini />
                  <CommonSelect v-model="batchRule.keepRule" :options="batchKeepOptions" :label="t('dialog.conflict.keep_label', '保留')" mini />
                  <CommonSelect v-model="batchRule.loserAction" :options="actionOptions" :label="t('dialog.conflict.loser_label', '其余')" mini />
                </div>

                <div class="mt-3 flex flex-wrap gap-1.5 text-xs">
                  <button class="rounded-full border border-accent-primary/24 bg-accent-primary/10 px-3 py-1 font-bold text-accent-primary transition-colors hover:bg-accent-primary/16"
                    v-tooltip="t('tooltip.conflict.apply_batch', '按当前范围、保留规则和处理方式，一次性应用到所有目标冲突组')" @click="applyBatchRule" >
                    {{ t('dialog.conflict.apply_batch', '应用选择条件') }}
                  </button>
                  <button class="rounded-full border border-accent-success/24 bg-accent-success/10 px-3 py-1 font-bold text-accent-success transition-colors hover:bg-accent-success/16"
                    v-tooltip="t('tooltip.conflict.restore_recommended', '恢复系统推荐方案：优先保留更可能实际生效的副本，其余副本改为禁用')" @click="restoreRecommended" >
                    {{ t('dialog.conflict.restore_recommended', '恢复默认') }}
                  </button>
                  <button class="rounded-full border border-accent-warn/20 bg-accent-warn/10 px-3 py-1 font-bold text-accent-warn transition-colors hover:bg-accent-warn/16"
                    v-tooltip="t('tooltip.conflict.disable_scope', '把当前范围内所有未保留副本统一改为禁用')" @click="setLoserActionForScope('disable')" >
                    {{ t('dialog.conflict.disable_scope', '当前范围全禁用') }}
                  </button>
                  <button class="rounded-full border border-border-base/10 bg-bg-overlay/5 px-3 py-1 font-bold text-text-dim transition-colors hover:text-accent-danger"
                    v-tooltip="t('tooltip.conflict.delete_scope', '把当前范围内所有未保留副本统一移到回收站')" @click="setLoserActionForScope('delete')" >
                    {{ t('dialog.conflict.delete_scope', '当前范围全删除') }}
                  </button>
                </div>
              </section>

              <section class="modal-section p-3 text-xs leading-5 text-text-dim">
                <div class="flex flex-wrap gap-x-2 gap-y-1">
                  <span>{{ t('dialog.conflict.scope_group_count', '当前范围 {count} 组', { count: scopedGroups.length }) }}</span>
                  <span>{{ t('dialog.conflict.badge.pending', '待处理 {count}', { count: countPendingForScope }) }}</span>
                  <span class="text-accent-warn">{{ t('dialog.conflict.badge.disable', '禁用 {count}', { count: countDisableForScope }) }}</span>
                  <span class="text-accent-danger">{{ t('dialog.conflict.badge.delete', '删除 {count}', { count: countDeleteForScope }) }}</span>
                  <span>{{ t('dialog.conflict.badge.skip', '跳过 {count}', { count: countSkipForScope }) }}</span>
                </div>
                <div class="mt-2">
                  {{ t('dialog.conflict.recommended_order', '推荐方案会优先保留实际更容易生效的副本：本地 > 管理器 > 工坊。') }}
                </div>
                <div v-if="summary.workshopDeleteCount > 0" class="mt-2 text-accent-warn">
                  {{ t('dialog.conflict.workshop_delete_warning', '删除工坊副本后，Steam 以后可能重新下载。') }}
                </div>
                <br>
                <div>
                  <p class="text-accent-tip">{{ t('dialog.conflict.soft_note', '对于共存模组（位于不同目录），游戏本身会优先加载本地目录版本。') }}</p><br>
                  <p class="text-accent-warn">{{ t('dialog.conflict.hard_note', '对于冲突模组（位于同一目录），游戏本身会选择一个加载，因各种因素下加载的版本可能不是最正确的，建议手动选择保留正确项，其余禁用或删除，确保加载正确。') }}</p>
                </div>
              </section>

              <section v-if="submitFeedback" class="rounded-2xl border p-3 text-xs"
                :class="submitFeedback.kind === 'error'
                  ? 'border-accent-danger/24 bg-accent-danger/10 text-accent-danger'
                  : 'border-accent-warn/24 bg-accent-warn/10 text-accent-warn'" >
                <div class="font-black">
                  {{ submitFeedback.kind === 'error' ? t('dialog.conflict.feedback_error', '处理失败') : t('dialog.conflict.feedback_warning', '处理提示') }}
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
            {{ t('dialog.conflict.footer_delete_disable_desc', '选择删除将直接移除文件至回收站，操作不可逆。禁用则会通过修改加载文件(About.xml)名称，让游戏无法检测，保留文件。') }}
            <div class="text-accent-warn">{{ t('dialog.conflict.footer_workshop_warning', '注意：直接删除创意工坊模组后，Steam 可能会重新下载。') }}
              <span class="text-accent-warning">{{ t('dialog.conflict.footer_disabled_hint', '禁用模组后可以在 库存枢纽 中对应列表筛选“已禁用”查看或解禁。') }}</span>
            </div>
            
          </div>
          <div class="flex shrink-0 items-center gap-2">
            <button class="rounded-xl border border-border-base/10 bg-bg-overlay/5 px-4 py-2 text-xs font-bold text-text-dim transition-colors hover:border-border-base/18 hover:text-text-main"
              v-tooltip="t('tooltip.conflict.defer', '关闭弹窗，暂不处理这些冲突')" @click="visible = false"
            >
              {{ t('dialog.conflict.defer', '稍后处理') }}
            </button>
            <button class="rounded-xl bg-accent-primary px-4 py-2 text-xs font-black text-on-accent-primary transition-colors hover:bg-accent-primary/85 disabled:cursor-not-allowed disabled:opacity-50"
              :disabled="processing" v-tooltip="t('tooltip.conflict.submit', '执行当前配置的禁用/删除操作，并在完成后自动重新扫描')" @click="submit"
            >
              {{ processing ? t('common.status.processing_dots', '处理中...') : t('dialog.conflict.submit', '执行处理') }}
            </button>
          </div>
        </div>
  </CommonModalShell>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { useToast } from 'vue-toastification'
import { Check, EllipsisVertical, ExternalLink, Folder, FolderInput, X, XCircle } from 'lucide-vue-next'
import CommonSwitch from '../../shared/components/input/CommonSwitch.vue'
import CommonSelect from '../../shared/components/input/CommonSelect.vue'
import CommonModalShell from '../../shared/components/modal/CommonModalShell.vue'
import { useContextMenuStore } from '../../shared/components/context-menu/contextMenuStore'
import { useAppStore } from '../../app/stores/appStore'
import { useModStore } from '../mod/stores/modStore'
import { useConfirmStore } from '../../shared/components/modal/confirmStore'
import { buildModExternalMenuItem, buildModInfoCopyMenuItem, normalizeModMenuSource } from '../mod/lib/modContextMenuItems'
import { toUserMessage } from '../../shared/lib/common'
import { getStoreTypeLabel } from '../../shared/lib/constants'
import { getCurrentLocale, t } from '../../shared/i18n'

const appStore = useAppStore()
const modStore = useModStore()
const confirmStore = useConfirmStore()
const contextMenuStore = useContextMenuStore()
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

const scopeOptions = computed(() => [
  { value: 'all', label: t('dialog.conflict.scope.all', '全部冲突'), desc: t('dialog.conflict.scope.all_desc', '同时处理硬冲突和版本共存。') },
  { value: 'hard', label: t('dialog.conflict.scope.hard', '只选硬冲突'), desc: t('dialog.conflict.scope.hard_desc', '只处理同级目录里的重复包 ID。') },
  { value: 'soft', label: t('dialog.conflict.scope.soft', '只选共存'), desc: t('dialog.conflict.scope.soft_desc', '只处理不同目录间的同包 ID 共存。') },
])

const batchKeepOptions = computed(() => [
  { value: 'recommended', label: t('dialog.conflict.keep_rule.recommended', '默认推荐'), desc: t('dialog.conflict.keep_rule.recommended_desc', '优先保留更可能实际生效的副本。') },
  { value: 'prefer_local', label: t('dialog.conflict.keep_rule.prefer_local', '保留本地副本'), desc: t('dialog.conflict.keep_rule.prefer_local_desc', '如果有本地副本，优先保留它。') },
  { value: 'prefer_self', label: t('dialog.conflict.keep_rule.prefer_self', '保留管理器副本'), desc: t('dialog.conflict.keep_rule.prefer_self_desc', '如果有管理器副本，优先保留它。') },
  { value: 'prefer_workshop', label: t('dialog.conflict.keep_rule.prefer_workshop', '保留工坊副本'), desc: t('dialog.conflict.keep_rule.prefer_workshop_desc', '如果有工坊副本，优先保留它。') },
  { value: 'latest_modified', label: t('dialog.conflict.keep_rule.latest_modified', '保留最新修改的'), desc: t('dialog.conflict.keep_rule.latest_modified_desc', '优先保留最近改动过的副本。') },
  { value: 'earliest_modified', label: t('dialog.conflict.keep_rule.earliest_modified', '保留最早修改的'), desc: t('dialog.conflict.keep_rule.earliest_modified_desc', '优先保留修改时间更早的副本。') },
  { value: 'latest_created', label: t('dialog.conflict.keep_rule.latest_created', '保留最新创建的'), desc: t('dialog.conflict.keep_rule.latest_created_desc', '优先保留新建时间更晚的副本。') },
  { value: 'earliest_created', label: t('dialog.conflict.keep_rule.earliest_created', '保留最早创建的'), desc: t('dialog.conflict.keep_rule.earliest_created_desc', '优先保留创建时间更早的副本。') },
  { value: 'highest_supported_version', label: t('dialog.conflict.keep_rule.highest_supported_version', '保留支持版本更高的'), desc: t('dialog.conflict.keep_rule.highest_supported_version_desc', '优先保留支持 RimWorld 版本更高的副本。') },
  { value: 'highest_mod_version', label: t('dialog.conflict.keep_rule.highest_mod_version', '保留模组版本更高的'), desc: t('dialog.conflict.keep_rule.highest_mod_version_desc', '优先保留模组自身版本号更高的副本。') },
  { value: 'shortest_path', label: t('dialog.conflict.keep_rule.shortest_path', '保留路径更短的'), desc: t('dialog.conflict.keep_rule.shortest_path_desc', '优先保留路径更短的副本。') },
  { value: 'longest_path', label: t('dialog.conflict.keep_rule.longest_path', '保留路径更长的'), desc: t('dialog.conflict.keep_rule.longest_path_desc', '优先保留路径更长的副本。') },
])

const actionOptions = computed(() => [
  { value: 'disable', label: t('dialog.conflict.action.disable_all', '其余都禁用'), desc: t('dialog.conflict.action.disable_all_desc', '其它副本改为禁用。') },
  { value: 'delete', label: t('dialog.conflict.action.delete_all', '其余都删除'), desc: t('dialog.conflict.action.delete_all_desc', '其它副本移到回收站。') },
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
  if (['local', 'self', 'workshop'].includes(value)) return getStoreTypeLabel(value)
  return store || t('common.store.unknown', '未知')
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
  return new Date(timestamp).toLocaleString(getCurrentLocale(), { hour12: false })
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
  let skipCount = 0
  groups.forEach((group) => {
    const keepKey = selections[group.key]
    group.items.forEach((item) => {
      if (getItemKey(item) === keepKey) return
      const action = actionMap[getItemKey(item)] || 'disable'
      if (action === 'skip') {
        skipCount += 1
        return
      }
      pending += 1
      if (action === 'delete') deleteCount += 1
      else disable += 1
    })
  })
  return { pending, disable, deleteCount, skipCount }
}

const summary = computed(() => {
  const result = {
    groupCount: localGroups.value.length,
    hardCount: 0,
    softCount: 0,
    pendingCount: 0,
    disableCount: 0,
    deleteCount: 0,
    skipCount: 0,
    workshopDeleteCount: 0,
  }

  localGroups.value.forEach((group) => {
    if (group._type === 'hard') result.hardCount += 1
    else result.softCount += 1

    const keepKey = selections[group.key]
    group.items.forEach((item) => {
      if (getItemKey(item) === keepKey) return
      const action = actionMap[getItemKey(item)] || 'disable'
      if (action === 'skip') {
        result.skipCount += 1
        return
      }
      result.pendingCount += 1
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
const countSkipForScope = computed(() => scopedSummary.value.skipCount)

const isWinner = (group, mod) => selections[group.key] === getItemKey(mod)

const getModTooltip = (mod) => {
  return [
    t('tooltip.conflict.mod_source', '来源：{value}', { value: storeLabel(mod.store) }),
    t('tooltip.conflict.mod_version', '模组版本：{value}', { value: mod.version || '-' }),
    t('tooltip.conflict.highest_supported_version', '最高支持版本：{value}', { value: getHighestSupportedVersion(mod) || '-' }),
    t('tooltip.conflict.supported_versions', '支持版本列表：{value}', { value: joinSupportedVersions(mod) || '-' }),
    t('tooltip.conflict.created_time', '创建时间：{value}', { value: formatTime(mod.file_create_time || mod.ctime) }),
    t('tooltip.conflict.modified_time', '修改时间：{value}', { value: formatTime(mod.file_modify_time || mod.mtime) }),
    t('tooltip.conflict.workshop_id', '工坊 ID：{value}', { value: mod.workshop_id || '-' }),
    t('tooltip.conflict.path', '路径：{value}', { value: mod.path || '-' }),
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

const canLocalize = (mod) => !!mod?.path_hash && !!mod?.workshop_id && ['workshop', 'self'].includes(normalizeStore(mod.store))
const getLocalizeLabel = (mod) => mod?.is_coexistence ? t('dialog.conflict.menu.sync_local_coexistence', '同步本地共存') : t('dialog.conflict.menu.localize_coexistence', '本地化共存')
const canUnsubscribe = (mod) => !!mod?.workshop_id && !!mod?.path_hash && normalizeStore(mod.store) === 'workshop'
const canOpenModPage = (mod) => {
  const info = normalizeModMenuSource(mod)
  return !!info.url || !!info.workshopId
}
const openModPage = (mod) => {
  const info = normalizeModMenuSource(mod)
  if (info.url) {
    appStore.openUrl(info.url)
    return
  }
  if (info.workshopId) appStore.openSteamWorkshopById(info.workshopId)
}
const openConflictItemMenu = (event, group, mod) => {
  event?.preventDefault?.()
  event?.stopPropagation?.()
  contextMenuStore.open(event, [
    buildModInfoCopyMenuItem(mod, { label: t('ui.mod.action.copy_info', '复制模组信息') }),
    buildModExternalMenuItem(mod, appStore, { label: t('common.action.visit_page', '访问页面') }),
    { divider: true },
    { label: t('dialog.conflict.menu.open_folder', '打开目录'), icon: Folder, disabled: !mod?.path, action: () => appStore.openPath(mod.path) },
    { divider: true },
    { label: getLocalizeLabel(mod), icon: FolderInput, disabled: !canLocalize(mod), action: () => handleLocalize(mod) },
    { label: t('dialog.conflict.menu.unsubscribe_delete', '退订并删除'), icon: XCircle, level: 'danger', disabled: !canUnsubscribe(mod), action: () => handleUnsubscribe(mod) },
  ], { group, mod })
}

const applyBatchRule = () => {
  if (!scopedGroups.value.length) {
    toast.info(t('toast.conflict.empty_scope', '当前作用范围内没有可处理的冲突组'))
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
  toast.success(t('toast.conflict.batch_applied', '已按条件处理 {count} 组冲突', { count: scopedGroups.value.length }))
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
  toast.success(t('toast.conflict.recommended_restored', '已恢复推荐处理方案'))
}

const setLoserActionForScope = (action) => {
  if (!scopedGroups.value.length) {
    toast.info(t('toast.conflict.empty_scope', '当前作用范围内没有可处理的冲突组'))
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
      const action = actionMap[getItemKey(item)] || 'disable'
      if (action === 'skip') return
      operations.push({
        action,
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
    toast.info(t('toast.conflict.no_operations', '当前没有需要处理的副本'))
    visible.value = false
    return
  }

  const confirmMessage = [
    t('dialog.conflict.confirm.summary', '将处理 {groupCount} 组冲突中的 {operationCount} 个未保留副本。', { groupCount: summary.value.groupCount, operationCount: operations.length }),
    t('dialog.conflict.confirm.action_counts', '禁用 {disableCount} 个，删除 {deleteCount} 个。', { disableCount: summary.value.disableCount, deleteCount: summary.value.deleteCount }),
    summary.value.workshopDeleteCount > 0
      ? t('dialog.conflict.confirm.workshop_delete', '其中 {count} 个工坊副本会被删除，Steam 后续可能重新下载。', { count: summary.value.workshopDeleteCount })
      : null,
    summary.value.skipCount > 0
      ? t('dialog.conflict.confirm.skip_count', '已跳过 {count} 个副本，本次不会处理。', { count: summary.value.skipCount })
      : null,
    t('dialog.conflict.confirm.rescan_notice', '提交后会立即刷新数据库并重新扫描文件系统，剩余未成功项会在新一轮扫描中重新提示。'),
  ].filter(Boolean).join('\n')

  const deleteCount = summary.value.deleteCount || 0
  const confirmResult = deleteCount > 0
    ? await confirmStore.confirmDeleteAction(
        t('dialog.conflict.confirm.title', '确认处理冲突'),
        confirmMessage,
        {
          confirmText: t('dialog.conflict.confirm.confirm_text', '确认执行'),
          cancelText: t('dialog.conflict.confirm.cancel_text', '再检查一下'),
          trashOptionText: t('dialog.conflict.confirm.trash_option', '删除副本并移入回收站'),
          forceOptionText: t('dialog.conflict.confirm.force_option', '强制彻底删除副本'),
          deleteOptionsHint: t('dialog.conflict.confirm.delete_hint', '该选项仅影响本次选择为“删除”的副本；禁用项仍只会调整文件状态。'),
        }
      )
    : await confirmStore.confirmAction(
        t('dialog.conflict.confirm.title', '确认处理冲突'),
        confirmMessage,
        {
          type: 'warning',
          confirmText: t('dialog.conflict.confirm.confirm_text', '确认执行'),
          cancelText: t('dialog.conflict.confirm.cancel_text', '再检查一下'),
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
        toast.success(t('toast.conflict.resolved_success', '已处理 {count} 项冲突副本，正在重新扫描。', { count: resultStats.success_count || operations.length }))
      } else {
        toast.warning(t('toast.conflict.resolved_partial', '已处理 {successCount} 项，{errorCount} 项失败；剩余问题会在重新扫描后重新提示。', { successCount: resultStats.success_count || 0, errorCount: resultStats.error_count || 0 }), {
          timeout: 9000,
        })
      }

      await appStore.requestModScan()
      return
    }

    const failedPaths = Array.isArray(res?.data?.failed_paths) ? res.data.failed_paths : []
    const userMessage = toUserMessage(res?.message, t('toast.conflict.resolve_failed', '冲突处理失败。可能是目标文件已被占用、路径权限不足或列表状态已变化，请重新扫描后再试。'))
    submitFeedback.value = {
      kind: 'error',
      message: userMessage,
      details: failedPaths.slice(0, 3),
    }
    toast.error(userMessage)
  } catch (error) {
    const message = toUserMessage(error?.message || error, t('toast.conflict.resolve_exception', '冲突处理请求失败。请确认后端服务仍在运行，并重新扫描后再试。'))
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
  await modStore.localizeMods([mod.path_hash], store, { existingCount: mod?.is_coexistence ? 1 : 0 })
}

const handleUnsubscribe = async (mod) => {
  if (!mod?.workshop_id || !mod?.path_hash) return
  const ok = await appStore.unsubscribeWorkshopIds([mod.workshop_id], [mod.path_hash])
  if (ok) await appStore.requestModScan({ preserveListState: true, forceCoreRefresh: true })
}
</script>
