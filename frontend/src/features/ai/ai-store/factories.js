import { normalizeText } from '../../../shared/lib/common'

export const normalizeTimestamp = (value, fallback = Date.now()) => {
  /** 把任意时间戳输入规整成可比较的毫秒值。 */
  const numeric = Number(value)
  return Number.isFinite(numeric) && numeric > 0 ? numeric : fallback
}

export const normalizeNumber = (value, fallback = 0) => {
  /** 把数值输入规整成 Number，失败时回退到明确默认值。 */
  const numeric = Number(value)
  return Number.isFinite(numeric) ? numeric : fallback
}

export const normalizeAssistantWarnings = (warnings = []) => {
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
export const normalizeSessionMessage = (message = {}, fallbackTimestamp = Date.now()) => {
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

export const createAttachmentDraft = ({
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

export const createAssistantSession = ({
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

export const createAssistantRuntimePrefs = ({
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

export const createEmptyTraceModalState = () => ({
  visible: false,
  sessionId: '',
  isLoading: false,
})
