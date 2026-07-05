import { createI18n } from 'vue-i18n'
import zhCN from '../../locales/zh-CN.json'
import en from '../../locales/en.json'

export const DEFAULT_LOCALE = 'zh-CN'

const builtinMessages = {
  'zh-CN': zhCN,
  en,
}

const loadedUserMessages = new Map()

const isPlainObject = (value) => value && typeof value === 'object' && !Array.isArray(value)

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
  messages: {
    [DEFAULT_LOCALE]: builtinMessages[DEFAULT_LOCALE],
    en: builtinMessages.en,
  },
})

const loadUserMessages = async (locale) => {
  if (!window.pywebview?.api?.locale_load_user_messages) return {}
  const res = await window.pywebview.api.locale_load_user_messages(locale)
  if (res?.status !== 'success') return {}
  return res.data?.messages && typeof res.data.messages === 'object' ? res.data.messages : {}
}

export const setLocale = async (language = DEFAULT_LOCALE) => {
  const locale = normalizeLocale(language)
  const builtin = builtinMessages[locale] || {}
  const userMessages = await loadUserMessages(locale)
  loadedUserMessages.set(locale, userMessages)
  i18n.global.setLocaleMessage(locale, deepMerge(builtin, userMessages))
  i18n.global.locale.value = locale
  document.documentElement.lang = locale
  return locale
}

export const getCurrentLocale = () => i18n.global.locale.value || DEFAULT_LOCALE

export const t = (key = '', defaultText = '', params = {}) => {
  const normalizedKey = String(key || '').trim()
  const safeParams = params && typeof params === 'object' ? params : {}
  if (!normalizedKey) return formatFallback(defaultText, safeParams)
  const translated = i18n.global.t(normalizedKey, safeParams)
  if (translated && translated !== normalizedKey) return translated
  return formatFallback(defaultText, safeParams)
}

export const translateMessagePayload = (payload = {}, fallback = '') => {
  const key = String(payload?.message_key || '').trim()
  const params = payload?.message_params && typeof payload.message_params === 'object' ? payload.message_params : {}
  const defaultText = payload?.user_message || payload?.message || fallback
  return key ? t(key, defaultText, params) : formatFallback(defaultText || fallback, params)
}
