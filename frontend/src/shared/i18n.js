import { createI18n } from 'vue-i18n'
import { ref } from 'vue'

export const DEFAULT_LOCALE = 'zh-CN'
export const UNTRANSLATED_PREFIX = '[UNTRANSLATED] '

const translationRegistry = new Map()
export const localeRevision = ref(0)
let localeRequestVersion = 0
const PLACEHOLDER_RE = /\{([A-Za-z_][\w.-]*)\}/g
const LOCALE_MARKER_RE = /\[\[|\]\]|\^\^|!!|__|··/g

const isPlainObject = (value) => value && typeof value === 'object' && !Array.isArray(value)
const cloneMessages = (messages = {}) => JSON.parse(JSON.stringify(isPlainObject(messages) ? messages : {}))

const localeModules = import.meta.glob('../locales/*.json', { eager: true, import: 'default' })
const builtinMessages = Object.fromEntries(Object.values(localeModules)
  .map(messages => [String(messages?._meta?.language || '').trim(), messages])
  .filter(([code, messages]) => code && isPlainObject(messages)))

export const deepMerge = (base = {}, override = {}) => {
  const result = { ...(isPlainObject(base) ? base : {}) }
  Object.entries(isPlainObject(override) ? override : {}).forEach(([key, value]) => {
    result[key] = isPlainObject(value) && isPlainObject(result[key])
      ? deepMerge(result[key], value)
      : value
  })
  return result
}

const formatFallback = (text = '', params = {}) => String(text ?? '').replace(/\{([^{}]+)\}/g, (match, name) => (
  Object.prototype.hasOwnProperty.call(params || {}, name) ? String(params[name] ?? '') : match
))

export const stripUntranslatedPrefix = (text = '') => {
  const value = String(text ?? '')
  return value.startsWith(UNTRANSLATED_PREFIX) ? value.slice(UNTRANSLATED_PREFIX.length) : value
}

const normalizeLookupText = (text = '') => String(text ?? '')
  .replace(/<[^>]*>/g, ' ')
  .replace(/(\^\^|!!|__|\[\[|\]\]|##|··|\*\*)/g, '')
  .replace(/\s+/g, ' ')
  .trim()
  .toLocaleLowerCase()

const recordTranslationEntry = (key, defaultText, rawText, displayText, params = {}) => {
  if (!key || !displayText) return
  translationRegistry.set(key, {
    key,
    defaultText: String(defaultText ?? ''),
    rawText: String(rawText ?? ''),
    currentText: stripUntranslatedPrefix(rawText),
    displayText: String(displayText ?? ''),
    params: { ...(params || {}) },
  })
}

const getMessageByPath = (messages = {}, key = '') => {
  if (!key) return undefined
  const segments = String(key).split('.')
  let current = messages
  for (const segment of segments) {
    if (!isPlainObject(current) || !Object.prototype.hasOwnProperty.call(current, segment)) return undefined
    current = current[segment]
  }
  return typeof current === 'string' || typeof current === 'number' ? String(current) : undefined
}

export const getBuiltinLocaleOptions = () => Object.entries(builtinMessages).map(([code, messages]) => {
  const meta = isPlainObject(messages?._meta) ? messages._meta : {}
  return { label: String(meta.label || code), value: code, code, name: String(meta.name || code), builtin: true, user: false }
})

const normalizeLocale = (language = '') => {
  const value = String(language || '').trim()
  if (!value) return DEFAULT_LOCALE
  const lowered = value.toLowerCase()
  if (lowered === 'zh' || lowered === 'zh-cn' || lowered === 'zh_hans') return 'zh-CN'
  if (lowered.startsWith('en')) return 'en'
  return value
}

export const i18n = createI18n({
  legacy: false,
  locale: DEFAULT_LOCALE,
  fallbackLocale: DEFAULT_LOCALE,
  missingWarn: false,
  fallbackWarn: false,
  messages: Object.fromEntries(Object.entries(builtinMessages).map(([code, messages]) => [code, cloneMessages(messages)])),
})

const loadUserMessages = async (locale) => {
  if (!window.pywebview?.api?.locale_load_user_messages) return { language: locale, messages: {} }
  const res = await window.pywebview.api.locale_load_user_messages(locale)
  if (res?.status !== 'success') {
    const error = new Error(translateMessagePayload(res, '读取用户语言文件失败。'))
    error.response = res
    throw error
  }
  return {
    language: normalizeLocale(res.data?.language || locale),
    messages: res.data?.messages && typeof res.data.messages === 'object' ? res.data.messages : {},
  }
}

export const getLocaleMessagesForManagement = async (language = DEFAULT_LOCALE) => {
  const requestedLocale = normalizeLocale(language)
  const loaded = await loadUserMessages(requestedLocale)
  const locale = loaded.language
  const builtin = cloneMessages(builtinMessages[locale])
  return {
    language: locale,
    base: cloneMessages(builtinMessages[DEFAULT_LOCALE]),
    builtin,
    user: loaded.messages,
    merged: deepMerge(builtin, loaded.messages),
  }
}

export const setLocale = async (language = DEFAULT_LOCALE) => {
  const version = ++localeRequestVersion
  const requestedLocale = normalizeLocale(language)
  let loaded
  try {
    loaded = await loadUserMessages(requestedLocale)
  } catch (error) {
    if (version !== localeRequestVersion) return getCurrentLocale()
    throw error
  }
  if (version !== localeRequestVersion) return getCurrentLocale()
  const locale = loaded.language
  const builtin = cloneMessages(builtinMessages[locale])
  i18n.global.setLocaleMessage(locale, deepMerge(builtin, loaded.messages))
  i18n.global.locale.value = locale
  localeRevision.value += 1
  document.documentElement.lang = locale
  return locale
}

export const getCurrentLocale = () => i18n.global.locale.value || DEFAULT_LOCALE

export const t = (key = '', defaultText = '', params = {}) => {
  localeRevision.value
  const normalizedKey = String(key || '').trim()
  const safeParams = params && typeof params === 'object' ? params : {}
  if (!normalizedKey) return formatFallback(defaultText, safeParams)
  // 项目只使用 {param} 简单插值，直接读取原始 message 可避免 vue-i18n 将 | 解析为复数分支。
  const locale = i18n.global.locale.value || DEFAULT_LOCALE
  const translated = getMessageByPath(i18n.global.getLocaleMessage(locale), normalizedKey)
    ?? getMessageByPath(i18n.global.getLocaleMessage(DEFAULT_LOCALE), normalizedKey)
  const rawText = translated !== undefined ? translated : defaultText
  const displayText = formatFallback(stripUntranslatedPrefix(rawText), safeParams)
  recordTranslationEntry(normalizedKey, defaultText, rawText, displayText, safeParams)
  return displayText
}

export const findTranslationEntriesForText = (text = '') => {
  const lookup = normalizeLookupText(text)
  if (!lookup) return []
  return Array.from(translationRegistry.values())
    .filter(entry => {
      const display = normalizeLookupText(entry.displayText)
      const fallback = normalizeLookupText(entry.defaultText)
      return (display && (display === lookup || lookup.includes(display)))
        || (fallback && (fallback === lookup || lookup.includes(fallback)))
    })
    .sort((left, right) => right.displayText.length - left.displayText.length)
}

export const findTranslationEntryByKey = (key = '') => translationRegistry.get(String(key || '').trim()) || null

export const getTranslationValidationIssue = (source = '', target = '') => {
  const sourceParams = new Set([...String(source ?? '').matchAll(PLACEHOLDER_RE)].map(item => item[1]))
  const targetParams = new Set([...String(target ?? '').matchAll(PLACEHOLDER_RE)].map(item => item[1]))
  if (sourceParams.size !== targetParams.size || [...sourceParams].some(item => !targetParams.has(item))) return 'placeholders'
  const sourceMarkers = String(source ?? '').match(LOCALE_MARKER_RE) || []
  const targetMarkers = String(target ?? '').match(LOCALE_MARKER_RE) || []
  if (sourceMarkers.length !== targetMarkers.length || sourceMarkers.some((item, index) => item !== targetMarkers[index])) return 'markers'
  return ''
}

export const translateMessagePayload = (payload = {}, fallback = '') => {
  const key = String(payload?.message_key || payload?.msg_key || '').trim()
  const rawParams = payload?.message_params || payload?.msg_params
  const params = rawParams && typeof rawParams === 'object' ? rawParams : {}
  const defaultText = payload?.user_message || payload?.message || payload?.msg || fallback
  return key ? t(key, defaultText, params) : formatFallback(defaultText || fallback, params)
}
