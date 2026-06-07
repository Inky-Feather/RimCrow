const modListActionsByScope = new Map()

export const registerModListActions = (scope = '', actions = {}) => {
  // 列表移动依赖当前列表的筛选、排序和联锁状态，保留在组件内执行，命令层只按作用域找到执行者。
  const normalizedScope = String(scope || '').trim()
  if (!normalizedScope) return () => {}
  modListActionsByScope.set(normalizedScope, actions)
  return () => {
    if (modListActionsByScope.get(normalizedScope) === actions) {
      modListActionsByScope.delete(normalizedScope)
    }
  }
}

export const getModListActions = (scope = '') => {
  const normalizedScope = String(scope || '').trim()
  if (normalizedScope && modListActionsByScope.has(normalizedScope)) {
    return modListActionsByScope.get(normalizedScope)
  }
  if (normalizedScope.startsWith('mod-list:')) return null
  return null
}
