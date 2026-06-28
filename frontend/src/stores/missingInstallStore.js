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
import { useAppStore } from './appStore'
import { useModStore } from './modStore'
import { useProfileStore } from './profileStore'
import { useWorkspaceStore } from './workspaceStore'

const GROUP_META = {
  missing_with_installed_replacement: {
    title: '已装替代的缺失项',
    description: '原版当前缺失，但已存在支持当前版本的替代项安装。可按需补装原版。',
  },
  missing_with_replacement_choice: {
    title: '缺失/替代候选',
    description: '当前原版缺失，且可安装原版或替代版候选。',
  },
  optional_install: {
    title: '可选安装',
    description: '当前原版已安装，但还有未安装的可替代版本可选安装。',
  },
  missing_install: {
    title: '缺失安装',
    description: '当前原版缺失，但可直接安装原版来源。',
  },
}

const TOOL_PACKAGE_IDS = new Set(['rmm.companion'])
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
    },
  })
  const state = reactive({
    title: '缺失项安装管理',
    message: '仅处理未安装来源，不会自动启用模组，也不会自动写盘。',
    groups: [],
    summary: { ...EMPTY_SUMMARY },
  })

  const visibleRows = computed(() => state.groups.flatMap(group => group.rows || []))
  const selectedRows = computed(() => visibleRows.value.filter(row => !!selections[row.id]))
  const selectedCount = computed(() => selectedRows.value.length)
  const totalCount = computed(() => visibleRows.value.length)
  const currentGameVersion = computed(() => normalizeVersion(profileStore.activeContext?.game_version))

  const isCoreId = (packageId = '') => normalizePackageId(packageId) === 'ludeon.rimworld'
  const isOfficialDlcId = (packageId = '') => normalizePackageId(packageId).startsWith('ludeon.rimworld.')
  const isToolModId = (packageId = '') => TOOL_PACKAGE_IDS.has(normalizePackageId(packageId))
  const isExcludedPackageId = (packageId = '') => (
    isCoreId(packageId) || isOfficialDlcId(packageId) || isToolModId(packageId)
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
    // 缺失幽灵项的 workshop/url 来自外部补全，不代表原版真实来源，不能混进 original source。
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
    state.groups = []
    state.summary = { ...EMPTY_SUMMARY }
    Object.keys(selections).forEach(key => delete selections[key])
    Object.keys(choiceSelections).forEach(key => delete choiceSelections[key])
  }

  const openForActiveList = async (activeIds = modStore.activeIds) => {
    resetState()
    const analysis = await buildAnalysis(activeIds)
    state.groups = analysis.groups
    state.summary = { ...analysis.summary }

    visibleRows.value.forEach(row => {
      selections[row.id] = row.defaultSelected !== false
      choiceSelections[row.id] = row.defaultChoiceId || row.choiceOptions?.[0]?.id || ''
    })

    if (analysis.summary.actionableTotal === 0) {
      const message = analysis.summary.unknownTotal > 0
        ? `当前没有可处理的安装来源，另有 ${analysis.summary.unknownTotal} 项缺失无法定位来源。`
        : '当前没有可处理的安装来源。'
      toast.info(message)
      return false
    }

    isVisible.value = true
    return true
  }

  const close = () => {
    isVisible.value = false
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
      toast.info('当前没有选中的可订阅项目')
      return false
    }
    const success = await appStore.subscribeInstallSources(sources)
    if (success) close()
    return success
  }

  const downloadSelected = async () => {
    const sources = getSelectedSources()
    if (sources.length === 0) {
      toast.info('当前没有选中的可下载项目')
      return false
    }
    const success = await appStore.downloadInstallSources(sources)
    if (success) close()
    return success
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
    close,
    toggleRow,
    setChoice,
    selectAll,
    clearSelection,
    subscribeSelected,
    downloadSelected,
    openSource,
  }
})
