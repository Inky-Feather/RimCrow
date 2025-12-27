<template>
  <div class="flex items-center w-full gap-1" ref="containerRef" >
     <!-- 左侧附加区 -->
    <div class="flex-none flex items-center justify-center">
      <slot name="left">
        <!-- 逻辑切换开关 (AND/OR) -->
        <button @click="toggleLogic" :title="logicMode === 'AND' ? '切换为OR逻辑' : '切换为AND逻辑'"
          class="shrink-0 w-6 h-6 font-bold cursor-pointer border transition-all relative"
          :class="[ props.circle ? 'rounded-full' : 'rounded-md',
            logicMode === 'AND' ? 'bg-accent-primary/20 text-accent-primary border-accent-primary/30' : 'bg-accent-warning/20 text-accent-warning border-accent-warning/30',]">
          <!-- 圆形按钮旋转动画 -->
          <div v-if="circle" class="absolute inset-0 flex items-center justify-center ">
            <svg class="transition-all duration-400 ease-in-out"
                :class="{'opacity-100 rotate-0': logicMode === 'AND', 'opacity-0 rotate-180': logicMode === 'OR'}" 
                xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m8 6 4-4 4 4"/><path d="M12 2v10.3a4 4 0 0 1-1.172 2.872L4 22"/><path d="m20 22-5-5"/></svg>
            <svg class="transition-all duration-400 ease-in-out absolute"
                :class="{ 'opacity-0 -rotate-180': logicMode === 'AND', 'opacity-100 rotate-0': logicMode === 'OR' }" 
                xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M16 3h5v5"/><path d="M8 3H3v5"/><path d="M12 22v-8.3a4 4 0 0 0-1.172-2.872L3 3"/><path d="m15 9 6-6"/></svg>
          </div>
          <!-- 方形按钮翻转动画 -->
          <div v-else class="absolute inset-0 flex items-center justify-center transition-all duration-500 ease transform-gpu" style="transform-style: preserve-3d;">
            <svg class="backface-hidden absolute transition-all duration-300" :class="logicMode === 'AND' ? 'rotate-x-0 opacity-100' : 'rotate-x-180 opacity-0'"
                xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m8 6 4-4 4 4"/><path d="M12 2v10.3a4 4 0 0 1-1.172 2.872L4 22"/><path d="m20 22-5-5"/></svg>
            <svg class="backface-hidden absolute transition-all duration-300" :class="logicMode === 'OR' ? 'rotate-x-0 opacity-100' : 'rotate-x-180 opacity-0'"
                xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M16 3h5v5"/><path d="M8 3H3v5"/><path d="M12 22v-8.3a4 4 0 0 0-1.172-2.872L3 3"/><path d="m15 9 6-6"/></svg>
          </div>
          
        </button>
      </slot>
    </div>

    <!-- 主要区域 -->
    <div class="relative flex-1 z-50 min-w-0 w-6 outline-none">
      <!-- 主输入容器（@keydown.tab.prevent禁止切换焦点功能） -->
      <div @keydown.tab.prevent class="w-full flex items-center gap-1 px-1 pt-0.5 outline-none bg-bg-deep/50 transition-all 
        border rounded-lg text-text-main border-text-dim/30 focus-within:border-accent-primary focus-within:bg-bg-deep/70 shadow-inner"
        :class="`hover:border-accent-${listColor} focus:border-accent-${listColor} focus-within:border-accent-${listColor}`">
        <!-- 图标 -->
        <slot name="icon">
          <svg class="w-3 h-3 text-text-dim" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" /></svg>
        </slot>
        <!-- 输入区域 + Tags -->
        <div class=" h-6 flex-1 flex overflow-x-scroll custom-scrollbar outline-none" 
            v-drag-scroll="{step: 20, wheelToHorizontal: true}" 
            ref="scrollContainer">
          <!-- 已生成的 Tags -->  
          <!-- Tags 列表 (使用 TransitionGroup 实现完美动画) -->
          <TransitionGroup v-if="!isExpanded" name="tag-list">
            <Tag v-for="(tag, index) in modelValue" :key="tag.id || index" :tag="tag" 
              :is-editing="editingIndex===index"
              @remove="removeTag(index)" @edit-start="editingIndex = index" 
              @edit-cancel="cancelEditing(index)" @update-value="(val) => stopEditing(index, val)"/>
          </TransitionGroup>

          <!-- 输入框 -->
          <input ref="inputRef" v-model="inputValue" type="text" 
            class="w-full flex-1 min-w-20 truncate bg-transparent border-none outline-none text-xs text-text-main placeholder-text-dim/60 py-0.5"
            :placeholder="placeholderText"
            @focus="showSuggestions = true"
            @keydown="handleKeydown" @blur="handleBlur"
            @input="handleInput" @keyup.esc="handleBlur"
          />
        </div>

        <!-- 右侧控制区 -->
        <div class="flex items-center gap-0.5 shrink-0">
          <!-- 清除按钮 -->
          <button v-show="modelValue.length > 0 || inputValue" @click="clearAll" class="p-1 text-text-dim hover:text-accent-danger transition-colors" title="清除全部">
            <svg class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="3" d="M6 18L18 6M6 6l12 12"/></svg>
          </button>
          <!-- 展开/收起按钮 -->
          <button @click="isExpanded = !isExpanded" class="p-1 text-text-dim hover:text-white transition-transform" :class="isExpanded ? 'rotate-180' : ''">
            <svg class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/></svg>
          </button>
        </div>
      </div>

      <!-- 自动补全下拉菜单 -->
      <Transition name="fade-drop">
        <div v-if="showSuggestions && suggestionList.length > 0" ref="suggestionContainer"
          class="absolute left-0 right-0 top-full mt-1 max-h-60 overflow-y-auto overflow-x-hidden bg-bg-surface/70 border border-white/10 backdrop-blur-md rounded-lg shadow-2xl z-100"
        >
          <div v-for="(item, index) in suggestionList" :key="index" :ref="el => { if (el) suggestionRefs[index] = el }"
            class="pl-1 pr-3 py-1.5 text-xs cursor-pointer flex items-center justify-between group transition-colors"
            :class="[highlightIndex === index ? 'bg-accent-primary/20 text-white' : 'text-text-dim hover:bg-white/5']"
            @mousedown.prevent="applySuggestion(item)"
            @mouseover="highlightIndex = index"
          >
            <div class="flex items-center gap-1">
              <!-- 图标/类型指示 -->
              <span class="text-[10px] w-8 h-4 flex items-center justify-center rounded bg-white/5 font-mono"
                 :class="item.type === 'key' ? 'text-[rgb(var(--accent-rgb))]' : 'text-green-400'">
                {{ item.type === 'key' ? 'KEY' : 'VAL' }}
              </span>
              <!-- 内容 -->
              <span class="font-mono">
                <span v-if="item.prefix" class="text-accent-secondary">{{ item.prefix }}</span>
                <span :class="highlightIndex === index ? 'text-white' : 'text-gray-300'">{{ item.label }}</span>
              </span>
            </div>
            <!-- 说明 -->
            <span v-if="item.desc" class="text-[10px] opacity-40">{{ item.desc }}</span>
          </div>
        </div>
      </Transition>
        
      <!-- 标签面板 -->
      <TransitionGroup tag="div" v-if="isExpanded" name="tag-list"
        class="absolute flex flex-wrap p-1.5 gap-1 left-0 right-0 top-full mt-1 ransition-all duration-200 
        overflow-y-auto overflow-x-hidden bg-bg-deep/70 border border-white/10 backdrop-blur-md rounded-lg shadow-2xl z-99"
      >
        <Tag v-for="(tag, index) in modelValue" :key="tag.id || index" :tag="tag" 
            :is-editing="editingIndex===index"
            @remove="removeTag(index)" @edit-start="editingIndex = index" 
            @edit-cancel="cancelEditing(index)" @update-value="(val) => stopEditing(index, val)"/>
      </TransitionGroup>
      
    </div>

    <!-- 右侧附加区 -->
    <div class="flex-none">
      <slot name="right">

      </slot>
    </div>

  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick, shallowRef, toRaw } from 'vue' // 新增 shallowRef, toRaw
import vDragScroll from '../../directives/dragScroll.js' //直接引入即可自动注册（注意命名需以 v 开头）用于标签面板的拖动滚动
import Tag from './Tag.vue'

// const directives = {
//   // 自定义指令：可拖动滚动 名称需要以 v- 开头
//   'v-drag-scroll': dragScroll
// }
const props = defineProps({
  // v-model 绑定的 Tags 数组，即输出结果，格式[{key:'',value:'',exclude:false}]
  modelValue: { type: Array, default: () => [] },
  // 传出外部的逻辑模式 v-model:logic
  logic: { type: String, default: 'AND' },
  // 核心数据源，用于搜索建议
  suggestionData: { type: Array, required: true, default: () => [] },
  // 建议生成Schema定义: { 'tags': 'list', 'name': 'string' }
  suggestionSchema: { type: Object, default: () => ({}) },
  // 是否为圆形按钮
  circle: { type: Boolean, default: false },
  // 主题色 (支持 '#3b82f6' 或 '--color-primary' 或 tailwind 颜色名如果配置了 resolve)
  listColor: { type: String, default: 'primary' }, 
  // 可选的手动缓存Key，如果数据巨大推荐传入版本号，避免计算Hash
  cacheKey: { type: [String, Number], default: '' }
})

const emit = defineEmits(['update:modelValue', 'update:logic', 'search'])

// --- 模块级全局缓存 (所有组件实例共享) ---
// 1. 引用缓存：基于数组内存地址
const referenceCache = new WeakMap()
// 2. 内容缓存：基于数据内容Hash
const contentHashCache = new Map()

// 简易且高效的 Hash 计算 (针对 JSON 结构)
const generateDataHash = (data) => {
  // 截取首尾和长度作为快速指纹，避免全量 JSON.stringify 带来的性能损耗
  if (!data || data.length === 0) return 'empty'
  const len = data.length
  const first = JSON.stringify(data[0])
  const last = JSON.stringify(data[len - 1])
  const mid = JSON.stringify(data[Math.floor(len / 2)])
  return `len:${len}_f:${first?.length}_m:${mid?.length}_l:${last?.length}_${len * 31}`
}

// --- 状态 ---
const inputValue = ref('')  // 当前输入框的值
const logicMode = ref(props.logic) // AND / OR
const isExpanded = ref(false) // 是否展开建议列表
const showSuggestions = ref(false)  // 是否显示建议列表
const highlightIndex = ref(0) // 当前高亮建议索引
const inputRef = ref(null)  // 输入框引用
const scrollContainer = ref(null) // 滚动容器
const suggestionRefs = ref([]); // 存储所有列表项的引用
const editingIndex = ref(-1)  // 当前正在编辑的标签索引

// 优化：使用 shallowRef 避免深层响应式代理带来的巨大性能开销
const keyMapping = shallowRef({}) 
const valueCache = shallowRef({}) 

// --- 核心优化：数据处理与缓存复用 ---
const processData = () => {
  // 1. 校验 suggestionSchema 是否为空
  if (!props.suggestionSchema || Object.keys(props.suggestionSchema).length === 0) {
    valueCache.value = {}
    return
  }
  const rawData = toRaw(props.suggestionData) // 获取原始数据，避免 Vue Proxy 干扰
  if (!rawData || !rawData.length) {
    valueCache.value = {}
    return
  }

  // 1. 尝试引用缓存 (最快)
  if (referenceCache.has(rawData)) {
    // console.log('Hit Reference Cache')
    valueCache.value = referenceCache.get(rawData)
    return
  }

  // 2. 尝试内容 Hash 缓存 (解决不同引用但相同数据的问题)
  // 如果 props 提供了 cacheKey 则直接用，否则计算 Hash
  const hash = props.cacheKey ? String(props.cacheKey) : generateDataHash(rawData)
  // 加上 suggestionSchema 的指纹，因为同样的 data 配合不同的 suggestionSchema 产生的索引不同
  const suggestionSchemaFingerprint = Object.keys(props.suggestionSchema).join(',')
  const uniqueCacheKey = `${hash}__${suggestionSchemaFingerprint}`

  if (contentHashCache.has(uniqueCacheKey)) {
    // console.log('Hit Content Hash Cache')
    const cachedResult = contentHashCache.get(uniqueCacheKey)
    // 同时写入引用缓存，方便下次快速读取
    referenceCache.set(rawData, cachedResult)
    valueCache.value = cachedResult
    return
  }

  // 3. 无缓存，生成新索引
  console.log('Generating New Index...')
  const cache = {}
  Object.keys(props.suggestionSchema).forEach(k => cache[k] = new Set())

  // 使用原始循环，性能优于 forEach
  for (let i = 0, len = rawData.length; i < len; i++) {
    const item = rawData[i]
    for (const key in props.suggestionSchema) {
      const val = item[key]
      if (val === null || val === undefined) continue
      
      if (Array.isArray(val)) {
        for (let j = 0; j < val.length; j++) {
          cache[key].add(val[j])
        }
      } else {
        cache[key].add(String(val))
      }
    }
  }

  // 存入全局缓存
  referenceCache.set(rawData, cache)
  contentHashCache.set(uniqueCacheKey, cache)
  valueCache.value = cache
}

// 生成 Key 映射 (同样只需要浅层响应)
const generateKeyMap = () => {
  if (!props.suggestionSchema || Object.keys(props.suggestionSchema).length === 0) {
    keyMapping.value = {}
    return
  }
  const map = {}
  const usedKeys = new Set()
  
  Object.keys(props.suggestionSchema).forEach(fullKey => {
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

// 监听
watch(() => props.suggestionData, processData, { immediate: true })
watch(() => props.suggestionSchema, () => {
  generateKeyMap()
  processData() // Schema 变了，索引也要重构
}, { immediate: true })


// --- 搜索逻辑 (保持不变，但适配 shallowRef) ---
// 动态计算建议列表
const suggestionList = computed(() => {
  const input = inputValue.value.trim()
  if (!input) {
    // 空输入：显示所有可用 Key
    return Object.entries(keyMapping.value)
      .filter(([short, full]) => short !== full) // 只显示简写，减少冗余
      .map(([short, full]) => ({
        type: 'key', label: short, prefix: '', value: short + ':',
        desc: `按属性搜索: ${full}`
      }))
  }

  // 情况 A: 用户正在输入 Key (没有冒号) -> 匹配 Key
  if (!input.includes(':')) {
    // 匹配 Key (不包含值部分)
    return Object.entries(keyMapping.value)
      .filter(([short]) => short.startsWith(input.replace(/^-/, ''))) // 忽略前面的 -
      .map(([short, full]) => ({
        type: 'key', label: short,
        prefix: input.startsWith('-') ? '-' : '',
        value: (input.startsWith('-') ? '-' : '') + short + ':',
        desc: `属性: ${full}`
      }))
  }

  // 情况 B: 用户输入了 Key:Value -> 匹配 Value
  const match = input.match(/^(-?)([^:]+):(.*)$/)
  if (match) {
    const [_, prefix, keyPart, valPart] = match
    const fullKey = keyMapping.value[keyPart]
    
    // 注意：valueCache 现在是 shallowRef，取 .value 即可，内部是 Set 原生对象
    if (fullKey && valueCache.value[fullKey]) {
      // 在对应字段的值中搜索
      const candidates = Array.from(valueCache.value[fullKey])
      const lowerVal = valPart.toLowerCase()
      
      // 性能优化：数量大时先 slice 再 map 还是先 filter？这里保持原样，
      // 但建议如果数据极大，应限制 filter 次数
      let count = 0
      const result = []
      for (const v of candidates) {
        if (v.toLowerCase().includes(lowerVal)) {
          result.push({
            type: 'value', label: v,
            prefix: prefix + keyPart + ':',
            value: prefix + keyPart + ':' + v + '$',
            desc: fullKey
          })
          count++
          if (count >= 50) break // 限制最大条数
        }
      }
      return result
    }
  }
  return []
})

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
        const fullKey = keyMapping.value[keyRaw] // 适配
      if (fullKey) {
        // 是有效的结构化搜索
        newTag = {
          id: Date.now() + Math.random(), // 唯一ID用于动画 key
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
      id: Date.now() + Math.random(),
      type: 'text',
      key: null,
      value: isExclude ? input.slice(1) : input,
      exclude: isExclude
    }
  }
  const isDuplicate = props.modelValue.some(tag => {
    // 比较 Key 和 Value (忽略排除符号 - 的差异，或者根据需求决定是否严格匹配)
    // 这里假设 key 和 value 相同即视为重复
    return tag.key === newTag.key && tag.value === newTag.value && tag.exclude === newTag.exclude
  })
  if (isDuplicate) {
    // 发现重复：清空输入，不添加，提示用户（可选：震动或闪烁现有的Tag）
    inputValue.value = ''
    showSuggestions.value = false
    // 这里可以加一个简单的动画逻辑让用户知道已存在，比如 console.warn
    console.warn('Duplicate tag detected')
    return 
  }
  // 发出更新
    const newTags = [...props.modelValue, newTag]
    emit('update:modelValue', newTags)
  // 清空输入
    inputValue.value = ''
    showSuggestions.value = false
  emit('search') // 触发父组件搜索
    nextTick(() => { if (scrollContainer.value) scrollContainer.value.scrollLeft = scrollContainer.value.scrollWidth })
}
// 删除 Tag
const removeTag = (index) => {
    const newTags = [...props.modelValue]
    newTags.splice(index, 1)
    emit('update:modelValue', newTags)
    emit('search')
  // 聚焦回到输入框
  nextTick(() => inputRef.value?.focus())
}
// 清空所有 Tag 以及输入框
const clearAll = () => {
    emit('update:modelValue', [])
    inputValue.value = ''
    emit('search')
}
// 切换逻辑运算符
const toggleLogic = () => {
    logicMode.value = logicMode.value === 'AND' ? 'OR' : 'AND'
    emit('update:logic', logicMode.value)
    emit('search')
}
// 提交编辑
const stopEditing = (index, val) => {
  if (editingIndex.value === -1) return
  // const val = tempEditingString.value.trim()
  // 1. 获取当前 Tag
  const currentTag = props.modelValue[index]
  // 2. 检查值是否变化
  if (val && val !== currentTag.value) {
    // 3. 检查修改后的值是否会导致重复 (可选，防止改成已有的值)
    const isDuplicate = props.modelValue.some((tag, i) => i !== index && tag.value === val && tag.key === currentTag.key)
    if (isDuplicate) {
        // 如果重复，还原或者提示
        // cancelEditing(index)
        editingIndex.value = -1 // 取消编辑
        return
    }

    // 4. 更新值，并更新 ID 以强制 DOM 重绘 (解决长文本滚动错位问题)
    const updatedTag = { 
      ...currentTag, 
      value: val,
      id: Date.now() + Math.random() // 关键：更新 Key
    }

    // 替换数组中的元素
    const newTags = [...props.modelValue]
    newTags[index] = updatedTag
    emit('update:modelValue', newTags)
    emit('search')
  } else if (!val) {
    // 也就是值被清空了，删除 tag
    removeTag(index)
  }
  editingIndex.value = -1
  // emit('search')
  // 聚焦回到输入框
  nextTick(() => inputRef.value?.focus())
}
// 取消编辑
const cancelEditing = (index) => {
    editingIndex.value = -1
    // tempEditingString.value = ''
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
    // 向下移动高亮建议
    e.preventDefault()
    if (highlightIndex.value < suggestionList.value.length - 1) highlightIndex.value++
  } else if (e.key === 'ArrowUp') {
    // 向上移动高亮建议
    e.preventDefault()
    if (highlightIndex.value > 0) highlightIndex.value--
  }
}
// 采纳建议
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
// 失去焦点时关闭建议框
const handleBlur = () => {
  // 延迟关闭，以便点击事件能先触发
  setTimeout(() => {
    showSuggestions.value = false
  }, 200)
}
// 输入框值变化时触发建议
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
.animate-fade-out {
  animation: fadeOut 0.2s ease-in;
}
@keyframes fadeOut {
  from { opacity: 1; transform: scale(1); }
  to { opacity: 0; transform: scale(0.9); }
}

.custom-scrollbar {
  overflow-x: auto;
  /* 核心：预留空间防止跳动 */
  scrollbar-gutter: stable; 
  overflow: overlay
}
/* 自定义滚动条 */
.custom-scrollbar::-webkit-scrollbar {
  width: 1px;
  height: 2px;
  scroll-behavior: smooth;
}
/* 2. Tag 列表动画 (TransitionGroup) */
.tag-list-move,
.tag-list-enter-active,
.tag-list-leave-active {
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.tag-list-enter-from,
.tag-list-leave-to {
  opacity: 0;
  transform: scale(0.8); /* 缩放消失 */
  width: 0 !important;   /* 宽度收缩 */
  padding: 0 !important;
  margin: 0 !important;
  border-width: 0 !important;
}

/* 确保删除时其他元素平滑移动，需要 absolute (但在 flex row 中 absolute 比较难处理，
   这里利用 width: 0 配合 flex 布局通常能达到不错的效果) 
   Flex 布局下 absolute 会导致重叠，建议不用，直接用 width 动画 */
/* .tag-list-leave-active {
  position: absolute;
} */

/* 下拉动画 */
.fade-drop-enter-active,
.fade-drop-leave-active {
  transition: all 0.2s ease;
}
.fade-drop-enter-from,
.fade-drop-leave-to {
  opacity: 0;
  transform: translateY(-5px);
}
</style>
