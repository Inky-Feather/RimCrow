import { normalizeKeybindingList } from './keybindingParser'

const commands = new Map()
let registerIndex = 0

const normalizeCommand = (command = {}) => {
  // 命令声明是插件和内置功能共同使用的最小契约，先归一化再进入注册表。
  const id = String(command.id || '').trim()
  if (!id) throw new Error('命令 ID 不能为空')
  const displayOnly = !!command.displayOnly
  if (!displayOnly && typeof command.run !== 'function') throw new Error(`命令 ${id} 缺少执行函数`)

  return {
    id,
    title: String(command.title || id).trim(),
    category: String(command.category || 'common.other').trim(),
    scope: String(command.scope || 'global').trim() || 'global',
    defaultKeys: normalizeKeybindingList(command.defaultKeys || []),
    lockedKeys: normalizeKeybindingList(command.lockedKeys || []),
    displayKeys: normalizeKeybindingList(command.displayKeys || []),
    allowInInput: !!command.allowInInput,
    captureWhenDisabled: !!command.captureWhenDisabled,
    dangerLevel: String(command.dangerLevel || 'normal').trim(),
    source: String(command.source || 'builtin').trim(),
    displayOnly,
    keybindingReadonly: !!(command.keybindingReadonly || displayOnly),
    priority: Number(command.priority || 0),
    description: String(command.description || '').trim(),
    enabled: typeof command.enabled === 'function' ? command.enabled : () => true,
    run: typeof command.run === 'function' ? command.run : () => {},
    _registerIndex: registerIndex++,
  }
}

export const registerCommand = (command, { replace = true } = {}) => {
  const normalized = normalizeCommand(command)
  if (!replace && commands.has(normalized.id)) {
    throw new Error(`命令已存在: ${normalized.id}`)
  }
  commands.set(normalized.id, normalized)
  return normalized
}

export const registerCommands = (commandList = [], options = {}) => {
  return commandList.map(command => registerCommand(command, options))
}

export const getCommand = (commandId = '') => commands.get(String(commandId || '').trim()) || null

export const getAllCommands = () => Array.from(commands.values())

export const clearCommands = () => {
  commands.clear()
  registerIndex = 0
}

export const canRunCommand = (command, context = {}, args = {}) => {
  if (!command) return false
  try {
    // enabled 只影响能否执行，不影响设置页展示；失败时降级为不可执行，避免快捷键运行时中断。
    return command.enabled(context, args) !== false
  } catch (error) {
    console.warn(`检查命令可用状态失败: ${command.id}`, error)
    return false
  }
}

export const runCommand = async (commandId, context = {}, args = {}) => {
  const command = getCommand(commandId)
  if (!command || !canRunCommand(command, context, args)) return false
  await command.run(context, args)
  return true
}
