import { defineStore } from 'pinia'
import { computed, reactive, ref } from 'vue'
import { toast } from '../../shared/lib/common'
import { useAppStore } from '../../app/stores/appStore'
import { useModStore } from '../mod/stores/modStore'
import { useProfileStore } from '../profiles/profileStore'
import { ISSUE_TYPE } from '../../shared/lib/constants'
import {
  dedupeNormalizedPackageIds, dedupeNormalizedPackageTokens,
  hasUsableLanguagePackOwnership, isLanguagePackType, mapUniqueDisplayNames,
  normalizePackageId, normalizePackageToken, pushUnique
} from '../mod/lib/modIdentity'
import { DEFAULT_TOOL_PACKAGE_IDS, isCorePackageId, isOfficialDlcPackageId } from '../mod/lib/packageScope'
import { getVersionInfo as getVersionInfoByVersions, normalizeVersion } from '../mod/lib/versioning'
import { t } from '../../shared/i18n.js'

const CATEGORY_DEFS = [
  ['core', 'danger'],
  ['official_dlc', 'danger'],
  ['tool_mod', 'danger'],
  ['dependency', 'danger'],
  ['language_pack', 'warn'],
  ['version_replacement', 'warn'],
  ['optional_replacement', 'info'],
]
const CATEGORY_ORDER = CATEGORY_DEFS.map(([key]) => key)
const CATEGORY_SEVERITY = Object.fromEntries(CATEGORY_DEFS)

const dedupeValues = (values = []) => [...new Set((values || []).filter(Boolean))]
const isLanguagePackMod = (mod) => isLanguagePackType(mod)

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

const categoryTitleText = (category = '') => ({
  core: 'Core',
  official_dlc: t('dialog.supplement.category.official_dlc.title', '官方 DLC'),
  tool_mod: t('dialog.supplement.category.tool_mod.title', '工具模组'),
  dependency: t('dialog.supplement.category.dependency.title', '依赖项'),
  language_pack: t('dialog.supplement.category.language_pack.title', '语言包'),
  version_replacement: t('dialog.supplement.category.version_replacement.title', '替代建议'),
  optional_replacement: t('dialog.supplement.category.optional_replacement.title', '可选启用'),
}[category] || category)

const categoryDescriptionText = (category = '') => ({
  core: t('dialog.supplement.category.core.description', '游戏核心模组未启用。'),
  official_dlc: t('dialog.supplement.category.official_dlc.description', '当前序列引用了未启用的官方扩展。'),
  tool_mod: t('dialog.supplement.category.tool_mod.description', '当前设置允许的工具模组未启用。'),
  dependency: t('dialog.supplement.category.dependency.description', '这些模组是当前启用模组的依赖。'),
  language_pack: t('dialog.supplement.category.language_pack.description', '存在可用但未启用的当前语言语言包。'),
  version_replacement: t('dialog.supplement.category.version_replacement.description', '当前版本可优先启用更合适的替代模组。'),
  optional_replacement: t('dialog.supplement.category.optional_replacement.description', '当前模组已可用，如有需要也可启用其它已安装替代项。'),
}[category] || '')

const buildReplacementOptionDetail = (ownerName = '', replacementName = '') => {
  const left = String(ownerName || '').trim()
  const right = String(replacementName || '').trim()
  if (left && right) return t('dialog.supplement.replacement_detail.replace_named', '启用后替换 {name}', { name: left })
  if (left) return t('dialog.supplement.replacement_detail.replace_current', '启用后替换当前模组')
  if (right) return t('dialog.supplement.replacement_detail.switch_to', '启用后切换到 {name}', { name: right })
  return t('dialog.supplement.replacement_detail.replace_current', '启用后替换当前模组')
}

const getResolvedLanguagePackOwnerIds = (mod) => (
  [...new Set(
    (mod?.language_pack_owner_result?.owners || [])
      .map(owner => normalizePackageId(owner?.package_id))
      .filter(Boolean)
  )]
)
const canUseLanguagePackForSupplement = (mod) => hasUsableLanguagePackOwnership(mod)
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

const SEVERITY_ORDER = ['danger', 'warn', 'info']
const pickPreferredSeverity = (left = 'info', right = 'info') => (
  SEVERITY_ORDER.indexOf(left) <= SEVERITY_ORDER.indexOf(right) ? left : right
)

const normalizeSelectionMode = (value = 'all') => {
  const normalized = String(value || '').trim().toLowerCase()
  return ['all', 'danger', 'none', 'custom'].includes(normalized) ? normalized : 'all'
}

const sortRows = (rows = []) => (
  [...rows].sort((left, right) => {
    const categoryDiff = compareCategory(left.category, right.category)
    if (categoryDiff !== 0) return categoryDiff
    return String(left.title || '').localeCompare(String(right.title || ''))
  })
)

export const useSupplementStore = defineStore('supplement', () => {
  const appStore = useAppStore()
  const modStore = useModStore()
  const profileStore = useProfileStore()

  const isVisible = ref(false)
  const state = reactive({
    title: '',
    message: '',
    confirmText: t('dialog.supplement.apply_selected', '应用选中项'),
    cancelText: t('common.action.cancel', '取消'),
    continueText: '',
    groups: [],
    summary: {
      count: 0,
      dangerCount: 0,
      warnCount: 0,
      infoCount: 0,
      visibleCount: 0,
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
    if (!currentLanguage.value) {
      return { strictTargetMap, fallbackTargetMap }
    }
    for (const mod of modStore.getAvailableModInstances()) {
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
    // 规则 owner 必须保留实例 token；依赖是否已满足仍按裸包名判断。
    const activeTokens = dedupeNormalizedPackageTokens(activeIds)
    const canonicalActiveIds = dedupeNormalizedPackageIds(activeTokens)
    return {
      activeIds: activeTokens,
      activeSet: new Set(canonicalActiveIds),
      ...getLanguagePackTargetMap(),
    }
  }

  const buildOwnersDetail = (owners = [], suffix = '') => {
    const ownerNames = listOwnerNames(owners, modStore)
    if (ownerNames.length === 0) return suffix
    const joined = ownerNames.join('、')
    return suffix ? `${joined}${suffix}` : joined
  }

  const collectInstalledReplacementEntries = (ownerIds = [], ctx) => {
    const entryMap = new Map()

    ownerIds.forEach(ownerId => {
      const owner = modStore.takeModById(ownerId)
      if (!owner || isIssueIgnored(owner, ISSUE_TYPE.WARN_VERSION_MISMATCH)) return

      const replacementId = normalizePackageId(owner?.replacement?.new_package_id)
      if (!replacementId) return
      if (!modStore.hasRealModById(replacementId) || ctx.activeSet.has(replacementId)) return

      const replacementVersionInfo = getVersionInfo(replacementId)
      if (replacementVersionInfo.tone !== 'success') return

      const ownerVersionInfo = getVersionInfo(ownerId)
      const category = ownerVersionInfo.tone === 'danger' ? 'version_replacement' : 'optional_replacement'
      const key = `replacement:${ownerId}`
      const ownerName = modStore.displayModName(ownerId)
      const replacementName = modStore.displayModName(replacementId)

      if (!entryMap.has(key)) {
        entryMap.set(key, {
          entryType: 'choice',
          key,
          category,
          severity: CATEGORY_SEVERITY[category] || 'info',
          title: ownerName,
          reason: '',
          detail: '',
          owners: [ownerId],
          allowSkip: true,
          defaultSelected: false,
          defaultOptionPackageId: replacementId,
          options: [{
            packageId: replacementId,
            title: replacementName,
            detail: buildReplacementOptionDetail(ownerName, replacementName),
            removeIds: [ownerId],
            relationLabel: t('dialog.supplement.relation.replacement', '替代版'),
          }],
        })
        return
      }

      const currentEntry = entryMap.get(key)
      currentEntry.options = [
        ...(currentEntry.options || []),
        {
          packageId: replacementId,
          title: replacementName,
          detail: buildReplacementOptionDetail(ownerName, replacementName),
          removeIds: [ownerId],
          relationLabel: t('dialog.supplement.relation.replacement', '替代版'),
        },
      ]
    })

    return Array.from(entryMap.values()).map(entry => {
      const hasVersionMismatchOwner = entry.category === 'version_replacement'
      const replacementNames = mapUniqueDisplayNames(entry.options || [], option => option?.title || '')
      return {
        ...entry,
        reason: hasVersionMismatchOwner
          ? t('dialog.supplement.reason.version_can_switch_replacement', '当前版本可切换到已安装替代模组')
          : t('dialog.supplement.reason.mod_can_switch_replacement', '当前模组可切换到已安装替代模组'),
        detail: hasVersionMismatchOwner
          ? mergeText(t('dialog.supplement.detail.can_switch_to', '可切换到：{names}', { names: replacementNames.join('、') }), t('dialog.supplement.detail.version_may_not_fit', '当前版本可能不适配'))
          : t('dialog.supplement.detail.can_switch_to', '可切换到：{names}', { names: replacementNames.join('、') }),
      }
    })
  }

  // 这里只收集“候选条目”，不直接决定是否显示或启用。
  // satisfiedSet 表示当前路径已满足的包，trailSet 用于阻断递归回环。
  const collectDependencyEntries = (ownerIds = [], ctx, satisfiedSet = ctx.activeSet, trailSet = new Set()) => {
    const entryMap = new Map()
    const availableInstances = modStore.getAvailableModInstances()
    const takeInstalledOptions = (optionId = '') => availableInstances
      .filter(mod => {
        const packageId = normalizePackageId(mod?.package_id)
        return packageId === optionId && !mod?.isMissing && !!mod?.path
      })
      .map(mod => {
        const packageToken = normalizePackageToken(mod.active_package_token || mod.package_id)
        const sourceLabel = packageToken.endsWith('_steam')
          ? t('common.store.workshop', '工坊')
          : t('common.store.local', '本地')
        return { packageId: packageToken, canonicalId: normalizePackageId(packageToken), mod, sourceLabel }
      })

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

        const installedOptions = optionIds.flatMap(takeInstalledOptions)
        if (installedOptions.length === 0) return
        const category = isCorePackageId(targetId)
          ? 'core'
          : isOfficialDlcPackageId(targetId)
            ? 'official_dlc'
            : 'dependency'

        const key = `dependency:${targetId}:${installedOptions.map(option => option.packageId).join('|')}`
        if (!entryMap.has(key)) {
          const onlyOption = installedOptions.length === 1 ? installedOptions[0] : null
          const usesAlternativeOnly = !!onlyOption && onlyOption.canonicalId !== targetId
          const preferredOption = installedOptions.find(option => option.canonicalId === targetId) || installedOptions[0]
          entryMap.set(key, {
            entryType: installedOptions.length > 1 ? 'choice' : 'toggle',
            key,
            category,
            severity: CATEGORY_SEVERITY[category] || 'danger',
            title: usesAlternativeOnly ? modStore.displayModName(onlyOption.packageId) : modStore.displayModName(targetId),
            reason: '',
            detail: '',
            owners: [],
            packageId: onlyOption?.packageId || '',
            removeIds: [],
            relationLabel: usesAlternativeOnly ? t('dialog.supplement.relation.alternative_dependency', '备选依赖') : t('dialog.supplement.relation.dependency', '依赖'),
            allowSkip: true,
            defaultOptionPackageId: preferredOption?.packageId || '',
            options: installedOptions.map(option => ({
              packageId: option.packageId,
              title: modStore.displayModName(option.packageId),
              detail: mergeText(
                option.canonicalId === targetId ? t('dialog.supplement.detail.original_dependency', '原始依赖项') : t('dialog.supplement.detail.alternative_dependency', '可用于满足依赖的备选模组'),
                option.sourceLabel,
              ),
              removeIds: [],
              relationLabel: option.canonicalId === targetId ? t('dialog.supplement.relation.dependency', '依赖') : t('dialog.supplement.relation.alternative_dependency', '备选依赖'),
            })),
            hasAlternatives: alternativeIds.length > 0,
          })
        }
        uniquePush(entryMap.get(key).owners, ownerId)
      })
    })

    return Array.from(entryMap.values()).map(entry => {
      const ownerCount = entry.owners.length
      const ownerDetail = buildOwnersDetail(entry.owners, ownerCount > 0 ? t('dialog.supplement.suffix.dependency_of', ' 的依赖') : t('dialog.supplement.relation.dependency', '依赖'))
      return {
        ...entry,
        reason: ownerCount > 1 ? t('dialog.supplement.reason.required_by_many', '被 {count} 个模组同时依赖', { count: ownerCount }) : t('dialog.supplement.reason.missing_dependency', '当前序列缺少依赖项'),
        detail: ownerDetail,
      }
    })
  }

  // 语言包补缺与“问题提示”保持同一口径：
  // 仅当原模组不支持当前语言、且当前路径上没有已满足的对应语言包时，才补出首个候选语言包。
  const collectLanguageEntries = (ownerIds = [], ctx, satisfiedSet = ctx.activeSet, trailSet = new Set()) => {
    if (!currentLanguage.value) return []
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
      const candidateToken = String(candidate.active_package_token || candidate.package_id || candidateId).trim().toLowerCase()
      const key = `language:${candidateToken}`
      if (!entryMap.has(key)) {
        const isFallback = strictCandidates.length === 0
        entryMap.set(key, {
          entryType: 'toggle',
          key,
          category: 'language_pack',
          severity: 'warn',
          title: modStore.displayModName(candidate),
          reason: '',
          detail: '',
          owners: [],
          // 语言包自身也可能存在本地/工坊共存，补齐时保留候选实例 token。
          packageId: candidateToken,
          removeIds: [],
          relationLabel: t('dialog.supplement.relation.language_pack', '语言包'),
          isLanguageFallback: isFallback,
        })
      }
      uniquePush(entryMap.get(key).owners, ownerId)
    })

    return Array.from(entryMap.values()).map(entry => {
      const ownerCount = entry.owners.length
      return {
        ...entry,
        reason: ownerCount > 1 ? t('dialog.supplement.reason.language_pack_for_many', '可为 {count} 个模组提供当前语言支持', { count: ownerCount }) : t('dialog.supplement.reason.language_pack_for_current', '可补充当前语言包'),
        detail: entry.isLanguageFallback
          ? mergeText(buildOwnersDetail(entry.owners, t('dialog.supplement.suffix.possible_language_pack', ' 的可能相关语言包')), t('dialog.supplement.detail.language_not_declared', '该语言包未标注当前语言'))
          : buildOwnersDetail(entry.owners, t('dialog.supplement.suffix.language_pack', ' 的语言包')),
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
        severity: 'danger',
        title: modStore.displayModName('ludeon.rimworld'),
        reason: t('dialog.supplement.reason.missing_core', '当前启用序列缺少 Core'),
        detail: t('dialog.supplement.detail.complete_before_save_or_launch', '保存或启动游戏前建议补齐。'),
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
          severity: 'danger',
          title: modStore.displayModName(toolId),
          reason: t('dialog.supplement.reason.tool_mod_enabled', '当前设置启用了工具模组支持'),
          detail: t('dialog.supplement.detail.tool_mod_inactive', '工具模组已安装但未启用。'),
          owners: [],
          packageId: toolId,
          removeIds: [],
          relationLabel: t('dialog.supplement.relation.tool', '工具'),
        })
      })
    }

    entries.push(...collectDependencyEntries(ctx.activeIds, ctx, ctx.activeSet, new Set()))
    entries.push(...collectLanguageEntries(ctx.activeIds, ctx, ctx.activeSet, new Set()))
    entries.push(...collectInstalledReplacementEntries(ctx.activeIds, ctx))

    return entries
  }

  const graphState = ref(null)
  const toggleOverrides = reactive({})
  const choiceOverrides = reactive({})
  const defaultSelectionMode = ref('all')

  // choice option 需要跨不同来源合并，这里先统一成标准结构。
  const createChoiceOption = (rowId, option = {}) => {
    // 选项可能指向共存实例；保留 token 供最终启用，删除项仍按规范包名处理。
    const packageId = normalizePackageToken(option.packageId)
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
  dangerCount: 0,
  warnCount: 0,
  infoCount: 0,
  visibleCount: 0,
  urgency: 'none',
})

  // 图节点不是最终 UI 行；这里把节点转成可合并的平面行结构。
  const createToggleRow = (node) => ({
    id: node.rowId,
    kind: 'toggle',
    category: node.category,
    severity: node.severity || 'info',
    packageId: node.packageId,
    title: node.title || modStore.displayModName(node.packageId),
    reason: node.reason || '',
    detail: node.detail || '',
    defaultSelected: node.defaultSelected,
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
    severity: node.severity || 'info',
    title: node.title || '',
    reason: node.reason || '',
    detail: node.detail || '',
    owners: dedupeNormalizedPackageIds(node.owners || []),
    allowSkip: node.allowSkip !== false,
    defaultSelected: node.defaultSelected,
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
	          title: categoryTitleText(category),
	          description: categoryDescriptionText(category),
          severity: CATEGORY_SEVERITY[category] || 'info',
          rows: sortRows(groupRows),
        }
      })
      .filter(Boolean)

    const count = rows.length
    const dangerCount = rows.filter(row => row.severity === 'danger').length
    const warnCount = rows.filter(row => row.severity === 'warn').length
    const infoCount = rows.filter(row => row.severity === 'info').length
    const visibleCount = dangerCount + warnCount

    return {
      groups,
      summary: {
        count,
        dangerCount,
        warnCount,
        infoCount,
        visibleCount,
        urgency: dangerCount > 0 ? 'danger' : warnCount > 0 ? 'warn' : 'none',
      },
    }
  }

  const getDefaultToggleSelection = (row, mode = defaultSelectionMode.value) => {
    const normalizedMode = normalizeSelectionMode(mode)
    if (normalizedMode === 'none') return false
    if (normalizedMode === 'danger') return row?.severity === 'danger'
    if (typeof row?.defaultSelected === 'boolean') return row.defaultSelected
    return true
  }

  const getDefaultChoiceSelection = (row, mode = defaultSelectionMode.value) => {
    const normalizedMode = normalizeSelectionMode(mode)
    if (normalizedMode === 'none') return ''
    if (normalizedMode === 'danger' && row?.severity !== 'danger') return ''
    if (normalizedMode === 'custom' && row?.defaultSelected === false) return ''
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
          const packageToken = normalizePackageToken(option.packageId)
          const packageId = normalizePackageId(packageToken)
          const nextTrailSet = new Set([...Array.from(trailSet), packageId])
          const nextSatisfiedSet = new Set([...Array.from(satisfiedSet), packageId])
          const childEntries = [
            ...collectDependencyEntries([packageToken], ctx, nextSatisfiedSet, nextTrailSet),
            ...collectLanguageEntries([packageToken], ctx, nextSatisfiedSet, nextTrailSet),
          ]
          const childNodeIds = childEntries
            .map(childEntry => buildNode(childEntry, nextSatisfiedSet, nextTrailSet))
            .filter(Boolean)

          return {
            id: `${rowId}:${packageToken}`,
            packageId: packageToken,
            title: option.title || modStore.displayModName(packageToken),
            detail: option.detail || '',
            removeIds: dedupeNormalizedPackageIds(option.removeIds || []),
            relationLabel: option.relationLabel || '',
            relationLabels: option.relationLabel ? [option.relationLabel] : [],
            versionInfo: getVersionInfo(packageToken),
            childNodeIds,
          }
        })

        const preferredPackageId = normalizePackageToken(entry.defaultOptionPackageId)
        const preferredOption = options.find(option => option.packageId === preferredPackageId) || options[0]
        const node = {
          id: nextNodeId('choice'),
          rowId,
          kind: 'choice',
          category: entry.category,
          severity: entry.severity || 'info',
          title: entry.title || '',
          reason: entry.reason || '',
          detail: entry.detail || '',
          owners: dedupeNormalizedPackageIds(entry.owners || []),
          allowSkip: entry.allowSkip !== false,
          defaultSelected: entry.defaultSelected,
          options,
          defaultOptionId: preferredOption?.id || '',
        }
        nodes.set(node.id, node)
        mergeRowFromNode(rowCatalog, node)
        return node.id
      }

      // packageToken 决定实际启用哪个共存实例，packageId 只用于依赖满足和回环检测。
      const packageToken = normalizePackageToken(entry.packageId)
      const packageId = normalizePackageId(packageToken)
      if (!packageId) return null
      const rowId = `toggle:${packageToken}`
      const nextTrailSet = new Set([...Array.from(trailSet), packageId])
      const nextSatisfiedSet = new Set([...Array.from(satisfiedSet), packageId])
      const childEntries = [
        ...collectDependencyEntries([packageToken], ctx, nextSatisfiedSet, nextTrailSet),
        ...collectLanguageEntries([packageToken], ctx, nextSatisfiedSet, nextTrailSet),
      ]
      const childNodeIds = childEntries
        .map(childEntry => buildNode(childEntry, nextSatisfiedSet, nextTrailSet))
        .filter(Boolean)

      const node = {
        id: nextNodeId('toggle'),
        rowId,
        kind: 'toggle',
        category: entry.category,
        severity: entry.severity || 'info',
        packageId: packageToken,
        title: entry.title || modStore.displayModName(packageToken),
        reason: entry.reason || '',
        detail: entry.detail || '',
        defaultSelected: entry.defaultSelected,
        owners: dedupeNormalizedPackageIds(entry.owners || []),
        removeIds: dedupeNormalizedPackageIds(entry.removeIds || []),
        relationLabel: entry.relationLabel || '',
        versionInfo: getVersionInfo(packageToken),
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
    confirmText = t('dialog.supplement.apply_selected', '应用选中项'),
    cancelText = t('common.action.cancel', '取消'),
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
    state.confirmText = t('dialog.supplement.apply_selected', '应用选中项')
    state.cancelText = t('common.action.cancel', '取消')
    state.continueText = ''
    state.groups = []
    state.summary = createEmptySummary()
    graphState.value = null
    defaultSelectionMode.value = 'custom'
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

  // 这里只处理“已安装但未启用”的候选。
  const prepareDialogPlan = async (activeIds = modStore.activeIds) => {
    const graph = buildSupplementGraph(activeIds)
    const plan = resolveProjectedPlan(graph)
    return { graph, plan }
  }

  // prepared 允许外部复用同一份预计算结果，减少重复构图与闭包求解。
  const openPreparedPlan = async ({
    activeIds = modStore.activeIds,
	    title = t('dialog.supplement.title', '补齐启用项'),
    message = '',
	    confirmText = t('dialog.supplement.enable_selected', '启用选中项'),
	    cancelText = t('common.action.cancel', '取消'),
    continueText = '',
    prepared = null,
  } = {}) => {
    resetDialogState()
    defaultSelectionMode.value = 'custom'
    const resolvedActiveIds = dedupeNormalizedPackageTokens(activeIds)
    const resolvedPrepared = prepared || await prepareDialogPlan(resolvedActiveIds)
    graphState.value = resolvedPrepared.graph
    applyResolvedPlan(resolvedPrepared.plan, { title, message, confirmText, cancelText, continueText })
    isVisible.value = true
    return new Promise(resolve => {
      resolvePromise = resolve
    })
  }
  const resolveSupplementPayloadForList = async (activeIds = modStore.activeIds, { selectionMode = 'danger' } = {}) => {
    const previousMode = defaultSelectionMode.value
    const previousToggleOverrides = { ...toggleOverrides }
    const previousChoiceOverrides = { ...choiceOverrides }
    try {
      clearSelectionOverrides()
      defaultSelectionMode.value = normalizeSelectionMode(selectionMode)
      const resolvedActiveIds = dedupeNormalizedPackageTokens(activeIds)
      const prepared = await prepareDialogPlan(resolvedActiveIds)
      const plan = resolveProjectedPlan(prepared.graph)
      return plan.payload || { addIds: [], removeIds: [] }
    } finally {
      defaultSelectionMode.value = previousMode
      clearReactiveObject(toggleOverrides)
      clearReactiveObject(choiceOverrides)
      Object.assign(toggleOverrides, previousToggleOverrides)
      Object.assign(choiceOverrides, previousChoiceOverrides)
    }
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
    defaultSelectionMode.value = 'danger'
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
    // addIds 必须保留来源 token；否则补齐工坊实例时，智能插入会重新读取本地原生规则。
    const idsToEnable = dedupeNormalizedPackageTokens(payload.addIds || [])
    const enabledCanonicalIds = new Set(idsToEnable.map(normalizePackageId))
    const idsToRemove = dedupeNormalizedPackageIds(payload.removeIds || [])
      .filter(removeId => !enabledCanonicalIds.has(removeId))
    if (idsToEnable.length === 0 && idsToRemove.length === 0) return false

    const success = await modStore.runListHistoryTransaction({
      type: 'supplement-enable',
      label: idsToRemove.length > 0
        ? t('dialog.supplement.history.enable_and_replace', '补充启用 {enableCount} 项并替换 {removeCount} 项', { enableCount: idsToEnable.length, removeCount: idsToRemove.length })
        : t('dialog.supplement.history.enable', '补充启用 {count} 项', { count: idsToEnable.length }),
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
      const suffix = idsToRemove.length > 0 ? t('dialog.supplement.enabled_success_removed_suffix', '，并移除了 {count} 个原项', { count: idsToRemove.length }) : ''
      toast.success(t('dialog.supplement.enabled_success', '已补充启用 {count} 个模组{suffix}', { count: idsToEnable.length, suffix }))
    }
    return success
  }

  // 常规入口：用户主动打开补缺弹窗。
  const openForActiveList = async ({
    activeIds = modStore.activeIds,
	    title = t('dialog.supplement.title', '补齐启用项'),
	    message = t('dialog.supplement.message', '选择要启用的模组。'),
  } = {}) => {
    const prepared = await prepareDialogPlan(activeIds)
    if (prepared.plan.summary.count === 0) {
	      toast.info(t('dialog.supplement.no_items', '当前没有可补齐的未启用模组'), { timeout: 1800 })
      return false
    }
    const payload = await openPreparedPlan({
      activeIds,
      title,
      message,
	      confirmText: t('dialog.supplement.add_to_current_list', '加入当前列表'),
	      cancelText: t('common.action.cancel', '取消'),
      prepared,
    })
    if (!payload) return false
    return await applySelectionPayload(payload)
  }

  // 保存前只强提示必需项；用户仍可明确确认后跳过。
  const ensureRequiredBeforeSave = async ({
    activeIds = modStore.activeIds,
	    actionLabel = t('common.action.save', '保存'),
  } = {}) => {
    if (appStore.settings.enable_action_prechecks === false) return true
    const prepared = await prepareDialogPlan(activeIds)
    if (prepared.plan.summary.dangerCount === 0) return true

    const result = await openPreparedPlan({
      activeIds,
	      title: t('dialog.supplement.precheck_title', '{action}前发现未启用项', { action: actionLabel }),
	      message: t('dialog.supplement.precheck_message', '有些已安装模组建议先启用再{action}。', { action: actionLabel }),
	      confirmText: t('dialog.supplement.enable_selected_and_continue', '启用选中项后继续{action}', { action: actionLabel }),
	      cancelText: t('dialog.supplement.cancel_action', '取消{action}', { action: actionLabel }),
	      continueText: t('dialog.supplement.continue_without_fix', '不处理继续{action}', { action: actionLabel }),
      prepared,
    })
    if (!result) return false
    if (result.action === 'continue') return true

    if (result.action === 'apply') {
      await applySelectionPayload(result.payload, { silent: true })
    }

    const nextSummary = buildSummary(modStore.activeIds).summary
    if (nextSummary.dangerCount === 0) return true
	    toast.warning(t('dialog.supplement.action_cancelled_remaining', '已取消{action}，还有 {count} 项未处理。', { action: actionLabel, count: nextSummary.dangerCount }), { timeout: 2600 })
    return false
  }

  // 自动排序前更严格：必需项未处理时直接取消排序，避免在不完整序列上排序。
  const ensureRequiredBeforeAutosort = async ({
    activeIds = modStore.activeIds,
  } = {}) => {
    if (appStore.settings.enable_action_prechecks === false) return true
    const prepared = await prepareDialogPlan(activeIds)
    if (prepared.plan.summary.dangerCount === 0) return true

    const result = await openPreparedPlan({
      activeIds,
	      title: t('dialog.supplement.autosort_precheck_title', '排序前发现未启用项'),
	      message: t('dialog.supplement.autosort_precheck_message', '有些已安装模组建议先启用再排序。'),
	      confirmText: t('dialog.supplement.enable_selected_and_continue_sort', '启用选中项后继续排序'),
	      cancelText: t('dialog.supplement.cancel_sort', '取消排序'),
	      continueText: t('dialog.supplement.continue_sort_without_fix', '不处理继续排序'),
      prepared,
    })
    if (!result) return false
    if (result.action === 'continue') return true

    await applySelectionPayload(result.payload, { silent: true })
    const nextSummary = buildSummary(modStore.activeIds).summary
    if (nextSummary.dangerCount === 0) return true

	    toast.warning(t('dialog.supplement.autosort_cancelled_remaining', '自动排序已取消，还有 {count} 项未处理。', { count: nextSummary.dangerCount }), { timeout: 2600 })
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
    // 弹窗状态
    isVisible, state, toggleSelections, choiceSelections, selectedCount, totalCount,
    // 摘要与打开入口
    getSuggestionSummary, openForActiveList, resolveSupplementPayloadForList, ensureRequiredBeforeSave, ensureRequiredBeforeAutosort,
    // 选择控制
    isRootChecked, getChoiceSelection, toggleRoot, chooseRootOption,
    selectAll, selectRequiredOnly, clearSelection,
    // 提交流程
    confirm, continueCurrentAction, cancel,
  }
})
