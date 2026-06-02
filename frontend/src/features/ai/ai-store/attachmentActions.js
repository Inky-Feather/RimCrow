import { normalizeText } from '../../../shared/lib/common'
import { cleanRichText } from '../../../shared/lib/text'
import { buildAttachmentDisplayMeta, buildDiagnosisContextAttachmentDraft } from './runtime/aiAttachmentRuntime'
import { createAttachmentDraft, normalizeTimestamp } from './factories'

export const useAttachmentActions = ({
  runtimeDefinitionEditorMeta, globalAttachmentEntries, sessionsById,
  getSession, getAssistantDefinition, getPromptDefinition,
} = {}) => {
  // -----------------------------------------------------------------
  // 附件定义与展示
  // -----------------------------------------------------------------
  const getAttachmentDefinition = (attachmentKind = '') => {
    const normalizedKind = normalizeText(attachmentKind)
    return normalizedKind ? (runtimeDefinitionEditorMeta.value?.attachments || {})[normalizedKind] || null : null
  }

  const getAttachmentDisplayMeta = (attachment) => buildAttachmentDisplayMeta(attachment, getAttachmentDefinition)

  const getSupportedAttachmentKindsForAssistant = (assistantId = '') => {
    /** 读取某个助手当前绑定 Prompt 支持的附件类型集合。 */
    const assistant = getAssistantDefinition(assistantId)
    const prompt = getPromptDefinition(assistant?.prompt_id || '')
    const attachmentKinds = Array.isArray(prompt?.attachment_kinds) ? prompt.attachment_kinds : []
    return [...new Set(attachmentKinds.map(item => normalizeText(item)).filter(Boolean))]
  }

  // -----------------------------------------------------------------
  // 附件草稿构造
  // -----------------------------------------------------------------
  const buildGlobalAttachmentEntryKey = (draft = {}) => {
    /**
     * 为全局附件生成稳定键。
     *
     * 键的目标不是绝对唯一，而是能表达“同一业务上下文的同一份附件”，
     * 便于后续 upsert 替换，而不是不断堆新条目。
     */
    const kind = normalizeText(draft?.kind)
    const source = draft?.source && typeof draft.source === 'object' ? draft.source : {}
    const identity = {
      kind,
      owner_type: normalizeText(source.owner_type),
      source_type: normalizeText(source.source_type),
      filename: normalizeText(source.filename),
      package_id: normalizeText(source.package_id),
    }
    return JSON.stringify(identity)
  }

  const buildLogOwnerKey = (sourceType = 'game', filename = '') => {
    const normalizedSourceType = normalizeText(sourceType, 'game')
    const normalizedFilename = normalizeText(filename, '__no_file__')
    return `log:${normalizedSourceType}:${normalizedFilename}`
  }

  const buildDiagnosisContextAttachment = (options = {}) => createAttachmentDraft(
    buildDiagnosisContextAttachmentDraft(options)
  )

  const normalizeModAliasTaskInputItem = (mod = {}) => {
    /** 把单个模组输入整理成别名任务可接受的最小对象。 */
    const packageId = normalizeText(mod?.package_id || mod?.packageId).toLowerCase()
    if (!packageId) return null
    return {
      package_id: packageId,
      name: normalizeText(mod?.name),
      // 这里先做一层轻量清洗，只是为了让界面状态保持稳定；
      // 真正入模前仍以后端归一化结果为准，避免两边规则漂移。
      description: cleanRichText(mod?.description, 800),
    }
  }

  const normalizeModAliasTaskInputItems = (mods = []) => {
    /** 归一化并按 package_id 去重整批别名任务输入。 */
    const itemMap = new Map()
    ;(Array.isArray(mods) ? mods : []).forEach((item) => {
      const normalized = normalizeModAliasTaskInputItem(item)
      if (!normalized?.package_id) return
      itemMap.set(normalized.package_id, normalized)
    })
    return Array.from(itemMap.values())
  }

  const buildModSelectionAttachment = ({
    mods = [], ownerType = 'task',
    mode = 'single', summary = '',
  } = {}) => {
    /**
     * 构建模组选择附件。
     *
     * 别名任务和通用助手都复用这类附件，因此这里直接把
     * package_id 列表和快照文案打包成统一协议。
     */
    const normalizedMods = (Array.isArray(mods) ? mods : [])
      .map(item => normalizeModAliasTaskInputItem(item))
      .filter(Boolean)
    const packageIds = normalizedMods.map(item => item.package_id)
    const firstPackageId = packageIds[0] || ''
    const firstName = normalizeText(normalizedMods[0]?.name, firstPackageId)
    const summaryText = normalizeText(summary) || (
      normalizedMods.length <= 1
        ? firstName
        : `已选 ${normalizedMods.length} 个模组`
    )
    return createAttachmentDraft({
      kind: 'mod_selection',
      source: { owner_type: normalizeText(ownerType, 'task'), package_id: firstPackageId },
      selector: { mode: normalizeText(mode, normalizedMods.length > 1 ? 'multiple' : 'single'), values: packageIds },
      snapshot: { summary: summaryText, mods: normalizedMods },
    })
  }

  // -----------------------------------------------------------------
  // 全局附件池
  // -----------------------------------------------------------------
  const upsertGlobalAttachmentDraft = (draft = {}, meta = {}) => {
    // 全局附件池用于在“日志面板/任务面板/助手面板”之间共享上下文，
    // 不直接挂在某条消息上，避免会话创建前就丢失用户选择态。
    const normalizedDraft = createAttachmentDraft(draft)
    const key = buildGlobalAttachmentEntryKey(normalizedDraft)
    if (!normalizeText(normalizedDraft.kind) || !key) return ''
    const now = Date.now()
    globalAttachmentEntries[key] = {
      key,
      draft: normalizedDraft,
      meta: { ...(meta || {}) },
      createdAt: normalizeTimestamp(globalAttachmentEntries[key]?.createdAt, now),
      updatedAt: now,
    }
    return key
  }

  const removeGlobalAttachmentDraft = (attachmentKey = '') => {
    const normalizedKey = normalizeText(attachmentKey)
    if (!normalizedKey || !globalAttachmentEntries[normalizedKey]) return false
    const removedEntry = globalAttachmentEntries[normalizedKey]
    delete globalAttachmentEntries[normalizedKey]
    Object.values(sessionsById).forEach((session) => {
      if (!Array.isArray(session?.dismissedAttachmentKeys)) return
      session.dismissedAttachmentKeys = session.dismissedAttachmentKeys.filter(key => key !== normalizedKey)
    })
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('ai-attachment-removed', {
        detail: { key: normalizedKey, draft: removedEntry?.draft || null, meta: removedEntry?.meta || null },
      }))
    }
    return true
  }

  const listGlobalAttachmentEntries = () => (
    Object.values(globalAttachmentEntries)
      .filter(entry => entry?.draft)
      .sort((a, b) => Number(a.createdAt || 0) - Number(b.createdAt || 0))
  )

  const removeGlobalAttachmentsByKind = (attachmentKind = '') => {
    const normalizedKind = normalizeText(attachmentKind)
    if (!normalizedKind) return []
    const removedKeys = listGlobalAttachmentEntries()
      .filter(entry => normalizeText(entry?.draft?.kind) === normalizedKind)
      .map(entry => entry.key)
    removedKeys.forEach(removeGlobalAttachmentDraft)
    return removedKeys
  }

  const replaceGlobalAttachmentsByKind = (attachmentKind = '', drafts = [], meta = {}) => {
    removeGlobalAttachmentsByKind(attachmentKind)
    return (Array.isArray(drafts) ? drafts : [])
      .map(draft => upsertGlobalAttachmentDraft(draft, meta))
      .filter(Boolean)
  }

  // -----------------------------------------------------------------
  // 会话输入框附件
  // -----------------------------------------------------------------
  const isAttachmentCompatibleWithSession = (entry = {}, session = null) => {
    const draft = entry?.draft && typeof entry.draft === 'object' ? entry.draft : {}
    const source = draft?.source && typeof draft.source === 'object' ? draft.source : {}
    if (!session) return true

    const sessionOwnerType = normalizeText(session.ownerType)
    const sessionSourceType = normalizeText(session.sourceType)
    const sessionFilename = normalizeText(session.filename)
    const attachmentOwnerType = normalizeText(source.owner_type)
    const attachmentSourceType = normalizeText(source.source_type)
    const attachmentFilename = normalizeText(source.filename)

    if (sessionOwnerType === 'log_viewer' || attachmentOwnerType === 'log_viewer') {
      if (sessionSourceType && attachmentSourceType && sessionSourceType !== attachmentSourceType) return false
      if (sessionFilename && attachmentFilename && sessionFilename !== attachmentFilename) return false
    }
    return true
  }

  const getSessionComposerAttachments = (sessionId = '', assistantId = '') => {
    const session = getSession(sessionId)
    const dismissedKeys = new Set(Array.isArray(session?.dismissedAttachmentKeys) ? session.dismissedAttachmentKeys : [])
    const supportedKinds = new Set(getSupportedAttachmentKindsForAssistant(assistantId))
    return listGlobalAttachmentEntries()
      .filter(entry => supportedKinds.has(normalizeText(entry?.draft?.kind)))
      .filter(entry => !dismissedKeys.has(entry.key))
      .filter(entry => isAttachmentCompatibleWithSession(entry, session))
  }

  const dismissSessionAttachment = (sessionId = '', attachmentKey = '') => {
    const session = getSession(sessionId)
    const normalizedKey = normalizeText(attachmentKey)
    if (!session || !normalizedKey) return null
    const next = new Set(Array.isArray(session.dismissedAttachmentKeys) ? session.dismissedAttachmentKeys : [])
    next.add(normalizedKey)
    session.dismissedAttachmentKeys = [...next]
    session.updatedAt = Date.now()
    return session
  }

  const resetSessionDismissedAttachments = (sessionId = '') => {
    const session = getSession(sessionId)
    if (!session) return null
    session.dismissedAttachmentKeys = []
    session.updatedAt = Date.now()
    return session
  }

  const removeComposerAttachment = (sessionId = '', attachmentKey = '') => {
    // 日志来源的 diagnosis_context 属于“共享附件”，移除时需要真的删掉草稿；
    // 其它附件默认只做当前会话级 dismiss，避免误伤别的入口。
    const normalizedKey = normalizeText(attachmentKey)
    if (!normalizedKey) return false
    const attachmentEntry = globalAttachmentEntries[normalizedKey]
    const attachmentKind = normalizeText(attachmentEntry?.draft?.kind)
    const attachmentOwnerType = normalizeText(attachmentEntry?.draft?.source?.owner_type)
    if (attachmentKind === 'diagnosis_context' && attachmentOwnerType === 'log_viewer') {
      return removeGlobalAttachmentDraft(normalizedKey)
    }
    return !!dismissSessionAttachment(sessionId, normalizedKey)
  }

  return {
    // 附件定义与展示
    getAttachmentDefinition, getAttachmentDisplayMeta, getSupportedAttachmentKindsForAssistant,
    // 附件草稿构造
    buildLogOwnerKey, buildDiagnosisContextAttachment, buildModSelectionAttachment, normalizeModAliasTaskInputItems,
    // 全局附件池
    upsertGlobalAttachmentDraft, removeGlobalAttachmentDraft, removeGlobalAttachmentsByKind, listGlobalAttachmentEntries, replaceGlobalAttachmentsByKind,
    // 会话输入框附件
    getSessionComposerAttachments, removeComposerAttachment, dismissSessionAttachment, resetSessionDismissedAttachments,
  }
}
