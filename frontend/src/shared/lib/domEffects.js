import { Copy, Download, Link } from 'lucide-vue-next'
import { useContextMenuStore } from '../components/context-menu/contextMenuStore'
import { checkResult, toast, toUserMessage } from './common'

/**
 * 给元素添加一次性的强调动画，用于提示用户关注某个控件。
 * @param {String|HTMLElement} target - 选择器或DOM元素
 * @param {Object} options - 配置项
 * @param {string} [options.mode='shake'] - 动画模式: 'shake'(震动), 'wobble'(摇摆), 'flash'(闪烁), 'pulse'(呼吸)
 * @param {string} [options.color] - RGB颜色值 (如 '255, 0, 0')，不传则使用CSS默认
 * @param {number} [options.duration=1000] - 动画持续时间(ms)，设为 0 则不自动移除
 * @param {boolean} [options.scroll=true] - 是否自动滚动
 */
export function highlightComponent(target, options = {}) {
  const {
    mode = 'shake',
    duration = 1000,
    color = null,
    scroll = false,
  } = options

  const element = typeof target === 'string' ? document.querySelector(target) : target
  if (!element) return

  // 1. 清理旧状态 (防止多次触发叠加)
  if (element._flashTimer) {
    clearTimeout(element._flashTimer)
    // 移除所有可能的类名
    element.classList.remove(
      'highlight-base',
      'highlight-effect-shake',
      'highlight-effect-wobble',
      'highlight-effect-flash',
      'highlight-effect-pulse',
    )
    void element.offsetWidth // 强制重绘
  }

  // 2. 设置颜色变量
  if (color) {
    element.style.setProperty('--highlight-color', color)
  } else {
    element.style.removeProperty('--highlight-color')
  }

  // 3. 滚动定位
  if (scroll) {
    element.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }

  // 4. 添加动画类
  element.classList.add('highlight-base', `highlight-effect-${mode}`)

  // 5. 定时移除
  if (duration > 0) {
    element._flashTimer = setTimeout(() => {
      element.classList.remove('highlight-base', `highlight-effect-${mode}`)
      element.style.removeProperty('--highlight-color')
      delete element._flashTimer
    }, duration)
  }
}

// 常用动画模式保留独立入口，组件调用时更直观。
export function shakeComponent(target, options = {}) {
  highlightComponent(target, { ...options, mode: 'shake' })
}

export function wobbleComponent(target, options = {}) {
  highlightComponent(target, { ...options, mode: 'wobble' })
}

export function flashComponent(target, options = {}) {
  highlightComponent(target, { ...options, mode: 'flash' })
}

export function pulseComponent(target, options = {}) {
  highlightComponent(target, { ...options, mode: 'pulse' })
}

const shouldPreviewImage = (image) => {
  if (!image || typeof image.closest !== 'function') return false
  return !image.closest('a')
}

const blurActiveViewerFocus = () => {
  const activeElement = typeof document === 'undefined' ? null : document.activeElement
  if (activeElement?.closest?.('.viewer-container')) {
    activeElement.blur()
  }
}

const IMAGE_SAVE_TYPES = new Map([
  ['image/png', '.png'],
  ['image/jpeg', '.jpg'],
  ['image/webp', '.webp'],
  ['image/gif', '.gif'],
  ['image/bmp', '.bmp'],
])
const IMAGE_VIEWER_STYLE_ID = 'image-viewer-style'

const ensureImageViewerStyle = () => {
  if (typeof document === 'undefined' || document.getElementById(IMAGE_VIEWER_STYLE_ID)) return
  const style = document.createElement('style')
  style.id = IMAGE_VIEWER_STYLE_ID
  style.textContent = `
    .image-viewer .viewer-toolbar > ul {
      padding: 12px 6px 18px;
    }
    .image-viewer .viewer-toolbar > ul > li {
      width: 48px;
      height: 48px;
      margin-left: 6px;
    }
    .image-viewer .viewer-toolbar > ul > li:first-child {
      margin-left: 0;
    }
    .image-viewer .viewer-toolbar > ul > li::before {
      margin: 14px;
      transform: scale(2);
      transform-origin: center;
    }
    .image-viewer .viewer-toolbar > ul > .viewer-small {
      width: 36px;
      height: 36px;
      margin-top: 6px;
      margin-bottom: 6px;
    }
    .image-viewer .viewer-toolbar > ul > .viewer-small::before {
      margin: 8px;
    }
    .image-viewer .viewer-toolbar > ul > .viewer-large {
      width: 60px;
      height: 60px;
      margin-top: -6px;
      margin-bottom: -6px;
    }
    .image-viewer .viewer-toolbar > ul > .viewer-large::before {
      margin: 20px;
    }
  `
  document.head.appendChild(style)
}

const stripQueryAndHash = (value = '') => String(value || '').split(/[?#]/)[0]

const imageFilenameFromUrl = (url = '', fallback = 'image.png') => {
  try {
    const parsed = new URL(String(url || ''), window.location.href)
    if (parsed.pathname === '/local' || parsed.pathname === '/thumb') {
      const localPath = parsed.searchParams.get('path') || ''
      const basename = stripQueryAndHash(decodeURIComponent(localPath)).split(/[\\/]/).pop()
      if (basename) return basename
    }
    if (parsed.pathname === '/remote') {
      const remoteUrl = parsed.searchParams.get('url') || ''
      if (remoteUrl) return imageFilenameFromUrl(remoteUrl, fallback)
    }
    const basename = stripQueryAndHash(decodeURIComponent(parsed.pathname)).split('/').pop()
    if (basename) return basename
  } catch {
    const basename = stripQueryAndHash(url).split(/[\\/]/).pop()
    if (basename) return basename
  }
  return fallback
}

const ensureImageFilenameExtension = (filename = '', mimeType = '') => {
  const fallbackExt = IMAGE_SAVE_TYPES.get(String(mimeType || '').toLowerCase()) || '.png'
  const normalized = String(filename || '').trim() || `image${fallbackExt}`
  return /\.[a-z0-9]{2,5}$/i.test(normalized) ? normalized : `${normalized}${fallbackExt}`
}

const getViewerImagePayload = (viewerImage, originalImage) => {
  const originalSrc = originalImage?.currentSrc || originalImage?.src || ''
  const displayedSrc = viewerImage?.currentSrc || viewerImage?.src || originalSrc
  const label = originalImage?.alt || originalImage?.title || ''
  return {
    src: displayedSrc,
    originalSrc,
    filename: ensureImageFilenameExtension(label || imageFilenameFromUrl(originalSrc || displayedSrc)),
  }
}

const fetchViewerImageBlob = async (imagePayload) => {
  if (!imagePayload?.src) throw new Error('未找到可复制的图片地址')
  const response = await fetch(imagePayload.src, { cache: 'no-store' })
  if (!response.ok) throw new Error(`读取图片失败：${response.status}`)
  const blob = await response.blob()
  if (!blob?.size) throw new Error('图片内容为空')
  return blob
}

const blobToBase64 = (blob) => new Promise((resolve, reject) => {
  const reader = new FileReader()
  reader.onload = () => resolve(String(reader.result || '').split(',')[1] || '')
  reader.onerror = () => reject(reader.error || new Error('读取图片内容失败'))
  reader.readAsDataURL(blob)
})

const convertImageBlobToPng = (blob) => new Promise((resolve, reject) => {
  const image = new Image()
  const objectUrl = URL.createObjectURL(blob)
  image.onload = () => {
    try {
      const canvas = document.createElement('canvas')
      canvas.width = image.naturalWidth || image.width
      canvas.height = image.naturalHeight || image.height
      const ctx = canvas.getContext('2d')
      ctx.drawImage(image, 0, 0)
      canvas.toBlob((pngBlob) => {
        URL.revokeObjectURL(objectUrl)
        if (pngBlob) resolve(pngBlob)
        else reject(new Error('转换图片格式失败'))
      }, 'image/png')
    } catch (error) {
      URL.revokeObjectURL(objectUrl)
      reject(error)
    }
  }
  image.onerror = () => {
    URL.revokeObjectURL(objectUrl)
    reject(new Error('图片解码失败'))
  }
  image.src = objectUrl
})

const copyViewerImage = async (imagePayload) => {
  try {
    if (!navigator?.clipboard?.write || typeof ClipboardItem === 'undefined') {
      throw new Error('当前环境不支持复制图片到剪贴板')
    }
    const sourceBlob = await fetchViewerImageBlob(imagePayload)
    // 系统剪贴板对 PNG 支持最稳定，其他图片格式统一转成 PNG 后写入。
    const clipboardBlob = sourceBlob.type === 'image/png'
      ? sourceBlob
      : await convertImageBlobToPng(sourceBlob)
    await navigator.clipboard.write([new ClipboardItem({ 'image/png': clipboardBlob })])
    toast.success('已复制图片')
  } catch (error) {
    console.warn('复制图片失败:', error)
    toast.error(toUserMessage(error?.message || error, '复制图片失败。请检查浏览器剪贴板权限，或改用另存为。'))
  }
}

const copyViewerImageUrl = async (imagePayload) => {
  try {
    if (!imagePayload?.originalSrc) throw new Error('未找到图片地址')
    if (!navigator?.clipboard?.writeText) throw new Error('当前环境不支持复制文本到剪贴板')
    await navigator.clipboard.writeText(imagePayload.originalSrc)
    toast.success('已复制图片地址')
  } catch (error) {
    console.warn('复制图片地址失败:', error)
    toast.error(toUserMessage(error?.message || error, '复制图片地址失败。请检查浏览器剪贴板权限，或手动复制地址。'))
  }
}

const saveViewerImageAs = async (imagePayload) => {
  try {
    if (!window.pywebview?.api?.image_save_as) {
      throw new Error('当前环境不支持图片另存为')
    }
    const blob = await fetchViewerImageBlob(imagePayload)
    const contentBase64 = await blobToBase64(blob)
    const res = await window.pywebview.api.image_save_as({
      filename: ensureImageFilenameExtension(imagePayload.filename, blob.type),
      mime_type: blob.type || 'application/octet-stream',
      content_base64: contentBase64,
    })
    if (res?.status === 'warning' && res?.message === '已取消') return
    checkResult(res, '图片另存为', true)
  } catch (error) {
    console.warn('图片另存为失败:', error)
    toast.error(toUserMessage(error?.message || error, '图片另存为失败。请检查目标目录权限、磁盘空间或当前运行环境是否支持保存文件。'))
  }
}

const openViewerImageContextMenu = (event, imagePayload) => {
  const contextMenuStore = useContextMenuStore()
  contextMenuStore.open(event, [
    { label: '复制图片', icon: Copy, action: () => copyViewerImage(imagePayload) },
    { label: '另存为...', icon: Download, action: () => saveViewerImageAs(imagePayload) },
    { divider: true },
    { label: '复制图片地址', icon: Link, action: () => copyViewerImageUrl(imagePayload) },
  ], imagePayload)
}

const attachViewerImageContextMenu = (event) => {
  ensureImageViewerStyle()
  const viewerImage = event?.detail?.image
  if (!viewerImage) return
  if (viewerImage._viewerImageContextMenu) {
    viewerImage.removeEventListener('contextmenu', viewerImage._viewerImageContextMenu)
  }
  const imagePayload = getViewerImagePayload(viewerImage, event?.detail?.originalImage)
  const handler = (menuEvent) => openViewerImageContextMenu(menuEvent, imagePayload)
  viewerImage.addEventListener('contextmenu', handler)
  viewerImage._viewerImageContextMenu = handler
}

export const imageViewerOptions = {
  className: 'image-viewer',
  focus: false,
  navbar: false,
  title: false,
  toolbar: true,
  tooltip: true,
  movable: true,
  zoomable: true,
  rotatable: true,
  scalable: true,
  transition: false,
  zIndex: 9000,
  filter: shouldPreviewImage,
  shown: ensureImageViewerStyle,
  hide: blurActiveViewerFocus,
  viewed: attachViewerImageContextMenu,
}

export const decoratePreviewableHtmlImages = (html, options = {}) => {
  if (typeof document === 'undefined') return html

  const { resolveImageUrl = null } = options
  const wrapper = document.createElement('div')
  wrapper.innerHTML = String(html || '')

  wrapper.querySelectorAll('img[src]').forEach((img) => {
    const rawSrc = String(img.getAttribute('src') || '').trim()
    const nextSrc = typeof resolveImageUrl === 'function'
      ? String(resolveImageUrl(rawSrc) || rawSrc).trim()
      : rawSrc

    if (nextSrc) {
      img.setAttribute('src', nextSrc)
    }
    img.setAttribute('loading', 'lazy')

    if (shouldPreviewImage(img)) {
      img.classList.add('cursor-zoom-in')
    } else {
      img.classList.remove('cursor-zoom-in')
    }
  })

  return wrapper.innerHTML
}
