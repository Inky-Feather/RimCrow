import { computed, reactive, ref } from 'vue'
import { defineStore } from 'pinia'
import { createToastInterface } from 'vue-toastification'
import {
  dedupeInstallSources,
  dedupeNormalizedPackageIds,
  getInstallSourceKey,
  normalizeInstallSource,
  normalizePackageId,
  normalizeWorkshopId,
} from '../utils/modIdentity'
import {
  buildVersionPreferenceScore,
  getVersionInfo,
  normalizeVersion,
} from '../utils/versioning'
import { ISSUE_TYPE } from '../utils/constants'
import { DEFAULT_TOOL_PACKAGE_IDS, isBuiltinManagedPackageId } from '../utils/packageScope'
import { useAppStore } from './appStore'
import { useModStore } from './modStore'
import { useProfileStore } from './profileStore'
import { useWorkspaceStore } from './workspaceStore'

const GROUP_META = {
  missing_install: {
    title: '可直接安装',
    description: '这些模组还没安装，现在可以直接处理。',
    severity: 'danger',
  },
  missing_with_replacement_choice: {
    title: '原版或替代',
    description: '可安装原模组，也可改装替代模组。',
    severity: 'danger',
  },
  version_replacement_warn: {
    title: '版本替代',
    description: '当前模组可能不适配，可改装更合适的替代模组。',
    severity: 'warn',
  },
  missing_with_installed_replacement: {
    title: '已装替代',
    description: '当前已有可用替代。点击订阅或下载时会自动切换为已装替代。',
    severity: 'info',
  },
  optional_install: {
    title: '可选补装',
    description: '当前模组已可用，如有需要也可补装其它版本。',
    severity: 'info',
  },
}

const EMPTY_SUMMARY = {
  dangerTotal: 0,
  warnTotal: 0,
  infoTotal: 0,
  unknownTotal: 0,
  actionableTotal: 0,
  visibleEntryTotal: 0,
}

const GROUP_SEVERITY = Object.fromEntries(
  Object.entries(GROUP_META).map(([key, meta]) => [key, meta.severity || 'info'])
)

const buildChoiceId = (source = {}, fallbackType = 'original') => {
  const key = getInstallSourceKey(source)
  return key ? `${fallbackType}:${key}` : ''
}

export const useMissingInstallStore = defineStore('missingInstall', () => {
  const toast = createToastInterface()
  const appStore = useAppStore()
  const modStore = useModStore()
  const profileStore = useProfileStore()
  const workspaceStore = useWorkspaceStore()

  const isVisible = ref(false)
  const selections = reactive({})
  const choiceSelections = reactive({})
  const cachedAnalysis = ref({
    signature: '',
    payload: {
      rows: [],
      groups: [],
      unknownItems: [],
      summary: { ...EMPTY_SUMMARY },
      unknownActiveIds: [],
    },
  })
  const state = reactive({
    title: '缺失项安装管理',
    message: '处理未安装模组。',
    cancelText: '取消',
    cleanupText: '',
    cleanupShouldContinue: false,
    continueText: '',
    continueResult: false,
    disableRelatedText: '',
    disableRelatedOwnerIds: [],
    groups: [],
    unknownItems: [],
    summary: { ...EMPTY_SUMMARY },
  })
  let resolvePromise = null

  const visibleRows = computed(() => state.groups.flatMap(group => group.rows || []))
  const selectedRows = computed(() => visibleRows.value.filter(row => !!selections[row.id]))
  const selectedCount = computed(() => selectedRows.value.length)
  const totalCount = computed(() => visibleRows.value.length)
  const currentGameVersion = computed(() => normalizeVersion(profileStore.activeContext?.game_version))

  const isExcludedPackageId = (packageId = '') => (
    isBuiltinManagedPackageId(packageId, DEFAULT_TOOL_PACKAGE_IDS)
  )

  const isIssueIgnored = (mod, issueType = '') => (
    !!issueType && Array.isArray(mod?.ignored_issues) && mod.ignored_issues.includes(issueType)
  )

  const getVersionTooltip = (versionInfo = null) => {
    const versions = Array.isArray(versionInfo?.versions) ? versionInfo.versions : []
    return versions.length > 0
      ? `支持版本：${versions.join(', ')}`
      : '未提供支持版本信息'
  }

  const supportsCurrentGameVersion = (source = {}) => {
    const versionInfo = getVersionInfo(
      currentGameVersion.value,
      source?.supportedVersions || source?.supported_versions || []
    )
    return versionInfo.tone === 'success'
  }

  const sortSources = (sources = [], { preferReplacement = false } = {}) => {
    return [...(sources || [])].sort((left, right) => {
      const leftScore = buildVersionPreferenceScore(
        currentGameVersion.value,
        left?.supportedVersions || [],
        {
          preferWorkshop: left?.kind === 'workshop',
          preferReplacement: preferReplacement && left?.isReplacement,
        }
      )
      const rightScore = buildVersionPreferenceScore(
        currentGameVersion.value,
        right?.supportedVersions || [],
        {
          preferWorkshop: right?.kind === 'workshop',
          preferReplacement: preferReplacement && right?.isReplacement,
        }
      )
      if (rightScore !== leftScore) return rightScore - leftScore
      return String(left?.title || left?.packageId || '').localeCompare(String(right?.title || right?.packageId || ''))
    })
  }

  const isInstalledBySource = (source = {}) => {
    if (!source) return false
    if (normalizeWorkshopId(source.workshopId)) {
      return modStore.hasInstalledWorkshopId(source.workshopId)
    }
    if (normalizePackageId(source.packageId)) {
      return modStore.hasRealModById(source.packageId)
    }
    return false
  }

  const collectRuntimeSource = (packageId, mod = {}) => {
    // 这里只接受“真实已安装模组”的运行态来源。
    // 缺失占位项带出的 workshop/url 只是补全线索，不能当成原模组的真实安装来源。
    if (!mod || mod?.isMissing || !mod?.path || mod?.is_replacement_derived) return null
    return normalizeInstallSource({
      packageId,
      workshopId: mod?.workshop_id,
      url: mod?.url,
      title: mod?.display_name || mod?.alias_name || mod?.name || packageId,
      supportedVersions: mod?.supported_versions || [],
      sourceOrigin: 'runtime',
    }, packageId)
  }

  const collectReplacementSourceFromMod = (packageId, mod = {}) => {
    if (!mod?.replacement?.new_workshop_id) return null
    return normalizeInstallSource({
      packageId: mod?.replacement?.new_package_id || packageId,
      workshopId: mod?.replacement?.new_workshop_id,
      title: mod?.replacement?.new_name || `${modStore.displayModName(packageId)} 的替代项`,
      supportedVersions: mod?.replacement?.new_versions || [],
      sourceOrigin: 'replacement',
      isReplacement: true,
    }, packageId)
  }

  const resolveSourcesForPackage = (packageId = '', installSourceMap = {}) => {
    const normalizedPackageId = normalizePackageId(packageId)
    const mod = modStore.takeModById(normalizedPackageId)
    const sourceBundle = installSourceMap[normalizedPackageId] || { originalSources: [], replacementSources: [] }
    const hintSources = dedupeInstallSources(modStore.getInstallSourceHints(normalizedPackageId) || [])
    const authoritativeOriginalSources = dedupeInstallSources([
      collectRuntimeSource(normalizedPackageId, mod),
      ...(sourceBundle.originalSources || []),
    ].filter(source => source && !source.isReplacement))
    const replacementSources = dedupeInstallSources([
      collectReplacementSourceFromMod(normalizedPackageId, mod),
      ...(sourceBundle.replacementSources || []),
    ].filter(Boolean).map(source => ({ ...source, isReplacement: true })))
    const originalSources = authoritativeOriginalSources.length > 0
      ? authoritativeOriginalSources
      : dedupeInstallSources(
        hintSources.filter(source => source && !source.isReplacement)
      )

    return {
      mod,
      originalSources: sortSources(originalSources),
      replacementSources: sortSources(replacementSources, { preferReplacement: true }),
    }
  }

  const collectVersionReplacementWarnings = (activeIds = [], installSourceMap = {}) => {
    const rows = []
    dedupeNormalizedPackageIds(activeIds).forEach(packageId => {
      if (!packageId || !modStore.hasRealModById(packageId)) return
      const mod = modStore.takeModById(packageId)
      const versionInfo = getVersionInfo(currentGameVersion.value, mod?.supported_versions || [])
      if (versionInfo.tone !== 'danger') return
      const { replacementSources } = resolveSourcesForPackage(packageId, installSourceMap)
      const installableReplacementSources = replacementSources.filter(source => !isInstalledBySource(source))
      if (installableReplacementSources.length === 0) return
      const choiceOptions = buildReplacementChoiceOptions({
        packageId,
        mod,
        installableReplacementSources,
        includeCurrent: true,
      })
      if (choiceOptions.length === 0) return
      rows.push({
        id: `warn-version:${packageId}`,
        groupKey: 'version_replacement_warn',
        packageId,
        title: modStore.displayModName(packageId),
        reasonLabels: ['版本不符'],
        choiceOptions,
        defaultChoiceId: choiceOptions.find(choice => choice?.type === 'current')?.id || choiceOptions[0]?.id || '',
        defaultSelected: false,
      })
    })
    return rows
  }

  const createRowChoice = (source = {}, type = 'original') => {
    const normalizedSource = normalizeInstallSource(source, source?.packageId || source?.package_id)
    if (!normalizedSource) return null
    return {
      id: buildChoiceId(normalizedSource, type),
      type,
      source: normalizedSource,
      title: normalizedSource.title,
      packageId: normalizedSource.packageId,
      versionInfo: getVersionInfo(currentGameVersion.value, normalizedSource.supportedVersions),
      label: type === 'replacement' ? '替代版' : type === 'installed' ? '已安装' : type === 'current' ? '当前' : '原版',
    }
  }

  const createInstalledChoice = ({ packageId = '', mod = null, label = '当前', type = 'current' } = {}) => {
    const normalizedPackageId = normalizePackageId(packageId)
    if (!normalizedPackageId || !mod) return null
    const source = collectRuntimeSource(normalizedPackageId, mod)
      || normalizeInstallSource({
        packageId: normalizedPackageId,
        title: modStore.displayModName(normalizedPackageId),
        supportedVersions: mod?.supported_versions || [],
        sourceOrigin: 'runtime',
      }, normalizedPackageId)
    if (!source) return null
    return {
      id: buildChoiceId(source, type),
      type,
      source,
      title: modStore.displayModName(normalizedPackageId),
      packageId: normalizedPackageId,
      versionInfo: getVersionInfo(currentGameVersion.value, mod?.supported_versions || []),
      label,
    }
  }

  const buildReplacementChoiceOptions = ({
    packageId = '',
    mod = null,
    installableOriginalSources = [],
    installableReplacementSources = [],
    installedReplacementSources = [],
    includeCurrent = false,
    includeInstalledReplacements = false,
  } = {}) => {
    const currentChoice = includeCurrent && mod
      ? createInstalledChoice({
        packageId,
        mod,
        label: '当前',
        type: 'current',
      })
      : null

    const originalChoices = (installableOriginalSources || [])
      .map(source => createRowChoice(source, 'original'))
      .filter(Boolean)

    const replacementChoices = (installableReplacementSources || [])
      .map(source => createRowChoice(source, 'replacement'))
      .filter(Boolean)

    const installedReplacementChoices = includeInstalledReplacements
      ? (installedReplacementSources || [])
        .map(source => {
          const replacementPackageId = normalizePackageId(source?.packageId || source?.package_id)
          return createInstalledChoice({
            packageId: replacementPackageId,
            mod: modStore.takeModById(replacementPackageId),
            label: '已安装',
            type: 'installed',
          })
        })
        .filter(Boolean)
      : []

    return [
      ...(currentChoice ? [currentChoice] : []),
      ...installedReplacementChoices,
      ...sortChoiceOptions([...originalChoices, ...replacementChoices]),
    ]
  }

  const isInstallableChoice = (choice = null) => {
    const source = choice?.source
    return !!source && !isInstalledBySource(source)
  }

  const sortChoiceOptions = (choices = []) => {
    const choiceMap = new Map()
    ;(choices || []).filter(Boolean).forEach(choice => {
      if (!choice?.id || choiceMap.has(choice.id)) return
      choiceMap.set(choice.id, choice)
    })
    return sortSources(
      Array.from(choiceMap.values()).map(choice => choice.source),
      { preferReplacement: true }
    )
      .map(source => Array.from(choiceMap.values()).find(choice => getInstallSourceKey(choice.source) === getInstallSourceKey(source)))
      .filter(Boolean)
  }

  const buildMissingDependencyOwnerMap = (activeIds = []) => {
    const ownerMap = new Map()
    const normalizedActiveIds = dedupeNormalizedPackageIds(activeIds)
    normalizedActiveIds.forEach(ownerId => {
      if (!modStore.hasRealModById(ownerId)) return
      const owner = modStore.takeModById(ownerId)
      if (isIssueIgnored(owner, ISSUE_TYPE.ERROR_MISSING_DEPENDENCY)) return
      ;(owner?.rules?.dependencies || []).forEach(rule => {
        const baseTargetId = normalizePackageId(rule?.target_id)
        if (!baseTargetId || isExcludedPackageId(baseTargetId)) return
        const alternatives = (rule?.alternatives || []).map(normalizePackageId).filter(Boolean)
        const isSatisfied = [baseTargetId, ...alternatives].some(candidateId => modStore.hasRealModById(candidateId))
        if (isSatisfied) return
        if (!ownerMap.has(baseTargetId)) {
          ownerMap.set(baseTargetId, [])
        }
        const owners = ownerMap.get(baseTargetId)
        if (!owners.includes(ownerId)) {
          owners.push(ownerId)
        }
      })
    })
    return ownerMap
  }

  const buildAnalysisSignature = (activeIds = []) => (
    `${dedupeNormalizedPackageIds(activeIds).join('|')}::${modStore.dataVersion}::${currentGameVersion.value || ''}`
  )

  const buildGroups = (rows = []) => (
    Object.entries(GROUP_META)
      .map(([key, meta]) => {
        const groupRows = (rows || []).filter(row => row.groupKey === key)
        if (groupRows.length === 0) return null
        return {
          key,
          title: meta.title,
          description: meta.description,
          severity: meta.severity || 'info',
          rows: groupRows,
        }
      })
      .filter(Boolean)
  )

  const buildScopedSummary = (baseSummary = EMPTY_SUMMARY, rows = []) => {
    const scopedRows = rows || []
    const dangerTotal = scopedRows.filter(row => GROUP_SEVERITY[row.groupKey] === 'danger').length
    const warnTotal = scopedRows.filter(row => GROUP_SEVERITY[row.groupKey] === 'warn').length
    const infoTotal = scopedRows.filter(row => GROUP_SEVERITY[row.groupKey] === 'info').length
    return {
      ...baseSummary,
      dangerTotal,
      warnTotal,
      infoTotal,
      actionableTotal: scopedRows.length,
      visibleEntryTotal: dangerTotal + warnTotal,
    }
  }

  const collectUnknownDependencyOwnerIds = (unknownItems = []) => (
    dedupeNormalizedPackageIds(
      (unknownItems || [])
        .filter(item => !item?.canCleanup)
        .flatMap(item => item?.ownerIds?.length ? item.ownerIds : (item?.ownerId ? [item.ownerId] : []))
    )
  )

  const buildAnalysis = async (activeIds = []) => {
    const normalizedActiveIds = dedupeNormalizedPackageIds(activeIds)
    const initialSignature = buildAnalysisSignature(normalizedActiveIds)
    if (cachedAnalysis.value.signature === initialSignature) {
      return cachedAnalysis.value.payload
    }

    const dependencyOwnerMap = buildMissingDependencyOwnerMap(normalizedActiveIds)
    const relevantIds = dedupeNormalizedPackageIds([
      ...normalizedActiveIds,
      ...dependencyOwnerMap.keys(),
    ]).filter(packageId => !isExcludedPackageId(packageId))

    await modStore.fetchAndCacheGhostMods(relevantIds)
    const signature = buildAnalysisSignature(normalizedActiveIds)
    if (cachedAnalysis.value.signature === signature) {
      return cachedAnalysis.value.payload
    }
    const installSourceMap = await workspaceStore.getInstallSourcesByPackageIdsMap(relevantIds)

    const missingSubjectMap = new Map()
    normalizedActiveIds.forEach(packageId => {
      if (isExcludedPackageId(packageId) || modStore.hasRealModById(packageId)) return
      missingSubjectMap.set(packageId, {
        packageId,
        fromActiveList: true,
        fromDependency: false,
      })
    })
    dependencyOwnerMap.forEach((owners, packageId) => {
      if (isExcludedPackageId(packageId) || modStore.hasRealModById(packageId)) return
      const subject = missingSubjectMap.get(packageId) || {
        packageId,
        fromActiveList: false,
        fromDependency: false,
      }
      subject.fromDependency = true
      subject.dependencyOwners = owners
      missingSubjectMap.set(packageId, subject)
    })

    const rows = []
    const unknownActiveIds = []
    const summary = { ...EMPTY_SUMMARY }
    const unknownItems = []
    const unknownOwnerMap = new Map()

    for (const subject of missingSubjectMap.values()) {
      const { packageId } = subject
      const { mod, originalSources, replacementSources } = resolveSourcesForPackage(packageId, installSourceMap)
      const installableOriginalSources = originalSources.filter(source => !isInstalledBySource(source))
      const installedReplacementSources = replacementSources.filter(source => isInstalledBySource(source))
      const installableReplacementSources = replacementSources.filter(source => !isInstalledBySource(source))
      const hasInstalledSupportedReplacement = installedReplacementSources.some(source => supportsCurrentGameVersion(source))

      const choiceOptions = buildReplacementChoiceOptions({
        packageId,
        mod,
        installableOriginalSources,
        installableReplacementSources,
        installedReplacementSources,
        includeInstalledReplacements: hasInstalledSupportedReplacement,
      })

      if (choiceOptions.length > 0) {
        const reasonLabels = []
        if (subject.fromActiveList) reasonLabels.push('缺失项')
        if (subject.fromDependency) reasonLabels.push('依赖缺失')
        if (hasInstalledSupportedReplacement) {
          reasonLabels.push('已装替代')
        }
        const defaultChoice = choiceOptions.find(choice => !isInstallableChoice(choice)) || choiceOptions[0]
        let groupKey = 'missing_install'
        if (hasInstalledSupportedReplacement) {
          groupKey = 'missing_with_installed_replacement'
        } else if (installableReplacementSources.length > 0) {
          groupKey = subject.fromDependency ? 'missing_with_replacement_choice' : 'missing_install'
        }
        rows.push({
          id: `missing:${packageId}`,
          groupKey,
          packageId,
          title: modStore.displayModName(packageId),
          reasonLabels,
          choiceOptions,
          defaultChoiceId: defaultChoice?.id || '',
          defaultSelected: isInstallableChoice(defaultChoice),
        })
      } else if (!hasInstalledSupportedReplacement) {
        summary.unknownTotal += 1
        if (subject.fromActiveList) {
          unknownActiveIds.push(packageId)
        }
        if (subject.fromActiveList) {
          const reasonLabels = ['缺失项']
          unknownItems.push({
            id: `unknown:${packageId}`,
            packageId,
            title: modStore.displayModName(packageId),
            reasonLabels,
            canCleanup: true,
            detailLines: [],
          })
        }
        if (subject.fromDependency) {
          ;(subject.dependencyOwners || []).forEach(ownerId => {
            const normalizedOwnerId = normalizePackageId(ownerId)
            if (!normalizedOwnerId) return
            if (!unknownOwnerMap.has(normalizedOwnerId)) {
              unknownOwnerMap.set(normalizedOwnerId, {
                id: `unknown-owner:${normalizedOwnerId}`,
                ownerId: normalizedOwnerId,
                ownerIds: [normalizedOwnerId],
                title: modStore.displayModName(normalizedOwnerId),
                reasonLabels: ['依赖未知'],
                canCleanup: false,
                unknownDependencyIds: [],
              })
            }
            const ownerEntry = unknownOwnerMap.get(normalizedOwnerId)
            if (!ownerEntry.unknownDependencyIds.includes(packageId)) {
              ownerEntry.unknownDependencyIds.push(packageId)
            }
          })
        }
      }
    }

    unknownOwnerMap.forEach(ownerEntry => {
      const detailLines = ownerEntry.unknownDependencyIds.map(depId => modStore.displayModName(depId))
      unknownItems.push({
        ...ownerEntry,
        unknownDependencyCount: ownerEntry.unknownDependencyIds.length,
        detailLines,
      })
    })

    normalizedActiveIds
      .filter(packageId => !isExcludedPackageId(packageId))
      .forEach(packageId => {
        if (!modStore.hasRealModById(packageId)) return
        const mod = modStore.takeModById(packageId)
        const versionInfo = getVersionInfo(currentGameVersion.value, mod?.supported_versions || [])
        if (versionInfo.tone === 'danger') return
        const { replacementSources } = resolveSourcesForPackage(packageId, installSourceMap)
        const installableReplacementSources = replacementSources.filter(source => !isInstalledBySource(source))
        if (installableReplacementSources.length === 0) return
        const choiceOptions = buildReplacementChoiceOptions({
          packageId,
          mod,
          installableReplacementSources,
          includeCurrent: true,
        })
        if (choiceOptions.length <= 1) return
        rows.push({
          id: `optional:${packageId}`,
          groupKey: 'optional_install',
          packageId,
          title: modStore.displayModName(packageId),
          reasonLabels: ['可选补装'],
          choiceOptions,
          defaultChoiceId: choiceOptions.find(choice => choice?.type === 'current')?.id || choiceOptions[0]?.id || '',
          defaultSelected: false,
        })
      })

    rows.push(...collectVersionReplacementWarnings(normalizedActiveIds, installSourceMap))

    Object.assign(summary, buildScopedSummary(summary, rows))
    const payload = {
      rows,
      groups: buildGroups(rows),
      unknownItems,
      summary,
      unknownActiveIds: dedupeNormalizedPackageIds(unknownActiveIds),
    }
    cachedAnalysis.value = { signature, payload }
    return payload
  }

  const getSummaryForActiveList = async (activeIds = modStore.activeIds) => {
    const analysis = await buildAnalysis(activeIds)
    return { ...(analysis.summary || EMPTY_SUMMARY) }
  }

  const resetState = () => {
    isVisible.value = false
    state.title = '缺失项安装管理'
    state.message = '处理未安装模组。'
    state.cancelText = '取消'
    state.cleanupText = ''
    state.cleanupShouldContinue = false
    state.continueText = ''
    state.continueResult = false
    state.disableRelatedText = ''
    state.disableRelatedOwnerIds = []
    state.groups = []
    state.unknownItems = []
    state.summary = { ...EMPTY_SUMMARY }
    Object.keys(selections).forEach(key => delete selections[key])
    Object.keys(choiceSelections).forEach(key => delete choiceSelections[key])
  }

  const finalizeDialog = (result = null) => {
    isVisible.value = false
    resolvePromise?.(result)
    resolvePromise = null
  }

  const applyRowDefaults = (rows = visibleRows.value) => {
    ;(rows || []).forEach(row => {
      selections[row.id] = row.defaultSelected !== false
      choiceSelections[row.id] = row.defaultChoiceId || row.choiceOptions?.[0]?.id || ''
    })
  }

  const applyAnalysisToState = (analysis = null) => {
    state.groups = analysis?.groups || []
    state.unknownItems = analysis?.unknownItems || []
    state.summary = { ...(analysis?.summary || EMPTY_SUMMARY) }
  }

  const openForActiveList = async (activeIds = modStore.activeIds) => {
    resetState()
    const analysis = await buildAnalysis(activeIds)
    state.message = analysis.summary.unknownTotal > 0
      ? '处理未安装模组，或清理无效项。'
      : '处理未安装模组。'
    state.cleanupText = (analysis.unknownActiveIds || []).length > 0 ? '清理未知项' : ''
    state.cleanupShouldContinue = false
    const disableRelatedOwnerIds = collectUnknownDependencyOwnerIds(analysis.unknownItems || [])
    state.disableRelatedText = disableRelatedOwnerIds.length > 0 ? '停用相关模组' : ''
    state.disableRelatedOwnerIds = disableRelatedOwnerIds
    applyAnalysisToState(analysis)
    applyRowDefaults()

    if (analysis.summary.actionableTotal === 0 && analysis.summary.unknownTotal === 0) {
      const message = '当前没有可处理的未安装项。'
      toast.info(message)
      return false
    }

    isVisible.value = true
    return true
  }

  const openPrecheckDialog = async ({
    analysis,
    title,
    message,
    cancelText,
    cleanupText = '',
    cleanupShouldContinue = false,
    continueText = '',
    continueResult = false,
    disableRelatedText = '',
    disableRelatedOwnerIds = [],
  }) => {
    resetState()
    state.title = title
    state.message = message
    state.cancelText = cancelText
    state.cleanupText = cleanupText
    state.cleanupShouldContinue = cleanupShouldContinue
    state.continueText = continueText
    state.continueResult = continueResult
    state.disableRelatedText = disableRelatedText
    state.disableRelatedOwnerIds = dedupeNormalizedPackageIds(disableRelatedOwnerIds)
    applyAnalysisToState(analysis)
    applyRowDefaults()

    isVisible.value = true
    return new Promise(resolve => {
      resolvePromise = resolve
    })
  }

  const close = (result = false) => {
    finalizeDialog(result)
  }

  const continueCurrentAction = () => {
    finalizeDialog(!!state.continueResult)
  }

  const toggleRow = (rowId, checked) => {
    const row = visibleRows.value.find(item => item.id === rowId)
    if (!row) return
    if (!checked) {
      selections[rowId] = false
      return
    }
    const selectedChoice = getSelectedChoice(row)
    if (selectedChoice?.type === 'installed') {
      selections[rowId] = true
      return
    }
    if (isInstallableChoice(selectedChoice)) {
      selections[rowId] = true
      return
    }
    const installableChoice = (row.choiceOptions || []).find(choice => isInstallableChoice(choice))
    if (installableChoice?.id) {
      choiceSelections[rowId] = installableChoice.id
      selections[rowId] = true
      return
    }
    selections[rowId] = false
  }
  const isSelected = (rowId) => !!selections[rowId]

  const setChoice = (rowId, choiceId) => {
    if (!rowId || !choiceId) return
    choiceSelections[rowId] = choiceId
    const row = visibleRows.value.find(item => item.id === rowId)
    const choice = row?.choiceOptions?.find(option => option.id === choiceId) || null
    selections[rowId] = choice?.type === 'installed' || isInstallableChoice(choice)
  }

  const getSelectedChoice = (row) => {
    if (!row?.choiceOptions?.length) return null
    const selectedId = choiceSelections[row.id] || row.defaultChoiceId
    return row.choiceOptions.find(choice => choice.id === selectedId) || row.choiceOptions[0] || null
  }

  const getSelectedSource = (row) => getSelectedChoice(row)?.source || null

  const getRowVersionInfo = (row) => (
    getSelectedChoice(row)?.versionInfo || getVersionInfo(currentGameVersion.value)
  )

  const getSelectedSources = () => (
    selectedRows.value
      .map(row => getSelectedSource(row))
      .filter(source => source && !isInstalledBySource(source))
  )

  const getSelectedInstalledReplacementRows = () => (
    selectedRows.value.filter(row => {
      if (row?.groupKey !== 'missing_with_installed_replacement') return false
      const choice = getSelectedChoice(row)
      return choice?.type === 'installed'
    })
  )

  const selectAll = () => {
    visibleRows.value.forEach(row => {
      const installableChoice = (row.choiceOptions || []).find(choice => isInstallableChoice(choice)) || null
      if (installableChoice?.id) {
        choiceSelections[row.id] = installableChoice.id
        selections[row.id] = true
        return
      }
      selections[row.id] = false
    })
  }

  const clearSelection = () => {
    visibleRows.value.forEach(row => {
      selections[row.id] = false
    })
  }

  const applyInstalledReplacementSelections = async () => {
    const replacementRows = getSelectedInstalledReplacementRows()
    if (replacementRows.length === 0) return false

    const originalIds = dedupeNormalizedPackageIds(replacementRows.map(row => row?.packageId))
    const replacementIds = dedupeNormalizedPackageIds(
      replacementRows.map(row => getSelectedChoice(row)?.packageId)
    ).filter(id => modStore.hasRealModById(id))

    if (originalIds.length === 0 || replacementIds.length === 0) return false

    return await modStore.runListHistoryTransaction({
      type: 'switch-installed-replacements',
      label: `切换 ${replacementIds.length} 个已装替代`,
      trackedModIds: [...originalIds, ...replacementIds],
    }, async () => {
      modStore.removeUnavailableIdsCompletely(originalIds)
      modStore.removeIdsOnAllList(replacementIds)
      await modStore.smartInsertMods(replacementIds)
      modStore.takeModListByIds(replacementIds).forEach(mod => {
        mod.last_moved_time = Date.now()
        mod.last_active_time = Date.now()
      })
      modStore.updateInactiveIds()
    })
  }

  const executeSelectedAction = async (executor, emptyMessage) => {
    const sources = getSelectedSources()
    const hasReplacementSwitches = getSelectedInstalledReplacementRows().length > 0

    if (sources.length === 0 && !hasReplacementSwitches) {
      toast.info(emptyMessage)
      return false
    }

    let switched = false
    if (hasReplacementSwitches) {
      switched = await applyInstalledReplacementSelections()
      if (!switched && sources.length === 0) return false
    }

    let success = true
    if (sources.length > 0) {
      success = await executor(sources)
    }

    if (switched || success) {
      finalizeDialog(false)
    }
    return switched || success
  }

  const subscribeSelected = async () => (
    await executeSelectedAction(
      async (sources) => await appStore.subscribeInstallSources(sources),
      '当前没有选中的可订阅项'
    )
  )

  const downloadSelected = async () => (
    await executeSelectedAction(
      async (sources) => await appStore.downloadInstallSources(sources),
      '当前没有选中的可下载项'
    )
  )

  const cleanupUnknownActiveItems = async (unknownActiveIds = []) => {
    const removableIds = dedupeNormalizedPackageIds(
      (unknownActiveIds || []).filter(id => !modStore.hasRealModById(id))
    )
    if (removableIds.length === 0) return 0
    await modStore.runListHistoryTransaction({
      type: 'batch-remove-list-items',
      label: `清理 ${removableIds.length} 个未知项`,
      trackedModIds: removableIds,
    }, async () => {
      modStore.removeUnavailableIdsCompletely(removableIds)
    })
    return removableIds.length
  }

  const cleanupUnknownItems = async () => {
    const analysis = await buildAnalysis(modStore.activeIds)
    const removedCount = await cleanupUnknownActiveItems(analysis.unknownActiveIds || [])
    if (removedCount === 0) {
      toast.info('当前没有可清理的未知项')
      return false
    }
    const nextAnalysis = await buildAnalysis(modStore.activeIds)
    if (state.cleanupShouldContinue && nextAnalysis.summary.dangerTotal === 0 && nextAnalysis.summary.unknownTotal === 0) {
      finalizeDialog(true)
      return true
    }
    if (state.cleanupShouldContinue) {
      toast.warning('已清理未知项，但当前仍有其它问题需要处理。', { timeout: 2400 })
      finalizeDialog(false)
      return false
    }
    state.cleanupText = (nextAnalysis.unknownActiveIds || []).length > 0 ? '清理未知项' : ''
    applyAnalysisToState(nextAnalysis)
    if (nextAnalysis.summary.actionableTotal === 0 && nextAnalysis.summary.unknownTotal === 0) {
      toast.success(`已清理 ${removedCount} 个未知项`, { timeout: 1800 })
      finalizeDialog(false)
      return true
    }
    toast.success(`已清理 ${removedCount} 个未知项`, { timeout: 1800 })
    return false
  }

  const disableRelatedOwners = async () => {
    const ownerIds = dedupeNormalizedPackageIds(state.disableRelatedOwnerIds || [])
      .filter(id => modStore.hasRealModById(id))
    if (ownerIds.length === 0) {
      toast.info('当前没有可停用的相关模组')
      return false
    }
    const success = await modStore.changeModsActive(ownerIds, false)
    if (!success) return false
    if (state.cleanupShouldContinue) {
      finalizeDialog(true)
      return true
    }
    finalizeDialog(false)
    return true
  }

  const ensureResolvedBeforeAction = async ({
    activeIds = modStore.activeIds,
    actionLabel = '保存',
  } = {}) => {
    if (appStore.settings.enable_action_prechecks === false) return true
    const analysis = await buildAnalysis(activeIds)
    if (analysis.summary.dangerTotal === 0 && analysis.summary.unknownTotal === 0) return true

    const hasRequired = analysis.summary.dangerTotal > 0
    const hasUnknown = (analysis.summary.unknownTotal || 0) > 0
    const unknownActiveCount = (analysis.unknownActiveIds || []).length
    const dependencyOnlyUnknownCount = Math.max(
      0,
      (analysis.summary.unknownTotal || 0) - (analysis.unknownActiveIds || []).length
    )

    const disableRelatedOwnerIds = collectUnknownDependencyOwnerIds(analysis.unknownItems || [])

    if (hasRequired) {
      const unknownText = hasUnknown ? `，另有 ${analysis.summary.unknownTotal} 项暂时找不到可用来源` : ''
      const result = await openPrecheckDialog({
        analysis,
        title: `${actionLabel}前发现未安装项`,
        message: `发现 ${analysis.summary.dangerTotal} 项未安装${unknownText}。`,
        cancelText: `取消${actionLabel}`,
        cleanupText: (analysis.unknownActiveIds || []).length > 0 ? '清理未知项' : '',
        disableRelatedText: disableRelatedOwnerIds.length > 0
          ? `停用相关模组并继续${actionLabel}`
          : '',
        disableRelatedOwnerIds,
        continueText: `不处理继续${actionLabel}`,
        continueResult: true,
      })
      return !!result
    }

    const cleanupText = unknownActiveCount > 0
      ? `清理未知项并继续${actionLabel}`
      : ''
    const disableRelatedText = disableRelatedOwnerIds.length > 0
      ? `停用相关模组并继续${actionLabel}`
      : ''
    const hasOnlyUnknownDependencyTargets = unknownActiveCount === 0 && dependencyOnlyUnknownCount > 0
    const result = await openPrecheckDialog({
      analysis,
      title: hasOnlyUnknownDependencyTargets
        ? `${actionLabel}前发现未知依赖目标`
        : `${actionLabel}前发现未知项`,
      message: hasOnlyUnknownDependencyTargets
        ? `发现 ${dependencyOnlyUnknownCount} 项未知依赖目标。`
        : `发现 ${analysis.summary.unknownTotal} 项暂时找不到可用来源。`,
      cancelText: `取消${actionLabel}`,
      cleanupText,
      cleanupShouldContinue: true,
      continueText: `不处理继续${actionLabel}`,
      continueResult: true,
      disableRelatedText,
      disableRelatedOwnerIds,
    })
    return !!result
  }

  const openSource = (target) => {
    const source = target?.kind ? target : getSelectedSource(target)
    if (!source) return
    appStore.openInstallSource(source)
  }

  return {
    isVisible,
    state,
    visibleRows,
    selectedCount,
    totalCount,
    isSelected,
    getSummaryForActiveList,
    getVersionTooltip,
    getRowVersionInfo,
    getSelectedChoice,
    getSelectedSource,
    openForActiveList,
    ensureResolvedBeforeAction,
    close,
    toggleRow,
    setChoice,
    selectAll,
    clearSelection,
    subscribeSelected,
    downloadSelected,
    cleanupUnknownItems,
    continueCurrentAction,
    disableRelatedOwners,
    openSource,
  }
})
