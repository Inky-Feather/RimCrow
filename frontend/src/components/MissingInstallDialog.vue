<template>
  <Teleport to="body">
    <Transition name="missing-install-fade">
      <div
        v-if="missingInstallStore.isVisible"
        class="fixed inset-0 z-9999 flex items-center justify-center bg-bg-deep/65 backdrop-blur-sm"
        @click.self="missingInstallStore.close()"
      >
        <div class="relative flex w-[68rem] max-h-[86vh] max-w-[94vw] flex-col overflow-hidden rounded-3xl border border-text-main/10 bg-bg-deep/94 shadow-[0_1.75rem_5.625rem_rgba(0,0,0,0.62)]">
          <div class="absolute inset-x-0 top-0 h-[0.0625rem] bg-linear-to-r from-transparent via-accent-primary to-transparent opacity-80"></div>

          <div class="relative z-10 flex items-start justify-between gap-3 border-b border-text-main/6 px-5 py-4">
            <div class="min-w-0">
              <h3 class="text-lg font-black tracking-wide text-text-main">{{ missingInstallStore.state.title }}</h3>
              <p class="mt-1.5 max-w-4xl text-[0.6875rem] leading-5 text-text-dim/85">
                {{ missingInstallStore.state.message }}
              </p>
            </div>
            <button
              class="rounded-lg border border-text-main/10 bg-text-main/5 px-3 py-1.5 text-xs font-bold text-text-dim transition-all hover:bg-text-main/10 hover:text-text-main"
              @click="missingInstallStore.close(false)"
            >
              关闭
            </button>
          </div>

          <div class="relative z-10 flex flex-wrap items-center justify-between gap-2 border-b border-text-main/6 bg-black/12 px-5 py-2.5">
            <div class="flex flex-wrap items-center gap-1.5 text-[0.6875rem] text-text-dim">
              <span class="rounded-full border border-accent-primary/25 bg-accent-primary/12 px-3 py-1 font-bold text-accent-primary">
                {{ missingInstallStore.selectedCount }} / {{ missingInstallStore.totalCount }} 已选
              </span>
              <span v-if="missingInstallStore.state.summary.missingTotal > 0" class="rounded-full border border-accent-danger/25 bg-accent-danger/12 px-3 py-1 font-bold text-accent-danger">
                缺失 {{ missingInstallStore.state.summary.missingTotal }}
              </span>
              <span v-if="missingInstallStore.state.summary.installableTotal > 0" class="rounded-full border border-accent-primary/25 bg-accent-primary/12 px-3 py-1 font-bold text-accent-primary">
                可安装 {{ missingInstallStore.state.summary.installableTotal }}
              </span>
              <span v-if="missingInstallStore.state.summary.optionalInstallTotal > 0" class="rounded-full border border-accent-tip/25 bg-accent-tip/12 px-3 py-1 font-bold text-accent-tip">
                可选安装 {{ missingInstallStore.state.summary.optionalInstallTotal }}
              </span>
              <span v-if="missingInstallStore.state.summary.unknownTotal > 0" class="rounded-full border border-text-main/10 bg-text-main/6 px-3 py-1 font-bold text-text-dim">
                未知来源 {{ missingInstallStore.state.summary.unknownTotal }}
              </span>
            </div>
            <div class="flex flex-wrap items-center gap-1.5">
              <button
                class="rounded-lg border border-text-main/10 bg-text-main/5 px-2.5 py-1.5 text-[0.6875rem] font-bold text-text-dim transition-all hover:bg-text-main/10 hover:text-text-main"
                @click="missingInstallStore.selectAll()"
              >
                全选
              </button>
              <button
                class="rounded-lg border border-text-main/10 bg-text-main/5 px-2.5 py-1.5 text-[0.6875rem] font-bold text-text-dim transition-all hover:bg-text-main/10 hover:text-text-main"
                @click="missingInstallStore.clearSelection()"
              >
                清空
              </button>
            </div>
          </div>

          <div class="relative z-10 flex-1 overflow-y-auto px-5 py-4">
            <div class="space-y-3.5">
              <section
                v-if="missingInstallStore.state.groups.length === 0"
                class="rounded-2xl border border-text-main/6 bg-text-main/[0.03] px-4 py-4"
              >
                <h4 class="text-sm font-black tracking-wide text-text-main">当前没有可直接处理的安装项</h4>
                <p class="mt-1.5 text-[0.6875rem] leading-5 text-text-dim/82">
                  这些项目暂时只能先排查，当前还不能直接下载或订阅。你可以先返回处理，或在可用时清理列表中的未知项。
                </p>
              </section>
              <section
                v-for="group in missingInstallStore.state.groups"
                :key="group.key"
                class="rounded-2xl border border-text-main/6 bg-text-main/[0.03]"
              >
                <div class="flex flex-wrap items-start justify-between gap-2 border-b border-text-main/6 px-4 py-3">
                  <div class="min-w-0">
                    <div class="flex flex-wrap items-center gap-1.5">
                      <h4 class="text-sm font-black tracking-wide text-text-main">{{ group.title }}</h4>
                      <span class="rounded-full border border-text-main/10 bg-text-main/6 px-2 py-0.5 text-[0.625rem] font-bold text-text-dim">
                        {{ group.rows.length }} 项
                      </span>
                    </div>
                    <p v-if="group.description" class="mt-1 text-[0.625rem] leading-4 text-text-dim/74">{{ group.description }}</p>
                  </div>
                </div>

                <div class="space-y-2 px-3 py-3">
                  <article
                    v-for="row in group.rows"
                    :key="row.id"
                    class="flex items-start gap-2 rounded-xl border border-text-main/8 bg-black/8 px-3 py-2 transition-colors"
                    :class="missingInstallStore.getSelectedSource(row) && missingInstallStore.isSelected(row.id) ? 'border-accent-primary/25 bg-accent-primary/[0.05]' : ''"
                  >
                    <label class="mt-0.5 flex shrink-0 cursor-pointer items-center">
                      <input
                        type="checkbox"
                        class="h-3.5 w-3.5 accent-[#06b6d4]"
                        :checked="missingInstallStore.isSelected(row.id)"
                        @change="missingInstallStore.toggleRow(row.id, $event.target.checked)"
                      >
                    </label>

                    <div class="min-w-0 flex-1">
                      <div class="flex flex-wrap items-center gap-1.5">
                        <span class="truncate text-[0.8125rem] font-black text-text-main">{{ row.title }}</span>
                        <span
                          v-for="reasonLabel in row.reasonLabels || []"
                          :key="reasonLabel"
                          class="rounded-full border border-text-main/10 bg-text-main/6 px-2 py-0.5 text-[0.625rem] font-bold text-text-dim"
                        >
                          {{ reasonLabel }}
                        </span>
                        <span
                          v-if="row.choiceOptions?.length === 1"
                          v-tooltip="missingInstallStore.getVersionTooltip(missingInstallStore.getRowVersionInfo(row))"
                          class="rounded-full border px-2 py-0.5 text-[0.625rem] font-bold"
                          :class="versionBadgeClass(missingInstallStore.getRowVersionInfo(row))"
                        >
                          {{ missingInstallStore.getRowVersionInfo(row).label }}
                        </span>
                        <span
                          v-if="row.choiceOptions?.length === 1"
                          class="rounded-full border border-accent-primary/20 bg-accent-primary/10 px-2 py-0.5 text-[0.625rem] font-bold text-accent-primary"
                        >
                          {{ sourceLabel(missingInstallStore.getSelectedSource(row)) }}
                        </span>
                      </div>
                      <div v-if="row.choiceOptions?.length > 1" class="mt-2 space-y-2">
                        <div
                          v-for="choice in row.choiceOptions"
                          :key="`${row.id}:${choice.id}`"
                          class="flex w-full items-start gap-3 rounded-xl border px-3 py-2.5 text-left transition-all"
                          :class="missingInstallStore.getSelectedChoice(row)?.id === choice.id
                            ? 'border-accent-primary/40 bg-accent-primary/[0.08]'
                            : 'border-text-main/10 bg-text-main/[0.03]'"
                        >
                          <button
                            type="button"
                            class="flex min-w-0 flex-1 items-start gap-3 text-left transition-all hover:brightness-110"
                            @click="missingInstallStore.setChoice(row.id, choice.id)"
                          >
                            <span class="mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full border border-text-main/18">
                              <span
                                class="h-2 w-2 rounded-full transition-opacity"
                                :class="missingInstallStore.getSelectedChoice(row)?.id === choice.id ? 'bg-accent-primary opacity-100' : 'opacity-0'"
                              ></span>
                            </span>

                            <div class="min-w-0 flex-1">
                              <div class="flex items-center justify-between gap-2">
                                <span class="truncate text-[0.75rem] font-black text-text-main">{{ choice.title }}</span>
                                <span class="shrink-0 rounded-full border border-text-main/10 bg-text-main/6 px-2 py-0.5 text-[0.625rem] font-bold text-text-dim">
                                  {{ choice.label }}
                                </span>
                              </div>
                              <div class="mt-1 flex flex-wrap items-center gap-1.5">
                                <span class="rounded-full border border-accent-primary/20 bg-accent-primary/10 px-2 py-0.5 text-[0.625rem] font-bold text-accent-primary">
                                  {{ sourceLabel(choice.source) }}
                                </span>
                                <span
                                  v-tooltip="missingInstallStore.getVersionTooltip(choice.versionInfo)"
                                  class="rounded-full border px-2 py-0.5 text-[0.625rem] font-bold"
                                  :class="versionBadgeClass(choice.versionInfo)"
                                >
                                  {{ choice.versionInfo.label }}
                                </span>
                              </div>
                            </div>
                          </button>

                          <button
                            class="shrink-0 rounded-xl border border-accent-primary/35 bg-accent-primary/10 px-3 py-1.5 text-[0.6875rem] font-black text-accent-primary transition-all hover:bg-accent-primary/18 hover:text-[#7dd3fc]"
                            @click.stop="missingInstallStore.openSource(choice.source)"
                          >
                            访问来源
                          </button>
                        </div>
                      </div>
                    </div>

                    <button
                      v-if="row.choiceOptions?.length === 1 && missingInstallStore.getSelectedSource(row)"
                      class="shrink-0 rounded-xl border border-accent-primary/35 bg-accent-primary/10 px-3 py-1.5 text-[0.6875rem] font-black text-accent-primary transition-all hover:bg-accent-primary/18 hover:text-[#7dd3fc]"
                      @click="missingInstallStore.openSource(missingInstallStore.getSelectedSource(row))"
                    >
                      访问来源
                    </button>
                  </article>
                </div>
              </section>
            </div>
          </div>

          <div class="relative z-10 flex items-center justify-end gap-2.5 border-t border-text-main/6 bg-black/14 px-5 py-3.5">
            <button
              class="rounded-lg border border-text-main/10 bg-text-main/5 px-4 py-2 text-[0.6875rem] font-bold text-text-dim transition-all hover:bg-text-main/10 hover:text-text-main"
              @click="missingInstallStore.close(false)"
            >
              {{ missingInstallStore.state.cancelText }}
            </button>
            <button
              v-if="missingInstallStore.state.cleanupText"
              class="rounded-lg bg-accent-danger px-5 py-2 text-[0.6875rem] font-black text-black shadow-[0_0.625rem_1.875rem_rgba(239,68,68,0.28)] transition-all hover:brightness-105 active:scale-95"
              @click="missingInstallStore.cleanupUnknownAndContinue()"
            >
              {{ missingInstallStore.state.cleanupText }}
            </button>
            <button
              v-if="missingInstallStore.state.summary.actionableTotal > 0"
              class="rounded-lg bg-accent-primary px-5 py-2 text-[0.6875rem] font-black text-black shadow-[0_0.625rem_1.875rem_rgba(6,182,212,0.28)] transition-all hover:brightness-105 active:scale-95 disabled:cursor-not-allowed disabled:opacity-45 disabled:hover:brightness-100 disabled:active:scale-100"
              :disabled="missingInstallStore.selectedCount === 0"
              @click="missingInstallStore.subscribeSelected()"
            >
              订阅选中项
            </button>
            <button
              v-if="missingInstallStore.state.summary.actionableTotal > 0"
              class="rounded-lg bg-accent-tip px-5 py-2 text-[0.6875rem] font-black text-black shadow-[0_0.625rem_1.875rem_rgba(234,179,8,0.28)] transition-all hover:brightness-105 active:scale-95 disabled:cursor-not-allowed disabled:opacity-45 disabled:hover:brightness-100 disabled:active:scale-100"
              :disabled="missingInstallStore.selectedCount === 0"
              @click="missingInstallStore.downloadSelected()"
            >
              下载选中项
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
import { useMissingInstallStore } from '../stores/missingInstallStore'

const missingInstallStore = useMissingInstallStore()

const versionBadgeClass = (versionInfo = {}) => {
  if (versionInfo?.tone === 'success') {
    return 'border-accent-success/25 bg-accent-success/12 text-accent-success'
  }
  if (versionInfo?.tone === 'danger') {
    return 'border-accent-danger/25 bg-accent-danger/12 text-accent-danger'
  }
  return 'border-text-main/10 bg-text-main/6 text-text-dim'
}

const sourceLabel = (source = null) => {
  if (!source) return '未知来源'
  if (source.kind === 'workshop') {
    return source.workshopId || 'Workshop'
  }
  return 'URL'
}
</script>

<style scoped>
.missing-install-fade-enter-active,
.missing-install-fade-leave-active {
  transition: opacity 0.2s ease;
}

.missing-install-fade-enter-from,
.missing-install-fade-leave-to {
  opacity: 0;
}
</style>
