import builtinThemes from './builtinThemes.json'
import { hexToRgbComponents, normalizeHexColor } from '../../shared/lib/color'

export const DEFAULT_THEME_ID = 'obsidian-cyan'
export const BUILTIN_THEMES = builtinThemes.map(theme => ({ ...theme, builtin: true }))

export const THEME_TOKEN_GROUPS = [
  { key: 'bg', label: '背景色', tokens: [
    { key: 'deep', label: '主背景色', usage: '影响主界面和大面积背景。' },
    { key: 'surface', label: '面板背景色', usage: '影响弹窗、列表面板和卡片底色。' },
    { key: 'elevated', label: '浮起背景色', usage: '影响浮窗、突出卡片和强调面板。' },
    { key: 'highlight', label: '层级背景色', usage: '影响选中、重点区域和较强层次。' },
    { key: 'muted', label: '弱背景色', usage: '影响悬停、标签和轻量分区。' },
    { key: 'inset', label: '内嵌背景色', usage: '影响输入框、代码区和日志区。' },
    { key: 'overlay', label: '叠加背景色', usage: '影响悬停、选中、按下和轻量控件反馈，可通过透明度控制强弱。' },
    { key: 'contrast', label: '反差背景色', usage: '影响高反差按钮、开关滑块和需要突出显示的小控件。' },
    { key: 'neutral', label: '中性填充色', usage: '影响非强调色的小圆点、开关滑块和状态标记。' },
  ] },
  { key: 'text', label: '字体色', tokens: [
    { key: 'main', label: '主要文字色', usage: '影响标题、正文和常用图标。' },
    { key: 'soft', label: '柔和正文色', usage: '影响弱化正文、非焦点标题和仍需清晰阅读的信息。' },
    { key: 'dim', label: '次要文字色', usage: '影响说明、提示和弱化信息。' },
    { key: 'subtle', label: '弱提示文字色', usage: '影响占位、禁用和最弱提示。' },
    { key: 'disabled', label: '不可用文字色', usage: '影响禁用、空状态和最低优先级提示。' },
    { key: 'inverse', label: '反差文字色', usage: '影响深浅反差按钮和特殊徽标。' },
  ] },
  { key: 'accent', label: '主题色', tokens: [
    { key: 'primary', label: '主操作色', usage: '影响保存、确认和当前选中。' },
    { key: 'danger', label: '危险色', usage: '影响删除、错误和危险确认。' },
    { key: 'highlight', label: '高亮色', usage: '影响搜索命中和重点标记。' },
    { key: 'special', label: '特殊功能色', usage: '影响 AI、高级功能和特殊入口。' },
    { key: 'cool', label: '信息色', usage: '影响链接和补充信息。' },
    { key: 'success', label: '成功色', usage: '影响完成、可用和成功状态。' },
    { key: 'tip', label: '提示色', usage: '影响推荐、提示和轻量成功。' },
    { key: 'warn', label: '注意色', usage: '影响引导、提醒和轻警告。' },
    { key: 'secondary', label: '辅助强调色', usage: '影响分组和次要操作。' },
    { key: 'warning', label: '警告色', usage: '影响待处理和中等警告。' },
  ] },
  { key: 'glass', label: '玻璃背景', tokens: [
    { key: 'light', label: '轻透明背景', usage: '影响轻量覆盖和细微层次。' },
    { key: 'medium', label: '常规透明背景', usage: '影响常用玻璃面板。' },
    { key: 'heavy', label: '重透明背景', usage: '影响遮罩弹窗和强覆盖区域。' },
  ] },
  { key: 'border', label: '边框色', tokens: [
    { key: 'base', label: '边框基础色', usage: '影响分隔线、输入框和卡片边界，可通过透明度控制强弱。' },
  ] },
  { key: 'overlay', label: '覆盖层', tokens: [
    { key: 'scrim', label: '遮罩背景', usage: '影响弹窗后方遮罩和压暗区域。' },
  ] },
]

const RGB_COLOR_PATTERN = /^rgba?\(([^)]+)\)$/i

const deepClone = (value) => JSON.parse(JSON.stringify(value))

const parseRgbComponents = (value = '') => {
  const match = String(value || '').trim().match(RGB_COLOR_PATTERN)
  if (!match) return ''
  const parts = match[1].split(',').slice(0, 3).map(item => Math.max(0, Math.min(255, Number.parseInt(item.trim(), 10) || 0)))
  return parts.length === 3 ? parts.join(', ') : ''
}

export const colorToRgbComponents = (value = '') => {
  const color = String(value || '').trim()
  if (!color) return '0, 0, 0'
  if (color.startsWith('#')) return hexToRgbComponents(normalizeHexColor(color))
  return parseRgbComponents(color) || '0, 0, 0'
}

const toTailwindColorValue = (value = '') => {
  const color = String(value || '').trim()
  if (color.startsWith('#')) return `rgb(${colorToRgbComponents(color)})`
  return color
}

const getRelativeLuminance = (value = '') => {
  const [r, g, b] = colorToRgbComponents(value).split(',').map(item => Number(item.trim()) / 255)
  const convert = (channel) => channel <= 0.03928 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4
  return 0.2126 * convert(r || 0) + 0.7152 * convert(g || 0) + 0.0722 * convert(b || 0)
}

const pickReadableTextColor = (value = '') => getRelativeLuminance(value) > 0.55 ? '#000000' : 'var(--color-text-main)'

const setCssVar = (root, name, value) => {
  root.style.setProperty(name, value)
}

export const getDefaultTheme = () => BUILTIN_THEMES.find(theme => theme.id === DEFAULT_THEME_ID) || BUILTIN_THEMES[0]

const mergeTokensWithDefault = (tokens = {}) => {
  const defaults = deepClone(getDefaultTheme().tokens)
  THEME_TOKEN_GROUPS.forEach(group => {
    defaults[group.key] = {
      ...(defaults[group.key] || {}),
      ...((tokens && typeof tokens[group.key] === 'object') ? tokens[group.key] : {}),
    }
  })
  return defaults
}

export const normalizeTheme = (theme = {}) => ({
  id: String(theme.id || '').trim(),
  name: String(theme.name || '').trim() || '未命名主题',
  builtin: !!theme.builtin,
  tokens: mergeTokensWithDefault(theme.tokens),
})

export const createEditableThemeFrom = (baseTheme = getDefaultTheme()) => {
  const normalized = normalizeTheme(baseTheme)
  return {
    id: '',
    name: `${normalized.name} 副本`,
    builtin: false,
    tokens: deepClone(normalized.tokens),
  }
}

export const mergeThemes = (userThemes = []) => {
  const userList = Array.isArray(userThemes) ? userThemes : []
  return [
    ...BUILTIN_THEMES.map(normalizeTheme),
    ...userList.map(theme => normalizeTheme({ ...theme, builtin: false })),
  ]
}

export const findThemeById = (themes = [], themeId = '') => {
  const id = String(themeId || '').trim()
  return themes.find(theme => theme.id === id) || themes.find(theme => theme.id === DEFAULT_THEME_ID) || themes[0] || getDefaultTheme()
}

export const applyTheme = (theme) => {
  if (typeof document === 'undefined') return
  const normalized = normalizeTheme(theme || getDefaultTheme())
  const root = document.documentElement
  const { bg, glass, accent, text, border, overlay } = normalized.tokens
  const isLightTheme = getRelativeLuminance(bg?.deep) > 0.55

  Object.entries(bg || {}).forEach(([key, value]) => {
    setCssVar(root, `--color-bg-${key}`, toTailwindColorValue(value))
    setCssVar(root, `--rgb-bg-${key}`, colorToRgbComponents(value))
  })
  Object.entries(glass || {}).forEach(([key, value]) => setCssVar(root, `--color-glass-${key}`, value))
  Object.entries(accent || {}).forEach(([key, value]) => {
    const rgb = colorToRgbComponents(value)
    setCssVar(root, `--color-accent-${key}`, `rgb(${rgb})`)
    setCssVar(root, `--rgb-accent-${key}`, rgb)
    setCssVar(root, `--color-on-accent-${key}`, pickReadableTextColor(value))
  })
  Object.entries(text || {}).forEach(([key, value]) => {
    setCssVar(root, `--color-text-${key}`, toTailwindColorValue(value))
    setCssVar(root, `--rgb-text-${key}`, colorToRgbComponents(value))
  })
  Object.entries(border || {}).forEach(([key, value]) => {
    setCssVar(root, `--color-border-${key}`, toTailwindColorValue(value))
    setCssVar(root, `--rgb-border-${key}`, colorToRgbComponents(value))
  })
  Object.entries(overlay || {}).forEach(([key, value]) => setCssVar(root, `--color-overlay-${key}`, value))

  const bgOverlayRgb = colorToRgbComponents(bg?.overlay || text?.main)
  setCssVar(root, '--color-bg-hover', `rgba(${bgOverlayRgb}, 0.05)`)
  setCssVar(root, '--color-bg-active', `rgba(${bgOverlayRgb}, 0.10)`)
  setCssVar(root, '--color-bg-selected', `rgba(${bgOverlayRgb}, 0.10)`)

  const borderBaseRgb = colorToRgbComponents(border?.base || text?.main)
  setCssVar(root, '--color-border-muted', `rgba(${borderBaseRgb}, 0.05)`)
  setCssVar(root, '--color-border-default', `rgba(${borderBaseRgb}, 0.10)`)
  setCssVar(root, '--color-border-subtle', `rgba(${borderBaseRgb}, 0.10)`)
  setCssVar(root, '--color-border-strong', `rgba(${borderBaseRgb}, 0.18)`)

  // 兼容已有少量手写 rgba(var(--xxx), alpha) 和 shadcn 风格变量。
  setCssVar(root, '--color-accent-rgb', colorToRgbComponents(accent?.primary))
  setCssVar(root, '--accent-rgb', colorToRgbComponents(accent?.primary))
  setCssVar(root, '--highlight-color', colorToRgbComponents(accent?.warn))
  setCssVar(root, '--shadow-color', isLightTheme ? 'rgba(15, 23, 42, 0.18)' : 'oklch(0 0 0 / 55%)')
  setCssVar(root, '--background', toTailwindColorValue(bg?.deep))
  setCssVar(root, '--foreground', toTailwindColorValue(text?.main))
  setCssVar(root, '--card', toTailwindColorValue(bg?.surface))
  setCssVar(root, '--card-foreground', toTailwindColorValue(text?.main))
  setCssVar(root, '--popover', toTailwindColorValue(bg?.surface))
  setCssVar(root, '--popover-foreground', toTailwindColorValue(text?.main))
  setCssVar(root, '--primary', toTailwindColorValue(accent?.primary))
  setCssVar(root, '--primary-foreground', pickReadableTextColor(accent?.primary))
  setCssVar(root, '--secondary', toTailwindColorValue(bg?.muted || bg?.highlight))
  setCssVar(root, '--secondary-foreground', toTailwindColorValue(text?.main))
  setCssVar(root, '--muted', toTailwindColorValue(bg?.muted || bg?.highlight))
  setCssVar(root, '--muted-foreground', toTailwindColorValue(text?.dim))
  setCssVar(root, '--accent', toTailwindColorValue(bg?.highlight))
  setCssVar(root, '--accent-foreground', toTailwindColorValue(text?.main))
  setCssVar(root, '--destructive', toTailwindColorValue(accent?.danger))
  setCssVar(root, '--border', `rgba(${borderBaseRgb}, 0.10)`)
  setCssVar(root, '--input', `rgba(${borderBaseRgb}, 0.18)`)
  setCssVar(root, '--ring', toTailwindColorValue(accent?.primary))

  root.dataset.theme = normalized.id
  root.classList.toggle('dark', !isLightTheme)
  root.style.colorScheme = isLightTheme ? 'light' : 'dark'
}
