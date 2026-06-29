// frontend/src/stores/aiStore.js

import { defineStore } from 'pinia'
import { computed, reactive, ref } from 'vue'
import { checkResult, normalizeStringList, normalizeText, toast, toUserMessage } from '../../shared/lib/common'
import { normalizeAssistantSessionResult } from './ai-store/runtime/aiActionRuntime'
import {
  createAssistantRuntimePrefs, createAssistantSession, createEmptyTraceModalState,
  normalizeAssistantWarnings, normalizeNumber, normalizeSessionMessage,
} from './ai-store/factories'
import { useModelConfigActions } from './ai-store/modelConfigActions'
import { useAttachmentActions } from './ai-store/attachmentActions'
import { useModAliasActions } from './ai-store/modAliasActions'
import { useAppStore } from '../../app/stores/appStore'
import { useTaskStore } from '../../app/stores/taskStore'

// -----------------------------------------------------------------
// 工具函数 (Utils)
// -----------------------------------------------------------------
export const useAiStore = defineStore('ai', () => {
  const taskStore = useTaskStore()

  // -----------------------------------------------------------------
  // 全局运行时状态 (Runtime State)
  // -----------------------------------------------------------------
  const isLoading = ref(false)
  const runtimeAiConfig = ref(null)
  const modelListCache = reactive({})

  // 统一会话中心：
  // 1. session 是一级实体，负责保存消息流和运行态
  // 2. ownerKey 负责把“某个页面入口 / 某个业务上下文”绑定到当前会话
  //    不能只靠 assistantId，因为同一个助手可能同时服务于不同日志文件、不同页面或不同业务对象。
  // 3. requestId 仍然保留，用于单轮请求取消、流式事件与 trace 对齐
  const sessionsById = reactive({})
  const sessionOrder = ref([])
  const currentSessionByOwner = reactive({})
  const assistantRuntimePrefsByOwner = reactive({})
  const globalAttachmentEntries = reactive({})
  const pendingConsumedAttachmentKeysByRequest = reactive({})

  // Trace 也按会话缓存，而不是全局平铺列表。
  // 这样页面切换后再次打开，同一会话仍能查看自己的完整链路。
  const traceBySessionId = reactive({})
  const traceModalState = reactive(createEmptyTraceModalState())

  const modAliasTaskCompletionDataById = reactive({})
  const modAliasTaskCompletionWaiters = new Map()
  const modAliasTaskRequestMetaById = reactive({})
  const modAliasReviewTaskPoolById = reactive({})
  const modAliasReviewTaskOrder = ref([])
  const runtimeDefinitionEditorMeta = computed(() => runtimeAiConfig.value?.definition_editor_meta || {})
  const promptDefinitions = computed(() => runtimeAiConfig.value?.prompts || {})
  const providerDefinitions = computed(() => (
    Array.isArray(runtimeAiConfig.value?.providers)
      ? runtimeAiConfig.value.providers
      : []
  ))
  const capabilityMeta = computed(() => runtimeAiConfig.value?.model_capability_meta || null)

  const getDefinitionEditorMeta = () => runtimeDefinitionEditorMeta.value || {}
  const getActionDefinitions = () => getDefinitionEditorMeta().actions || {}
  const getAssistantDefinition = (assistantId = '') => {
    const normalizedId = normalizeText(assistantId)
    return normalizedId ? (runtimeAiConfig.value?.assistants || {})[normalizedId] || null : null
  }
  const getTaskDefinition = (taskId = '') => {
    const normalizedId = normalizeText(taskId)
    return normalizedId ? (runtimeAiConfig.value?.tasks || {})[normalizedId] || null : null
  }

  const {
    // 配置
    getAiConfig, saveAIConfig, listAiProviders,
    // 模型列表
    getAiModels, getCachedAiModels, getCachedAiModelOptions,
    // 能力与测试
    resolveAiModelCapabilities, getAiModelCapabilities, chatWithAI,
  } = useModelConfigActions({
    isLoading,
    runtimeAiConfig,
    modelListCache,
    providerDefinitions,
    capabilityMeta,
  })

  const getPromptDefinition = (promptId = '') => {
    const normalizedId = normalizeText(promptId)
    return normalizedId ? promptDefinitions.value?.[normalizedId] || null : null
  }

  const {
    // 附件定义与草稿
    getAttachmentDefinition, getAttachmentDisplayMeta, getSupportedAttachmentKindsForAssistant,
    buildLogOwnerKey, buildDiagnosisContextAttachment, buildModSelectionAttachment, normalizeModAliasTaskInputItems,
    // 全局附件池
    upsertGlobalAttachmentDraft, removeGlobalAttachmentDraft, removeGlobalAttachmentsByKind, listGlobalAttachmentEntries, replaceGlobalAttachmentsByKind,
    // 会话输入框附件
    getSessionComposerAttachments, removeComposerAttachment, dismissSessionAttachment, resetSessionDismissedAttachments,
  } = useAttachmentActions({
    runtimeDefinitionEditorMeta, globalAttachmentEntries, sessionsById,
    getSession: (...args) => getSession(...args),
    getAssistantDefinition, getPromptDefinition,
  })

  const {
    // 任务输入与启动
    prepareModAliasTaskAttachment, startModAliasGenerationTask, requestSingleModAliasGenerationResult,
    // 任务完成等待
    settleModAliasTaskCompletion, waitForModAliasTaskCompletion,
    // 检阅池状态与修改
    modAliasReviewTasks, modAliasReviewItemCount, getModAliasReviewTask,
    updateModAliasReviewTaskItem, removeModAliasReviewTask, removeModAliasReviewTaskItem, clearModAliasReviewTaskPool,
    // 事件桥接内部复用
    buildModAliasReviewTaskResult, upsertModAliasReviewTask, pruneDuplicateModAliasReviewItems,
  } = useModAliasActions({
    taskStore,
    modAliasTaskCompletionDataById, modAliasTaskCompletionWaiters, modAliasTaskRequestMetaById,
    modAliasReviewTaskPoolById, modAliasReviewTaskOrder,
    normalizeModAliasTaskInputItems, buildModSelectionAttachment,
    replaceGlobalAttachmentsByKind, removeGlobalAttachmentDraft,
  })

  const normalizeToolDefinition = (toolId = '', tool = {}) => {
    const normalizedId = normalizeText(toolId || tool?.id)
    const label = normalizeText(tool?.label)
    return {
      id: normalizedId,
      label: label || normalizedId,
      description: normalizeText(tool?.description),
      parameters: tool?.parameters && typeof tool.parameters === 'object' ? { ...tool.parameters } : {},
    }
  }

  const normalizedToolDefinitions = computed(() => (
    Object.fromEntries(
      Object.entries(runtimeDefinitionEditorMeta.value?.tools || {})
        .map(([toolId, tool]) => {
          const normalized = normalizeToolDefinition(toolId, tool)
          return normalized.id ? [normalized.id, normalized] : null
        })
        .filter(Boolean)
    )
  ))

  // 这里返回的是“允许范围”，不是会话默认勾选历史。
  // 新会话始终从允许范围全开开始，避免旧会话残留误导用户。
  const buildAssistantToolConfig = (assistant = {}) => {
    /**
     * 计算某个助手允许使用的工具集合与默认启用集合。
     *
     * 前端把“允许范围”和“当前会话勾选值”分开管理，
     * 这样助手定义变化时，旧会话也能被安全裁剪。
     */
    const allowedToolIds = normalizeStringList(assistant?.tool_scope_selectable)
    return {
      allowedToolIds,
      defaultEnabledToolIds: [...allowedToolIds],
    }
  }

  const getAssistantToolConfig = (assistantId = '') => {
    const assistant = getAssistantDefinition(assistantId)
    return buildAssistantToolConfig(assistant || {})
  }

  const buildAssistantSessionRequest = ({
    sessionId = '',
    requestId = '',
    assistantId = '',
    question = '',
    attachments = [],
    enabledTools = [],
    ownerType = 'assistant',
    ownerKey = '',
    overrideConfig = {},
    variables = {},
    requestPayload = {},
  } = {}) => {
    // 这里统一构造发给后端的 assistant_context，
    // 避免不同组件自行拼装时把 owner / tools / attachments 字段拼散。
    const normalizedSessionId = normalizeText(sessionId, createSessionId())
    const normalizedQuestion = normalizeText(question)
    const assistantContext = {
      assistant_id: normalizeText(assistantId),
      question: normalizedQuestion,
      owner_type: normalizeText(ownerType, 'assistant'),
      owner_key: normalizeText(ownerKey),
      override_config: { ...(overrideConfig || {}) },
      variables: { ...(variables || {}) },
      request_payload: {
        client_request_id: normalizeText(requestId),
        attachments: Array.isArray(attachments) ? attachments : [],
        enabled_tools: Array.isArray(enabledTools) ? enabledTools : [],
        ...(requestPayload || {}),
      },
    }

    return {
      session_id: normalizedSessionId,
      assistant_context: assistantContext,
    }
  }

  const resolveAssistantQuestion = ({
    assistantId = '',
    question = '',
    attachments = [],
  } = {}) => {
    // 日志助手允许“无显式问题直接开聊”，但前提是附件足够明确；
    // 这里统一补默认问题，避免后端入口为了日志场景再写一层前端推断。
    const normalizedQuestion = normalizeText(question)
    if (normalizedQuestion) return normalizedQuestion

    const normalizedAssistantId = normalizeText(assistantId)
    if (!['assistant.log_game', 'assistant.log_app'].includes(normalizedAssistantId)) {
      return ''
    }

    const diagnosisAttachment = Array.isArray(attachments)
      ? attachments.find(item => normalizeText(item?.kind) === 'diagnosis_context')
      : null
    if (!diagnosisAttachment) return ''

    const selector = diagnosisAttachment?.selector && typeof diagnosisAttachment.selector === 'object'
      ? diagnosisAttachment.selector
      : {}
    const selectorMode = normalizeText(selector.mode).toLowerCase()
    return selectorMode === 'all'
      ? '请基于本次全局扫描结果直接开始排错，给出最可能的问题根因、证据和修复建议。'
      : '请深度分析我提交的日志数据，并给出修复建议。'
  }

  const createSessionId = () => `ai_session_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`

  const getSession = (sessionId = '') => {
    /** 读取指定会话对象，不存在时返回 null。 */
    const normalizedSessionId = normalizeText(sessionId)
    return normalizedSessionId ? sessionsById[normalizedSessionId] || null : null
  }

  const createSession = (meta = {}) => {
    /** 创建一条新的本地会话实体，并插入会话顺序列表。 */
    const sessionId = normalizeText(meta.id, createSessionId())
    if (sessionsById[sessionId]) {
      return sessionsById[sessionId]
    }
    const session = createAssistantSession({ ...meta, id: sessionId })
    sessionsById[sessionId] = session
    sessionOrder.value.unshift(sessionId)
    return session
  }

  const updateSessionMeta = (sessionId, patch = {}) => {
    /** 对已有会话做浅层字段更新，并刷新更新时间。 */
    const session = getSession(sessionId)
    if (!session) return null
    Object.entries(patch || {}).forEach(([key, value]) => {
      if (value === undefined) return
      session[key] = value
    })
    session.updatedAt = Date.now()
    return session
  }

  const setCurrentSessionForOwner = (ownerKey, sessionId) => {
    const normalizedOwnerKey = normalizeText(ownerKey)
    const normalizedSessionId = normalizeText(sessionId)
    if (!normalizedOwnerKey || !normalizedSessionId) return null
    currentSessionByOwner[normalizedOwnerKey] = normalizedSessionId
    return getSession(normalizedSessionId)
  }

  const getCurrentSessionIdForOwner = (ownerKey = '') => normalizeText(currentSessionByOwner[normalizeText(ownerKey)])

  const getAssistantRuntimePrefs = (ownerKey = '', defaults = {}) => {
    /** 读取某个助手组件实例的临时请求偏好；不存在时用 defaults 初始化。 */
    const normalizedOwnerKey = normalizeText(ownerKey)
    if (!normalizedOwnerKey) {
      return createAssistantRuntimePrefs(defaults)
    }
    if (!assistantRuntimePrefsByOwner[normalizedOwnerKey]) {
      assistantRuntimePrefsByOwner[normalizedOwnerKey] = createAssistantRuntimePrefs(defaults)
    }
    return assistantRuntimePrefsByOwner[normalizedOwnerKey]
  }

  const updateAssistantRuntimePrefs = (ownerKey = '', patch = {}) => {
    /** 更新某个助手组件实例的临时请求偏好。 */
    const normalizedOwnerKey = normalizeText(ownerKey)
    if (!normalizedOwnerKey) return null
    const prefs = getAssistantRuntimePrefs(normalizedOwnerKey)
    const hasEnabledToolsTouched = Object.prototype.hasOwnProperty.call(patch || {}, 'enabledToolsTouched')
    const hasModelTouched = Object.prototype.hasOwnProperty.call(patch || {}, 'modelTouched')
    const hasTemperatureTouched = Object.prototype.hasOwnProperty.call(patch || {}, 'temperatureTouched')
    const hasReasoningModeTouched = Object.prototype.hasOwnProperty.call(patch || {}, 'reasoningModeTouched')
    Object.entries(patch || {}).forEach(([key, value]) => {
      if (value === undefined) return
      if (key === 'enabledTools') {
        prefs.enabledTools = Array.isArray(value) ? [...value] : []
        prefs.enabledToolsTouched = hasEnabledToolsTouched ? !!patch.enabledToolsTouched : true
      } else if (key === 'enabledToolsTouched') {
        prefs.enabledToolsTouched = !!value
      } else if (key === 'temperature') {
        prefs.temperature = value == null ? null : normalizeNumber(value, 0.7)
        prefs.temperatureTouched = hasTemperatureTouched ? !!patch.temperatureTouched : true
      } else if (key === 'temperatureTouched') {
        prefs.temperatureTouched = !!value
      } else if (key === 'model') {
        prefs.model = normalizeText(value)
        prefs.modelTouched = hasModelTouched ? !!patch.modelTouched : true
      } else if (key === 'modelTouched') {
        prefs.modelTouched = !!value
      } else if (key === 'reasoningMode') {
        prefs.reasoningMode = normalizeText(value, 'off').toLowerCase() || 'off'
        prefs.reasoningModeTouched = hasReasoningModeTouched ? !!patch.reasoningModeTouched : true
      } else if (key === 'reasoningModeTouched') {
        prefs.reasoningModeTouched = !!value
      }
    })
    prefs.updatedAt = Date.now()
    return prefs
  }

  const getOrCreateBoundSession = (ownerKey, meta = {}) => {
    /**
     * 读取或创建某个业务入口绑定的当前会话。
     *
     * ownerKey 表示“哪个页面上下文的会话”，这样同一助手也能同时服务
     * 于不同日志文件、不同面板或不同业务对象。
     */
    const normalizedOwnerKey = normalizeText(ownerKey)
    if (!normalizedOwnerKey) {
      return createSession(meta)
    }
    const currentSessionId = getCurrentSessionIdForOwner(normalizedOwnerKey)
    const existingSession = getSession(currentSessionId)
    if (existingSession) {
      const patch = {
        assistantId: meta.assistantId,
        ownerType: meta.ownerType,
        ownerKey: normalizedOwnerKey,
        title: meta.title,
        sourceType: meta.sourceType,
        filename: meta.filename,
      }
      updateSessionMeta(existingSession.id, patch)
      return existingSession
    }
    const session = createSession({
      ...meta,
      ownerKey: normalizedOwnerKey,
    })
    setCurrentSessionForOwner(normalizedOwnerKey, session.id)
    return session
  }

  const resetBoundSession = (ownerKey, meta = {}) => {
    /**
     * 为某个业务入口重建新会话，并把旧会话归档。
     *
     * 这样可以保留旧会话历史，又能确保新的对话从干净状态开始。
     */
    const normalizedOwnerKey = normalizeText(ownerKey)
    const previousSessionId = getCurrentSessionIdForOwner(normalizedOwnerKey)
    if (previousSessionId) {
      const previousSession = getSession(previousSessionId)
      if (previousSession) {
        previousSession.status = 'archived'
        previousSession.updatedAt = Date.now()
      }
    }
    const nextSession = createSession({
      ...meta,
      ownerKey: normalizedOwnerKey,
    })
    setCurrentSessionForOwner(normalizedOwnerKey, nextSession.id)
    return nextSession
  }

  const appendMessage = (sessionId, message) => {
    /** 向指定会话尾部追加一条标准化消息。 */
    const session = getSession(sessionId)
    if (!session) return null
    const now = Date.now()
    const normalizedMessage = normalizeSessionMessage(message, now)
    session.messages.push(normalizedMessage)
    session.updatedAt = Date.now()
    return normalizedMessage
  }

  const replaceMessages = (sessionId, messages = []) => {
    /** 用一组标准化后的消息整体替换会话消息流。 */
    const session = getSession(sessionId)
    if (!session) return null
    const now = Date.now()
    session.messages = Array.isArray(messages)
      ? messages.map((message, index) => normalizeSessionMessage(message, now + index))
      : []
    session.updatedAt = Date.now()
    return session
  }

  const findSessionMessage = (sessionId, {
    requestId = '',
    role = '',
    fromEnd = true,
  } = {}) => {
    /**
     * 在会话消息流中查找一条匹配消息。
     *
     * 默认从尾部反查，因为“当前活跃请求的最新 user/assistant 消息”
     * 是最常见的读取场景。
     */
    const session = getSession(sessionId)
    if (!session || !Array.isArray(session.messages) || session.messages.length === 0) return null

    const normalizedRequestId = normalizeText(requestId)
    const normalizedRole = normalizeText(role)
    const messages = fromEnd ? [...session.messages].reverse() : session.messages
    return messages.find((message) => {
      if (normalizedRole && normalizeText(message?.role) !== normalizedRole) return false
      if (normalizedRequestId && normalizeText(message?.request_id) !== normalizedRequestId) return false
      return true
    }) || null
  }

  const applyAssistantSessionResult = (sessionId, requestId, result = {}) => {
    const session = getSession(sessionId)
    if (!session) return null

    const userMessage = findSessionMessage(sessionId, { requestId, role: 'user' })
    const assistantMessage = findSessionMessage(sessionId, { requestId, role: 'assistant' })
    if (userMessage) {
      userMessage.messageUsage = result?.message_usage || null
      userMessage.promptInputBreakdown = result?.prompt_input_breakdown || null
      userMessage.updatedAt = Date.now()
    }
    if (assistantMessage) {
      assistantMessage.content = String(result?.analysis || '')
      assistantMessage.reasoning = String(result?.reasoning_content || assistantMessage.reasoning || '')
      assistantMessage.actions = Array.isArray(result?.actions) ? [...result.actions] : []
      assistantMessage.warnings = normalizeAssistantWarnings(result?.warnings)
      assistantMessage.messageUsage = result?.message_usage || null
      assistantMessage.tokenUsage = result?.token_usage || null
      assistantMessage.promptInputBreakdown = result?.prompt_input_breakdown || null
      assistantMessage.updatedAt = Date.now()
    }
    session.sessionUsageSummary = result?.session_usage_summary || null
    session.updatedAt = Date.now()
    consumePendingAttachmentKeysForRequest(requestId)
    return { session, userMessage, assistantMessage }
  }

  const bindRequestToSession = (requestId, sessionId) => {
    const normalizedRequestId = normalizeText(requestId)
    const session = getSession(sessionId)
    if (!normalizedRequestId || !session) return null
    session.activeRequestId = normalizedRequestId
    session.updatedAt = Date.now()
    return session
  }

  const setSessionThinking = (sessionId, isThinking, requestId = '') => {
    const session = getSession(sessionId)
    if (!session) return null
    session.isThinking = !!isThinking
    session.status = isThinking ? 'running' : session.status === 'archived' ? 'archived' : 'idle'
    session.activeRequestId = isThinking ? normalizeText(requestId) : (session.activeRequestId === requestId ? null : session.activeRequestId)
    session.updatedAt = Date.now()
    return session
  }

  const getActiveAssistantMessageForSession = (sessionId = '') => {
    const session = getSession(sessionId)
    if (!session) return null
    const activeRequestId = normalizeText(session.activeRequestId)
    if (activeRequestId) {
      const matched = findSessionMessage(sessionId, { requestId: activeRequestId, role: 'assistant' })
      if (matched) return matched
    }
    return findSessionMessage(sessionId, { role: 'assistant' })
  }

  const getActiveUserMessageForSession = (sessionId = '') => {
    const session = getSession(sessionId)
    if (!session) return null
    const activeRequestId = normalizeText(session.activeRequestId)
    if (activeRequestId) {
      const matched = findSessionMessage(sessionId, { requestId: activeRequestId, role: 'user' })
      if (matched) return matched
    }
    return findSessionMessage(sessionId, { role: 'user' })
  }

  const consumePendingAttachmentKeysForRequest = (requestId = '') => {
    const normalizedRequestId = normalizeText(requestId)
    if (!normalizedRequestId) return []
    const keys = Array.isArray(pendingConsumedAttachmentKeysByRequest[normalizedRequestId])
      ? [...pendingConsumedAttachmentKeysByRequest[normalizedRequestId]]
      : []
    delete pendingConsumedAttachmentKeysByRequest[normalizedRequestId]
    keys.forEach(removeGlobalAttachmentDraft)
    return keys
  }

  const applyAssistantStreamChunk = (sessionId = '', type = 'content', chunk = '') => {
    const normalizedSessionId = normalizeText(sessionId)
    if (!normalizedSessionId) return null
    const message = getActiveAssistantMessageForSession(normalizedSessionId)
    if (!message) return null
    if (type === 'reasoning') {
      message.reasoning = `${message.reasoning || ''}${String(chunk || '')}`
    } else {
      message.content = `${message.content || ''}${String(chunk || '')}`
    }
    message.updatedAt = Date.now()
    return message
  }

  const applyAssistantToolCall = (sessionId = '', payload = {}) => {
    const message = getActiveAssistantMessageForSession(sessionId)
    if (!message) return null
    if (!Array.isArray(message.tools)) {
      message.tools = []
    }
    message.tools.push({
      id: payload.tool_id,
      name: payload.name,
      displayName: payload.display_name || payload.name || '系统工具',
      arguments: payload.arguments || '',
      argumentsPreview: payload.arguments_preview || '',
      argumentsPretty: payload.arguments_pretty || payload.arguments || '无参数',
      status: 'running',
      summary: '',
      result: '',
      resultPretty: '',
      durationMs: null,
      expanded: false,
    })
    message.updatedAt = Date.now()
    return message
  }

  const applyAssistantToolResult = (sessionId = '', payload = {}) => {
    const message = getActiveAssistantMessageForSession(sessionId)
    if (!message || !Array.isArray(message.tools)) return null
    const tool = message.tools.find(item => item.id === payload.tool_id)
    if (!tool) return null
    tool.status = payload.status || 'done'
    tool.displayName = payload.display_name || tool.displayName || tool.name || '系统工具'
    tool.summary = payload.summary || ''
    tool.result = payload.result || ''
    tool.resultPretty = payload.result_pretty || payload.result || '暂无结果'
    tool.durationMs = payload.duration_ms ?? null
    message.updatedAt = Date.now()
    return tool
  }

  const applyAssistantRequestUsage = (
    sessionId = '',
    requestId = '',
    tokenUsage = null,
    messageUsage = null,
    promptInputBreakdown = null,
    options = {},
  ) => {
    const shouldConsumeAttachments = !!options.consumeAttachments
    const normalizedRequestId = normalizeText(requestId)
    const userMessage = normalizedRequestId
      ? findSessionMessage(sessionId, { requestId: normalizedRequestId, role: 'user' })
      : getActiveUserMessageForSession(sessionId)
    const assistantMessage = normalizedRequestId
      ? findSessionMessage(sessionId, { requestId: normalizedRequestId, role: 'assistant' })
      : getActiveAssistantMessageForSession(sessionId)

    if (userMessage) {
      userMessage.messageUsage = messageUsage || null
      userMessage.promptInputBreakdown = promptInputBreakdown || userMessage.promptInputBreakdown || null
      userMessage.updatedAt = Date.now()
    }
    if (assistantMessage) {
      assistantMessage.messageUsage = messageUsage || null
      assistantMessage.tokenUsage = tokenUsage || null
      assistantMessage.promptInputBreakdown = promptInputBreakdown || assistantMessage.promptInputBreakdown || null
      assistantMessage.updatedAt = Date.now()
    }
    if (normalizedRequestId && shouldConsumeAttachments) {
      consumePendingAttachmentKeysForRequest(normalizedRequestId)
    }
    return { userMessage, assistantMessage }
  }

  const markAssistantSessionCancelled = (sessionId = '') => {
    const session = getSession(sessionId)
    if (!session) return null
    setSessionThinking(sessionId, false, normalizeText(session.activeRequestId))
    return session
  }

  const refreshSessionTrace = async (sessionId) => {
    if (!window.pywebview) return null
    const normalizedSessionId = normalizeText(sessionId)
    if (!normalizedSessionId) return null
    const res = await window.pywebview.api.ai_get_trace_records(normalizedSessionId)
    if (!checkResult(res, '获取AI请求链记录')) return traceBySessionId[normalizedSessionId] || null
    const records = Array.isArray(res.data) ? res.data : []
    const traceSession = records[0] || null
    if (traceSession) {
      traceBySessionId[normalizedSessionId] = traceSession
    }
    return traceBySessionId[normalizedSessionId] || null
  }

  const openSessionTraceViewer = async (sessionId) => {
    const normalizedSessionId = normalizeText(sessionId)
    if (!normalizedSessionId) return
    traceModalState.visible = true
    traceModalState.sessionId = normalizedSessionId
    traceModalState.isLoading = true
    try {
      await refreshSessionTrace(normalizedSessionId)
    } finally {
      traceModalState.isLoading = false
    }
  }

  const closeSessionTraceViewer = () => {
    traceModalState.visible = false
    traceModalState.sessionId = ''
    traceModalState.isLoading = false
  }

  const runAssistantSession = async (payload = {}) => {
    if (!window.pywebview) return null
    const appStore = useAppStore()
    isLoading.value = true
    if (!appStore.settings.ai.enabled) {
      toast.warning('AI 功能未启用。请先在设置中开启 AI 功能并完成模型配置。')
      isLoading.value = false
      return null
    }
    try {
      const res = await window.pywebview.api.ai_execute_assistant_session(payload)
      if (checkResult(res, '发送 AI 对话')) {
        return normalizeAssistantSessionResult(res.data)
      }
      return null
    } catch (error) {
      console.error('AI 助手会话异常:', error)
      toast.error(toUserMessage(error?.message || error, 'AI 助手会话异常。可能是软件后端暂时不可用、模型服务无响应或网络请求中断，请稍后重试。'))
      return null
    } finally {
      isLoading.value = false
    }
  }

  const estimateAssistantSessionRequest = async (payload = {}) => {
    if (!window.pywebview) return null
    const appStore = useAppStore()
    if (!appStore.settings.ai.enabled) {
      return null
    }
    try {
      const res = await window.pywebview.api.ai_estimate_assistant_session_request(payload)
      if (res?.status === 'success') {
        return res.data || null
      }
      return null
    } catch (error) {
      console.warn('AI 助手请求估算异常:', error)
      return null
    }
  }

  const sendAssistantMessage = async ({
    sessionId = '',
    assistantId = '',
    ownerType = 'assistant',
    ownerKey = '',
    question = '',
    overrideConfig = {},
    variables = {},
    requestPayload = {},
    enabledTools = [],
  } = {}) => {
    const session = getSession(sessionId)
    if (!session) return null

    const requestId = `chat_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`
    const composerEntries = getSessionComposerAttachments(session.id, assistantId)
    const attachments = composerEntries.map(entry => entry.draft)
    const consumedAttachmentKeys = composerEntries.map(entry => entry.key)
    const effectiveQuestion = resolveAssistantQuestion({
      assistantId,
      question,
      attachments,
    })

    bindRequestToSession(requestId, session.id)
    setSessionThinking(session.id, true, requestId)

    const userMessage = appendMessage(session.id, {
      role: 'user',
      request_id: requestId,
      content: String(effectiveQuestion || ''),
      attachments,
    })
    const assistantMessage = appendMessage(session.id, {
      role: 'assistant',
      session_id: session.id,
      request_id: requestId,
      tools: [],
      content: '',
      reasoning: '',
      actions: [],
      warnings: [],
      tokenUsage: null,
      messageUsage: null,
    })

    pendingConsumedAttachmentKeysByRequest[requestId] = consumedAttachmentKeys
    const payload = buildAssistantSessionRequest({
      sessionId: session.id,
      requestId,
      assistantId,
      question: effectiveQuestion,
      attachments,
      enabledTools,
      ownerType,
      ownerKey,
      overrideConfig,
      variables,
      requestPayload,
    })

    // 先做一次轻量预估，只用于尽快把本轮体积感知反馈到界面，
    // 真正落盘和累计仍以后端完成后的正式统计为准。
    void estimateAssistantSessionRequest(payload).then((estimate) => {
      if (!estimate) return
      applyAssistantRequestUsage(
        session.id,
        requestId,
        estimate?.token_usage || null,
        estimate?.message_usage || null,
        estimate?.prompt_input_breakdown || null,
        { consumeAttachments: false },
      )
    })

    try {
      const result = await runAssistantSession(payload)
      if (!result) {
        delete pendingConsumedAttachmentKeysByRequest[requestId]
        assistantMessage.content = 'AI 请求失败。请检查模型服务、API Key、Base URL、代理设置和当前网络状态，详细原因已写入系统日志。'
        assistantMessage.updatedAt = Date.now()
        return { requestId, userMessage, assistantMessage, response: null }
      }

      applyAssistantSessionResult(session.id, requestId, result)
      if (result.cancelled && !String(assistantMessage.content || '').trim()) {
        assistantMessage.content = '本次分析已中断。'
      }
      return { requestId, userMessage, assistantMessage, response: result }
    } catch (error) {
      delete pendingConsumedAttachmentKeysByRequest[requestId]
      assistantMessage.content = toUserMessage(error?.message || error, '分析过程中发生错误。可能是模型服务、网络连接或软件内部状态暂时不可用，详细原因已写入系统日志。')
      assistantMessage.updatedAt = Date.now()
      return { requestId, userMessage, assistantMessage, response: null, error }
    } finally {
      setSessionThinking(session.id, false, requestId)
    }
  }

  const cancelAssistantSession = async (sessionId = '') => {
    if (!window.pywebview || !sessionId) return false
    try {
      const res = await window.pywebview.api.cancel_ai_session(sessionId)
      return !!checkResult(res, '取消 AI 回答')
    } catch (error) {
      console.error('取消 AI 助手会话失败:', error)
      return false
    }
  }

  // -----------------------------------------------------------------
  // 定义管理 (Definition CRUD)
  // -----------------------------------------------------------------
  const savePrompt = async (id, data) => {
    if (!window.pywebview) return false
    const res = await window.pywebview.api.ai_save_prompt(id, data)
    return checkResult(res, '保存模板', true) ? res.data : false
  }

  const saveAssistant = async (id, data) => {
    if (!window.pywebview) return false
    const res = await window.pywebview.api.ai_save_assistant(id, data)
    return checkResult(res, '保存助手', true) ? res.data : false
  }

  const saveTask = async (id, data) => {
    if (!window.pywebview) return false
    const res = await window.pywebview.api.ai_save_task(id, data)
    return checkResult(res, '保存任务', true) ? res.data : false
  }

  const deletePrompt = async (id) => {
    if (!window.pywebview) return false
    const res = await window.pywebview.api.ai_delete_prompt(id)
    return checkResult(res, '删除模板', true) ? res.data : false
  }

  // -----------------------------------------------------------------
  // 事件桥接 (Event Bridge)
  // -----------------------------------------------------------------
  const setupEventListeners = () => {
    if (window._rmmAiEventsInitialized) return
    window._rmmAiEventsInitialized = true

    window.addEventListener('ai-task-complete', (e) => {
      const taskId = normalizeText(e.detail?.task_id)
      const status = normalizeText(e.detail?.status)
      const payload = e.detail?.data && typeof e.detail.data === 'object' ? e.detail.data : {}
      const requestMeta = taskId ? modAliasTaskRequestMetaById[taskId] || null : null
      settleModAliasTaskCompletion(taskId, payload)
      if (!requestMeta) return

      // 单项生成直接交给调用方消费；只有“批量 + 需要检阅”才进入结果池。
      const shouldStoreForReview = !!requestMeta.needsReview && Number(requestMeta.inputCount || 0) > 1
      if (shouldStoreForReview) {
        const hasPayloadResults = Array.isArray(payload?.results) && payload.results.length > 0
        const shouldSkipCancelledTask = status === 'cancelled' && !hasPayloadResults
        if (!shouldSkipCancelledTask) {
          const reviewTask = buildModAliasReviewTaskResult({
            taskId,
            status,
            payload,
            requestMeta,
            message: normalizeText(e.detail?.message || payload?.message),
          })
          if (Array.isArray(reviewTask.items) && reviewTask.items.length > 0) {
            upsertModAliasReviewTask(taskId, reviewTask)
            pruneDuplicateModAliasReviewItems(taskId, reviewTask.items.map(item => item.package_id))
            useAppStore().uiState.showModAliasReviewModal = true
          }
        }
      }
      delete modAliasTaskRequestMetaById[taskId]
    })

    window.addEventListener('ai-chat-stream', (e) => {
      const { session_id, type, chunk } = e.detail || {}
      if (!session_id) return
      applyAssistantStreamChunk(session_id, type, chunk)
    })

    window.addEventListener('ai-tool-call', (e) => {
      const { session_id, ...payload } = e.detail || {}
      if (!session_id) return
      applyAssistantToolCall(session_id, payload)
    })

    window.addEventListener('ai-tool-result', (e) => {
      const { session_id, ...payload } = e.detail || {}
      if (!session_id) return
      applyAssistantToolResult(session_id, payload)
    })

    window.addEventListener('ai-request-usage', (e) => {
      const { session_id, request_id, token_usage, message_usage, prompt_input_breakdown } = e.detail || {}
      if (!session_id) return
      applyAssistantRequestUsage(
        session_id,
        request_id,
        token_usage || null,
        message_usage || null,
        prompt_input_breakdown || null,
        { consumeAttachments: true },
      )
    })

    window.addEventListener('ai-chat-cancelled', (e) => {
      const { session_id } = e.detail || {}
      if (!session_id) return
      markAssistantSessionCancelled(session_id)
    })
  }

  const initialize = async () => {
    setupEventListeners()
    return await getAiConfig()
  }

  const getToolDefinitions = () => normalizedToolDefinitions.value || {}

  return {
    // 运行时状态
    isLoading, runtimeAiConfig,
    sessionsById, sessionOrder, currentSessionByOwner,
    traceBySessionId, traceModalState,
    modAliasReviewTasks, modAliasReviewItemCount,
    // 定义读取
    getDefinitionEditorMeta, getToolDefinitions, getActionDefinitions,
    getAssistantDefinition, getAssistantToolConfig, getTaskDefinition, getPromptDefinition,
    // 附件
    getAttachmentDefinition, getAttachmentDisplayMeta, getSupportedAttachmentKindsForAssistant,
    buildLogOwnerKey, buildDiagnosisContextAttachment, buildModSelectionAttachment,
    upsertGlobalAttachmentDraft, removeGlobalAttachmentDraft, removeGlobalAttachmentsByKind, listGlobalAttachmentEntries,
    getSessionComposerAttachments, removeComposerAttachment, dismissSessionAttachment, resetSessionDismissedAttachments,
    // Mod 别名
    prepareModAliasTaskAttachment, startModAliasGenerationTask, requestSingleModAliasGenerationResult,
    getModAliasReviewTask, updateModAliasReviewTaskItem, removeModAliasReviewTask, removeModAliasReviewTaskItem, clearModAliasReviewTaskPool,
    // 会话
    createSession, getSession, updateSessionMeta,
    getCurrentSessionIdForOwner, setCurrentSessionForOwner,
    getAssistantRuntimePrefs, updateAssistantRuntimePrefs,
    getOrCreateBoundSession, resetBoundSession,
    appendMessage, replaceMessages, findSessionMessage, applyAssistantSessionResult,
    getActiveAssistantMessageForSession, getActiveUserMessageForSession,
    bindRequestToSession, setSessionThinking,
    resolveAssistantQuestion, buildAssistantSessionRequest,
    // Trace 与模型
    refreshSessionTrace, openSessionTraceViewer, closeSessionTraceViewer,
    getAiConfig, saveAIConfig, listAiProviders,
    getAiModels, getCachedAiModels, getCachedAiModelOptions,
    resolveAiModelCapabilities, getAiModelCapabilities, chatWithAI,
    // 请求与定义管理
    runAssistantSession, estimateAssistantSessionRequest, sendAssistantMessage, cancelAssistantSession,
    savePrompt, saveAssistant, saveTask, deletePrompt, initialize,
  }
})
