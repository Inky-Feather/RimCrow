// -----------------------------------------------------------------
// AI Token 用量提示词
// -----------------------------------------------------------------
// 这里统一生成 tooltip 文案，避免多个组件各自拼接后出现字段名、
// 顺序和术语不一致。

import { t } from '../../shared/i18n.js'

const numberOrZero = (value) => {
  /** 把任意输入压成安全数字，避免 tooltip 拼接时出现 NaN。 */
  const numeric = Number(value || 0)
  return Number.isFinite(numeric) ? numeric : 0
}

const formatTokenCount = (value) => numberOrZero(value).toLocaleString('zh-CN')

const appendDetailLine = (lines, label, value) => {
  /** 仅在某项 token > 0 时才把细项写入 tooltip，避免出现大段空统计。 */
  const numeric = numberOrZero(value)
  if (numeric <= 0) return
  lines.push(t('ai.usage.detail_line', ' - ··{label} [[{count}]] token··', { label, count: formatTokenCount(numeric) }))
}

export const buildUserMessageUsageTooltip = ({
  totalTokens = 0,
  promptTokens = 0,
  promptTemplateTokens = 0,
  memoryTokens = 0,
  attachmentTokens = 0,
  userInputTokens = 0,
  toolContextTokens = 0,
  forcedSummaryTokens = 0,
} = {}) => {
  /** 生成“用户侧消息输入”说明。 */
  // “消息输入”强调的是一次真实请求里送给模型的主对话输入成本，
  // 不只等于用户文本本身。
  const lines = [
    t('ai.usage.user_input_intro', '消息输入按一次真实请求统计的^^估算Token^^，包含系统提示词、会话记忆、附件信息、用户输入、工具回灌和必要的总结补充。'),
    t('ai.usage.main_prompt_input', '主对话输入 ^^{count}^^ token', { count: formatTokenCount(promptTokens || totalTokens) }),
  ]
  appendDetailLine(lines, t('ai.usage.system_prompt', '系统提示'), promptTemplateTokens)
  appendDetailLine(lines, t('ai.usage.session_memory', '会话记忆'), memoryTokens)
  appendDetailLine(lines, t('ai.usage.attachments', '附件信息'), attachmentTokens)
  appendDetailLine(lines, t('ai.usage.user_input', '用户输入'), userInputTokens)
  appendDetailLine(lines, t('ai.usage.tool_context', '工具调用'), toolContextTokens)
  appendDetailLine(lines, t('ai.usage.forced_summary', '总结补充'), forcedSummaryTokens)
  return lines.join('\n')
}

export const buildAssistantMessageUsageTooltip = ({
  totalTokens = 0,
  completionTokens = 0,
  reasoningTokens = 0,
  toolCallTokens = 0,
  answerTokens = 0,
} = {}) => {
  /** 生成“助手侧消息输出”说明。 */
  // “消息输出”既包含最终正文，也包含 reasoning/tool call 这类用户未必直接看到的成本。
  const lines = [
    t('ai.usage.assistant_output_intro', '消息输出按一次真实请求统计的^^估算Token^^，包含主回复输出、工具调用、深度思考和回复正文等内容的总和。'),
    t('ai.usage.main_completion_output', '主回复输出 ^^{count}^^ token', { count: formatTokenCount(completionTokens || totalTokens) }),
  ]
  appendDetailLine(lines, t('ai.usage.reasoning', '深度思考'), reasoningTokens)
  appendDetailLine(lines, t('ai.usage.tool_calls', '工具调用'), toolCallTokens)
  appendDetailLine(lines, t('ai.usage.answer_body', '回复正文'), answerTokens)
  return lines.join('\n')
}

export const buildRequestTotalUsageTooltip = ({
  totalTokens = 0,
  promptTokens = 0,
  completionTokens = 0,
  toolRounds = 0,
} = {}) => {
  /** 生成“整轮请求总账”说明。 */
  // 总请求消耗是整轮链路的总账，适合和单条消息的局部消耗做区分。
  const lines = [
    t('ai.usage.request_total_intro', '总请求消耗是本轮完整请求的^^估算Token^^总和。'),
    t('ai.usage.request_total', '总请求消耗 ^^{count}^^ token', { count: formatTokenCount(totalTokens) }),
  ]
  appendDetailLine(lines, t('ai.usage.main_prompt_input_label', '主对话输入'), promptTokens)
  appendDetailLine(lines, t('ai.usage.main_completion_output_label', '主回复输出'), completionTokens)
  if (numberOrZero(toolRounds) > 0) {
    lines.push(t('ai.usage.tool_rounds', '工具轮次 [[{count}]] 轮', { count: numberOrZero(toolRounds) }))
  }
  return lines.join('\n')
}

export { formatTokenCount, numberOrZero }
