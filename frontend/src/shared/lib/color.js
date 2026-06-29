const FALLBACK_RGB = 'rgb(0, 0, 0)'
const FALLBACK_RGB_COMPONENTS = '0, 0, 0'
const FALLBACK_HEX = '#000000'
export const DEFAULT_ACCENT_HEX = '#a1a1aa'

const clampByte = (value) => Math.max(0, Math.min(255, Number(value) || 0))

// 统一处理透明度，保证 0 也能被正确保留。
const normalizeAlpha = (alpha = 1) => {
  const numericAlpha = Number(alpha)
  if (!Number.isFinite(numericAlpha)) return 1
  return Math.max(0, Math.min(1, numericAlpha))
}

const parseHexChannels = (hex) => {
  if (!hex || typeof hex !== 'string') return null

  let cleanHex = hex.replace('#', '')
  // 兼容 3 位短十六进制，例如 `#fff`。
  if (cleanHex.length === 3) {
    cleanHex = cleanHex.split('').map(char => char + char).join('')
  }
  if (cleanHex.length !== 6 || !/^[0-9a-fA-F]+$/.test(cleanHex)) {
    return null
  }

  return [
    parseInt(cleanHex.slice(0, 2), 16),
    parseInt(cleanHex.slice(2, 4), 16),
    parseInt(cleanHex.slice(4, 6), 16),
  ]
}

/**
 * 统一规范化十六进制颜色：
 * 1. 接受 `#rgb` 和 `#rrggbb`
 * 2. 输出统一的小写 `#rrggbb`
 * 3. 非法输入回退到调用方指定的默认值
 */
export const normalizeHexColor = (hex, fallback = FALLBACK_HEX) => {
  const normalizedHex = typeof hex === 'string' ? hex.trim().toLowerCase() : ''
  if (!normalizedHex) return fallback

  const channels = parseHexChannels(normalizedHex)
  if (!channels) return fallback

  return `#${channels.map(channel => clampByte(channel).toString(16).padStart(2, '0')).join('')}`
}

const parseRgbChannels = (rgb) => {
  if (!rgb || typeof rgb !== 'string' || !rgb.startsWith('rgb(') || !rgb.endsWith(')')) {
    return null
  }

  // 兼容带空格和不带空格的 `rgb(r,g,b)` 格式。
  const channels = rgb
    .replace(/rgb\(|\)/g, '')
    .split(',')
    .map(item => clampByte(item.trim()))

  return channels.length === 3 ? channels : null
}

/**
 * 获取Tailwind根节点的CSS变量颜色值
 * @param {string} name - 颜色名/完整CSS变量名(如 primary / --color-primary)
 * @returns {string} 纯净的颜色值（#xxx / rgb() / rgba()）
 */
export const getTailwindColor = (name) => {
  // 严格入参校验，避免 `startsWith` 在非法值上报错。
  if (!name || typeof name !== 'string') return ''
  // 拼接规范的CSS变量名
  const variableName = name.startsWith('--') ? name : `--color-${name}`
  return getComputedStyle(document.documentElement).getPropertyValue(variableName).trim()
}

/**
 * 将十六进制颜色转换为 `r, g, b` 组件字符串，便于拼接 CSS 变量。
 */
export const hexToRgbComponents = (hex) => {
  const normalizedHex = typeof hex === 'string' ? hex.trim() : ''
  // 对空颜色值静默兜底，避免合法的“未设置颜色”场景刷控制台错误。
  if (!normalizedHex) return FALLBACK_RGB_COMPONENTS

  const channels = parseHexChannels(normalizedHex)
  if (!channels) {
    console.error(`颜色转换失败：非法十六进制颜色值。函数=hexToRgbComponents，输入=${hex}`)
    return FALLBACK_RGB_COMPONENTS
  }
  return channels.join(', ')
}

/**
 * 十六进制颜色转 `rgb(r, g, b)`。
 */
export const hexToRgb = (hex) => `rgb(${hexToRgbComponents(hex)})`

/**
 * 十六进制颜色转 `rgba(r, g, b, a)`。
 */
export const hexToRgba = (hex, alpha = 1) => (
  `rgba(${hexToRgbComponents(hex)}, ${normalizeAlpha(alpha)})`
)

/**
 * `rgb(r, g, b)` 转十六进制颜色。
 */
export const rgbToHex = (rgb) => {
  const channels = parseRgbChannels(rgb)
  if (!channels) {
    console.error(`颜色转换失败：非法 RGB 颜色值。函数=rgbToHex，输入=${rgb}`)
    return FALLBACK_HEX
  }

  return `#${channels.map(channel => clampByte(channel).toString(16).padStart(2, '0')).join('')}`.toLowerCase()
}

/**
 * 获取RGB格式的Tailwind颜色
 * @param {string} name - 颜色名/完整CSS变量名
 * @returns {string} rgb(r,g,b) 格式颜色值
 */
export const getTailwindColorRgb = (name) => {
  const color = getTailwindColor(name)

  if (color.startsWith('rgb(')) {
    const channels = parseRgbChannels(color)
    return channels ? `rgb(${channels.join(', ')})` : FALLBACK_RGB
  }
  if (color.startsWith('#')) return hexToRgb(color)

  console.error(`读取主题颜色失败：颜色变量【${name}】取值无效，函数=getTailwindColorRgb，值=${color}`)
  return FALLBACK_RGB
}

/**
 * 获取RGBA格式的Tailwind颜色（带透明度）
 * @param {string} name - 颜色名/完整CSS变量名
 * @param {number} alpha - 透明度 0~1
 * @returns {string} rgba(r,g,b,alpha) 格式颜色值
 */
export const getTailwindColorRgba = (name, alpha = 1) => {
  const channels = parseRgbChannels(getTailwindColorRgb(name))
  return `rgba(${(channels || [0, 0, 0]).join(', ')}, ${normalizeAlpha(alpha)})`
}

/**
 * 获取十六进制格式的Tailwind颜色
 * @param {string} name - 颜色名/完整CSS变量名
 * @returns {string} #xxxxxx 格式颜色值
 */
export const getTailwindColorHex = (name) => {
  const color = getTailwindColor(name)

  if (color.startsWith('rgb(')) return rgbToHex(color)
  if (color.startsWith('#')) return color

  console.error(`读取主题颜色失败：颜色变量【${name}】取值无效，函数=getTailwindColorHex，值=${color}`)
  return FALLBACK_HEX
}
