// src/utils/constants.js

import { h, markRaw } from 'vue'

/**
 * 辅助函数：将 SVG 路径转换为 Vue 渲染函数组件
 * @param {string} colorClass Tailwind 颜色类名
 * @param {Array} paths 路径元素数组
 */
const createIcon = (colorClass, paths) => {
  const iconComponent =  {
    name: 'ModIcon',
    // 使用 functional: true (Vue 3 默认写法) 提高性能
    render() {
      return h(
        'svg',
        {
          class: ['shrink-0', colorClass],
          viewBox: '0 0 48 48',
          fill: 'none',
          xmlns: 'http://www.w3.org/2000/svg',
        },
        paths
      )
    },
  }
  // 使用 markRaw 标记该对象，防止被变成响应式
  return markRaw(iconComponent)
}
// 统一的描边属性，方便以后全局修改粗细
const STROKE_OPTS = {
  stroke: 'currentColor',
  'stroke-width': '4',
  'stroke-linecap': 'round',
  'stroke-linejoin': 'round',
}



// 错误严重等级
export const ISSUE_LEVEL = {
  ERROR: 'error',   // 红色：必须修复 (依赖缺失、版本不符)
  WARN: 'warn',     // 黄色：建议修复 (排序错误)
  INFO: 'info'      // 蓝色：提示
}

// 错误类型枚举
export const ISSUE_TYPE = {
  ERROR_MISSING_FILE: 'missing_file',               // 本地文件丢失
  ERROR_MISSING_DEPENDENCY: 'missing_dependency',   // 缺前置 (完全没装)
  ERROR_INACTIVE_DEPENDENCY: 'inactive_dependency', // 前置没启用
  ERROR_INCOMPATIBLE: 'incompatible',               // 不兼容
  WARN_WRONG_ORDER: 'wrong_order',                  // 顺序错了
  WARN_VERSION_MISMATCH: 'version_mismatch',        // 版本不对
  WARN_LINK_MOD_MISSING: 'link_mod_missing',        // 联锁模组缺失
  WARN_LINK_WRONG_ORDER: 'link_wrong_order',        // 联锁排序错误

  WARN_MISSING_LANGUAGE: 'warn_missing_language',   // 缺少语言支持
  WARN_INACTIVE_LANGUAGE_PACK: 'warn_inactive_language_pack', // 语言包未启用
  WARN_UNKNOWN_TARGET: 'warn_unknown_target',       // 未知指向对象
  WARN_INACTIVE_TARGET: 'warn_inactive_target',     // 指向对象未启用

  INFO_ALTERNATIVE_USED: 'info_alternative_used',   // 依赖替代

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
  'info_alternative_used': '依赖替代',

  'warn_missing_language': '缺少语言支持',
  'warn_inactive_language_pack': '语言包未启用',
  'warn_unknown_target': '语言包指向未知',
  'warn_inactive_target': '语言包指向未启用',

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
export const MOD_TYPE_ICON_MAP = {
  LanguagePack: createIcon('text-accent-warn', [
    h('path', { d: 'M28.2857 37H39.7143M42 42L39.7143 37L42 42ZM26 42L28.2857 37L26 42ZM28.2857 37L34 24L39.7143 37H28.2857Z', ...STROKE_OPTS }),
    h('path', { d: 'M16 6L17 9', ...STROKE_OPTS }),
    h('path', { d: 'M6 11H28', ...STROKE_OPTS }),
    h('path', { d: 'M10 16C10 16 11.7895 22.2609 16.2632 25.7391C20.7368 29.2174 28 32 28 32', ...STROKE_OPTS }),
    h('path', { d: 'M24 11C24 11 22.2105 19.2174 17.7368 23.7826C13.2632 28.3478 6 32 6 32', ...STROKE_OPTS }),
  ]),

  XML: createIcon('text-accent-success', [
    h('path', { d: 'M16 13L4 25.4322L16 37', ...STROKE_OPTS }),
    h('path', { d: 'M32 13L44 25.4322L32 37', ...STROKE_OPTS }),
    h('path', { d: 'M28 4L21 44', ...STROKE_OPTS }),
  ]),

  Assembly: createIcon('text-accent-primary', [
    h('rect', { x: '6', y: '6', width: '36', height: '36', rx: '3', ...STROKE_OPTS }),
    h('path', { d: 'M19 16V32', ...STROKE_OPTS }),
    h('path', { d: 'M29 16V32', ...STROKE_OPTS }),
    h('path', { d: 'M16 19H32', ...STROKE_OPTS }),
    h('path', { d: 'M16 29H32', ...STROKE_OPTS }),
  ]),

  Texture: createIcon('text-accent-special', [
    h('path', { d: 'M39 6H9C7.34315 6 6 7.34315 6 9V39C6 40.6569 7.34315 42 9 42H39C40.6569 42 42 40.6569 42 39V9C42 7.34315 40.6569 6 39 6Z', ...STROKE_OPTS }),
    h('path', { d: 'M18 23C20.7614 23 23 20.7614 23 18C23 15.2386 20.7614 13 18 13C15.2386 13 13 15.2386 13 18C13 20.7614 15.2386 23 18 23Z', ...STROKE_OPTS }),
    h('path', { d: 'M27.7901 26.2194C28.6064 25.1269 30.2528 25.1538 31.0329 26.2725L39.8077 38.8561C40.7322 40.182 39.7835 42.0001 38.1671 42.0001H16L27.7901 26.2194Z', ...STROKE_OPTS }),
  ]),

  Audio: createIcon('text-accent-highlight', [
    h('path', { d: 'M30 34.5C30 32.567 31.567 31 33.5 31H41V34.4C41 36.3882 39.3882 38 37.4 38H33.5C31.567 38 30 36.433 30 34.5Z', ...STROKE_OPTS }),
    h('path', { d: 'M6 38.5C6 36.567 7.567 35 9.5 35H16V38.4C16 40.3882 14.3882 42 12.4 42H9.5C7.567 42 6 40.433 6 38.5Z', ...STROKE_OPTS }),
    h('path', { d: 'M16 18.044V18.044L41 12.125', ...STROKE_OPTS }),
    h('path', { d: 'M16 38V10L41 4V33.6924', ...STROKE_OPTS }),
  ]),

  Mixed: createIcon('text-accent-cool', [
    h('rect', { x: '16', y: '16', width: '27', height: '27', rx: '2', ...STROKE_OPTS }),
    h('rect', { x: '5', y: '5', width: '27', height: '27', rx: '2', ...STROKE_OPTS }),
    h('path', { d: 'M27 16L16 27', ...STROKE_OPTS }),
    h('path', { d: 'M32 21L21 32', ...STROKE_OPTS }),
  ]),

  Unknown: createIcon('text-text-dim', [
    h('path', { d: 'M39 6H9C7.34315 6 6 7.34315 6 9V39C6 40.6569 7.34315 42 9 42H39C40.6569 42 42 40.6569 42 39V9C42 7.34315 40.6569 6 39 6Z', ...STROKE_OPTS }),
    h('path', { d: 'M24 28.625V24.625C27.3137 24.625 30 21.9387 30 18.625C30 15.3113 27.3137 12.625 24 12.625C20.6863 12.625 18 15.3113 18 18.625', ...STROKE_OPTS }),
    h('path', { fill: 'currentColor', 'fill-rule': 'evenodd', 'clip-rule': 'evenodd', d: 'M24 37.625C25.3807 37.625 26.5 36.5057 26.5 35.125C26.5 33.7443 25.3807 32.625 24 32.625C22.6193 32.625 21.5 33.7443 21.5 35.125C21.5 36.5057 22.6193 37.625 24 37.625Z' }),
  ]),
}
// 模组颜色列表
export const MOD_SIGN_COLOR_MAP = {
  '#ef4444': '红色',
  '#ec4899': '粉色',
  '#8b5cf6': '紫色',
  '#3b82f6': '蓝色',
  '#06b6d4': '青色',
  '#10b981': '绿色',
  '#84cc16': '草色',
  '#eab308': '黄色',
  '#f97316': '橙色',
}
// 模组来源映射
export const SOURCE_TYPE_MAP = {
  'core': '游戏本体',
  'dlc': 'DLC',
  'github': 'GitHub',
  'workshop': 'Steam 创意工坊',
  'local': '本地文件',
  'self': '管理器下载',
  'other': '其它来源'
}

export const RUN_COMMAND_TAGS = [
  { value: '-popupwindow', label: '无边框窗口模式' },
  { value: '-quicktest', label: '快速测试' },
]
export const IconSteam = h('svg', { viewBox: "0 0 448 512", fill: "currentColor" }, 
  [ h('path', { d: "M273.5 177.5a61 61 0 1 1 122 0 61 61 0 1 1 -122 0zm174.5 .2c0 63-51 113.8-113.7 113.8L225 371.3c-4 43-40.5 76.8-84.5 76.8-40.5 0-74.7-28.8-83-67L0 358 0 250.7 97.2 290c15.1-9.2 32.2-13.3 52-11.5l71-101.7C220.7 114.5 271.7 64 334.2 64 397 64 448 115 448 177.7zM203 363c0-34.7-27.8-62.5-62.5-62.5-4.5 0-9 .5-13.5 1.5l26 10.5c25.5 10.2 38 39 27.7 64.5-10.2 25.5-39.2 38-64.7 27.5-10.2-4-20.5-8.3-30.7-12.2 10.5 19.7 31.2 33.2 55.2 33.2 34.7 0 62.5-27.8 62.5-62.5zM410.5 177.7a76.4 76.4 0 1 0 -152.8 0 76.4 76.4 0 1 0 152.8 0z" })]
)
// <svg  class=" size-4 grayscale-20" viewBox="0 0 96 96" > <use href="/icon.svg"></use></svg>
export const IconSelf = h('svg', { viewBox: "0 0 96 96", fill: "currentColor" }, [ h('use', { href: "/icon.svg" }) ])