// src/utils/constants.js

// 错误严重等级
export const ISSUE_LEVEL = {
  ERROR: 'error',   // 红色：必须修复 (依赖缺失、版本不符)
  WARN: 'warn',     // 黄色：建议修复 (排序错误)
  INFO: 'info'      // 蓝色：提示
}

// 错误类型枚举
export const ISSUE_TYPE = {
  ERROR_MISSING_FILE: 'missing_file',      // 本地文件丢失
  ERROR_MISSING_DEPENDENCY: 'missing_dependency', // 缺前置 (完全没装)
  ERROR_INACTIVE_DEPENDENCY: 'inactive_dependency', // 前置没启用
  ERROR_INCOMPATIBLE: 'incompatible',     // 不兼容
  WARN_WRONG_ORDER: 'wrong_order',       // 顺序错了
  WARN_VERSION_MISMATCH: 'version_mismatch', // 版本不对
  WARN_LINK_MOD_MISSING: 'link_mod_missing', // 联锁模组缺失
  WARN_LINK_WRONG_ORDER: 'link_wrong_order', // 联锁排序错误
}

// 定义类型到中文标题的映射
export const ISSUE_TITLE_MAP = {
  'missing_file': '文件丢失',
  'missing_dependency': '依赖缺失',
  'inactive_dependency': '依赖未启用',
  'incompatible': '模组冲突',
  'wrong_order': '排序错误',
  'version_mismatch': '版本不符',
  'link_mod_missing': '联锁模组缺失',
  'link_wrong_order': '联锁排序错误',
  'default': '其他问题'
}

// 模组类型映射
export const MOD_TYPE_MAP = {
  'LanguagePack': '语言包',
  'XML': '纯XML',
  'Assembly': '含程序集',
  'Texture': '纹理包',
  'Audio': '音频包',
  'Mixed': '混合',
  'Unknown': '未知类型'
}
// 模组颜色列表
export const MOD_COLOR_LIST = [
  '#ef4444',
  '#ec4899',
  '#8b5cf6',
  '#3b82f6',
  '#06b6d4',
  '#10b981',
  '#84cc16',
  '#eab308',
  '#f97316'
]
// 模组来源映射
export const SOURCE_TYPE_MAP = {
  'core': '游戏本体',
  'dlc': 'DLC',
  'github': 'GitHub',
  'workshop': 'Steam 创意工坊',
  'local': '本地文件',
  'other': '其它来源'
}