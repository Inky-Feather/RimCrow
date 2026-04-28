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
import { useConfirmStore } from './confirmStore'
import { useModStore } from './modStore'
import { useProfileStore } from './profileStore'
import { useWorkspaceStore } from './workspaceStore'

const GROUP_META = {
  missing_with_installed_replacement: {
    title: '已装替代的缺失项',
    description: '原模组未安装，但已经有可用的替代模组。需要的话也可以补装原模组。',
  },
  missing_with_replacement_choice: {
    title: '缺失/替代候选',
    description: '原模组未安装，可以选择安装原模组或替代模组。',
  },
  optional_install: {
    title: '可选安装',
    description: '当前模组已经可用，另外还有可选的替代模组可以安装。',
  },
  missing_install: {
    title: '缺失安装',
    description: '原模组未安装，但可以直接安装。',
  },
}

const EMPTY_SUMMARY = {
  missingTotal: 0,
  installableTotal: 0,
  unknownTotal: 0,
  optionalInstallTotal: 0,
  actionableTotal: 0,
  alreadyInstalledReplacementTotal: 0,
}

const buildChoiceId = (source = {}, fallbackType = 'original') => {
  const key = getInstallSourceKey(source)
  return key ? `${fallbackType}:${key}` : ''
}

export const useMissingInstallStore = defineStore('missingInstall', () => {
  const toast = createToastInterface()
  const appStore = useAppStore()
  const confirmStore = useConfirmStore()
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
      summary: { ...EMPTY_SUMMARY },
      unknownActiveIds: [],
    },
  })
  const state = reactive({
    title: '缺失项安装管理',
    message: '处理当前列表中未安装的项目。',
    cancelText: '取消',
    cleanupText: '',
    groups: [],
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
      label: type === 'replacement' ? '替代版' : '原版',
    }
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
          rows: groupRows,
        }
      })
      .filter(Boolean)
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
    const summary = {
      ...EMPTY_SUMMARY,
      missingTotal: missingSubjectMap.size,
    }

    for (const subject of missingSubjectMap.values()) {
      const { packageId } = subject
      const { mod, originalSources, replacementSources } = resolveSourcesForPackage(packageId, installSourceMap)
      const installableOriginalSources = originalSources.filter(source => !isInstalledBySource(source))
      const installedReplacementSources = replacementSources.filter(source => isInstalledBySource(source))
      const installableReplacementSources = replacementSources.filter(source => !isInstalledBySource(source))
      const hasInstalledSupportedReplacement = installedReplacementSources.some(source => supportsCurrentGameVersion(source))

      const choiceOptions = []
      const bestOriginal = installableOriginalSources[0] || null
      const bestReplacement = installableReplacementSources[0] || null
      if (bestOriginal && bestReplacement) {
        choiceOptions.push(createRowChoice(bestOriginal, 'original'))
        choiceOptions.push(createRowChoice(bestReplacement, 'replacement'))
      } else if (bestOriginal) {
        choiceOptions.push(createRowChoice(bestOriginal, 'original'))
      } else if (bestReplacement) {
        choiceOptions.push(createRowChoice(bestReplacement, 'replacement'))
      }

      if (choiceOptions.length > 0) {
        summary.installableTotal += 1
        const reasonLabels = []
        if (subject.fromActiveList) reasonLabels.push('缺失项')
        if (subject.fromDependency) reasonLabels.push('缺失依赖')
        if (hasInstalledSupportedReplacement) {
          reasonLabels.push('已装替代')
          summary.alreadyInstalledReplacementTotal += 1
        }
        const sortedChoices = sortSources(choiceOptions.map(choice => choice.source), { preferReplacement: true })
          .map(source => choiceOptions.find(choice => getInstallSourceKey(choice.source) === getInstallSourceKey(source)))
          .filter(Boolean)
        const defaultChoice = sortedChoices[0] || choiceOptions[0]
        let groupKey = 'missing_install'
        if (hasInstalledSupportedReplacement) {
          groupKey = 'missing_with_installed_replacement'
        } else if (installableReplacementSources.length > 0) {
          groupKey = 'missing_with_replacement_choice'
        }
        rows.push({
          id: `missing:${packageId}`,
          groupKey,
          packageId,
          title: modStore.displayModName(packageId),
          reasonLabels,
          choiceOptions,
          defaultChoiceId: defaultChoice?.id || '',
          defaultSelected: !(hasInstalledSupportedReplacement && choiceOptions.length === 1 && defaultChoice?.type === 'original'),
        })
      } else if (!hasInstalledSupportedReplacement) {
        summary.unknownTotal += 1
        if (subject.fromActiveList) {
          unknownActiveIds.push(packageId)
        }
      } else {
        summary.alreadyInstalledReplacementTotal += 1
      }
    }

    normalizedActiveIds
      .filter(packageId => !isExcludedPackageId(packageId))
      .forEach(packageId => {
        if (!modStore.hasRealModById(packageId)) return
        const { replacementSources } = resolveSourcesForPackage(packageId, installSourceMap)
        const installableReplacementSources = replacementSources.filter(source => !isInstalledBySource(source))
        if (installableReplacementSources.length === 0) return
        const choiceOptions = installableReplacementSources
          .map(source => createRowChoice(source, 'replacement'))
          .filter(Boolean)
        if (choiceOptions.length === 0) return
        summary.optionalInstallTotal += 1
        rows.push({
          id: `optional:${packageId}`,
          groupKey: 'optional_install',
          packageId,
          title: modStore.displayModName(packageId),
          reasonLabels: ['可选替代'],
          choiceOptions,
          defaultChoiceId: choiceOptions[0]?.id || '',
          defaultSelected: true,
        })
      })

    summary.actionableTotal = rows.length
    const payload = {
      rows,
      groups: buildGroups(rows),
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
    state.message = '处理当前列表中未安装的项目。'
    state.cancelText = '取消'
    state.cleanupText = ''
    state.groups = []
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

  const openForActiveList = async (activeIds = modStore.activeIds) => {
    resetState()
    const analysis = await buildAnalysis(activeIds)
    state.message = analysis.summary.unknownTotal > 0
      ? '处理当前列表中未安装的项目。另有部分项目暂时找不到可用来源。'
      : '处理当前列表中未安装的项目。'
    state.groups = analysis.groups
    state.summary = { ...analysis.summary }
    applyRowDefaults()

    if (analysis.summary.actionableTotal === 0) {
      const message = analysis.summary.unknownTotal > 0
        ? `当前没有可直接处理的安装项，另有 ${analysis.summary.unknownTotal} 项暂时找不到可用来源。`
        : '当前没有可直接处理的安装项。'
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
  }) => {
    resetState()
    state.title = title
    state.message = message
    state.cancelText = cancelText
    state.cleanupText = cleanupText
    state.groups = analysis.groups
    state.summary = { ...(analysis.summary || EMPTY_SUMMARY) }
    applyRowDefaults()

    isVisible.value = true
    return new Promise(resolve => {
      resolvePromise = resolve
    })
  }

  const close = (result = false) => {
    finalizeDialog(result)
  }

  const toggleRow = (rowId, checked) => {
    selections[rowId] = !!checked
  }
  const isSelected = (rowId) => !!selections[rowId]

  const setChoice = (rowId, choiceId) => {
    if (!rowId || !choiceId) return
    choiceSelections[rowId] = choiceId
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
      .filter(Boolean)
  )

  const selectAll = () => {
    visibleRows.value.forEach(row => {
      selections[row.id] = true
    })
  }

  const clearSelection = () => {
    visibleRows.value.forEach(row => {
      selections[row.id] = false
    })
  }

  const subscribeSelected = async () => {
    const sources = getSelectedSources()
    if (sources.length === 0) {
      toast.info('当前没有选中的可订阅项')
      return false
    }
    const success = await appStore.subscribeInstallSources(sources)
    if (success) finalizeDialog(false)
    return success
  }

  const downloadSelected = async () => {
    const sources = getSelectedSources()
    if (sources.length === 0) {
      toast.info('当前没有选中的可下载项')
      return false
    }
    const success = await appStore.downloadInstallSources(sources)
    if (success) finalizeDialog(false)
    return success
  }

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
      modStore.removeIdsOnAllList(removableIds)
    })
    return removableIds.length
  }

  const cleanupUnknownAndContinue = async () => {
    const analysis = await buildAnalysis(modStore.activeIds)
    const removedCount = await cleanupUnknownActiveItems(analysis.unknownActiveIds || [])
    if (removedCount === 0) {
      toast.info('当前没有可清理的未知项')
      finalizeDialog(false)
      return false
    }
    const nextAnalysis = await buildAnalysis(modStore.activeIds)
    if ((nextAnalysis.summary.missingTotal || 0) === 0) {
      finalizeDialog(true)
      return true
    }
    toast.warning('已清理列表中的未知项，但还有未安装的问题需要处理，所以这次没有继续。', { timeout: 2800 })
    finalizeDialog(false)
    return false
  }

  const ensureResolvedBeforeAction = async ({
    activeIds = modStore.activeIds,
    actionLabel = '保存',
  } = {}) => {
    const analysis = await buildAnalysis(activeIds)
    if ((analysis.summary.missingTotal || 0) === 0) return true

    const hasActionable = (analysis.summary.actionableTotal || 0) > 0
    const hasUnknown = (analysis.summary.unknownTotal || 0) > 0
    const dependencyOnlyUnknownCount = Math.max(
      0,
      (analysis.summary.unknownTotal || 0) - (analysis.unknownActiveIds || []).length
    )

    if (hasActionable) {
      const unknownText = hasUnknown ? `，另有 ${analysis.summary.unknownTotal} 项暂时找不到可用来源` : ''
      await openPrecheckDialog({
        analysis,
        title: `${actionLabel}前发现未安装项`,
        message: `当前列表里有 ${analysis.summary.missingTotal} 项还没安装，其中 ${analysis.summary.actionableTotal} 项现在就能处理${unknownText}。\n你可以先去处理这些项目。处理完成后，请再重新${actionLabel}一次。`,
        cancelText: `取消${actionLabel}`,
      })
      return false
    }

    const cleanupText = (analysis.unknownActiveIds || []).length > 0
      ? `清理未知项并继续${actionLabel}`
      : ''
    const dependencyHint = dependencyOnlyUnknownCount > 0
      ? `\n其中有 ${dependencyOnlyUnknownCount} 项是缺少依赖，清理未知项后，你可能还是需要再处理一次。`
      : ''
    const result = await openPrecheckDialog({
      analysis,
      title: `${actionLabel}前发现未知项`,
      message: `当前列表里有 ${analysis.summary.unknownTotal} 项暂时找不到可用来源。${dependencyHint}`,
      cancelText: `取消${actionLabel}`,
      cleanupText,
    })
    return !!result
  }

  const notifyAfterScan = async (activeIds = modStore.activeIds) => {
    const analysis = await buildAnalysis(activeIds)
    if ((analysis.summary.missingTotal || 0) === 0) return false
    if ((analysis.summary.actionableTotal || 0) > 0) {
      await openForActiveList(activeIds)
      return true
    }
    await confirmStore.alert(
      '扫描后发现未知项',
      `当前列表里有 ${analysis.summary.unknownTotal} 项暂时找不到可用来源。你可以检查一下这些项是否已经取消订阅、被删除，或本来就没有可用来源。`,
      { type: 'warning', confirmText: '知道了' }
    )
    return true
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
    notifyAfterScan,
    close,
    toggleRow,
    setChoice,
    selectAll,
    clearSelection,
    subscribeSelected,
    downloadSelected,
    cleanupUnknownAndContinue,
    openSource,
  }
})
