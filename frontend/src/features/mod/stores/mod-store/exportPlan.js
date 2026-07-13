import { computed } from 'vue'
import { normalizePackageToken } from '../../lib/modIdentity'

export const useModExportPlan = ({
  activeIds,
  inactiveIds,
  tempIds,
  interlocksMap,
  appSettings,
  currentLanguage,
  normalizeCanonicalId,
  takeModById,
  isExportableRuntimeMod,
  isLanguagePackMod,
  canUseLanguagePackForIssueDetection,
  getLanguagePackOwnerIds,
  isDeclaredForCurrentLanguage,
} = {}) => {
  // 当前界面可见的规范化 Mod ID，作为导出范围的基础集合。
  const currentVisibleCanonicalIds = computed(() => [
    ...new Set([
      ...activeIds.value,
      ...inactiveIds.value,
      ...tempIds.value,
    ].map(normalizeCanonicalId).filter(Boolean)),
  ])

  // 导出范围按规范包名去重，但要保留列表中的实例 token，供后端选择对应原生规则。
  const visibleTokenByCanonicalId = computed(() => {
    const result = new Map()
    ;[...activeIds.value, ...inactiveIds.value, ...tempIds.value].forEach(rawId => {
      const token = normalizePackageToken(rawId)
      const canonicalId = normalizeCanonicalId(token)
      if (canonicalId && !result.has(canonicalId)) result.set(canonicalId, token)
    })
    return result
  })
  const preferredTokenForId = (rawId = '') => {
    const token = normalizePackageToken(rawId)
    const canonicalId = normalizeCanonicalId(token)
    return token.endsWith('_steam') || token.endsWith('_local')
      ? token
      : (visibleTokenByCanonicalId.value.get(canonicalId) || canonicalId)
  }

  // 只保留运行时可导出的 Mod，过滤缺失项和非本地/自建/工坊路径项。
  const exportableModsMap = computed(() => {
    const result = new Map()
    for (const canonicalId of currentVisibleCanonicalIds.value) {
      const mod = takeModById(preferredTokenForId(canonicalId))
      if (!canonicalId || !isExportableRuntimeMod(mod)) continue
      result.set(canonicalId, mod)
    }
    return result
  })

  const exportableVisibleIds = computed(() => Array.from(exportableModsMap.value.keys()))
  const exportableVisibleIdSet = computed(() => new Set(exportableVisibleIds.value))
  const exportableActiveIds = computed(() => (
    activeIds.value
      .map(id => normalizeCanonicalId(id))
      .filter(id => id && exportableVisibleIdSet.value.has(id))
  ))
  const exportableActiveIdSet = computed(() => new Set(exportableActiveIds.value))
  const exportableVisibleCount = computed(() => exportableVisibleIds.value.length)
  const exportableActiveCount = computed(() => exportableActiveIds.value.length)

  // 从联锁链中挑出当前导出范围内的成员。
  const takeInterlockChainIds = (interlockId = '', scopeSet = exportableVisibleIdSet.value) => {
    const normalizedId = String(interlockId || '').trim()
    if (!normalizedId) return []
    const source = interlocksMap.value
    const chain = source instanceof Map ? source.get(normalizedId) : source?.[normalizedId]
    return Array.isArray(chain)
      ? chain.map(normalizeCanonicalId).filter(id => id && scopeSet.has(id))
      : []
  }

  // 收集导出时需要自动补充的依赖项，优先使用后端 rules，兼容旧字段 dependencies_mods。
  const collectExportDependencyIds = (mod) => {
    const result = []
    const pushDependencyId = (rawId = '') => {
      const dependencyId = normalizeCanonicalId(rawId)
      if (dependencyId && !result.includes(dependencyId)) {
        result.push(dependencyId)
      }
    }
    ;(mod?.rules?.dependencies || []).forEach(dep => pushDependencyId(dep?.target_id || dep?.package_id))
    if (result.length > 0) return result
    ;(mod?.dependencies_mods || []).forEach(dep => pushDependencyId(dep?.package_id))
    return result
  }

  // 导出依赖图：只记录当前可导出集合中的依赖，避免把缺失项带入导出计划。
  const exportDependencyMap = computed(() => {
    const result = new Map()
    exportableModsMap.value.forEach((mod, canonicalId) => {
      result.set(
        canonicalId,
        collectExportDependencyIds(mod).filter(depId => exportableVisibleIdSet.value.has(depId))
      )
    })
    return result
  })

  // 语言包映射分严格命中和兜底命中，严格命中优先用于导出补全。
  const exportLanguagePackMaps = computed(() => {
    const strictMap = new Map()
    const fallbackMap = new Map()
    if (!appSettings.value.check_language_support || !currentLanguage.value) {
      return { strictMap, fallbackMap }
    }
    exportableModsMap.value.forEach(mod => {
      if (!isLanguagePackMod(mod) || !canUseLanguagePackForIssueDetection(mod)) return
      const ownerIds = getLanguagePackOwnerIds(mod)
      if (ownerIds.length === 0) return
      const targetMap = isDeclaredForCurrentLanguage(mod) ? strictMap : fallbackMap
      ownerIds.forEach(ownerId => {
        if (!exportableVisibleIdSet.value.has(ownerId)) return
        if (!targetMap.has(ownerId)) targetMap.set(ownerId, [])
        targetMap.get(ownerId).push(normalizeCanonicalId(mod?.package_id))
      })
    })
    return { strictMap, fallbackMap }
  })

  // 根据导出范围解析基础 ID：当前可见、当前启用，或用户自选。
  const resolveCurrentExportBaseIds = ({
    exportScope = 'custom',
    modIds = [],
  } = {}) => {
    const normalizedScope = String(exportScope || 'custom').trim().toLowerCase()
    if (normalizedScope === 'profile-effective') return exportableVisibleIds.value.map(preferredTokenForId)
    if (normalizedScope === 'profile-active') return activeIds.value
      .map(normalizePackageToken)
      .filter(id => id && exportableVisibleIdSet.value.has(normalizeCanonicalId(id)))
    return [...new Set(
      (modIds || [])
        .map(preferredTokenForId)
        .filter(id => id && exportableVisibleIdSet.value.has(normalizeCanonicalId(id)))
    )]
  }

  // 为指定 owner 挑选一个语言包，优先选择当前启用列表中的严格命中项。
  const pickExportLanguagePackId = (ownerId = '', selectedSet = new Set()) => {
    const owner = exportableModsMap.value.get(ownerId)
    if (!owner || isLanguagePackMod(owner) || isDeclaredForCurrentLanguage(owner)) return ''
    const strictCandidates = (exportLanguagePackMaps.value.strictMap.get(ownerId) || []).filter(candidateId => !selectedSet.has(candidateId))
    const fallbackCandidates = (exportLanguagePackMaps.value.fallbackMap.get(ownerId) || []).filter(candidateId => !selectedSet.has(candidateId))
    const preferredActive = [...strictCandidates, ...fallbackCandidates].find(candidateId => exportableActiveIdSet.value.has(candidateId))
    return preferredActive || strictCandidates[0] || fallbackCandidates[0] || ''
  }

  // 解析最终导出计划，按需迭代补齐依赖、联锁成员和语言包。
  const resolveCurrentExportPlan = ({
    exportScope = 'custom',
    modIds = [],
    includeDependencies = false,
    includeInterlocks = false,
    includeLanguagePacks = false,
  } = {}) => {
    const baseIds = resolveCurrentExportBaseIds({ exportScope, modIds })
    const orderedIds = []
    const selectedSet = new Set()
    const pushModId = (rawId = '') => {
      const canonicalId = normalizeCanonicalId(rawId)
      const packageToken = preferredTokenForId(rawId)
      if (!canonicalId || selectedSet.has(canonicalId) || !exportableVisibleIdSet.value.has(canonicalId)) return false
      selectedSet.add(canonicalId)
      orderedIds.push(packageToken)
      return true
    }

    baseIds.forEach(pushModId)

    let changed = true
    while (changed) {
      changed = false
      const snapshot = [...orderedIds]

      if (includeDependencies) {
        snapshot.forEach(id => {
          const canonicalId = normalizeCanonicalId(id)
          ;(exportDependencyMap.value.get(canonicalId) || []).forEach(depId => {
            if (pushModId(depId)) changed = true
          })
        })
      }

      if (includeInterlocks) {
        snapshot.forEach(id => {
          const canonicalId = normalizeCanonicalId(id)
          takeInterlockChainIds(exportableModsMap.value.get(canonicalId)?.interlock_id, exportableVisibleIdSet.value).forEach(linkedId => {
            if (pushModId(linkedId)) changed = true
          })
        })
      }

      if (includeLanguagePacks) {
        snapshot.forEach(id => {
          const canonicalId = normalizeCanonicalId(id)
          const languagePackId = pickExportLanguagePackId(canonicalId, selectedSet)
          if (pushModId(languagePackId)) changed = true
        })
      }
    }

    return {
      selected_count: baseIds.length,
      mod_count: orderedIds.length,
      extra_count: Math.max(0, orderedIds.length - baseIds.length),
      mod_ids: orderedIds,
    }
  }

  return {
    exportableVisibleCount,
    exportableActiveCount,
    resolveCurrentExportBaseIds,
    resolveCurrentExportPlan,
  }
}
