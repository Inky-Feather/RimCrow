import { FIELD_TYPES, DEFAULT_FIELD_CONFIG } from './SearchTypes';
import { QueryParser } from './QueryParser';

export class SearchEngine {
  /**
   * @param {Array} data - 数据源
   * @param {Object} options
   * @param {Object} options.schema - 用户强制指定的 Schema
   * @param {Array<String|RegExp>} options.excludeFields - 排除字段规则 (支持字符串通配或正则)
   * @param {Boolean} options.autoDetect - 是否自动探测 (默认 true)
   */
  constructor(data = [], options = {}) {
    this.rawData = data;
    this.schema = {};
    this.indices = new Map();
    this.defaultSearchFields = [];
    
    // 预处理排除规则
    this.excludeRules = (options.excludeFields || []).map(rule => {
      if (rule instanceof RegExp) return rule;
      // 将字符串简易通配符转为正则: '*path' -> /path$/
      // 如果你更喜欢完全正则，这里可以只处理字符串精确匹配
      // 下面是一个支持 *通配符 的简易转换实现
      const pattern = rule.replace(/\*/g, '.*'); 
      return new RegExp(`^${pattern}$`);
    });

    this.initSchema(options.schema || {}, options.autoDetect !== false);
    
    // 初始化解析器时，Schema 已经包含了自动生成的别名
    this.parser = new QueryParser(this.schema);
    
    this.buildIndices();
  }

  // === 初始化阶段 ===

  initSchema(userSchema, autoDetect) {
    // 1. 收集所有候选字段 (Key Set)
    const candidateFields = new Set(Object.keys(userSchema));

    if (autoDetect && this.rawData.length > 0) {
      const sampleSize = Math.min(this.rawData.length, 20); // 增加采样样本
      for (let i = 0; i < sampleSize; i++) {
        Object.keys(this.rawData[i]).forEach(key => candidateFields.add(key));
      }
    }

    // 2. 过滤 & 初步构建
    candidateFields.forEach(key => {

      // A. 确定配置源
      const userConfig = userSchema[key];
      // B. 排除规则检查
      // 只有当 userConfig 不存在（即非用户强制指定）时，才检查排除规则
      if (!userConfig && this.isExcluded(key)) return;
      
      // 如果不在数据中且用户没配置，跳过（针对 userSchema 里写了但数据没这个字段的情况，
      // 但通常 userSchema 是“强制”的，所以主要用来过滤 autoDetect 出来的垃圾字段）
      // 这里为了保险，如果不开启 autoDetect，仅使用 userSchema；
      // 如果开启，则 candidateFields 包含了数据里的 key。
      
      // C. 推断类型 (如果用户没指定类型)
      let type = userConfig?.type;
      if (!type && this.rawData.length > 0) {
        type = this.inferType(key);
      }
      
      // 如果连类型都推断不出来（所有数据该字段都为null），且用户没配，则丢弃
      if (!type && !userConfig) return;

      // D. 构建配置
      this.schema[key] = {
        ...DEFAULT_FIELD_CONFIG,
        label: key, // 默认 Label
        type: type || FIELD_TYPES.STRING,
        ...userConfig // 用户配置覆盖默认
      };

      // 默认策略补充
      // 如果是自动检测出来的 String，默认加入全文搜索
      // if (!userConfig && this.schema[key].type === FIELD_TYPES.STRING) {
      //   this.schema[key].defaultSearch = true;
      // }
    });

    // 3. 自动生成简写别名 (Auto-Alias)
    this.generateAutoAliases();

    // 4. 缓存默认搜索字段
    this.defaultSearchFields = Object.keys(this.schema).filter(k => this.schema[k].defaultSearch);
  }

  // 判断字段是否被排除
  isExcluded(key) {
    // 私有字段强制排除
    if (key.startsWith('_')) return true;
    // 规则匹配
    return this.excludeRules.some(regex => regex.test(key));
  }

  // 推断字段类型
  inferType(key) {
    // 遍历所有数据直到找到非空值
    for (const item of this.rawData) {
      const val = item[key];
      if (val === null || val === undefined) continue;
      if (Array.isArray(val)) return FIELD_TYPES.LIST;
      if (typeof val === 'boolean') return FIELD_TYPES.BOOLEAN;
      if (typeof val === 'number') return FIELD_TYPES.NUMBER;
      // 简单的日期检测 (需谨慎，可能会误判字符串)
      // if (val instanceof Date) return FIELD_TYPES.DATE;
      return FIELD_TYPES.STRING;
    }
    return null; // 全是空值
  }

  // 核心功能：自动生成最短唯一别名
  generateAutoAliases() {
    const allKeys = Object.keys(this.schema);
    const usedAliases = new Set(allKeys); // 别名不能和主键冲突
    
    // 先把用户手动配置的别名占位，防止自动生成的冲突
    allKeys.forEach(key => {
      const conf = this.schema[key];
      if (conf.alias) {
        const aliases = Array.isArray(conf.alias) ? conf.alias : [conf.alias];
        aliases.forEach(a => usedAliases.add(a));
      }
    });

    // 开始生成
    allKeys.forEach(key => {
      const conf = this.schema[key];
      // 如果用户已经手动配了别名，不生成自动别名
    //   if (conf.alias) return;
      // 生成候选列表 (按优先级排序)
      const candidates = [];
      
      // 策略 A: 首字母缩写 (Acronym) - 优先级最高
      // 逻辑: 按下划线、横杠或大写字母分割单词
      // supported_languages -> ['supported', 'languages'] -> 'sl'
      // package_id -> ['package', 'id'] -> 'pi'
      // isActive -> ['is', 'Active'] -> 'ia'
      const words = key.split(/[\s_-]+|(?=[A-Z])/).filter(w => w); // 分割单词
      if (words.length > 1) {
        const acronym = words.map(w => w[0]).join('').toLowerCase();
        // 只有当缩写长度 > 1 时才有意义 (避免单字母 'a' 和前缀策略冲突，虽然逻辑上也没事)
        candidates.push(acronym); 
      }

      // 策略 B: 最短前缀 (Prefix)
      // s, su, sup, supp...
      for (let len = 1; len < key.length; len++) {
        candidates.push(key.substring(0, len).toLowerCase());
      }

      // 3. 选出最佳可用别名
      // 我们只选 *一个* 最短/最好的可用别名，以免污染命名空间
      let bestAlias = null;
      
      for (const candidate of candidates) {
        // 检查: 未被占用 且 不是纯数字 (防止和未来的数值搜索混淆)
        if (!usedAliases.has(candidate) && isNaN(Number(candidate))) {
          bestAlias = candidate;
          break; // 找到即停止，这就是优先级最高的可用别名
        }
      }

      // 4. 应用别名
      if (bestAlias) {
        usedAliases.add(bestAlias);
        // 合并到现有 alias 中
        const existing = Array.isArray(conf.alias) ? conf.alias : (conf.alias ? [conf.alias] : []);
        // 避免重复 (虽然 Set 已经保证了 unique，但防御性编程)
        if (!existing.includes(bestAlias)) {
          conf.alias = [...existing, bestAlias];
        }
      }
    });
  }

  buildIndices() {
    // 仅针对开启了 suggest 的字段建立值索引
    Object.keys(this.schema).forEach(key => {
      if (!this.schema[key].suggest) return;
      this.indices.set(key, new Set());
    });

    // 遍历数据收集值 (非响应式，速度快)
    for (const item of this.rawData) {
      for (const [key, valSet] of this.indices) {
        const val = item[key];
        if (val === null || val === undefined) continue;

        if (Array.isArray(val)) {
          val.forEach(v => valSet.add(String(v)));
        } else {
          valSet.add(String(val));
        }
      }
    }
  }

  // === 运行阶段 ===

  /**
   * 执行搜索
   * @param {Array} tags - 解析后的 tag 对象数组
   * @param {String} logic - 'AND' | 'OR'
   * @returns {Array} 过滤后的数据
   */
  search(tags, logic = 'AND') {
    if (!tags || tags.length === 0) return this.rawData;

    return this.rawData.filter(item => {
      const results = tags.map(tag => this.matchItem(item, tag));
      if (logic === 'AND') return results.every(r => r === true);
      else return results.some(r => r === true);
    });
  }

  /**
   * 判断单项匹配
   */
  matchItem(item, tag) {
    // 1. 全文/默认搜索
    if (tag.type === 'text') {
      const valLower = tag.value.toLowerCase();
      const isMatch = this.defaultSearchFields.some(field => {
        const fieldVal = item[field];
        return String(fieldVal || '').toLowerCase().includes(valLower);
      });
      return tag.exclude ? !isMatch : isMatch;
    }

    // 2. 字段规则搜索
    const config = this.schema[tag.key];
    if (!config) return false;

    // 获取值 (支持自定义 getter)
    const itemVal = config.getter ? config.getter(item) : item[tag.key];
    let isMatch = false;

    switch (config.type) {
      case FIELD_TYPES.BOOLEAN:
        //获取值的状态：Positive (有值), Negative (False), Null (未定义)
        const valState = this.getValueState(itemVal);
        if (tag.value === true) {
          // 搜索 + : 要求状态为 Positive
          isMatch = (valState === 'positive');
        } else if (tag.value === false) {
          // 搜索 - : 要求状态为 Negative (空数组/False/空字符串)
          isMatch = (valState === 'negative');
        } else if (tag.value === null) {
          // 搜索 _ : 要求状态为 Null
          isMatch = (valState === 'null');
        }
        break;

      case FIELD_TYPES.LIST:
        if (Array.isArray(itemVal)) {
          // 模糊匹配列表项
          const tagValLower = String(tag.value).toLowerCase();
          isMatch = itemVal.some(v => String(v).toLowerCase().includes(tagValLower));
        }
        break;
        
      case FIELD_TYPES.STRING:
      default:
        // 字符串包含
        isMatch = String(itemVal || '').toLowerCase().includes(String(tag.value).toLowerCase());
        break;
    }

    return tag.exclude ? !isMatch : isMatch;
  }

  /**
   * 判断值的“三态”
   * Positive: 有实际内容的 (非空数组、true、非空字符串、非0数字)
   * Negative: 明确为空的 (false, 0, [], "")
   * Null:     根本不存在 (null, undefined)
   */
  getValueState(val) {
    if (val === undefined || val === null) return 'null';
    if (Array.isArray(val)) {
        return val.length > 0 ? 'positive' : 'negative';
    }
    if (typeof val === 'string') {
        return val.trim().length > 0 ? 'positive' : 'negative';
    }
    if (typeof val === 'boolean') {
        return val ? 'positive' : 'negative';
    }
    if (typeof val === 'number') {
      // 大于0：Positive，小于0：Null， 等于0：Negative
      return val > 0 ? 'positive' : val < 0 ? 'null' : 'negative';
    }
    // 对象等其他情况，默认视为有值
    return 'positive';
  }


  // 获取字段的“首选简写键” (Preferred Key)
  // 逻辑：在所有别名和主键中，找最短的那个。如果长度一样，优先用主键。
  getPreferredKey(key) {
    const config = this.schema[key];
    if (!config) return key;

    let candidates = [key];
    if (config.alias) {
      if (Array.isArray(config.alias)) candidates.push(...config.alias);
      else candidates.push(config.alias);
    }

    // 按长度排序，短的在前；长度相同，字母序在后（让更有语义的排前？或者保持原样）
    // 这里简单策略：找最短的
    return candidates.reduce((a, b) => a.length <= b.length ? a : b);
  }

  /**
   * [重写] 获取搜索建议
   * 目标：去重、紧凑、标准化
   */
  getSuggestions(input) {
    const suggestions = [];
    const trimmed = input.trim();
    
    // ---------------------------------------------------------
    // 场景 A: 空输入 -> 列出所有可用字段 (每个字段只显示 1 条)
    // ---------------------------------------------------------
    if (!trimmed) {
      Object.keys(this.schema).forEach(realKey => {
        const conf = this.schema[realKey];
        if (conf.searchable === false) return; 

        const shortKey = this.getPreferredKey(realKey);
        
        // 构造描述：显示全称和其他别名
        const aliases = [realKey, ...(Array.isArray(conf.alias) ? conf.alias : [conf.alias])]
          .filter(a => a && a !== shortKey) // 排除当前显示的
          // 去重
          .filter((v, i, a) => a.indexOf(v) === i)
          .join(', ');

        suggestions.push({
          type: 'key',
          label: shortKey,         // 显示：a
          value: shortKey + ':',   // 填入：a:
          desc: conf.label || realKey, // 描述：作者
          // [新增] 额外信息供 Tooltip 使用
          meta: {
            fullKey: realKey,
            aliases: aliases,
            usage: this.getFieldUsage(conf, shortKey)
          }
        });
      });

      // [可选] 排序建议列表
      // 比如把 defaultSearch 的排前面，或者按字母序
    //   suggestions.sort((a, b) => {
    //      // 这里简单按 label 长度排，短的在前？或者按字母
    //      return a.label.length - b.label.length || a.label.localeCompare(b.label);
    //   });

      return suggestions;
    }

    // ---------------------------------------------------------
    // 场景 B: 用户输入了 "key:" -> 提示 Value (大幅优化布尔值)
    // ---------------------------------------------------------
    const match = trimmed.match(/^(-?)([^:]+):(.*)$/);
    if (match) {
      const [_, prefix, keyRaw, valRaw] = match;
      const realKey = this.parser.aliasMap.get(keyRaw.toLowerCase());
      
      if (realKey) {
        const config = this.schema[realKey];
        const shortKey = this.getPreferredKey(realKey); // 强转为简写
        
        // B1. 布尔值优化：只显示 2 条 (True / False)
        if (config.type === FIELD_TYPES.BOOLEAN) {
            // 找到最简单的真值/假值表达 (通常是 + / - 或 true / false)
            const trueSign = config.trueValues[0];  // +
            const falseSign = config.falseValues[0]; // -
            const nullSign = config.nullValues[0];   // _

            const valLower = valRaw.toLowerCase();
            const suggestionsList = [];

            // 过滤：如果用户已经输入了 valRaw，比如 "fa"，则只显示 false 的建议
            // 1. Positive (+/True)
            if (config.trueValues.some(v => v.startsWith(valLower))) {
                suggestionsList.push({
                    type: 'value',
                    label: 'True / Has Value',
                    value: prefix + shortKey + ':' + trueSign,
                    desc: 'Exists & Not Empty',
                    meta: { isBool: true }
                });
            }

            // 2. Negative (-/False)
            if (config.falseValues.some(v => v.startsWith(valLower))) {
                suggestionsList.push({
                    type: 'value',
                    label: 'False / Empty',
                    value: prefix + shortKey + ':' + falseSign,
                    desc: 'Empty Array/String or False',
                    meta: { isBool: true }
                });
            }

            // 3. Null (_/Null)
            if (config.nullValues.some(v => v.startsWith(valLower))) {
                suggestionsList.push({
                    type: 'value',
                    label: 'Null / Missing',
                    value: prefix + shortKey + ':' + nullSign,
                    desc: 'Null or Undefined',
                    meta: { isBool: true }
                });
            }
            return suggestionsList;
        }

        // B2. 列表/字符串建议 (去重 + 强转简写)
        if (config.suggest) {
          const candidates = this.indices.get(realKey);
          if (candidates) {
            const valLower = valRaw.toLowerCase();
            let count = 0;
            for (const val of candidates) {
              if (val.toLowerCase().includes(valLower)) {
                const label_string = config.label_getter ? config.label_getter(val) : val;
                suggestions.push({
                  type: 'value',
                  label: label_string,
                  // 关键：这里把用户输入的 keyRaw (可能是全称) 替换为了 shortKey
                  value: prefix + shortKey + ':' + val, 
                  desc: config.label || realKey,
                  color: config.color_getter ? config.color_getter(val) : null,
                });
                count++;
                if (count > 50) break;
              }
            }
          }
        }
      }
      return suggestions;
    }

    // ---------------------------------------------------------
    // 场景 C: 用户正在输入 Key (模糊匹配)
    // ---------------------------------------------------------
    const inputLower = trimmed.toLowerCase().replace(/^-/, '');
    const isExclude = trimmed.startsWith('-');
    const prefix = isExclude ? '-' : '';

    // 遍历所有字段，看是否有“任意别名”匹配输入
    Object.keys(this.schema).forEach(realKey => {
      const conf = this.schema[realKey];
      if (!conf.searchable) return;

      // 检查：主键 或 任意别名 是否以此开头
      const allAliases = [realKey, ...(Array.isArray(conf.alias) ? conf.alias : [])];
      const isMatch = allAliases.some(a => a.toLowerCase().startsWith(inputLower));

      if (isMatch) {
        const shortKey = this.getPreferredKey(realKey);
        // 构造显示的别名列表 (排除短键自身)
        const otherAliases = allAliases.filter(a => a !== shortKey).join(', ');

        suggestions.push({
          type: 'key',
          label: shortKey,       // 即使匹配的是 author，也建议 a
          value: prefix + shortKey + ':',
          desc: conf.label || realKey,
          meta: {
            matchInfo: `${allAliases.find(a => a.toLowerCase().startsWith(inputLower))}`, // 告诉用户为什么匹配到了
            fullKey: realKey,
            aliases: otherAliases,
            usage: this.getFieldUsage(conf, shortKey)
          }
        });
      }
      return suggestions;
    });

    return suggestions;
  }

  // 辅助：生成用法示例字符串
  getFieldUsage(conf, key) {
      if (conf.type === FIELD_TYPES.BOOLEAN) return `${key}:true | ${key}:false | ${key}:null`;
      if (conf.type === FIELD_TYPES.LIST) return `${key}:Value`;
      return `${key}:XXX`;
  }
}