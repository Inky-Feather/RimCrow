import { readFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'

export async function resolve(specifier, context, nextResolve) {
  if (specifier === 'vue-toastification') {
    return { url: 'virtual:vue-toastification', shortCircuit: true }
  }
  try {
    return await nextResolve(specifier, context)
  } catch (error) {
    if ((specifier.startsWith('.') || specifier.startsWith('/')) && !/\.[a-z0-9]+$/i.test(specifier)) {
      return nextResolve(`${specifier}.js`, context)
    }
    throw error
  }
}

export async function load(url, context, nextLoad) {
  if (url === 'virtual:vue-toastification') {
    return {
      format: 'module',
      shortCircuit: true,
      source: 'export const globalEventBus = {}; export const createToastInterface = () => ({ success(){}, error(){}, warning(){}, info(){} }); export default {}',
    }
  }
  if (url.endsWith('/src/shared/i18n.js')) {
    return {
      format: 'module',
      shortCircuit: true,
      source: `
        export const DEFAULT_LOCALE = 'zh-CN'
        export const UNTRANSLATED_PREFIX = '[UNTRANSLATED] '
        export const localeRevision = { value: 0 }
        export const deepMerge = (base = {}, override = {}) => ({ ...base, ...override })
        export const stripUntranslatedPrefix = (text = '') => String(text || '').replace(UNTRANSLATED_PREFIX, '')
        export const getBuiltinLocaleOptions = () => []
        export const i18n = { global: { locale: { value: DEFAULT_LOCALE }, t: (_key, params) => params?.default || '' } }
        export const getLocaleMessagesForManagement = async () => ({})
        export const setLocale = async (language = DEFAULT_LOCALE) => language
        export const getCurrentLocale = () => DEFAULT_LOCALE
        export const t = (_key = '', defaultText = '', params = {}) => String(defaultText || '').replace(/\\{(\\w+)\\}/g, (_, key) => params[key] ?? '')
        export const findTranslationEntriesForText = () => []
        export const findTranslationEntryByKey = () => null
        export const getTranslationValidationIssue = () => null
        export const translateMessagePayload = (_payload = {}, fallback = '') => fallback
      `,
    }
  }
  if (url.endsWith('.svg') || url.endsWith('.css')) {
    return { format: 'module', shortCircuit: true, source: 'export default ""' }
  }
  if (url.endsWith('.json')) {
    const content = await readFile(fileURLToPath(url), 'utf8')
    return { format: 'module', shortCircuit: true, source: `export default ${content}` }
  }
  return nextLoad(url, context)
}
