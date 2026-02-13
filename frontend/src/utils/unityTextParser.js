/**
 * 将 Unity Rich Text (BBCode 变体) 转换为 HTML
 * 
 * @param {string} unityText - 原始文本
 * @param {boolean} removeImg - 是否移除图片标签 (默认 true)
 * @returns {string} 转换后的 HTML
 */
export const parseUnityRichText = (unityText, removeImg = true) => {
  // 严谨空值判断，过滤纯空白文本
  if (!unityText || unityText.trim() === '') return ''

  // 先把所有换行符统一为 \n，方便正则处理
  let htmlText = unityText.replace(/\r\n/g, '\n').replace(/\r/g, '\n').replace(/\\n/g, '\n')
  let whiteSpace = 'pre-wrap'

  // 1. 定义基础标签映射 (Type 1)
  const simpleTags = [
    { regex: /\[b\]/gi, replace: '<strong>' },
    { regex: /\[\/b\]/gi, replace: '</strong>' },
    { regex: /\[u\]/gi, replace: '<u>' },
    { regex: /\[\/u\]/gi, replace: '</u>' },
    { regex: /\[i\]/gi, replace: '<em>' },
    { regex: /\[\/i\]/gi, replace: '</em>' },
    // 表格相关 (添加了 tailwind 边框类)
    { regex: /\[table\]\s*/gi, replace: '<table class="w-full border-collapse my-2">' },
    { regex: /\[\/table\]\s*/gi, replace: '</table>' },
    { regex: /\[tr\]\s*/gi, replace: '<tr class="border-b border-text-main/10">' },
    { regex: /\[\/tr\]\s*/gi, replace: '</tr>' },
    { regex: /\[td\]\s*/gi, replace: '<td class="p-2 border border-text-main/10">' },
    { regex: /\[\/td\]\s*/gi, replace: '</td>' },
    // [*]替换为</li><li>，解决无闭合问题
    { regex: /\[list\]\s*/gi, replace: '<ul class="list-disc pl-5 my-2" style="white-space: normal"><li>' },
    { regex: /\[\/list\]\s*/gi, replace: '</li></ul>' },
    { regex: /\[\*\]\s*/gi, replace: '</li><li>' },
    { regex: /<li><\/li>/gi, replace: '' },
    // 代码块
    { regex: /\[code\]/gi, replace: '<code class="bg-black/30 px-1 rounded font-mono text-xs block p-2 my-2">' },
    { regex: /\[\/code\]/gi, replace: '</code>' },
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

  // 3. 执行 Type 1 替换
  for (const tag of simpleTags) {
    htmlText = htmlText.replace(tag.regex, tag.replace)
  }


  // 4. 处理标题 [h1]-[h6]
  for (let i = 1; i <= 6; i++) {
    const startRegex = new RegExp(`\\[h${i}\\]`, 'gi')
    const endRegex = new RegExp(`\\[\\/h${i}\\][\n]*`, 'gi')
    // 添加了字体大小和粗细样式
    htmlText = htmlText
      .replace(startRegex, `<h${i} class="font-bold text-lg">`)
      .replace(endRegex, `</h${i}>`)
  }

  // 5. 处理 Unity 特有标签：尖括号+方括号双版本 <color>/[color]、<size>/[size]
  // 支持带引号 <color="#fff"> 和不带引号 <color=#fff>
  htmlText = htmlText
    // 颜色 (Hex6/Hex8/英文名) 尖括号+方括号双版本
    .replace(/\[color="?(\#[0-9a-fA-F]{6}|\#[0-9a-fA-F]{8}|[a-zA-Z]+)"?\]/gi, '<span style="color:$1">')
    .replace(/<color="?(#[0-9a-fA-F]{6}|#[0-9a-fA-F]{8}|[a-zA-Z]+)"?>/gi, '<span style="color:$1">')
    .replace(/\[\/color\]/gi, '</span>')
    .replace(/<\/color>/gi, '</span>')
    // 字体大小 尖括号+方括号双版本
    .replace(/\[size=(\d+)\]/gi, '<span style="font-size:$1px">')
    .replace(/<size=(\d+)>/gi, '<span style="font-size:$1px">')
    .replace(/\[\/size\]/gi, '</span>')
    .replace(/<\/size>/gi, '</span>')

  // 6. URL 标签
  // [url=xxx]text[/url] -> <a href="xxx">text</a>
  // 添加了 text-accent-primary 颜色和 target="_blank"
  htmlText = htmlText.replace(
    /\[url=(.*?)\](.*?)\[\/url\]/gi,
    (_, href, text) => `<a href="${encodeURI(href)}" target="_blank" class="text-accent-primary hover:underline cursor-pointer">${text}</a>`
  )


  // 2. 定义文本分割线正则 (Type 2)
  // 匹配格式：
  // - 可选的【或[开头
  // - 3个以上的分隔符（星号、减号、等号、下划线、破折号）
  // - 可选的空格
  // - 标题内容（可选）
  // - 可选的空格
  // - 3个以上的分隔符（星号、减号、等号、下划线、破折号）
  // - 可选的】或]结尾
  const dividerRegex = /(?:^|\n)[\t ]*[【\[\(]?\s*([\*\.\-—=_─~]){2,} *(.*?) *(?:[\*\.\-—=_─~]{2,})\s*[】\]\)]?[\t \s]*/g
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
  // 8. 图片标签
  if (removeImg) {
    htmlText = htmlText.replace(/\[img\](.*?)\[\/img\]\n*/gi, '')
  } else {
    htmlText = htmlText.replace(
      /\[img\](.*?)\[\/img\]\n*/gi, 
      (_, src) => `<img src="${encodeURI(src)}" alt="unity-img" class="max-w-full rounded-lg border border-text-main/10" loading="lazy" style="object-fit: contain; margin: 0 auto; margin-top: 5px; margin-bottom: 5px;" />`
    )
  }

  
  // 纯文本链接自动转换，先把已有的 HTML 标签保护起来
  const placeholders = []
  htmlText = htmlText.replace(/<[^>]+?>/g, (match) => {
    placeholders.push(match)
    return `__HTML_${placeholders.length - 1}__`
  })
  // 现在 htmlText 里只有纯文本和占位符了，可以放心替换 URL
  // 匹配 URL: 以 http/https 开头，直到遇到空格或特殊符号
  htmlText = htmlText.replace(/(https?:\/\/[^\s<]+)/gi, (match) => {
    return `<a href="${encodeURI(match)}" target="_blank" class="text-accent-primary hover:underline break-all">${match}</a>`
  })
  // 还原 HTML 标签
  htmlText = htmlText.replace(/__HTML_(\d+)__/g, (_, index) => {
    return placeholders[Number(index)]
  })
  

  // 9. 换行处理 核心修复：white-space判断逻辑+换行转换逻辑重构
  // 修复9：提前判断原始文本是否有格式化标签，而非替换后；双换行转段落，单换行转空格
  // let hasFormatting = simpleTags.some(tag => tag.regex.test(unityText))
  // if (hasFormatting) {
  //   whiteSpace = 'normal'
  //   htmlText = htmlText.replace(/\n\n+/g, '<br><br>') // 双换行转双br，保留分段间距
  //   htmlText = htmlText.replace(/\n/g, ' ') // 单换行转空格，保留行内间隔
  // } else {
  //   htmlText = htmlText.replace(/\n/g, '<br>') // 无格式化时保留所有换行
  // }
  htmlText = htmlText.replace(/\\n/g, '<br>')

  // 10. 清理空标签 + 收尾处理
  // 修复10：补全所有空标签清理、延后trim执行时机，解决空白缝隙+丢失有效空格问题
  htmlText = htmlText
    .replace(/<table>\s*<\/table>/gi, '')
    .replace(/<ul>\s*<\/ul>/gi, '')
    .replace(/<p>\s*<\/p>/gi, '')
    .replace(/<div>\s*<\/div>/gi, '')
    .replace(/<code>\s*<\/code>/gi, '')
    .replace(/<strong>\s*<\/strong>/gi, '')
    .trim() // 最后执行trim，只清理首尾无效空白

  // 10. 最终包裹
  // 如果内容包含 html 标签，或者是纯文本，统一包裹
  return `<div class="unity-content text-sm leading-relaxed" style="white-space: ${whiteSpace};">${htmlText}</div>`
}