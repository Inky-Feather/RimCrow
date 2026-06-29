import { normalizePackageId } from './modIdentity'

export const OFFICIAL_PACKAGE_PREFIX = 'ludeon.rimworld'
export const DEFAULT_TOOL_PACKAGE_IDS = new Set(['rimcrow.companion', 'rmm.companion'])

// 本体包是官方体系里最特殊的一项，因此单独提供判断函数。
export const isCorePackageId = (packageId = '') => (
  normalizePackageId(packageId) === OFFICIAL_PACKAGE_PREFIX
)

// 官方 DLC 与本体共享同一前缀。
export const isOfficialPackageId = (packageId = '') => (
  normalizePackageId(packageId).startsWith(`${OFFICIAL_PACKAGE_PREFIX}.`)
  || isCorePackageId(packageId)
)

export const isOfficialDlcPackageId = (packageId = '') => {
  const normalized = normalizePackageId(packageId)
  return normalized.startsWith(`${OFFICIAL_PACKAGE_PREFIX}.`) && normalized !== OFFICIAL_PACKAGE_PREFIX
}

export const isToolPackageId = (packageId = '', toolPackageIds = DEFAULT_TOOL_PACKAGE_IDS) => (
  toolPackageIds.has(normalizePackageId(packageId))
)

// 当前项目内建管理对象包含：本体、官方 DLC、工具伴生包。
export const isBuiltinManagedPackageId = (packageId = '', toolPackageIds = DEFAULT_TOOL_PACKAGE_IDS) => (
  isCorePackageId(packageId)
  || isOfficialDlcPackageId(packageId)
  || isToolPackageId(packageId, toolPackageIds)
)
