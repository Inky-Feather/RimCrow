<template>
  <transition name="panel-fade">
    <div v-show="appStore.uiState.showLogDrawer" 
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
                <button v-for="tab in tabs" :key="tab.id" @click="currentTab = tab.id"
                  :data-tour="`log-tab-${tab.id}`"
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
                  <!-- 一键分析 -->
                  <button data-tour="log-viewer-auto-analyze" @click="autoAnalyzeGlobalErrors"
                          class="px-3 py-1.5 rounded-lg flex items-center gap-2 transition-all border bg-accent-danger/10 border-accent-danger/30 text-accent-danger hover:bg-accent-danger hover:text-white shadow-[0_0_10px_rgba(239,68,68,0.1)]">
                    <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
                    <span class="font-bold">一键分析</span>
                  </button>
                  
                  <!-- 手动开关 AI 侧边栏按钮 -->
                  <button data-tour="log-viewer-ai-toggle" @click="showAiSidebar = !showAiSidebar"
                          class="px-3 py-1.5 rounded-lg flex items-center gap-2 transition-all border"
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
              <UnifiedLogPanel :key="currentTab" :source-type="currentTab" ref="logPanelRef"
                @update:selected-logs="handleSelectedLogsUpdate"
              />
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
        <AiDiagnosticSidebar 
          v-model="showAiSidebar"
          :pending-logs="selectedLogs"
          :token-info="tokenInfo"
          :auto-start-request="autoDiagnosisRequest"
          :source-type="currentTab"
          :filename="logPanelRef?.selectedFile || ''"
          @clear-selection="clearLogSelection"
        />

      </div>
    </div>
  </transition>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { Terminal, Gamepad2, Copy } from 'lucide-vue-next'
import { useAppStore } from '../stores/appStore'
import { useToast } from 'vue-toastification'
import UnifiedLogPanel from './utils/UnifiedLogPanel.vue';
import AiDiagnosticSidebar from './utils/AiDiagnosticSidebar.vue'
import { checkResult } from '../utils/tools';


const appStore = useAppStore()
const toast = useToast()
// --- 状态数据 ---
const currentTab = ref('app') // 'app' | 'game'
const tabs = [
  { id: 'app', label: '系统日志', icon: Terminal },
  { id: 'game', label: '游戏日志', icon: Gamepad2 }
]

// AI 相关状态
const showAiSidebar = ref(false)   // 控制 AI 侧栏的开关
const selectedLogs = ref([]) 
const logPanelRef = ref(null)      // 引用当前的 UnifiedLogPanel 组件实例
const autoDiagnosisRequest = ref(null)
const isGlobalScanning = ref(false)
// 【修复 5】引入请求序号，防抖并防止旧请求覆盖新请求
let currentTokenRequestId = 0

// 【核心新增】前置 Token 计算状态
const tokenInfo = ref({
  isLoading: false,
  estimated: 0,
  limit: 32000,
  isOverLimit: false,
  condensedData: null
})

const createEmptyTokenInfo = () => ({
  isLoading: false,
  estimated: 0,
  limit: 32000,
  isOverLimit: false,
  condensedData: null
})

const resetAttachmentState = () => {
  clearTimeout(debounceTimer)
  selectedLogs.value = []
  tokenInfo.value = createEmptyTokenInfo()
  autoDiagnosisRequest.value = null
  currentTokenRequestId++
}

// 防抖计算器
let debounceTimer = null
// 接收子组件日志选中更新
const handleSelectedLogsUpdate = (logs) => {
  // 【关键修复】如果正在进行全局扫描/带有全局附件，忽略来自子组件框选的空事件更新
  if (isGlobalScanning.value && logs.length === 0) return
  selectedLogs.value = logs
  if (logs.length === 0) {
    tokenInfo.value = createEmptyTokenInfo()
    currentTokenRequestId++
    return
  }

  tokenInfo.value.isLoading = true
  clearTimeout(debounceTimer)
  
  debounceTimer = setTimeout(async () => {
    currentTokenRequestId++
    const myRequestId = currentTokenRequestId
    await fetchTokenEstimate(logs, myRequestId)
  }, 500)
}
// 调用后端的预检接口
const fetchTokenEstimate = async (logs, requestId) => {
  if (!window.pywebview) return
  
  const allRawLines = [...new Set(logs.flatMap(l => l.raw_lines || []))]
  if (allRawLines.length === 0) {
    if (requestId === currentTokenRequestId) tokenInfo.value.isLoading = false
    return
  }

  const panel = Array.isArray(logPanelRef.value) ? logPanelRef.value[0] : logPanelRef.value
  const currentFilename = panel?.selectedFile || ''

  try {
    const res = await window.pywebview.api.ai_prepare_diagnosis({
      raw_lines: allRawLines,
      filename: currentFilename,
      log_source_type: currentTab.value
    })
    
    // 如果序号匹配，才更新状态
    if (requestId === currentTokenRequestId) {
      if (checkResult(res,'Token检测')) {
        tokenInfo.value = {
          isLoading: false,
          estimated: res.data.estimated_tokens,
          limit: res.data.token_limit,
          isOverLimit: res.data.is_over_limit,
          condensedData: res.data.condensed_data
        }
      } else {
        tokenInfo.value.isLoading = false
        toast.error(res.message)
      }
    }
  } catch (e) {
    console.error("Token 计算失败:", e)
    if (requestId === currentTokenRequestId) tokenInfo.value.isLoading = false
  }
}

// 辅助方法：根据占比计算颜色
const getTokenColor = (est, limit) => {
  if (!limit || limit === 0) return 'text-text-main'
  const ratio = est / limit
  if (ratio > 0.9) return 'text-accent-danger'
  if (ratio > 0.6) return 'text-accent-warn'
  return 'text-accent-success'
}

// 触发子组件复制
const triggerCopy = () => {
  const panel = Array.isArray(logPanelRef.value) ? logPanelRef.value[0] : logPanelRef.value
  if (panel && typeof panel.copySelection === 'function') {
    panel.copySelection()
  }
}
// 供自身悬浮条或子组件调用的清空方法
const clearLogSelection = () => {
  isGlobalScanning.value = false // 【关键修复】清空时解除锁
  resetAttachmentState()
  // 调用子组件 UnifiedLogPanel 暴露的 clearSelection 方法
  if (logPanelRef.value) {
    // 处理 KeepAlive 下获取引用的兼容
    // 有时 Vue3 ref 包装的组件是一个数组或代理对象
    const panel = Array.isArray(logPanelRef.value) ? logPanelRef.value[0] : logPanelRef.value;
    if (panel && typeof panel.clearSelection === 'function') {
      panel.clearSelection()
    }
  }
}

watch(currentTab, () => {
  resetAttachmentState()
})

// 一键分析
const autoAnalyzeGlobalErrors = async () => {
  const panel = Array.isArray(logPanelRef.value) ? logPanelRef.value[0] : logPanelRef.value
  const currentFilename = panel?.selectedFile || ''
  if (!currentFilename || !window.pywebview) {
    toast.warning("未选中任何日志文件。")
    return
  }

  // UI 反馈，清空旧状态
  toast.info("正在扫描全部日志，请稍候...", { timeout: 3000 })
  // 先锁定状态，再清空 UI 选择！
  isGlobalScanning.value = true
  
  // 这会触发底层清空，但因为锁存在，上层的 handleSelectedLogsUpdate 忽略了空数据
  resetAttachmentState() 
  if (panel && typeof panel.clearSelection === 'function') {
    panel.clearSelection()
  }
  // 先挂上一个全局附件占位，用户点击后一眼就能看到状态变化。
  selectedLogs.value = [{ id: 'global_mock', raw_lines: [] }]
  tokenInfo.value = {
    ...createEmptyTokenInfo(),
    isLoading: true
  }
  autoDiagnosisRequest.value = null
  showAiSidebar.value = true
  
  currentTokenRequestId++ // 阻断其他常规框选预检
  const myRequestId = currentTokenRequestId

  try {
    // 调用全局扫描接口
    const res = await window.pywebview.api.ai_scan_global_errors({
      filename: currentFilename,
      log_source_type: currentTab.value
    })

    if (myRequestId !== currentTokenRequestId) return

    if (checkResult(res,"全局扫描")) {
      const diagnosisContext = res.data.diagnosis_context || null
      const stats = diagnosisContext?.stats || {}
      const tocCount = stats.output_item_count || diagnosisContext?.error_table_of_contents?.length || 0
      const repeatCount = stats.total_repeat_count || 0

      tokenInfo.value = {
        isLoading: false,
        estimated: res.data.estimated_tokens,
        limit: res.data.token_limit,
        isOverLimit: res.data.is_over_limit,
        condensedData: diagnosisContext
      }

      // 维持全局附件状态，让侧栏和顶部 Token 统计立刻反映压缩结果。
      selectedLogs.value = [{ id: 'global_mock', raw_lines: [], count: repeatCount }]
      const tokenText = `${(Number(res.data.estimated_tokens || 0) / 1000).toFixed(1)}k TK`
      const notice = res.data?.compression_notice || `压缩完成：保留 ${tocCount} 条错误摘要，共覆盖 ${repeatCount} 次错误，当前占用约 ${tokenText}。`
      toast.success(`${notice} 正在启动 AI 分析...`, { timeout: 5000 })
      autoDiagnosisRequest.value = {
        nonce: Date.now(),
        question: '请基于本次全局扫描结果直接开始排错，给出最可能的问题根因、证据和修复建议。'
      }
    } else {
      clearLogSelection() // 失败时彻底清空并解锁
      toast.warning(res.message)
    }
  } catch (e) {
    if (myRequestId === currentTokenRequestId) {
      clearLogSelection()
    }
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
