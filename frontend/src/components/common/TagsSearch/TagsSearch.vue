<template>
  <div class="flex items-center w-full gap-1" ref="containerRef" >
     <!-- 左侧附加区 -->
    <div class="flex-none flex items-center justify-center">
      <slot name="left">
        <!-- 逻辑切换开关 (AND/OR) -->
        <button @click="toggleLogic" 
          v-tooltip="logicMode === 'AND' ? 
            '当前为^^‘与’^^逻辑，检索满足^^所有^^条件的项\n[[(点击切换为^^‘或’^^逻辑)]]' : 
            '当前为^^‘或’^^逻辑，检索满足^^任意^^条件的项\n[[(点击切换为^^‘与’^^逻辑)]]'"
          class="shrink-0 size-7 font-bold cursor-pointer border transition-all relative"
          :class="[ props.circle ? 'rounded-full' : 'rounded-md',
            logicMode === 'AND' ? 'bg-accent-primary/20 text-accent-primary border-accent-primary/30' : 'bg-accent-warning/20 text-accent-warning border-accent-warning/30',]">
          <!-- 圆形按钮旋转动画 -->
          <div v-if="circle" class="absolute inset-0 flex items-center justify-center ">
            <svg class="transition-all duration-400 ease-in-out size-4"
                :class="{'opacity-100 rotate-0': logicMode === 'AND', 'opacity-0 rotate-180': logicMode === 'OR'}" 
                xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m8 6 4-4 4 4"/><path d="M12 2v10.3a4 4 0 0 1-1.172 2.872L4 22"/><path d="m20 22-5-5"/></svg>
            <svg class="transition-all duration-400 ease-in-out absolute size-4"
                :class="{ 'opacity-0 -rotate-180': logicMode === 'AND', 'opacity-100 rotate-0': logicMode === 'OR' }" 
                xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M16 3h5v5"/><path d="M8 3H3v5"/><path d="M12 22v-8.3a4 4 0 0 0-1.172-2.872L3 3"/><path d="m15 9 6-6"/></svg>
          </div>
          <!-- 方形按钮翻转动画 -->
          <div v-else class="absolute inset-0 flex items-center justify-center transition-all duration-500 ease transform-gpu" style="transform-style: preserve-3d;">
            <svg class="backface-hidden absolute transition-all duration-300 size-4" :class="logicMode === 'AND' ? 'rotate-x-0 opacity-100' : 'rotate-x-180 opacity-0'"
                xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m8 6 4-4 4 4"/><path d="M12 2v10.3a4 4 0 0 1-1.172 2.872L4 22"/><path d="m20 22-5-5"/></svg>
            <svg class="backface-hidden absolute transition-all duration-300 size-4" :class="logicMode === 'OR' ? 'rotate-x-0 opacity-100' : 'rotate-x-180 opacity-0'"
                xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M16 3h5v5"/><path d="M8 3H3v5"/><path d="M12 22v-8.3a4 4 0 0 0-1.172-2.872L3 3"/><path d="m15 9 6-6"/></svg>
          </div>
          
        </button>
      </slot>
    </div>

    <!-- 主要区域 -->
    <div class="relative flex-1 z-50 min-w-0 w-6 outline-none">
      <!-- 主输入容器（@keydown.tab.prevent禁止切换焦点功能） -->
      <div @keydown.tab.prevent class="input-glass flex w-full items-center gap-1 px-1 pt-0.5 text-text-main outline-none"
        :class="`hover:border-accent-${listColor} focus:border-accent-${listColor} focus-within:border-accent-${listColor}`">
        <!-- 图标 -->
        <slot name="icon">
          <svg class="w-3 h-3 text-text-dim" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" /></svg>
        </slot>
        <!-- 输入区域 + Tags -->
        <div class=" h-6 flex-1 flex overflow-x-scroll custom-scrollbar outline-none" 
            v-drag-scroll="{step: 20, wheelToHorizontal: true}" 
            ref="scrollContainer" v-tooltip="tooltipText">
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
            class="w-full flex-1 min-w-20 truncate bg-transparent border-none outline-none text-xs text-text-main placeholder:text-text-disabled py-0.5"
            :placeholder="placeholderText"
            @focus="showSuggestions = true"
            @keydown="handleKeydown" @blur="handleBlur"
            @input="handleInput" @keyup.esc="handleBlur"
          />
        </div>

        <!-- 右侧控制区 -->
        <div class="flex items-center gap-0.5 shrink-0">
          <!-- 清除按钮 -->
          <button v-show="modelValue.length > 0 || inputValue" @click="clearAll" class="p-1 text-text-dim hover:text-accent-danger transition-colors" v-tooltip="`清除全部`">
            <svg class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="3" d="M6 18L18 6M6 6l12 12"/></svg>
          </button>
          <!-- 展开/收起按钮 -->
          <button @click="isExpanded = !isExpanded" v-tooltip="'可展开输入的关键词标签'" class="p-1 text-text-dim hover:text-text-main transition-transform" :class="isExpanded ? 'rotate-180' : ''">
            <svg class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/></svg>
          </button>
        </div>
      </div>

      <!-- 自动补全下拉菜单 -->
      <Transition name="fade-drop">
        <div v-if="showSuggestions && suggestionList.length > 0" ref="suggestionContainer"
          class="popover-surface absolute top-full z-100 mt-1 max-h-60 w-full overflow-y-auto overflow-x-hidden rounded-lg"
        >
          <div v-for="(item, index) in suggestionList" :key="index"
            class="pl-1 pr-3 py-1.5 text-xs cursor-pointer flex items-center justify-between group transition-colors"
            :class="[highlightIndex === index ? 'bg-accent-primary/20 text-text-main' : 'text-text-dim hover:bg-bg-overlay/5']"
            @mousedown.prevent="applySuggestion(item)"
            @mouseover="highlightIndex = index" v-tooltip="tagTooltip(item)"
          >
            <div class="flex items-center gap-1">
              <!-- 图标/类型指示 -->
              <span class="text-xs w-8 h-4 flex items-center justify-center rounded bg-bg-overlay/5 font-mono"
                 :class="item.type === 'key' ? 'text-[rgb(var(--accent-rgb))]' : 'text-accent-success'">
                {{ item.type === 'key' ? 'KEY' : 'VAL' }}
              </span>
              <!-- 内容 -->
              <span class="font-mono ">
                <!-- item.value 包含了完整输入建议，展示 label -->
                <span class="text-accent-secondary">
                  {{ item.value.split(':')[0] + ':' }}
                  <!-- <span v-if="item.meta.matchInfo" class="text-[0.65rem] ml-auto text-accent-warn">
                      ({{ item.meta.matchInfo }})
                  </span> -->
                </span>
                <span :class="highlightIndex === index ? 'text-text-main' : 'text-text-soft'"
                  :style="{'color': item.color || 'currentColor', 'font-weight': item.color ? 'bold' : 'normal'}">
                  {{ item.type === 'value' ? item.label : '' }}
                </span>
              </span>
            </div>
            <!-- 说明 -->
            <span v-if="item.desc && item.type !== 'value'" class="shrink-0 text-xs opacity-40">{{ item.desc }}</span>
          </div>
        </div>
      </Transition>
        
      <!-- 标签面板 -->
      <TransitionGroup tag="div" v-if="isExpanded" name="tag-list"
        class="absolute flex flex-wrap p-1.5 gap-1 left-0 right-0 top-full mt-1 ransition-all duration-200 
        overflow-y-auto overflow-x-hidden bg-bg-deep/70 border border-border-base/10 backdrop-blur-md rounded-lg shadow-2xl z-99"
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
import vDragScroll from '../../../directives/dragScroll.js' //直接引入即可自动注册（注意命名需以 v 开头）用于标签面板的拖动滚动
import { useSearchStore } from '../../../stores/searchStore' // [新增]
import Tag from './Tag.vue'
const props = defineProps({
  // v-model 绑定的 Tags 数组，即输出结果，格式[{key:'',value:'',exclude:false}]
  modelValue: { type: Array, default: () => [] },
  placeholder: { type: String, default: '' },
  // 传出外部的逻辑模式 v-model:logic
  logic: { type: String, default: 'AND' },
  // 是否为圆形按钮
  circle: { type: Boolean, default: false },
  // 主题色 (支持 '#3b82f6' 或 '--color-primary' 或 tailwind 颜色名如果配置了 resolve)
  listColor: { type: String, default: 'primary' }, 
})

const emit = defineEmits(['update:modelValue', 'update:logic', 'search'])

// === Store 连接 ===
const searchStore = useSearchStore()
const engine = computed(() => searchStore.engine) // 获取全局唯一的 Engine 实例

// --- 状态 ---
const inputValue = ref('')  // 当前输入框的值
const logicMode = ref(props.logic) // AND / OR
const isExpanded = ref(false) // 是否展开建议列表
const showSuggestions = ref(false)  // 是否显示建议列表
const highlightIndex = ref(0) // 当前高亮建议索引
const inputRef = ref(null)  // 输入框引用
const scrollContainer = ref(null) // 滚动容器
const editingIndex = ref(-1)  // 当前正在编辑的标签索引



// --- 搜索逻辑 ---
// 动态计算建议列表
const suggestionList = computed(() => {
  // 如果引擎还没初始化好，或者没有输入，返回空（或者想默认显示 keys，取决于 Engine 实现）
  if (!engine.value) return []
  return engine.value.getSuggestions(inputValue.value)
})

// 提交 Tag
const addTag = (rawInput) => {
  if(!rawInput && inputValue.value) rawInput = inputValue.value
  if(!rawInput) return
  const input = rawInput.trim()
  if (!input) return
  
  if (!engine.value) {
    console.warn('Search Engine not ready')
    return
  }

  // 1. 使用 Engine 的解析器
  const newTag = engine.value.parser.parse(input)
  
  if (newTag) {
    // 补充 ID 用于 UI 动画
    newTag.id = Date.now() + Math.random()

    // 2. 查重 (Engine 无法决定 UI 是否允许重复，这里做简单判断)
    const isDuplicate = props.modelValue.some(tag => 
      // 比较 Key 和 Value (忽略排除符号 - 的差异，或者根据需求决定是否严格匹配)
      // 这里假设 key 和 value 相同即视为重复
      tag.key === newTag.key && tag.value === newTag.value && tag.exclude === newTag.exclude
    )
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
    //emit('search') // 触发搜索
    nextTick(() => { 
      if (scrollContainer.value) scrollContainer.value.scrollLeft = scrollContainer.value.scrollWidth 
    })
  }
}
// === 核心逻辑：应用建议 ===
const applySuggestion = (item) => {
  // item 是 Engine.getSuggestions 返回的对象: { type, value, label... }
  if (item.type === 'key') {
    // 选中了 Key，填入输入框继续输入 Value
    inputValue.value = item.value 
    inputRef.value.focus()
    highlightIndex.value = 0
  } else {
    // 选中了 Value，直接生成 Tag
    // item.value 已经是完整的 "key:val" 格式
    addTag(item.value)
  }
}
// 删除 Tag
const removeTag = (index) => {
    const newTags = [...props.modelValue]
    newTags.splice(index, 1)
    emit('update:modelValue', newTags)
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
  if (!val) {
    removeTag(index)
  } else if (val !== props.modelValue[index].value) {
    // 尝试重新解析，因为用户可能把 value 改成了 key:value 格式，或者改了值
    // 这里为了简单，假设用户只改值，保留 key。
    // 如果想要强大的编辑，可以用 parser 重新解析 val，看是否生成新的结构
    
    // 简单版：只更新 displayValue 和 value
    const currentTag = props.modelValue[index]
  // 2. 检查值是否变化
  /*if (val && val !== currentTag.value) {
    // 3. 检查修改后的值是否会导致重复 (可选，防止改成已有的值)
    const isDuplicate = props.modelValue.some((tag, i) => i !== index && tag.value === val && tag.key === currentTag.key)
    if (isDuplicate) {
        // 如果重复，还原或者提示
        // cancelEditing(index)
        editingIndex.value = -1 // 取消编辑
        return
    }*/

    // 4. 更新值，并更新 ID 以强制 DOM 重绘 (解决长文本滚动错位问题)
    const newTag = { ...currentTag, value: val, displayValue: val, id: Date.now() }
    

    // 替换数组中的元素
    const newTags = [...props.modelValue]
    newTags[index] = newTag
    emit('update:modelValue', newTags)
    emit('search')
  }
  editingIndex.value = -1
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
  if (e.key === 'Enter') {
    // 直接提交输入
    if(inputValue.value) addTag(inputValue.value)
    else emit('search')
  } else if (e.key === 'Tab' && showSuggestions.value && suggestionList.value.length > 0) {
    // 优先采纳建议（如果有高亮）
    e.preventDefault() // 阻止 Tab 切换焦点
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
    if (props.modelValue.length > 0) return '添加关键词...'
    if (props.placeholder) return props.placeholder
    const examples = ''
    return `输入关键词 或 ${examples}`
})
// 提示文本
const tooltipText = computed(() => {
    const examples =''
    return `在此输入关键词并[[回车]]确认\n可直接输入关键词 或 格式标签 ${examples}\n[[(使用Tab键应用输入建议)]]`
})

// 标签提示
const tagTooltip = (item) => {
  if(item.type!=='key') return ''
  return `**${item.desc}**\n原始格式：${item.meta.fullKey}\n其它格式：${item.meta.aliases}\n使用示例：${item.meta.usage}`
}

  defineExpose({
		addTag
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
