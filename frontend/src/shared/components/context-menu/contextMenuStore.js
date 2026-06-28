// stores/contextMenuStore.js
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getCommand } from '../../commands/commandRegistry'
import { useCommandStore } from '../../commands/commandStore'
import { formatKeybindingLabel } from '../../commands/keybindingParser'

export const getVisibleMenuItems = (items = []) => (items || []).filter(item => item && !item.hidden)

const getCommandShortcutLabel = (commandStore, commandId = '') => {
  return commandStore.getCommandKeybindings(commandId)
    .map(keybinding => formatKeybindingLabel(keybinding))
    .filter(Boolean)
    .join(' / ')
}

const normalizeMenuItem = (item, commandStore) => {
  if (!item) return item

  // 菜单项可以只声明 commandId，标题、禁用状态、快捷键文案和执行动作都从命令注册表补齐。
  const children = Array.isArray(item.children)
    ? item.children.map(child => normalizeMenuItem(child, commandStore))
    : item.children
  const commandId = String(item.commandId || '').trim()
  if (!commandId) return { ...item, children }

  const command = getCommand(commandId)
  if (!command) return { ...item, children, disabled: true, tooltip: item.tooltip || `命令不存在：${commandId}` }

  const args = item.args || {}
  const commandDisabled = !commandStore.isCommandEnabled(commandId, args)
  const commandShortcut = getCommandShortcutLabel(commandStore, commandId)
  // gesture 用于展示固定鼠标手势；真实键盘快捷键仍来自用户当前配置。
  const shortcut = item.shortcut ?? [item.gesture, commandShortcut].filter(Boolean).join(' / ')

  return {
    ...item,
    children,
    label: item.labelOverride || item.label || command.title,
    shortcut,
    disabled: !!(item.disabled || commandDisabled),
    level: item.level || (command.dangerLevel === 'warning' ? 'danger' : undefined),
    tooltip: item.tooltip || command.description || item.labelOverride || item.label || command.title,
    action: item.action || (() => commandStore.executeCommand(commandId, args)),
  }
}

const normalizeMenuItems = (items = [], commandStore) => {
  return (items || []).map(item => normalizeMenuItem(item, commandStore))
}

export const useContextMenuStore = defineStore('contextMenu', () => {
  const commandStore = useCommandStore()
  const show = ref(false)
  const x = ref(0)
  const y = ref(0)
  const items = ref([])

  // 保存触发菜单时的自定义数据（例如右键点击的那个列表项ID）
  const payload = ref(null)
  const menuId = ref(0) // 用于强制刷新

  const open = (event, menuItems, data = null) => {
    // 阻止默认浏览器右键
    event.preventDefault()
    event.stopPropagation() // 阻止冒泡

    x.value = event.clientX
    y.value = event.clientY
    items.value = normalizeMenuItems(menuItems, commandStore)
    payload.value = data
    menuId.value = Date.now() // 每次打开更新 ID
    show.value = true
  }

  const close = () => {
    show.value = false
  }

  return {
    // 状态
    show, menuId, x, y, items, payload,
    // 操作
    open, close,
  }
})
