import DOMPurify from 'dompurify'
import MarkdownIt from 'markdown-it'
import hljs from 'highlight.js'
import 'highlight.js/styles/atom-one-dark.css'
import { decoratePreviewableHtmlImages } from './domEffects'

const md = new MarkdownIt({
  html: true,
  linkify: true,
  typographer: true,
  highlight: (str, lang) => {
    if (lang && hljs.getLanguage(lang)) {
      try {
        return `<pre class="hljs p-3 rounded-lg text-xs overflow-x-auto custom-scrollbar my-2 border border-border-base/10 bg-bg-inset/90"><code>${hljs.highlight(str, { language: lang, ignoreIllegals: true }).value}</code></pre>`
      } catch {}
    }
    return `<pre class="hljs p-3 rounded-lg text-xs overflow-x-auto custom-scrollbar my-2 border border-border-base/10 bg-bg-inset/90"><code>${md.utils.escapeHtml(str)}</code></pre>`
  },
})

export const sanitizeRenderedHtml = (html) => DOMPurify.sanitize(html, {
  USE_PROFILES: { html: true },
  ADD_TAGS: ['details', 'summary'],
  ADD_ATTR: ['class', 'target', 'rel', 'src', 'alt', 'title', 'loading'],
})

export const renderMarkdownContent = (text, options = {}) => {
  const rendered = md.render(String(text || '')).replace(/<code>/g, '<code class="bg-bg-inset/70 text-accent-special px-1.5 py-0.5 rounded text-sm font-mono border border-border-base/10">')
  const withCachedImages = decoratePreviewableHtmlImages(rendered, { resolveImageUrl: options.resolveImageUrl })
  return sanitizeRenderedHtml(withCachedImages)
}
