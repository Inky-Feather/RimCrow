import { ref } from 'vue'
import {
  dedupeInstallSources,
  normalizeInstallSource,
  normalizePackageId,
  normalizeWorkshopId,
} from '../../lib/modIdentity'

export const useInstallSourceHints = ({
  dataVersion,
  arePlainValuesEqual,
} = {}) => {
  const installSourceHints = ref(new Map())

  // 获取安装源提示
  // 安装源提示只来自临时导入、工坊解析等辅助信息，不直接改变 Mod 的持久化数据。
  const getInstallSourceHints = (packageId = '') => {
    const normalizedPackageId = normalizePackageId(packageId)
    if (!normalizedPackageId) return []
    return installSourceHints.value.get(normalizedPackageId) || []
  }

  // 获取首选安装源提示
  const getPreferredInstallSourceHint = (packageId = '') => getInstallSourceHints(packageId)[0] || null

  // 将安装源提示回填到 Mod 展示对象，补齐 workshop_id / url 等前端可用字段。
  const applyInstallSourceHintToMod = (mod = null, packageId = '') => {
    const normalizedPackageId = normalizePackageId(packageId || mod?.package_id)
    const sourceHint = getPreferredInstallSourceHint(normalizedPackageId)
    if (!mod || !sourceHint) return
    if (sourceHint.kind === 'workshop' && !normalizeWorkshopId(mod.workshop_id)) {
      mod.workshop_id = sourceHint.workshopId
    }
    if (!String(mod.url || '').trim() && sourceHint.url) {
      mod.url = sourceHint.url
    }
  }

  // 合并安装源提示
  const mergeInstallSourceHintsFromMods = (mods = [], sourceOrigin = 'import') => {
    const nextMap = new Map(installSourceHints.value)
    let changed = false
    ;(mods || []).forEach(mod => {
      const normalizedPackageId = normalizePackageId(mod?.package_id)
      if (!normalizedPackageId) return
      const hasWorkshopIdRaw = Object.prototype.hasOwnProperty.call(mod || {}, 'workshop_id_raw')
      const hasSourceUrlRaw = Object.prototype.hasOwnProperty.call(mod || {}, 'source_url_raw')
      const rawWorkshopValue = hasWorkshopIdRaw ? String(mod?.workshop_id_raw || '').trim() : ''
      const rawSourceUrl = hasSourceUrlRaw ? String(mod?.source_url_raw || mod?.sourceUrlRaw || '').trim() : ''
      const preferRawOnly = sourceOrigin === 'import' && (hasWorkshopIdRaw || hasSourceUrlRaw)
      const sourceWorkshopId = (() => {
        const rawValue = preferRawOnly ? rawWorkshopValue : (hasWorkshopIdRaw ? mod?.workshop_id_raw : mod?.workshop_id)
        const normalizedValue = String(rawValue || '').trim()
        return normalizedValue === '0' ? '' : normalizedValue
      })()
      const sourceUrl = preferRawOnly
        ? rawSourceUrl
        : (
          hasSourceUrlRaw
            ? (mod?.source_url_raw || mod?.sourceUrlRaw || '')
            : (mod?.source_url || mod?.sourceUrl || mod?.url)
        )
      const normalizedSource = normalizeInstallSource(
        {
          packageId: normalizedPackageId,
          workshopId: sourceWorkshopId,
          url: sourceUrl,
          title: mod?.name || mod?.display_name || mod?.alias_name || normalizedPackageId,
          supportedVersions: mod?.supported_versions || mod?.supportedVersions || [],
          sourceOrigin,
        },
        normalizedPackageId
      )
      const currentSources = nextMap.get(normalizedPackageId) || []
      const baseSources = sourceOrigin === 'import'
        ? currentSources.filter(source => String(source?.sourceOrigin || source?.source_origin || '') !== 'import')
        : currentSources
      if (!normalizedSource) {
        if (!arePlainValuesEqual(currentSources, baseSources)) {
          if (baseSources.length > 0) nextMap.set(normalizedPackageId, baseSources)
          else nextMap.delete(normalizedPackageId)
          changed = true
        }
        return
      }
      const mergedSources = dedupeInstallSources([...baseSources, normalizedSource])
      if (!arePlainValuesEqual(currentSources, mergedSources)) {
        nextMap.set(normalizedPackageId, mergedSources)
        changed = true
      }
    })
    if (changed) {
      installSourceHints.value = nextMap
      dataVersion.value++
    }
    return changed
  }

  // 清除所有安装源提示
  const clearInstallSourceHints = () => {
    installSourceHints.value = new Map()
    dataVersion.value++
  }

  // 清除指定来源的安装源提示
  const clearInstallSourceHintsByOrigin = (sourceOrigin = 'import') => {
    const normalizedOrigin = String(sourceOrigin || '').trim()
    if (!normalizedOrigin) return false
    const nextMap = new Map()
    let changed = false
    installSourceHints.value.forEach((sources, packageId) => {
      const keptSources = (sources || []).filter(source => {
        const origin = String(source?.sourceOrigin || source?.source_origin || '').trim()
        return origin !== normalizedOrigin
      })
      if (keptSources.length !== (sources || []).length) {
        changed = true
      }
      if (keptSources.length > 0) {
        nextMap.set(packageId, keptSources)
      }
    })
    if (changed) {
      installSourceHints.value = nextMap
      dataVersion.value++
    }
    return changed
  }

  return {
    installSourceHints,
    getInstallSourceHints,
    getPreferredInstallSourceHint,
    applyInstallSourceHintToMod,
    mergeInstallSourceHintsFromMods,
    clearInstallSourceHints,
    clearInstallSourceHintsByOrigin,
  }
}
