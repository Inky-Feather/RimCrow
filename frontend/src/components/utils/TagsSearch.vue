<template>
  <div class="relative w-full z-50" ref="containerRef">
    <!-- 主输入容器 -->
    <div class="w-full flex items-center gap-2 bg-bg-deep/50 border border-white/10 rounded-lg p-1.5 transition-all focus-within:border-accent-primary focus-within:bg-bg-deep/80 shadow-inner"
      :class="isExpanded ? 'flex-wrap' : 'flex-nowrap overflow-hidden'"
    >
      <!-- 逻辑切换开关 (AND/OR) -->
      <button 
        @click="toggleLogic"
        class="shrink-0 px-1.5 py-0.5 text-[10px] font-bold rounded cursor-pointer border transition-all select-none"
        :class="logicMode === 'AND' 
          ? 'bg-accent-primary/20 text-accent-primary border-accent-primary/30' 
          : 'bg-accent-warning/20 text-accent-warning border-accent-warning/30'"
        title="切换多条件逻辑"
      >
        {{ logicMode }}
      </button>

      <div class="flex-1 w-full flex items-center gap-1 overflow-x-auto overflow-y-hidden">

        <!-- 已生成的 Tags -->
        <div v-for="(tag, index) in modelValue" :key="index"
          class="max-w-20 flex items-center gap-1 px-1.5 py-0.5 rounded text-xs font-mono border animate-fade-in"
          :class="getTagClass(tag)">
          <!-- 排除标记 -->
          <span v-if="tag.exclude" class="text-red-400 font-bold">-</span>
          <!-- 键 (如果有) -->
          <span v-if="tag.key" class="opacity-70">{{ tag.originalKey }}:</span>
          <!-- 值 -->
          <span class="font-medium truncate max-w-[150px]" :title="tag.value">{{ tag.value }}</span>
          <!-- 删除按钮 -->
          <button 
            @click="removeTag(index)"
            class="ml-1 hover:text-white opacity-50 hover:opacity-100 focus:outline-none"
          >
            ×
          </button>
        </div>

        <!-- 输入框 -->
        <input ref="inputRef" v-model="inputValue" type="text" 
          
          class=" min-w-20 w-full truncate bg-transparent border-none outline-none text-sm text-white placeholder-text-dim/50 font-mono py-0.5"
          :placeholder="placeholderText"
          @keydown="handleKeydown"
          @focus="showSuggestions = true"
          @blur="handleBlur"
          @input="handleInput"
        />

      </div>

      <!-- 右侧控制区 -->
      <div class="flex items-center gap-1 shrink-0">
        <!-- 清除按钮 -->
        <button v-show="modelValue.length > 0 || inputValue" @click="clearAll" class="p-1 text-text-dim hover:text-white" title="清除全部">
          <svg class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
        </button>
        <!-- 展开/收起按钮 (仅当Tag较多时有效，这里简单处理常驻或根据数量判断) -->
        <button @click="isExpanded = !isExpanded" class="p-1 text-text-dim hover:text-white transition-transform" :class="isExpanded ? 'rotate-180' : ''">
           <svg class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/></svg>
        </button>
      </div>
    </div>

    <!-- 自动补全下拉菜单 -->
    <Transition name="fade">
      <div v-if="showSuggestions && suggestionList.length > 0" 
        class="absolute left-0 right-0 top-full mt-1 max-h-60 overflow-y-auto bg-bg-surface border border-white/10 rounded-lg shadow-2xl z-100 custom-scrollbar"
      >
        <div 
          v-for="(item, index) in suggestionList" 
          :key="index"
          class="px-3 py-1.5 text-xs cursor-pointer flex items-center justify-between group transition-colors"
          :class="highlightIndex === index ? 'bg-accent-primary/20 text-white' : 'text-text-dim hover:bg-white/5'"
          @mousedown.prevent="applySuggestion(item)"
          @mouseover="highlightIndex = index"
        >
          <div class="flex items-center gap-2">
            <!-- 图标/类型指示 -->
            <span class="opacity-50 font-mono text-[10px] w-6 text-right">{{ item.type === 'key' ? 'KEY' : 'VAL' }}</span>
            <!-- 内容 -->
            <span class="font-mono">
              <span v-if="item.prefix" class="text-accent-secondary">{{ item.prefix }}</span>
              <span class="text-text-main" v-html="highlightMatch(item.label)"></span>
            </span>
          </div>
          <!-- 说明 -->
          <span v-if="item.desc" class="text-[10px] opacity-40">{{ item.desc }}</span>
        </div>
      </div>
    </Transition>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, nextTick } from 'vue'

const props = defineProps({
  // 核心数据源
  data: { type: Array, required: true, default: () => [] },
  // Schema定义: { 'tags': 'list', 'name': 'string' }
  schema: { type: Object, required: true },
  // 默认搜索范围
  defaultScope: { type: Array, default: () => ['name'] },
  // v-model 绑定的 Tags 数组
  modelValue: { type: Array, default: () => [] },
  // 外部传入的逻辑模式 v-model:logic
  logic: { type: String, default: 'AND' }
})

const emit = defineEmits(['update:modelValue', 'update:logic', 'search'])

// --- 状态 ---
const inputValue = ref('')
const logicMode = ref(props.logic) // AND / OR
const isExpanded = ref(false)
const showSuggestions = ref(false)
const highlightIndex = ref(0)
const containerRef = ref(null)
const inputRef = ref(null)

// 内部映射表 & 数据缓存
const keyMapping = ref({}) // { 't': 'tags', 'tags': 'tags' }
const valueCache = ref({}) // { 'tags': Set(['Core', ...]) }

// --- 1. 自动化初始化逻辑 ---

// 生成简写映射
const generateKeyMap = () => {
  const map = {}
  const usedKeys = new Set()
  
  Object.keys(props.schema).forEach(fullKey => {
    // 1. 保留全名
    map[fullKey] = fullKey
    usedKeys.add(fullKey)
    
    // 2. 生成简写
    let short = ''
    for (let i = 0; i < fullKey.length; i++) {
      short += fullKey[i].toLowerCase()
      // 如果这个简写没被用过，且不是全名本身
      if (!usedKeys.has(short) && short !== fullKey) {
        map[short] = fullKey
        usedKeys.add(short)
        break // 找到最短唯一前缀，停止
      }
    }
  })
  keyMapping.value = map
  console.log('SmartInput: Key Mapping Generated:', map)
}

// 提取数据值缓存
const generateValueCache = () => {
  if (!props.data.length) return
  
  const cache = {}
  // 初始化 Set
  Object.keys(props.schema).forEach(k => cache[k] = new Set())
  
  props.data.forEach(item => {
    Object.keys(props.schema).forEach(key => {
      const type = props.schema[key]
      const val = item[key]
      if (!val) return
      
      if (type === 'list' && Array.isArray(val)) {
        val.forEach(v => cache[key].add(v))
      } else {
        cache[key].add(String(val))
      }
    })
  })
  valueCache.value = cache
}

// 监听数据变化重新索引
watch(() => props.data, generateValueCache, { immediate: true })
watch(() => props.schema, generateKeyMap, { immediate: true })


// --- 2. 交互与搜索逻辑 ---

// 动态计算建议列表
const suggestionList = computed(() => {
  const input = inputValue.value.trim()
  if (!input) {
    // 空输入：显示所有可用 Key
    return Object.entries(keyMapping.value)
      .filter(([short, full]) => short !== full) // 只显示简写，减少冗余
      .map(([short, full]) => ({
        type: 'key',
        label: short,
        prefix: '',
        value: short + ':',
        desc: `按属性搜索: ${full}`
      }))
  }

  // 情况 A: 用户正在输入 Key (没有冒号) -> 匹配 Key
  if (!input.includes(':')) {
    // 匹配 Key
    const keyMatches = Object.entries(keyMapping.value)
      .filter(([short]) => short.startsWith(input.replace(/^-/, ''))) // 忽略前面的 -
      .map(([short, full]) => ({
        type: 'key',
        label: short,
        prefix: input.startsWith('-') ? '-' : '',
        value: (input.startsWith('-') ? '-' : '') + short + ':',
        desc: `属性: ${full}`
      }))
    
    // 也匹配默认范围的值 (如输入 'Co' 提示 'Core')
    // 这里为了性能，只取 defaultScope 第一个字段做示例，或者根据 input 长度决定是否搜索
    return keyMatches
  }

  // 情况 B: 用户输入了 Key:Value -> 匹配 Value
  const match = input.match(/^(-?)([^:]+):(.*)$/)
  if (match) {
    const [_, prefix, keyPart, valPart] = match
    const fullKey = keyMapping.value[keyPart]
    
    if (fullKey && valueCache.value[fullKey]) {
      // 在对应字段的值中搜索
      const candidates = Array.from(valueCache.value[fullKey])
      const lowerVal = valPart.toLowerCase()
      
      return candidates
        .filter(v => v.toLowerCase().includes(lowerVal))
        .slice(0, 20) // 限制数量
        .map(v => ({
          type: 'value',
          label: v,
          prefix: prefix + keyPart + ':',
          value: prefix + keyPart + ':' + v,
          desc: fullKey
        }))
    }
  }
  
  return []
})

// 高亮匹配文字
const highlightMatch = (text) => {
  // 简单实现：高亮输入部分
  // 实际项目中建议使用专用库或更复杂的正则
  return text
}

const getTagClass = (tag) => {
  if (tag.exclude) return 'bg-red-900/30 border-red-500/30 text-red-200'
  if (tag.key) return 'bg-accent-primary/10 border-accent-primary/20 text-accent-primary'
  return 'bg-white/5 border-white/10 text-gray-300' // 纯文本
}

// 提交 Tag
const addTag = (rawInput) => {
  const input = rawInput.trim()
  if (!input) return

  let newTag = null
  
  // 解析: (-)?(key):?(value)
  // 支持简写 t:Core 或 完整 tags:Core
  const match = input.match(/^(-?)([^:]+):(.*)$/)
  
  if (match) {
    const [_, excludeStr, keyRaw, valueRaw] = match
    const fullKey = keyMapping.value[keyRaw]
    
    if (fullKey) {
      // 是有效的结构化搜索
      newTag = {
        type: 'rule',
        key: fullKey,        // 存全名，方便过滤逻辑
        originalKey: keyRaw, // 存用户输入的简写，方便显示
        value: valueRaw,
        exclude: excludeStr === '-'
      }
    }
  }
  
  // 如果没匹配上，或者Key不对，视为纯文本搜索
  if (!newTag) {
    // 纯文本也支持排除: -文本
    const isExclude = input.startsWith('-')
    newTag = {
      type: 'text',
      key: null,
      value: isExclude ? input.slice(1) : input,
      exclude: isExclude
    }
  }

  // 发出更新
  const newTags = [...props.modelValue, newTag]
  emit('update:modelValue', newTags)
  
  // 清空输入
  inputValue.value = ''
  showSuggestions.value = false
  emit('search') // 触发父组件搜索
}

const removeTag = (index) => {
  const newTags = [...props.modelValue]
  newTags.splice(index, 1)
  emit('update:modelValue', newTags)
  emit('search')
}

const clearAll = () => {
  emit('update:modelValue', [])
  inputValue.value = ''
  emit('search')
}

const toggleLogic = () => {
  logicMode.value = logicMode.value === 'AND' ? 'OR' : 'AND'
  emit('update:logic', logicMode.value)
  emit('search')
}

// --- 键盘事件 ---
const handleKeydown = (e) => {
  if (e.key === 'Enter' && inputValue.value) {
    // 直接提交输入
    addTag(inputValue.value)
  } else if (e.key === 'Tab' && showSuggestions.value && suggestionList.value.length > 0) {
    // 优先采纳建议（如果有高亮）
    applySuggestion(suggestionList.value[highlightIndex.value])
  } else if (e.key === 'Backspace' && !inputValue.value && props.modelValue.length) {
    // 输入框为空时，回删最后一个Tag
    removeTag(props.modelValue.length - 1)
  } else if (e.key === 'ArrowDown') {
    e.preventDefault()
    if (highlightIndex.value < suggestionList.value.length - 1) highlightIndex.value++
  } else if (e.key === 'ArrowUp') {
    e.preventDefault()
    if (highlightIndex.value > 0) highlightIndex.value--
  }
}

const applySuggestion = (item) => {
  if (item.type === 'key') {
    // 如果选的是 Key，填入输入框并继续输入值
    inputValue.value = item.value 
    inputRef.value.focus()
    // 保持建议框打开，重置高亮
    highlightIndex.value = 0
  } else {
    // 如果选的是 Value，直接生成 Tag
    addTag(item.value)
  }
}

const handleBlur = () => {
  // 延迟关闭，以便点击事件能先触发
  setTimeout(() => {
    showSuggestions.value = false
  }, 200)
}

const handleInput = () => {
  showSuggestions.value = true
  highlightIndex.value = 0
}

// placeholder 提示
const placeholderText = computed(() => {
  if (props.modelValue.length > 0) return '添加筛选...'
  const examples = Object.keys(keyMapping.value).slice(0, 3).map(k => `${k}:...`).join(' ')
  return `输入关键词 或 ${examples}`
})

</script>

<style scoped>
.animate-fade-in {
  animation: fadeIn 0.2s ease-out;
}
@keyframes fadeIn {
  from { opacity: 0; transform: scale(0.9); }
  to { opacity: 1; transform: scale(1); }
}

/* 自定义滚动条 */
.custom-scrollbar::-webkit-scrollbar {
  width: 4px;
}
.custom-scrollbar::-webkit-scrollbar-track {
  background: rgba(0,0,0,0.1);
}
.custom-scrollbar::-webkit-scrollbar-thumb {
  background: rgba(255,255,255,0.2);
  border-radius: 2px;
}
.custom-scrollbar::-webkit-scrollbar-thumb:hover {
  background: rgba(255,255,255,0.3);
}
</style>