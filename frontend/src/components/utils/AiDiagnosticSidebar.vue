<!-- frontend/src/components/utils/AiDiagnosticSidebar.vue -->
<template>
  <transition name="slide-right">
    <div v-if="modelValue" class="w-[450px] shrink-0 bg-bg-surface/90 backdrop-blur-xl border-l border-text-main/10 flex flex-col h-full z-40 relative shadow-2xl">
      
      <!-- 1. 标题栏 (增加 Token 监控仪) -->
      <div class="h-14 border-b border-white/5 flex items-center justify-between px-4 shrink-0 bg-black/40">
        <div class="flex items-center gap-3">
          <div class="w-7 h-7 rounded-lg bg-gradient-to-br from-accent-special to-accent-primary flex items-center justify-center text-white shadow-[0_0_10px_rgba(139,92,246,0.3)]">
            <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
          </div>
          <div class="flex flex-col">
            <span class="font-bold text-sm text-text-main leading-tight">AI 诊断专家</span>
            <!-- 【新增】会话记忆指示器 -->
            <div class="flex items-center gap-1.5" v-tooltip="'当前会话累积消耗的 Token，过高会导致 AI 失忆'">
              <div class="w-1.5 h-1.5 rounded-full" :class="sessionTokens > 16000 ? 'bg-accent-danger animate-pulse' : 'bg-accent-success'"></div>
              <span class="text-[10px] text-text-dim font-mono">Memory: {{ (sessionTokens / 1000).toFixed(1) }}k TK</span>
            </div>
          </div>
        </div>
        
        <div class="flex items-center gap-1.5">
          <button @click="clearChat" class="p-1.5 text-text-dim hover:text-accent-danger hover:bg-white/5 transition-all rounded-md" v-tooltip="'清空记忆，开启新会话'">
            <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
          </button>
          <button @click="closeSidebar" class="p-1.5 text-text-dim hover:text-white hover:bg-white/5 transition-all rounded-md">
            <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" /></svg>
          </button>
        </div>
      </div>

      <!-- 2. 聊天消息流 -->
      <div class="flex-1 overflow-y-auto p-4 flex flex-col gap-5 custom-scrollbar" ref="chatContainer">
        
        <!-- 欢迎/引导消息 -->
        <div v-if="chatHistory.length === 0" class="flex flex-col items-center justify-center h-full text-center opacity-80 mt-10">
          <div class="w-16 h-16 rounded-2xl bg-gradient-to-br from-accent-special/20 to-transparent flex items-center justify-center mb-4 border border-accent-special/20">
            <svg class="w-8 h-8 text-accent-special" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" /></svg>
          </div>
          <p class="text-sm font-bold text-white mb-2">需要排错帮助吗？</p>
          <p class="text-xs text-text-dim max-w-[260px] leading-relaxed">
            在左侧勾选红字，你可以直接点击底部发送附件，或要求我进行深度溯源分析。
          </p>
        </div>

        <!-- 消息气泡渲染 -->
        <div v-for="(msg, idx) in chatHistory" :key="idx" class="flex flex-col group/msg" :class="msg.role === 'user' ? 'items-end' : 'items-start'">
          
          <div class="text-[10px] text-text-dim mb-1 ml-1 mr-1 flex items-center gap-1.5 opacity-0 group-hover/msg:opacity-100 transition-opacity">
            <span>{{ msg.role === 'user' ? '你' : 'AI' }}</span>
          </div>
          
          <div class="max-w-[92%] rounded-2xl px-3.5 py-2.5 text-sm shadow-sm"
              :class="msg.role === 'user' ? 'bg-gradient-to-br from-accent-primary to-accent-highlight text-white rounded-tr-sm' : 'bg-[#1a1a1a]/80 backdrop-blur-md border border-white/5 text-text-main rounded-tl-sm'">
            
            <!-- 用户发送的附件标识 -->
            <div v-if="msg.isLogPayload" class="flex items-center gap-2 bg-black/30 rounded-lg p-2 mb-2 opacity-90 text-[11px] border border-white/10 w-fit backdrop-blur-sm shadow-inner">
              <svg class="w-3.5 h-3.5 text-accent-special" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>
              <span>附件: {{ msg.logCount === 1 && msg._hidden_context ? '全局扫描日志包' : msg.logCount + ' 条具体日志' }}</span>
            </div>
            
            <!-- AI 调用工具状态栏 (折叠与运行态) -->
            <div v-if="msg.tools && msg.tools.length > 0" class="mb-3 flex flex-col gap-1.5">
              <div v-for="t in msg.tools" :key="t.id" class="flex items-center gap-2 text-[11px] bg-black/40 px-2.5 py-1.5 rounded-md border border-white/5">
                <svg v-if="t.status === 'running'" class="w-3.5 h-3.5 animate-spin text-accent-special" viewBox="0 0 24 24" fill="none" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg>
                <svg v-else class="w-3.5 h-3.5 text-accent-success" viewBox="0 0 24 24" fill="none" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/></svg>
                <span class="text-text-dim/90 font-mono" v-html="formatToolName(t.name, t.arguments)"></span>
              </div>
            </div>
            <!-- 普通文本 -->
            <!-- 文本正文 (支持高级 Markdown 渲染) -->
            <div v-if="msg.role === 'assistant'" class="prose prose-sm prose-invert prose-p:my-1.5 prose-ul:my-1.5 prose-li:my-0.5 max-w-none relative">
              <!-- 【精美打字机光标】当尚未收到文字，且没在调用工具时，显示闪烁光标 -->
              <div v-if="(!msg.content.analysis && (!msg.tools || msg.tools.length === 0 || msg.tools.every(t => t.status === 'done'))) && isThinking" 
                   class="flex items-center gap-1 py-1">
                <span class="w-2.5 h-4 bg-accent-special animate-pulse rounded-sm"></span>
              </div>
              <div v-else v-html="renderMarkdown(msg.content)"></div>
            </div>
            
            <div v-else-if="msg.content" class="whitespace-pre-wrap leading-relaxed text-[13.5px]">{{ msg.content }}</div>

            <!-- 【优雅的 Actionable JSON 渲染】 -->
            <div v-if="msg.actions && msg.actions.length > 0" class="mt-4 pt-3 border-t border-white/10 flex flex-col gap-2.5">
              <p class="text-[11px] text-text-dim font-bold flex items-center gap-1.5 mb-1">
                <svg class="w-3.5 h-3.5 text-accent-special" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
                AI 建议操作
              </p>
              
              <div v-for="(action, aIdx) in msg.actions" :key="aIdx" 
                   class="group/action bg-gradient-to-b from-white/5 to-transparent border border-white/10 hover:border-accent-special/50 rounded-xl p-3 transition-all duration-300">
                <div class="flex items-center justify-between mb-1.5">
                  <span class="font-bold text-accent-special text-xs">{{ action.title }}</span>
                </div>
                <p class="text-[11px] text-text-dim leading-relaxed mb-3">{{ action.description }}</p>
                <button @click="executeAction(action)" 
                        class="w-full py-1.5 rounded-lg bg-accent-special/10 hover:bg-accent-special text-accent-special hover:text-white transition-all duration-300 text-xs font-bold border border-accent-special/20 hover:border-transparent flex items-center justify-center gap-1.5">
                  <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
                  {{ getActionLabel(action.type) }}
                </button>
              </div>
            </div>
          </div>
        </div>

      </div>

      <!-- 3. 输入区 -->
      <div class="p-3 bg-black/60 backdrop-blur-xl border-t border-white/5 shrink-0">
        
        <div class="relative bg-white/5 border border-white/10 rounded-xl transition-all duration-300 focus-within:border-accent-special/50 focus-within:bg-black/50 flex flex-col shadow-inner">
          
          <!-- 【核心修改】悬浮附件 (Payload Indicator) -->
          <transition name="fade-up">
            <div v-if="pendingLogs.length > 0" class="px-3 pt-2 pb-1">
              <div class="flex items-center justify-between bg-accent-special/10 border border-accent-special/20 rounded-lg px-2.5 py-1.5">
                <div class="flex items-center gap-2">
                  <svg class="w-3.5 h-3.5 text-accent-special" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" /></svg>
                  <span class="text-xs text-accent-special font-bold">附件: {{ pendingLogs[0]?.id === 'global_mock' ? '全局诊断报告' : pendingLogs.length + ' 条日志' }}</span>
                  <span v-if="!tokenInfo.isLoading" class="text-[10px] text-text-dim ml-1">
                    (约 {{ (tokenInfo.estimated/1000).toFixed(1) }}k TK)
                  </span>
                  <span v-else class="text-[10px] text-text-dim ml-1">计算中...</span>
                </div>
                <button @click="$emit('clear-selection')" class="text-text-dim hover:text-accent-danger p-0.5 rounded-full bg-white/5 transition-colors" v-tooltip="'移除附件'">
                  <svg class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" /></svg>
                </button>
              </div>
              <div v-if="tokenInfo.isOverLimit" class="text-[10px] text-accent-danger mt-1.5 pl-1 flex items-center gap-1">
                <svg class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" /></svg>
                数据过大，建议取消部分勾选。
              </div>
            </div>
          </transition>

          <textarea v-model="userInput" 
                    @keydown.enter.exact.prevent="sendMessage"
                    placeholder="输入其它要求或直接点击右下角发送..." 
                    class="w-full bg-transparent border-none py-3 px-3.5 text-sm text-text-main focus:outline-none resize-none h-14 custom-scrollbar placeholder:text-text-dim/40"></textarea>
          
          <div class="absolute right-2 bottom-2">
            <button @click="sendMessage" :disabled="isSendDisabled"
                    class="p-1.5 rounded-lg transition-all duration-300 flex items-center justify-center"
                    :class="isSendDisabled ? 'text-text-dim/30 bg-transparent' : 'bg-gradient-to-br from-accent-special to-accent-primary text-white hover:shadow-[0_0_15px_rgba(139,92,246,0.5)]'">
              <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" /></svg>
            </button>
          </div>
        </div>

      </div>
    </div>
  </transition>
</template>

<script setup>
import { ref, computed, nextTick, onMounted, onUnmounted } from 'vue'
import { useToast } from 'vue-toastification'
import { useAppStore } from '../../stores/appStore'
import { useModStore } from '../../stores/modStore'
import { useRuleStore } from '../../stores/ruleStore'
import { useConfirmStore } from '../../stores/confirmStore'
import MarkdownIt from 'markdown-it'
import hljs from 'highlight.js'
import 'highlight.js/styles/atom-one-dark.css' // 引入酷炫的暗黑代码高亮主题

const props = defineProps({
  modelValue: { type: Boolean, default: false }, // 控制侧边栏显隐
  // 从父组件(LogViewer)直接接收处理好的状态
  pendingLogs: { type: Array, default: () => [] },
  filename: { type: String, default: '' }, // 从父组件接收文件名
  tokenInfo: { type: Object, default: () => ({ isLoading: false, condensedData: null }) },
  sourceType: { type: String, default: 'game' }
})
const emit = defineEmits(['update:modelValue', 'clear-selection'])

const appStore = useAppStore()
const modStore = useModStore()
const toast = useToast()

const chatContainer = ref(null)
const chatHistory = ref([])
const userInput = ref('')
const isThinking = ref(false)


const closeSidebar = () => emit('update:modelValue', false)
const clearChat = () => { chatHistory.value =[] }

const scrollToBottom = async () => {
  await nextTick()
  if (chatContainer.value) {
    chatContainer.value.scrollTop = chatContainer.value.scrollHeight
  }
}

// 【新增】会话 Token 粗略估算 (用于 UI 顶部指示器)
// 中英文混合，1 Token 约等于 2.5 字符
const sessionTokens = computed(() => {
  let totalChars = 0
  chatHistory.value.forEach(m => {
    totalChars += typeof m.content === 'object' ? (m.content.analysis || '').length : (m.content || '').length
    if (m._hidden_context) {
      totalChars += JSON.stringify(m._hidden_context).length
    }
  })
  return Math.round(totalChars / 2.5)
})
// 核心判断：发送按钮何时置灰
const isSendDisabled = computed(() => {
  if (isThinking.value) return true
  if (props.tokenInfo.isLoading) return true // Token 计算中不准发
  // 如果没有挂载日志附件，且没输入文字，不能发
  if (props.pendingLogs.length === 0 && userInput.value.trim() === '') return true
  return false
})
// 初始化 Markdown-it
const md = new MarkdownIt({
  html: false, // 安全起见，禁用 HTML 标签
  linkify: true, // 自动转换 URL 为链接
  typographer: true,
  highlight: function (str, lang) {
    if (lang && hljs.getLanguage(lang)) {
      try {
        return `<pre class="hljs p-3 rounded-lg text-xs overflow-x-auto custom-scrollbar my-2 border border-white/5 bg-black/50"><code>${hljs.highlight(str, { language: lang, ignoreIllegals: true }).value}</code></pre>`
      } catch (__) {}
    }
    return `<pre class="hljs p-3 rounded-lg text-xs overflow-x-auto custom-scrollbar my-2 border border-white/5 bg-black/50"><code>${md.utils.escapeHtml(str)}</code></pre>`
  }
})
const renderMarkdown = (text) => {
  if (text == null) return ''
  let content = typeof text === 'object' ? text.analysis || '' : String(text)
  // Markdown 处理后，针对普通内联 code 进行一点样式增强
  return md.render(content).replace(/<code>/g, '<code class="bg-black/30 text-accent-special px-1.5 py-0.5 rounded text-[12px] font-mono border border-white/5">')
}

// 工具名称格式化，解析 arguments 让界面更友好
const formatToolName = (name, argsStr) => {
  let args = {}
  try { args = argsStr ? JSON.parse(argsStr) : {} } catch(e){}
  
  switch(name) {
    case 'get_log_context':
      return `读取物理上下文 <code>L:${args.target_line || '?'}</code>`
    case 'get_active_mod_list':
      return `核对全局排序规则`
    case 'get_mod_info':
      return `检索模组元数据 <code>${args.package_id || ''}</code>`
    case 'get_load_order_context':
      return `分析局部冲突 <code>${args.package_id || ''}</code>`
    default:
      return `调用系统工具 <code>${name}</code>`
  }
}

// ====== 新增：生命周期监听后端流事件 ======
const handleStream = (e) => {
  const { session_id, chunk } = e.detail
  const msg = chatHistory.value.find(m => m.session_id === session_id)
  if (msg) {
    if (typeof msg.content === 'object') {
      msg.content.analysis += chunk
    } else {
      msg.content += chunk
    }
    scrollToBottom()
  }
}

const handleToolCall = (e) => {
  const { session_id, tool_id, name, arguments: args } = e.detail
  const msg = chatHistory.value.find(m => m.session_id === session_id)
  if (msg) {
    if (!msg.tools) msg.tools = []
    // 【修改】存入 arguments 以供前端解析展示
    msg.tools.push({ id: tool_id, name, arguments: args, status: 'running' })
    scrollToBottom()
  }
}

const handleToolResult = (e) => {
  const { session_id, tool_id } = e.detail
  const msg = chatHistory.value.find(m => m.session_id === session_id)
  if (msg && msg.tools) {
    const tool = msg.tools.find(t => t.id === tool_id)
    if (tool) tool.status = 'done'
    scrollToBottom()
  }
}

onMounted(() => {
  window.addEventListener('ai-chat-stream', handleStream)
  window.addEventListener('ai-tool-call', handleToolCall)
  window.addEventListener('ai-tool-result', handleToolResult)
})

onUnmounted(() => {
  window.removeEventListener('ai-chat-stream', handleStream)
  window.removeEventListener('ai-tool-call', handleToolCall)
  window.removeEventListener('ai-tool-result', handleToolResult)
})


// ================== 发送与处理逻辑 ==================

// 发送选中日志
const sendMessage = async () => {
  if (isSendDisabled.value || !window.pywebview) return
  isThinking.value = true

  let questionText = userInput.value.trim()
  const hasAttachment = props.pendingLogs.length > 0 && props.tokenInfo.condensedData
  
  // 如果用户啥都没写，但是有日志附件，就补一个默认提示词
  if (hasAttachment && questionText === '') {
    questionText = "请深度分析我提交的日志数据，并给出修复建议。"
  }

  // 1. 生成会话 ID 绑定流
  const sessionId = `chat_${Date.now()}`

  // 2. 将数据推入本地聊天气泡以供展示
  chatHistory.value.push({ 
    role: 'user', 
    content: questionText === '请深度分析我提交的日志数据，并给出修复建议。' ? '' : questionText, 
    isLogPayload: hasAttachment,
    logCount: props.pendingLogs.length,
    _hidden_context: hasAttachment ? props.tokenInfo.condensedData : null
  })
  // 构造发给后端的 history（合并隐藏上下文）
  const historyForBackend = chatHistory.value.map(m => {
    let finalContent = m.content || ""
    // 对于用户消息，如果有隐藏的附件数据，拼接到内容开头
    if (m.role === 'user' && m._hidden_context) {
      finalContent = `[系统注入的错误日志摘要]\n\`\`\`json\n${JSON.stringify(m._hidden_context)}\n\`\`\`\n\n[用户补充说明]\n${finalContent}`
    }
    // 对于 AI 消息，如果是对象，提取 analysis
    if (m.role === 'assistant' && typeof finalContent === 'object') {
      finalContent = finalContent.analysis || ""
    }
    return { role: m.role, content: finalContent }
  })

  // 移除最后一条刚才 push 的 user 消息，因为它等下会被包含在 historyForBackend 中
  // 但为了不让 historyForBackend 最后一项变成 user 导致对话错乱，其实我们可以直接传
  // 但是后端的逻辑是把 question 独立处理，所以我们把最后一项 pop 出来
  const lastUserMsg = historyForBackend.pop()

  const requestPayload = {
    session_id: sessionId,
    log_source_type: props.sourceType, // 【修复 1】传入正确的源类型
    filename: props.filename,          // 【修复 1】传入文件名
    history: historyForBackend,        // 带有完整记忆的历史
    question: lastUserMsg.content      // 组装好的当前问题（含隐藏附件）
  }

  const aiMsg = {
    role: 'assistant',
    session_id: sessionId,
    tools: [],
    content: { analysis: '', actions: [] },
    actions: []
  }
  chatHistory.value.push(aiMsg)
  userInput.value = ''

  if (hasAttachment) {
    emit('clear-selection')
  }

  await nextTick()
  scrollToBottom()
  try {
    const res = await window.pywebview.api.ai_diagnostic_chat(requestPayload)
    if (res.status === 'success') {
      aiMsg.actions = res.data.actions || res.data.solutions || []
      if (!aiMsg.content.analysis && res.data.analysis) {
        aiMsg.content.analysis = res.data.analysis
      }
    } else {
      throw new Error(res.message)
    }
  } catch(e) {
    aiMsg.content.analysis += `\n\n⚠️ 分析过程中发生错误: ${e.message}`
  } finally {
    isThinking.value = false
    scrollToBottom()
  }
}

// ================== 动作执行 (Actionable JSON) ==================

const getActionLabel = (type) => {
  switch (type) {
    case 'ENABLE_MOD': return '一键启用 Mod'
    case 'DISABLE_MOD': return '一键停用 Mod'
    case 'ADD_RULE': return '应用排序规则'
    case 'REPORT_BUG': return '复制反馈模板'
    default: return '执行操作'
  }
}

const executeAction = async (action) => {
  const payload = action.payload || {}
  
  try {
    switch (action.action || action.type) {
      case 'ENABLE_MOD':
        if (payload.mod_id) {
          modStore.changeModsActive([payload.mod_id], true)
          toast.success(`已启用: ${payload.mod_id}`)
        }
        break;
        
      case 'DISABLE_MOD':
        const ids = payload.mod_ids || (payload.mod_id ? [payload.mod_id] :[])
        if (ids.length > 0) {
          modStore.changeModsActive(ids, false)
          toast.success(`已停用选中 Mod`)
        }
        break;
        
      case 'ADD_RULE':
        // 调用 ruleStore 写入动态规则
        const ruleStore = useRuleStore()
        const newRule = {
          rule_id: `ai_fix_${Date.now()}`,
          name: `AI 修复: ${payload.mod_id} -> ${payload.target_id}`,
          enabled: true, logic: 'AND',
          filters:[{ field: 'package_id', operator: 'equals', value: payload.mod_id }],
          action: { type: payload.rule_type || 'load_after', value: payload.target_id }
        }
        await ruleStore.saveDynamicRule(newRule)
        
        // 询问用户是否立刻重新排序
        const confirmStore = useConfirmStore()
        if (await confirmStore.confirmAction('规则已应用', '是否立即重新执行自动排序以使规则生效？', {type: 'success'})) {
          await modStore.autoSortMods()
        }
        break;
        
      case 'REPORT_BUG':
        if (payload.report_text) {
          await navigator.clipboard.writeText(payload.report_text)
          toast.success("反馈模板已复制到剪贴板")
        }
        break;
        
      default:
        toast.warning(`暂不支持的操作类型: ${action.type}`)
    }
  } catch (e) {
    toast.error(`操作执行失败: ${e.message}`)
  }
}
</script>

<style scoped>
.slide-right-enter-active, .slide-right-leave-active { transition: transform 0.4s cubic-bezier(0.16, 1, 0.3, 1); }
.slide-right-enter-from, .slide-right-leave-to { transform: translateX(100%); opacity: 0; }

.fade-up-enter-active, .fade-up-leave-active { transition: all 0.3s ease; }
.fade-up-enter-from, .fade-up-leave-to { opacity: 0; transform: translateY(10px); }

/* 代码块外层的自适应 */
:deep(.prose) {
  line-height: 1.6;
}
:deep(.prose pre) {
  margin: 0.5rem 0;
  padding: 0.75rem;
  background-color: rgba(0, 0, 0, 0.4);
  border: 1px solid rgba(255, 255, 255, 0.05);
  border-radius: 0.5rem;
}
:deep(.prose code) {
  font-family: 'Fira Code', Consolas, Monaco, 'Andale Mono', 'Ubuntu Mono', monospace;
  font-size: 0.85em;
}
</style>