// frontend/src/utils/searchLogic.js

/**
 * 1. 动态前缀生成器
 * 输入: ['tags', 'title', 'author', 'time']
 * 输出: { 't': 'tags', 'ti': 'title', 'a': 'author', 'tm': 'time' } (示例)
 */
export function generatePrefixMap(schemaKeys) {
  const prefixToKey = {}
  const keyToPrefix = {}
  
  // 排序：优先短单词，保证常用词先占有短前缀（可选，这里按字母序）
  const sortedKeys = [...schemaKeys].sort()

  sortedKeys.forEach(key => {
    let len = 1
    let prefix = key.substring(0, len).toLowerCase()
    
    // 冲突检测：如果前缀已存在，则加长
    while (prefixToKey[prefix] && len <= key.length) {
      len++
      prefix = key.substring(0, len).toLowerCase()
    }
    
    // 如果整个单词都被占用了（极少见），加数字后缀
    if (prefixToKey[prefix]) {
      let i = 1
      while (prefixToKey[prefix + i]) i++
      prefix = prefix + i
    }

    prefixToKey[prefix] = key
    keyToPrefix[key] = prefix
  })

  return { prefixToKey, keyToPrefix }
}

/**
 * 2. 自动构建参考词列表 (Autocomplete Source)
 * 根据 schema 类型自动提取 list 和 string
 */
export function buildAutocompleteIndex(dataList, schema) {
  const index = {}
  
  // 初始化
  Object.keys(schema).forEach(key => index[key] = new Set())

  // 遍历数据
  dataList.forEach(item => {
    Object.entries(schema).forEach(([key, type]) => {
      const val = item[key]
      if (!val) return

      if (type === 'list' && Array.isArray(val)) {
        val.forEach(v => index[key].add(v))
      } else if (type === 'string') {
        index[key].add(val)
      }
    })
  })

  // 转为数组并排序
  const result = {}
  Object.keys(index).forEach(key => {
    result[key] = Array.from(index[key]).sort()
  })
  return result
}

/**
 * 3. 通用过滤函数生成器
 * @param {Array} tags - 用户输入的标签数组 ["t:Core", "abc"]
 * @param {String} mode - 'AND' | 'OR'
 * @param {Object} prefixToKey - 前缀映射表
 * @param {Array} defaultFields - 无前缀时的默认搜索字段
 */
export function createFilterPredicate(tags, mode, prefixToKey, defaultFields) {
  // 预解析 Tags
  const criteria = tags.map(tag => {
    // 处理排除逻辑 (例如 -t:Core)
    let isExclude = false
    let cleanTag = tag
    if (tag.startsWith('-')) {
      isExclude = true
      cleanTag = tag.slice(1)
    }

    const colonIdx = cleanTag.indexOf(':')
    if (colonIdx === -1) {
      // 无前缀 -> 全局搜索
      return { type: '_global', value: cleanTag.toLowerCase(), isExclude }
    }

    const prefix = cleanTag.substring(0, colonIdx).toLowerCase()
    const value = cleanTag.substring(colonIdx + 1).toLowerCase()
    const targetField = prefixToKey[prefix]

    if (targetField) {
      return { type: 'field', field: targetField, value, isExclude }
    } else {
      // 未知前缀，当作普通文本搜
      return { type: '_global', value: cleanTag.toLowerCase(), isExclude }
    }
  })

  // 返回一个断言函数 (Item => Boolean)
  return (item) => {
    if (criteria.length === 0) return true

    // 单个条件的校验逻辑
    const checkSingle = (crit) => {
      let match = false
      
      if (crit.type === 'field') {
        const val = item[crit.field]
        if (Array.isArray(val)) {
          match = val.some(v => String(v).toLowerCase().includes(crit.value))
        } else if (val !== undefined && val !== null) {
          match = String(val).toLowerCase().includes(crit.value)
        }
      } else {
        // Global search
        match = defaultFields.some(field => {
          const val = item[field]
          if (Array.isArray(val)) return val.some(v => String(v).toLowerCase().includes(crit.value))
          return String(val).toLowerCase().includes(crit.value)
        })
      }
      
      return crit.isExclude ? !match : match
    }

    if (mode === 'AND') {
      return criteria.every(checkSingle)
    } else {
      return criteria.some(checkSingle)
    }
  }
}