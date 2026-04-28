import { defineStore } from 'pinia'
import { computed, reactive, ref } from 'vue'
import { createToastInterface } from 'vue-toastification'
import { useAppStore } from './appStore'
import { useModStore } from './modStore'
import { useProfileStore } from './profileStore'
import { ISSUE_TYPE } from '../utils/constants'
import { dedupeNormalizedPackageIds, mapUniqueDisplayNames, normalizePackageId, pushUnique } from '../utils/modIdentity'
import { DEFAULT_TOOL_PACKAGE_IDS, isCorePackageId, isOfficialDlcPackageId } from '../utils/packageScope'
import { getVersionInfo as getVersionInfoByVersions, normalizeVersion } from '../utils/versioning'

const CATEGORY_ORDER = [
  'core',
  'official_dlc',
  'tool_mod',
  'dependency',
  'language_pack',
]

const CATEGORY_META = {
  core: {
    title: 'Core',
    description: '游戏核心模组。缺失时建议优先补齐。',
    severity: 'required',
  },
  official_dlc: {
    title: '官方 DLC',
    description: '当前序列引用了未启用的官方扩展。',
    severity: 'required',
  },
  tool_mod: {
    title: '辅助工具',
    description: '当前设置允许的工具模组未启用。',
    severity: 'required',
  },
  dependency: {
    title: '依赖项',
    description: '这些模组是当前序列或补充候选的前置依赖。',
    severity: 'required',
  },
  language_pack: {
    title: '语言包',
    description: '当前语言存在可用但未启用的语言包。',
    severity: 'optional',
  },
}

const SEVERITY_META = {
  required: {
    tone: 'danger',
    label: '必需',
  },
  optional: {
    tone: 'warn',
    label: '可选',
  },
}

const dedupeValues = (values = []) => [...new Set((values || []).filter(Boolean))]
const isLanguagePackMod = (mod) => (mod?.user_mod_type || mod?.mod_type) === 'LanguagePack'

const clearReactiveObject = (target) => {
  Object.keys(target).forEach(key => {
    delete target[key]
  })
}

const uniquePush = pushUnique

const mergeText = (...values) => [...new Set(
  values
    .flatMap(value => String(value || '').split('；'))
    .map(value => value.trim())
    .filter(Boolean)
)].join('；')

const getResolvedLanguagePackOwnerIds = (mod) => (
  [...new Set(
    (mod?.language_pack_owner_result?.owners || [])
      .map(owner => normalizePackageId(owner?.package_id))
      .filter(Boolean)
  )]
)
const canUseLanguagePackForSupplement = (mod) => {
  const confidence = String(mod?.language_pack_owner_result?.summary_confidence || '').trim().toLowerCase()
  return confidence === 'high' || confidence === 'medium'
}
const isLanguagePackDeclaredForCurrentLanguage = (mod, targetLanguage) => (
  (mod?.supported_languages || []).includes(String(targetLanguage || '').trim())
)
const isIssueIgnored = (mod, issueType = '') => (
  !!issueType && Array.isArray(mod?.ignored_issues) && mod.ignored_issues.includes(issueType)
)

const listOwnerNames = (owners = [], modStore) => (
  mapUniqueDisplayNames(owners, ownerId => modStore.displayModName(ownerId))
)

const compareCategory = (left = '', right = '') => (
  CATEGORY_ORDER.indexOf(left) - CATEGORY_ORDER.indexOf(right)
)

const pickPreferredCategory = (left = '', right = '') => {
  if (!left) return right
  if (!right) return left
  return compareCategory(left, right) <= 0 ? left : right
}

const pickPreferredSeverity = (left = 'optional', right = 'optional') => (
  left === 'required' || right === 'required' ? 'required' : 'optional'
)

const normalizeSelectionMode = (value = 'all') => {
  const normalized = String(value || '').trim().toLowerCase()
  return ['all', 'required', 'none', 'custom'].includes(normalized) ? normalized : 'all'
}

const sortRows = (rows = []) => (
  [...rows].sort((left, right) => {
    const categoryDiff = compareCategory(left.category, right.category)
    if (categoryDiff !== 0) return categoryDiff
    return String(left.title || '').localeCompare(String(right.title || ''))
  })
)

export const useSupplementStore = defineStore('supplement', () => {
  const toast = createToastInterface()
  const appStore = useAppStore()
  const modStore = useModStore()
  const profileStore = useProfileStore()

  const isVisible = ref(false)
  const state = reactive({
    title: '',
    message: '',
    confirmText: '应用选中项',
    cancelText: '取消',
    continueText: '',
    groups: [],
    summary: {
      count: 0,
      requiredCount: 0,
      optionalCount: 0,
      urgency: 'none',
    },
  })

  const toggleSelections = reactive({})
  const choiceSelections = reactive({})

  let resolvePromise = null

  const currentGameVersion = computed(() => normalizeVersion(profileStore.activeContext?.game_version))
  const currentLanguage = computed(() => String(appStore.settings?.language || '').trim())
  const visibleRows = computed(() => state.groups.flatMap(group => group.rows || []))

  // 统一计算版本兼容状态，供替代模组排序和界面标签复用。
  const getVersionInfo = (packageId = '') => {
    const mod = modStore.takeModById(packageId)
    if (!mod || mod.isMissing) return getVersionInfoByVersions(currentGameVersion.value)
    const versions = dedupeNormalizedPackageIds((mod.supported_versions || []).map(value => normalizeVersion(value)))
    return getVersionInfoByVersions(currentGameVersion.value, versions)
  }

  // 统一复用后端的 language_pack_owner_result。
  // strictTargetMap: 语言包明确声明支持当前语言
  // fallbackTargetMap: 归属可信，但语言作者可能漏标 supported_languages
  const getLanguagePackTargetMap = () => {
    const strictTargetMap = new Map()
    const fallbackTargetMap = new Map()
    if (!appStore.settings.check_language_support || !currentLanguage.value) {
      return { strictTargetMap, fallbackTargetMap }
    }
    for (const mod of modStore.allModsMap.values()) {
      if (!mod || mod.isMissing || !mod.path || !isLanguagePackMod(mod)) continue
      if (!canUseLanguagePackForSupplement(mod)) continue
      const relatedTargets = new Set(getResolvedLanguagePackOwnerIds(mod))
      const supportsCurrentLanguage = isLanguagePackDeclaredForCurrentLanguage(mod, currentLanguage.value)
      relatedTargets.forEach(targetId => {
        if (!targetId) return
        const targetMap = supportsCurrentLanguage ? strictTargetMap : fallbackTargetMap
        if (!targetMap.has(targetId)) targetMap.set(targetId, [])
        targetMap.get(targetId).push(mod)
      })
    }
    return { strictTargetMap, fallbackTargetMap }
  }

  // ctx 是一次补缺计算共享的只读上下文，递归构图时都复用这一份派生数据。
  const createContext = (activeIds = modStore.activeIds) => {
    const normalizedActiveIds = dedupeNormalizedPackageIds(activeIds)
    return {
      activeIds: normalizedActiveIds,
      activeSet: new Set(normalizedActiveIds),
      ...getLanguagePackTargetMap(),
    }
  }

  const buildOwnersDetail = (owners = [], suffix = '') => {
    const ownerNames = listOwnerNames(owners, modStore)
    if (ownerNames.length === 0) return suffix
    const joined = ownerNames.join('、')
    return suffix ? `${joined}${suffix}` : joined
  }

  // 这里只收集“候选条目”，不直接决定是否显示或启用。
  // satisfiedSet 表示当前路径已满足的包，trailSet 用于阻断递归回环。
  const collectDependencyEntries = (ownerIds = [], ctx, satisfiedSet = ctx.activeSet, trailSet = new Set()) => {
    const entryMap = new Map()

    ownerIds.forEach(ownerId => {
      const owner = modStore.takeModById(ownerId)
      if (!owner) return
      if (isIssueIgnored(owner, ISSUE_TYPE.ERROR_INACTIVE_DEPENDENCY)) return
      ;(owner.rules?.dependencies || []).forEach(rule => {
        const targetId = normalizePackageId(rule?.target_id)
        if (!targetId) return
        const alternativeIds = dedupeNormalizedPackageIds(rule?.alternatives || [])
        const optionIds = dedupeNormalizedPackageIds([targetId, ...alternativeIds]).filter(optionId => !trailSet.has(optionId))
        if (optionIds.length === 0) return
        if (optionIds.some(optionId => satisfiedSet.has(optionId))) return

        const installedOptionIds = optionIds.filter(optionId => modStore.hasRealModById(optionId))
        if (installedOptionIds.length === 0) return
        const category = isCorePackageId(targetId)
          ? 'core'
          : isOfficialDlcPackageId(targetId)
            ? 'official_dlc'
            : 'dependency'

        const key = `dependency:${targetId}:${installedOptionIds.join('|')}`
        if (!entryMap.has(key)) {
          const onlyOptionId = installedOptionIds.length === 1 ? installedOptionIds[0] : ''
          const usesAlternativeOnly = !!onlyOptionId && onlyOptionId !== targetId
          entryMap.set(key, {
            entryType: installedOptionIds.length > 1 ? 'choice' : 'toggle',
            key,
            category,
            severity: CATEGORY_META[category]?.severity || 'required',
            title: usesAlternativeOnly ? modStore.displayModName(onlyOptionId) : modStore.displayModName(targetId),
            reason: '',
            detail: '',
            owners: [],
            packageId: onlyOptionId,
            removeIds: [],
            relationLabel: usesAlternativeOnly ? '备选依赖' : '依赖',
            allowSkip: true,
            defaultOptionPackageId: installedOptionIds.includes(targetId) ? targetId : installedOptionIds[0],
            options: installedOptionIds.map(optionId => ({
              packageId: optionId,
              title: modStore.displayModName(optionId),
              detail: optionId === targetId ? '原始依赖项' : '可用于满足依赖的备选模组',
              removeIds: [],
              relationLabel: optionId === targetId ? '依赖' : '备选依赖',
            })),
            hasAlternatives: alternativeIds.length > 0,
          })
        }
        uniquePush(entryMap.get(key).owners, ownerId)
      })
    })

    return Array.from(entryMap.values()).map(entry => {
      const ownerCount = entry.owners.length
      const ownerDetail = buildOwnersDetail(entry.owners, ownerCount > 0 ? ' 的依赖' : '依赖')
      return {
        ...entry,
        reason: ownerCount > 1 ? `被 ${ownerCount} 个模组同时依赖` : '当前序列缺少依赖项',
        detail: ownerDetail,
      }
    })
  }

  // 语言包补缺与“问题提示”保持同一口径：
  // 仅当原模组不支持当前语言、且当前路径上没有已满足的对应语言包时，才补出首个候选语言包。
  const collectLanguageEntries = (ownerIds = [], ctx, satisfiedSet = ctx.activeSet, trailSet = new Set()) => {
    if (!appStore.settings.check_language_support || !currentLanguage.value) return []
    const entryMap = new Map()

    ownerIds.forEach(ownerId => {
      const owner = modStore.takeModById(ownerId)
      if (!owner) return
      if (isIssueIgnored(owner, ISSUE_TYPE.WARN_INACTIVE_LANGUAGE_PACK)) return
      const supportedLanguages = owner.supported_languages || []
      if (supportedLanguages.length === 0) return
      if (supportedLanguages.includes(currentLanguage.value)) return
      const allStrictCandidates = (ctx.strictTargetMap.get(normalizePackageId(ownerId)) || [])
      const allFallbackCandidates = (ctx.fallbackTargetMap.get(normalizePackageId(ownerId)) || [])
      const hasSatisfiedCandidate = [...allStrictCandidates, ...allFallbackCandidates].some(candidate => {
        const candidateId = normalizePackageId(candidate?.package_id)
        return !!candidateId && satisfiedSet.has(candidateId)
      })
      if (hasSatisfiedCandidate) return

      const strictCandidates = allStrictCandidates
        .filter(candidate => {
          const candidateId = normalizePackageId(candidate?.package_id)
          return !!candidateId
            && !candidate?.isMissing
            && !!candidate?.path
            && !satisfiedSet.has(candidateId)
            && !trailSet.has(candidateId)
        })
      const fallbackCandidates = allFallbackCandidates
        .filter(candidate => {
          const candidateId = normalizePackageId(candidate?.package_id)
          return !!candidateId
            && !candidate?.isMissing
            && !!candidate?.path
            && !satisfiedSet.has(candidateId)
            && !trailSet.has(candidateId)
        })
      const candidate = strictCandidates[0] || fallbackCandidates[0]
      if (!candidate) return

      const candidateId = normalizePackageId(candidate.package_id)
      const key = `language:${candidateId}`
      if (!entryMap.has(key)) {
        const isFallback = strictCandidates.length === 0
        entryMap.set(key, {
          entryType: 'toggle',
          key,
          category: 'language_pack',
          severity: isFallback ? 'optional' : 'optional',
          title: modStore.displayModName(candidate),
          reason: '',
          detail: '',
          owners: [],
          packageId: candidateId,
          removeIds: [],
          relationLabel: '语言包',
          isLanguageFallback: isFallback,
        })
      }
      uniquePush(entryMap.get(key).owners, ownerId)
    })

    return Array.from(entryMap.values()).map(entry => {
      const ownerCount = entry.owners.length
      return {
        ...entry,
        reason: ownerCount > 1 ? `可为 ${ownerCount} 个模组提供当前语言支持` : '可补充当前语言包',
        detail: entry.isLanguageFallback
          ? mergeText(buildOwnersDetail(entry.owners, ' 的可能相关语言包'), '该语言包未声明支持当前语言')
          : buildOwnersDetail(entry.owners, ' 的语言包'),
      }
    })
  }

  // 根候选只负责当前启用列表里直接可见的缺口，链式补充在后续构图阶段递归展开。
  const collectRootEntries = (ctx) => {
    const entries = []

    if (modStore.hasRealModById('ludeon.rimworld') && !ctx.activeSet.has('ludeon.rimworld')) {
      entries.push({
        entryType: 'toggle',
        key: 'core:ludeon.rimworld',
        category: 'core',
        severity: 'required',
        title: modStore.displayModName('ludeon.rimworld'),
        reason: '当前启用序列缺少 Core',
        detail: '保存或启动游戏前建议补齐。',
        owners: [],
        packageId: 'ludeon.rimworld',
        removeIds: [],
        relationLabel: 'Core',
      })
    }

    if (appStore.settings.enable_tool_mods) {
      DEFAULT_TOOL_PACKAGE_IDS.forEach(toolId => {
        if (!modStore.hasRealModById(toolId) || ctx.activeSet.has(toolId)) return
        entries.push({
          entryType: 'toggle',
          key: `tool:${toolId}`,
          category: 'tool_mod',
          severity: 'required',
          title: modStore.displayModName(toolId),
          reason: '当前设置启用了工具模组支持',
          detail: '工具模组已安装但未启用。',
          owners: [],
          packageId: toolId,
          removeIds: [],
          relationLabel: '工具',
        })
      })
    }

    entries.push(...collectDependencyEntries(ctx.activeIds, ctx, ctx.activeSet, new Set()))
    entries.push(...collectLanguageEntries(ctx.activeIds, ctx, ctx.activeSet, new Set()))

    return entries
  }

  const graphState = ref(null)
  const toggleOverrides = reactive({})
  const choiceOverrides = reactive({})
  const defaultSelectionMode = ref('all')

  // choice option 需要跨不同来源合并，这里先统一成标准结构。
  const createChoiceOption = (rowId, option = {}) => {
    const packageId = normalizePackageId(option.packageId)
    return {
      id: `${rowId}:${packageId}`,
      packageId,
      title: option.title || modStore.displayModName(packageId),
      detail: option.detail || '',
      removeIds: dedupeNormalizedPackageIds(option.removeIds || []),
      relationLabel: option.relationLabel || '',
      relationLabels: option.relationLabel ? [option.relationLabel] : [],
      versionInfo: getVersionInfo(packageId),
    }
  }

  // 同一 option 可能被多条路径引用，按 packageId 合并后再用于平面展示。
  const mergeChoiceOptions = (currentOptions = [], incomingOptions = [], rowId) => {
    const optionMap = new Map(currentOptions.map(option => [option.packageId, { ...option }]))
    ;(incomingOptions || []).forEach(option => {
      const nextOption = createChoiceOption(rowId, option)
      const currentOption = optionMap.get(nextOption.packageId)
      if (!currentOption) {
        optionMap.set(nextOption.packageId, nextOption)
        return
      }
      currentOption.title = currentOption.title || nextOption.title
      currentOption.detail = mergeText(currentOption.detail, nextOption.detail)
      currentOption.removeIds = dedupeNormalizedPackageIds([...currentOption.removeIds, ...nextOption.removeIds])
      currentOption.relationLabel = currentOption.relationLabel || nextOption.relationLabel
      currentOption.relationLabels = dedupeValues([...currentOption.relationLabels, ...nextOption.relationLabels])
      currentOption.versionInfo = currentOption.versionInfo?.tone === 'success' ? currentOption.versionInfo : nextOption.versionInfo
    })
    return Array.from(optionMap.values()).sort((left, right) => String(left.title || '').localeCompare(String(right.title || '')))
  }

  const createEmptySummary = () => ({
    count: 0,
    requiredCount: 0,
    optionalCount: 0,
    urgency: 'none',
  })

  // 图节点不是最终 UI 行；这里把节点转成可合并的平面行结构。
  const createToggleRow = (node) => ({
    id: node.rowId,
    kind: 'toggle',
    category: node.category,
    severity: node.severity || 'optional',
    packageId: node.packageId,
    title: node.title || modStore.displayModName(node.packageId),
    reason: node.reason || '',
    detail: node.detail || '',
    owners: dedupeNormalizedPackageIds(node.owners || []),
    removeIds: dedupeNormalizedPackageIds(node.removeIds || []),
    relationLabel: node.relationLabel || '',
    relationLabels: node.relationLabel ? [node.relationLabel] : [],
    versionInfo: node.versionInfo || getVersionInfo(node.packageId),
  })

  const createChoiceRow = (node) => ({
    id: node.rowId,
    kind: 'choice',
    category: node.category,
    severity: node.severity || 'optional',
    title: node.title || '',
    reason: node.reason || '',
    detail: node.detail || '',
    owners: dedupeNormalizedPackageIds(node.owners || []),
    allowSkip: node.allowSkip !== false,
    options: mergeChoiceOptions([], node.options || [], node.rowId),
    defaultOptionId: node.defaultOptionId || '',
  })

  // rowCatalog 用来把内部递归图投影成“去重后的平面行目录”。
  const mergeRowFromNode = (catalog, node) => {
    if (node.kind === 'choice') {
      const currentRow = catalog.get(node.rowId)
      if (!currentRow) {
        catalog.set(node.rowId, createChoiceRow(node))
        return
      }
      currentRow.category = pickPreferredCategory(currentRow.category, node.category)
      currentRow.severity = pickPreferredSeverity(currentRow.severity, node.severity)
      currentRow.title = currentRow.title || node.title || ''
      currentRow.reason = mergeText(currentRow.reason, node.reason)
      currentRow.detail = mergeText(currentRow.detail, node.detail)
      currentRow.owners = dedupeNormalizedPackageIds([...currentRow.owners, ...(node.owners || [])])
      currentRow.allowSkip = currentRow.allowSkip && node.allowSkip !== false
      currentRow.options = mergeChoiceOptions(currentRow.options, node.options || [], node.rowId)
      const preferredOption = currentRow.options.find(option => option.id === node.defaultOptionId) || currentRow.options[0]
      currentRow.defaultOptionId = preferredOption?.id || currentRow.defaultOptionId || ''
      return
    }

    const currentRow = catalog.get(node.rowId)
    if (!currentRow) {
      catalog.set(node.rowId, createToggleRow(node))
      return
    }
    currentRow.category = pickPreferredCategory(currentRow.category, node.category)
    currentRow.severity = pickPreferredSeverity(currentRow.severity, node.severity)
    currentRow.title = currentRow.title || node.title || modStore.displayModName(node.packageId)
    currentRow.reason = mergeText(currentRow.reason, node.reason)
    currentRow.detail = mergeText(currentRow.detail, node.detail)
    currentRow.owners = dedupeNormalizedPackageIds([...currentRow.owners, ...(node.owners || [])])
    currentRow.removeIds = dedupeNormalizedPackageIds([...currentRow.removeIds, ...(node.removeIds || [])])
    currentRow.relationLabels = dedupeValues([...currentRow.relationLabels, ...(node.relationLabel ? [node.relationLabel] : [])])
    currentRow.relationLabel = currentRow.relationLabels[0] || ''
    currentRow.versionInfo = currentRow.versionInfo?.tone === 'success' ? currentRow.versionInfo : node.versionInfo
  }

  const cloneRow = (row) => {
    if (!row) return null
    if (row.kind === 'choice') {
      return {
        ...row,
        owners: [...(row.owners || [])],
        options: (row.options || []).map(option => ({
          ...option,
          removeIds: [...(option.removeIds || [])],
          relationLabels: [...(option.relationLabels || [])],
        })),
      }
    }
    return {
      ...row,
      owners: [...(row.owners || [])],
      removeIds: [...(row.removeIds || [])],
      relationLabels: [...(row.relationLabels || [])],
    }
  }

  // UI 仍按类别分组，但数据来源是闭包求解后的平面行结果。
  const buildGroupsFromRows = (rows = []) => {
    const groups = CATEGORY_ORDER
      .map(category => {
        const groupRows = rows.filter(row => row.category === category)
        if (groupRows.length === 0) return null
        return {
          key: category,
          title: CATEGORY_META[category]?.title || category,
          description: CATEGORY_META[category]?.description || '',
          severity: CATEGORY_META[category]?.severity || 'optional',
          rows: sortRows(groupRows),
        }
      })
      .filter(Boolean)

    const count = rows.length
    const requiredCount = rows.filter(row => row.severity === 'required').length
    const optionalCount = count - requiredCount

    return {
      groups,
      summary: {
        count,
        requiredCount,
        optionalCount,
        urgency: requiredCount > 0 ? 'danger' : count > 0 ? 'warn' : 'none',
      },
    }
  }

  const getDefaultToggleSelection = (row, mode = defaultSelectionMode.value) => {
    const normalizedMode = normalizeSelectionMode(mode)
    if (normalizedMode === 'none') return false
    if (normalizedMode === 'required') return row?.severity === 'required'
    return true
  }

  const getDefaultChoiceSelection = (row, mode = defaultSelectionMode.value) => {
    const normalizedMode = normalizeSelectionMode(mode)
    if (normalizedMode === 'none') return ''
    if (normalizedMode === 'required' && row?.severity !== 'required') return ''
    return row?.defaultOptionId || ''
  }

  // 核心设计：先完整构图，再从图里按当前选择求闭包。
  // 这样可以一次拿到整条补缺链，不会出现“补一次再补一次”。
  const buildSupplementGraph = (activeIds = modStore.activeIds) => {
    const ctx = createContext(activeIds)
    const nodes = new Map()
    const rowCatalog = new Map()
    const sequenceRef = { value: 0 }

    const nextNodeId = (prefix = 'node') => {
      sequenceRef.value += 1
      return `${prefix}:${sequenceRef.value}`
    }

    // satisfiedSet 会随着当前路径假定启用的包逐层扩展，
    // 因此新补进来的依赖也会继续触发自己的依赖和语言包检查。
    const buildNode = (entry, satisfiedSet = ctx.activeSet, trailSet = new Set()) => {
      if (!entry) return null

      if (entry.entryType === 'choice') {
        const rowId = entry.key
        const options = (entry.options || []).map(option => {
          const packageId = normalizePackageId(option.packageId)
          const nextTrailSet = new Set([...Array.from(trailSet), packageId])
          const nextSatisfiedSet = new Set([...Array.from(satisfiedSet), packageId])
          const childEntries = [
            ...collectDependencyEntries([packageId], ctx, nextSatisfiedSet, nextTrailSet),
            ...collectLanguageEntries([packageId], ctx, nextSatisfiedSet, nextTrailSet),
          ]
          const childNodeIds = childEntries
            .map(childEntry => buildNode(childEntry, nextSatisfiedSet, nextTrailSet))
            .filter(Boolean)

          return {
            id: `${rowId}:${packageId}`,
            packageId,
            title: option.title || modStore.displayModName(packageId),
            detail: option.detail || '',
            removeIds: dedupeNormalizedPackageIds(option.removeIds || []),
            relationLabel: option.relationLabel || '',
            relationLabels: option.relationLabel ? [option.relationLabel] : [],
            versionInfo: getVersionInfo(packageId),
            childNodeIds,
          }
        })

        const preferredPackageId = normalizePackageId(entry.defaultOptionPackageId)
        const preferredOption = options.find(option => option.packageId === preferredPackageId) || options[0]
        const node = {
          id: nextNodeId('choice'),
          rowId,
          kind: 'choice',
          category: entry.category,
          severity: entry.severity || 'optional',
          title: entry.title || '',
          reason: entry.reason || '',
          detail: entry.detail || '',
          owners: dedupeNormalizedPackageIds(entry.owners || []),
          allowSkip: entry.allowSkip !== false,
          options,
          defaultOptionId: preferredOption?.id || '',
        }
        nodes.set(node.id, node)
        mergeRowFromNode(rowCatalog, node)
        return node.id
      }

      const packageId = normalizePackageId(entry.packageId)
      if (!packageId) return null
      const rowId = `toggle:${packageId}`
      const nextTrailSet = new Set([...Array.from(trailSet), packageId])
      const nextSatisfiedSet = new Set([...Array.from(satisfiedSet), packageId])
      const childEntries = [
        ...collectDependencyEntries([packageId], ctx, nextSatisfiedSet, nextTrailSet),
        ...collectLanguageEntries([packageId], ctx, nextSatisfiedSet, nextTrailSet),
      ]
      const childNodeIds = childEntries
        .map(childEntry => buildNode(childEntry, nextSatisfiedSet, nextTrailSet))
        .filter(Boolean)

      const node = {
        id: nextNodeId('toggle'),
        rowId,
        kind: 'toggle',
        category: entry.category,
        severity: entry.severity || 'optional',
        packageId,
        title: entry.title || modStore.displayModName(packageId),
        reason: entry.reason || '',
        detail: entry.detail || '',
        owners: dedupeNormalizedPackageIds(entry.owners || []),
        removeIds: dedupeNormalizedPackageIds(entry.removeIds || []),
        relationLabel: entry.relationLabel || '',
        versionInfo: getVersionInfo(packageId),
        childNodeIds,
      }
      nodes.set(node.id, node)
      mergeRowFromNode(rowCatalog, node)
      return node.id
    }

    const rootNodeIds = collectRootEntries(ctx)
      .map(entry => buildNode(entry, ctx.activeSet, new Set()))
      .filter(Boolean)

    return {
      nodes,
      rowCatalog,
      rootNodeIds,
    }
  }

  // 用户交互只记录 override，真实可见项与最终 payload 每次都重新从图里求解。
  const applySelectionDefaults = (rowId, row) => {
    if (row.kind === 'choice') {
      if (Object.prototype.hasOwnProperty.call(choiceOverrides, rowId)) {
        return choiceOverrides[rowId] || ''
      }
      return getDefaultChoiceSelection(row, defaultSelectionMode.value)
    }
    if (Object.prototype.hasOwnProperty.call(toggleOverrides, rowId)) {
      return !!toggleOverrides[rowId]
    }
    return getDefaultToggleSelection(row, defaultSelectionMode.value)
  }

  // 闭包求解同时完成两件事：
  // 1. 计算当前应显示的平面列表
  // 2. 汇总最终 add/remove 的 packageId 载荷
  const resolveSelectionClosure = (graph) => {
    if (!graph) {
      return {
        rows: [],
        toggleState: {},
        choiceState: {},
        payload: { addIds: [], removeIds: [] },
      }
    }

    const visibleRowMap = new Map()
    const toggleState = {}
    const choiceState = {}
    const addIds = []
    const removeIds = []

    const ensureVisibleRow = (rowId) => {
      if (visibleRowMap.has(rowId)) return visibleRowMap.get(rowId)
      const baseRow = cloneRow(graph.rowCatalog.get(rowId))
      if (!baseRow) return null
      visibleRowMap.set(rowId, baseRow)
      return baseRow
    }

    const traverseNode = (nodeId) => {
      const node = graph.nodes.get(nodeId)
      if (!node) return
      const row = ensureVisibleRow(node.rowId)
      if (!row) return

      if (node.kind === 'choice') {
        const selectedOptionId = applySelectionDefaults(node.rowId, row)
        choiceState[node.rowId] = selectedOptionId
        const selectedOption = (node.options || []).find(option => option.id === selectedOptionId)
        if (!selectedOption) return
        uniquePush(addIds, selectedOption.packageId)
        ;(selectedOption.removeIds || []).forEach(removeId => uniquePush(removeIds, removeId))
        ;(selectedOption.childNodeIds || []).forEach(traverseNode)
        return
      }

      const checked = applySelectionDefaults(node.rowId, row)
      toggleState[node.rowId] = checked
      if (!checked) return
      uniquePush(addIds, node.packageId)
      ;(node.removeIds || []).forEach(removeId => uniquePush(removeIds, removeId))
      ;(node.childNodeIds || []).forEach(traverseNode)
    }

    ;(graph.rootNodeIds || []).forEach(traverseNode)

    return {
      rows: sortRows(Array.from(visibleRowMap.values())),
      toggleState,
      choiceState,
      payload: {
        addIds,
        removeIds: removeIds.filter(removeId => !addIds.includes(removeId)),
      },
    }
  }

  // UI 使用的是分组平面计划，而不是内部节点结构。
  const resolveProjectedPlan = (graph) => {
    const closure = resolveSelectionClosure(graph)
    return {
      ...buildGroupsFromRows(closure.rows),
      toggleState: closure.toggleState,
      choiceState: closure.choiceState,
      payload: closure.payload,
    }
  }

  // 这是直接绑定到界面的派生选择状态，每次重算计划时整体替换。
  const replaceSelectionState = (toggleState = {}, choiceState = {}) => {
    clearReactiveObject(toggleSelections)
    clearReactiveObject(choiceSelections)
    Object.entries(toggleState).forEach(([key, value]) => {
      toggleSelections[key] = !!value
    })
    Object.entries(choiceState).forEach(([key, value]) => {
      choiceSelections[key] = value || ''
    })
  }

  // 打开弹窗时只灌入预先算好的结果，不在这里再做业务判断。
  const applyResolvedPlan = (plan, {
    title = '',
    message = '',
    confirmText = '应用选中项',
    cancelText = '取消',
    continueText = '',
  } = {}) => {
    state.title = title
    state.message = message
    state.confirmText = confirmText
    state.cancelText = cancelText
    state.continueText = continueText
    state.groups = plan.groups || []
    state.summary = plan.summary || createEmptySummary()
    replaceSelectionState(plan.toggleState || {}, plan.choiceState || {})
  }

  const clearSelectionOverrides = () => {
    clearReactiveObject(toggleOverrides)
    clearReactiveObject(choiceOverrides)
  }

  const resetDialogState = () => {
    state.title = ''
    state.message = ''
    state.confirmText = '应用选中项'
    state.cancelText = '取消'
    state.continueText = ''
    state.groups = []
    state.summary = createEmptySummary()
    graphState.value = null
    defaultSelectionMode.value = 'all'
    clearReactiveObject(toggleSelections)
    clearReactiveObject(choiceSelections)
    clearSelectionOverrides()
  }

  // 每次切换勾选后都重新投影一次计划，确保父子联动始终一致。
  const rebuildVisiblePlan = () => {
    const plan = resolveProjectedPlan(graphState.value)
    state.groups = plan.groups || []
    state.summary = plan.summary || createEmptySummary()
    replaceSelectionState(plan.toggleState || {}, plan.choiceState || {})
  }

  // 摘要同样走完整闭包流程，避免和弹窗实际看到的建议数量不一致。
  const buildSummary = (activeIds = modStore.activeIds) => {
    const graph = buildSupplementGraph(activeIds)
    const closure = resolveSelectionClosure(graph)
    return buildGroupsFromRows(closure.rows)
  }

  const collectSelectionPayload = () => resolveSelectionClosure(graphState.value).payload

  // 补齐窗口只处理“已安装但未启用”的候选，不再混入缺失/替代分析。
  const prepareDialogPlan = async (activeIds = modStore.activeIds) => {
    const graph = buildSupplementGraph(activeIds)
    const plan = resolveProjectedPlan(graph)
    return { graph, plan }
  }

  // prepared 允许外部复用同一份预计算结果，减少重复构图与闭包求解。
  const openPreparedPlan = async ({
    activeIds = modStore.activeIds,
    title = '启用建议',
    message = '',
    confirmText = '启用选中项',
    cancelText = '取消',
    continueText = '',
    prepared = null,
  } = {}) => {
    resetDialogState()
    defaultSelectionMode.value = 'all'
    const resolvedActiveIds = dedupeNormalizedPackageIds(activeIds)
    const resolvedPrepared = prepared || await prepareDialogPlan(resolvedActiveIds)
    graphState.value = resolvedPrepared.graph
    applyResolvedPlan(resolvedPrepared.plan, { title, message, confirmText, cancelText, continueText })
    isVisible.value = true
    return new Promise(resolve => {
      resolvePromise = resolve
    })
  }

  const cancel = () => {
    isVisible.value = false
    resolvePromise?.(null)
    resolvePromise = null
  }

  const confirm = () => {
    const payload = collectSelectionPayload()
    isVisible.value = false
    resolvePromise?.(state.continueText ? { action: 'apply', payload } : payload)
    resolvePromise = null
  }

  const continueCurrentAction = () => {
    if (!state.continueText) return
    isVisible.value = false
    resolvePromise?.({ action: 'continue' })
    resolvePromise = null
  }

  // 这些批量操作本质上只是切换默认选择模式并清空手动 override。
  const selectAll = () => {
    defaultSelectionMode.value = 'all'
    clearSelectionOverrides()
    rebuildVisiblePlan()
  }

  const selectRequiredOnly = () => {
    defaultSelectionMode.value = 'required'
    clearSelectionOverrides()
    rebuildVisiblePlan()
  }

  const clearSelection = () => {
    defaultSelectionMode.value = 'none'
    clearSelectionOverrides()
    rebuildVisiblePlan()
  }

  const isRootChecked = (rowId) => !!toggleSelections[rowId]
  const getChoiceSelection = (rowId) => choiceSelections[rowId] || ''

  const toggleRoot = (rowId, checked) => {
    toggleOverrides[rowId] = !!checked
    rebuildVisiblePlan()
  }

  const chooseRootOption = (rowId, optionId) => {
    choiceOverrides[rowId] = optionId || ''
    rebuildVisiblePlan()
  }

  // 真正应用时只更新当前启用列表并写入历史栈，不会直接触发保存。
  // removeIds 主要服务于替代模组这类“启用新项同时移除旧项”的场景。
  const applySelectionPayload = async (payload = { addIds: [], removeIds: [] }, { silent = false } = {}) => {
    const idsToEnable = dedupeNormalizedPackageIds(payload.addIds || [])
    const idsToRemove = dedupeNormalizedPackageIds(payload.removeIds || []).filter(removeId => !idsToEnable.includes(removeId))
    if (idsToEnable.length === 0 && idsToRemove.length === 0) return false

    const success = await modStore.runListHistoryTransaction({
      type: 'supplement-enable',
      label: idsToRemove.length > 0
        ? `补充启用 ${idsToEnable.length} 项并替换 ${idsToRemove.length} 项`
        : `补充启用 ${idsToEnable.length} 项`,
      trackedModIds: [...idsToEnable, ...idsToRemove],
    }, async () => {
      modStore.removeIdsOnAllList([...idsToEnable, ...idsToRemove])
      if (idsToEnable.length > 0) {
        await modStore.smartInsertMods(idsToEnable)
        modStore.takeModListByIds(idsToEnable).forEach(mod => {
          mod.last_moved_time = Date.now()
          mod.last_active_time = Date.now()
        })
      }
      modStore.updateInactiveIds()
    })

    if (success && !silent) {
      const suffix = idsToRemove.length > 0 ? `，并移除了 ${idsToRemove.length} 个原项` : ''
      toast.success(`已补充启用 ${idsToEnable.length} 个模组${suffix}`)
    }
    return success
  }

  // 常规入口：用户主动打开补缺弹窗。
  const openForActiveList = async ({
    activeIds = modStore.activeIds,
    title = '启用建议',
    message = '下面这些模组会在你确认后加入当前启用列表，但不会自动保存。',
  } = {}) => {
    const prepared = await prepareDialogPlan(activeIds)
    if (prepared.plan.summary.count === 0) {
      toast.info('当前没有需要启用的建议', { timeout: 1800 })
      return false
    }
    const payload = await openPreparedPlan({
      activeIds,
      title,
      message,
      confirmText: '加入当前列表',
      cancelText: '取消',
      prepared,
    })
    if (!payload) return false
    return await applySelectionPayload(payload)
  }

  // 保存前只强提示必需项；用户仍可明确确认后跳过。
  const ensureRequiredBeforeSave = async ({
    activeIds = modStore.activeIds,
    actionLabel = '保存',
  } = {}) => {
    const prepared = await prepareDialogPlan(activeIds)
    if (prepared.plan.summary.requiredCount === 0) return true

    const result = await openPreparedPlan({
      activeIds,
      title: `${actionLabel}前发现必需启用项`,
      message: `下面这些已安装但未启用的模组会影响这次${actionLabel}。你可以先启用它们再继续，也可以先忽略，或者取消这次${actionLabel}。`,
      confirmText: `启用选中项后继续${actionLabel}`,
      cancelText: `取消${actionLabel}`,
      continueText: `忽略这些项并继续${actionLabel}`,
      prepared,
    })
    if (!result) return false
    if (result.action === 'continue') return true

    if (result.action === 'apply') {
      await applySelectionPayload(result.payload, { silent: true })
    }

    const nextSummary = buildSummary(modStore.activeIds).summary
    if (nextSummary.requiredCount === 0) return true
    toast.warning(`已取消${actionLabel}，还有 ${nextSummary.requiredCount} 项建议没有处理。`, { timeout: 2600 })
    return false
  }

  // 自动排序前更严格：必需项未处理时直接取消排序，避免在不完整序列上排序。
  const ensureRequiredBeforeAutosort = async ({
    activeIds = modStore.activeIds,
  } = {}) => {
    const prepared = await prepareDialogPlan(activeIds)
    if (prepared.plan.summary.requiredCount === 0) return true

    const result = await openPreparedPlan({
      activeIds,
      title: '自动排序前发现必需启用项',
      message: '下面这些已安装但未启用的模组会影响这次自动排序。你可以先启用它们再继续，也可以先忽略，或者取消这次排序。',
      confirmText: '启用选中项后继续排序',
      cancelText: '取消排序',
      continueText: '忽略这些项并继续排序',
      prepared,
    })
    if (!result) return false
    if (result.action === 'continue') return true

    await applySelectionPayload(result.payload, { silent: true })
    const nextSummary = buildSummary(modStore.activeIds).summary
    if (nextSummary.requiredCount === 0) return true

    toast.warning(`自动排序已取消，还有 ${nextSummary.requiredCount} 项建议没有处理。`, { timeout: 2600 })
    return false
  }

  // 统计始终基于当前闭包结果，因此父项取消后其子项会同步从计数中移除。
  const selectedStats = computed(() => {
    let total = 0
    let selected = 0

    visibleRows.value.forEach(row => {
      total += 1
      if (row.kind === 'choice') {
        if (choiceSelections[row.id]) selected += 1
        return
      }
      if (toggleSelections[row.id]) selected += 1
    })

    return { selected, total }
  })

  const selectedCount = computed(() => selectedStats.value.selected)
  const totalCount = computed(() => selectedStats.value.total)

  // 提供给外层按钮/徽标使用的轻量摘要，不暴露完整行数据。
  const getSuggestionSummary = (activeIds = modStore.activeIds) => {
    const { groups, summary } = buildSummary(activeIds)
    return {
      groups: groups.map(group => ({
        key: group.key,
        title: group.title,
        severity: group.severity,
        count: group.rows.length,
      })),
      ...summary,
    }
  }

  return {
    isVisible,
    state,
    toggleSelections,
    choiceSelections,
    selectedCount,
    totalCount,
    getSuggestionSummary,
    openForActiveList,
    ensureRequiredBeforeSave,
    ensureRequiredBeforeAutosort,
    isRootChecked,
    getChoiceSelection,
    toggleRoot,
    chooseRootOption,
    selectAll,
    selectRequiredOnly,
    clearSelection,
    confirm,
    continueCurrentAction,
    cancel,
    severityMeta: SEVERITY_META,
  }
})
