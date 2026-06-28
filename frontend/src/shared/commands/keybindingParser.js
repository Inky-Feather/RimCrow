const MODIFIER_ORDER = ['Ctrl', 'Meta', 'Alt', 'Shift']

// 统一把用户输入、浏览器事件和展示文案收口到同一种键名，避免配置文件出现多套写法。
const KEY_ALIASES = {
  ' ': 'Space',
  spacebar: 'Space',
  esc: 'Escape',
  escape: 'Escape',
  del: 'Delete',
  delete: 'Delete',
  comma: ',',
  plus: '+',
  mouseleft: 'MouseLeft',
  mouseright: 'MouseRight',
  mousemiddle: 'MouseMiddle',
  mouseback: 'MouseBack',
  mouseforward: 'MouseForward',
}

const MODIFIER_ALIASES = {
  control: 'Ctrl',
  ctrl: 'Ctrl',
  cmd: 'Meta',
  command: 'Meta',
  meta: 'Meta',
  win: 'Meta',
  option: 'Alt',
  alt: 'Alt',
  shift: 'Shift',
}

const DISPLAY_MODIFIERS = {
  Ctrl: 'Ctrl',
  Meta: 'Meta',
  Alt: 'Alt',
  Shift: 'Shift',
  MouseLeft: '左键',
  MouseMiddle: '中键',
  MouseRight: '右键',
  MouseBack: '后退键',
  MouseForward: '前进键',
}

const normalizeMainKey = (value = '') => {
  const raw = String(value || '').trim()
  if (!raw) return ''
  const lowered = raw.toLowerCase()
  if (KEY_ALIASES[lowered]) return KEY_ALIASES[lowered]
  if (/^f\d{1,2}$/i.test(raw)) return raw.toUpperCase()
  if (raw.length === 1) return raw.toUpperCase()
  return raw.charAt(0).toUpperCase() + raw.slice(1)
}

export const normalizeKeybinding = (value = '') => {
  const parts = String(value || '')
    .split('+')
    .map(part => part.trim())
    .filter(Boolean)
  if (!parts.length) return ''

  const modifiers = new Set()
  let mainKey = ''

  // 允许只保存 Ctrl / Alt / Shift 这类纯修饰键组合，方便设置页显示固定手势或后续扩展。
  for (const part of parts) {
    const normalizedModifier = MODIFIER_ALIASES[part.toLowerCase()]
    if (normalizedModifier) {
      modifiers.add(normalizedModifier)
      continue
    }
    mainKey = normalizeMainKey(part)
  }

  if (!mainKey) return MODIFIER_ORDER.filter(modifier => modifiers.has(modifier)).join('+')
  if (MODIFIER_ORDER.includes(mainKey)) modifiers.add(mainKey)
  const orderedModifiers = MODIFIER_ORDER.filter(modifier => modifiers.has(modifier))
  if (MODIFIER_ORDER.includes(mainKey)) return orderedModifiers.join('+')
  return [...orderedModifiers, mainKey].join('+')
}

export const normalizeKeybindingList = (values = []) => {
  const list = Array.isArray(values) ? values : []
  const normalized = []
  const seen = new Set()
  for (const value of list) {
    const keybinding = normalizeKeybinding(value)
    if (!keybinding || seen.has(keybinding)) continue
    seen.add(keybinding)
    normalized.push(keybinding)
  }
  return normalized
}

export const eventToKeybinding = (event) => {
  if (!event) return ''
  const rawKey = String(event.key || '')
  const mainKey = MODIFIER_ALIASES[rawKey.toLowerCase()] || normalizeMainKey(rawKey)
  if (!mainKey) return ''

  const modifiers = new Set()
  if (event.ctrlKey) modifiers.add('Ctrl')
  if (event.metaKey) modifiers.add('Meta')
  if (event.altKey) modifiers.add('Alt')
  if (event.shiftKey) modifiers.add('Shift')
  if (MODIFIER_ORDER.includes(mainKey)) modifiers.add(mainKey)

  // 按下 Ctrl 本身时不把 Ctrl 重复追加为主键，统一归一化成 Ctrl。
  return normalizeKeybinding([...modifiers, ...(MODIFIER_ORDER.includes(mainKey) ? [] : [mainKey])].join('+'))
}

const mouseButtonToKey = (button) => {
  const buttonMap = {
    0: 'MouseLeft',
    1: 'MouseMiddle',
    2: 'MouseRight',
    3: 'MouseBack',
    4: 'MouseForward',
  }
  return buttonMap[button] || ''
}

export const eventToMouseKeybinding = (event) => {
  if (!event) return ''
  const mainKey = mouseButtonToKey(event.button)
  if (!mainKey) return ''
  const modifiers = []
  if (event.ctrlKey) modifiers.push('Ctrl')
  if (event.metaKey) modifiers.push('Meta')
  if (event.altKey) modifiers.push('Alt')
  if (event.shiftKey) modifiers.push('Shift')
  return normalizeKeybinding([...modifiers, mainKey].join('+'))
}

export const formatKeybindingLabel = (value = '') => {
  const normalized = normalizeKeybinding(value)
  if (!normalized) return ''
  return normalized
    .split('+')
    .map(part => DISPLAY_MODIFIERS[part] || part)
    .join('+')
}

export const isEditableKeybindingTarget = (target) => {
  if (typeof HTMLElement === 'undefined' || !(target instanceof HTMLElement)) return false
  if (target.isContentEditable) return true
  // 输入控件默认不触发全局快捷键，除非命令显式声明 allowInInput。
  return !!target.closest('input, textarea, select, [contenteditable="true"], [role="textbox"]')
}
