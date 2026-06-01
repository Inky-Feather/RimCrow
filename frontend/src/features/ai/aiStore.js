// frontend/src/stores/aiStore.js

import { defineStore } from 'pinia'
import { computed, reactive, ref } from 'vue'
import { checkResult, normalizeStringList, normalizeText, toast } from '../../shared/lib/common'
import { normalizeAssistantSessionResult } from './runtime/aiActionRuntime'
import { buildAttachmentDisplayMeta, buildDiagnosisContextAttachmentDraft } from './runtime/aiAttachmentRuntime'
import { cleanRichText } from '../../shared/lib/text'
import { useAppStore } from '../../app/stores/appStore'
import { useModStore } from '../mod/modStore'
import { useTaskStore } from '../../app/stores/taskStore'

// -----------------------------------------------------------------
// 工具函数 (Utils)
// -----------------------------------------------------------------
const normalizeTimestamp = (value, fallback = Date.now()) => {
  /** 把任意时间戳输入规整成可比较的毫秒值。 */
  const numeric = Number(value)
  return Number.isFinite(numeric) && numeric > 0 ? numeric : fallback
}

const normalizeNumber = (value, fallback = 0) => {
  /** 把数值输入规整成 Number，失败时回退到明确默认值。 */
  const numeric = Number(value)
  return Number.isFinite(numeric) ? numeric : fallback
}

const PENDING_REASONING_CAPABILITIES = {
  supports_reasoning: false,
  supports_reasoning_effort: false,
  reasoning_mode_kind: 'pending',
  reasoning_options: [
    { value: 'off', label: '关闭' },
    { value: 'auto', label: '自动' },
  ],
  default_session_reasoning_mode: 'auto',
}

const UNSUPPORTED_REASONING_CAPABILITIES = {
  supports_reasoning: false,
  supports_reasoning_effort: false,
  reasoning_mode_kind: 'unsupported',
  reasoning_options: [
    { value: 'off', label: '关闭' },
  ],
  default_session_reasoning_mode: 'off',
}

const DEFAULT_AI_BASE_URLS = {
  openai_compatible: 'https://api.openai.com/v1',
  anthropic: 'https://api.anthropic.com',
  gemini: 'https://generativelanguage.googleapis.com',
  ollama: 'http://127.0.0.1:11434',
}

const resolveAiProviderBaseUrl = (provider = '', baseUrl = '') => {
  const normalizedProvider = normalizeText(provider, 'openai_compatible').toLowerCase()
  const explicitBaseUrl = normalizeText(baseUrl).replace(/\/+$/, '')
  return explicitBaseUrl || DEFAULT_AI_BASE_URLS[normalizedProvider] || ''
}

const normalizeAssistantWarnings = (warnings = []) => {
  if (!Array.isArray(warnings)) return []
  return warnings
    .map((warning) => {
      if (warning && typeof warning === 'object') {
        return {
          ...warning,
          code: normalizeText(warning.code),
          message: normalizeText(warning.message || warning.detail),
        }
      }
      return { code: '', message: normalizeText(warning) }
    })
    .filter(warning => warning.message)
}

// 会话消息需要尽量保持结构稳定：
// 这样流式补写、trace 回放和重新打开窗口时都能走同一套渲染路径。
const normalizeSessionMessage = (message = {}, fallbackTimestamp = Date.now()) => {
  /**
   * 统一整理会话消息结构。
   *
   * 这一步的目标不是“校验消息是否合法”，而是保证消息在以下场景下
   * 都能走同一套渲染逻辑：
   * - 流式补写
   * - 历史回放
   * - trace 回填
   * - 重新打开面板后的本地状态恢复
   */
  const role = normalizeText(message?.role)
  const isAssistant = role === 'assistant'
  const rawContent = message?.content
  return {
    ...message,
    role,
    session_id: normalizeText(message?.session_id),
    request_id: normalizeText(message?.request_id),
    content: isAssistant
      ? String(rawContent ?? '')
      : (typeof rawContent === 'string' ? rawContent : String(rawContent ?? '')),
    attachments: Array.isArray(message?.attachments) ? [...message.attachments] : [],
    tools: Array.isArray(message?.tools) ? [...message.tools] : [],
    actions: Array.isArray(message?.actions) ? [...message.actions] : [],
    warnings: isAssistant ? normalizeAssistantWarnings(message?.warnings) : [],
    reasoning: isAssistant ? String(message?.reasoning ?? '') : '',
    tokenUsage: message?.tokenUsage || null,
    messageUsage: message?.messageUsage || null,
    promptInputBreakdown: message?.promptInputBreakdown || null,
    createdAt: normalizeTimestamp(message?.createdAt, fallbackTimestamp),
    updatedAt: normalizeTimestamp(message?.updatedAt, fallbackTimestamp),
  }
}

  const createAttachmentDraft = ({
    kind = '',
    source = {},
    selector = {},
    snapshot = {},
    options = {},
  } = {}) => ({
    // 附件草稿只表达“前端当前选择态”，不尝试伪造后端解析结果；
    // 这样后续附件协议扩展时，旧草稿仍然可以被后端安全兜底。
    kind: normalizeText(kind),
    source: { ...(source || {}) },
  selector: { ...(selector || {}) },
  ...(snapshot && Object.keys(snapshot).length ? { snapshot: { ...snapshot } } : {}),
  ...(options && Object.keys(options).length ? { options: { ...options } } : {}),
})

  const createAssistantSession = ({
  id,
  assistantId = '',
  ownerType = 'assistant',
  ownerKey = '',
  title = '',
  sourceType = '',
  filename = '',
  } = {}) => ({
    // 会话是多轮助手的一级实体，负责记住消息流、附件屏蔽态和会话级覆写；
    // ownerKey 只负责把业务入口绑定到“当前活跃会话”。
    id,
  assistantId,
  ownerType,
  ownerKey,
  title: normalizeText(title, '新会话'),
  sourceType: normalizeText(sourceType, 'game'),
  filename: normalizeText(filename),
  createdAt: Date.now(),
  updatedAt: Date.now(),
  status: 'idle',
  messages: [],
  dismissedAttachmentKeys: [],
  userInput: '',
  isThinking: false,
  activeRequestId: null,
  consumedAutoStartNonce: null,
  sessionUsageSummary: null,
})

const createAssistantRuntimePrefs = ({
  model = '',
  modelTouched = false,
  temperature = null,
  temperatureTouched = false,
  reasoningMode = 'auto',
  reasoningModeTouched = false,
  enabledTools = [],
  enabledToolsTouched = false,
} = {}) => ({
  // 这些是“助手组件实例”的临时请求偏好，不属于某一条会话历史。
  // 新建/清空会话时应继续沿用，避免用户反复设置同一入口的模型和工具。
  model: normalizeText(model),
  modelTouched: !!modelTouched,
  temperature: temperature == null ? null : normalizeNumber(temperature, 0.7),
  temperatureTouched: !!temperatureTouched,
  reasoningMode: normalizeText(reasoningMode, 'auto').toLowerCase() || 'auto',
  reasoningModeTouched: !!reasoningModeTouched,
  enabledTools: Array.isArray(enabledTools) ? [...enabledTools] : [],
  enabledToolsTouched: !!enabledToolsTouched,
  updatedAt: Date.now(),
})

  const createEmptyTraceModalState = () => ({
  visible: false,
  sessionId: '',
  isLoading: false,
})

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

  const buildAiModelCacheKey = (tempConfig = {}) => JSON.stringify({
    provider: normalizeText(tempConfig?.provider),
    base_url: resolveAiProviderBaseUrl(tempConfig?.provider, tempConfig?.base_url),
    api_key: normalizeText(tempConfig?.api_key),
  })

  const normalizeReasoningCapabilityResult = (payload = {}, fallback = UNSUPPORTED_REASONING_CAPABILITIES) => ({
    supports_reasoning: !!payload?.supports_reasoning,
    supports_reasoning_effort: !!payload?.supports_reasoning_effort,
    reasoning_mode_kind: normalizeText(payload?.reasoning_mode_kind, fallback.reasoning_mode_kind || 'unsupported'),
    reasoning_options: Array.isArray(payload?.reasoning_options) && payload.reasoning_options.length > 0
      ? payload.reasoning_options.map(item => ({
        value: normalizeText(item?.value),
        label: normalizeText(item?.label, normalizeText(item?.value)),
      })).filter(item => item.value)
      : [...(fallback.reasoning_options || [{ value: 'off', label: '关闭' }])],
    default_session_reasoning_mode: normalizeText(
      payload?.default_session_reasoning_mode,
      fallback.default_session_reasoning_mode || 'off',
    ).toLowerCase(),
  })

  const getPromptDefinition = (promptId = '') => {
    const normalizedId = normalizeText(promptId)
    return normalizedId ? promptDefinitions.value?.[normalizedId] || null : null
  }

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

  const getAttachmentDefinition = (attachmentKind = '') => {
    const normalizedKind = normalizeText(attachmentKind)
    return normalizedKind ? (runtimeDefinitionEditorMeta.value?.attachments || {})[normalizedKind] || null : null
  }

  const getAttachmentDisplayMeta = (attachment) => buildAttachmentDisplayMeta(attachment, getAttachmentDefinition)

  const getSupportedAttachmentKindsForAssistant = (assistantId = '') => {
    /** 读取某个助手当前绑定 Prompt 支持的附件类型集合。 */
    const assistant = getAssistantDefinition(assistantId)
    const prompt = getPromptDefinition(assistant?.prompt_id || '')
    const attachmentKinds = Array.isArray(prompt?.attachment_kinds) ? prompt.attachment_kinds : []
    return [...new Set(attachmentKinds.map(item => normalizeText(item)).filter(Boolean))]
  }

  const buildGlobalAttachmentEntryKey = (draft = {}) => {
    /**
     * 为全局附件生成稳定键。
     *
     * 键的目标不是绝对唯一，而是能表达“同一业务上下文的同一份附件”，
     * 便于后续 upsert 替换，而不是不断堆新条目。
     */
    const kind = normalizeText(draft?.kind)
    const source = draft?.source && typeof draft.source === 'object' ? draft.source : {}
    const identity = {
      kind,
      owner_type: normalizeText(source.owner_type),
      source_type: normalizeText(source.source_type),
      filename: normalizeText(source.filename),
      package_id: normalizeText(source.package_id),
    }
    return JSON.stringify(identity)
  }

  const buildLogOwnerKey = (sourceType = 'game', filename = '') => {
    const normalizedSourceType = normalizeText(sourceType, 'game')
    const normalizedFilename = normalizeText(filename, '__no_file__')
    return `log:${normalizedSourceType}:${normalizedFilename}`
  }

  const buildDiagnosisContextAttachment = (options = {}) => createAttachmentDraft(
    buildDiagnosisContextAttachmentDraft(options)
  )

  const normalizeModAliasTaskInputItem = (mod = {}) => {
    /** 把单个模组输入整理成别名任务可接受的最小对象。 */
    const packageId = normalizeText(mod?.package_id || mod?.packageId).toLowerCase()
    if (!packageId) return null
    return {
      package_id: packageId,
      name: normalizeText(mod?.name),
      // 这里先做一层轻量清洗，只是为了让界面状态保持稳定；
      // 真正入模前仍以后端归一化结果为准，避免两边规则漂移。
      description: cleanRichText(mod?.description, 800),
    }
  }

  const normalizeModAliasTaskInputItems = (mods = []) => {
    /** 归一化并按 package_id 去重整批别名任务输入。 */
    const itemMap = new Map()
    ;(Array.isArray(mods) ? mods : []).forEach((item) => {
      const normalized = normalizeModAliasTaskInputItem(item)
      if (!normalized?.package_id) return
      itemMap.set(normalized.package_id, normalized)
    })
    return Array.from(itemMap.values())
  }

  const buildModSelectionAttachment = ({
    mods = [],
    ownerType = 'task',
    mode = 'single',
    summary = '',
  } = {}) => {
    /**
     * 构建模组选择附件。
     *
     * 别名任务和通用助手都复用这类附件，因此这里直接把
     * package_id 列表和快照文案打包成统一协议。
     */
    const normalizedMods = (Array.isArray(mods) ? mods : [])
      .map(item => normalizeModAliasTaskInputItem(item))
      .filter(Boolean)
    const packageIds = normalizedMods.map(item => item.package_id)
    const firstPackageId = packageIds[0] || ''
    const firstName = normalizeText(normalizedMods[0]?.name, firstPackageId)
    const summaryText = normalizeText(summary) || (
      normalizedMods.length <= 1
        ? firstName
        : `已选 ${normalizedMods.length} 个模组`
    )
    return createAttachmentDraft({
      kind: 'mod_selection',
      source: {
        owner_type: normalizeText(ownerType, 'task'),
        package_id: firstPackageId,
      },
      selector: {
        mode: normalizeText(mode, normalizedMods.length > 1 ? 'multiple' : 'single'),
        values: packageIds,
      },
      snapshot: {
        summary: summaryText,
        mods: normalizedMods,
      },
    })
  }

  const upsertGlobalAttachmentDraft = (draft = {}, meta = {}) => {
    // 全局附件池用于在“日志面板/任务面板/助手面板”之间共享上下文，
    // 不直接挂在某条消息上，避免会话创建前就丢失用户选择态。
    const normalizedDraft = createAttachmentDraft(draft)
    const key = buildGlobalAttachmentEntryKey(normalizedDraft)
    if (!normalizeText(normalizedDraft.kind) || !key) return ''
    const now = Date.now()
    globalAttachmentEntries[key] = {
      key,
      draft: normalizedDraft,
      meta: { ...(meta || {}) },
      createdAt: normalizeTimestamp(globalAttachmentEntries[key]?.createdAt, now),
      updatedAt: now,
    }
    return key
  }

  const removeGlobalAttachmentDraft = (attachmentKey = '') => {
    const normalizedKey = normalizeText(attachmentKey)
    if (!normalizedKey || !globalAttachmentEntries[normalizedKey]) return false
    const removedEntry = globalAttachmentEntries[normalizedKey]
    delete globalAttachmentEntries[normalizedKey]
    Object.values(sessionsById).forEach((session) => {
      if (!Array.isArray(session?.dismissedAttachmentKeys)) return
      session.dismissedAttachmentKeys = session.dismissedAttachmentKeys.filter(key => key !== normalizedKey)
    })
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('ai-attachment-removed', {
        detail: {
          key: normalizedKey,
          draft: removedEntry?.draft || null,
          meta: removedEntry?.meta || null,
        },
      }))
    }
    return true
  }

  const listGlobalAttachmentEntries = () => (
    Object.values(globalAttachmentEntries)
      .filter(entry => entry?.draft)
      .sort((a, b) => Number(a.createdAt || 0) - Number(b.createdAt || 0))
  )

  const removeGlobalAttachmentsByKind = (attachmentKind = '') => {
    const normalizedKind = normalizeText(attachmentKind)
    if (!normalizedKind) return []
    const removedKeys = listGlobalAttachmentEntries()
      .filter(entry => normalizeText(entry?.draft?.kind) === normalizedKind)
      .map(entry => entry.key)
    removedKeys.forEach(removeGlobalAttachmentDraft)
    return removedKeys
  }

  const replaceGlobalAttachmentsByKind = (attachmentKind = '', drafts = [], meta = {}) => {
    removeGlobalAttachmentsByKind(attachmentKind)
    return (Array.isArray(drafts) ? drafts : [])
      .map(draft => upsertGlobalAttachmentDraft(draft, meta))
      .filter(Boolean)
  }

  const isAttachmentCompatibleWithSession = (entry = {}, session = null) => {
    const draft = entry?.draft && typeof entry.draft === 'object' ? entry.draft : {}
    const source = draft?.source && typeof draft.source === 'object' ? draft.source : {}
    if (!session) return true

    const sessionOwnerType = normalizeText(session.ownerType)
    const sessionSourceType = normalizeText(session.sourceType)
    const sessionFilename = normalizeText(session.filename)
    const attachmentOwnerType = normalizeText(source.owner_type)
    const attachmentSourceType = normalizeText(source.source_type)
    const attachmentFilename = normalizeText(source.filename)

    if (sessionOwnerType === 'log_viewer' || attachmentOwnerType === 'log_viewer') {
      if (sessionSourceType && attachmentSourceType && sessionSourceType !== attachmentSourceType) {
        return false
      }
      if (sessionFilename && attachmentFilename && sessionFilename !== attachmentFilename) {
        return false
      }
    }

    return true
  }

  const getSessionComposerAttachments = (sessionId = '', assistantId = '') => {
    const session = getSession(sessionId)
    const dismissedKeys = new Set(Array.isArray(session?.dismissedAttachmentKeys) ? session.dismissedAttachmentKeys : [])
    const supportedKinds = new Set(getSupportedAttachmentKindsForAssistant(assistantId))
    return listGlobalAttachmentEntries()
      .filter(entry => supportedKinds.has(normalizeText(entry?.draft?.kind)))
      .filter(entry => !dismissedKeys.has(entry.key))
      .filter(entry => isAttachmentCompatibleWithSession(entry, session))
  }

  const dismissSessionAttachment = (sessionId = '', attachmentKey = '') => {
    const session = getSession(sessionId)
    const normalizedKey = normalizeText(attachmentKey)
    if (!session || !normalizedKey) return null
    const next = new Set(Array.isArray(session.dismissedAttachmentKeys) ? session.dismissedAttachmentKeys : [])
    next.add(normalizedKey)
    session.dismissedAttachmentKeys = [...next]
    session.updatedAt = Date.now()
    return session
  }

  const resetSessionDismissedAttachments = (sessionId = '') => {
    const session = getSession(sessionId)
    if (!session) return null
    session.dismissedAttachmentKeys = []
    session.updatedAt = Date.now()
    return session
  }

  const removeComposerAttachment = (sessionId = '', attachmentKey = '') => {
    // 日志来源的 diagnosis_context 属于“共享附件”，移除时需要真的删掉草稿；
    // 其它附件默认只做当前会话级 dismiss，避免误伤别的入口。
    const normalizedKey = normalizeText(attachmentKey)
    if (!normalizedKey) return false
    const attachmentEntry = globalAttachmentEntries[normalizedKey]
    const attachmentKind = normalizeText(attachmentEntry?.draft?.kind)
    const attachmentOwnerType = normalizeText(attachmentEntry?.draft?.source?.owner_type)
    if (attachmentKind === 'diagnosis_context' && attachmentOwnerType === 'log_viewer') {
      return removeGlobalAttachmentDraft(normalizedKey)
    }
    return !!dismissSessionAttachment(sessionId, normalizedKey)
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

  const prepareModAliasTaskAttachment = ({
    mods = [],
    ownerType = 'task',
    mode = 'single',
  } = {}) => {
    // 别名任务统一通过 mod_selection 附件传递输入对象，
    // 这样单模组重试和批量生成共用一套后端入口。
    const normalizedMods = normalizeModAliasTaskInputItems(mods)
    const draft = buildModSelectionAttachment({
      mods: normalizedMods,
      ownerType,
      mode,
    })
    const attachmentKeys = replaceGlobalAttachmentsByKind('mod_selection', [draft], {
      ownerType,
      taskPurpose: 'mod_alias_generation',
    })
    return { attachments: [draft], attachmentKeys, mods: normalizedMods }
  }

  const startModAliasGenerationTask = async ({
    mods = [],
    ownerType = 'task',
    needsReview = false,
  } = {}) => {
    /**
     * 发起模组别名生成任务。
     *
     * 这里负责把 UI 层输入统一改写成后端任务协议，并根据是否批量审阅
     * 记录对应的本地请求元数据。
     */
    if (!window.pywebview) return ''
    const appStore = useAppStore()
    if (!appStore.settings.ai.enabled) {
      toast.warning('AI功能未启用！')
      return ''
    }
    const normalizedMods = normalizeModAliasTaskInputItems(mods)
    if (normalizedMods.length === 0) {
      toast.warning('没有可供处理的模组输入')
      return ''
    }
    const isBatch = normalizedMods.length > 1
    const normalizedNeedsReview = !!needsReview && isBatch
    const attachmentMode = isBatch ? 'multiple' : 'single'
    const prepared = prepareModAliasTaskAttachment({
      mods: normalizedMods,
      ownerType,
      mode: attachmentMode,
    })
    const payload = {
      attachments: prepared.attachments,
      needs_review: normalizedNeedsReview,
    }
    const res = await window.pywebview.api.ai_start_task('task.mod_alias_generation', payload)
    if (!checkResult(res, '启动 AI 别名生成任务')) {
      prepared.attachmentKeys.forEach(removeGlobalAttachmentDraft)
      return ''
    }

    const taskId = normalizeText(res?.data?.task_id)
    if (!taskId) {
      prepared.attachmentKeys.forEach(removeGlobalAttachmentDraft)
      return ''
    }
    prepared.attachmentKeys.forEach(removeGlobalAttachmentDraft)

    modAliasTaskRequestMetaById[taskId] = {
      taskId,
      ownerType: normalizeText(ownerType, 'task'),
      createdAt: Date.now(),
      needsReview: normalizedNeedsReview,
      inputCount: normalizedMods.length,
      inputPackageIds: normalizedMods.map(item => item.package_id),
      title: normalizedMods.length > 1 ? 'AI 别名批量生成' : 'AI 别名生成',
    }

    taskStore.createPlaceholderTask({
      id: taskId,
      type: 'ai-task',
      status: 'pending',
      progress: 0,
      message: '任务已加入后台队列',
      metrics: {
        task_id: taskId,
        task_key: 'task.mod_alias_generation',
        title: modAliasTaskRequestMetaById[taskId].title,
        total: normalizedMods.length,
      },
    })
    return taskId
  }

  const requestSingleModAliasGenerationResult = async ({
    packageId = '',
    name = '',
    description = '',
    ownerType = 'review_modal',
  } = {}) => {
    /**
     * 以“单条立即返回”的方式请求一个模组的别名生成结果。
     *
     * 本质上仍走异步任务通道，只是前端在这里等待完成并提取第一条成功结果，
     * 方便检阅弹窗里的单项重试复用同一后端能力。
     */
    const normalizedPackageId = normalizeText(packageId).toLowerCase()
    if (!normalizedPackageId) return null
    const taskId = await startModAliasGenerationTask({
      mods: [{ package_id: normalizedPackageId, name, description }],
      ownerType,
      needsReview: false,
    })
    if (!taskId) return null
    const completionPayload = await waitForModAliasTaskCompletion(taskId).catch(() => null)
    delete modAliasTaskCompletionDataById[taskId]
    const finalResults = Array.isArray(completionPayload?.results) ? completionPayload.results : []
    const first = finalResults.find(item => !item?._failed) || null
    return first && !first._failed ? first : null
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

  const getAiConfig = async () => {
    if (!window.pywebview) return
    const res = await window.pywebview.api.ai_get_config()
    if (checkResult(res, '获取AI配置')) {
      runtimeAiConfig.value = res.data || null
      return res.data
    }
  }

  const saveAIConfig = async (configData) => {
    if (!window.pywebview) return
    const res = await window.pywebview.api.ai_save_config(configData)
    if (checkResult(res, '保存AI配置', true)) {
      return true
    }
  }

  const listAiProviders = () => providerDefinitions.value || []

  const getCachedAiModels = (tempConfig = {}) => {
    const cacheKey = buildAiModelCacheKey(tempConfig)
    const models = modelListCache[cacheKey]
    return Array.isArray(models) ? [...models] : []
  }

  const getCachedAiModelOptions = (tempConfig = {}) => (
    getCachedAiModels(tempConfig).map(model => ({ value: model, label: model }))
  )

  const getAiModels = async (tempConfig, { forceRefresh = false, warnOnEmpty = false, silent = false } = {}) => {
    if (!window.pywebview) return []
    if (!tempConfig || !tempConfig.provider) {
      return []
    }
    const cacheKey = buildAiModelCacheKey(tempConfig)
    if (!forceRefresh) {
      const cachedModels = getCachedAiModels(tempConfig)
      if (cachedModels.length > 0) {
        return cachedModels
      }
    }
    isLoading.value = true
    try {
      const res = await window.pywebview.api.ai_get_models(tempConfig)
      if (checkResult(res, '获取AI模型', false, { silent })) {
        const models = Array.isArray(res.data) ? res.data.map(item => normalizeText(item)).filter(Boolean) : []
        modelListCache[cacheKey] = [...new Set(models)].sort((a, b) => a.localeCompare(b))
        if (warnOnEmpty && modelListCache[cacheKey].length === 0) {
          const provider = normalizeText(tempConfig?.provider, 'unknown')
          const baseUrl = resolveAiProviderBaseUrl(tempConfig?.provider, tempConfig?.base_url)
          toast.warning(`未获取到 AI 模型列表，请确认 ${provider} 服务已启动且 Base URL 可访问：${baseUrl}`, { timeout: 8000 })
        }
        return getCachedAiModels(tempConfig)
      }
    } finally {
      isLoading.value = false
    }
    return getCachedAiModels(tempConfig)
  }

  const resolveAiModelCapabilities = (tempConfig = {}) => {
    const provider = normalizeText(tempConfig?.provider)
    const model = normalizeText(tempConfig?.model)
    const baseUrl = normalizeText(tempConfig?.base_url)
    if (!provider || !model) {
      return {
        provider,
        model,
        base_url: baseUrl,
        policy_name: '',
        ...PENDING_REASONING_CAPABILITIES,
      }
    }
    const meta = capabilityMeta.value || {}
    const providerScope = normalizeText(meta?.provider_scope, 'openai_compatible')
    const unsupported = normalizeReasoningCapabilityResult(meta?.unsupported, UNSUPPORTED_REASONING_CAPABILITIES)
    if (provider !== providerScope) {
      return {
        provider,
        model,
        base_url: baseUrl,
        policy_name: '',
        ...unsupported,
      }
    }
    const policies = Array.isArray(meta?.policies) ? meta.policies : []
    const matchedPolicy = policies.find((policy) => {
      const patterns = Array.isArray(policy?.matches) ? policy.matches : []
      return patterns.some((pattern) => {
        try {
          return new RegExp(String(pattern || ''), 'i').test(model)
        } catch {
          return false
        }
      })
    }) || null
    const resolved = matchedPolicy
      ? normalizeReasoningCapabilityResult(matchedPolicy, unsupported)
      : unsupported
    return {
      provider,
      model,
      base_url: baseUrl,
      policy_name: normalizeText(matchedPolicy?.name),
      requires_reasoning_replay: !!matchedPolicy?.requires_reasoning_replay,
      prefer_responses: !!matchedPolicy?.prefer_responses,
      ...resolved,
    }
  }

  const getAiModelCapabilities = async (tempConfig = {}) => resolveAiModelCapabilities(tempConfig)

  const chatWithAI = async (prompt, tempConfig) => {
    if (!window.pywebview) {
      return { ok: false, text: '', error: '界面尚未完成初始化', isEmpty: false }
    }
    isLoading.value = true
    try {
      const res = await window.pywebview.api.ai_chat(prompt, tempConfig)
      if (checkResult(res, '测试 AI 回复')) {
        const payload = res.data
        const text = typeof payload === 'string'
          ? payload
          : String(payload?.text ?? payload ?? '')
        return {
          ok: text.trim().length > 0,
          text,
          error: text.trim().length > 0 ? '' : '模型已返回，但内容为空',
          isEmpty: text.trim().length === 0,
          raw: payload,
        }
      }
      return {
        ok: false,
        text: '',
        error: String(res?.message || 'AI 请求失败'),
        isEmpty: false,
      }
    } catch (error) {
      console.error('AI 聊天请求异常:', error)
      return {
        ok: false,
        text: '',
        error: error?.message || String(error),
        isEmpty: false,
      }
    } finally {
      isLoading.value = false
    }
  }

  const runAssistantSession = async (payload = {}) => {
    if (!window.pywebview) return null
    const appStore = useAppStore()
    isLoading.value = true
    if (!appStore.settings.ai.enabled) {
      toast.warning('AI功能未启用！')
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
        assistantMessage.content = '⚠️ AI 请求失败。'
        assistantMessage.updatedAt = Date.now()
        return { requestId, userMessage, assistantMessage, response: null }
      }

      applyAssistantSessionResult(session.id, requestId, result)
      if (result.cancelled && !String(assistantMessage.content || '').trim()) {
        assistantMessage.content = '🛑 本次分析已中断。'
      }
      return { requestId, userMessage, assistantMessage, response: result }
    } catch (error) {
      delete pendingConsumedAttachmentKeysByRequest[requestId]
      assistantMessage.content = `⚠️ 分析过程中发生错误: ${error?.message || error || '未知错误'}`
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

  const settleModAliasTaskCompletion = (taskId = '', payload = null) => {
    const normalizedTaskId = normalizeText(taskId)
    if (!normalizedTaskId) return
    modAliasTaskCompletionDataById[normalizedTaskId] = payload
    const waiters = modAliasTaskCompletionWaiters.get(normalizedTaskId) || []
    modAliasTaskCompletionWaiters.delete(normalizedTaskId)
    waiters.forEach(resolve => {
      try {
        resolve(payload)
      } catch {
        // no-op
      }
    })
  }

  const waitForModAliasTaskCompletion = (taskId = '', timeout = 600000) => {
    const normalizedTaskId = normalizeText(taskId)
    if (!normalizedTaskId) return Promise.resolve(null)
    if (Object.prototype.hasOwnProperty.call(modAliasTaskCompletionDataById, normalizedTaskId)) {
      return Promise.resolve(modAliasTaskCompletionDataById[normalizedTaskId] || null)
    }
    return new Promise((resolve) => {
      const timer = window.setTimeout(() => {
        const waiters = modAliasTaskCompletionWaiters.get(normalizedTaskId) || []
        modAliasTaskCompletionWaiters.set(
          normalizedTaskId,
          waiters.filter(entry => entry !== wrappedResolve),
        )
        resolve(null)
      }, timeout)
      const wrappedResolve = (payload) => {
        clearTimeout(timer)
        resolve(payload)
      }
      const waiters = modAliasTaskCompletionWaiters.get(normalizedTaskId) || []
      waiters.push(wrappedResolve)
      modAliasTaskCompletionWaiters.set(normalizedTaskId, waiters)
    })
  }

  const normalizeModAliasReviewResultItem = (item = {}, fallbackPackageId = '') => {
    const packageId = normalizeText(item?.package_id || fallbackPackageId).toLowerCase()
    if (!packageId) return null
    return {
      package_id: packageId,
      alias_name: normalizeText(item?.alias_name),
      notes: normalizeText(item?.notes),
      _failed: !!item?._failed,
      _attempt_count: normalizeNumber(item?._attempt_count, 0),
      _error: normalizeText(item?._error || item?.error || item?.message),
    }
  }

  const buildFailedModAliasReviewResultItem = (packageId = '', message = '') => {
    const normalizedPackageId = normalizeText(packageId).toLowerCase()
    if (!normalizedPackageId) return null
    return {
      package_id: normalizedPackageId,
      alias_name: '',
      notes: '',
      _failed: true,
      _attempt_count: 0,
      _error: normalizeText(message),
    }
  }

  const normalizeModAliasReviewResultItems = ({
    items = [],
    requestedPackageIds = [],
    fallbackError = '',
  } = {}) => {
    const requestedIds = [...new Set(
      (Array.isArray(requestedPackageIds) ? requestedPackageIds : [])
        .map(item => normalizeText(item).toLowerCase())
        .filter(Boolean)
    )]
    const requestedIdSet = new Set(requestedIds)
    const itemMap = new Map()

    ;(Array.isArray(items) ? items : []).forEach((rawItem) => {
      const normalized = normalizeModAliasReviewResultItem(rawItem)
      if (!normalized?.package_id) return
      if (requestedIdSet.size > 0 && !requestedIdSet.has(normalized.package_id)) return
      itemMap.set(normalized.package_id, normalized)
    })

    requestedIds.forEach((packageId) => {
      if (itemMap.has(packageId)) return
      const failedItem = buildFailedModAliasReviewResultItem(packageId, fallbackError)
      if (failedItem) {
        itemMap.set(packageId, failedItem)
      }
    })

    return Array.from(itemMap.values())
  }

  const createModAliasReviewTaskResult = (taskId = '', patch = {}) => ({
    taskId: normalizeText(taskId),
    title: normalizeText(patch?.title, '模组别名批量检阅'),
    status: normalizeText(patch?.status, 'success'),
    ownerType: normalizeText(patch?.ownerType, 'task'),
    createdAt: normalizeTimestamp(patch?.createdAt, Date.now()),
    completedAt: normalizeTimestamp(patch?.completedAt, Date.now()),
    inputCount: Math.max(0, normalizeNumber(patch?.inputCount, 0)),
    inputPackageIds: Array.isArray(patch?.inputPackageIds)
      ? [...new Set(patch.inputPackageIds.map(item => normalizeText(item).toLowerCase()).filter(Boolean))]
      : [],
    message: normalizeText(patch?.message),
    meta: patch?.meta && typeof patch.meta === 'object' ? { ...patch.meta } : {},
    items: Array.isArray(patch?.items) ? [...patch.items] : [],
  })

  const getModAliasReviewTask = (taskId = '') => {
    const normalizedTaskId = normalizeText(taskId)
    return normalizedTaskId ? modAliasReviewTaskPoolById[normalizedTaskId] || null : null
  }

  const upsertModAliasReviewTask = (taskId = '', patch = {}) => {
    const normalizedTaskId = normalizeText(taskId)
    if (!normalizedTaskId) return null
    const existing = getModAliasReviewTask(normalizedTaskId)
    const next = existing
      ? {
        ...existing,
        ...patch,
        taskId: normalizedTaskId,
        title: normalizeText(patch?.title, existing.title || '模组别名批量检阅'),
        status: normalizeText(patch?.status, existing.status || 'success'),
        ownerType: normalizeText(patch?.ownerType, existing.ownerType || 'task'),
        createdAt: normalizeTimestamp(patch?.createdAt, existing.createdAt || Date.now()),
        completedAt: normalizeTimestamp(patch?.completedAt, Date.now()),
        inputCount: Math.max(0, normalizeNumber(patch?.inputCount, existing.inputCount || 0)),
        inputPackageIds: Array.isArray(patch?.inputPackageIds)
          ? [...new Set(patch.inputPackageIds.map(item => normalizeText(item).toLowerCase()).filter(Boolean))]
          : [...(existing.inputPackageIds || [])],
        message: normalizeText(patch?.message, existing.message || ''),
        meta: {
          ...(existing.meta || {}),
          ...((patch?.meta && typeof patch.meta === 'object') ? patch.meta : {}),
        },
        items: Array.isArray(patch?.items) ? [...patch.items] : [...(existing.items || [])],
      }
      : createModAliasReviewTaskResult(normalizedTaskId, patch)
    modAliasReviewTaskPoolById[normalizedTaskId] = next
    if (!modAliasReviewTaskOrder.value.includes(normalizedTaskId)) {
      modAliasReviewTaskOrder.value.unshift(normalizedTaskId)
    }
    return next
  }

  const removeModAliasReviewTask = (taskId = '') => {
    const normalizedTaskId = normalizeText(taskId)
    if (!normalizedTaskId || !modAliasReviewTaskPoolById[normalizedTaskId]) return false
    delete modAliasReviewTaskPoolById[normalizedTaskId]
    modAliasReviewTaskOrder.value = modAliasReviewTaskOrder.value.filter(id => id !== normalizedTaskId)
    return true
  }

  const updateModAliasReviewTaskItem = (taskId = '', packageId = '', patch = {}) => {
    const task = getModAliasReviewTask(taskId)
    const normalizedPackageId = normalizeText(packageId).toLowerCase()
    if (!task || !normalizedPackageId || !Array.isArray(task.items)) return false
    const index = task.items.findIndex(item => normalizeText(item?.package_id).toLowerCase() === normalizedPackageId)
    if (index < 0) return false
    const normalizedItem = normalizeModAliasReviewResultItem({
      ...task.items[index],
      ...(patch || {}),
      package_id: normalizedPackageId,
    })
    if (!normalizedItem) return false
    task.items.splice(index, 1, normalizedItem)
    task.completedAt = Date.now()
    return true
  }

  const removeModAliasReviewTaskItem = (taskId = '', packageId = '') => {
    const task = getModAliasReviewTask(taskId)
    const normalizedPackageId = normalizeText(packageId).toLowerCase()
    if (!task || !normalizedPackageId || !Array.isArray(task.items)) return false
    const nextItems = task.items.filter(item => normalizeText(item?.package_id).toLowerCase() !== normalizedPackageId)
    if (nextItems.length === task.items.length) return false
    task.items = nextItems
    task.completedAt = Date.now()
    if (task.items.length === 0) {
      removeModAliasReviewTask(taskId)
    }
    return true
  }

  const clearModAliasReviewTaskPool = () => {
    Object.keys(modAliasReviewTaskPoolById).forEach((taskId) => {
      delete modAliasReviewTaskPoolById[taskId]
    })
    modAliasReviewTaskOrder.value = []
  }

  const pruneDuplicateModAliasReviewItems = (currentTaskId = '', packageIds = []) => {
    const duplicateIds = new Set(
      (Array.isArray(packageIds) ? packageIds : [])
        .map(item => normalizeText(item).toLowerCase())
        .filter(Boolean)
    )
    if (duplicateIds.size === 0) return
    // 检阅池只保留每个模组的最新结果，避免旧任务和新任务同时修改同一条数据。
    modAliasReviewTaskOrder.value.slice().forEach((taskId) => {
      if (taskId === currentTaskId) return
      const task = getModAliasReviewTask(taskId)
      if (!task || !Array.isArray(task.items)) return
      const nextItems = task.items.filter(item => !duplicateIds.has(normalizeText(item?.package_id).toLowerCase()))
      if (nextItems.length === task.items.length) return
      task.items = nextItems
      task.completedAt = Date.now()
      if (task.items.length === 0) {
        removeModAliasReviewTask(taskId)
      }
    })
  }

  const buildModAliasReviewTaskResult = ({
    taskId = '',
    status = '',
    payload = {},
    requestMeta = {},
    message = '',
  } = {}) => {
    const meta = payload?.meta && typeof payload.meta === 'object' ? payload.meta : {}
    const requestedPackageIds = Array.isArray(requestMeta?.inputPackageIds) ? requestMeta.inputPackageIds : []
    const normalizedItems = normalizeModAliasReviewResultItems({
      items: Array.isArray(payload?.results) ? payload.results : [],
      requestedPackageIds,
      fallbackError: message || (status === 'error' ? '任务执行失败' : ''),
    })
    return {
      taskId: normalizeText(taskId),
      title: normalizeText(requestMeta?.title, '模组别名批量检阅'),
      status: normalizeText(status, 'success'),
      ownerType: normalizeText(requestMeta?.ownerType, 'task'),
      createdAt: normalizeTimestamp(meta?.created_at, requestMeta?.createdAt || Date.now()),
      completedAt: Date.now(),
      inputCount: normalizeNumber(meta?.input_total, requestMeta?.inputCount || normalizedItems.length),
      inputPackageIds: requestedPackageIds,
      message: normalizeText(message),
      meta: {
        ...meta,
        needs_review: true,
      },
      items: normalizedItems,
    }
  }

  const modAliasReviewTasks = computed(() => (
    modAliasReviewTaskOrder.value
      .map(taskId => modAliasReviewTaskPoolById[taskId] || null)
      .filter(Boolean)
  ))

  const modAliasReviewItemCount = computed(() => (
    modAliasReviewTasks.value.reduce((sum, task) => sum + (Array.isArray(task?.items) ? task.items.length : 0), 0)
  ))

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

  const getDefinitionEditorMeta = () => runtimeDefinitionEditorMeta.value || {}
  const getToolDefinitions = () => normalizedToolDefinitions.value || {}
  const getActionDefinitions = () => getDefinitionEditorMeta().actions || {}
  const getAssistantDefinition = (assistantId = '') => {
    const normalizedId = normalizeText(assistantId)
    return normalizedId ? (runtimeAiConfig.value?.assistants || {})[normalizedId] || null : null
  }
  const getTaskDefinition = (taskId = '') => {
    const normalizedId = normalizeText(taskId)
    return normalizedId ? (runtimeAiConfig.value?.tasks || {})[normalizedId] || null : null
  }

  return {
    isLoading,
    runtimeAiConfig,
    sessionsById,
    sessionOrder,
    currentSessionByOwner,
    traceBySessionId,
    traceModalState,
    modAliasReviewTasks,
    modAliasReviewItemCount,
    getDefinitionEditorMeta,
    getToolDefinitions,
    getActionDefinitions,
    getAssistantDefinition,
    getAssistantToolConfig,
    getTaskDefinition,
    getPromptDefinition,
    getAttachmentDefinition,
    getAttachmentDisplayMeta,
    getSupportedAttachmentKindsForAssistant,
    buildLogOwnerKey,
    buildDiagnosisContextAttachment,
    buildModSelectionAttachment,
    resolveAssistantQuestion,
    buildAssistantSessionRequest,
    upsertGlobalAttachmentDraft,
    removeGlobalAttachmentDraft,
    removeGlobalAttachmentsByKind,
    listGlobalAttachmentEntries,
    getSessionComposerAttachments,
    removeComposerAttachment,
    dismissSessionAttachment,
    resetSessionDismissedAttachments,
    prepareModAliasTaskAttachment,
    startModAliasGenerationTask,
    requestSingleModAliasGenerationResult,
    getModAliasReviewTask,
    updateModAliasReviewTaskItem,
    removeModAliasReviewTask,
    removeModAliasReviewTaskItem,
    clearModAliasReviewTaskPool,
    createSession,
    getSession,
    updateSessionMeta,
    getCurrentSessionIdForOwner,
    setCurrentSessionForOwner,
    getAssistantRuntimePrefs,
    updateAssistantRuntimePrefs,
    getOrCreateBoundSession,
    resetBoundSession,
    appendMessage,
    replaceMessages,
    findSessionMessage,
    applyAssistantSessionResult,
    getActiveAssistantMessageForSession,
    getActiveUserMessageForSession,
    bindRequestToSession,
    setSessionThinking,
    refreshSessionTrace,
    openSessionTraceViewer,
    closeSessionTraceViewer,
    getAiConfig,
    saveAIConfig,
    listAiProviders,
    getAiModels,
    getCachedAiModels,
    getCachedAiModelOptions,
    resolveAiModelCapabilities,
    getAiModelCapabilities,
    chatWithAI,
    runAssistantSession,
    estimateAssistantSessionRequest,
    sendAssistantMessage,
    cancelAssistantSession,
    savePrompt,
    saveAssistant,
    saveTask,
    deletePrompt,
    initialize,
  }
})
