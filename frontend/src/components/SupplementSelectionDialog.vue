<template>
  <CommonModalShell :show="supplementStore.isVisible" :show-header="false" size="custom" :z-index="9999" accent="tip" panel-class="w-[62rem] max-h-[86vh] max-w-[94vw]" content-class="h-full flex flex-col"
    @close="supplementStore.cancel()" >
          <div class="absolute inset-x-0 top-0 h-[0.0625rem] bg-linear-to-r from-transparent via-accent-tip to-transparent opacity-80"></div>
          <div class="absolute -top-20 right-10 h-44 w-44 rounded-full bg-accent-tip/10 blur-[4.5rem] pointer-events-none"></div>

          <div class="relative z-10 flex items-start justify-between gap-3 border-b border-border-base/5 px-5 py-4">
            <div class="min-w-0">
              <h3 class="text-lg font-black tracking-wide text-text-main">{{ supplementStore.state.title }}</h3>
              <p v-if="supplementStore.state.message" class="mt-1.5 max-w-4xl text-[0.6875rem] leading-5 text-text-dim">
                {{ supplementStore.state.message }}
              </p>
            </div>
            <button class="modal-close-button" aria-label="关闭" @click="supplementStore.cancel()" >
              <X class="size-4" />
            </button>
          </div>

          <div class="toolbar-surface relative z-10 flex flex-wrap items-center justify-between gap-2 px-5 py-2.5">
            <div class="flex flex-wrap items-center gap-1.5 text-[0.6875rem] text-text-dim">
              <span class="rounded-full border border-accent-tip/25 bg-accent-tip/12 px-3 py-1 font-bold text-accent-tip">
                {{ supplementStore.selectedCount }} / {{ supplementStore.totalCount }} 已选
              </span>
              <span v-if="supplementStore.state.summary.dangerCount > 0" class="rounded-full border border-accent-danger/25 bg-accent-danger/12 px-3 py-1 font-bold text-accent-danger" >
                {{ supplementStore.state.summary.dangerCount }} 项必要
              </span>
              <span v-if="supplementStore.state.summary.warnCount > 0" class="rounded-full border border-accent-warn/25 bg-accent-warn/12 px-3 py-1 font-bold text-accent-warn" >
                {{ supplementStore.state.summary.warnCount }} 项建议
              </span>
              <span v-if="supplementStore.state.summary.infoCount > 0" class="rounded-full border border-border-base/10 bg-bg-overlay/5 px-3 py-1 font-bold text-text-dim" >
                {{ supplementStore.state.summary.infoCount }} 项可选
              </span>
            </div>
            <div class="flex flex-wrap items-center gap-1.5">
              <button class="rounded-lg border border-border-base/10 bg-bg-overlay/5 px-2.5 py-1.5 text-[0.6875rem] font-bold text-text-dim transition-all hover:bg-bg-overlay/10 hover:text-text-main"
                @click="supplementStore.selectAll()" >
                全选
              </button>
              <button class="rounded-lg border border-accent-danger/18 bg-accent-danger/10 px-2.5 py-1.5 text-[0.6875rem] font-bold text-accent-danger transition-all hover:bg-accent-danger/16"
                @click="supplementStore.selectRequiredOnly()" >
                仅选必要
              </button>
              <button class="rounded-lg border border-border-base/10 bg-bg-overlay/5 px-2.5 py-1.5 text-[0.6875rem] font-bold text-text-dim transition-all hover:bg-bg-overlay/10 hover:text-text-main"
                @click="supplementStore.clearSelection()" >
                全部清空
              </button>
            </div>
          </div>

          <div class="relative z-10 flex-1 overflow-y-auto px-5 py-4">
            <div class="space-y-3.5">
              <section v-for="group in supplementStore.state.groups" :key="group.key" class="modal-section" >
                <div class="flex flex-wrap items-start justify-between gap-2 border-b border-border-base/5 px-4 py-3">
                  <div class="min-w-0">
                    <div class="flex flex-wrap items-center gap-1.5">
                      <h4 class="text-sm font-black tracking-wide text-text-main">{{ group.title }}</h4>
                      <span class="rounded-full border px-2 py-0.5 text-[0.625rem] font-black uppercase tracking-wider"
                        :class="severityClass(group.severity)" >
                        {{ severityLabel(group.severity) }}
                      </span>
                      <span class="rounded-full border border-border-base/10 bg-bg-overlay/5 px-2 py-0.5 text-[0.625rem] font-bold text-text-dim">
                        {{ group.rows.length }} 项
                      </span>
                    </div>
                    <p v-if="group.description" class="mt-1 text-[0.625rem] leading-4 text-text-dim">{{ group.description }}</p>
                  </div>
                </div>

                <div class="space-y-2 px-3 py-3">
                  <article v-for="row in group.rows" :key="row.id" class="rounded-xl border bg-bg-surface/80 px-3 py-2"
                    :class="rowContainerClass(row)" >
                    <div v-if="row.kind === 'choice'" class="space-y-2">
                      <div class="flex items-start gap-2">
                        <div class="mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full border border-border-base/10 bg-bg-overlay/5 text-[0.625rem] font-black text-text-dim">
                          !
                        </div>
                        <div class="min-w-0 flex-1">
                          <div class="flex flex-wrap items-center gap-1.5">
                            <span class="truncate text-[0.8125rem] font-black text-text-main">{{ row.title }}</span>
                            <span class="rounded-full border px-2 py-0.5 text-[0.625rem] font-black uppercase tracking-wider" :class="severityClass(row.severity)">
                              {{ severityLabel(row.severity) }}
                            </span>
                          </div>
                          <p v-if="row.reason" class="mt-1 text-[0.6875rem] leading-4 text-text-dim">{{ row.reason }}</p>
                          <p v-if="row.detail" class="mt-1 text-[0.625rem] leading-4 text-text-disabled" :title="row.detail">{{ row.detail }}</p>
                        </div>
                      </div>

                      <div class="grid gap-1.5 pl-6">
                        <label class="modal-section-subtle flex cursor-pointer items-start gap-2 px-2.5 py-2 transition-colors hover:bg-bg-overlay/5">
                          <input type="radio" :name="row.id" class="mt-0.5 h-3.5 w-3.5 accent-text-dim"
                            :checked="supplementStore.getChoiceSelection(row.id) === ''" @change="supplementStore.chooseRootOption(row.id, '')" >
                          <div class="min-w-0 flex-1">
                            <div class="text-[0.75rem] font-bold text-text-main">暂不启用</div>
                            <p class="mt-0.5 text-[0.625rem] leading-4 text-text-dim">保持当前状态。</p>
                          </div>
                        </label>

                        <label v-for="option in row.options" :key="option.id" class="modal-section-subtle flex cursor-pointer items-start gap-2 px-2.5 py-2 transition-colors hover:bg-bg-overlay/5" >
                          <input type="radio" :name="row.id" class="mt-0.5 h-3.5 w-3.5 shrink-0 accent-accent-primary"
                           
                            :checked="supplementStore.getChoiceSelection(row.id) === option.id" @change="supplementStore.chooseRootOption(row.id, option.id)" >
                          <div class="min-w-0 flex-1">
                            <div class="flex flex-wrap items-center gap-1.5">
                              <span class="truncate text-[0.75rem] font-bold text-text-main">{{ option.title }}</span>
                              <span v-for="relationLabel in option.relationLabels || []" :key="relationLabel" class="rounded-full border border-border-base/10 bg-bg-overlay/5 px-2 py-0.5 text-[0.625rem] font-bold text-text-dim" >
                                {{ relationLabel }}
                              </span>
                              <span v-if="option.versionInfo" class="rounded-full border px-2 py-0.5 text-[0.625rem] font-bold" :class="versionClass(option.versionInfo?.tone)" >
                                {{ option.versionInfo?.label }}
                              </span>
                            </div>
                            <p v-if="option.detail" class="mt-0.5 text-[0.625rem] leading-4 text-text-dim">{{ option.detail }}</p>
                          </div>
                        </label>
                      </div>
                    </div>

                    <div v-else class="flex items-start gap-2">
                      <label class="mt-0.5 flex shrink-0 cursor-pointer items-center">
                        <input type="checkbox" class="h-3.5 w-3.5 accent-accent-warn" :checked="supplementStore.isRootChecked(row.id)"
                          @change="supplementStore.toggleRoot(row.id, $event.target.checked)" >
                      </label>

                      <div class="min-w-0 flex-1">
                        <div class="flex flex-wrap items-center gap-1.5">
                          <span class="truncate text-[0.8125rem] font-black text-text-main">{{ row.title }}</span>
                          <span class="rounded-full border px-2 py-0.5 text-[0.625rem] font-black uppercase tracking-wider" :class="severityClass(row.severity)">
                            {{ severityLabel(row.severity) }}
                          </span>
                          <span v-for="relationLabel in row.relationLabels || []" :key="relationLabel" class="rounded-full border border-border-base/10 bg-bg-overlay/5 px-2 py-0.5 text-[0.625rem] font-bold text-text-dim" >
                            {{ relationLabel }}
                          </span>
                          <span v-if="row.versionInfo" class="rounded-full border px-2 py-0.5 text-[0.625rem] font-bold" :class="versionClass(row.versionInfo?.tone)" >
                            {{ row.versionInfo?.label }}
                          </span>
                        </div>
                        <p v-if="row.reason" class="mt-1 text-[0.6875rem] leading-4 text-text-dim">{{ row.reason }}</p>
                        <p v-if="row.detail" class="mt-1 text-[0.625rem] leading-4 text-text-disabled" :title="row.detail">{{ row.detail }}</p>
                      </div>
                    </div>
                  </article>
                </div>
              </section>
            </div>
          </div>

          <div class="modal-footer relative z-10 flex items-center justify-end gap-2.5 px-5 py-3.5">
            <button class="rounded-lg border border-border-base/10 bg-bg-overlay/5 px-4 py-2 text-[0.6875rem] font-bold text-text-dim transition-all hover:bg-bg-overlay/10 hover:text-text-main"
              @click="supplementStore.cancel()" >
              {{ supplementStore.state.cancelText }}
            </button>
            <button v-if="supplementStore.state.continueText"
              class="rounded-lg bg-accent-danger px-5 py-2 text-[0.6875rem] font-black text-on-accent-danger shadow-[0_0.625rem_1.875rem_rgba(var(--rgb-accent-danger),0.28)] transition-all hover:brightness-105 active:scale-95"
              @click="supplementStore.continueCurrentAction()" >
              {{ supplementStore.state.continueText }}
            </button>
            <button class="rounded-lg bg-accent-tip px-5 py-2 text-[0.6875rem] font-black text-on-accent-tip shadow-[0_0.625rem_1.875rem_rgba(var(--rgb-accent-warn),0.28)] transition-all hover:brightness-105 active:scale-95"
              @click="supplementStore.confirm()" >
              {{ supplementStore.state.confirmText }}
            </button>
          </div>
  </CommonModalShell>
</template>

<script setup>
import { X } from 'lucide-vue-next'
import { useSupplementStore } from '../stores/supplementStore'
import CommonModalShell from './common/CommonModalShell.vue'

const supplementStore = useSupplementStore()

const severityLabel = (severity = 'info') => (
  supplementStore.severityMeta[severity]?.label || '可选'
)

const severityClass = (severity = 'info') => {
  if (severity === 'danger') {
    return 'border-accent-danger/30 bg-accent-danger/12 text-accent-danger'
  }
  if (severity === 'warn') {
    return 'border-accent-warn/25 bg-accent-warn/12 text-accent-warn'
  }
  return 'border-border-base/10 bg-bg-overlay/5 text-text-dim'
}

const versionClass = (tone = 'muted') => {
  if (tone === 'success') return 'border-accent-success/25 bg-accent-success/12 text-accent-success'
  if (tone === 'danger') return 'border-accent-danger/25 bg-accent-danger/12 text-accent-danger'
  return 'border-border-base/10 bg-bg-overlay/5 text-text-dim'
}

const rowContainerClass = (row) => (
  row?.severity === 'danger'
    ? 'border-accent-danger/18'
    : row?.severity === 'warn'
      ? 'border-accent-warn/18'
      : 'border-border-base/10'
)
</script>
