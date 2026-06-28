import { normalizeText } from '../utils/common'

// -----------------------------------------------------------------
// AI 附件显示与草稿构造
// -----------------------------------------------------------------
// 附件的“真实解析”在后端完成，这里只负责：
// 1. 把草稿整理成前端统一显示文案
// 2. 把日志上下文等前端选择态收口成稳定草稿对象

const formatTokenEstimateText = (tokenInfo = null) => {
  /** 把 token 预估结果压成适合标签展示的短文本。 */
  const estimated = Number(tokenInfo?.estimated || 0)
  if (!Number.isFinite(estimated) || estimated <= 0) return ''
  return `约 ${(estimated / 1000).toFixed(1)}k token`
}

export const buildAttachmentDisplayMeta = (attachment, getAttachmentDefinition) => {
  /**
   * 为输入框里的附件标签生成摘要与细节文案。
   *
   * 这里优先使用草稿快照，而不是强依赖后端已解析字段，
   * 这样用户刚选中上下文时就能立即看到稳定反馈。
   */
  // 摘要优先使用用户当前看到的 snapshot 文案，
  // 这样即使后端真正解析前，输入框里的附件标签也不会突然跳变。
  if (!attachment) {
    return { summary: '附件', detail: '' }
  }
  if (typeof attachment === 'string') {
    return { summary: attachment, detail: '' }
  }
  const snapshot = attachment.snapshot && typeof attachment.snapshot === 'object' ? attachment.snapshot : {}
  const summary = normalizeText(
    attachment.summary || attachment.title || snapshot.summary || snapshot.label,
  )
  const detail = normalizeText(snapshot.detail || snapshot.token_estimate_text || snapshot.meta)
  if (summary) {
    return {
      summary: `附件: ${summary}`,
      detail,
    }
  }
  const kind = normalizeText(attachment.kind || attachment.type)
  const definition = typeof getAttachmentDefinition === 'function' ? getAttachmentDefinition(kind) : null
  return {
    summary: `附件: ${definition?.label || '上下文'}`,
    detail,
  }
}

export const buildDiagnosisContextAttachmentDraft = ({
  sourceType = 'game',
  filename = '',
  selectedLineNumbers = [],
  isGlobalSummary = false,
  selectedLogCount = 0,
  sourceLabel = '',
  tokenInfo = null,
  summaryText = '',
  detailText = '',
} = {}) => ({
  /**
   * 构造日志诊断附件草稿。
   *
   * 这只是“前端选择态”的序列化结果：
   * - source 描述日志来源
   * - selector 描述是局部选中还是全局摘要
   * - snapshot 只提供界面展示需要的即时文案
   */
  // 全局扫描和局部选中共用同一附件类型，
  // 区别只体现在 selector.mode 与 snapshot 文案上，避免后端分叉处理。
  kind: 'diagnosis_context',
  source: {
    owner_type: 'log_viewer',
    source_type: normalizeText(sourceType, 'game'),
    filename: normalizeText(filename),
  },
  selector: {
    mode: isGlobalSummary ? 'all' : 'summary',
    values: isGlobalSummary
      ? []
      : (Array.isArray(selectedLineNumbers) ? selectedLineNumbers : []),
  },
  snapshot: {
    summary: normalizeText(summaryText) || (
      isGlobalSummary
        ? `${normalizeText(sourceLabel, '日志')}摘要`
        : `${Number(selectedLogCount || 0)} 条已选${normalizeText(sourceLabel, '日志')}`
    ),
    detail: normalizeText(detailText) || formatTokenEstimateText(tokenInfo),
    token_estimate: Number(tokenInfo?.estimated || 0),
    token_estimate_text: normalizeText(detailText) || formatTokenEstimateText(tokenInfo),
    source_label: normalizeText(sourceLabel),
  },
})
