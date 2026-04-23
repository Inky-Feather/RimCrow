<template>
  <transition name="panel-fade">
    <div
      v-if="appStore.uiState.showTextureOptModal"
      class="fixed inset-0 z-100 flex items-center justify-center bg-bg-deep/70 backdrop-blur-md"
      @click.self="closeModal"
    >
      <div data-tour="texture-opt-modal" class="flex h-[92vh] w-[92vw] max-w-screen-2xl flex-col overflow-hidden rounded-2xl border border-text-main/10 bg-bg-deep/95 shadow-2xl">
        <header class="shrink-0 border-b border-text-main/5 bg-[linear-gradient(135deg,rgba(15,23,42,0.88),rgba(2,6,23,0.96))] px-6 py-2">
          <div class="flex items-center justify-between">

            <h2 data-tour="texture-opt-title" class="shrink-0 flex items-center gap-3 min-w-0 text-2xl font-black tracking-wider text-text-main">
              <Images class="w-6 h-6 text-accent-highlight" />
              <span>贴图优化</span>
              <span v-tooltip="textureOptHelpText" class="inline-flex size-5 cursor-help items-center justify-center text-lg font-bold text-text-dim hover:text-text-main hover:border-text-main/30">?</span>
            </h2>

            <div data-tour="texture-opt-summary" class="mx-5 min-w-0 flex-1 rounded-xl border border-text-main/6 bg-black/18 px-4 py-2 text-xs">
              <div class="grid grid-cols-4 gap-x-4 gap-y-2">
                <div class="min-w-0">
                  <span class="text-accent-tip/80">PNG</span>
                  <span class="ml-1 text-text-dim">{{ summary.source_total_count || 0 }} 张</span>
                  <span class="ml-1 font-mono font-bold text-accent-tip">{{ formatFileSize(summary.source_total_bytes || 0) }}</span>
                </div>
                <div class="min-w-0">
                  <span class="text-accent-primary/80">DDS</span>
                  <span class="ml-1 text-text-dim">{{ summary.output_total_count || 0 }} 张</span>
                  <span class="ml-1 font-mono font-bold text-accent-primary">{{ formatFileSize(summary.output_total_bytes || 0) }}</span>
                </div>
                <div class="min-w-0 truncate text-accent-highlight">
                  显存占用预估
                  <span class="ml-1 line-through opacity-50">{{ formatFileSize(summary.source_vram_bytes_est || 0) }}</span>
                  <span class="mx-1">→</span>
                  <span class="font-mono font-bold">{{ formatFileSize(summary.output_vram_bytes_est || 0) }}</span>
                </div>
                <div class="min-w-0 text-text-dim">
                  模组 <span class="ml-1 font-mono font-bold text-text-main">{{ summary.mod_count || 0 }}</span>
                </div>

                <div class="min-w-0 text-accent-warning/80">
                  待生成 <span class="ml-1 font-mono font-bold text-text-main">{{ summary.generate_required_count || 0 }}</span>
                </div>
                <div class="min-w-0 text-text-dim">
                  超范围 <span class="ml-1 font-mono font-bold text-text-main">{{ summary.skip_small_count || 0 }}</span>
                </div>
                <div class="min-w-0 flex items-center gap-4 col-span-2">
                  <span class="shrink-0 text-accent-tip/80">
                    缩放 <span class="ml-1 font-mono font-bold text-text-main">{{ summary.scaled_count || 0 }}</span>
                  </span>
                  <span class="shrink-0 text-accent-secondary/80">
                    回退 <span class="ml-1 font-mono font-bold text-text-main">{{ summary.fallback_scaled_count || 0 }}</span>
                  </span>
                  <span class="shrink-0 text-text-dim">
                    原尺寸 <span class="ml-1 font-mono font-bold text-text-main">{{ summary.keep_original_count || 0 }}</span>
                  </span>
                  <span v-if="summary.unsupported_source_count" class="shrink-0 cursor-help text-accent-warning" v-tooltip="unsupportedSummaryTooltip">
                    无效 PNG <span class="ml-1 font-mono font-bold text-text-main">{{ summary.unsupported_source_count }}</span>
                  </span>
                </div>
              </div>
            </div>

            <div class="flex justify-end">
              <button @click="closeModal" class="p-2 rounded-full text-text-dim hover:text-text-main hover:bg-red-500/20 transition-colors">
                <X class="w-5 h-5" />
              </button>
            </div>

          </div>
        </header>

        <div class="flex flex-1 min-h-0">
          <section class="flex min-w-0 flex-1 flex-col border-r border-text-main/5">
            <div data-tour="texture-opt-list-toolbar" class="shrink-0 border-b border-text-main/5 bg-black/20 px-6 py-3">
              <div class="flex flex-wrap items-center justify-between gap-3">
                <div class="flex items-center gap-1 rounded-lg bg-text-main/5 p-1">
                  <button v-for="mode in ['ALL', 'PNG', 'DDS']" :key="mode" @click="textureStore.viewMode = mode" class="px-3 py-1 rounded-md text-xs font-bold transition-all"
                    :class="textureStore.viewMode === mode ? 'bg-text-main/15 text-text-main shadow-sm' : 'text-text-dim hover:text-text-main'" >
                    {{ mode === 'ALL' ? '综合视图' : (mode === 'PNG' ? '仅看 PNG' : '仅看 DDS') }}
                  </button>
                </div>

                <div class="flex flex-wrap items-center gap-3">
                  <div class="flex items-center gap-2 rounded-lg border border-text-main/10 bg-black/20 px-3 py-2">
                    <Search class="w-4 h-4 text-text-dim" />
                    <input v-model.trim="searchQuery" type="text" class="w-44 bg-transparent text-xs text-text-main outline-none"
                      placeholder="筛选模组名称或路径" >
                  </div>
                  <CommonSelect class="w-44" v-model="sortMetric" :options="sortOptions" />
                  <div class="text-xs italic text-text-dim">共 {{ displayRows.length }} 个结果</div>
                </div>
              </div>
            </div>

            <div data-tour="texture-opt-list" class="relative min-h-0 flex-1 overflow-hidden bg-black/10">
              <div v-if="displayRows.length === 0" class="absolute inset-0 flex flex-col items-center justify-center text-text-dim/50" >
                <Inbox class="mb-4 w-16 h-16 opacity-50" />
                <p>暂无数据，请先扫描统计或直接开始生成。</p>
              </div>

              <DynamicScroller v-else :items="displayRows" :min-item-size="textureListMinItemSize" key-field="mod_path"
                class="h-full min-h-0 custom-scrollbar px-3 py-2" v-slot="{ item, index, active }" >
                <DynamicScrollerItem :item="item" :active="active" :data-index="index" :size-dependencies="getRowSizeDependencies(item)" >
                  <div class="pb-1">
                    <TextureModCard :mod="item" :view-mode="textureStore.viewMode" :max-bytes="maxBytesInCurrentView" />
                  </div>
                </DynamicScrollerItem>
              </DynamicScroller>
            </div>

            <footer class="min-h-16 shrink-0 border-t border-text-main/5 bg-black/40 px-6 py-3">
              <div v-if="showProgressBlock" class="space-y-2">
                <div class="flex items-center gap-3">
                  <component :is="progressStatusIcon" class="w-4 h-4 shrink-0" :class="progressStatusIconClass" />
                  <div class="min-w-0 flex-1 overflow-hidden rounded-full bg-text-main/10 h-2">
                    <div class="h-full transition-all duration-300" :class="progressBarClass" :style="{ width: `${progressDisplayPercent}%` }"></div>
                  </div>
                  <span class="shrink-0 text-xs font-mono" :class="progressPercentClass">{{ progressDisplayPercent }}%</span>
                  <span class="shrink-0 text-xs font-mono text-text-dim">{{ progressElapsedLabel }}</span>
                </div>
                <div class="flex items-center justify-between gap-3 text-xs">
                  <span class="min-w-0 truncate text-text-dim" v-tooltip="progressFullMessage">
                    {{ progressFullMessage }}
                  </span>
                  <div class="shrink-0 whitespace-nowrap text-text-dim">
                    <span v-if="progressCountLabel">{{ progressCountLabel }}</span>
                  </div>
                </div>
              </div>

              <div v-else class="flex items-center gap-2 text-xs text-text-dim">
                <CheckCircle2 class="w-4 h-4 text-accent-success" />
                就绪
              </div>
            </footer>
          </section>

          <aside class="flex w-96 shrink-0 flex-col bg-bg-surface">
            <div data-tour="texture-opt-options"  class="min-h-0 flex-1 overflow-y-auto custom-scrollbar p-4">
              <div class="space-y-2">
                <div class="rounded-lg border p-3 text-xs"
                  :class="toolStatus.available ? 'bg-accent-success/10 border-accent-success/20 text-accent-success' : 'bg-accent-danger/10 border-accent-danger/20 text-accent-danger'">
                  <div class="font-bold">{{ toolStatus.available ? '工具已就绪' : '工具未就绪' }}</div>
                  <div class="mt-1 break-all opacity-90">{{ toolStatus.message || '正在检测环境...' }}</div>
                  <div v-if="toolStatus.resolved_path" class="mt-2 break-all text-xs opacity-70">{{ toolStatus.resolved_path }}</div>
                </div>

                <button v-if="!toolStatus.available && !isBusy" @click="textureStore.downloadTool()"
                  class="w-full rounded-xl bg-text-main/10 py-2 text-sm font-bold transition-colors hover:bg-text-main/20" >
                  下载 todds
                </button>

                <section class="space-y-3 rounded-xl border border-text-main/8 bg-black/12 p-3">
                  <h3 class="text-xs font-black uppercase tracking-widest text-text-main">处理范围</h3>
                  <CommonSelect v-model="targetScope"
                    :options="[
                      { label: '仅当前启用的模组', value: 'active' },
                      { label: '全部已安装模组', value: 'all' }
                    ]"
                  />
                </section>

                <section class="space-y-2 rounded-xl border border-text-main/8 bg-black/12 p-3">
                  <h3 class="text-xs font-black uppercase tracking-widest text-text-main">生成选项</h3>
                  <CommonSwitch label="生成 Mipmap" description="Mipmap 是给远距离显示准备的缩小层级。开启后远看更平滑、闪烁更少，但生成时间和文件体积会增加一些。" v-model="config.generate_mipmaps"
                    @change="saveConfig" mini />
                  <CommonSelect label="生成范围" v-model="config.process_mode" @change="saveConfig"
                    description="决定这次是全量重做、只补缺失结果，还是只更新可缩放的图片。"
                    :options="[
                      { label: '完全覆盖生成', value: 'all_overwrite' },
                      { label: '增量生成', value: 'all_skip_existing' },
                      { label: '只生成压缩贴图（覆盖）', value: 'scaled_only_overwrite' }
                    ]"
                  />
                </section>

                <section class="space-y-3 rounded-xl border border-text-main/8 bg-black/12 p-3">
                  <h3 class="text-xs font-black uppercase tracking-widest text-text-main">缩放降显存</h3>
                  <CommonSelect label="最小清晰度" v-model.number="config.max_size" @change="saveConfig"
                    description="缩放时会尽量保证最短边不低于这个目标，避免图片被压得过小。"
                    :options="[
                      { label: '256 px', value: 256 },
                      { label: '128 px', value: 128 }
                    ]"
                  />
                  <CommonSelect label="缩放比例" v-model.number="config.scale_factor" @change="saveConfig"
                    description="优先按当前比例处理；如果某些图片不适合这个比例，会自动回退到更稳妥的比例，必要时保持原尺寸。"
                    :options="[
                      { label: '100%', value: 1.0 },
                      { label: '80%', value: 0.8 },
                      { label: '75%', value: 0.75 },
                      { label: '60%', value: 0.6 },
                      { label: '50%', value: 0.5 },
                      { label: '40%', value: 0.4 },
                      { label: '25%', value: 0.25 },
                      { label: '20%', value: 0.2 }
                    ]"
                  />
                  <CommonSwitch label="超范围图片不参与缩放" description="太小或太大的图片仍会生成 DDS，但会保留原尺寸，不参与缩放比例计算。"
                    v-model="config.skip_small_textures" @change="saveConfig" mini />
                </section>

                <section class="space-y-2 rounded-xl border border-text-main/8 bg-black/12 p-3">
                  <h3 class="text-xs font-black uppercase tracking-widest text-text-main">清理说明</h3>
                  <div class="rounded-lg border border-text-main/10 bg-black/20 px-3 py-2 text-xs text-text-dim">
                    清理功能会删除当前选中范围内，与 PNG 源图同名的 DDS 结果文件。
                  </div>
                </section>
              </div>
            </div>

            <div class="shrink-0 border-t border-text-main/5 bg-black/20 p-4">
              <div data-tour="texture-opt-actions" class="space-y-2">
                <div class="flex gap-2">
                  <button data-tour="texture-opt-analyze" @click="handleAnalyze" :disabled="isBusy"
                    class="flex w-full items-center justify-center gap-2 rounded-xl border border-accent-secondary/30 bg-accent-secondary/10 py-2.5 font-bold text-accent-secondary transition-all hover:scale-102 active:scale-95 cursor-pointer disabled:cursor-not-allowed disabled:opacity-50">
                    <ScanSearch class="w-4 h-4" /> 扫描统计
                  </button>
                  <button data-tour="texture-opt-clean" @click="handleCleanGenerated" :disabled="!toolStatus.available || isBusy"
                    class="flex w-full items-center justify-center gap-2 rounded-xl border border-accent-warning/30 bg-accent-warning/10 py-2.5 font-bold text-accent-warning transition-all hover:scale-102 active:scale-95 cursor-pointer disabled:cursor-not-allowed disabled:opacity-50">
                    <BrushCleaning class="w-4 h-4" /> 清理已生成 DDS
                  </button>
                </div>

                <button v-if="!isBusy" data-tour="texture-opt-generate" @click="handleOptimize" :disabled="!toolStatus.available"
                  class="flex w-full items-center justify-center gap-2 rounded-xl bg-accent-primary py-3 font-black text-black shadow-[0_0_15px_rgba(59,130,246,0.3)] transition-all hover:scale-102 active:scale-95 cursor-pointer disabled:cursor-not-allowed disabled:opacity-50">
                  <Rocket class="w-5 h-5" /> {{ processModeLabel }}
                </button>


                <button v-else @click="handleCancel" class="flex w-full items-center justify-center gap-2 rounded-xl bg-accent-danger py-3 font-black text-white shadow-[0_0_15px_rgba(244,63,94,0.3)] transition-all hover:scale-102 active:scale-95 cursor-pointer">
                  <Ban class="w-5 h-5" /> 停止当前任务
                </button>
              </div>
            </div>
          </aside>
        </div>
      </div>
    </div>
  </transition>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { DynamicScroller, DynamicScrollerItem } from 'vue-virtual-scroller'
import { useNow } from '@vueuse/core'
import { Ban, BrushCleaning, CheckCircle2, Cpu, Images, Inbox, Loader2, Rocket, ScanSearch, Search, X } from 'lucide-vue-next'
import { useAppStore } from '../stores/appStore'
import { useTextureStore } from '../stores/textureStore'
import { useModStore } from '../stores/modStore'
import CommonSwitch from './common/input/CommonSwitch.vue'
import CommonSelect from './common/input/CommonSelect.vue'
import TextureModCard from './utils/TextureModCard.vue'
import { formatFileSize } from '../utils/uiHelper'

const appStore = useAppStore()
const textureStore = useTextureStore()
const modStore = useModStore()

const config = computed(() => appStore.settings.texture_opt)
const summary = computed(() => textureStore.globalSummary || {})
const progressState = computed(() => textureStore.progressState)
const toolStatus = computed(() => textureStore.toolStatus)
const isBusy = computed(() => textureStore.isAnalyzing || textureStore.isOptimizing)
const now = useNow({ interval: 1000 })
const targetScope = ref('active')
const searchQuery = ref('')
const sortMetric = ref('impact')
const textureOptHelpText = '把图片提前转换成更适合游戏读取的格式。通常能减少显存压力、加快加载，但会多占一些磁盘空间，而且第一次生成需要等一会儿。'
const textureListMinItemSize = computed(() => Math.max(88, Math.round(Number(appStore.settings.ui.font_size || 14) * 7.2)))

const sortOptions = [
  { label: '按总体积占比', value: 'impact' },
  { label: '按待生成数量', value: 'pending' },
  { label: '按显存节省', value: 'vram' },
  { label: '按名称', value: 'name' },
]

const displayRows = computed(() => {
  const query = searchQuery.value.trim().toLowerCase()
  const rows = textureStore.modsData
    .map(item => ({
      ...item,
      mod_name: resolveModName(item),
      mod_path: item.mod_path || '',
      vram_saved: Math.max(0, Number(item.source_vram_bytes_est || 0) - Number(item.output_vram_bytes_est || 0)),
    }))
    .filter(item => {
      if (!query) return true
      return item.mod_name.toLowerCase().includes(query) || item.mod_path.toLowerCase().includes(query)
    })

  rows.sort((a, b) => {
    if (sortMetric.value === 'name') {
      return a.mod_name.localeCompare(b.mod_name, 'zh-Hans-CN')
    }
    if (sortMetric.value === 'pending') {
      return (Number(b.generate_required_count || 0) - Number(a.generate_required_count || 0))
        || (Number(b.unsupported_source_count || 0) - Number(a.unsupported_source_count || 0))
        || (Number(b.combined_total_bytes || 0) - Number(a.combined_total_bytes || 0))
    }
    if (sortMetric.value === 'vram') {
      return Number(b.vram_saved || 0) - Number(a.vram_saved || 0)
    }

    const aMetric = textureStore.viewMode === 'PNG'
      ? Number(a.source_total_bytes || 0)
      : textureStore.viewMode === 'DDS'
        ? Number(a.output_total_bytes || 0)
        : Number(a.combined_total_bytes || 0)
    const bMetric = textureStore.viewMode === 'PNG'
      ? Number(b.source_total_bytes || 0)
      : textureStore.viewMode === 'DDS'
        ? Number(b.output_total_bytes || 0)
        : Number(b.combined_total_bytes || 0)
    return bMetric - aMetric
      || Number(b.generate_required_count || 0) - Number(a.generate_required_count || 0)
      || Number(b.unsupported_source_count || 0) - Number(a.unsupported_source_count || 0)
  })

  return rows
})

const maxBytesInCurrentView = computed(() => {
  const list = displayRows.value
  if (list.length === 0) return 1
  return list.reduce((maxBytes, item) => {
    const currentBytes = textureStore.viewMode === 'PNG'
      ? Number(item.source_total_bytes || 0)
      : textureStore.viewMode === 'DDS'
        ? Number(item.output_total_bytes || 0)
        : Number(item.combined_total_bytes || 0)
    return Math.max(maxBytes, currentBytes)
  }, 1)
})

const getRowSizeDependencies = (item) => [
  Number(appStore.settings.ui.font_size || 14),
  textureStore.viewMode,
  String(item?.mod_name || ''),
  Number(item?.generate_required_count || 0),
  Number(item?.unsupported_source_count || 0),
  JSON.stringify(item?.scale_breakdown || []),
  Number(item?.source_total_count || 0),
  Number(item?.output_total_count || 0),
  Number(item?.source_total_bytes || 0),
  Number(item?.output_total_bytes || 0),
]
const unsupportedSummaryTooltip = computed(() => {
  const preview = Array.isArray(summary.value.engine_unsupported_preview) ? summary.value.engine_unsupported_preview : []
  if (!preview.length) return '有些文件看起来像图片，其实不是正常图片，已经自动跳过。'
  return [
    '以下伪装 PNG 已从任务中自动排除：',
    ...preview.map(item => `${item.mod_name} / ${item.rel_path}${item.reason ? ` - ${item.reason}` : ''}`),
  ].join('\n')
})

const processedCount = computed(() => {
  const details = progressState.value.details || {}
  return Number((details.phase_done ?? details.done ?? details.processed_mods) || 0)
})

const totalCount = computed(() => {
  const details = progressState.value.details || {}
  return Number((details.phase_total ?? details.total ?? details.total_mods) || 0)
})

const progressPhaseLabel = computed(() => {
  const details = progressState.value.details || {}
  return String(details.phase_label || '')
})

const processModeLabel = computed(() => {
  if (config.value.process_mode === 'all_overwrite') return '完全覆盖生成'
  if (config.value.process_mode === 'all_skip_existing') return '增量生成'
  return '只生成压缩贴图'
})

const progressCountLabel = computed(() => {
  if (!totalCount.value) return ''
  const details = progressState.value.details || {}
  const unit = String(details.phase_unit || (details.total_mods != null || details.processed_mods != null ? '模组' : '项'))
  const phase = progressPhaseLabel.value ? `${progressPhaseLabel.value} ` : ''
  return `${phase}${processedCount.value}/${totalCount.value} ${unit}`
})

const progressFullMessage = computed(() => String(progressState.value.message || '处理中...'))
const showProgressBlock = computed(() => isBusy.value || showFinishedProgress.value)
const progressDisplayPercent = computed(() => {
  if (showFinishedProgress.value) return 100
  const details = progressState.value.details || {}
  return Number((details.phase_percent ?? progressState.value.percent) || 0)
})
const progressStatusIcon = computed(() => (showFinishedProgress.value ? CheckCircle2 : Loader2))
const progressStatusIconClass = computed(() => (showFinishedProgress.value ? 'text-accent-success' : 'text-accent-primary animate-spin'))
const progressBarClass = computed(() => (showFinishedProgress.value ? 'bg-accent-success' : 'bg-accent-primary'))
const progressPercentClass = computed(() => (showFinishedProgress.value ? 'text-accent-success' : 'text-accent-primary'))

const progressElapsedLabel = computed(() => {
  const details = progressState.value.details || {}
  const startedAt = Number(details.local_started_at || 0)
  if (!startedAt) return '--:--'
  const totalElapsed = Number(details.local_total_elapsed_ms || 0)
  const isTerminal = ['success', 'failed', 'cancelled'].includes(String(details.local_status || ''))
  if (isTerminal && totalElapsed > 0) {
    return `总用时 ${formatDuration(totalElapsed)}`
  }
  return `已用时 ${formatDuration(Math.max(0, Number(now.value) - startedAt))}`
})

const showFinishedProgress = computed(() => {
  const status = String(progressState.value.details?.local_status || '')
  return ['success', 'failed', 'cancelled'].includes(status)
})

const closeModal = () => {
  appStore.uiState.showTextureOptModal = false
}

const saveConfig = async () => {
  await appStore.saveSetting('texture_opt', config.value)
  await textureStore.checkToolStatus()
}

const getTargetIds = () => {
  if (targetScope.value === 'active') {
    return modStore.activeIds
  }
  return Array.from(modStore.allModsMap.values())
    .filter(mod => !mod.isMissing && mod.path)
    .map(mod => mod.package_id)
}

const handleAnalyze = async () => {
  const ids = getTargetIds()
  await textureStore.startAnalysis(ids)
}

const handleOptimize = async () => {
  const ids = getTargetIds()
  await textureStore.startOptimization(ids, 'optimize')
}

const handleCleanGenerated = async () => {
  const ids = getTargetIds()
  await textureStore.startOptimization(ids, 'clean_generated')
}

const handleCancel = async () => {
  await textureStore.cancelCurrentTask()
}

watch(() => appStore.uiState.showTextureOptModal, (visible) => {
  if (visible) {
    textureStore.checkToolStatus()
  }
})

function resolveModName(item) {
  const match = Array.from(modStore.allModsMap.values()).find(mod => mod?.path === item.mod_path)
  return match?.alias_name || match?.display_name || match?.name || item.mod_name || '未知模组'
}


function formatDuration(ms) {
  const totalSeconds = Math.max(0, Math.floor(Number(ms || 0) / 1000))
  const hours = Math.floor(totalSeconds / 3600)
  const minutes = Math.floor((totalSeconds % 3600) / 60)
  const seconds = totalSeconds % 60
  return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
}

</script>

<style scoped>
.panel-fade-enter-active,
.panel-fade-leave-active {
  transition: opacity 0.3s ease;
}

.panel-fade-enter-from,
.panel-fade-leave-to {
  opacity: 0;
}

.custom-scrollbar::-webkit-scrollbar {
  width: 6px;
}

.custom-scrollbar::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.1);
  border-radius: 10px;
}

.custom-scrollbar::-webkit-scrollbar-thumb:hover {
  background: var(--color-accent-primary);
}
</style>
