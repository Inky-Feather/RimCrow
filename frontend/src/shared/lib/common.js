import { h } from 'vue'
import { createToastInterface, globalEventBus } from 'vue-toastification'
import { t } from '../i18n.js'
import { buildUserErrorMessage, stripLogHint } from './userErrorMessage.js'

// -----------------------------------------------------------------
// 文本与列表工具 (Text / Collection Utils)
// -----------------------------------------------------------------
/**
 * 提取分割线模组标题的有效文本。
 * 兼容两类语法，且包裹符号数量不固定：
 * 1. 等号包裹：`=标题=`、`===标题===`
 * 2. 注释风格包裹：斜杠 + 多个星号 + 标题 + 多个星号 + 斜杠
 *
 * 返回空字符串表示它不是合法的分割线标题。
 */
export const extractSectionHeaderTitle = (value = '') => {
  const name = String(value ?? '').trim()
  if (!name) return ''

  const equalsMatch = name.match(/^=+\s*(.*?)\s*=+$/)
  if (equalsMatch) {
    return String(equalsMatch[1] || '').trim()
  }

  const commentMatch = name.match(/^\/\*+\s*(.*?)\s*\*+\/$/)
  if (commentMatch) {
    return String(commentMatch[1] || '').trim()
  }

  return ''
}

export const isSectionHeaderTitle = (value = '') => !!extractSectionHeaderTitle(value)

export const normalizeText = (value, fallback = '') => {
  // 统一在边界层收口空值和首尾空白，避免各 store/组件重复写 String(...).trim()。
  const text = String(value ?? '').trim()
  return text || fallback
}

export const normalizeStringList = (values = []) => {
  // 这里顺手去重，原因是很多前端表单项最终会回写到后端白名单字段，
  // 如果不在前端先压平，界面展示和提交结果会同时出现重复项。
  const normalized = []
  const seen = new Set()
  for (const value of Array.isArray(values) ? values : []) {
    const text = normalizeText(value)
    if (!text || seen.has(text)) continue
    seen.add(text)
    normalized.push(text)
  }
  return normalized
}

const displayNameCollator = new Intl.Collator('zh-CN', { numeric: true, sensitivity: 'base' })

// 标签、分组这类面向用户的列表统一按可见名称排序，避免不同入口顺序忽左忽右。
export const compareDisplayName = (left, right) => (
  displayNameCollator.compare(normalizeText(left), normalizeText(right))
)

export const sortTextByName = (values = []) => (
  [...(Array.isArray(values) ? values : [])].sort((left, right) => compareDisplayName(left, right))
)

export const sortByDisplayName = (items = [], getName = item => item?.name ?? item) => (
  [...(Array.isArray(items) ? items : [])].sort((left, right) => (
    compareDisplayName(getName(left), getName(right))
  ))
)

// 全局 Toast 实例
export const toast = createToastInterface(globalEventBus)

const OPEN_SYSTEM_LOG_EVENT = 'rimcrow-open-system-log-target'

export const requestOpenSystemLog = (errorId = '') => {
  if (typeof window === 'undefined') return
  const normalizedErrorId = normalizeText(errorId)
  const detail = { sourceType: 'app', errorId: normalizedErrorId, live: true }
  window.__RIMCROW_PENDING_LOG_TARGET__ = detail
  window.dispatchEvent(new CustomEvent(OPEN_SYSTEM_LOG_EVENT, { detail }))
}

const UserErrorToast = {
  props: {
    message: { type: String, required: true },
    errorId: { type: String, default: '' },
  },
  emits: ['close-toast'],
  setup(props, { emit }) {
    return () => h('div', { class: 'max-w-[24rem] space-y-2 text-sm leading-5' }, [
      h('div', { class: 'whitespace-pre-wrap' }, props.message),
      props.errorId
        ? h('button', {
          type: 'button',
          class: 'rounded bg-bg-overlay/10 px-2 py-1 text-xs font-bold hover:bg-bg-overlay/20',
          onClick: () => {
            requestOpenSystemLog(props.errorId)
            emit('close-toast')
          },
        }, t('toast.api.open_corresponding_log', '查看对应系统日志'))
        : null,
    ])
  },
}

// -----------------------------------------------------------------
// 深拷贝工具 (Clone Utils)
// -----------------------------------------------------------------
const toPlainCloneable = (value, seen = new WeakMap()) => {
  if (value == null || typeof value !== 'object') {
    return value
  }
  if (typeof value === 'function') {
    return undefined
  }
  if (typeof Window !== 'undefined' && value instanceof Window) {
    return undefined
  }
  if (seen.has(value)) {
    return seen.get(value)
  }
  if (Array.isArray(value)) {
    const arr = []
    seen.set(value, arr)
    value.forEach((item) => {
      const cloned = toPlainCloneable(item, seen)
      if (cloned !== undefined) arr.push(cloned)
    })
    return arr
  }
  const result = {}
  seen.set(value, result)
  Object.entries(value).forEach(([key, item]) => {
    const cloned = toPlainCloneable(item, seen)
    if (cloned !== undefined) {
      result[key] = cloned
    }
  })
  return result
}

// 深拷贝函数
export const deepClone = (value) => {
  // 这里不能盲信 structuredClone：
  // - Vue 的 reactive/proxy 对象直接 structuredClone 时可能抛 DataCloneError
  // - 某些桥接层返回的数据也可能夹带不可克隆引用
  // 因此统一采用“先快路径，失败再降级”的策略，避免前端配置页直接白屏。
  if (value == null || typeof value !== 'object') {
    return value
  }

  const plainValue = toPlainCloneable(value)

  if (typeof globalThis.structuredClone === 'function') {
    try {
      return globalThis.structuredClone(plainValue)
    } catch (error) {
      console.warn('structuredClone 失败，回退到 JSON 深拷贝:', error)
    }
  }

  try {
    return JSON.parse(JSON.stringify(plainValue))
  } catch (error) {
    console.warn('JSON 深拷贝失败，回退到手写递归拷贝:', error)
  }

  if (Array.isArray(plainValue)) {
    return plainValue.map(item => deepClone(item))
  }

  const result = {}
  Object.entries(plainValue).forEach(([key, item]) => {
    if (typeof item === 'function') return
    result[key] = deepClone(item)
  })
  return result
}

// -----------------------------------------------------------------
// API 结果提示 (Result Helpers)
// -----------------------------------------------------------------
export const toUserMessage = (value = '', fallback = t('errors.fallback.operation_unfinished', '操作未完成。可能是网络连接、路径权限、配置或运行环境暂时不可用。')) => {
  return buildUserErrorMessage(value && typeof value === 'object' ? value : String(value || ''), fallback, t)
}

export const getApiResponseMessage = (res, fallback = '') => {
  return stripLogHint(buildUserErrorMessage(res && typeof res === 'object' ? res : {}, fallback, t) || fallback)
}

export const showUserErrorToast = (payload = {}, fallback = '', options = {}) => {
  const data = payload && typeof payload === 'object' ? payload : { message: payload }
  const { variant = 'error', ...toastOptions } = options || {}
  const message = buildUserErrorMessage(data, fallback, t)
  const errorId = normalizeText(
    data.error_id
    || data.errorId
  )
  if (errorId) {
    toast[variant]({ component: UserErrorToast, props: { message, errorId } }, toastOptions)
    return
  }
  toast[variant](stripLogHint(message), toastOptions)
}

export const checkResult = (res, workname, showSuccess = false, options = {}) => {
  const debugMode = options?.debugMode ?? (
    typeof window !== 'undefined' ? !!window.__APP_DEBUG_MODE__ : false
  )
  const silent = !!options?.silent
  if (debugMode) console.debug('API 结果检查:', workname, res)
  if (res?.status === 'success') {
    if (showSuccess && !silent) toast.success(t('toast.api.success', '{workname}已完成', { workname }), { timeout: 1000 })
    return true
  }
  if (silent) return false
  if (res?.status === 'warning') {
    const message = getApiResponseMessage(res, t('errors.fallback.operation_warning', '操作已完成，但有部分情况需要确认。'))
    showUserErrorToast({ ...(res || {}), user_message: t('toast.api.warning', '{workname}需要确认：\n{message}', { workname, message }) }, message, { variant: 'warning' })
  } else {
    const message = getApiResponseMessage(res, t('errors.fallback.work_failed', '{workname}未完成。可能是网络连接、路径权限、配置或运行环境暂时不可用。', { workname }))
    showUserErrorToast({ ...(res || {}), user_message: t('toast.api.error', '{workname}失败：\n{message}', { workname, message }) }, message)
  }
  return false
}
