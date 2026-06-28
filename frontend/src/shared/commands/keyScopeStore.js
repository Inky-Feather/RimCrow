const scopeLayerStack = []
let lastActiveScope = ''

export const pushKeyScopeLayer = (scope = '') => {
  // 浮层、弹窗等临时区域用栈表达优先级，后打开的区域先处理快捷键。
  const normalized = String(scope || '').trim()
  if (!normalized) return () => {}
  const token = { scope: normalized, id: `${normalized}:${Date.now()}:${Math.random().toString(36).slice(2)}` }
  scopeLayerStack.push(token)
  return () => popKeyScopeLayer(token.id)
}

export const popKeyScopeLayer = (tokenId = '') => {
  const index = scopeLayerStack.findIndex(item => item.id === tokenId || item.scope === tokenId)
  if (index >= 0) scopeLayerStack.splice(index, 1)
}

export const setActiveKeyScope = (scope = '') => {
  lastActiveScope = String(scope || '').trim()
}

export const getDomKeyScope = (target) => {
  if (typeof HTMLElement === 'undefined' || !(target instanceof HTMLElement)) return ''
  return String(target.closest('[data-key-scope]')?.dataset?.keyScope || '').trim()
}

export const getKeyScopeSearchOrder = (target) => {
  // 判定顺序：临时浮层 > 事件所在 DOM 区域 > 最近交互区域 > 全局。
  const scopes = []
  for (let index = scopeLayerStack.length - 1; index >= 0; index -= 1) {
    scopes.push(scopeLayerStack[index].scope)
  }
  const domScope = getDomKeyScope(target)
  if (domScope) scopes.push(domScope)
  if (lastActiveScope) scopes.push(lastActiveScope)
  scopes.push('global')
  return [...new Set(scopes.filter(Boolean))]
}

export const commandScopeMatches = (commandScope = 'global', activeScope = 'global') => {
  const command = String(commandScope || 'global').trim()
  const active = String(activeScope || 'global').trim()
  if (command === active) return true
  if (command === 'global') return active === 'global'
  // 子作用域可继承父作用域命令，例如 mod-list:active 可以触发 mod-list 命令。
  return active.startsWith(`${command}:`)
}
