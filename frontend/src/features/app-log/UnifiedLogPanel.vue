<!-- frontend/src/components/utils/UnifiedLogPanel.vue -->
<template>
  <div class="content-surface flex h-full w-full flex-col font-mono text-sm">

    <!-- ================= 1. 顶部工具栏 ================= -->
    <div class="toolbar-surface flex flex-wrap items-center justify-between gap-2 px-3 py-2">

      <!-- A. 文件选择 / 实时切换 与 刷新 -->
      <div class="flex items-center gap-2">
        <div class="relative group/file z-30">
          <button class="flex items-center gap-2 px-3 py-1.5 bg-bg-inset/70 hover:bg-bg-overlay/5 border border-border-base/10 rounded-lg text-xs text-accent-cool transition-colors min-w-40 justify-between shadow-inner">
            <span class="truncate">{{ files.length ? selectedFile : '无日志文件' }}</span>
            <svg class="w-3 h-3 opacity-50" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" /></svg>
          </button>

          <div class="absolute left-0 top-full mt-1 w-72 bg-glass-heavy border border-border-base/10 rounded-lg shadow-2xl backdrop-blur-xl opacity-0 invisible group-hover/file:opacity-100 group-hover/file:visible transition-all duration-200 transform origin-top-left z-50">
            <div v-for="file in files" :key="file.path" @click="switchFile(file.name)"
                class="px-3 py-2 hover:bg-bg-overlay/10 cursor-pointer flex items-center justify-between">
              <div class="flex flex-col min-w-0">
                <span class="text-sm text-text-main truncate" :class="{'font-bold text-accent-primary': file.name === selectedFile}">{{ file.name }}</span>
                <span class="text-xs text-text-dim">{{ file.mtime }}</span>
              </div>
              <span class="text-xs text-accent-primary bg-accent-primary/10 px-1.5 py-0.5 rounded">{{ formatFileSize(file.size) }}</span>
            </div>
          </div>
        </div>

        <!-- 显式的实时模式切换按钮：优先绑定到 app.log / RimCrow_Realtime.log -->
        <button v-if="liveFileName"
          @click="switchToLive"
          class="px-2 py-1 rounded-lg text-xs font-bold flex items-center gap-1 border transition-all"
          :class="isLiveView
            ? 'bg-accent-success/20 text-accent-success border-accent-success/40'
            : 'bg-bg-overlay/5 text-text-dim border-border-base/10 hover:bg-accent-success/10 hover:text-accent-success'">
          <span
            class="w-2 h-2 rounded-full"
            :class="isLiveView ? 'bg-accent-success shadow-[0_0_8px_rgba(var(--rgb-accent-success),0.8)]' : 'bg-bg-neutral'">
          </span>
          <span>{{ isLiveView ? '实时模式' : '切到实时' }}</span>
        </button>

        <button @click="reloadAll" class="p-1.5 hover:bg-bg-overlay/10 rounded-lg text-text-dim hover:text-text-main transition-colors" v-tooltip="'强制重新读取'">
          <svg class="w-4 h-4" :class="{'animate-spin text-accent-primary': loadingFile}" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg>
        </button>
        <!-- 自动刷新开关 -->
        <button @click="autoScroll = !autoScroll"
          class="p-1.5 rounded-lg border transition-all"
          :class="autoScroll ? 'bg-accent-primary/20 text-accent-primary border-accent-primary/30' : 'bg-transparent text-text-dim border-transparent hover:bg-bg-overlay/5'"
          v-tooltip="autoScroll ? '禁用自动滚动' : '启用自动滚动到底部'">
          <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 14l-7 7m0 0l-7-7m7 7V3" /></svg>
        </button>
      </div>

      <!-- B. 搜索与时间过滤 -->
      <div class="flex-1 flex items-center gap-2 max-w-xl">
        <div class="flex-1 relative group/search">
          <svg class="absolute left-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-text-dim group-focus-within/search:text-accent-primary" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" /></svg>
          <input v-model="searchQuery" type="text" placeholder="正则搜索 (如 Exception|Crash)..."
            class="w-full bg-bg-inset/70 border border-border-base/10 rounded-lg py-1.5 pl-8 pr-8 text-xs text-text-main focus:outline-none focus:border-accent-primary/50 transition-all placeholder:text-text-disabled" />
          <button v-if="searchQuery" @click="searchQuery = ''" class="absolute right-2 top-1/2 -translate-y-1/2 text-text-dim hover:text-text-main">
            <svg class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6L6 18M6 6l12 12"/></svg>
          </button>
        </div>

        <!-- 时间段筛选 (简单起见使用原生 time input) -->
        <div class="flex items-center gap-1 bg-bg-inset/70 border border-border-base/10 rounded-lg px-2 py-1">
          <input type="time" v-model="timeFilter.start" class="bg-transparent text-xs text-text-main outline-none w-20" v-tooltip="'开始时间'" />
          <span class="text-text-dim">-</span>
          <input type="time" v-model="timeFilter.end" class="bg-transparent text-xs text-text-main outline-none w-20" v-tooltip="'结束时间'" />
          <button v-if="timeFilter.start || timeFilter.end" @click="timeFilter.start=''; timeFilter.end=''" class="text-accent-danger ml-1" v-tooltip="'清除时间限制'"><svg class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6L6 18M6 6l12 12"/></svg></button>
        </div>
      </div>

      <!-- C. 级别筛选 -->
      <div class="flex items-center gap-1 rounded-lg border border-border-base/10 bg-bg-inset/70 p-1">
        <button v-for="lvl in ['INFO','WARNING','ERROR','DEBUG']" :key="lvl"
          @click="filters[lvl] = !filters[lvl]"
          class="px-2 py-0.5 text-xs font-bold rounded transition-all select-none"
          :class="filters[lvl] ? getBtnColor(lvl) : 'text-text-dim opacity-40 hover:opacity-80'">
          {{ lvl }}
        </button>
      </div>

    </div>

    <div v-if="showRuntimeProfileSwitch" class="flex items-center justify-between gap-3 px-3 py-2 border-b border-accent-primary/15 bg-accent-primary/8" >
      <div class="text-xs text-accent-primary">
        当前运行的游戏环境是 <span class="font-bold">{{ runtimeProfileName }}</span> ，点击切换到当前实际运行的游戏环境，获取实时日志。
      </div>
      <button @click="switchToRuntimeProfile" class="px-2 py-1 rounded-lg text-[0.7rem] font-bold bg-accent-primary/15 text-accent-primary hover:bg-accent-primary hover:text-on-accent-primary transition-colors" >
        切换到当前运行的游戏环境
      </button>
    </div>

    <!-- ================= 2. 日志内容区 ================= -->
    <div class="flex-1 relative min-h-0 bg-bg-inset" ref="scrollContainer">

      <!-- 触顶加载指示器 -->
      <div v-if="hasMore" class="absolute top-0 left-0 w-full py-2 flex justify-center z-10 bg-linear-to-b from-bg-inset/90 to-transparent pointer-events-none">
        <div class="px-3 py-1 rounded-full bg-accent-primary/20 text-accent-primary text-xs font-bold backdrop-blur-md flex items-center gap-2 shadow-lg">
          <svg v-if="loadingMore" class="w-3 h-3 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg>
          <span v-else>向上滚动加载更多...</span>
        </div>
      </div>

      <!-- 虚拟滚动容器 -->
      <DynamicScroller v-if="filteredLogs.length" :items="filteredLogs" :min-item-size="28" class="h-full custom-scrollbar px-2"
        key-field="id" ref="scrollerRef" @scroll="onScroll" v-selectable-list="selectionConfig" >
        <template v-slot="{ item, index, active }">
          <DynamicScrollerItem :item="item" :active="active" :data-index="index" :size-dependencies="getRowSizeDependencies(item)" >
            <!-- 行容器：绑定 data-id，增加选中高亮背景，增加 swipe-trigger 类名以支持拖拽滑动多选 -->
            <div class="flex gap-2 group/row rounded-sm border-l-2 transition-colors text-shadow-md wrap-break-word leading-relaxed hover:bg-bg-overlay/5 mb-0.5"
                :class="[ getBorderClass(item.level), selectedIds.includes(item.id) ? 'bg-accent-primary/10 border-accent-primary' : '' ]"
                :data-id="item.id">

              <!-- 多选框区 (click-trigger 支持单点/Shift多选) -->
              <div v-if="sourceType === 'game' || appStore.settings.debug_mode" class="shrink-0 flex items-start pt-1 pl-1 swipe-trigger cursor-pointer">
                <div class="w-4 h-4 rounded border flex items-center justify-center transition-colors pointer-events-none"
                    :class="selectedIds.includes(item.id) ? 'bg-accent-primary border-accent-primary text-bg-deep' : 'border-border-base/18 group-hover/row:border-border-base/10'">
                  <svg v-if="selectedIds.includes(item.id)" class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/></svg>
                </div>
              </div>

              <!-- 时间戳与级别 (紧凑显示) -->
              <div class="shrink-0 w-fit flex items-start text-text-disabled select-none pt-0.5 pl-1">
                <span >{{ formatTime(item.timestamp) }}</span>
              </div>

              <!-- 主体内容 -->
              <div class="flex-1 min-w-0 py-0.5 pr-2 select-text">
                <!-- 诊断标签区 -->
                <div v-if="item.context && (sourceType === 'game' || appStore.settings.debug_mode)" class="flex flex-wrap gap-1 mb-1 items-center">
                  <!-- App 模块标签 -->
                  <span v-if="item.context.source === 'app' && item.context.module" class="px-1.5 py-0.5 rounded bg-accent-cool/20 text-accent-cool text-xs font-bold border border-accent-cool/30">
                    {{ item.context.module }} <span v-if="item.context.func" class="opacity-60">:: {{ item.context.func }}</span>
                  </span>
                  <!-- App 源文件路径 -->
                  <span v-if="item.context.source === 'app' && item.context.path"
                    class="px-1.5 py-0.5 rounded bg-bg-inset/80 text-text-dim text-xs border border-border-base/18 max-w-[18rem] truncate"
                    v-tooltip="item.context.path">
                    {{ item.context.path }}
                  </span>
                  <!-- 游戏 错误类型 -->
                  <span v-if="item.context.inferredType" class="px-1.5 py-0.5 rounded bg-accent-danger/20 text-accent-danger text-xs font-bold border border-accent-danger/30">
                    {{ item.context.inferredType }}
                  </span>
                  <span v-if="item.context.phase" class="px-1.5 py-0.5 rounded bg-bg-inset/80 text-text-dim text-xs border border-border-base/18">
                    {{ formatLogPhase(item.context.phase) }}
                  </span>
                  <!-- 关联文件 -->
                  <span v-for="file in (item.context.relatedFiles || []).slice(0,3)"
                    :key="file"
                    class="px-1.5 py-0.5 rounded bg-accent-cool/10 text-accent-cool text-xs border border-accent-cool/30 max-w-56 truncate"
                    v-tooltip="file">
                    {{ file }}
                  </span>
                  <span v-if="item.context.relatedFiles && item.context.relatedFiles.length > 3"
                    class="px-1 py-0.5 rounded text-xs text-text-dim">
                    +{{ item.context.relatedFiles.length - 3 }} 更多文件…
                  </span>
                  <!-- 嫌疑 Mod 点击跳转 -->
                  <button v-for="modId in (item.context.relatedModIds || [])" :key="modId"
                    @click="openMod(modId)"
                    class="px-1.5 py-0.5 rounded bg-accent-primary/20 hover:bg-accent-primary/40 text-accent-primary text-xs cursor-pointer border border-accent-primary/30 transition-colors"
                    v-tooltip="'点击查看 Mod 详情'">[Mod: {{ modId }}]
                  </button>
                  <span v-for="namespace in (item.context.relatedNamespaces || []).slice(0,3)"
                    :key="namespace"
                    class="px-1.5 py-0.5 rounded bg-accent-warning/12 text-accent-warning text-xs border border-accent-warning/25 max-w-56 truncate"
                    v-tooltip="'错误堆栈中出现的可疑来源'">
                    {{ namespace }}
                  </span>
                </div>
                <!-- 消息正文 (高亮搜索词) -->
                <div class="whitespace-pre-wrap"
                  :class="[item._folded ? 'log-body-collapsed' : '', getMessageTextClass(item.level)]"
                  v-html="highlightHtml(item._parsedMessage)">
                </div>
                <button v-if="item._folded"
                  @click="item._folded = false"
                  class="mt-0.5 text-xs text-accent-primary hover:text-accent-highlight">
                  展开完整日志
                </button>
                <!-- 展开详情 -->
                <div v-if="item.details || formatLogDiagnosticDetails(item)" class="mt-1">
                  <button @click="item._expanded = !item._expanded"
                    class="flex items-center gap-1 text-xs text-text-dim hover:text-text-main transition-colors select-none mb-0.5">
                    <svg class="w-3 h-3 transition-transform" :class="item._expanded ? 'rotate-90' : ''" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 18l6-6-6-6"/></svg>
                    <span>{{ item._expanded ? '收起诊断详情' : '展开诊断详情' }}</span>
                  </button>
                  <div v-if="item._expanded" class="pl-2 border-l border-border-base/10 text-text-dim text-xs bg-bg-inset/70 rounded p-1.5 overflow-x-auto whitespace-pre-wrap">
                    {{ [item.details, formatLogDiagnosticDetails(item)].filter(Boolean).join('\n\n') }}
                  </div>
                </div>

              </div>

              <!-- 右侧重复计数 -->
              <div class="shrink-0 flex items-start pt-0.5 pr-1 gap-1">
                <div v-if="item.count && item.count > 1"
                  class="px-1.5 py-0.5 rounded-full bg-bg-overlay/10 text-text-main text-[0.7rem] font-bold">
                  x{{ item.count }}
                </div>
                <!-- 复制按钮 -->
                <button @click="copyLogContent([item])" class="p-1 rounded opacity-0 group-hover/row:opacity-100 hover:bg-bg-overlay/10 text-text-dim hover:text-text-main transition-all" v-tooltip="'复制日志内容'">
                  <Copy class="w-4 h-4" />
                </button>
              </div>
            </div>
          </DynamicScrollerItem>
        </template>
      </DynamicScroller>

      <div v-else-if="!loadingFile" class="h-full flex flex-col items-center justify-center text-text-disabled">
        <svg class="w-12 h-12 mb-2 opacity-20" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>
        <span>暂无与当前筛选条件匹配的日志。</span>
      </div>

    </div>
  </div>
</template>

<script setup>
import {  ref, computed, onMounted, onUnmounted, nextTick, onActivated, onDeactivated, watch } from 'vue'
import { useToast } from 'vue-toastification'
import { useAppStore } from '../../app/stores/appStore'
import { useLogStore } from './logStore'
import { useProfileStore } from '../profiles/profileStore'
import { formatFileSize } from '../../shared/lib/format'
import { Copy } from 'lucide-vue-next'
import { checkResult } from '../../shared/lib/common'

const props = defineProps({
  sourceType: { type: String, default: 'app' } // 'app' or 'game'
})
const emit = defineEmits(['selection-change'])

const appStore = useAppStore()
const logStore = useLogStore()
const profileStore = useProfileStore()
const toast = useToast()

// 数据状态
const files = ref([])
const allLoadedLogs = ref([]) // 本地缓存的日志数组

// 分页与懒加载状态
const loadingFile = ref(false)
const loadingMore = ref(false)
const currentPage = ref(1)
const hasMore = ref(true)
const scrollerRef = ref(null)

const autoScroll = ref(true);

// 过滤与搜索
const filters = ref({ INFO: true, WARNING: true, ERROR: true, DEBUG: false })
const searchQuery = ref('')
const timeFilter = ref({ start: '', end: '' })

let isComponentActive = false; // KeepAlive 状态追踪
// 【防 OOM 配置】前端最大保留的日志条数
const MAX_FRONTEND_LOGS = 3000; // 内存保护

const selectedFile = computed({
  get: () => logStore.getSourceState(props.sourceType).selectedFile,
  set: (value) => {
    logStore.setSelectedFile(props.sourceType, value)
  }
})

const runtimeProfileId = computed(() => String(appStore.runtimeSession?.profile_id || '').trim())
const runtimeProfileName = computed(() => {
  const runtimeProfile = (profileStore.profiles || []).find(item => item.id === runtimeProfileId.value)
  return runtimeProfile?.name || runtimeProfileId.value || 'default'
})
const showRuntimeProfileSwitch = computed(() => {
  if (props.sourceType !== 'game') return false
  if (appStore.runtimeSession?.state !== 'running') return false
  if (!runtimeProfileId.value) return false
  return runtimeProfileId.value !== String(profileStore.currentProfileId || '').trim()
})

async function switchToRuntimeProfile() {
  if (!runtimeProfileId.value) return
  await profileStore.switchProfile(runtimeProfileId.value)
}

const selectedIds = computed({
  get: () => logStore.getSourceState(props.sourceType).selectedIds,
  set: (value) => {
    logStore.replaceSelection({
      sourceType: props.sourceType,
      filename: selectedFile.value,
      selectedIds: Array.isArray(value) ? value : [],
      selectedLogs: allLoadedLogs.value.filter(log => (Array.isArray(value) ? value : []).includes(log.id)),
      syncAttachment: true,
      resetTokenInfoWhenEmpty: true,
    })
  }
})

// 判断一条日志是否需要折叠显示（多行长日志）
function shouldFoldBlock(block) {
  const msg = block.message || '';
  const lineCount = msg.split(/\r?\n/).length;
  const startsWithLoading = msg.startsWith('Loading game from file');
  // 规则：
  // 1. 以 "Loading game from file" 开头的日志默认折叠；
  // 2. 总行数超过 3 行的日志默认折叠。
  return startsWithLoading || lineCount > 3;
}

function escapeHtml(text = '') {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function renderColoredLogText(text = '') {
  if (!text) return '';

  const normalized = text
    .replace(/\r\n/g, '\n')
    .replace(/\r/g, '\n')
    .replace(/\\n/g, '\n');

  const colorPlaceholders = [];
  const withTokens = normalized
    .replace(/<color="?(#[0-9a-fA-F]{6}|#[0-9a-fA-F]{8}|[a-zA-Z]+)"?>/gi, (_, color) => {
      const token = `@@LOG_COLOR_OPEN_${colorPlaceholders.length}@@`;
      colorPlaceholders.push(`<span style="color:${color}">`);
      return token;
    })
    .replace(/<\/color>/gi, '@@LOG_COLOR_CLOSE@@');

  let safeHtml = escapeHtml(withTokens);

  colorPlaceholders.forEach((openTag, index) => {
    safeHtml = safeHtml.replaceAll(`@@LOG_COLOR_OPEN_${index}@@`, openTag);
  });

  return safeHtml.replace(/@@LOG_COLOR_CLOSE@@/g, '</span>');
}

// 统一预处理 Block：仅保留颜色标签，其余内容按纯文本显示
function normalizeBlock(raw) {
  const base = {
    ...raw,
    _expanded: false
  };

  base._parsedMessage = renderColoredLogText(raw.message || '');

  base._folded = shouldFoldBlock(raw);

  if (!base.count) {
    base.count = 1;
  }

  return base;
}

function stringifyDiagnosticValue(value) {
  if (value === null || value === undefined || value === '') return ''
  if (typeof value === 'string') return value
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

function formatLogPhase(value) {
  const phase = String(value || '').trim()
  if (phase === 'startup') return '启动阶段'
  if (phase === 'runtime') return '运行阶段'
  return '阶段未知'
}

function formatLogDiagnosticDetails(log) {
  const parts = []
  const context = log?.context || {}
  if (context.phase) {
    parts.push(`阶段: ${formatLogPhase(context.phase)}`)
  }
  if (context.diagnosisExplanation) {
    parts.push(`说明: ${context.diagnosisExplanation}`)
  }
  if (Array.isArray(context.relatedNamespaces) && context.relatedNamespaces.length) {
    parts.push(`可疑来源: ${context.relatedNamespaces.join(', ')}`)
  }
  if (log?.error_code) {
    parts.push(`错误码: ${log.error_code}`)
  }
  const extraContext = stringifyDiagnosticValue(log?.extra_context)
  if (extraContext) {
    parts.push(`诊断信息:\n${extraContext}`)
  }
  return parts.join('\n')
}

// 提取纯净日志文本
const copyLogContent = async (logsArray) => {
  if (!logsArray || logsArray.length === 0) return;
  const textToCopy = logsArray.map(l => {
    const msg = l.message || '';
    const detailsText = [l.details, formatLogDiagnosticDetails(l)].filter(Boolean).join('\n\n');
    const details = detailsText ? `\n[诊断详情]\n${detailsText}` : '';
    return `${msg}${details}`;
  }).join('\n\n------\n\n');

  try {
    await navigator.clipboard.writeText(textToCopy);
    toast.success(`成功复制 ${logsArray.length} 条日志`);
  } catch (err) {
    toast.error('复制失败，可能是浏览器权限限制');
  }
}

// 暴露给父组件(LogViewer)使用的批量复制方法
defineExpose({
  clearSelection: () => {
    logStore.clearSelection(props.sourceType)
  },
  copySelection: () => {
    const selectedObjects = logStore.getSelectedLogs(props.sourceType)
    copyLogContent(selectedObjects);
  },
  // 获取全局错误供一键排错使用
  getGlobalErrorLogs: () => {
    return allLoadedLogs.value.filter(l => l.level === 'ERROR' || l.level === 'WARNING' || l.level === 'EXCEPTION');
  },
  // 暴露当前文件名给父组件调用预检接口
  selectedFile: selectedFile
})


// --- 模式判断 ---
const LIVE_FILES = {
  app: ['app.log'],
  game: ['RimCrow_Realtime.log']
};
const isLiveView = computed(() => LIVE_FILES[props.sourceType]?.includes(selectedFile.value));

// 当前源类型下，匹配到的“实时文件”名（app: app.log, game: RimCrow_Realtime.log）
const liveFileName = computed(() => {
  const candidates = LIVE_FILES[props.sourceType] || [];
  const match = files.value.find(f => candidates.includes(f.name));
  return match ? match.name : '';
});

// 等待后端 pywebview 注入完成，避免组件过早初始化导致第一次为空
function waitForBackend() {
  return new Promise((resolve) => {
    if (typeof window === 'undefined') {
      resolve();
      return;
    }
    if (window.pywebview) {
      resolve();
    } else {
      const handler = () => {
        window.removeEventListener('pywebviewready', handler);
        resolve();
      };
      window.addEventListener('pywebviewready', handler, { once: true });
    }
  });
}

// --- 生命周期控制 ---
onMounted(async () => {
  isComponentActive = true
  // 确保后端就绪后再加载日志文件，避免第一次进入时拿不到文件列表
  await waitForBackend()
  await initPanel()
})

onUnmounted(() => {
  isComponentActive = false
  cleanupPanel()
})

// 兼容 KeepAlive 缓存组件的情况
onActivated(async () => {
  isComponentActive = true
  if (allLoadedLogs.value.length === 0) {
    await initPanel();
  } else if (isLiveView.value) {
    startRealtimeListener();
  }
});

onDeactivated(() => {
  // 隐藏组件时，必须清理定时器和事件，防止后台偷跑占用资源
  isComponentActive = false
  cleanupPanel()
})

// --- 监听器 ---
// 监听 sourceType 变化 (防御性设计，如果父组件动态改 props)
watch(() => props.sourceType, async (newVal) => {
  if (isComponentActive) {
    cleanupPanel()
    files.value = []
    allLoadedLogs.value = []
    await initPanel()
  }
})

watch(() => profileStore.currentProfileId, async (_newProfileId, oldProfileId) => {
  if (!isComponentActive || props.sourceType !== 'game') return
  const previousProfileId = String(oldProfileId || '').trim()
  const currentProfileId = String(profileStore.currentProfileId || '').trim()
  if (!currentProfileId || currentProfileId === previousProfileId) return

  // 游戏日志面板跟随当前活动环境。
  // 只要活动环境切换了，就立刻重载文件列表和内容，避免按钮切过去后仍停留在旧环境日志。
  cleanupPanel()
  files.value = []
  allLoadedLogs.value = []
  await initPanel()
})
// 初始化流程封装
async function initPanel() {
  loadingFile.value = true;
  cleanupPanel();
  await fetchFiles();
  if (files.value.length > 0) {
    // 优先选择实时文件作为默认文件，其次才是最新的普通日志文件
    const liveCandidates = LIVE_FILES[props.sourceType] || [];
    const liveFile = files.value.find(f => liveCandidates.includes(f.name));
    const storedFilename = normalizeStoredFilename(files.value, selectedFile.value)
    const targetName = storedFilename || (liveFile ? liveFile.name : files.value[0].name);
    // 关键：等待文件切换和首屏数据加载完成
    await switchFile(targetName, { preserveSelection: !!storedFilename && storedFilename === targetName });
  }
  loadingFile.value = false;
}

function cleanupPanel() {
  stopRealtimeListener();
}


async function fetchFiles() {
  if (!window.pywebview) return;
  try {
    const res = await window.pywebview.api.get_log_files(String(props.sourceType), 'active');
    if (checkResult(res, '获取日志文件', false)) {
      files.value = res.data || [];
    }
  } catch (e) {
    toast.error('获取日志文件列表失败。请稍后重试，或检查日志目录是否可访问。');
  }
}

function normalizeStoredFilename(filesList = [], filename = '') {
  const normalizedFilename = String(filename || '').trim()
  if (!normalizedFilename) return ''
  return filesList.some(file => file?.name === normalizedFilename) ? normalizedFilename : ''
}

// 一键切换到实时文件（如果存在）
function switchToLive() {
  if (!liveFileName.value) return;
  if (selectedFile.value === liveFileName.value && isLiveView.value) return;
  switchFile(liveFileName.value);
}

// 切换文件，重置分页
async function switchFile(filename) {
  if (!filename) return;
  return switchFileWithOptions(filename, { preserveSelection: false })
}

async function switchFileWithOptions(filename, { preserveSelection = false } = {}) {
  if (!filename) return;

  loadingFile.value = true;
  cleanupPanel(); // 清理旧的监听
  if (!preserveSelection) {
    logStore.clearSelection(props.sourceType, {
      preserveFile: false,
      removeAttachment: true,
      resetTokenInfo: true,
    })
  }

  selectedFile.value = filename;
  currentPage.value = 1;
  hasMore.value = true;
  allLoadedLogs.value = [];

  // 加载首屏数据 (page=1, isInitial=true)
  await fetchPage(1, false, true);

  // 如果是实时模式，启动监听
  if (isLiveView.value) {
    startRealtimeListener();
  }

  loadingFile.value = false;
}

// 强制重新读取（清空缓存）
function reloadAll() {
  if (selectedFile.value) {
    switchFileWithOptions(selectedFile.value, { preserveSelection: true });
  }
}

// 核心懒加载与轮询逻辑
// isScrollUp: 向上拉加载历史 (插入头部)
// isPolling: 定时器后台刷新最新数据 (插入尾部)
async function fetchPage(page, isScrollUp = false, isInitial = false) {
  if (!window.pywebview || !selectedFile.value) return;

  try {
    const res = await window.pywebview.api.read_log_page(String(props.sourceType), String(selectedFile.value), Number(page), 500, 'active');

    if (res && res.status === 'success') {
      const newBlocks = res.data.blocks.map(b => normalizeBlock(b));
      hasMore.value = res.data.has_more;

      if (isInitial) {
        allLoadedLogs.value = newBlocks;
        logStore.refreshSelectedSnapshotsFromLoadedLogs(props.sourceType, allLoadedLogs.value)
        if (autoScroll.value) {
          nextTick(() => scrollerRef.value?.scrollToBottom());
        }
      } else if (isScrollUp) {
        const scroller = scrollerRef.value?.$el;
        const oldScrollHeight = scroller ? scroller.scrollHeight : 0;
        const oldScrollTop = scroller ? scroller.scrollTop : 0;

        allLoadedLogs.value = [...newBlocks, ...allLoadedLogs.value];
        _enforceMemoryLimit({ keep: 'oldest' });
        logStore.refreshSelectedSnapshotsFromLoadedLogs(props.sourceType, allLoadedLogs.value)

        nextTick(() => {
          if (scroller) {
            const newScrollHeight = scroller.scrollHeight;
            scroller.scrollTop = oldScrollTop + (newScrollHeight - oldScrollHeight);
          }
        });
      }
    }
  } catch (e) {
    toast.error('读取日志失败。请确认日志文件仍存在且没有被其它程序占用。');
  }
}

function startRealtimeListener() {
  const eventName = props.sourceType === 'app' ? 'app-log' : 'game-log';
  window.addEventListener(eventName, handleRealtimeLog);
}

function stopRealtimeListener() {
  window.removeEventListener('app-log', handleRealtimeLog);
  window.removeEventListener('game-log', handleRealtimeLog);
}

// 实时日志接收 (适用于 App 和 Game)
function handleRealtimeLog(e) {
  if (!isLiveView.value || !isComponentActive) return;

  const entry = e.detail;
  const scroller = scrollerRef.value?.$el;
  const isAtBottom = scroller && (scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight < 50);

  // 简单的去重与计数累加
  const lastLog = allLoadedLogs.value[allLoadedLogs.value.length - 1];
  if (lastLog && lastLog.message === entry.message && lastLog.level === entry.level && lastLog.details === entry.details && lastLog.error_code === entry.error_code && stringifyDiagnosticValue(lastLog.extra_context) === stringifyDiagnosticValue(entry.extra_context)) {
    lastLog.count = (lastLog.count || 1) + 1;
    lastLog.timestamp = entry.timestamp;
    lastLog.raw_lines = [...new Set([...(lastLog.raw_lines || []), ...(entry.raw_lines || [])])];
    // 强制 Vue 更新
    allLoadedLogs.value.splice(allLoadedLogs.value.length - 1, 1, { ...lastLog });
  } else {
    allLoadedLogs.value.push(normalizeBlock(entry));
    _enforceMemoryLimit({ keep: 'latest' });
  }
  logStore.refreshSelectedSnapshotsFromLoadedLogs(props.sourceType, allLoadedLogs.value)

  if (autoScroll.value && isAtBottom) {
    nextTick(() => scrollerRef.value?.scrollToBottom());
  }
}
function _enforceMemoryLimit({ keep = 'latest' } = {}) {
  if (allLoadedLogs.value.length > MAX_FRONTEND_LOGS) {
    const overflowCount = allLoadedLogs.value.length - MAX_FRONTEND_LOGS;
    if (keep === 'oldest') {
      allLoadedLogs.value.splice(MAX_FRONTEND_LOGS, overflowCount);
      return;
    }
    allLoadedLogs.value.splice(0, overflowCount);
    hasMore.value = true; // 实时日志挤掉了旧窗口，顶部仍可重新分段加载历史
  }
}


// 监听滚动，触顶加载
async function onScroll(e) {
  if (loadingMore.value || !hasMore.value) return;
  if (e.target.scrollTop < 100) {
    loadingMore.value = true;
    currentPage.value++;
    await fetchPage(currentPage.value, true, false);
    loadingMore.value = false;
  }
}

// === 计算属性：过滤与搜索 ===
const filteredLogs = computed(() => {
  let result = allLoadedLogs.value.filter(l => filters.value[l.level])

  // 1. 时间过滤
  if (timeFilter.value.start || timeFilter.value.end) {
    const start = timeFilter.value.start ? timeFilter.value.start + ':00' : '00:00:00'
    const end = timeFilter.value.end ? timeFilter.value.end + ':59' : '23:59:59'
    result = result.filter(l => {
      if (!l.timestamp) return true // 没时间的日志放行 (比如普通游戏报错)
      const t = l.timestamp.includes(' ') ? l.timestamp.split(' ')[1] : l.timestamp
      return t >= start && t <= end
    })
  }

  // 2. 正则搜索
  if (searchQuery.value) {
    try {
      const re = new RegExp(searchQuery.value, 'i')
      result = result.filter(l => {
        const ctx = l.context || {};
        const diagnostics = formatLogDiagnosticDetails(l);
        return re.test(l.message || '') ||
               re.test(l.details || '') ||
               re.test(diagnostics) ||
               (ctx.inferredType && re.test(ctx.inferredType)) ||
               (Array.isArray(ctx.relatedModIds) && ctx.relatedModIds.some(id => re.test(id))) ||
               (Array.isArray(ctx.relatedFiles) && ctx.relatedFiles.some(f => re.test(f)));
      })
    } catch(e) {
      // 正则不合法时，降级为普通包含匹配
      const q = searchQuery.value.toLowerCase()
      result = result.filter(l => {
        const ctx = l.context || {};
        const msg = (l.message || '').toLowerCase();
        const det = (l.details || '').toLowerCase();
        const diagnostics = formatLogDiagnosticDetails(l).toLowerCase();
        const inferred = (ctx.inferredType || '').toLowerCase();
        const mods = (ctx.relatedModIds || []).map(x => (x || '').toLowerCase());
        const files = (ctx.relatedFiles || []).map(x => (x || '').toLowerCase());
        return msg.includes(q) ||
               det.includes(q) ||
               diagnostics.includes(q) ||
               inferred.includes(q) ||
               mods.some(x => x.includes(q)) ||
               files.some(x => x.includes(q));
      })
    }
  }

  return result
})

// 提取当前过滤后日志的所有 ID，提供给 vSelection 计算 Shift 连选范围
const filteredLogIds = computed(() => {
  return filteredLogs.value.map(log => log.id)
})

// v-selectable-list 指令的配置对象
const selectionConfig = computed(() => ({
  data: filteredLogIds.value,     // 当前列表数据的全集 IDs
  selectedIds: selectedIds.value, // 当前已选中的 IDs
  clickClass: 'swipe-trigger',    // 点击和拖拽都只在左侧复选框区域触发
  swipeClass: 'swipe-trigger',    // 保持与 clickClass 同一区域，但由指令内部区分点击/拖拽
  clickMode: 'toggle',            // 日志勾选更接近复选框语义：点击默认切换多选
  idAttribute: 'data-id',         // DOM 绑定的 ID 属性
  onSelect: (newSelectedIds, anchorId) => {
    // 日志多选可能一次选中大量行，用 Set 避免每条日志都 includes 扫描选中数组。
    const selectedSet = new Set(newSelectedIds)
    const nextSelectedLogs = allLoadedLogs.value.filter(log => selectedSet.has(log.id))
    logStore.replaceSelection({
      sourceType: props.sourceType,
      filename: selectedFile.value,
      selectedIds: newSelectedIds,
      selectedLogs: nextSelectedLogs,
      syncAttachment: true,
      resetTokenInfoWhenEmpty: true,
    })
    emit('selection-change', nextSelectedLogs)
  },
  onClear: () => {
    logStore.clearSelection(props.sourceType)
    emit('selection-change', [])
  }
}))



// === 辅助工具 ===
const formatTime = (ts) => {
  if (!ts) return ''
  return ts.includes(' ') ? ts.split(' ')[1].substring(0,8) : ts.substring(0,8)
}

const getRowSizeDependencies = (item) => {
  const context = item.context || {}
  return [
    item._folded,
    item._expanded,
    item.count || 1,
    searchQuery.value,
    item._parsedMessage || '',
    item.details || '',
    item.error_code || '',
    stringifyDiagnosticValue(item.extra_context),
    context.module || '',
    context.func || '',
    context.path || '',
    context.inferredType || '',
    (context.relatedFiles || []).join('|'),
    (context.relatedModIds || []).join('|')
  ]
}

// 预编译当前搜索词的高亮正则，避免在每条日志上重复构造 RegExp
const searchRegex = computed(() => {
  if (!searchQuery.value) return null;
  try {
    return new RegExp(`(${searchQuery.value})`, 'gi');
  } catch (e) {
    return null;
  }
});

// 高亮已经预解析好的 HTML 内容
const highlightHtml = (html) => {
  if (!html) return '';
  const re = searchRegex.value;
  if (!re) return html;

  const placeholders = [];
  const protectedHtml = html.replace(/<\/?span(?:\s+style="[^"]*")?>/gi, (match) => {
    const token = `@@LOG_HTML_${placeholders.length}@@`;
    placeholders.push(match);
    return token;
  });

  let highlighted = protectedHtml.replace(re, '<mark class="bg-accent-primary/40 text-text-main rounded px-0.5">$1</mark>');

  placeholders.forEach((tag, index) => {
    highlighted = highlighted.replaceAll(`@@LOG_HTML_${index}@@`, tag);
  });

  return highlighted;
}

const getBtnColor = (lvl) => {
  if (lvl === 'INFO') return 'bg-accent-success/20 text-accent-success border-accent-success/30 shadow-sm'
  if (lvl === 'WARNING') return 'bg-accent-warn/20 text-accent-warn border-accent-warn/30 shadow-sm'
  if (lvl === 'DEBUG') return 'bg-accent-primary/20 text-accent-primary border-accent-primary/30 shadow-sm'
  return 'bg-accent-danger/20 text-accent-danger border-accent-danger/30 shadow-sm'
}

const getBorderClass = (lvl) => {
  if (lvl === 'ERROR') return 'border-accent-danger/60 bg-accent-danger/5'
  if (lvl === 'WARNING') return 'border-accent-warn/40 bg-accent-warn/5'
  if (lvl === 'DEBUG') return 'border-accent-primary/40 bg-accent-primary/5'
  return 'border-border-base/10'
}

// 根据级别调整正文文字颜色，提高信息对比度
const getMessageTextClass = (lvl) => {
  if (lvl === 'ERROR') return 'text-accent-danger'
  if (lvl === 'WARNING') return 'text-accent-warn'
  if (lvl === 'DEBUG') return 'text-accent-primary'
  return 'text-text-main'
}

// 唤起侧边栏查看 Mod
const openMod = (modId) => {
  // 触发全局总线或 store，通知主界面打开该 Mod
  toast.info(`正在查询 Mod: ${modId}`)
  // TODO: appStore.openModDetails(modId)
}
</script>

<style scoped>
.custom-scrollbar::-webkit-scrollbar { width: 8px; height: 8px; }
.custom-scrollbar::-webkit-scrollbar-track { background: transparent; }
.custom-scrollbar::-webkit-scrollbar-thumb { background: var(--color-border-strong); border-radius: 4px; border: 2px solid var(--color-bg-inset); }
.custom-scrollbar::-webkit-scrollbar-thumb:hover { background: var(--color-accent-primary); }

/* 多行日志默认折叠时使用的渐隐效果，控制高度约为三行左右 */
.log-body-collapsed {
  max-height: 4.5em;
  overflow: hidden;
  position: relative;
}
.log-body-collapsed::after {
  content: "";
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  height: 1.5em;
  background: linear-gradient(to top, var(--color-bg-inset), transparent);
}
</style>
