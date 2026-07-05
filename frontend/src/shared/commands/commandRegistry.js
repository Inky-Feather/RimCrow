import { normalizeKeybindingList } from './keybindingParser'
import { t } from '../i18n'

const commands = new Map()
let registerIndex = 0

const normalizeCommandIdSegment = (segment = '') => String(segment || '')
  .replace(/([a-z0-9])([A-Z])/g, '$1_$2')
  .replace(/[\s-]+/g, '_')
  .toLowerCase()

const commandLocaleKey = (id = '', field = '') => {
  const base = String(id || '').split('.').map(normalizeCommandIdSegment).filter(Boolean).join('.')
  return base && field ? `command.${base}.${field}` : ''
}

const resolveLocalizedCommandText = (key, fallback = '') => {
  const safeKey = String(key || '').trim()
  const safeFallback = String(fallback || '').trim()
  return safeKey ? t(safeKey, safeFallback) : safeFallback
}

const normalizeCommand = (command = {}) => {
  // 命令声明是插件和内置功能共同使用的最小契约，先归一化再进入注册表。
  const id = String(command.id || '').trim()
  if (!id) throw new Error('命令 ID 不能为空')
  const displayOnly = !!command.displayOnly
  if (!displayOnly && typeof command.run !== 'function') throw new Error(`命令 ${id} 缺少执行函数`)
  const titleKey = String(command.titleKey || commandLocaleKey(id, 'title')).trim()
  const titleDefault = String(command.titleDefault || command.title || id).trim()
  const categoryMeta = command.category && typeof command.category === 'object' ? command.category : null
  const categoryKey = String(command.categoryKey || categoryMeta?.key || '').trim()
  const categoryDefault = String(command.categoryDefault || categoryMeta?.defaultText || command.category || t('command.category.other', '其他')).trim()
  const descriptionKey = String(command.descriptionKey || commandLocaleKey(id, 'description')).trim()
  const descriptionDefault = String(command.descriptionDefault || command.description || '').trim()

  return {
    id,
    titleKey,
    titleDefault,
    get title() { return resolveLocalizedCommandText(titleKey, titleDefault) },
    categoryKey,
    categoryDefault,
    get category() { return resolveLocalizedCommandText(categoryKey, categoryDefault) },
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
    descriptionKey,
    descriptionDefault,
    get description() { return resolveLocalizedCommandText(descriptionKey, descriptionDefault) },
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
