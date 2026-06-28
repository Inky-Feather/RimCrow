import { canRunCommand, getAllCommands } from './commandRegistry'
import { buildEffectiveKeybindingMap } from './keybindingConflicts'
import { eventToKeybinding, eventToMouseKeybinding, isEditableKeybindingTarget } from './keybindingParser'
import { commandScopeMatches, getKeyScopeSearchOrder } from './keyScopeStore'

const sortCommandsForRuntime = (commands = []) => {
  return [...commands].sort((left, right) => {
    // 同一快捷键下先看显式优先级，再按注册顺序稳定排序，避免运行时结果漂移。
    const priorityDiff = Number(right.priority || 0) - Number(left.priority || 0)
    if (priorityDiff !== 0) return priorityDiff
    return Number(left._registerIndex || 0) - Number(right._registerIndex || 0)
  })
}

export const startKeybindingRuntime = ({ commandStore } = {}) => {
  if (!commandStore) return () => {}

  const dispatchKeybinding = async (event, keybinding) => {
    if (!keybinding) return

    const config = commandStore.getKeybindingConfig()
    const commands = getAllCommands()
    const effectiveMap = buildEffectiveKeybindingMap(commands, config)
    const scopedSearchOrder = getKeyScopeSearchOrder(event.target)
    const editableTarget = isEditableKeybindingTarget(event.target)

    // 从最具体的区域向全局查找，命中第一个可执行命令后立即停止。
    for (const scope of scopedSearchOrder) {
      const matchingCommands = sortCommandsForRuntime(commands.filter(command => {
        if (command.displayOnly) return false
        const keys = effectiveMap.get(command.id) || []
        if (!keys.includes(keybinding)) return false
        if (!commandScopeMatches(command.scope, scope)) return false
        if (editableTarget && !command.allowInInput) return false
        return true
      }))

      const enabledCommand = matchingCommands.find(command => canRunCommand(command, commandStore.commandContext))
      if (enabledCommand) {
        event.preventDefault()
        event.stopPropagation()
        await commandStore.executeCommand(enabledCommand.id, { keybinding, scope })
        return
      }

      if (matchingCommands.some(command => command.captureWhenDisabled)) {
        // 例如 Ctrl+R 扫描中不可用时仍要阻止浏览器刷新，避免用户误丢当前状态。
        event.preventDefault()
        event.stopPropagation()
        return
      }
    }
  }

  const handleKeydown = async (event) => {
    await dispatchKeybinding(event, eventToKeybinding(event))
  }

  const handleMousedown = async (event) => {
    await dispatchKeybinding(event, eventToMouseKeybinding(event))
  }

  window.addEventListener('keydown', handleKeydown, { capture: true })
  window.addEventListener('mousedown', handleMousedown, { capture: true })
  return () => {
    // 根组件卸载时释放监听，避免热更新或窗口重建后重复触发。
    window.removeEventListener('keydown', handleKeydown, { capture: true })
    window.removeEventListener('mousedown', handleMousedown, { capture: true })
  }
}
