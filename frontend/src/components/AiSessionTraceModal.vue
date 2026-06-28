<template>
  <transition name="fade">
    <div v-if="aiStore.traceModalState.visible" class="fixed inset-0 z-140 flex items-center justify-center bg-bg-deep/80 backdrop-blur-md">
      <!-- 主容器：会话链路三栏视图 -->
      <div class="flex h-[86vh] w-[92vw] max-w-7xl select-text flex-col overflow-hidden rounded-2xl border border-accent-special/20 bg-bg-surface/95 shadow-[0_0_80px_rgba(0,0,0,0.75)]">
        <!-- 顶部标题栏：会话标识与刷新/关闭操作 -->
        <div class="flex h-14 shrink-0 items-center justify-between border-b border-text-main/10 bg-black/35 px-5">
          <div class="min-w-0">
            <div class="truncate text-sm font-bold text-text-main">会话请求链路</div>
            <div class="truncate font-mono text-[0.7rem] text-text-dim">{{ activeSession?.session_id || aiStore.traceModalState.sessionId }}</div>
          </div>
          <div class="flex items-center gap-2">
            <button @click="refresh" class="rounded border border-white/10 bg-black/20 px-3 py-1.5 text-xs text-text-dim transition-colors hover:text-accent-special">
              刷新
            </button>
            <button @click="aiStore.closeSessionTraceViewer()" class="p-2 text-text-dim transition-colors hover:text-accent-special">
              <X class="size-5" />
            </button>
          </div>
        </div>

        <div class="grid min-h-0 flex-1 grid-cols-[22rem_minmax(0,1fr)_24rem]">
          <!-- 左栏：会话概览与累计 token 指标 -->
          <div class="min-h-0 overflow-y-auto border-r border-text-main/10 bg-black/20 p-4">
            <div class="mb-4 text-xs font-black uppercase tracking-[0.2em] text-text-dim/60">会话概览</div>
            <div v-if="!activeSession" class="rounded-xl border border-white/10 bg-black/20 px-4 py-6 text-center text-xs text-text-dim">
              当前会话暂无链路数据
            </div>
            <div v-else class="space-y-3 text-xs text-text-dim">
              <div class="rounded-xl border border-white/10 bg-black/20 p-3">
                <div class="mb-2 text-sm font-bold text-text-main">{{ activeSession.title || '未命名会话' }}</div>
                <div>所属助手：{{ activeSession.assistant_id || '未知' }}</div>
                <div>当前模型：{{ sessionRequestMeta.model }}</div>
                <div>当前随机性：{{ sessionRequestMeta.temperature }}</div>
                <div>请求数量：{{ activeSession.request_count || 0 }}</div>
                <div>会话状态：{{ activeSession.status || 'unknown' }}</div>
              </div>
              <div class="rounded-xl border border-white/10 bg-black/20 p-3">
                <div class="mb-2 flex items-center gap-1 text-sm font-bold text-text-main">
                  <span>消息累计</span>
                  <button class="text-text-dim/70 hover:text-accent-special transition-colors" v-tooltip="'这里显示的是这条消息对应请求的^^估算Token^^消耗量，包含固定说明、上下文、附件、用户输入和工具补充内容。'">
                    <CircleHelp class="size-3.5" />
                  </button>
                </div>
                <div class="space-y-1.5">
                  <div class="flex items-center justify-between text-text-main">
                    <div class="flex items-center gap-1">
                      <span>消息输入总计</span>
                      <button class="text-text-dim/70 hover:text-accent-special transition-colors" v-tooltip="sessionMessageUsageTooltip">
                        <CircleHelp class="size-3.5" />
                      </button>
                    </div>
                    <span class="font-mono">{{ formatTokenMetric(sessionTokenSummary.messageInputTotal) }}</span>
                  </div>
                  <div class="space-y-1">
                    <div class="flex items-center justify-between pl-4">
                      <span>主对话输入</span>
                      <span class="font-mono">{{ formatTokenMetric(sessionTokenSummary.mainPromptTokens) }}</span>
                    </div>
                    <div class="text-[0.7rem] text-text-dim/70 -mt-1">
                      <div v-if="sessionTokenSummary.promptTemplateTokens > 0" class="flex items-center justify-between pl-8">
                        <span>系统提示</span>
                        <span class="font-mono">{{ formatTokenMetric(sessionTokenSummary.promptTemplateTokens) }}</span>
                      </div>
                      <div v-if="sessionTokenSummary.memoryTokens > 0" class="flex items-center justify-between pl-8">
                        <span>会话记忆</span>
                        <span class="font-mono">{{ formatTokenMetric(sessionTokenSummary.memoryTokens) }}</span>
                      </div>
                      <div v-if="sessionTokenSummary.attachmentTokens > 0" class="flex items-center justify-between pl-8">
                        <span>附件信息</span>
                        <span class="font-mono">{{ formatTokenMetric(sessionTokenSummary.attachmentTokens) }}</span>
                      </div>
                      <div v-if="sessionTokenSummary.userInputTokens > 0" class="flex items-center justify-between pl-8">
                        <span>用户输入</span>
                        <span class="font-mono">{{ formatTokenMetric(sessionTokenSummary.userInputTokens) }}</span>
                      </div>
                      <div v-if="sessionTokenSummary.toolContextTokens > 0" class="flex items-center justify-between pl-8">
                        <span>工具调用</span>
                        <span class="font-mono">{{ formatTokenMetric(sessionTokenSummary.toolContextTokens) }}</span>
                      </div>
                      <div v-if="sessionTokenSummary.forcedSummaryTokens > 0" class="flex items-center justify-between pl-8">
                        <span>总结补充</span>
                        <span class="font-mono">{{ formatTokenMetric(sessionTokenSummary.forcedSummaryTokens) }}</span>
                      </div>
                    </div>
                  </div>

                  <div class="flex items-center justify-between pt-1 text-text-main">
                    <div class="flex items-center gap-1">
                      <span>消息输出总计</span>
                      <button class="text-text-dim/70 hover:text-accent-special transition-colors" v-tooltip="sessionOutputUsageTooltip">
                        <CircleHelp class="size-3.5" />
                      </button>
                    </div>
                    <span class="font-mono">{{ formatTokenMetric(sessionTokenSummary.messageOutputTotal) }}</span>
                  </div>
                  <div class="space-y-1">
                    <div class="flex items-center justify-between pl-4">
                      <span>主回复输出</span>
                      <span class="font-mono">{{ formatTokenMetric(sessionTokenSummary.mainCompletionTokens) }}</span>
                    </div>
                    <div class="text-[0.7rem] text-text-dim/70 -mt-1">
                      <div v-if="sessionTokenSummary.reasoningTokens > 0" class="flex items-center justify-between pl-8 ">
                        <span>深度思考</span>
                        <span class="font-mono">{{ formatTokenMetric(sessionTokenSummary.reasoningTokens) }}</span>
                      </div>
                      <div v-if="sessionTokenSummary.toolCallTokens > 0" class="flex items-center justify-between pl-8 ">
                        <span>工具调用</span>
                        <span class="font-mono">{{ formatTokenMetric(sessionTokenSummary.toolCallTokens) }}</span>
                      </div>
                      <div v-if="sessionTokenSummary.answerTokens > 0" class="flex items-center justify-between pl-8 ">
                        <span>回复正文</span>
                        <span class="font-mono">{{ formatTokenMetric(sessionTokenSummary.answerTokens) }}</span>
                      </div>
                    </div>
                    
                  </div>
                </div>
              </div>
              <div class="rounded-xl border border-white/10 bg-black/20 p-3">
                <div class="mb-2 flex items-center gap-1 text-sm font-bold text-text-main">
                  <span>补充指标</span>
                  <button class="text-text-dim/70 hover:text-accent-special transition-colors" v-tooltip="sessionRequestUsageTooltip">
                    <CircleHelp class="size-3.5" />
                  </button>
                </div>
                <div class="space-y-1.5">
                  <div class="flex items-center justify-between text-text-main">
                    <span>总请求消耗</span>
                    <span class="font-mono">{{ formatTokenMetric(sessionTokenSummary.requestTotalTokens) }}</span>
                  </div>
                  <div class="flex items-center justify-between">
                    <span>工具轮次</span>
                    <span class="font-mono">{{ sessionTokenSummary.toolRounds }}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- 中栏：统一时间轴，按请求顺序展开事件 -->
          <div class="min-h-0 overflow-y-auto overflow-x-hidden bg-bg-surface/40 p-4">
            <div v-if="aiStore.traceModalState.isLoading" class="rounded-xl border border-white/10 bg-black/20 px-4 py-8 text-center text-sm text-text-dim">
              正在加载链路...
            </div>
            <div v-else>
              <div class="mb-4 text-xs font-black uppercase tracking-[0.2em] text-text-dim/60">统一时间轴</div>
              <div v-if="!timelineItems.length" class="rounded-xl border border-white/10 bg-black/20 px-4 py-8 text-center text-sm text-text-dim">
                当前会话没有可展示的链路数据
              </div>
              <div v-else class="relative space-y-4 pb-6 before:absolute before:left-0 before:top-0 before:bottom-0 before:w-px before:bg-white/10">
                <div v-for="item in timelineItems" :key="item.id" class="relative pl-4" >
                  <div class="absolute -left-1 top-7 size-3 rounded-full border border-primary/10 bg-accent-primary shadow-accent-primary" :class="item.dotClass"></div>
                  <div class="rounded-2xl border p-3" :class="item.cardClass">
                    <div class="mb-2 flex items-start justify-between gap-3">
                      <div class="min-w-0">
                        <div class="truncate text-sm font-bold text-text-main">{{ item.title }}</div>
                        <div class="mt-1 flex flex-wrap items-center gap-2 text-[0.7rem] text-text-dim">
                          <span>{{ formatTime(item.timestamp) }}</span>
                          <span v-if="item.traceId" class="font-mono">{{ item.traceId }}</span>
                          <span v-if="item.requestId" class="font-mono">{{ item.requestId }}</span>
                        </div>
                      </div>
                      <span v-if="item.badge" class="rounded px-2 py-1 text-[0.7rem]" :class="item.badgeClass">
                        {{ item.badge }}
                      </span>
                    </div>

                    <div v-if="item.attachments?.length" class="mb-3 flex flex-wrap gap-2">
                      <span v-for="(attachment, attachmentIndex) in item.attachments" :key="`${item.id}-${attachmentIndex}`"
                        class="rounded-lg border border-white/10 bg-black/20 px-2.5 py-1 text-[0.7rem] text-text-dim" >
                        {{ attachment }}
                      </span>
                    </div>

                    <div v-if="item.metrics?.length" class="mb-3 grid grid-cols-2 gap-2 text-xs text-text-dim">
                      <div v-for="metric in item.metrics" :key="`${item.id}-${metric.label}`"
                        class="rounded-lg border border-white/5 bg-black/25 px-2.5 py-2" >
                        {{ metric.label }}：{{ metric.value }}
                      </div>
                    </div>

                    <pre v-if="item.body" class="whitespace-pre-wrap break-all text-xs text-text-dim">{{ item.body }}</pre>

                    <div v-if="item.reasoning" class="mt-3 rounded-xl border border-white/5 bg-black/20 p-3">
                      <div class="mb-2 text-xs font-bold text-text-main">思考流</div>
                      <pre class="whitespace-pre-wrap break-all text-xs text-text-dim">{{ item.reasoning }}</pre>
                    </div>

                    <details v-if="item.details" class="mt-3 rounded border border-white/5 bg-black/20 p-2 text-[0.7rem] text-text-main">
                      <summary class="cursor-pointer text-text-dim">查看原始数据</summary>
                      <pre class="mt-2 whitespace-pre-wrap break-all rounded border border-white/5 bg-black/25 p-2">{{ prettyJson(item.details) }}</pre>
                    </details>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- 右栏：当前选中会话的原始 JSON 面板 -->
          <div class="min-h-0 overflow-y-auto border-l border-text-main/10 bg-black/20 p-4">
            <div class="mb-4 text-xs font-black uppercase tracking-[0.2em] text-text-dim/60">原始 JSON</div>
            <pre class="whitespace-pre-wrap break-all rounded-2xl border border-white/10 bg-black/30 p-3 text-[0.7rem] text-text-main">{{ prettyJson(rawJsonPanel) }}</pre>
          </div>
        </div>
      </div>
    </div>
  </transition>
</template>

<script setup>
import { computed } from 'vue'
import { CircleHelp, X } from 'lucide-vue-next'
import { useAiStore } from '../stores/aiStore'
import {
  buildAssistantMessageUsageTooltip,
  buildRequestTotalUsageTooltip,
  buildUserMessageUsageTooltip,
  formatTokenCount,
  numberOrZero,
} from '../runtime/aiUsageTooltips'

// -----------------------------------------------------------------
// Store 依赖 (Stores)
// -----------------------------------------------------------------
const aiStore = useAiStore()

// -----------------------------------------------------------------
// 工具方法 (Utils)
// -----------------------------------------------------------------
const activeSession = computed(() => {
  /** 读取当前 trace 面板正在查看的会话对象。 */
  const sessionId = String(aiStore.traceModalState.sessionId || '').trim()
  return sessionId ? aiStore.traceBySessionId[sessionId] || null : null
})

const formatTime = (value) => {
  /** 把毫秒时间戳格式化为面板可读时间。 */
  const timestamp = Number(value)
  if (!timestamp) return '未知时间'
  const date = new Date(timestamp)
  if (Number.isNaN(date.getTime())) return '未知时间'
  return date.toLocaleString('zh-CN', {
    hour12: false,
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

const prettyJson = (value) => {
  // trace 面板既要展示原始字符串，也要展示结构化 payload；
  // 这里统一兜底，避免模板里重复 try/catch。
  if (value == null) return ''
  if (typeof value === 'string') {
    try {
      return JSON.stringify(JSON.parse(value), null, 2)
    } catch {
      return value
    }
  }
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

const formatTokenMetric = (value) => `${formatTokenCount(value)} token`

// -----------------------------------------------------------------
// 视图映射 (View Meta)
// -----------------------------------------------------------------
const toneClassMap = {
  cool: {
    dotClass: 'bg-accent-cool/80',
    cardClass: 'border-accent-cool/20 bg-accent-cool/8',
  },
  tip: {
    dotClass: 'bg-accent-tip/80',
    cardClass: 'border-accent-tip/20 bg-accent-tip/8',
  },
  success: {
    dotClass: 'bg-accent-success/80',
    cardClass: 'border-accent-success/20 bg-accent-success/8',
  },
  danger: {
    dotClass: 'bg-accent-danger/80',
    cardClass: 'border-accent-danger/20 bg-accent-danger/8',
  },
  warn: {
    dotClass: 'bg-accent-warn/80',
    cardClass: 'border-accent-warn/20 bg-accent-warn/8',
  },
  special: {
    dotClass: 'bg-accent-special/80',
    cardClass: 'border-accent-special/20 bg-accent-special/8',
  },
}

const statusBadgeClassMap = {
  done: 'bg-accent-success/15 text-accent-success',
  error: 'bg-accent-danger/15 text-accent-danger',
  cancelled: 'bg-accent-warn/15 text-accent-warn',
  running: 'bg-accent-special/15 text-accent-special',
}

const decorateTimelineItem = (item) => {
  // 时间线节点先在脚本层补齐 badge / metrics / tone，
  // 模板只负责渲染，避免模板里堆复杂分支。
  const tone = toneClassMap[String(item?.tone || 'special').toLowerCase()] || toneClassMap.special
  const badgeKey = String(item?.badge || '').toLowerCase()
  const details = item?.details && typeof item.details === 'object' ? item.details : {}
  const responsePayload = details?.response_payload && typeof details.response_payload === 'object' ? details.response_payload : {}
  const tokenUsage = responsePayload?.token_usage && typeof responsePayload.token_usage === 'object' ? responsePayload.token_usage : {}
  const messageUsage = details?.message_usage && typeof details.message_usage === 'object' ? details.message_usage : {}
  const normalizedItem = { ...item }
  if (normalizedItem.kind === 'request') {
    normalizedItem.metrics = [
      {
        label: '消息输入',
        value: formatTokenMetric(numberOrZero(messageUsage?.user?.total_tokens)),
      },
    ]
  } else if (normalizedItem.kind === 'response') {
    normalizedItem.metrics = [
      {
        label: '主回复输出',
        value: formatTokenMetric(numberOrZero(tokenUsage?.estimated_completion_tokens)),
      },
      {
        label: '深度思考',
        value: formatTokenMetric(numberOrZero(tokenUsage?.estimated_reasoning_completion_tokens)),
      },
      {
        label: '工具调用',
        value: formatTokenMetric(numberOrZero(tokenUsage?.estimated_tool_call_completion_tokens)),
      },
      {
        label: '回复正文',
        value: formatTokenMetric(numberOrZero(tokenUsage?.estimated_answer_completion_tokens)),
      },
      {
        label: '消息输出总计',
        value: formatTokenMetric(numberOrZero(messageUsage?.assistant?.total_tokens)),
      },
    ].filter(metric => metric.value !== '0 token')
  }
  return {
    ...normalizedItem,
    dotClass: tone.dotClass,
    cardClass: tone.cardClass,
    badgeClass: statusBadgeClassMap[badgeKey] || statusBadgeClassMap.running,
  }
}

// -----------------------------------------------------------------
// 计算属性 (Computed)
// -----------------------------------------------------------------
const sessionTokenSummary = computed(() => {
  const totalTokenUsage = activeSession.value?.total_token_usage || {}
  const totalMessageUsage = activeSession.value?.total_message_usage || {}
  return {
    messageInputTotal: numberOrZero(totalMessageUsage?.user?.total_tokens),
    messageOutputTotal: numberOrZero(totalMessageUsage?.assistant?.total_tokens),
    mainPromptTokens: numberOrZero(totalTokenUsage?.prompt_tokens),
    mainCompletionTokens: numberOrZero(totalTokenUsage?.completion_tokens),
    promptTemplateTokens: numberOrZero(activeSession.value?.total_prompt_input_breakdown?.prompt_template_tokens),
    memoryTokens: numberOrZero(activeSession.value?.total_prompt_input_breakdown?.memory_tokens),
    attachmentTokens: numberOrZero(activeSession.value?.total_prompt_input_breakdown?.attachment_tokens),
    userInputTokens: numberOrZero(activeSession.value?.total_prompt_input_breakdown?.user_input_tokens),
    toolContextTokens: numberOrZero(activeSession.value?.total_prompt_input_breakdown?.tool_context_tokens),
    forcedSummaryTokens: numberOrZero(activeSession.value?.total_prompt_input_breakdown?.forced_summary_tokens),
    answerTokens: numberOrZero(totalTokenUsage?.answer_completion_tokens),
    reasoningTokens: numberOrZero(totalTokenUsage?.reasoning_completion_tokens),
    toolCallTokens: numberOrZero(totalTokenUsage?.tool_call_completion_tokens),
    requestTotalTokens: numberOrZero(totalTokenUsage?.total_tokens),
    toolRounds: numberOrZero(totalTokenUsage?.tool_rounds),
  }
})

const sessionRequestMeta = computed(() => {
  // 当前展示的会话级“模型/温度”取最近一条 trace，
  // 因为会话中途可能切换覆写配置，用户需要看到最新有效值。
  const traces = Array.isArray(activeSession.value?.traces) ? activeSession.value.traces : []
  const latestTrace = traces[traces.length - 1] || {}
  const requestPayload = latestTrace?.request_payload && typeof latestTrace.request_payload === 'object'
    ? latestTrace.request_payload
    : {}
  const overrideConfig = requestPayload?.ai_override_config && typeof requestPayload.ai_override_config === 'object'
    ? requestPayload.ai_override_config
    : {}
  const rawTemperature = overrideConfig?.temperature
  const numericTemperature = Number(rawTemperature)
  return {
    model: String(latestTrace?.model || '未知'),
    temperature: Number.isFinite(numericTemperature) ? `${numericTemperature.toFixed(1)}` : '默认',
  }
})

const sessionMessageUsageTooltip = computed(() => buildUserMessageUsageTooltip({
  totalTokens: sessionTokenSummary.value.messageInputTotal,
  promptTokens: sessionTokenSummary.value.mainPromptTokens,
  promptTemplateTokens: sessionTokenSummary.value.promptTemplateTokens,
  memoryTokens: sessionTokenSummary.value.memoryTokens,
  attachmentTokens: sessionTokenSummary.value.attachmentTokens,
  userInputTokens: sessionTokenSummary.value.userInputTokens,
  toolContextTokens: sessionTokenSummary.value.toolContextTokens,
  forcedSummaryTokens: sessionTokenSummary.value.forcedSummaryTokens,
}))

const sessionOutputUsageTooltip = computed(() => buildAssistantMessageUsageTooltip({
  totalTokens: sessionTokenSummary.value.messageOutputTotal,
  completionTokens: sessionTokenSummary.value.mainCompletionTokens,
  reasoningTokens: sessionTokenSummary.value.reasoningTokens,
  toolCallTokens: sessionTokenSummary.value.toolCallTokens,
  answerTokens: sessionTokenSummary.value.answerTokens,
}))

const sessionRequestUsageTooltip = computed(() => buildRequestTotalUsageTooltip({
  totalTokens: sessionTokenSummary.value.requestTotalTokens,
  promptTokens: sessionTokenSummary.value.mainPromptTokens,
  completionTokens: sessionTokenSummary.value.mainCompletionTokens,
  toolRounds: sessionTokenSummary.value.toolRounds,
}))

const timelineItems = computed(() => (
  Array.isArray(activeSession.value?.timeline_items)
    ? activeSession.value.timeline_items.map(decorateTimelineItem)
    : []
))

const rawJsonPanel = computed(() => ({
  trace_session: activeSession.value || null,
}))

const refresh = async () => {
  /** 主动刷新当前会话的链路数据。 */
  if (!aiStore.traceModalState.sessionId) return
  aiStore.traceModalState.isLoading = true
  try {
    await aiStore.refreshSessionTrace(aiStore.traceModalState.sessionId)
  } finally {
    aiStore.traceModalState.isLoading = false
  }
}
</script>

<style scoped>
.fade-enter-active, .fade-leave-active { transition: opacity 0.2s ease; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>
