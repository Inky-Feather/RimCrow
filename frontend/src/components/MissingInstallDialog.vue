<template>
  <CommonModalShell :show="missingInstallStore.isVisible" :show-header="false" size="custom" :z-index="9999" accent="primary"
    panel-class="w-[80vw] max-h-[86vh] max-w-[94vw]" content-class="h-full flex flex-col"
    @close="missingInstallStore.close()" >
    <div class="absolute inset-x-0 top-0 h-px bg-linear-to-r from-transparent via-accent-primary to-transparent opacity-80"></div>

    <div class="relative z-10 flex items-start justify-between gap-3 border-b border-border-base/5 px-5 py-4">
      <div class="min-w-0">
        <h3 class="text-lg font-black tracking-wide text-text-main">{{ missingInstallStore.state.title }}</h3>
        <p class="mt-1.5 max-w-4xl text-[0.6875rem] leading-5 text-text-dim">
          {{ missingInstallStore.state.message }}
        </p>
      </div>
      <button class="modal-close-button" aria-label="关闭" @click="missingInstallStore.close(false)" >
        <X class="size-4" />
      </button>
    </div>

    <div class="toolbar-surface relative z-10 flex flex-wrap items-center justify-between gap-2 px-5 py-2.5">
      <div class="flex flex-wrap items-center gap-1.5 text-[0.6875rem] text-text-dim">
        <span v-if="hasActionableRows" class="rounded-full border border-accent-primary/25 bg-accent-primary/12 px-3 py-1 font-bold text-accent-primary">
          {{ missingInstallStore.selectedCount }} / {{ missingInstallStore.totalCount }} 已选
        </span>
        <span v-if="missingInstallStore.state.summary.dangerTotal > 0" class="rounded-full border border-accent-danger/25 bg-accent-danger/12 px-3 py-1 font-bold text-accent-danger">
          必要 {{ missingInstallStore.state.summary.dangerTotal }}
        </span>
        <span v-if="missingInstallStore.state.summary.warnTotal > 0" class="rounded-full border border-accent-warn/25 bg-accent-warn/12 px-3 py-1 font-bold text-accent-warn">
          建议 {{ missingInstallStore.state.summary.warnTotal }}
        </span>
        <span v-if="missingInstallStore.state.summary.infoTotal > 0" class="rounded-full border border-border-base/10 bg-bg-overlay/5 px-3 py-1 font-bold text-text-dim">
          可选 {{ missingInstallStore.state.summary.infoTotal }}
        </span>
        <span v-if="missingInstallStore.state.summary.unknownTotal > 0" class="rounded-full border border-accent-danger/25 bg-accent-danger/12 px-3 py-1 font-bold text-accent-danger">
          未知 {{ missingInstallStore.state.summary.unknownTotal }}
        </span>
      </div>
      <div v-if="hasActionableRows" class="flex flex-wrap items-center gap-1.5">
        <button class="rounded-lg border border-border-base/10 bg-bg-overlay/5 px-2.5 py-1.5 text-[0.6875rem] font-bold text-text-dim transition-all hover:bg-bg-overlay/10 hover:text-text-main"
          :disabled="missingInstallStore.isActionPending" @click="missingInstallStore.selectAll()" >
          全选
        </button>
        <button class="rounded-lg border border-border-base/10 bg-bg-overlay/5 px-2.5 py-1.5 text-[0.6875rem] font-bold text-text-dim transition-all hover:bg-bg-overlay/10 hover:text-text-main"
          :disabled="missingInstallStore.isActionPending" @click="missingInstallStore.clearSelection()" >
          清空
        </button>
      </div>
    </div>

    <div class="relative z-10 flex-1 overflow-y-auto px-5 py-4">
      <div class="space-y-3.5">
        <section v-if="isUnknownOnlyMode" class="modal-section px-4 py-4" >
          <h4 class="text-sm font-black tracking-wide text-text-main">只有未知项</h4>
          <p class="mt-1.5 text-[0.6875rem] leading-5 text-text-dim">这些项目暂时无法直接处理。</p>
        </section>
        <section v-if="hasUnknownItems" class="rounded-2xl border border-accent-danger/18 bg-accent-danger/4" >
          <div class="flex flex-wrap items-start justify-between gap-2 border-b border-accent-danger/12 px-4 py-3">
            <div class="min-w-0">
              <div class="flex flex-wrap items-center gap-1.5">
                <h4 class="text-sm font-black tracking-wide text-text-main">未知项</h4>
                <span class="rounded-full border border-accent-danger/20 bg-accent-danger/12 px-2 py-0.5 text-[0.625rem] font-bold text-accent-danger">
                  {{ missingInstallStore.state.unknownItems.length }} 项
                </span>
              </div>
              <p class="mt-1 text-[0.625rem] leading-4 text-text-dim">这些项目暂时找不到可用来源或依赖目标。</p>
            </div>
          </div>

          <div class="space-y-2 px-3 py-3">
            <article v-for="item in missingInstallStore.state.unknownItems" :key="item.id" class="flex items-start gap-2 rounded-xl border border-accent-danger/12 bg-bg-muted/40 px-3 py-2" >
              <div class="mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full border border-accent-danger/22 bg-accent-danger/10 text-[0.625rem] font-black text-accent-danger">
                !
              </div>
              <div class="min-w-0 flex-1">
                <div class="flex flex-wrap items-center gap-1.5">
                  <span class="truncate text-[0.8125rem] font-black text-text-main">{{ item.title }}</span>
                  <span v-for="reasonLabel in item.reasonLabels || []" :key="reasonLabel" class="rounded-full border border-border-base/10 bg-bg-overlay/5 px-2 py-0.5 text-[0.625rem] font-bold text-text-dim" >
                    {{ reasonLabel }}
                  </span>
                  <span v-if="item.canCleanup" class="rounded-full border border-accent-danger/20 bg-accent-danger/10 px-2 py-0.5 text-[0.625rem] font-bold text-accent-danger" >
                    可清理
                  </span>
                  <span v-if="item.unknownDependencyCount > 0" class="rounded-full border border-accent-danger/20 bg-accent-danger/10 px-2 py-0.5 text-[0.625rem] font-bold text-accent-danger" >
                    未知依赖 {{ item.unknownDependencyCount }}
                  </span>
                </div>
                <p v-if="item.detailLines?.length" class="mt-1 text-[0.625rem] leading-4 text-text-dim" >
                  {{ item.canCleanup ? '无效项' : '未知依赖' }}：{{ item.detailLines.join('、') }}
                </p>
              </div>
            </article>
          </div>
        </section>
        <section v-for="group in missingInstallStore.state.groups" :key="group.key" class="modal-section" >
          <div class="flex flex-wrap items-start justify-between gap-2 border-b border-border-base/5 px-4 py-3">
            <div class="min-w-0">
              <div class="flex flex-wrap items-center gap-1.5">
                <h4 class="text-sm font-black tracking-wide text-text-main">{{ group.title }}</h4>
                <span class="rounded-full border border-border-base/10 bg-bg-overlay/5 px-2 py-0.5 text-[0.625rem] font-bold text-text-dim">
                  {{ group.rows.length }} 项
                </span>
                <span v-if="group.key === 'missing_with_installed_replacement'" class="rounded-full border border-accent-primary/20 bg-accent-primary/10 px-2 py-0.5 text-[0.625rem] font-bold text-accent-primary" >
                  点击订阅或下载时会自动切换
                </span>
              </div>
              <p v-if="group.description" class="mt-1 text-[0.625rem] leading-4 text-text-dim">{{ group.description }}</p>
            </div>
          </div>

          <div class="space-y-2 px-3 py-3 bg-bg-deep/40 rounded-md">
            <article v-for="row in group.rows" :key="row.id" class="flex items-start gap-2 rounded-xl border border-border-base/10 bg-bg-muted px-3 py-2 transition-colors"
              :class="missingInstallStore.getSelectedSource(row) && missingInstallStore.isSelected(row.id) ? 'border-accent-primary/25 bg-accent-primary/5' : ''" >
              <label class="mt-0.5 flex shrink-0 cursor-pointer items-center">
                <input type="checkbox" class="h-3.5 w-3.5 accent-accent-primary" :checked="missingInstallStore.isSelected(row.id)"
                  @change="missingInstallStore.toggleRow(row.id, $event.target.checked)" >
              </label>

              <div class="min-w-0 flex-1">
                <div class="flex flex-wrap items-center gap-1.5">
                  <span class="truncate text-[0.8125rem] font-black text-text-main">{{ row.title }}</span>
                  <span v-for="reasonLabel in row.reasonLabels || []" :key="reasonLabel" class="rounded-full border border-border-base/10 bg-bg-overlay/5 px-2 py-0.5 text-[0.625rem] font-bold text-text-dim" >
                    {{ reasonLabel }}
                  </span>
                  <span v-if="row.choiceOptions?.length === 1" v-tooltip="missingInstallStore.getVersionTooltip(missingInstallStore.getRowVersionInfo(row))"
                    class="rounded-full border px-2 py-0.5 text-[0.625rem] font-bold" :class="versionBadgeClass(missingInstallStore.getRowVersionInfo(row))" >
                    {{ missingInstallStore.getRowVersionInfo(row).label }}
                  </span>
                  <span v-if="row.choiceOptions?.length === 1" class="rounded-full border border-accent-primary/20 bg-accent-primary/10 px-2 py-0.5 text-[0.625rem] font-bold text-accent-primary" >
                    {{ sourceLabel(missingInstallStore.getSelectedSource(row)) }}
                  </span>
                </div>
                <div v-if="row.choiceOptions?.length > 1" class="mt-2 space-y-2">
                  <p v-if="row.groupKey === 'missing_with_installed_replacement'" class="text-[0.625rem] leading-4 text-accent-primary/88" >
                    选中已安装替代后，点击订阅或下载时会自动替换当前缺失项。
                  </p>
                  <div v-for="choice in row.choiceOptions" :key="`${row.id}:${choice.id}`" class="flex w-full items-start gap-3 rounded-xl border px-3 py-2.5 text-left transition-all"
                    :class="missingInstallStore.getSelectedChoice(row)?.id === choice.id ? 'border-accent-primary/40 bg-accent-primary/3' : 'border-border-base/10 bg-bg-inset/55'" >
                    <button type="button" class="flex min-w-0 flex-1 items-start gap-3 text-left transition-all hover:brightness-110"
                      @click="missingInstallStore.setChoice(row.id, choice.id)" >
                      <span class="mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full border border-border-base/18">
                        <span class="h-2 w-2 rounded-full transition-opacity" :class="missingInstallStore.getSelectedChoice(row)?.id === choice.id ? 'bg-accent-primary opacity-100' : 'opacity-0'" ></span>
                      </span>

                      <div class="min-w-0 flex-1">
                        <div class="flex items-center justify-between gap-2">
                          <span class="truncate text-[0.75rem] font-black text-text-main">{{ choice.title }}</span>
                          <span class="shrink-0 rounded-full border border-border-base/10 bg-bg-overlay/5 px-2 py-0.5 text-[0.625rem] font-bold text-text-dim">
                            {{ choice.label }}
                          </span>
                        </div>
                        <div class="mt-1 flex flex-wrap items-center gap-1.5">
                          <span class="rounded-full border border-accent-primary/20 bg-accent-primary/10 px-2 py-0.5 text-[0.625rem] font-bold text-accent-primary">
                            {{ sourceLabel(choice.source) }}
                          </span>
                          <span v-tooltip="missingInstallStore.getVersionTooltip(choice.versionInfo)" class="rounded-full border px-2 py-0.5 text-[0.625rem] font-bold" :class="versionBadgeClass(choice.versionInfo)" >
                            {{ choice.versionInfo.label }}
                          </span>
                        </div>
                      </div>
                    </button>

                    <button class="shrink-0 rounded-xl border border-accent-primary/35 bg-accent-primary/10 px-3 py-1.5 text-[0.6875rem] font-black text-accent-primary transition-all hover:bg-accent-primary/18 hover:text-accent-cool"
                      @click.stop="missingInstallStore.openSource(choice.source)" >
                      访问来源
                    </button>
                  </div>
                </div>
              </div>

              <button v-if="row.choiceOptions?.length === 1 && missingInstallStore.getSelectedSource(row)"
                class="shrink-0 rounded-xl border border-accent-primary/35 bg-accent-primary/10 px-3 py-1.5 text-[0.6875rem] font-black text-accent-primary transition-all hover:bg-accent-primary/18 hover:text-accent-cool"
                @click="missingInstallStore.openSource(missingInstallStore.getSelectedSource(row))" >
                访问来源
              </button>
            </article>
          </div>
        </section>
      </div>
    </div>

    <div class="modal-footer relative z-10 flex items-center justify-end gap-2.5 px-5 py-3.5">
      <button class="rounded-lg border border-border-base/10 bg-bg-overlay/5 px-4 py-2 text-[0.6875rem] font-bold text-text-dim transition-all hover:bg-bg-overlay/10 hover:text-text-main disabled:cursor-not-allowed disabled:opacity-45 disabled:hover:bg-bg-overlay/5 disabled:hover:text-text-dim"
        :disabled="missingInstallStore.isActionPending" @click="missingInstallStore.close(false)" >
        {{ missingInstallStore.state.cancelText }}
      </button>
      <button v-if="missingInstallStore.state.cleanupText" :disabled="missingInstallStore.isActionPending"
        class="rounded-lg bg-accent-danger px-5 py-2 text-[0.6875rem] font-black text-on-accent-danger shadow-[0_0.625rem_1.875rem_rgba(var(--rgb-accent-danger),0.28)] transition-all hover:brightness-105 active:scale-95 disabled:cursor-not-allowed disabled:opacity-45 disabled:hover:brightness-100 disabled:active:scale-100"
        @click="missingInstallStore.cleanupUnknownItems()" >
        {{ missingInstallStore.state.cleanupText }}
      </button>
      <button v-if="missingInstallStore.state.disableRelatedText" :disabled="missingInstallStore.isActionPending"
        class="rounded-lg bg-accent-warn px-5 py-2 text-[0.6875rem] font-black text-on-accent-warn shadow-[0_0.625rem_1.875rem_rgba(var(--rgb-accent-secondary),0.28)] transition-all hover:brightness-105 active:scale-95 disabled:cursor-not-allowed disabled:opacity-45 disabled:hover:brightness-100 disabled:active:scale-100"
        @click="missingInstallStore.disableRelatedOwners()" >
        {{ missingInstallStore.state.disableRelatedText }}
      </button>
      <button v-if="missingInstallStore.state.continueText" :disabled="missingInstallStore.isActionPending"
        class="rounded-lg bg-accent-danger px-5 py-2 text-[0.6875rem] font-black text-on-accent-danger shadow-[0_0.625rem_1.875rem_rgba(var(--rgb-accent-danger),0.28)] transition-all hover:brightness-105 active:scale-95 disabled:cursor-not-allowed disabled:opacity-45 disabled:hover:brightness-100 disabled:active:scale-100"
          @click="missingInstallStore.continueCurrentAction()" >
        {{ missingInstallStore.state.continueText }}
      </button>
      <button v-if="missingInstallStore.state.summary.actionableTotal > 0" :disabled="missingInstallStore.selectedCount === 0 || missingInstallStore.isActionPending"
        class="rounded-lg bg-accent-primary px-5 py-2 text-[0.6875rem] font-black text-on-accent-primary shadow-[0_0.625rem_1.875rem_rgba(var(--rgb-accent-primary),0.28)] transition-all hover:brightness-105 active:scale-95 disabled:cursor-not-allowed disabled:opacity-45 disabled:hover:brightness-100 disabled:active:scale-100"
        @click="missingInstallStore.subscribeSelected()" >
        {{ missingInstallStore.pendingAction === 'subscribe' ? '订阅中...' : '订阅选中项' }}
      </button>
      <button v-if="missingInstallStore.state.summary.actionableTotal > 0" @click="missingInstallStore.downloadSelected()"
        class="rounded-lg bg-accent-tip px-5 py-2 text-[0.6875rem] font-black text-on-accent-tip shadow-[0_0.625rem_1.875rem_rgba(var(--rgb-accent-warn),0.28)] transition-all hover:brightness-105 active:scale-95 disabled:cursor-not-allowed disabled:opacity-45 disabled:hover:brightness-100 disabled:active:scale-100"
        :disabled="missingInstallStore.selectedCount === 0 || missingInstallStore.isActionPending" >
        {{ missingInstallStore.pendingAction === 'download' ? '下载中...' : '下载选中项' }}
      </button>
    </div>
  </CommonModalShell>
</template>

<script setup>
import { computed } from 'vue'
import { X } from 'lucide-vue-next'
import { useMissingInstallStore } from '../stores/missingInstallStore'
import CommonModalShell from './common/CommonModalShell.vue'

const missingInstallStore = useMissingInstallStore()
const hasActionableRows = computed(() => missingInstallStore.state.summary.actionableTotal > 0)
const hasUnknownItems = computed(() => missingInstallStore.state.summary.unknownTotal > 0)
const isUnknownOnlyMode = computed(() => !hasActionableRows.value && hasUnknownItems.value)

const versionBadgeClass = (versionInfo = {}) => {
  if (versionInfo?.tone === 'success') {
    return 'border-accent-success/25 bg-accent-success/12 text-accent-success'
  }
  if (versionInfo?.tone === 'danger') {
    return 'border-accent-danger/25 bg-accent-danger/12 text-accent-danger'
  }
  return 'border-border-base/10 bg-bg-overlay/5 text-text-dim'
}

const sourceLabel = (source = null) => {
  if (!source) return '未知'
  if (source.kind === 'workshop') {
    return source.workshopId || 'Workshop'
  }
  return 'URL'
}
</script>
