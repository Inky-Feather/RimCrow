import { defineStore } from 'pinia'
import { ref, shallowRef, watch } from 'vue'
import { useModStore } from './modStore'
import { TagSearchEngine, TAG_FIELD_TYPES } from '../../../shared/components/tag-search/tagSearchEngine'
import { MOD_SIGN_COLOR_MAP } from '../../../shared/lib/constants'
import { useAppStore } from '../../../app/stores/appStore'

export const useSearchStore = defineStore('search', () => {
  const modStore = useModStore()
  const appStore = useAppStore()
  const STORE_MAP = {'local': '本地', 'self': '管理器', 'workshop': '创意工坊'}

  // 统一声明 Mod 列表可搜索字段。这里只放用户能理解、且适合 key:value 检索的字段；
  // 路径、描述、规则等长文本不进入语法字段，避免建议列表变脏、搜索结果难解释。
  const searchSchema = {
    // 基础信息
    name: { type: TAG_FIELD_TYPES.STRING, defaultSearch: true, label: '名称' },
    alias_name: { type: TAG_FIELD_TYPES.STRING, defaultSearch: true, label: '别名' },
    author: { type: TAG_FIELD_TYPES.STRING, suggest: true, defaultSearch: true, label: '作者' },
    package_id: { type: TAG_FIELD_TYPES.STRING, label: '包名' },
    workshop_id: { type: TAG_FIELD_TYPES.STRING, label: '工坊ID' },

    // 用户标记
    sign_color: {
      type: TAG_FIELD_TYPES.STRING,
      suggest: true,
      label: '颜色',
      label_getter: (color) => MOD_SIGN_COLOR_MAP[color] || color || '无',
      color_getter: (color) => color || 'var(--color-text-main)',
    },
    tags: { type: TAG_FIELD_TYPES.LIST, suggest: true, label: '标签' },
    groups: { type: TAG_FIELD_TYPES.LIST, suggest: true, label: '分组' },

    // 来源与类型
    mod_type: {
      type: TAG_FIELD_TYPES.STRING,
      suggest: true,
      label: '类型',
      getter: (mod) => modStore.displayModType(mod)
    },
    source: {
      type: TAG_FIELD_TYPES.STRING,
      suggest: true,
      label: '来源',
    },
    store: {
      type: TAG_FIELD_TYPES.STRING,
      suggest: true,
      label: '位置',
      label_getter: (store) => STORE_MAP[store] || '未知'
    },

    // 支持信息
    supported_versions: { type: TAG_FIELD_TYPES.LIST, suggest: true, label: '支持版本' },
    supported_languages: { type: TAG_FIELD_TYPES.LIST, suggest: true, label: '支持语言' },
    multiplayer_compat: {
      type: TAG_FIELD_TYPES.LIST,
      suggest: true,
      label: '联机模组兼容性',
      alias: ['联机模组兼容性', '联机兼容', 'mp兼容'],
      getter: (mod) => mod?.multiplayer_compat?.search_values || [],
    },
    ignored_issues: { type: TAG_FIELD_TYPES.LIST, suggest: true, label: '忽略问题' },

    // 状态判断
    last_active: {
      type: TAG_FIELD_TYPES.BOOLEAN,
      label: '最近启用',
      getter: (mod) => mod.last_active_time > appStore.settings.last_run_time
    },
    coexist_variant: {
      type: TAG_FIELD_TYPES.BOOLEAN,
      label: '存在共存',
      getter: (mod) => !!mod.coexist_workshop_variant
    },
    shadow_paths: { type: TAG_FIELD_TYPES.BOOLEAN, label: '存在禁用' },
    replacement: { type: TAG_FIELD_TYPES.BOOLEAN, label: '存在替代' },
    save_breaking: { type: TAG_FIELD_TYPES.BOOLEAN, label: '是否坏档' },
  }

  // 引擎内部持有 Map/Set 索引，只需要在重建时替换实例，不需要深层响应式代理。
  const engine = shallowRef(null)
  const mainListExactFilter = ref(null)
  const mainListFilterRevision = ref(0)

  const normalizeFilterText = (value) => String(value ?? '').trim()
  const normalizeFilterKey = (value) => normalizeFilterText(value).toLowerCase()

  const applyMainListExactFilter = ({ field = '', value = '', label = '' } = {}) => {
    const normalizedField = normalizeFilterText(field)
    const normalizedValue = normalizeFilterText(value)
    const normalizedKey = normalizeFilterKey(normalizedValue)
    const current = mainListExactFilter.value

    if (!normalizedField || !normalizedValue || (
      current?.field === normalizedField && current?.normalizedValue === normalizedKey
    )) {
      mainListExactFilter.value = null
      mainListFilterRevision.value += 1
      return
    }

    mainListExactFilter.value = {
      field: normalizedField,
      value: normalizedValue,
      normalizedValue: normalizedKey,
      label: normalizeFilterText(label) || normalizedValue,
    }
    mainListFilterRevision.value += 1
  }

  const rebuildEngine = () => {
    const allMods = Array.from(modStore.allModsMap.values())

    // Mod 列表的两个搜索框共用同一个索引；数据版本变化时重建，输入变化时只执行匹配。
    engine.value = new TagSearchEngine(allMods, {
      schema: searchSchema,
      autoDetect: false,
      excludeFields: [
        // 这些规则主要保护未来误开 autoDetect 时不会暴露内部字段；当前显式 schema 不受影响。
        /mods?$/i, /stats?$/i, /time$/i,
        /urls?$/i, /paths?$/i, /colors?$/i,
        'description', 'descriptions_by_version', 'notes',
        'version', 'id', 'mod_id', 'path_hash', 'rules', 'disabled',
        'package_id_raw', 'language_pack_owner_result', 'file_size',
      ],
    })
  }

  watch(() => modStore.dataVersion, () => {
    rebuildEngine()
  }, { immediate: true })

  return {
    // 搜索引擎
    engine, rebuildEngine,
    // 主列表筛选
    mainListExactFilter, mainListFilterRevision, applyMainListExactFilter,
  }
})
