/**
 * 将字节数格式化为更适合展示的存储单位。
 * @param {number|string} bytes 字节数
 * @param {number} decimals 保留小数位数，默认为 2
 * @returns {string} 格式化后的字符串 (如: 1.25 MB)
 */
export function formatFileSize(bytes, decimals = 2) {
  const numericBytes = Number(bytes)
  if (numericBytes === 0) return '0 B'
  if (!Number.isFinite(numericBytes) || numericBytes < 0) return '-'

  const base = 1024 // 计算机通常使用 1024 进制
  const precision = decimals < 0 ? 0 : decimals
  const units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB', 'EB', 'ZB', 'YB']
    // 计算单位索引
  const unitIndex = Math.min(
    Math.floor(Math.log(numericBytes) / Math.log(base)),
    units.length - 1,
  )

    // 格式化输出：字节数 / 1024的i次方，并保留小数
  return `${parseFloat((numericBytes / (base ** unitIndex)).toFixed(precision))} ${units[unitIndex]}`
}

/**
 * 统一格式化项目内常见的日期时间展示。
 */
export function formatDate(dateString) {
  if (!dateString) return ''

  return new Date(dateString).toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}
