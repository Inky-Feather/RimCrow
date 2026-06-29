import { checkResult, getApiResponseMessage, normalizeText, toast, toUserMessage } from '../../../shared/lib/common'

const PENDING_REASONING_CAPABILITIES = {
  supports_reasoning: false,
  supports_reasoning_effort: false,
  reasoning_mode_kind: 'pending',
  reasoning_options: [
    { value: 'off', label: '关闭' },
    { value: 'auto', label: '自动' },
  ],
  default_session_reasoning_mode: 'auto',
}

const UNSUPPORTED_REASONING_CAPABILITIES = {
  supports_reasoning: false,
  supports_reasoning_effort: false,
  reasoning_mode_kind: 'unsupported',
  reasoning_options: [
    { value: 'off', label: '关闭' },
  ],
  default_session_reasoning_mode: 'off',
}

const DEFAULT_AI_BASE_URLS = {
  openai_compatible: 'https://api.openai.com/v1',
  anthropic: 'https://api.anthropic.com',
  gemini: 'https://generativelanguage.googleapis.com',
  ollama: 'http://127.0.0.1:11434',
}

const resolveAiProviderBaseUrl = (provider = '', baseUrl = '') => {
  const normalizedProvider = normalizeText(provider, 'openai_compatible').toLowerCase()
  const explicitBaseUrl = normalizeText(baseUrl).replace(/\/+$/, '')
  return explicitBaseUrl || DEFAULT_AI_BASE_URLS[normalizedProvider] || ''
}

const fingerprintText = (value = '') => {
  const text = normalizeText(value)
  if (!text) return ''
  let hash = 2166136261
  for (let index = 0; index < text.length; index += 1) {
    hash ^= text.charCodeAt(index)
    hash = Math.imul(hash, 16777619)
  }
  return (hash >>> 0).toString(36)
}

const normalizeReasoningCapabilityResult = (payload = {}, fallback = UNSUPPORTED_REASONING_CAPABILITIES) => ({
  supports_reasoning: !!payload?.supports_reasoning,
  supports_reasoning_effort: !!payload?.supports_reasoning_effort,
  reasoning_mode_kind: normalizeText(payload?.reasoning_mode_kind, fallback.reasoning_mode_kind || 'unsupported'),
  reasoning_options: Array.isArray(payload?.reasoning_options) && payload.reasoning_options.length > 0
    ? payload.reasoning_options.map(item => ({
      value: normalizeText(item?.value),
      label: normalizeText(item?.label, normalizeText(item?.value)),
    })).filter(item => item.value)
    : [...(fallback.reasoning_options || [{ value: 'off', label: '关闭' }])],
  default_session_reasoning_mode: normalizeText(
    payload?.default_session_reasoning_mode,
    fallback.default_session_reasoning_mode || 'off',
  ).toLowerCase(),
})

export const useModelConfigActions = ({
  isLoading,
  runtimeAiConfig,
  modelListCache,
  providerDefinitions,
  capabilityMeta,
} = {}) => {
  const buildAiModelCacheKey = (tempConfig = {}) => JSON.stringify({
    provider: normalizeText(tempConfig?.provider),
    base_url: resolveAiProviderBaseUrl(tempConfig?.provider, tempConfig?.base_url),
    api_key_fingerprint: normalizeText(tempConfig?.api_key_fingerprint) || fingerprintText(tempConfig?.api_key),
  })

  const getAiConfig = async () => {
    if (!window.pywebview) return
    const res = await window.pywebview.api.ai_get_config()
    if (checkResult(res, '获取AI配置')) {
      runtimeAiConfig.value = res.data || null
      return res.data
    }
  }

  const saveAIConfig = async (configData) => {
    if (!window.pywebview) return
    const res = await window.pywebview.api.ai_save_config(configData)
    if (checkResult(res, '保存AI配置', true)) {
      return true
    }
  }

  const listAiProviders = () => providerDefinitions.value || []

  const getCachedAiModels = (tempConfig = {}) => {
    const cacheKey = buildAiModelCacheKey(tempConfig)
    const models = modelListCache[cacheKey]
    return Array.isArray(models) ? [...models] : []
  }

  const getCachedAiModelOptions = (tempConfig = {}) => (
    getCachedAiModels(tempConfig).map(model => ({ value: model, label: model }))
  )

  const getAiModels = async (tempConfig, { forceRefresh = false, warnOnEmpty = false, silent = false } = {}) => {
    if (!window.pywebview) return []
    if (!tempConfig || !tempConfig.provider) {
      return []
    }
    const cacheKey = buildAiModelCacheKey(tempConfig)
    if (!forceRefresh) {
      const cachedModels = getCachedAiModels(tempConfig)
      if (cachedModels.length > 0) {
        return cachedModels
      }
    }
    isLoading.value = true
    try {
      const res = await window.pywebview.api.ai_get_models(tempConfig)
      if (checkResult(res, '获取AI模型', false, { silent })) {
        const models = Array.isArray(res.data) ? res.data.map(item => normalizeText(item)).filter(Boolean) : []
        modelListCache[cacheKey] = [...new Set(models)].sort((a, b) => a.localeCompare(b))
        if (warnOnEmpty && modelListCache[cacheKey].length === 0) {
          const provider = normalizeText(tempConfig?.provider, 'unknown')
          const baseUrl = resolveAiProviderBaseUrl(tempConfig?.provider, tempConfig?.base_url)
          toast.warning(`未获取到 AI 模型列表。请确认 ${provider} 服务已启动、Base URL 可访问、API Key 有效，并检查代理设置：${baseUrl}`, { timeout: 8000 })
        }
        return getCachedAiModels(tempConfig)
      }
    } finally {
      isLoading.value = false
    }
    return getCachedAiModels(tempConfig)
  }

  const resolveAiModelCapabilities = (tempConfig = {}) => {
    const provider = normalizeText(tempConfig?.provider)
    const model = normalizeText(tempConfig?.model)
    const baseUrl = normalizeText(tempConfig?.base_url)
    if (!provider || !model) {
      return {
        provider,
        model,
        base_url: baseUrl,
        policy_name: '',
        ...PENDING_REASONING_CAPABILITIES,
      }
    }
    const meta = capabilityMeta.value || {}
    const providerScope = normalizeText(meta?.provider_scope, 'openai_compatible')
    const unsupported = normalizeReasoningCapabilityResult(meta?.unsupported, UNSUPPORTED_REASONING_CAPABILITIES)
    if (provider !== providerScope) {
      return {
        provider,
        model,
        base_url: baseUrl,
        policy_name: '',
        ...unsupported,
      }
    }
    const policies = Array.isArray(meta?.policies) ? meta.policies : []
    const matchedPolicy = policies.find((policy) => {
      const patterns = Array.isArray(policy?.matches) ? policy.matches : []
      return patterns.some((pattern) => {
        try {
          return new RegExp(String(pattern || ''), 'i').test(model)
        } catch {
          return false
        }
      })
    }) || null
    const resolved = matchedPolicy
      ? normalizeReasoningCapabilityResult(matchedPolicy, unsupported)
      : unsupported
    return {
      provider,
      model,
      base_url: baseUrl,
      policy_name: normalizeText(matchedPolicy?.name),
      requires_reasoning_replay: !!matchedPolicy?.requires_reasoning_replay,
      prefer_responses: !!matchedPolicy?.prefer_responses,
      ...resolved,
    }
  }

  const getAiModelCapabilities = async (tempConfig = {}) => resolveAiModelCapabilities(tempConfig)

  const chatWithAI = async (prompt, tempConfig) => {
    if (!window.pywebview) {
      return { ok: false, text: '', error: '界面尚未完成初始化', isEmpty: false }
    }
    isLoading.value = true
    try {
      const res = await window.pywebview.api.ai_chat(prompt, tempConfig)
      if (checkResult(res, '测试 AI 回复')) {
        const payload = res.data
        const text = typeof payload === 'string'
          ? payload
          : String(payload?.text ?? payload ?? '')
        return {
          ok: text.trim().length > 0,
          text,
          error: text.trim().length > 0 ? '' : '模型已返回，但内容为空',
          isEmpty: text.trim().length === 0,
          raw: payload,
        }
      }
      return {
        ok: false,
        text: '',
        error: getApiResponseMessage(res, 'AI 测试请求失败。请检查模型名称、Base URL、API Key、代理设置和服务状态，详细原因已写入系统日志。'),
        isEmpty: false,
      }
    } catch (error) {
      console.error('AI 聊天请求异常:', error)
      return {
        ok: false,
        text: '',
        error: toUserMessage(error?.message || String(error), 'AI 测试请求异常。可能是软件后端暂时不可用、网络连接失败或模型服务无响应，请稍后重试。'),
        isEmpty: false,
      }
    } finally {
      isLoading.value = false
    }
  }

  return {
    // 配置
    getAiConfig, saveAIConfig, listAiProviders,
    // 模型列表
    getAiModels, getCachedAiModels, getCachedAiModelOptions,
    // 能力与测试
    resolveAiModelCapabilities, getAiModelCapabilities, chatWithAI,
  }
}
