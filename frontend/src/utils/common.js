import { createToastInterface, globalEventBus } from 'vue-toastification'

/**
 * 判断一个名称是否应被视为“启用列表分组标题”。
 * 目前兼容两种写法：
 * 1. `=标题=`
 * 2. 斜杠星号包裹标题，例如注释风格标题
 *
 * 这样既兼容旧的等号包裹方案，也兼容部分用户使用注释风格名称
 * 来做纯标题模组的习惯，避免折叠功能只认单一格式。
 */
export const isSectionHeaderTitle = (value = '') => {
  const name = String(value ?? '').trim()
  if (!name) return false

  const isEqualsWrapped = name.length >= 2 && name.startsWith('=') && name.endsWith('=')
  const isCommentWrapped = name.length >= 4 && name.startsWith('/*') && name.endsWith('*/')

  return isEqualsWrapped || isCommentWrapped
}

// 全局 Toast 实例
export const toast = createToastInterface(globalEventBus)

// 深拷贝函数
export const deepClone = (value) => {
  if (typeof globalThis.structuredClone === 'function') {
    return globalThis.structuredClone(value)
  }
  return JSON.parse(JSON.stringify(value))
}

// 检查 API 响应结果
export const checkResult = (res, workname, showSuccess = false, options = {}) => {
  const debugMode = options?.debugMode ?? (
    typeof window !== 'undefined' ? !!window.__RMM_DEBUG_MODE__ : false
  )
  if (debugMode) console.log('checkResult', workname, res)
  if (res.status === 'success') {
    if (showSuccess) toast.success(`${workname}成功`, { timeout: 1000 })
    return true
  }
  if (res.status === 'warning') {
    toast.warning(`${workname}注意: \n${res.message}`)
  } else {
    toast.error(`${workname}失败: \n${res.message}`)
  }
  return false
}
