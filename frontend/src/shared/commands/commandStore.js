import { defineStore } from 'pinia'
import { shallowRef } from 'vue'
import { canRunCommand, getAllCommands, getCommand, runCommand } from './commandRegistry'
import { buildEffectiveKeybindingMap, normalizeKeybindingConfig } from './keybindingConflicts'

export const useCommandStore = defineStore('commands', () => {
  const commandContext = shallowRef({})
  const keybindingConfigProvider = shallowRef(() => ({}))

  const setCommandContext = (context = {}) => {
    // 上下文由根组件注入，命令模块不直接依赖具体业务 store，后续插件命令也走同一个入口。
    commandContext.value = context
  }

  const setKeybindingConfigProvider = (provider) => {
    // 配置读取保持为函数，避免设置加载/保存时复制一份过期的快捷键配置。
    keybindingConfigProvider.value = typeof provider === 'function' ? provider : () => ({})
  }

  const getKeybindingConfig = () => normalizeKeybindingConfig(keybindingConfigProvider.value?.() || {})

  const getEffectiveKeybindingMap = () => buildEffectiveKeybindingMap(getAllCommands(), getKeybindingConfig())

  const getCommandKeybindings = (commandId = '') => {
    return getEffectiveKeybindingMap().get(commandId) || []
  }

  const isCommandEnabled = (commandId = '', args = {}) => canRunCommand(getCommand(commandId), commandContext.value, args)

  const executeCommand = (commandId, args = {}) => runCommand(commandId, commandContext.value, args)

  return {
    // 上下文
    commandContext, setCommandContext, setKeybindingConfigProvider,
    // 快捷键配置
    getKeybindingConfig, getEffectiveKeybindingMap, getCommandKeybindings,
    // 命令执行
    isCommandEnabled, executeCommand,
  }
})
