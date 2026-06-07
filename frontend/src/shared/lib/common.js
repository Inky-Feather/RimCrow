import { createToastInterface, globalEventBus } from 'vue-toastification'

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

// 全局 Toast 实例
export const toast = createToastInterface(globalEventBus)

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
export const checkResult = (res, workname, showSuccess = false, options = {}) => {
  const debugMode = options?.debugMode ?? (
    typeof window !== 'undefined' ? !!window.__RMM_DEBUG_MODE__ : false
  )
  const silent = !!options?.silent
  if (debugMode) console.log('checkResult', workname, res)
  if (res.status === 'success') {
    if (showSuccess && !silent) toast.success(`${workname}成功`, { timeout: 1000 })
    return true
  }
  if (silent) return false
  if (res.status === 'warning') {
    toast.warning(`${workname}注意: \n${res.message}`)
  } else {
    toast.error(`${workname}失败: \n${res.message}`)
  }
  return false
}
