

<template>
  <!-- 使用 Tailwind Typography 插件美化排版 -->
  <div 
    class="prose prose-invert prose-sm max-w-none wrap-break-word whitespace-pre-wrap leading-relaxed custom-rich-text"
    v-html="processedContent"
  ></div>
</template>

<script setup>
import { computed } from 'vue'
import MarkdownIt from 'markdown-it'
import DOMPurify from 'dompurify'

const props = defineProps({
  content: {
    type: String,
    default: ''
  }
})

// 配置 Markdown 解析器
const md = new MarkdownIt({
  html: true,       // 允许 HTML 标签
  breaks: true,     // 转换 \n 为 <br>
  linkify: true,    // 自动识别 URL
  typographer: true
})

// === 核心处理流水线 ===
const processedContent = computed(() => {
  if (!props.content) return '<span class="text-gray-500 italic">暂无简介</span>'

  let text = props.content

  // 1. 【预处理】Unity Rich Text (<color>, <size>) -> HTML
  // RimWorld 模组描述里大量存在这种非标准标签
  text = text
    .replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&') // 反转义
    .replace(/<color=(.*?)>(.*?)<\/color>/gi, '<span style="color: $1;">$2</span>')
    .replace(/<size=(.*?)>(.*?)<\/size>/gi, '<span style="font-size: 1.1em;">$2</span>') // 简单处理 size
    .replace(/<b>(.*?)<\/b>/gi, '<strong>$1</strong>')
    .replace(/<i>(.*?)<\/i>/gi, '<em>$1</em>')

  // 2. 【预处理】BBCode -> HTML/Markdown
  // Steam 工坊常混用 BBCode
  text = text
    .replace(/\[b\](.*?)\[\/b\]/gi, '<strong>$1</strong>')
    .replace(/\[i\](.*?)\[\/i\]/gi, '<em>$1</em>')
    .replace(/\[u\](.*?)\[\/u\]/gi, '<u>$1</u>')
    .replace(/\[h1\](.*?)\[\/h1\]/gi, '# $1') // 转为 Markdown 标题
    .replace(/\[h2\](.*?)\[\/h2\]/gi, '## $1')
    .replace(/\[url=(.*?)\](.*?)\[\/url\]/gi, '[$2]($1)') // 转为 Markdown 链接
    .replace(/\[img\](.*?)\[\/img\]/gi, '![]($1)') // 转为 Markdown 图片
    .replace(/\[list\]/gi, '\n').replace(/\[\/list\]/gi, '')
    .replace(/\[\*\]/gi, '- ') // 转为 Markdown 列表
    .replace(/\[hr\]/gi, '---')

  // 3. 【核心解析】Markdown -> HTML
  let html = md.render(text)

  // 4. 【安全清洗】防止 XSS 攻击
  // 允许 style 标签是为了保留颜色设置，target 标签是为了链接在新窗口打开
  html = DOMPurify.sanitize(html, {
    ADD_TAGS: ['span'],
    ADD_ATTR: ['style', 'target'] 
  })

  // 5. 【链接优化】所有链接强制在新窗口打开（防止在本窗口跳转覆盖了界面）
  html = html.replace(/<a /g, '<a target="_blank" rel="noopener noreferrer" ')

  return html
})
</script>

<style>
/* 针对 RimWorld 描述的特殊微调 */
.custom-rich-text a {
  color: var(--color-accent-primary, #06b6d4);
  text-decoration: none;
}
.custom-rich-text a:hover {
  text-decoration: underline;
}
.custom-rich-text img {
  border-radius: 8px;
  max-width: 100%;
  margin-top: 0.5em;
  margin-bottom: 0.5em;
  border: 1px solid rgba(255,255,255,0.1);
}
.custom-rich-text h1, .custom-rich-text h2 {
  color: white;
  font-weight: 700;
  margin-top: 1em;
  margin-bottom: 0.5em;
}
.custom-rich-text strong {
  color: #fff;
}
.custom-rich-text ul {
  list-style-type: disc;
  padding-left: 1.5em;
}
</style>