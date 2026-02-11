// src/stores/searchStore.js
import { defineStore } from 'pinia'
import { ref, computed, watch } from 'vue'
import { useModStore } from './modStore'
import { SearchEngine } from '../modules/search/SearchEngine'
import { FIELD_TYPES } from '../modules/search/SearchTypes'

export const useSearchStore = defineStore('search', () => {
  const modStore = useModStore()
  
  // 1. 定义 Schema (你的“配置中心”)
  // 统一配置、别名、来源、布尔值等
  const searchSchema = {
    // === 基础信息 ===
    name: { type: FIELD_TYPES.STRING, defaultSearch: true, label: '名称' },
    alias_name: { type: FIELD_TYPES.STRING, defaultSearch: true, label: '别名' },
    author: { type: FIELD_TYPES.STRING, suggest: true, defaultSearch: true, label: '作者' },
    package_id: { type: FIELD_TYPES.STRING, label: '包名' },

    // === 列表类型 ===
    tags: { type: FIELD_TYPES.LIST, suggest: true, label: '标签' },
    ignored_issues: { type: FIELD_TYPES.LIST, suggest: true, label: '忽略问题' },
    supported_versions: { type: FIELD_TYPES.LIST, suggest: true, label: '支持版本' },
    supported_languages: { type: FIELD_TYPES.LIST, suggest: true, label: '支持语言' },

    // === 布尔值 ===
    save_breaking: { type: FIELD_TYPES.BOOLEAN, label: '存档可用' },
    shadow_paths: { type: FIELD_TYPES.BOOLEAN, label: '存在禁用包名' },

    // === 来源 (枚举) ===
    source: { 
      type: FIELD_TYPES.STRING, 
      suggest: true,
      label: '来源',
    },
    mod_type: { 
        type: FIELD_TYPES.STRING, 
        suggest: true, 
        label: '类型',
        getter: (mod) => modStore.displayModType(mod)
    },
    
    // === 时间 (假设 mod 对象里有 updated_at) ===
    // last_updated: {
    //   type: FIELD_TYPES.DATE,
    //   alias: ['date', 'time'],
    //   label: '更新时间'
    // }
  }

  // 2. 维护唯一的引擎实例
  // 使用 shallowRef 因为 Engine 实例本身不需要响应式，只需替换实例时触发更新
  const engine = ref(null)

  // 3. 初始化/重建引擎的逻辑
  const rebuildEngine = () => {
    const allMods = Array.from(modStore.allModsMap.values())
  
    engine.value = new SearchEngine(allMods, {
        // 1. 强制指定的 Schema (特殊逻辑)
        schema: searchSchema,
        
        // 2. 开启自动检测 (填充 name, author, version 等常规字段)
        autoDetect: true,
        
        // 3. [新增] 排除规则
        // 支持正则，彻底屏蔽不需要的字段
        excludeFields: [
            /mods?$/i,
            /stats?$/i,
            /time$/i,
            /urls?$/i,        // 屏蔽所有以 url 结尾的 (thumb_url, preview_url)
            /paths?$/i,       // 屏蔽所有以 path 结尾的 (install_path)
            /colors?$/i,      // 屏蔽所有以 color 结尾的 (color)
            'description','notes',    // 屏蔽描述 (太长，不适合 key:value 搜索，适合全文搜索)
            'version','workshop_id','id','mod_id', 'path_hash',
            // 'ignored_issues',
        ]
    })
  }

  // 4. 监听数据源变化
  // 只有当 modStore 的数据版本号变化时，才重新建立索引
  // 这完美解决了 4 个搜索框的问题：它们共享这唯一的索引
  watch(() => modStore.dataVersion, () => {
    rebuildEngine()
  }, { immediate: true }) // 立即执行一次

  return {
    engine, // 暴露引擎实例供组件调用
    rebuildEngine
  }
})