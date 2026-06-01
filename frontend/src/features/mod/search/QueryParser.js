import { FIELD_TYPES } from './SearchTypes';

export class QueryParser {
  constructor(schema) {
    this.schema = schema;
    // 建立别名映射表: 'br' -> 'breaking'
    this.aliasMap = new Map();
    Object.keys(schema).forEach(key => {
      this.aliasMap.set(key.toLowerCase(), key); // 主键
      const config = schema[key];
      if (config.alias) {
        if (Array.isArray(config.alias)) {
          config.alias.forEach(a => this.aliasMap.set(a.toLowerCase(), key));
        } else {
          this.aliasMap.set(config.alias.toLowerCase(), key);
        }
      }
    });
  }

  /**
   * 解析单个输入字符串
   * @param {string} input - 用户输入，如 "br:+" 或 "Core"
   * @returns {Object|null} - 返回 Tag 对象或 null
   */
  parse(input) {
    if (!input) return null;
    const trimmed = input.trim();
    
    // 1. 正则匹配结构: (-)?(key):?(value)
    // 捕获组: 1=排除符号, 2=键, 3=值
    const match = trimmed.match(/^(-?)([^:]+):(.*)$/);

    if (match) {
      const [_, excludeSign, keyRaw, valueRaw] = match;
      const realKey = this.aliasMap.get(keyRaw.toLowerCase());

      if (realKey) {
        const config = this.schema[realKey];
        const isExclude = excludeSign === '-';

        // 特殊类型值的预处理
        let processedValue = valueRaw;
        
        // 布尔值处理: 将 +, true 转换为 true (boolean)
        if (config.type === FIELD_TYPES.BOOLEAN) {
          const vLower = valueRaw.toLowerCase();
          if (config.trueValues.includes(vLower)) processedValue = true;
          else if (config.falseValues.includes(vLower)) processedValue = false;
          else if (config.nullValues.includes(vLower)) processedValue = null; // 必须显式解析 null 值
          // 如果都不是，可能用户输入了一半，暂且保留原字符串供后续逻辑处理，或者标记无效
        }

        return {
          type: 'rule',
          key: realKey,        // 真实字段名
          originalKey: keyRaw, // 用户输入的别名
          value: processedValue,
          displayValue: valueRaw, // 用于UI显示
          exclude: isExclude,
          schema: config       // 携带配置以便渲染
        };
      }
    }

    // 2. 纯文本搜索
    const isExclude = trimmed.startsWith('-');
    return {
      type: 'text',
      key: null,
      value: isExclude ? trimmed.slice(1) : trimmed,
      exclude: isExclude
    };
  }
}