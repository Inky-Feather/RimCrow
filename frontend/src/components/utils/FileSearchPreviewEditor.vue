<template>
  <div v-if="loading" class="flex h-full items-center justify-center text-sm text-text-dim">
    正在读取文件...
  </div>

  <div v-else-if="error" class="flex h-full items-center justify-center px-6 text-center text-sm text-accent-danger">
    {{ error }}
  </div>

  <div v-else-if="!hasContent" class="flex h-full items-center justify-center px-6 text-center text-sm text-text-dim">
    选择左侧文件或命中项后，这里显示只读文件内容。
  </div>

  <div v-else class="h-full min-h-0 overflow-hidden" :style="editorCssVars">
    <CodeMirror v-model="editorContent" class="h-full file-search-preview-editor" :basic="true" :dark="true" :readonly="true" :disabled="false"
      :wrap="wrapLines" :lang="languageSupport" :extensions="editorExtensions" :scroll-into-view="false" :preserve-scroll-position="true"
      @ready="handleEditorReady"
    />
  </div>
</template>

<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import CodeMirror from 'vue-codemirror6'
import { json } from '@codemirror/lang-json'
import { xml } from '@codemirror/lang-xml'
import { csharp } from '@replit/codemirror-lang-csharp'
import { EditorSelection, RangeSetBuilder, StateEffect, StateField } from '@codemirror/state'
import { Decoration, EditorView } from '@codemirror/view'
import { getTailwindColorRgba } from '../../utils/color'
import { buildSearchRegExp } from '../../utils/text'

const props = defineProps({
  filePath: {
    type: String,
    default: '',
  },
  content: {
    type: String,
    default: '',
  },
  loading: {
    type: Boolean,
    default: false,
  },
  error: {
    type: String,
    default: '',
  },
  wrapLines: {
    type: Boolean,
    default: false,
  },
  searchQuery: {
    type: String,
    default: '',
  },
  useRegex: {
    type: Boolean,
    default: false,
  },
  caseSensitive: {
    type: Boolean,
    default: false,
  },
  lineNumber: {
    type: Number,
    default: 0,
  },
  activeMatch: {
    type: Object,
    default: null,
  },
})

const editorView = ref(null)
const editorContent = ref('')

const hasContent = computed(() => String(props.content || '').length > 0)
const editorCssVars = computed(() => ({
  '--file-search-match-bg': getTailwindColorRgba('accent-highlight', 0.5),
  '--file-search-match-current-bg': getTailwindColorRgba('accent-highlight', 1),
  '--file-search-match-current-text': 'var(--color-bg-deep)',
  '--file-search-active-line-bg': getTailwindColorRgba('accent-highlight', 0.08),
  '--file-search-active-line-gutter-bg': getTailwindColorRgba('accent-highlight', 0.12),
  '--file-search-selection-bg': getTailwindColorRgba('accent-highlight', 0.28),
  '--file-search-gutter-border': getTailwindColorRgba('text-main', 0.12),
  '--file-search-gutter-bg': getTailwindColorRgba('bg-surface', 0.7),
  '--file-search-gutter-color': getTailwindColorRgba('text-dim', 0.7),
}))

const markSearchEffect = StateEffect.define()
const matchDecoration = Decoration.mark({
  class: 'cm-search-match',
})
const currentMatchDecoration = Decoration.mark({
  class: 'cm-search-match-current',
})
const activeLineDecoration = Decoration.line({
  class: 'cm-search-active-line',
})

const searchDecorationField = StateField.define({
  create: () => Decoration.none,
  update(decorations, transaction) {
    let next = decorations.map(transaction.changes)
    for (const effect of transaction.effects) {
      if (effect.is(markSearchEffect)) {
        next = effect.value
      }
    }
    return next
  },
  provide: field => EditorView.decorations.from(field),
})

const editorTheme = EditorView.theme({
  '&': {
    height: '100%',
    fontSize: '12px',
    backgroundColor: 'transparent',
  },
  '.cm-scroller': {
    fontFamily: 'Consolas, "Cascadia Mono", "JetBrains Mono", monospace',
    overflow: 'auto',
  },
  '.cm-content': {
    minHeight: '100%',
    padding: '8px 0',
  },
  '.cm-line': {
    padding: '0 12px',
  },
  '.cm-gutters': {
    borderRight: '1px solid var(--file-search-gutter-border)',
    backgroundColor: 'var(--file-search-gutter-bg)',
    color: 'var(--file-search-gutter-color)',
  },
  '.cm-activeLineGutter': {
    backgroundColor: 'var(--file-search-active-line-gutter-bg)',
  },
  '.cm-activeLine': {
    backgroundColor: 'var(--file-search-active-line-bg)',
  },
  '.cm-selectionBackground, &.cm-focused .cm-selectionBackground, ::selection': {
    backgroundColor: 'var(--file-search-selection-bg)',
  },
}, { dark: true })

const editorExtensions = computed(() => [
  searchDecorationField,
  editorTheme,
  ...(props.wrapLines ? [EditorView.lineWrapping] : []),
])

const languageSupport = computed(() => {
  const filePath = String(props.filePath || '').toLowerCase()
  if (filePath.endsWith('.xml')) return xml()
  if (filePath.endsWith('.json')) return json()
  if (filePath.endsWith('.cs')) return csharp()
  return null
})

const buildSearchPattern = () => {
  return buildSearchRegExp(props.searchQuery, {
    useRegex: props.useRegex,
    caseSensitive: props.caseSensitive,
  })
}

const buildDecorations = (view) => {
  const builder = new RangeSetBuilder()
  const pattern = buildSearchPattern()
  const targetLine = Number(props.activeMatch?.lineNumber || props.lineNumber || 0)
  const currentMatch = props.activeMatch
  for (let index = 1; index <= view.state.doc.lines; index += 1) {
    const line = view.state.doc.line(index)
    if (targetLine === index) {
      builder.add(line.from, line.from, activeLineDecoration)
    }
    if (!pattern) continue
    const regex = new RegExp(pattern.source, pattern.flags)
    for (const match of line.text.matchAll(regex)) {
      const start = Number(match.index || 0)
      const text = String(match[0] || '')
      if (!text) continue
      const from = line.from + start
      const to = from + text.length
      const isCurrent = currentMatch
        && Number(currentMatch.lineNumber) === index
        && Number(currentMatch.start) === start
        && Number(currentMatch.end) === start + text.length
      builder.add(from, to, isCurrent ? currentMatchDecoration : matchDecoration)
    }
  }
  return builder.finish()
}

const syncEditorDecorations = () => {
  const view = editorView.value
  if (!view) return
  view.dispatch({
    effects: markSearchEffect.of(buildDecorations(view)),
  })
}

const syncEditorSelection = async () => {
  const view = editorView.value
  if (!view) return

  await jumpToTarget({
    lineNumber: props.activeMatch?.lineNumber || props.lineNumber,
    start: props.activeMatch?.start,
    end: props.activeMatch?.end,
  })
}

const syncEditorState = async () => {
  if (!editorView.value || props.loading) return
  await nextTick()
  syncEditorDecorations()
  await syncEditorSelection()
}

const clamp = (value, min, max) => Math.min(max, Math.max(min, value))

const waitForFrame = async () => {
  await new Promise(resolve => requestAnimationFrame(() => resolve()))
}

const alignEditorScroll = (view, anchor) => {
  const scrollElement = view?.scrollDOM
  if (!scrollElement) return

  const lineBlock = view.lineBlockAt(anchor)
  const maxTop = Math.max(0, scrollElement.scrollHeight - scrollElement.clientHeight)
  const centeredTop = clamp(
    lineBlock.top - Math.max(0, (scrollElement.clientHeight - lineBlock.height) / 2),
    0,
    maxTop,
  )
  scrollElement.scrollTop = centeredTop

  const coords = view.coordsAtPos(anchor)
  const scrollerRect = scrollElement.getBoundingClientRect()
  if (!coords || !Number.isFinite(coords.left) || !Number.isFinite(coords.right)) return

  const padding = 48
  const currentLeft = Number(scrollElement.scrollLeft || 0)
  const minVisibleLeft = scrollerRect.left + padding
  const maxVisibleRight = scrollerRect.right - padding

  if (coords.left < minVisibleLeft) {
    scrollElement.scrollLeft = Math.max(0, currentLeft - (minVisibleLeft - coords.left))
    return
  }

  if (coords.right > maxVisibleRight) {
    const maxLeft = Math.max(0, scrollElement.scrollWidth - scrollElement.clientWidth)
    scrollElement.scrollLeft = clamp(currentLeft + (coords.right - maxVisibleRight), 0, maxLeft)
  }
}

const jumpToTarget = async (target = {}) => {
  const view = editorView.value
  if (!view) return false

  const targetLine = Number(target.lineNumber || 0)
  if (targetLine <= 0 || targetLine > view.state.doc.lines) return false

  const line = view.state.doc.line(targetLine)
  const start = Number(target.start || 0)
  const end = Number(target.end || start)
  const anchor = Math.min(line.to, Math.max(line.from, line.from + start))
  const head = Math.min(line.to, Math.max(anchor, line.from + end))

  view.dispatch({
    selection: EditorSelection.cursor(head || anchor),
  })
  await waitForFrame()
  alignEditorScroll(view, anchor)
  return true
}

const jumpToLine = async (lineNumber) => {
  await nextTick()
  return jumpToTarget({ lineNumber })
}

const jumpToMatch = async (match) => {
  await nextTick()
  return jumpToTarget(match || {})
}

const handleEditorReady = ({ view }) => {
  editorView.value = view
  syncEditorState()
}

defineExpose({
  jumpToLine,
  jumpToMatch,
  syncEditorState,
})

watch(
  () => props.content,
  (value) => {
    editorContent.value = String(value || '')
  },
  { immediate: true }
)

watch(
  () => [
    props.content,
    props.loading,
    props.filePath,
    props.wrapLines,
    props.searchQuery,
    props.useRegex,
    props.caseSensitive,
    props.lineNumber,
    props.activeMatch?.id || '',
  ],
  async () => {
    await syncEditorState()
  },
  { deep: false }
)
</script>

<style scoped>
:deep(.file-search-preview-editor) {
  height: 100%;
}

:deep(.file-search-preview-editor .cm-editor) {
  height: 100%;
  background: transparent;
}

:deep(.file-search-preview-editor .cm-scroller) {
  overflow: auto;
}

:deep(.file-search-preview-editor .cm-search-match) {
  background: var(--file-search-match-bg);
  border-radius: 2px;
}

:deep(.file-search-preview-editor .cm-search-match-current) {
  background: var(--file-search-match-current-bg);
  color: var(--file-search-match-current-text);
  border-radius: 2px;
}

:deep(.file-search-preview-editor .cm-search-active-line) {
  background: var(--file-search-active-line-bg);
}
</style>
