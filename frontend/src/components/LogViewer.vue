<template>
  <transition name="panel-fade">
    <div v-if="appStore.uiState.showLogDrawer" 
      class="fixed inset-0 z-100 flex items-center justify-center bg-bg-deep/60 backdrop-blur-md"
      @click.self="appStore.uiState.showLogDrawer = false">
      
      <div class="fixed top-0 left-0 w-full h-full p-10 bg-black/50 backdrop-blur-2xl rounded-lg z-999 flex gap-4 overflow-hidden" @click.self="appStore.uiState.showLogDrawer = false">
        <!-- ================= 左侧：日志主体区 ================= -->
        <div data-tour="log-viewer-panel" class="flex-1 flex flex-col h-full bg-bg-surface/40 backdrop-blur-md rounded-2xl border border-text-main/10 shadow-2xl relative group overflow-hidden transition-all duration-300">
          
          <!-- 1. 顶部控制台 (Header & Toolbar) -->
          <div class="shrink-0 bg-bg-deep/50 border-b border-text-main/5 backdrop-blur-xl z-20">
            <div class="flex items-center justify-between px-4 h-12">
              
              <!-- 模式切换 Tabs -->
              <div data-tour="log-viewer-tabs" class="flex p-1 bg-black/20 rounded-lg border border-text-main/5">
                <button v-for="tab in tabs" :key="tab.id" @click="currentTab = tab.id" :data-tour="`log-tab-${tab.id}`"
                  class="px-4 py-1 rounded-md text-sm font-bold transition-all duration-300 flex items-center gap-2 relative overflow-hidden"
                  :class="currentTab === tab.id ? 'text-text-main shadow-lg bg-text-main/10' : 'text-text-dim hover:text-text-main hover:bg-text-main/5'">
                  <div v-if="currentTab === tab.id" class="absolute bottom-0 left-0 w-full h-0.5 bg-accent-primary shadow-[0_0_8px_var(--color-accent-primary)]"></div>
                  <component :is="tab.icon" class="w-3.5 h-3.5" />
                  {{ tab.label }}
                </button>
              </div>

              <!-- 右侧区域：统计看板 + AI 侧边栏开关 -->
              <div class="flex items-center gap-4 text-xs font-mono select-none">
                <!-- 游戏日志，或（软件日志 + Debug模式）才允许使用 AI -->
                <template v-if="currentTab === 'game' || appStore.settings.debug_mode">
                  <CommonSwitch class="col-span-1" label="使用辅助工具模组" v-model="enable_tool_mods" mini description="开启后，将在保存或自动排序时自动启用辅助工具模组，提供为软件提供更加详细的游戏日志获取功能。" />
                  <!-- 一键分析 -->
                  <button data-tour="log-viewer-auto-analyze" @click="autoAnalyzeGlobalErrors" class="px-3 py-1.5 rounded-lg flex items-center gap-2 transition-all border bg-accent-danger/10 border-accent-danger/30 text-accent-danger hover:bg-accent-danger hover:text-white shadow-[0_0_10px_rgba(239,68,68,0.1)]">
                    <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
                    <span class="font-bold">一键分析</span>
                  </button>
                  
                  <!-- 手动开关 AI 侧边栏按钮 -->
                  <button data-tour="log-viewer-ai-toggle" @click="showAiSidebar = !showAiSidebar" class="px-3 py-1.5 rounded-lg flex items-center gap-2 transition-all border"
                          :class="showAiSidebar ? 'bg-accent-special/20 border-accent-special/50 text-accent-special shadow-[0_0_10px_rgba(139,92,246,0.2)]' : 'bg-black/20 border-text-main/10 text-text-dim hover:text-accent-special'">
                    <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" /></svg>
                    <span class="font-bold">{{ showAiSidebar ? '隐藏 AI 助手' : '打开 AI 助手' }}</span>
                  </button>

                </template>
              </div>

            </div>
          </div>

          <!-- 2. 日志内容区 (Log Stream) -->
          <div data-tour="log-viewer-stream" class="flex-1 min-h-0 bg-black/20 font-mono text-sm relative">
            <KeepAlive>
              <UnifiedLogPanel :key="currentTab" :source-type="currentTab" ref="logPanelRef" @selection-change="handleSelectedLogsUpdate" />
            </KeepAlive>

            <!-- 悬浮操作条 (Floating Action Bar) -->
            <!-- 当用户在左侧勾选了日志，且 AI 侧边栏未打开时，在底部弹出提示 -->
            <transition name="fade-up">
              <div v-if="selectedLogs.length > 0 && !showAiSidebar && (currentTab === 'game' || appStore.settings.debug_mode)" 
                  class="absolute bottom-6 left-1/2 -translate-x-1/2 bg-bg-deep/95 border border-accent-primary/30 shadow-[0_10px_30px_rgba(0,0,0,0.8)] backdrop-blur-xl rounded-full px-5 py-2.5 flex items-center gap-4 z-30">
                
                <div class="flex items-center gap-2 text-sm">
                  <span class="w-2.5 h-2.5 rounded-full bg-accent-primary animate-pulse"></span>
                  <span class="text-text-main">已选 <strong class="text-accent-primary">{{ selectedLogs.length }}</strong> 条</span>
                </div>
                
                <!-- 即时 Token 状态显示 -->
                <div v-if="tokenInfo.isLoading" class="flex items-center gap-1 text-text-dim text-xs">
                  <svg class="w-3 h-3 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg>
                  <span>估算中...</span>
                </div>
                <div v-else class="flex items-center gap-1.5 text-xs font-bold" :class="getTokenColor(tokenInfo.estimated, tokenInfo.limit)">
                  <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
                  <span>{{ tokenInfo.estimated }} / {{ tokenInfo.limit }} TK</span>
                </div>
                <div class="w-px h-4 bg-text-main/20"></div>
                
                <button @click="showAiSidebar = true" :disabled="tokenInfo.isLoading"
                  class="text-sm font-bold text-accent-special hover:text-white transition-colors flex items-center gap-1 disabled:opacity-50">
                  AI 分析 
                  <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14 5l7 7m0 0l-7 7m7-7H3" /></svg>
                </button>
                <!-- 复制内容 -->
                <button @click="triggerCopy" class="text-text-dim hover:text-text-main p-1.5 rounded-full bg-black/20 ml-2" v-tooltip="'复制选中内容'">
                  <Copy class="w-4 h-4" />
                </button>
                
                <button @click="clearLogSelection" class="text-text-dim hover:text-accent-danger p-1.5 rounded-full bg-black/20" v-tooltip="'取消选择'">
                  <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" /></svg>
                </button>
              </div>
            </transition>
          </div>

        </div>

        <!-- ================= 右侧：AI 诊断侧边栏 ================= -->
        <!-- 使用我们新创建的组件，并通过 v-model 控制显隐 -->
        <AiDiagnosticSidebar  v-model="showAiSidebar" :assistant-id="currentAssistantId"
          :auto-start-request="autoDiagnosisRequest" :source-type="currentTab" :filename="activeFilename">
        </AiDiagnosticSidebar>

      </div>
    </div>
  </transition>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { Terminal, Gamepad2, Copy } from 'lucide-vue-next'
import { useAppStore } from '../stores/appStore'
import { useLogStore } from '../stores/logStore'
import { useToast } from 'vue-toastification'
import UnifiedLogPanel from './utils/UnifiedLogPanel.vue';
import AiDiagnosticSidebar from './ai/AiDiagnosticSidebar.vue'
import CommonSwitch from './common/input/CommonSwitch.vue';


// -----------------------------------------------------------------
// Store 依赖 (Stores)
// -----------------------------------------------------------------
const appStore = useAppStore()
const logStore = useLogStore()
const toast = useToast()

// -----------------------------------------------------------------
// 状态定义 (State / Refs)
// -----------------------------------------------------------------
const currentTab = ref('game') // 'app' | 'game'
const tabs = [
  { id: 'game', label: '游戏日志', icon: Gamepad2, assistantId: 'assistant.log_game' },
  { id: 'app', label: '系统日志', icon: Terminal, assistantId: 'assistant.log_app' }
]
const currentAssistantId = computed(() => tabs.find(tab => tab.id === currentTab.value)?.assistantId || 'assistant.log_game')

// AI 诊断侧栏和附件状态与当前日志来源强绑定。
const showAiSidebar = computed({
  get: () => logStore.showSidebar,
  set: (value) => {
    logStore.showSidebar = !!value
  }
})
const selectedLogs = computed(() => logStore.selectedLogsBySource[currentTab.value] || [])
const logPanelRef = ref(null)      // 引用当前的 UnifiedLogPanel 组件实例
const autoDiagnosisRequest = ref(null)
const isGlobalScanning = ref(false)
const tokenInfo = computed(() => logStore.tokenInfoBySource[currentTab.value] || {
  isLoading: false,
  estimated: 0,
  limit: 32000,
  isOverLimit: false,
  condensedData: null,
})
const activeFilename = computed(() => logStore.getSourceState(currentTab.value)?.selectedFile || '')

const enable_tool_mods = computed({
  get() {
    return appStore.settings.enable_tool_mods ?? true
  },
  set(val) {
    appStore.saveSetting('enable_tool_mods', val)
  }
})

const resetAttachmentState = () => {
  // 切文件、切标签或清空选择时，需要同时重置 token 估算和附件草稿，
  // 否则 AI 会带着旧日志上下文继续对话。
  clearTimeout(debounceTimer)
  logStore.clearSelection(currentTab.value)
  autoDiagnosisRequest.value = null
  logStore.beginSelectionRequest(currentTab.value)
}

// -----------------------------------------------------------------
// 工具方法 (Utils)
// -----------------------------------------------------------------
let debounceTimer = null
const createEmptyTokenInfo = () => ({
  /** 创建日志面板本地使用的默认 token 状态，占位时无需依赖 store 初始化顺序。 */
  isLoading: false,
  estimated: 0,
  limit: 32000,
  isOverLimit: false,
  condensedData: null
})

// -----------------------------------------------------------------
// 业务方法 (Methods)
// -----------------------------------------------------------------
const handleSelectedLogsUpdate = (logs) => {
  // 全局扫描模式下，底层面板会先触发一次“清空选择”事件；
  // 这里必须忽略它，避免刚生成的全局摘要附件被误删。
  if (isGlobalScanning.value && logs.length === 0) return
  if (logs.length === 0) {
    logStore.clearSelection(currentTab.value)
    logStore.beginSelectionRequest(currentTab.value)
    return
  }

  logStore.replaceSelection({
    sourceType: currentTab.value,
    filename: activeFilename.value,
    selectedLogs: logs,
    syncAttachment: true,
  })
  logStore.setTokenInfo(currentTab.value, {
    ...createEmptyTokenInfo(),
    isLoading: true,
  }, { syncAttachment: true })

  clearTimeout(debounceTimer)
  const requestSeq = logStore.beginSelectionRequest(currentTab.value)
  debounceTimer = setTimeout(async () => {
    await fetchTokenEstimate(logs, requestSeq)
  }, 500)
}
// 估算结果只用于提示和请求预算判断，不作为后端硬限制依据。
const fetchTokenEstimate = async (logs, requestSeq) => {
  try {
    await logStore.estimateSelectionTokenInfo({
      sourceType: currentTab.value,
      filename: activeFilename.value,
      logs,
      requestSeq,
    })
  } catch (e) {
    console.error('Token 计算失败:', e)
  }
}

const getTokenColor = (est, limit) => {
  /** 根据 token 占用比例返回提示色，帮助用户快速判断是否接近模型上限。 */
  if (!limit || limit === 0) return 'text-text-main'
  const ratio = est / limit
  if (ratio > 0.9) return 'text-accent-danger'
  if (ratio > 0.6) return 'text-accent-warn'
  return 'text-accent-success'
}

const triggerCopy = () => {
  /** 把复制动作透传给当前活动日志面板实例。 */
  const panel = Array.isArray(logPanelRef.value) ? logPanelRef.value[0] : logPanelRef.value
  if (panel && typeof panel.copySelection === 'function') {
    panel.copySelection()
  }
}
const clearLogSelection = () => {
  /**
   * 清空当前日志选择，并同步重置附件与侧栏联动状态。
   *
   * 这里既会清理 store，也会驱动子组件清空框选视觉状态。
   */
  isGlobalScanning.value = false
  resetAttachmentState()
  if (logPanelRef.value) {
    // KeepAlive 下组件 ref 可能被包装成数组代理，这里统一取首项兼容。
    const panel = Array.isArray(logPanelRef.value) ? logPanelRef.value[0] : logPanelRef.value;
    if (panel && typeof panel.clearSelection === 'function') {
      panel.clearSelection()
    }
  }
}

// -----------------------------------------------------------------
// 副作用监听 (Watchers)
// -----------------------------------------------------------------
watch(currentTab, () => {
  isGlobalScanning.value = false
  autoDiagnosisRequest.value = null
})

const autoAnalyzeGlobalErrors = async () => {
  /**
   * 发起“全局摘要分析”。
   *
   * 这条链路与普通框选不同：它会先请求后端压缩整份日志，再把压缩摘要
   * 作为一条特殊 diagnosis_context 附件交给 AI 会话自动开聊。
   */
  const panel = Array.isArray(logPanelRef.value) ? logPanelRef.value[0] : logPanelRef.value
  const currentFilename = panel?.selectedFile || ''
  if (!currentFilename || !window.pywebview) {
    toast.warning("未选中任何日志文件。")
    return
  }

  toast.info("正在扫描全部日志，请稍候...", { timeout: 3000 })
  isGlobalScanning.value = true
  
  resetAttachmentState() 
  if (panel && typeof panel.clearSelection === 'function') {
    panel.clearSelection()
  }
  autoDiagnosisRequest.value = null
  showAiSidebar.value = true
  
  const requestSeq = logStore.beginSelectionRequest(currentTab.value)

  try {
    const scanResult = await logStore.scanGlobalErrorsSelection({
      sourceType: currentTab.value,
      filename: currentFilename,
      requestSeq,
    })
    if (!scanResult) {
      clearLogSelection()
      return
    }
    const diagnosisContext = scanResult.condensedData || null
    const stats = diagnosisContext?.stats || {}
    const tocCount = stats.output_item_count || diagnosisContext?.error_table_of_contents?.length || 0
    const repeatCount = stats.total_repeat_count || 0
    const tokenText = `${(Number(scanResult.tokenInfo?.estimated || 0) / 1000).toFixed(1)}k TK`
    const notice = scanResult.notice || `压缩完成：保留 ${tocCount} 条错误摘要，共覆盖 ${repeatCount} 次错误，当前占用约 ${tokenText}。`
    toast.success(`${notice} 正在启动 AI 分析...`, { timeout: 5000 })
    autoDiagnosisRequest.value = {
      nonce: Date.now(),
    }
  } catch (e) {
    clearLogSelection()
    toast.error("全局扫描失败: " + e.message)
  }
}
</script>

<style scoped>
/* 呼吸灯动画 */
@keyframes pulse-slow {
  0%, 100% { opacity: 1; transform: scale(1); box-shadow: 0 0 15px rgba(139, 92, 246, 0.3); }
  50% { opacity: 0.8; transform: scale(0.98); box-shadow: 0 0 5px rgba(139, 92, 246, 0.1); }
}
.animate-pulse-slow {
  animation: pulse-slow 3s infinite ease-in-out;
}

/* 页面切换动画 */
.panel-fade-enter-active, .panel-fade-leave-active { transition: opacity 0.4s ease; }
.panel-fade-enter-from, .panel-fade-leave-to { opacity: 0; }
</style>
