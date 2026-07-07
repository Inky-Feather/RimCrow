// src/utils/constants.js

import { h, markRaw } from 'vue'
import defaultLogoUrl from '../../../../icon.svg'
import { t } from '../i18n'

export const RIMWORLD_STEAM_APP_ID = 294100

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
  ERROR_MISSING_FILE: 'missing_file',               // 本地文件缺失
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
  WARN_MULTIPLAYER_COMPATIBILITY: 'warn_multiplayer_compatibility', // 旧版联机兼容性类型，保留用于兼容历史忽略记录
  ERROR_MULTIPLAYER_INCOMPATIBLE: 'multiplayer_incompatible',       // 不兼容联机
  WARN_MULTIPLAYER_BARELY_COMPATIBLE: 'multiplayer_barely_compatible', // 勉强兼容联机
  INFO_MULTIPLAYER_UNKNOWN: 'multiplayer_unknown',                  // 联机兼容性未知

  INFO_ALTERNATIVE_USED: 'info_alternative_used',   // 依赖替代

}

export const getIssueTitle = (type) => {
  const key = String(type || 'default')
  if (key === 'missing_file') return t('ui.issue.missing_file', '文件缺失')
  if (key === 'missing_dependency') return t('ui.issue.missing_dependency', '依赖缺失')
  if (key === 'inactive_dependency') return t('ui.issue.inactive_dependency', '依赖未启用')
  if (key === 'incompatible') return t('ui.issue.incompatible', '模组冲突')
  if (key === 'wrong_order') return t('ui.issue.wrong_order', '排序错误')
  if (key === 'version_mismatch') return t('ui.issue.version_mismatch', '版本不符')
  if (key === 'link_mod_missing') return t('ui.issue.link_mod_missing', '联锁模组缺失')
  if (key === 'link_wrong_order') return t('ui.issue.link_wrong_order', '联锁排序错误')
  if (key === 'info_alternative_used') return t('ui.issue.info_alternative_used', '依赖替代')
  if (key === 'warn_missing_language') return t('ui.issue.warn_missing_language', '缺少语言支持')
  if (key === 'warn_inactive_language_pack') return t('ui.issue.warn_inactive_language_pack', '语言包未启用')
  if (key === 'warn_unknown_target') return t('ui.issue.warn_unknown_target', '语言包指向未知')
  if (key === 'warn_inactive_target') return t('ui.issue.warn_inactive_target', '语言包指向未启用')
  if (key === 'warn_multiplayer_compatibility') return t('ui.issue.warn_multiplayer_compatibility', '联机兼容性')
  if (key === 'multiplayer_incompatible') return t('ui.issue.multiplayer_incompatible', '不兼容联机')
  if (key === 'multiplayer_barely_compatible') return t('ui.issue.multiplayer_barely_compatible', '勉强兼容联机')
  if (key === 'multiplayer_unknown') return t('ui.issue.multiplayer_unknown', '联机兼容性未知')
  return t('ui.issue.default', '其他问题')
}

export const getModTypeLabel = (type) => {
  if (type === 'LanguagePack') return t('ui.mod_type.LanguagePack', '语言包')
  if (type === 'XML') return t('ui.mod_type.XML', '纯XML')
  if (type === 'Assembly') return t('ui.mod_type.Assembly', '含程序集')
  if (type === 'Texture') return t('ui.mod_type.Texture', '纹理包')
  if (type === 'Audio') return t('ui.mod_type.Audio', '音频包')
  if (type === 'Mixed') return t('ui.mod_type.Mixed', '混合')
  if (type === 'Unknown') return t('ui.mod_type.Unknown', '未知类型')
  return type || t('ui.mod_type.Unknown', '未知类型')
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
export const MOD_SIGN_COLORS = ['#ef4444', '#ec4899', '#8b5cf6', '#3b82f6', '#06b6d4', '#10b981', '#84cc16', '#eab308', '#f97316']
export const getModSignColorLabel = (color) => {
  if (color === '#ef4444') return t('ui.mod_sign_color.red', '红色')
  if (color === '#ec4899') return t('ui.mod_sign_color.pink', '粉色')
  if (color === '#8b5cf6') return t('ui.mod_sign_color.purple', '紫色')
  if (color === '#3b82f6') return t('ui.mod_sign_color.blue', '蓝色')
  if (color === '#06b6d4') return t('ui.mod_sign_color.cyan', '青色')
  if (color === '#10b981') return t('ui.mod_sign_color.green', '绿色')
  if (color === '#84cc16') return t('ui.mod_sign_color.lime', '草色')
  if (color === '#eab308') return t('ui.mod_sign_color.yellow', '黄色')
  if (color === '#f97316') return t('ui.mod_sign_color.orange', '橙色')
  return color || t('common.status.none', '无')
}
export const getSourceTypeLabel = (source) => {
  if (source === 'core') return t('common.source.core', '游戏本体')
  if (source === 'dlc') return t('common.source.dlc', 'DLC')
  if (source === 'github') return t('common.source.github', 'Git 仓库')
  if (source === 'workshop') return t('common.source.workshop', 'Steam 创意工坊')
  if (source === 'local') return t('common.source.local', '本地模组')
  if (source === 'self') return t('common.source.self', '管理器下载')
  if (source === 'other') return t('common.source.other', '其它来源')
  return source || t('common.source.unknown', '未知来源')
}
export const getStoreTypeLabel = (store) => {
  if (store === 'core') return t('common.store.core', '本体')
  if (store === 'dlc') return t('common.store.dlc', 'DLC')
  if (store === 'local') return t('common.store.local', '本地')
  if (store === 'self') return t('common.store.self', '管理器')
  if (store === 'workshop') return t('common.store.workshop', '工坊')
  if (store === 'other') return t('common.store.other', '其它')
  return store || t('common.store.unknown', '未知')
}


export const getRunCommandTags = () => [
  { value: '-popupwindow', label: t('common.run_command.popup_window', '无边框窗口模式') },
  { value: '-quicktest', label: t('common.run_command.quick_test', '快速测试') },
]
export const RUN_COMMAND_TAGS = getRunCommandTags()
const STEAM_ICON_PATH = 'M273.5 177.5a61 61 0 1 1 122 0 61 61 0 1 1 -122 0zm174.5 .2c0 63-51 113.8-113.7 113.8L225 371.3c-4 43-40.5 76.8-84.5 76.8-40.5 0-74.7-28.8-83-67L0 358 0 250.7 97.2 290c15.1-9.2 32.2-13.3 52-11.5l71-101.7C220.7 114.5 271.7 64 334.2 64 397 64 448 115 448 177.7zM203 363c0-34.7-27.8-62.5-62.5-62.5-4.5 0-9 .5-13.5 1.5l26 10.5c25.5 10.2 38 39 27.7 64.5-10.2 25.5-39.2 38-64.7 27.5-10.2-4-20.5-8.3-30.7-12.2 10.5 19.7 31.2 33.2 55.2 33.2 34.7 0 62.5-27.8 62.5-62.5zM410.5 177.7a76.4 76.4 0 1 0 -152.8 0 76.4 76.4 0 1 0 152.8 0z'
export const IconSteam = markRaw({
  name: 'IconSteam',
  inheritAttrs: false,
  render() {
    return h('svg', { ...this.$attrs, viewBox: '0 0 448 512', fill: 'currentColor' }, [
      h('path', { d: STEAM_ICON_PATH }),
    ])
  },
})
export const IconSelf = markRaw({
  name: 'IconSelf',
  inheritAttrs: false,
  render() {
    return h('svg', { ...this.$attrs, viewBox: '18 15 60 66', fill: 'currentColor', 'aria-hidden': 'true' }, [
      h('path', { opacity: '0.95', d: 'M48 16 76.3 31 48 45.9 19.7 31 48 16Z' }),
      h('path', { opacity: '0.72', d: 'M48 45.9 76.3 31v33.4c0 .5-.3 1-.8 1.3L48 80V45.9Z' }),
      h('path', { opacity: '0.5', d: 'M19.7 31 48 45.9V80L20.5 65.7c-.5-.3-.8-.8-.8-1.3V31Z' }),
    ])
  },
})
export const IconSelfOriginal = markRaw({
  name: 'IconSelfOriginal',
  inheritAttrs: false,
  render() {
    return h('img', { ...this.$attrs, src: defaultLogoUrl, alt: '', draggable: false, 'aria-hidden': 'true' })
  },
})
