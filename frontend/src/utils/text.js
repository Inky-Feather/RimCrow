/**
 * 对纯文本做 HTML 转义，避免直接插入 DOM 时破坏结构。
 */
export const escapeHtml = (value = '') => String(value)
  .replace(/&/g, '&amp;')
  .replace(/</g, '&lt;')
  .replace(/>/g, '&gt;')
  .replace(/"/g, '&quot;')
  .replace(/'/g, '&#39;')

/**
 * 根据搜索配置构造正则；当正则无效时返回 null。
 */
export function buildSearchRegExp(query, { useRegex = false, caseSensitive = false } = {}) {
  const source = String(query || '')
  if (!source) return null

  const flags = caseSensitive ? 'g' : 'gi'
  if (useRegex) {
    try {
      return new RegExp(source, flags)
    } catch {
      return null
    }
  }

  return new RegExp(source.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), flags)
}

/**
 * 将 Unity Rich Text (BBCode 变体) 转换为 HTML
 * 
 * @param {string} unityText - 原始文本
 * @param {boolean} removeImg - 是否移除图片标签 (默认 true)
 * @returns {string} 转换后的 HTML
 */
export const parseUnityRichText = (unityText, removeImg = true, remoteImageResolver = null) => {
  // 严谨空值判断，过滤纯空白文本
  if (!unityText || unityText.trim() === '') return ''

  // 1. 先统一换行格式，后面的正则处理都按 `\n` 进行。
  let htmlText = unityText.replace(/\r\n/g, '\n').replace(/\r/g, '\n').replace(/\\n/g, '\n')
  const tableCellClass = 'p-2 border border-text-main/10'
  const tableHeaderClass = `${tableCellClass} text-left align-top font-semibold`
  const protectedBlocks = []

  const protectBlock = (content = '') => {
    const token = `__UNITY_PROTECTED_${protectedBlocks.length}__`
    protectedBlocks.push(content)
    return token
  }

  const resolveMediaUrl = (src = '') => {
    const normalizedSrc = String(src).trim().replace(/^["']|["']$/g, '')
    if (!normalizedSrc) return ''
    return typeof remoteImageResolver === 'function'
      ? String(remoteImageResolver(normalizedSrc) || normalizedSrc).trim()
      : normalizedSrc
  }

  const parsePreviewLayout = (rawAttrs = '') => {
    const attrs = String(rawAttrs || '')
    const size = /sizeOriginal/i.test(attrs)
      ? 'original'
      : /sizeFull/i.test(attrs)
        ? 'full'
        : /sizeThumb/i.test(attrs)
          ? 'thumb'
          : 'thumb'
    const align = /floatRight/i.test(attrs)
      ? 'right'
      : /floatLeft/i.test(attrs)
        ? 'left'
        : /inline/i.test(attrs)
          ? 'inline'
          : 'center'
    return { size, align }
  }

  const buildPreviewFigure = ({ src, alt = '', rawAttrs = '', extraClasses = '', element = 'img' } = {}) => {
    const resolvedSrc = resolveMediaUrl(src)
    if (!resolvedSrc) return ''
    const { size, align } = parsePreviewLayout(rawAttrs)
    const sizeClasses = size === 'full'
      ? 'w-full'
      : size === 'original'
        ? 'w-auto max-w-full'
        : 'w-full max-w-md'
    const alignClasses = align === 'left'
      ? 'float-left mr-4 mb-2'
      : align === 'right'
        ? 'float-right ml-4 mb-2'
        : align === 'inline'
          ? 'inline-block align-middle mx-1'
          : 'mx-auto'
    const classes = [sizeClasses, alignClasses, 'rounded-lg', 'border', 'border-text-main/10', extraClasses]
      .filter(Boolean)
      .join(' ')
    const altText = escapeHtml(alt || 'preview-image')
    const clearFloat = align === 'left' || align === 'right'
      ? '<div class="clear-both"></div>'
      : ''
    return `<${element} ${element === 'video' ? `poster="${encodeURI(resolvedSrc)}"` : `src="${encodeURI(resolvedSrc)}"`} alt="${altText}" class="${classes}" loading="lazy" style="object-fit: contain; margin-top: 5px; margin-bottom: 5px;" />${clearFloat}`
  }

  const buildPreviewImageTag = (src = '', alt = '', extraClasses = '') => {
    return buildPreviewFigure({ src, alt, extraClasses })
  }

  // `noparse` 需要最先保护，否则内部标记会被后续规则提前消费。
  htmlText = htmlText.replace(/\[noparse\]([\s\S]*?)\[\/noparse\]/gi, (_, content) => (
    protectBlock(`<code class="bg-black/30 px-1 rounded font-mono text-xs">${escapeHtml(content)}</code>`)
  ))
  // `code` 也必须在前面保护，否则内部链接、列表或其它标签会被继续解析。
  htmlText = htmlText.replace(/\[code\]([\s\S]*?)\[\/code\]/gi, (_, content) => (
    protectBlock(`<pre class="bg-black/30 rounded font-mono text-xs block p-2 my-2 overflow-x-auto"><code>${escapeHtml(content)}</code></pre>`)
  ))

  htmlText = htmlText.replace(/\[table([^\]]*)\]\s*/gi, (_, rawAttrs = '') => {
    const noborder = /\bnoborder\s*=\s*["']?1["']?/i.test(rawAttrs)
    const equalcells = /\bequalcells\s*=\s*["']?1["']?/i.test(rawAttrs)
    const tableClasses = ['w-full', 'my-2']
    const tableStyles = []

    if (equalcells) {
      tableClasses.push('table-fixed')
    } else {
      tableClasses.push('border-collapse')
    }

    if (noborder) {
      tableStyles.push('border-collapse: separate', 'border-spacing: 0')
    }

    const styleAttr = tableStyles.length ? ` style="${tableStyles.join('; ')}"` : ''
    const flags = [noborder ? 'noborder' : '', equalcells ? 'equalcells' : '']
      .filter(Boolean)
      .join(' ')

    return `<table class="${tableClasses.join(' ')}" data-unity-table="${flags}"${styleAttr}>`
  })

  // 2. 基础标签映射，优先处理结构性最强的一批标签。
  const simpleTags = [
    { regex: /\[b\]/gi, replace: '<strong>' },
    { regex: /\[\/b\]/gi, replace: '</strong>' },
    { regex: /\[u\]/gi, replace: '<u>' },
    { regex: /\[\/u\]/gi, replace: '</u>' },
    { regex: /\[i\]/gi, replace: '<em>' },
    { regex: /\[\/i\]/gi, replace: '</em>' },
    // 表格相关 (添加了 tailwind 边框类)
    { regex: /\[\/table\]\s*/gi, replace: '</table>' },
    { regex: /\[tr\]\s*/gi, replace: '<tr class="border-b border-text-main/10">' },
    { regex: /\[\/tr\]\s*/gi, replace: '</tr>' },
    { regex: /\[th\]\s*/gi, replace: `<th class="${tableHeaderClass}">` },
    { regex: /\[\/th\]\s*/gi, replace: '</th>' },
    { regex: /\[td\]\s*/gi, replace: `<td class="${tableCellClass}">` },
    { regex: /\[\/td\]\s*/gi, replace: '</td>' },
    // [*]替换为</li><li>，解决无闭合问题
    { regex: /\[list\]\s*/gi, replace: '<ul class="list-disc pl-5 my-2" style="white-space: normal"><li>' },
    { regex: /\[\/list\]\s*/gi, replace: '</li></ul>' },
    { regex: /\[olist\]\s*/gi, replace: '<ol class="list-decimal pl-5 my-2" style="white-space: normal"><li>' },
    { regex: /\[\/olist\]\s*/gi, replace: '</li></ol>' },
    { regex: /\[\*\]\s*/gi, replace: '</li><li>' },
    { regex: /<li><\/li>/gi, replace: '' },
    // 分割线 
    { regex: /\[hr\]\s*/gi, replace: '<div class="w-3/4 mx-auto border-t border-text-main/10 my-4"></div>' },
    { regex: /\[\/hr\]\s*/gi, replace: '' },
    { regex: /\[br\]/gi, replace: '<br>' },
    { regex: /\[p\]/gi, replace: '<p class="mb-2">' },
    { regex: /\[\/p\]/gi, replace: '</p>' },
    // 删除线
    { regex: /\[strike\]/gi, replace: '<del>' },
    { regex: /\[\/strike\]/gi, replace: '</del>' },
  ]

  for (const tag of simpleTags) {
    htmlText = htmlText.replace(tag.regex, tag.replace)
  }

  htmlText = htmlText.replace(/<table([^>]*)data-unity-table="([^"]*)"([^>]*)>([\s\S]*?)<\/table>/gi, (match, beforeAttrs, flagText, afterAttrs, content) => {
    const flags = new Set(String(flagText).split(/\s+/).filter(Boolean))
    let nextContent = content

    if (flags.has('noborder')) {
      nextContent = nextContent
        .replace(/<tr class="border-b border-text-main\/10">/gi, '<tr>')
        .replace(new RegExp(`<th class="${tableHeaderClass.replace(/\//g, '\\/')}"`, 'g'), '<th class="p-2 text-left align-top font-semibold"')
        .replace(new RegExp(`<td class="${tableCellClass.replace(/\//g, '\\/')}"`, 'g'), '<td class="p-2"')
    }

    return `<table${beforeAttrs}${afterAttrs}>${nextContent}</table>`
  })

  // 3. 标题标签单独处理，避免和普通标签规则混在一起难维护。
  for (let i = 1; i <= 6; i++) {
    const startRegex = new RegExp(`\\[h${i}\\]`, 'gi')
    const endRegex = new RegExp(`\\[\\/h${i}\\][\n]*`, 'gi')
    htmlText = htmlText
      .replace(startRegex, `<h${i} class="font-bold ${i === 1 ? 'text-xl' : i === 2 ? 'text-lg' : 'text-base'}">`)
      .replace(endRegex, `</h${i}>`)
  }

  // 4. 处理 Unity 特有的 `<color>` / `[color]`、`<size>` / `[size]` 双写法。
  // 支持带引号 <color="#fff"> 和不带引号 <color=#fff>
  htmlText = htmlText
    .replace(/\[color="?(\#[0-9a-fA-F]{6}|\#[0-9a-fA-F]{8}|[a-zA-Z]+)"?\]/gi, '<span style="color:$1">')
    .replace(/<color="?(#[0-9a-fA-F]{6}|#[0-9a-fA-F]{8}|[a-zA-Z]+)"?>/gi, '<span style="color:$1">')
    .replace(/\[\/color\]/gi, '</span>')
    .replace(/<\/color>/gi, '</span>')
    // 字体大小 尖括号+方括号双版本
    .replace(/\[size=(\d+)\]/gi, '<span style="font-size:$1px">')
    .replace(/<size=(\d+)>/gi, '<span style="font-size:$1px">')
    .replace(/\[\/size\]/gi, '</span>')
    .replace(/<\/size>/gi, '</span>')

  // 5. 处理 Steam 常见的引用、剧透与显式 URL 标签。
  htmlText = htmlText
    .replace(
      /\[quote=([^\]]+)\]([\s\S]*?)\[\/quote\]/gi,
      (_, author, content) => `<blockquote class="my-3 rounded-lg border-l-4 border-text-main/15 bg-black/15 px-4 py-3"><div class="mb-2 text-xs text-text-dim">Originally posted by ${escapeHtml(author)}:</div><div>${content}</div></blockquote>`,
    )
    .replace(
      /\[quote\]([\s\S]*?)\[\/quote\]/gi,
      (_, content) => `<blockquote class="my-3 rounded-lg border-l-4 border-text-main/15 bg-black/15 px-4 py-3">${content}</blockquote>`,
    )
    .replace(
      /\[spoiler\]([\s\S]*?)\[\/spoiler\]/gi,
      (_, content) => `<details class="inline-block max-w-full align-middle rounded-md border border-text-main/10 bg-black/20 px-2 py-1"><summary class="cursor-pointer select-none text-xs text-text-dim">剧透内容</summary><div class="mt-2">${content}</div></details>`,
    )
    .replace(
      /\[pullquote\]([\s\S]*?)\[\/pullquote\]/gi,
      (_, content) => `<blockquote class="my-3 rounded-lg border-l-4 border-accent-primary/40 bg-black/10 px-4 py-3 italic text-text-main/90">${content}</blockquote>`,
    )

  // 6. 显式 URL 标签转成链接。
  // [url=xxx]text[/url] -> <a href="xxx">text</a>
  htmlText = htmlText.replace(
    /\[url=(.*?)\](.*?)\[\/url\]/gi,
    (_, href, text) => `<a href="${encodeURI(String(href).trim())}" target="_blank" class="text-accent-primary hover:underline cursor-pointer">${text}</a>`,
  )
  htmlText = htmlText.replace(
    /\[url\](.*?)\[\/url\]/gi,
    (_, href) => {
      const normalizedHref = String(href).trim()
      return `<a href="${encodeURI(normalizedHref)}" target="_blank" class="text-accent-primary hover:underline cursor-pointer">${escapeHtml(normalizedHref)}</a>`
    },
  )

  // 7. Guide/Workshop 专用的预览媒体做最佳努力渲染。
  htmlText = htmlText.replace(/\[video([^\]]*)\]([\s\S]*?)\[\/video\]/gi, (_, rawAttrs = '', innerContent = '') => {
    const mp4Match = String(rawAttrs).match(/\bmp4=([^\]\s]+)/i)
    const posterMatch = String(rawAttrs).match(/\bposter=([^\]\s]+)/i)
    const autoplayOff = /\bautoplay=0\b/i.test(rawAttrs)
    const resolvedVideoUrl = resolveMediaUrl(mp4Match?.[1] || innerContent)
    const resolvedPosterUrl = resolveMediaUrl(posterMatch?.[1] || '')
    if (!resolvedVideoUrl) return ''
    const { size, align } = parsePreviewLayout(rawAttrs)
    const sizeClasses = size === 'full'
      ? 'w-full'
      : size === 'original'
        ? 'w-auto max-w-full'
        : 'w-full max-w-md'
    const alignClasses = align === 'left'
      ? 'float-left mr-4 mb-2'
      : align === 'right'
        ? 'float-right ml-4 mb-2'
        : align === 'inline'
          ? 'inline-block align-middle mx-1'
          : 'mx-auto'
    const clearFloat = align === 'left' || align === 'right' ? '<div class="clear-both"></div>' : ''
    return `<video class="${sizeClasses} ${alignClasses} rounded-lg border border-text-main/10 my-2" controls ${autoplayOff ? '' : 'autoplay'} preload="metadata" muted playsinline ${resolvedPosterUrl ? `poster="${encodeURI(resolvedPosterUrl)}"` : ''} src="${encodeURI(resolvedVideoUrl)}"></video>${clearFloat}`
  })
  htmlText = htmlText.replace(/\[previewyoutube=([^;\]]+)(?:;([^\]]+))?\]\[\/previewyoutube\]/gi, (_, videoId, mode = '') => {
    const youtubeId = String(videoId || '').trim()
    if (!youtubeId) return ''
    const previewMode = String(mode || '').trim().toLowerCase()
    const layoutClass = previewMode.includes('full')
      ? 'w-full aspect-video'
      : previewMode.includes('right')
        ? 'w-full max-w-sm aspect-video float-right ml-4 mb-2'
        : previewMode.includes('left')
          ? 'w-full max-w-sm aspect-video float-left mr-4 mb-2'
          : 'w-full max-w-2xl aspect-video mx-auto'
    return `<iframe class="${layoutClass} my-2 rounded-lg border border-text-main/10" src="https://www.youtube.com/embed/${encodeURIComponent(youtubeId)}" title="YouTube preview" loading="lazy" allowfullscreen referrerpolicy="no-referrer-when-downgrade"></iframe>`
  })
  htmlText = htmlText.replace(/\[(previewimg|previewicon|screenshot)=([^\]]+)\]([\s\S]*?)\[\/\1\]/gi, (_, tagName, rawArgs, altText) => {
    const args = String(rawArgs || '').split(';').map(item => item.trim()).filter(Boolean)
    const sourceArg = [...args].reverse().find(item => /^https?:\/\//i.test(item))
    if (!sourceArg) {
      return `<span class="inline-block rounded-md border border-text-main/10 bg-black/20 px-2 py-1 text-xs text-text-dim">${tagName}</span>`
    }
    const extraClasses = tagName === 'previewicon' ? 'max-w-20 max-h-20' : ''
    return buildPreviewFigure({ src: sourceArg, alt: altText, rawAttrs, extraClasses })
  })

  // 8. 文本分隔线语法转成可视化分隔块。
  // 匹配格式：
  // - 可选的【或[开头
  // - 3个以上的分隔符（星号、减号、等号、下划线、破折号）
  // - 可选的空格
  // - 标题内容（可选）
  // - 可选的空格
  // - 3个以上的分隔符（星号、减号、等号、下划线、破折号）
  // - 可选的】或]结尾
  const dividerRegex = /(?:^|\n)[\t ]*[【\[\(]?\s*([\*\.\-—―=_─~]{2,}) *(.*?) *(?:[\*\.\-—―=_─~]{2,})\s*[】\]\)]?[\t \s]*/g
  htmlText = htmlText.replace(dividerRegex, (match, symbol, content) => {
    // match: 完整匹配字符串；symbol: 捕获的符号 (如 '=')；content: 捕获的标题内容 (如 '更新')
    const text = content ? content.trim() : ''
    if (text) { // --- 带标题的分割线 ---
      return `<div class="flex w-3/4 items-center mx-auto my-4"><div class="grow border-t border-text-main/10"></div><span class="text-xs mx-1 text-text-main/40 font-bold whitespace-nowrap">${text}</span><div class="grow border-t border-text-main/10"></div></div>`
    } else {// --- 纯分割线 ---
      // (为了保持高度一致，也可以用 Flex 写法，或者用之前的 simple div)
      return '<div class="w-3/4 mx-auto border-t border-text-main/10 my-4"></div>'
    }
  })

  // 9. 图片标签按调用方决定保留还是清理。
  const renderImageTag = (src = '') => {
    const normalizedSrc = String(src).trim().replace(/^["']|["']$/g, '')
    if (!normalizedSrc) return ''
    if (removeImg) return ''
    return buildPreviewImageTag(normalizedSrc, 'unity-img')
  }

  if (removeImg) {
    htmlText = htmlText.replace(/\[img\](.*?)\[\/img\]\n*/gi, '')
  } else {
    htmlText = htmlText.replace(/\[img\](.*?)\[\/img\]\n*/gi, (_, src) => renderImageTag(src))
  }
  htmlText = htmlText.replace(/\[img=([^\]\n\r]+)\]\s*/gi, (_, src) => renderImageTag(src))

  // 10. 自动识别纯文本里的裸链接，但要先保护已生成的 HTML。
  const placeholders = []
  htmlText = htmlText.replace(/<[^>]+?>/g, (match) => {
    placeholders.push(match)
    return `__HTML_${placeholders.length - 1}__`
  })
  // 匹配 URL: 以 http/https 开头，直到遇到空格或特殊符号
  htmlText = htmlText.replace(/(https?:\/\/[^\s<]+)/gi, match => (
    `<a href="${encodeURI(match)}" target="_blank" class="text-accent-primary hover:underline break-all">${match}</a>`
  ))
  // 还原 HTML 标签
  htmlText = htmlText.replace(/__HTML_(\d+)__/g, (_, index) => placeholders[Number(index)])
  htmlText = htmlText.replace(/__UNITY_PROTECTED_(\d+)__/g, (_, index) => protectedBlocks[Number(index)] || '')
  // 11. 保留旧逻辑里的 `\n` 转 `<br>` 行为，避免描述展示回退。
  htmlText = htmlText.replace(/\\n/g, '<br>')

  // 12. 清理替换后残留的空标签，减少无意义包裹层。补全所有空标签清理、延后trim执行时机，解决空白缝隙+丢失有效空格问题
  htmlText = htmlText
    .replace(/<table>\s*<\/table>/gi, '')
    .replace(/<ul>\s*<\/ul>/gi, '')
    .replace(/<ol>\s*<\/ol>/gi, '')
    .replace(/<p>\s*<\/p>/gi, '')
    .replace(/<div>\s*<\/div>/gi, '')
    .replace(/<pre[^>]*>\s*<code>\s*<\/code>\s*<\/pre>/gi, '')
    .replace(/<blockquote[^>]*>\s*<\/blockquote>/gi, '')
    .replace(/<strong>\s*<\/strong>/gi, '')
    .trim()

  // 13. 统一包裹展示容器，保持现有样式和 white-space 行为不变。
  return `<div class="unity-content text-sm leading-relaxed" style="white-space: pre-wrap;">${htmlText}</div>`
}

/**
 * 将富文本描述压缩成适合提示词或摘要展示的纯文本。
 */
export const cleanRichText = (text, maxLength = 500) => {
  if (!text) return ''

  let clean = text;
  // 1. 移除 Unity 标签 (如 <color=#ff0000>...</color>, <b>...</b>)
  // 采用非贪婪匹配移除所有 <...> 格式的标签
  clean = clean.replace(/<[^>]+>/g, '');
  // 2. 移除 Steam/BBCode 链接标签，但保留中间的文字内容
  // 匹配 [url=xxxx]显示文字[/url] -> 替换为 "显示文字"
  clean = clean.replace(/\[url=[^\]]*\]([^\[]+)\[\/url\]/gi, '$1');
  // 3. 移除其它 BBCode 标签 (如 [list], [img], [b], [i] 等)
  // 匹配所有 [...] 格式的标签
  clean = clean.replace(/\[[^\]]+\]/g, '');
  // 4. 移除 Markdown 格式的链接 (如果描述里有的话)
  // 匹配 [显示文字](http://...) -> 替换为 "显示文字"
  clean = clean.replace(/\[([^\]]+)\]\([^\)]+\)/g, '$1');
  // 5. 移除裸露的 URL (http/https/ftp)
  // AI 不需要具体的网址来理解 Mod 的功能
  clean = clean.replace(/(https?|ftp):\/\/[^\s/$.?#].[^\s]*/gi, '');
  // 6. 极致压缩：去除多余换行、制表符
  // 将 2 个及以上的换行/空格合并为 1 个，并去除首尾空格
  clean = clean.replace(/\s{2,}/g, ' ').replace(/\n+/g, '\n').trim();
  // 7. 长度兜底拦截 (AI 只需要前 300-500 字通常就足够理解功能了)
  if (clean.length > maxLength) {
    clean = clean.substring(0, maxLength) + "...";
  }

  return clean
}
