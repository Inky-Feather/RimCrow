import { normalizePackageId } from './modIdentity'

export const OFFICIAL_PACKAGE_PREFIX = 'ludeon.rimworld'
export const DEFAULT_TOOL_PACKAGE_IDS = new Set(['rmm.companion'])

export const isCorePackageId = (packageId = '') => (
  normalizePackageId(packageId) === OFFICIAL_PACKAGE_PREFIX
)

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

export const isBuiltinManagedPackageId = (packageId = '', toolPackageIds = DEFAULT_TOOL_PACKAGE_IDS) => (
  isCorePackageId(packageId)
  || isOfficialDlcPackageId(packageId)
  || isToolPackageId(packageId, toolPackageIds)
)
