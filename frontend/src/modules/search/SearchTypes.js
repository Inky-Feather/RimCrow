// 定义支持的字段类型
export const FIELD_TYPES = {
  STRING: 'string',
  LIST: 'list',     // 数组，如 tags: ['Core', 'Mod']
  BOOLEAN: 'boolean',
  DATE: 'date',
  NUMBER: 'number'
};

// 默认的字段配置
export const DEFAULT_FIELD_CONFIG = {
  type: FIELD_TYPES.STRING,
  label: '',            // UI显示的名称
  alias: [],            // 别名，如 ['br', 'broken']
  searchable: true,     // 是否允许通过 key:value 搜索
  defaultSearch: false, // 是否包含在无指令的全文搜索中
  suggest: false,        // 是否出现在下拉建议中
  // 布尔值专用配置
  trueValues: ['+', 'true', 'yes', '1', 'on','T','Y'],
  falseValues: ['-', 'false', 'no', '0', 'off','F','N'],
  nullValues: ['_', 'null', 'nil', 'none'], // 定义代表 null 的字符
  // getter: 动态判断 (高级用法)
  // getter: (mod) => modStore.activeIds.includes(mod.package_id)
  getter:null
};