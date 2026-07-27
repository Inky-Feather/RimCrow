const DEFAULT_TRANSLATE = (_key, defaultText) => defaultText
const DEFAULT_UNKNOWN_ERROR = t => t('errors.common.unknown_operation_unfinished', '操作未完成。请检查网络连接、配置、路径权限或稍后重试。')
const TECHNICAL_MESSAGE_PATTERN = /(?:Traceback|Exception|Error code:|Client Error|Server Error|HTTP[S]?:\/\/|ConnectionPool|ReadTimeout|ProxyError|requests\.|httpx\.|openai\.|RuntimeError|FileNotFoundError|PermissionError|TimeoutError)/i

const normalizeText = (value = '') => String(value ?? '').trim()
const looksTechnicalMessage = (value = '') => TECHNICAL_MESSAGE_PATTERN.test(normalizeText(value))

export const stripLogHint = (value = '') => {
  const text = normalizeText(value)
    .replace(/[，,。；;]?\s*(详细原因|失败详情)已写入系统日志[。.]?/g, '')
    .replace(/[，,。；;]?\s*可点击查看系统日志了解详情[。.]?/g, '')
    .replace(/[，,。；;]?\s*请查看系统日志[。.]?/g, '')
    .replace(/[，,。；;]?\s*请查看日志[。.]?/g, '')
    .replace(/，。/g, '。')
    .replace(/。。+/g, '。')
    .trim()
  if (!text) return ''
  return /[。.!?！？]$/.test(text) ? text : `${text}。`
}

export const buildUserErrorMessage = (value = {}, fallback = '', translate = DEFAULT_TRANSLATE) => {
  const payload = value && typeof value === 'object' ? value : {}
  const rawText = typeof value === 'string' ? normalizeText(value) : normalizeText(payload.message || '')
  const messageKey = normalizeText(payload.message_key)
  const messageParams = payload.message_params || {}
  const userMessage = stripLogHint(payload.user_message || '')

  if (messageKey) {
    const translated = stripLogHint(translate(messageKey, userMessage || fallback, messageParams))
    if (translated) return translated
  }

  if (userMessage) return userMessage

  if (rawText && !looksTechnicalMessage(rawText)) return stripLogHint(rawText)

  const fallbackMessage = stripLogHint(fallback)
  if (fallbackMessage) return fallbackMessage

  return DEFAULT_UNKNOWN_ERROR(translate)
}
