// -----------------------------------------------------------------
// AI 动作展示与执行运行时
// -----------------------------------------------------------------
// 这里集中处理两类问题：
// 1. 把后端动作定义翻译成前端可渲染的卡片/提示/确认文案
// 2. 把最终确认后的动作路由到具体 store 执行

// -----------------------------------------------------------------
// 基础归一化 (Normalization)
// -----------------------------------------------------------------
export const normalizeAssistantSessionResult = (rawResult = {}) => {
  /**
   * 把后端 assistant 会话返回值压成前端稳定消费的形状。
   *
   * 设计原因：
   * - 后端在流式中断、空动作、旧接口兼容场景下可能缺字段
   * - 组件层不应该到处写 `Array.isArray(...) ? ... : []` 这类兜底
   * - 因此前端统一在入口层完成一次结构归一化
   */
  const payload = rawResult && typeof rawResult === 'object' ? rawResult : {}

  return {
    ...payload,
    actions: Array.isArray(payload.actions) ? payload.actions : [],
    token_usage: payload.token_usage || null,
    message_usage: payload.message_usage || null,
    session_usage_summary: payload.session_usage_summary || null,
    analysis: String(payload.analysis ?? ''),
    reasoning_content: String(payload.reasoning_content ?? ''),
    cancelled: Boolean(payload.cancelled),
  }
}

const stringifyActionValue = (value) => {
  // 模板上下文和签名计算都需要稳定字符串视图；
  // 这里统一把数组、对象和标量收口，避免不同入口各自实现导致预览文案不一致。
  if (value == null) return ''
  if (typeof value === 'string') return value.trim()
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  if (Array.isArray(value)) {
    return value.map(item => stringifyActionValue(item)).filter(Boolean).join('、')
  }
  try {
    return JSON.stringify(value)
  } catch {
    return String(value)
  }
}

// -----------------------------------------------------------------
// 展示运行时 (Presentation Runtime)
// -----------------------------------------------------------------
export const createActionPresentationRuntime = ({
  getActionDefinition,
  getModDisplayName,
  getModPreviewData,
}) => {
  /**
   * 创建动作展示运行时。
   *
   * 这层只负责“读动作定义并生成可展示信息”，不直接执行动作。
   * 这样组件可以把文案生成、预览拆分、实体映射都委托给同一套逻辑，
   * 避免不同消息卡片或弹窗各自拼接 title/preview。
   */
  // 这层故意通过依赖注入读取定义和模组展示信息，
  // 避免 runtime 直接耦合具体 store，方便组件和测试环境复用。
  const resolveActionDefinition = (actionType) => (
    typeof getActionDefinition === 'function' ? getActionDefinition(actionType) || null : null
  )
  const resolveModDisplayName = (modId) => (
    typeof getModDisplayName === 'function' ? getModDisplayName(modId) : String(modId || '').trim()
  )
  const resolveModPreviewData = (modId) => (
    typeof getModPreviewData === 'function' ? getModPreviewData(modId) : null
  )

  const getActionType = (action) => String(action?.type || '').trim()
  const getActionVariant = (action) => String(action?.variant || '').trim()
  const getActionVariantDefinition = (action) => {
    const definition = resolveActionDefinition(getActionType(action))
    const variants = definition?.variants && typeof definition.variants === 'object' ? definition.variants : {}
    return variants[getActionVariant(action)] || null
  }
  const buildActionTemplateContext = (action, extra = {}) => {
    // 模板变量统一从这里产出，避免 preview / confirm / success 三套文案
    // 分别拼接字段后出现命名漂移。
    const payload = action?.payload && typeof action.payload === 'object' ? action.payload : {}
    const modIds = Array.isArray(payload.mod_ids) ? payload.mod_ids.map(item => String(item || '').trim()).filter(Boolean) : []
    const modId = String(payload.mod_id || '').trim()
    const targetId = String(payload.target_id || '').trim()
    const modDisplayNames = modIds.map(item => resolveModDisplayName(item))
    const baseContext = {
      type: getActionType(action),
      variant: getActionVariant(action),
      mod_ids_joined: modIds.join('、'),
      mod_ids_csv: modIds.join(', '),
      mod_ids_display_joined: modDisplayNames.join('、'),
      mod_ids_display_csv: modDisplayNames.join(', '),
      mod_ids_count: String(modIds.length),
      mod_id: modId,
      mod_id_display: modId ? resolveModDisplayName(modId) : '',
      target_id: targetId,
      target_id_display: targetId ? resolveModDisplayName(targetId) : '',
      setting_key: String(payload.setting_key || '').trim(),
      text: String(payload.text || '').trim(),
      value_json: payload.value === undefined ? '' : stringifyActionValue(payload.value),
      payload_json: stringifyActionValue(payload),
    }
    for (const [key, value] of Object.entries(payload)) {
      if (baseContext[key] !== undefined) continue
      baseContext[key] = stringifyActionValue(value)
    }
    return {
      ...baseContext,
      ...Object.fromEntries(Object.entries(extra || {}).map(([key, value]) => [key, stringifyActionValue(value)])),
    }
  }
  const formatActionTemplate = (template, action, extra = {}) => {
    /**
     * 用动作上下文填充模板字符串。
     *
     * 这里不使用更重的模板引擎，原因是动作模板只需要做
     * 轻量占位符替换；保持实现简单可以减少调试成本。
     */
    const normalizedTemplate = String(template || '').trim()
    if (!normalizedTemplate) return ''
    const context = buildActionTemplateContext(action, extra)
    return normalizedTemplate.replace(/\{([A-Za-z0-9_]+)\}/g, (_, key) => context[key] || '').trim()
  }
  const getActionMetaText = (action, field) => {
    const variantDefinition = getActionVariantDefinition(action)
    const variantValue = String(variantDefinition?.[field] || '').trim()
    if (variantValue) return variantValue
    const definition = resolveActionDefinition(getActionType(action))
    return String(definition?.[field] || '').trim()
  }
  const getActionExecuteLabel = (action) => getActionMetaText(action, 'execute_label') || getActionMetaText(action, 'label') || '执行操作'
  const getActionTitle = (action) => getActionMetaText(action, 'title') || getActionMetaText(action, 'label') || '执行操作'
  const getActionDescription = (action) => getActionMetaText(action, 'description') || '执行这条 AI 建议。'
  const getActionPreview = (action) => formatActionTemplate(getActionMetaText(action, 'preview_template'), action)
  const getActionMissingPayloadMessage = (action) => getActionMetaText(action, 'missing_payload_message') || '这条动作缺少必要字段，已跳过。'
  const getActionBlockedMessage = (action) => formatActionTemplate(getActionMetaText(action, 'blocked_message'), action)
  const getActionConfirmMeta = (action) => ({
    title: getActionMetaText(action, 'confirm_title'),
    message: formatActionTemplate(getActionMetaText(action, 'confirm_message'), action),
    confirmText: getActionMetaText(action, 'confirm_confirm_text'),
  })
  const getActionPostSuccessMeta = (action) => ({
    title: getActionMetaText(action, 'post_success_title'),
    message: formatActionTemplate(getActionMetaText(action, 'post_success_message'), action),
    confirmText: getActionMetaText(action, 'post_success_confirm_text'),
  })
  const getActionSuccessMessage = (action) => formatActionTemplate(getActionMetaText(action, 'success_message'), action)
  const getActionExecutionConfig = (action) => {
    const definition = resolveActionDefinition(getActionType(action))
    return definition?.execution_config && typeof definition.execution_config === 'object' ? definition.execution_config : {}
  }
  const getActionRenderConfig = (action) => {
    /**
     * 计算动作最终渲染配置。
     *
     * 合并顺序是“类型级默认值 -> 变体级覆写”，因为大多数动作共用
     * 一套卡片语义，只在 enable/disable 这类变体上覆盖少数字段。
     */
    const definition = resolveActionDefinition(getActionType(action))
    const baseConfig = definition?.render_config && typeof definition.render_config === 'object' ? definition.render_config : {}
    const variantDefinition = getActionVariantDefinition(action)
    const variantConfig = variantDefinition?.render_config && typeof variantDefinition.render_config === 'object'
      ? variantDefinition.render_config
      : {}
    return {
      ...baseConfig,
      ...variantConfig,
      subjects: Array.isArray(variantConfig?.subjects)
        ? variantConfig.subjects
        : (Array.isArray(baseConfig?.subjects) ? baseConfig.subjects : []),
    }
  }
  const resolveActionSubjectItems = (subjectConfig = {}, payload = {}) => {
    // 主题色、预览卡片和占位符片段都依赖“subject item”这一层抽象，
    // 这样动作模板不用直接感知模组卡片该怎么渲染。
    const payloadKey = String(subjectConfig?.payload_key || '').trim()
    if (!payloadKey) return []
    const rawValue = payload?.[payloadKey]
    const values = Array.isArray(rawValue) ? rawValue : [rawValue]
    const entityType = String(subjectConfig?.entity_type || '').trim()
    return values
      .map(item => String(item || '').trim())
      .filter(Boolean)
      .map((value, index) => {
        if (entityType === 'mod') {
          return {
            key: `${payloadKey}:${value}:${index}`,
            display: resolveModDisplayName(value),
            previewData: resolveModPreviewData(value),
            tone: String(subjectConfig?.tone || '').trim().toLowerCase(),
          }
        }
        return {
          key: `${payloadKey}:${value}:${index}`,
          display: value,
          previewData: null,
          tone: String(subjectConfig?.tone || '').trim().toLowerCase(),
        }
      })
  }
  const getActionSubjectMap = (action) => {
    const renderConfig = getActionRenderConfig(action)
    const subjectConfigs = Array.isArray(renderConfig?.subjects) ? renderConfig.subjects : []
    const payload = action?.payload && typeof action.payload === 'object' ? action.payload : {}
    return Object.fromEntries(
      subjectConfigs
        .map((subjectConfig, index) => {
          const payloadKey = String(subjectConfig?.payload_key || index).trim()
          const items = resolveActionSubjectItems(subjectConfig, payload)
          return [payloadKey, items]
        })
        .filter(([, items]) => Array.isArray(items) && items.length > 0)
    )
  }
  const getActionPreviewTemplate = (action) => getActionMetaText(action, 'preview_template')
  const getActionPreviewPlaceholderItems = (action) => {
    const subjectMap = getActionSubjectMap(action)
    return {
      mod_id_display: subjectMap.mod_id || [],
      target_id_display: subjectMap.target_id || [],
      mod_ids_display_joined: subjectMap.mod_ids || [],
    }
  }
  const getActionPreviewParts = (action) => {
    // 预览模板会被拆成“普通文本片段 + 可渲染实体片段”，
    // 这样前端既能显示自然语言，也能把模组名替换成带样式的 chip。
    const template = getActionPreviewTemplate(action)
    if (!template) return []
    const placeholderItemMap = getActionPreviewPlaceholderItems(action)
    const context = buildActionTemplateContext(action)
    const parts = []
    let lastIndex = 0
    const regex = /\{([A-Za-z0-9_]+)\}/g
    let match
    while ((match = regex.exec(template)) !== null) {
      const [rawToken, tokenName] = match
      const textSegment = template.slice(lastIndex, match.index)
      if (textSegment) {
        parts.push({
          key: `text:${lastIndex}`,
          type: 'text',
          text: textSegment.replace(/\{([A-Za-z0-9_]+)\}/g, (_, key) => context[key] || ''),
        })
      }
      const subjectItems = placeholderItemMap[tokenName]
      if (Array.isArray(subjectItems) && subjectItems.length > 0) {
        parts.push({
          key: `subject:${tokenName}:${match.index}`,
          type: 'subject',
          items: subjectItems,
        })
      } else {
        parts.push({
          key: `text:${match.index}`,
          type: 'text',
          text: String(context[tokenName] || rawToken),
        })
      }
      lastIndex = match.index + rawToken.length
    }
    const tailText = template.slice(lastIndex)
    if (tailText) {
      parts.push({
        key: `text:${lastIndex}:tail`,
        type: 'text',
        text: tailText.replace(/\{([A-Za-z0-9_]+)\}/g, (_, key) => context[key] || ''),
      })
    }
    return parts.filter(part => {
      if (part.type === 'subject') return Array.isArray(part.items) && part.items.length > 0
      return String(part.text || '').length > 0
    })
  }
  const buildRenderableActionKey = (action, suffix = '') => {
    const payloadJson = stringifyActionValue(action?.payload || {})
    return [
      getActionType(action),
      getActionVariant(action),
      payloadJson,
      suffix,
    ].filter(Boolean).join('::')
  }
  const getActionCardTone = (action) => String(getActionRenderConfig(action)?.card_tone || '').trim().toLowerCase() || 'accent'
  const expandRenderableAction = (action) => {
    const renderConfig = getActionRenderConfig(action)
    const splitPayloadListKey = String(renderConfig?.split_payload_list_key || '').trim()
    const payload = action?.payload && typeof action.payload === 'object' ? action.payload : {}
    const splitValues = splitPayloadListKey && Array.isArray(payload?.[splitPayloadListKey])
      ? payload[splitPayloadListKey].map(item => String(item || '').trim()).filter(Boolean)
      : []
    if (!splitPayloadListKey || splitValues.length <= 1) {
      return [{
        ...action,
        _renderKey: buildRenderableActionKey(action),
      }]
    }
    // 一条批量动作会被拆成多张独立卡片，原因是：
    // - 用户更容易逐条确认风险
    // - 执行失败时也能把影响范围限制在单个对象上
    return splitValues.map((value, index) => ({
      ...action,
      payload: {
        ...payload,
        [splitPayloadListKey]: [value],
      },
      _renderKey: buildRenderableActionKey(action, `${splitPayloadListKey}:${value}:${index}`),
    }))
  }
  const getRenderableActions = (message) => {
    const actions = Array.isArray(message?.actions) ? message.actions : []
    return actions.flatMap(expandRenderableAction)
  }

  return {
    getActionType,
    getActionVariant,
    buildActionTemplateContext,
    formatActionTemplate,
    getActionMetaText,
    getActionExecuteLabel,
    getActionTitle,
    getActionDescription,
    getActionPreview,
    getActionMissingPayloadMessage,
    getActionBlockedMessage,
    getActionConfirmMeta,
    getActionPostSuccessMeta,
    getActionSuccessMessage,
    getActionExecutionConfig,
    getActionRenderConfig,
    getActionPreviewParts,
    getActionCardTone,
    getRenderableActions,
  }
}

// -----------------------------------------------------------------
// 执行注册表 (Executor Registry)
// -----------------------------------------------------------------
export const createActionExecutorRegistry = ({
  modStore,
  ruleStore,
  appStore,
  confirmStore,
  toast,
  getActionVariant,
  getActionMissingPayloadMessage,
  getActionSuccessMessage,
  getActionConfirmMeta,
  getActionPostSuccessMeta,
  getActionExecutionConfig,
  getActionBlockedMessage,
  getActionPreview,
  getActionDescription,
}) => ({
  /**
   * 创建动作执行注册表。
   *
   * 每个 key 对应一种后端动作类型，真正执行时由消息卡片按
   * `type -> executor` 路由。这样比把执行逻辑直接塞进组件更容易维护：
   * - 组件只负责交互
   * - store 只负责状态变更
   * - runtime 负责把两者粘起来
   */
  async MOD_STATE(payload, action) {
    const shouldEnable = getActionVariant(action) !== 'disable'
    const modIds = Array.isArray(payload.mod_ids) ? payload.mod_ids : []
    if (modIds.length === 0) {
      toast.warning(getActionMissingPayloadMessage(action))
      return
    }
    // 默认前端会先把这类动作拆成单模组卡片；
    // 这里仍保留逐项执行兜底，避免其它入口直接执行批量 payload。
    for (const modId of modIds) {
      await modStore.changeModsActive([modId], shouldEnable)
    }
    const successMessage = getActionSuccessMessage(action)
    if (successMessage) {
      toast.success(successMessage)
    }
  },

  async MOD_RULE(payload, action) {
    /**
     * 应用一条用户规则动作。
     *
     * 规则类动作有副作用且可能影响排序，因此必须先确认，再在成功后
     * 根据后端定义决定是否追加“顺手自动排序”的二次动作。
     */
    const normalizedType = String(action?.variant || payload.rule_type || '')
    if (!payload.mod_id || !payload.target_id || !normalizedType) {
      toast.warning(getActionMissingPayloadMessage(action))
      return
    }

    const confirmMeta = getActionConfirmMeta(action)
    const confirmed = await confirmStore.confirmAction(
      confirmMeta.title || '确认执行操作',
      confirmMeta.message || getActionPreview(action) || getActionDescription(action),
      { type: 'warning', confirmText: confirmMeta.confirmText || '确认', cancelText: '取消' },
    )
    if (!confirmed) return

    await ruleStore.addUserModRule(payload.mod_id, normalizedType, payload.target_id)

    const postSuccessMeta = getActionPostSuccessMeta(action)
    if (postSuccessMeta.message && await confirmStore.confirmAction(
      postSuccessMeta.title || '操作已应用',
      postSuccessMeta.message,
      { type: 'success', confirmText: postSuccessMeta.confirmText || '确定', cancelText: '稍后' },
    )) {
      await modStore.autoSortMods()
      return
    }

    const successMessage = getActionSuccessMessage(action)
    if (successMessage && !postSuccessMeta.message) {
      toast.success(successMessage)
    }
  },

  async TEXT_TRANSFER(payload, action) {
    // 这类动作只负责把 AI 生成的可复制文本交给系统剪贴板，
    // 不参与任何本地状态变更。
    const text = String(payload.text || '').trim()
    if (!text) {
      toast.warning(getActionMissingPayloadMessage(action))
      return
    }
    await navigator.clipboard.writeText(text)
    const successMessage = getActionSuccessMessage(action)
    if (successMessage) {
      toast.success(successMessage)
    }
  },

  async SETTING_UPDATE(payload, action) {
    /**
     * 更新一条前端设置。
     *
     * 这里会额外检查 `allowed_setting_keys`，因为 AI 生成 setting_key
     * 的风险比普通按钮操作高，前端必须再做一道白名单保护。
     */
    const settingKey = String(payload.setting_key || '').trim()
    if (!settingKey) {
      toast.warning(getActionMissingPayloadMessage(action))
      return
    }
    const executionConfig = getActionExecutionConfig(action)
    const allowedSettingKeys = new Set(
      Array.isArray(executionConfig.allowed_setting_keys)
        ? executionConfig.allowed_setting_keys.map(item => String(item || '').trim()).filter(Boolean)
        : []
    )
    if (allowedSettingKeys.size > 0 && !allowedSettingKeys.has(settingKey)) {
      toast.warning(getActionBlockedMessage(action) || '当前不允许执行这条设置修改动作。')
      return
    }
    await appStore.saveSetting(settingKey, payload.value)
    const successMessage = getActionSuccessMessage(action)
    if (successMessage) {
      toast.success(successMessage)
    }
  },
})
