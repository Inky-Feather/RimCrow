import { t } from '../../../app/i18n'

export const TAG_FIELD_TYPES = {
  STRING: 'string',
  LIST: 'list',
  BOOLEAN: 'boolean',
  DATE: 'date',
  NUMBER: 'number',
}

export const DEFAULT_TAG_FIELD_CONFIG = {
  type: TAG_FIELD_TYPES.STRING,
  label: '',
  alias: [],
  searchable: true,
  defaultSearch: false,
  suggest: false,
  trueValues: ['+', 'true', 'yes', '1', 'on', 't', 'y'],
  falseValues: ['-', 'false', 'no', '0', 'off', 'f', 'n'],
  nullValues: ['_', 'null', 'nil', 'none'],
  getter: null,
  label_getter: null,
  color_getter: null,
}

export const DEFAULT_TAG_SEARCH_INPUT_HELP_TEXT = '输入关键词并回车确认\n可直接输入关键词，或使用 类别:关键词 格式\n[[(使用 Tab 键应用输入建议)]]'

// =============================================================================
// 基础归一化：把外部配置整理成引擎内部统一使用的格式
// =============================================================================
const normalizeAliases = (value) => {
  if (value === null || value === undefined || value === '') return []
  const values = Array.isArray(value) ? value : [value]
  return values.map(item => String(item).trim()).filter(Boolean)
}

const normalizeStringList = (value) => normalizeAliases(value).map(item => item.toLowerCase())
const toSearchText = (value) => String(value ?? '').toLowerCase()
const escapeHelpHtml = (value = '') => String(value)
  .replace(/&/g, '&amp;')
  .replace(/</g, '&lt;')
  .replace(/>/g, '&gt;')
  .replace(/"/g, '&quot;')
  .replace(/'/g, '&#39;')

const normalizeOption = (item) => {
  if (typeof item === 'string' || typeof item === 'number') return { label: String(item), value: String(item) }
  return {
    ...item,
    label: String(item?.label ?? item?.value ?? ''),
    value: String(item?.value ?? item?.label ?? ''),
  }
}

const normalizeExcludeRules = (rules = []) => rules.map(rule => {
  if (rule instanceof RegExp) return rule
  // 字符串规则支持 * 通配，方便调用方用 '*path'、'description' 这类轻量规则屏蔽字段。
  const pattern = String(rule).replace(/[.+?^${}()|[\]\\]/g, '\\$&').replace(/\*/g, '.*')
  return new RegExp(`^${pattern}$`)
})

const normalizeTagSearchOptions = (dataOrOptions = [], maybeOptions = {}) => {
  if (Array.isArray(dataOrOptions)) {
    return { ...maybeOptions, data: dataOrOptions }
  }
  return { ...(dataOrOptions || {}) }
}

// =============================================================================
// Schema 构建：合并默认配置，确保解析、匹配、提示看到同一套字段定义
// =============================================================================
export const buildTagSearchSchema = (schema = {}) => {
  const normalized = {}
  Object.entries(schema).forEach(([key, config = {}]) => {
    normalized[key] = {
      ...DEFAULT_TAG_FIELD_CONFIG,
      label: key,
      ...config,
      alias: normalizeAliases(config.alias),
      trueValues: normalizeStringList(config.trueValues || DEFAULT_TAG_FIELD_CONFIG.trueValues),
      falseValues: normalizeStringList(config.falseValues || DEFAULT_TAG_FIELD_CONFIG.falseValues),
      nullValues: normalizeStringList(config.nullValues || DEFAULT_TAG_FIELD_CONFIG.nullValues),
    }
  })
  return normalized
}

// =============================================================================
// 查询解析：把用户输入拆成“纯文本搜索”或“字段规则搜索”
// =============================================================================
class TagQueryParser {
  constructor(schema = {}) {
    this.schema = schema
    this.aliasMap = new Map()
    Object.keys(schema).forEach(key => {
      this.aliasMap.set(key.toLowerCase(), key)
      normalizeAliases(schema[key].alias).forEach(alias => this.aliasMap.set(alias.toLowerCase(), key))
    })
  }

  parse(input) {
    if (!input) return null
    const trimmed = String(input).trim()
    if (!trimmed) return null

    // 1. 正则匹配结构: (-)?(key):?(value)
    // 捕获组: 1=排除符号, 2=键, 3=值
    const match = trimmed.match(/^(-?)([^:]+):(.*)$/)
    if (match) {
      const [, excludeSign, keyRaw, valueRaw] = match
      const realKey = this.aliasMap.get(String(keyRaw).toLowerCase())
      if (realKey) {
        const config = this.schema[realKey]
        let processedValue = valueRaw
        // 布尔字段使用三态值：有值(+/true)、明确无值(-/false)、未知或缺失(_/null)。
        if (config.type === TAG_FIELD_TYPES.BOOLEAN) {
          const valueLower = String(valueRaw).toLowerCase()
          if (config.trueValues.includes(valueLower)) processedValue = true
          else if (config.falseValues.includes(valueLower)) processedValue = false
          else if (config.nullValues.includes(valueLower)) processedValue = null
        }
        return {
          type: 'rule',
          key: realKey,        // 真实字段名
          originalKey: keyRaw, // 用户输入的别名
          value: processedValue,
          displayValue: valueRaw, // 用于UI显示
          exclude: excludeSign === '-',
          schema: config,       // 携带配置以便渲染
        }
      }
    }

    // 2. 纯文本搜索
    const isExclude = trimmed.startsWith('-')
    const value = isExclude ? trimmed.slice(1) : trimmed
    return { type: 'text', key: null, value, displayValue: value, exclude: isExclude }
  }
}

// =============================================================================
// 搜索引擎：负责字段探测、索引构建、实际匹配和输入建议
// =============================================================================
export class TagSearchEngine {
  /**
   * @param {Array|Object} dataOrOptions - 数据数组，或完整 options。传 options 时可省略数据源，仅用作输入解析/建议。
   * @param {Object} maybeOptions - dataOrOptions 为数组时使用的配置。
   * @param {Object} options.schema - 用户强制指定的 Schema
   * @param {Array<String|RegExp>} options.excludeFields - 排除字段规则 (支持字符串通配或正则)
   * @param {Boolean} options.autoDetect - 是否自动探测 (默认 true)
   */
  constructor(dataOrOptions = [], maybeOptions = {}) {
    const options = normalizeTagSearchOptions(dataOrOptions, maybeOptions)
    this.options = options
    this.rawData = options.data || []
    this.valueOptions = options.valueOptions || {}
    this.inputHelpText = options.inputHelpText === undefined ? DEFAULT_TAG_SEARCH_INPUT_HELP_TEXT : options.inputHelpText
    this.schema = {}
    this.indices = new Map()
    this.defaultSearchFields = []
    this.excludeRules = normalizeExcludeRules(options.excludeFields || [])

    this.initSchema(options.schema || {}, options.autoDetect !== false, options.autoAlias !== false)
    this.parser = new TagQueryParser(this.schema)
    this.buildIndices()
    this.searchHelpText = options.searchHelpText === undefined ? generateTagSearchHtmlHelp(this) : options.searchHelpText
    this.controller = this.createInputController()
  }

  // 输入组件只需要解析、建议和帮助文本；用窄接口避免 UI 依赖完整搜索实现。
  createInputController() {
    const engine = this
    return {
      schema: this.schema,
      get inputHelpText() {
        return engine.options?.inputHelpText === undefined ? t('tagSearch.helpText') : engine.inputHelpText
      },
      get searchHelpText() {
        return engine.options?.searchHelpText === undefined ? generateTagSearchHtmlHelp(engine) : engine.searchHelpText
      },
      parse: (input) => this.parse(input),
      getSuggestions: (input) => this.getSuggestions(input),
      getFieldUsage: (config, key) => this.getFieldUsage(config, key),
      getPreferredKey: (key) => this.getPreferredKey(key),
      getSearchHelpText: () => this.searchHelpText || generateTagSearchHtmlHelp(this),
    }
  }

  parse(input) {
    return this.parser.parse(input)
  }

  initSchema(userSchema, autoDetect, autoAlias) {
    // 1. 收集所有候选字段 (Key Set)
    // 用户显式配置优先；自动探测只补充未排除的数据字段，避免把内部大字段暴露给用户。
    const candidateFields = new Set(Object.keys(userSchema))
    if (autoDetect && this.rawData.length > 0) {
      const sampleSize = Math.min(this.rawData.length, 20); // 增加采样样本
      for (let index = 0; index < sampleSize; index++) {
        Object.keys(this.rawData[index] || {}).forEach(key => candidateFields.add(key))
      }
    }

    // 2. 过滤 & 初步构建
    candidateFields.forEach(key => {
      // A. 确定配置源
      const userConfig = userSchema[key]
      // B. 排除规则检查
      // 显式配置的字段即使命中排除规则也保留；排除规则只作用于自动探测字段。
      if (!userConfig && this.isExcluded(key)) return

      // 如果不在数据中且用户没配置，跳过（针对 userSchema 里写了但数据没这个字段的情况，
      // 但通常 userSchema 是“强制”的，所以主要用来过滤 autoDetect 出来的垃圾字段）
      // 这里为了保险，如果不开启 autoDetect，仅使用 userSchema；
      // 如果开启，则 candidateFields 包含了数据里的 key。
      
      // C. 推断类型 (如果用户没指定类型)
      let type = userConfig?.type
      if (!type && this.rawData.length > 0) type = this.inferType(key)
      // 如果连类型都推断不出来（所有数据该字段都为null），且用户没配，则丢弃
      if (!type && !userConfig) return

      // D. 构建配置
      this.schema[key] = buildTagSearchSchema({
        [key]: { type: type || TAG_FIELD_TYPES.STRING, ...userConfig }, // 用户配置覆盖默认
      })[key]
      // 默认策略补充
      // 如果是自动检测出来的 String，默认加入全文搜索
      // if (!userConfig && this.schema[key].type === FIELD_TYPES.STRING) {
      //   this.schema[key].defaultSearch = true;
      // }
    })

    // 3. 自动生成简写别名 (Auto-Alias)
    if (autoAlias) this.generateAutoAliases()
    this.parser = new TagQueryParser(this.schema)
    // 4. 缓存默认搜索字段
    this.defaultSearchFields = Object.keys(this.schema).filter(key => this.schema[key].defaultSearch)
  }

  // 判断字段是否被排除
  isExcluded(key) {
    // 下划线字段视为内部字段，默认不进入搜索语法。
    if (String(key).startsWith('_')) return true
    return this.excludeRules.some(regex => regex.test(key))
  }

  // 推断字段类型
  inferType(key) {
    // 只取第一个非空样本推断类型，减少初始化成本；需要精确类型时由 schema 显式指定。
    for (const item of this.rawData) {
      const value = item?.[key]
      if (value === null || value === undefined) continue
      if (Array.isArray(value)) return TAG_FIELD_TYPES.LIST
      if (typeof value === 'boolean') return TAG_FIELD_TYPES.BOOLEAN
      if (typeof value === 'number') return TAG_FIELD_TYPES.NUMBER
      return TAG_FIELD_TYPES.STRING
    }
    return null; // 全是空值
  }

  // 核心功能：自动生成最短唯一别名
  generateAutoAliases() {
    // 只生成一个最短可用别名，避免建议列表被低价值别名污染。
    // 优先首字母缩写，如 supported_languages -> sl；再尝试最短前缀，如 source -> so。
    const usedAliases = new Set(Object.keys(this.schema).map(key => String(key).toLowerCase()))
    Object.keys(this.schema).forEach(key => normalizeAliases(this.schema[key].alias).forEach(alias => usedAliases.add(alias.toLowerCase())))

    Object.keys(this.schema).forEach(key => {
      const config = this.schema[key]
      // 生成候选列表 (按优先级排序)
      const candidates = []
      // 策略 A: 首字母缩写 (Acronym) - 优先级最高
      // 逻辑: 按下划线、横杠或大写字母分割单词
      // supported_languages -> ['supported', 'languages'] -> 'sl'
      // package_id -> ['package', 'id'] -> 'pi'
      // isActive -> ['is', 'Active'] -> 'ia'
      const words = key.split(/[\s_-]+|(?=[A-Z])/).filter(Boolean)
      // 只有当缩写长度 > 1 时才有意义 (避免单字母 'a' 和前缀策略冲突，虽然逻辑上也没事)
      if (words.length > 1) candidates.push(words.map(word => word[0]).join('').toLowerCase())
      // 策略 B: 最短前缀 (Prefix)
      // s, su, sup, supp...
      for (let length = 1; length < key.length; length++) candidates.push(key.substring(0, length).toLowerCase())

      // 3. 选出最佳可用别名
      // 只选 *一个* 最短/最好的可用别名，以免污染命名空间
      const bestAlias = candidates.find(candidate => !usedAliases.has(candidate.toLowerCase()) && Number.isNaN(Number(candidate)))
      // 4. 应用别名
      if (!bestAlias) return
      usedAliases.add(bestAlias.toLowerCase())
      config.alias = [...normalizeAliases(config.alias), bestAlias]
    })
  }

  buildIndices() {
    // 只给需要补全的字段建值索引；搜索本身直接遍历当前数据，避免维护双份过滤状态。
    Object.keys(this.schema).forEach(key => {
      if (this.schema[key].suggest) this.indices.set(key, new Set())
    })

    // 遍历数据收集值 (非响应式，速度快)
    for (const item of this.rawData) {
      for (const [key, values] of this.indices) {
        const config = this.schema[key]
        const itemValue = config.getter ? config.getter(item) : item?.[key]
        if (itemValue === null || itemValue === undefined) continue
        if (Array.isArray(itemValue)) itemValue.forEach(value => values.add(String(value)))
        else values.add(String(itemValue))
      }
    }
  }

  // ---------------------------------------------------------------------------
  // 匹配逻辑：AND/OR 组合多个 token，单项内部按字段类型匹配
  // ---------------------------------------------------------------------------
  /**
   * 执行搜索
   * @param {Array} tags - 解析后的 tag 对象数组
   * @param {String} logic - 'AND' | 'OR'
   * @returns {Array} 过滤后的数据
   */
  search(tags, logic = 'AND') {
    if (!tags || tags.length === 0) return this.rawData
    return this.rawData.filter(item => {
      const results = tags.map(tag => this.matchItem(item, tag))
      return logic === 'OR' ? results.some(Boolean) : results.every(Boolean)
    })
  }

  /**
   * 判断单项匹配
   */
  matchItem(item, tag) {
    // 1. 全文/默认搜索
    if (tag.type === 'text') {
      // 直接输入关键词时，只匹配 schema 中声明为 defaultSearch 的字段。
      const valueLower = toSearchText(tag.value)
      const isMatch = this.defaultSearchFields.some(field => {
        const config = this.schema[field]
        const fieldValue = config?.getter ? config.getter(item) : item?.[field]
        return toSearchText(fieldValue).includes(valueLower)
      })
      return tag.exclude ? !isMatch : isMatch
    }

    // 2. 字段规则搜索
    const config = this.schema[tag.key]
    if (!config) return false
    // 获取值 (支持自定义 getter)
    const itemValue = config.getter ? config.getter(item) : item?.[tag.key]
    let isMatch = false

    switch (config.type) {
      case TAG_FIELD_TYPES.BOOLEAN:
        //获取值的状态：Positive (有值), Negative (False), Null (未定义)
        isMatch = this.matchBoolean(itemValue, tag.value)
        break
      case TAG_FIELD_TYPES.LIST:
        isMatch = Array.isArray(itemValue) && itemValue.some(value => this.includesText(value, tag.value))
        break
      case TAG_FIELD_TYPES.NUMBER:
        isMatch = this.includesText(itemValue, tag.value)
        break
      case TAG_FIELD_TYPES.DATE:
      case TAG_FIELD_TYPES.STRING:
      default:
        isMatch = this.includesText(itemValue, tag.value)
        break
    }

    return tag.exclude ? !isMatch : isMatch
  }

  includesText(itemValue, searchValue) {
    return toSearchText(itemValue).includes(toSearchText(searchValue))
  }

  matchBoolean(itemValue, searchValue) {
    const valueState = this.getValueState(itemValue)
    if (searchValue === true) return valueState === 'positive'    // 搜索 + : 要求状态为 Positive
    if (searchValue === false) return valueState === 'negative'   // 搜索 - : 要求状态为 Negative (空数组/False/空字符串)
    if (searchValue === null) return valueState === 'null'        // 搜索 _ : 要求状态为 Null
    return false
  }

  /**
   * 判断值的“三态”
   * Positive: 有实际内容的 (非空数组、true、非空字符串、非0数字)
   * Negative: 明确为空的 (false, 0, [], "")
   * Null:     根本不存在 (null, undefined)
   */
  getValueState(value) {
    // 三态规则与旧搜索保持一致：负数被视为未知，用于表达“明确异常/不可判断”的状态。
    if (value === undefined || value === null) return 'null'
    if (Array.isArray(value)) return value.length > 0 ? 'positive' : 'negative'
    if (typeof value === 'string') return value.trim().length > 0 ? 'positive' : 'negative'
    if (typeof value === 'boolean') return value ? 'positive' : 'negative'
    // 大于0：Positive，小于0：Null， 等于0：Negative
    if (typeof value === 'number') return value > 0 ? 'positive' : value < 0 ? 'null' : 'negative'
    // 对象等其他情况，默认视为有值
    return 'positive'
  }

  // ---------------------------------------------------------------------------
  // 建议与帮助：生成输入框补全和搜索说明数据
  // ---------------------------------------------------------------------------
  
  // 获取字段的“首选简写键” (Preferred Key)
  // 逻辑：在所有别名和主键中，找最短的那个。如果长度一样，优先用主键。
  getPreferredKey(key) {
    const config = this.schema[key]
    if (!config) return key
    // 按长度排序，短的在前；长度相同，字母序在后（让更有语义的排前？或者保持原样）
    // 这里简单策略：找最短的
    return [key, ...normalizeAliases(config.alias)].reduce((best, item) => String(item).length < String(best).length ? item : best, key)
  }

  getFieldUsage(config, key) {
    if (config.type === TAG_FIELD_TYPES.BOOLEAN) return `${key}:+ | ${key}:- | ${key}:_`
    return t('tagSearch.keywordPlaceholder', { key })
  }

  // 搜索建议
  getSuggestions(input = '') {
    const suggestions = []
    const trimmed = String(input || '').trim()

    if (!trimmed) {
      // 空输入时列出所有可搜索字段，每个字段只给一条首选写法。
      Object.keys(this.schema).forEach(realKey => {
        const config = this.schema[realKey]
        if (config.searchable === false) return
        suggestions.push(this.buildKeySuggestion(realKey, ''))
      })
      // [可选] 排序建议列表
      // 比如把 defaultSearch 的排前面，或者按字母序
      // suggestions.sort((a, b) => {
      //    // 这里简单按 label 长度排，短的在前？或者按字母
      //    return a.label.length - b.label.length || a.label.localeCompare(b.label);
      // });
      return suggestions
    }

    const valueMatch = trimmed.match(/^(-?)([^:]+):(.*)$/)
    if (valueMatch) {
      // 已输入 key: 时，优先补全字段值；布尔字段只返回三态快捷值。
      const [, prefix, keyRaw, valueRaw] = valueMatch
      const realKey = this.parser.aliasMap.get(String(keyRaw).toLowerCase())
      if (!realKey) return suggestions
      const config = this.schema[realKey]
      const shortKey = this.getPreferredKey(realKey)

      if (config.type === TAG_FIELD_TYPES.BOOLEAN) return this.getBooleanSuggestions(config, prefix, shortKey, valueRaw)
      return this.getValueSuggestions(realKey, config, prefix, shortKey, valueRaw)
    }

    const inputLower = trimmed.replace(/^-/, '').toLowerCase()
    const prefix = trimmed.startsWith('-') ? '-' : ''
    // 未输入冒号时按字段名和别名前缀补全，保留排除符号。
    Object.keys(this.schema).forEach(realKey => {
      const config = this.schema[realKey]
      if (config.searchable === false) return
      const aliases = [realKey, ...normalizeAliases(config.alias)]
      if (!aliases.some(alias => alias.toLowerCase().startsWith(inputLower))) return
      suggestions.push(this.buildKeySuggestion(realKey, prefix, aliases.find(alias => alias.toLowerCase().startsWith(inputLower))))
    })
    return suggestions
  }

  buildKeySuggestion(realKey, prefix = '', matchInfo = '') {
    const config = this.schema[realKey]
    const shortKey = this.getPreferredKey(realKey)
    const aliases = [realKey, ...normalizeAliases(config.alias)]
      .filter((alias, index, array) => alias && alias !== shortKey && array.indexOf(alias) === index)
      .join(', ')
    return {
      type: 'key',
      label: shortKey,
      value: `${prefix}${shortKey}:`,
      desc: config.label || realKey,
      meta: { fullKey: realKey, aliases, usage: this.getFieldUsage(config, shortKey), matchInfo },
    }
  }

  getBooleanSuggestions(config, prefix, shortKey, valueRaw) {
    const valueLower = String(valueRaw || '').toLowerCase()
    const options = [
      { label: t('tagSearch.boolTrue'), value: config.trueValues[0], values: config.trueValues },
      { label: t('tagSearch.boolFalse'), value: config.falseValues[0], values: config.falseValues },
      { label: t('tagSearch.boolNull'), value: config.nullValues[0], values: config.nullValues },
    ]
    return options
      .filter(item => item.values.some(value => value.startsWith(valueLower)))
      .map(item => ({ type: 'value', label: item.label, value: `${prefix}${shortKey}:${item.value}`, desc: item.label, meta: { isBool: true } }))
  }

  getValueSuggestions(realKey, config, prefix, shortKey, valueRaw) {
    // valueOptions 用于外部显式枚举；没有枚举时回退到当前数据索引。
    const keyword = String(valueRaw || '').toLowerCase()
    const fromOptions = (this.valueOptions[realKey] || []).map(normalizeOption)
    const fromIndices = [...(this.indices.get(realKey) || [])].map(value => ({ label: config.label_getter ? config.label_getter(value) : value, value }))
    const options = fromOptions.length ? fromOptions : fromIndices
    return options
      .filter(item => !keyword || item.label.toLowerCase().includes(keyword) || item.value.toLowerCase().includes(keyword))
      .slice(0, 50)
      .map(item => ({
        type: 'value',
        label: item.label,
        value: `${prefix}${shortKey}:${item.value}`,
        desc: config.label || realKey,
        color: config.color_getter ? config.color_getter(item.value) : item.color,
      }))
  }
}

export const createTagSearchController = (options = {}) => (
  new TagSearchEngine(options).controller
)

// =============================================================================
// 帮助数据：给非 HTML 展示场景使用
// =============================================================================
export const generateTagSearchHelp = (engine) => {
  if (!engine?.schema) return []
  return Object.entries(engine.schema)
    .filter(([, config]) => config.searchable !== false)
    .map(([key, config]) => ({
      name: config.label || key,
      key,
      aliases: normalizeAliases(config.alias).join(', '),
      usage: engine.getFieldUsage(config, key),
      description: config.type === TAG_FIELD_TYPES.BOOLEAN ? '判断字段状态' : '按字段内容匹配',
      isDefault: config.defaultSearch,
    }))
}

// =============================================================================
// 帮助浮层：生成可直接放入 tooltip 的紧凑 HTML
// =============================================================================
/**
 * 生成极简、高密度的 HUD 风格帮助文档 (HTML)
 */
export const generateTagSearchHtmlHelp = (engine) => {
  if (!engine?.schema) return '<div class="p-2 text-xs">Loading...</div>'

  const entries = Object.entries(engine.schema).filter(([, config]) => config.searchable !== false)
  // 1. 字段排序：默认搜索的在前 -> 布尔值在前 -> 其他按首字母
  entries.sort((a, b) => {
    if (a[1].defaultSearch && !b[1].defaultSearch) return -1
    if (!a[1].defaultSearch && b[1].defaultSearch) return 1
    if (a[1].type === TAG_FIELD_TYPES.BOOLEAN && b[1].type !== TAG_FIELD_TYPES.BOOLEAN) return -1
    if (a[1].type !== TAG_FIELD_TYPES.BOOLEAN && b[1].type === TAG_FIELD_TYPES.BOOLEAN) return 1
    return engine.getPreferredKey(a[0]).length - engine.getPreferredKey(b[0]).length
  })

  // 2. 样式常量 (Tailwind)
  const C = {
    box: 'text-xs text-text-soft font-sans overflow-hidden',
    header: 'py-1 px-2 border-b border-border-base/10 flex items-center justify-between',
    sectionTitle: 'text-[0.65rem] uppercase tracking-wider opacity-40 font-bold mt-2 mb-1 px-1',
    syntaxGrid: 'grid grid-cols-4 gap-1 px-1',
    syntaxItem: 'bg-bg-overlay/5 rounded px-0.5 py-0.5 flex flex-col items-center justify-center text-center border border-border-base/5',
    fieldGrid: 'grid grid-cols-2 gap-x-2 gap-y-1 px-1 pb-2',
    fieldRow: 'flex items-center border-l-2 border-border-base/10 pl-1 group',
    keyBadge: 'font-mono font-bold text-accent-primary bg-accent-primary/10 px-1.5 rounded text-xs min-w-[20px] text-center border border-accent-primary/20 group-hover:bg-accent-primary/20 transition-colors',
    label: 'text-text-dim text-xs text-end truncate flex-1',
  }
  // 是否是默认搜索字段
  const defaultMarker = `<span class="text-accent-highlight ml-1" title="${t('tagSearch.defaultInFuzzySearch')}">•</span>`
  // 3. 构建 HTML
  // 这里拼接的是固定模板和转义后的字段文本，避免 schema label 破坏帮助浮层结构。
  let html = `<div class="${C.box}">`
  // === 顶部：标题 + 状态 ===
  html += `<div class="${C.header}">
      <span class="font-bold text-text-main">${t('tagSearch.searchGuide')}</span>
      <span class="text-[0.65rem] bg-accent-highlight/5 text-accent-highlight px-1.5 rounded border border-accent-highlight/10">${t('tagSearch.searchQuickRef')}</span>
    </div>`;
  // === 区域 1：基础语法 (3个核心卡片) ===
  html += `<div class="${C.sectionTitle}">${t('tagSearch.basicSearchSyntax')}</div>`
  html += `<div class="${C.syntaxGrid}">
    <div class="${C.syntaxItem}">
      <span class="opacity-60">${t('tagSearch.directSearch')}${defaultMarker}</span>
      <span class="font-mono bg-bg-overlay/10 px-1.5 rounded text-text-main">${t('tagSearch.keywordPlaceholder', { key: '' }).replace(':', '')}</span>
    </div>
    <div class="${C.syntaxItem}">
      <span class="opacity-60">${t('tagSearch.categorySearch')}</span>
      <span class="font-mono bg-bg-overlay/10 px-1.5 rounded"><span class="text-accent-primary">Category</span>:Value</span>
    </div>
    <div class="${C.syntaxItem}">
      <span class="opacity-60">${t('tagSearch.excludeSearch')}</span>
      <span class="font-mono bg-bg-overlay/10 px-1.5 rounded text-accent-danger">-<span class="text-accent-primary">Category</span><span class="text-text-main">:Value</span></span>
    </div>
    <div class="${C.syntaxItem}">
      <span class="opacity-60">${t('tagSearch.boolSearch')}</span>
      <span class="font-mono bg-bg-overlay/10 px-1.5 rounded"><span class="text-accent-primary">Category</span>:<span class="text-accent-success">+</span>/<span class="text-accent-danger">-</span>/<span class="text-accent-warn">_</span></span>
    </div>
  </div>`
  // === 区域 2：字段列表 (高密度双栏) ===
  html += `<div class="${C.sectionTitle}">${t('tagSearch.availableFields')}</div><div class="${C.fieldGrid}">`

  entries.forEach(([realKey, config]) => {
    const shortKey = engine.getPreferredKey(realKey)
    const label = config.label === realKey ? realKey : `${realKey} (${config.label})`
    html += `<div class="${C.fieldRow}">
      <div class="${C.keyBadge}">${escapeHelpHtml(shortKey)}:</div>
      <div class="${C.label}">${escapeHelpHtml(label)}${config.defaultSearch ? defaultMarker : ''}</div>
    </div>`
  })
  html += `</div>`; // 字段区块结束

  html += `<div>${t('tagSearch.threeStateTip')}</div>`;
  html += `<div>${t('tagSearch.logicRelationsTip')}</div>`;
  html += `<div class="text-xs text-text-dim">${t('tagSearch.andRelationTip')}</div>`;
  html += `<div class="text-xs text-text-dim">${t('tagSearch.orRelationTip')}</div>`;
  html += `</div>`;
  return html
}
