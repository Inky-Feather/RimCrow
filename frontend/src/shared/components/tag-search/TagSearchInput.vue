<template>
  <div class="relative flex items-center w-full gap-1" ref="containerRef">
    <!-- 左侧附加区：默认显示 AND/OR 逻辑切换，也允许业务方用 slot 覆盖 -->
    <div class="flex-none flex items-center justify-center">
      <slot name="left">
        <button v-if="showLogic" @click="toggleLogic"
          v-tooltip="logicMode === 'AND'
            ? '当前为^^与^^逻辑，检索满足^^所有^^条件的项\n[[(点击切换为^^或^^逻辑)]]'
            : '当前为^^或^^逻辑，检索满足^^任意^^条件的项\n[[(点击切换为^^与^^逻辑)]]'"
          class="shrink-0 size-7 font-bold cursor-pointer border transition-all relative"
          :class="[circle ? 'rounded-full' : 'rounded-md', logicMode === 'AND' ? 'bg-accent-primary/20 text-accent-primary border-accent-primary/30' : 'bg-accent-warning/20 text-accent-warning border-accent-warning/30']">
          <div class="absolute inset-0 flex items-center justify-center transition-all duration-500 ease transform-gpu" style="transform-style: preserve-3d;">
            <svg class="backface-hidden absolute transition-all duration-300 size-4" :class="logicMode === 'AND' ? 'rotate-x-0 opacity-100' : 'rotate-x-180 opacity-0'"
              xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="m8 6 4-4 4 4"/><path d="M12 2v10.3a4 4 0 0 1-1.172 2.872L4 22"/><path d="m20 22-5-5"/>
            </svg>
            <svg class="backface-hidden absolute transition-all duration-300 size-4" :class="logicMode === 'OR' ? 'rotate-x-0 opacity-100' : 'rotate-x-180 opacity-0'"
              xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M16 3h5v5"/><path d="M8 3H3v5"/><path d="M12 22v-8.3a4 4 0 0 0-1.172-2.872L3 3"/><path d="m15 9 6-6"/>
            </svg>
          </div>
        </button>
      </slot>
    </div>

    <!-- 主输入区：横向容纳已确认 token、当前输入框、建议列表和展开面板 -->
    <div class="relative flex-1 z-50 min-w-0 w-6 outline-none">
      <!-- 主输入容器。Tab 在这里用于采纳建议，所以阻止默认切换焦点。 -->
      <div @keydown.tab.prevent class="input-glass flex w-full items-center gap-1 px-1 pt-0.5 text-text-main outline-none"
        :class="`hover:border-accent-${listColor} focus:border-accent-${listColor} focus-within:border-accent-${listColor}`">
        <slot name="icon">
          <svg class="w-3 h-3 text-text-dim" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
        </slot>

        <div class="h-6 flex-1 flex overflow-x-scroll custom-scrollbar outline-none"
            v-drag-scroll="{ step: 20, wheelToHorizontal: true }"
            ref="scrollContainer" v-tooltip="inputTooltipText">
          <!-- 收起状态下直接在输入框左侧展示已确认条件，方便连续输入。 -->
          <TransitionGroup v-if="!isExpanded" name="tag-list">
            <TagToken v-for="(tag, index) in modelValue" :key="tag.id || index" :tag="tag"
              :is-editing="editingIndex === index"
              @remove="removeTag(index)" @edit-start="editingIndex = index"
              @edit-cancel="cancelEditing" @update-value="(val) => stopEditing(index, val)" />
          </TransitionGroup>

          <input ref="inputRef" v-model="inputValue" type="text"
            class="w-full flex-1 min-w-20 truncate bg-transparent border-none outline-none text-xs text-text-main placeholder:text-text-disabled py-0.5"
            :placeholder="placeholderText"
            @focus="showSuggestions = true"
            @keydown="handleKeydown" @blur="handleBlur"
            @input="handleInput" @keyup.esc="handleBlur" />
        </div>

        <!-- 右侧控制区：清空当前条件，或展开完整 token 面板。 -->
        <div class="flex items-center gap-0.5 shrink-0">
          <button v-show="modelValue.length > 0 || inputValue" @click="clearAll" class="p-1 text-text-dim hover:text-accent-danger transition-colors" v-tooltip="'清除全部'">
            <svg class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="3" d="M6 18L18 6M6 6l12 12"/>
            </svg>
          </button>
          <button @click="isExpanded = !isExpanded" v-tooltip="'展开已输入的搜索条件'" class="p-1 text-text-dim hover:text-text-main transition-transform" :class="isExpanded ? 'rotate-180' : ''">
            <svg class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/>
            </svg>
          </button>
        </div>
      </div>

      <!-- 自动补全菜单：key 建议继续输入 value，value 建议直接生成 token。 -->
      <Transition name="fade-drop">
        <div v-if="showSuggestions && suggestionList.length > 0" ref="suggestionContainer"
          class="popover-surface absolute top-full z-100 mt-1 max-h-60 w-full overflow-y-auto overflow-x-hidden rounded-lg shadow-[0_18px_50px_var(--shadow-color)]">
          <div v-for="(item, index) in suggestionList" :key="index"
            class="pl-1 pr-3 py-1.5 text-xs cursor-pointer flex items-center justify-between group transition-colors"
            :class="[highlightIndex === index ? 'bg-accent-primary/20 text-text-main' : 'text-text-dim hover:bg-bg-overlay/5']"
            @mousedown.prevent="applySuggestion(item)"
            @mouseover="highlightIndex = index" v-tooltip="tagTooltip(item)">
            <div class="flex items-center gap-1 min-w-0">
              <span class="text-xs w-8 h-4 flex items-center justify-center rounded bg-bg-overlay/5 font-mono"
                :class="item.type === 'key' ? 'text-accent-primary' : 'text-accent-success'">
                {{ item.type === 'key' ? 'KEY' : 'VAL' }}
              </span>
              <span class="font-mono min-w-0 truncate">
                <span class="text-accent-secondary">{{ item.value.split(':')[0] + ':' }}</span>
                <span :class="highlightIndex === index ? 'text-text-main' : 'text-text-soft'"
                  :style="{ color: item.color || 'currentColor', fontWeight: item.color ? 'bold' : 'normal' }">
                  {{ item.type === 'value' ? item.label : '' }}
                </span>
              </span>
            </div>
            <span v-if="item.desc && item.type !== 'value'" class="shrink-0 text-xs opacity-40">{{ item.desc }}</span>
          </div>
        </div>
      </Transition>

      <!-- 展开面板：token 较多时避免横向滚动区域过窄。 -->
      <TransitionGroup tag="div" v-if="isExpanded" name="tag-list"
        class="absolute flex flex-wrap p-1.5 gap-1 left-0 right-0 top-full mt-1 transition-all duration-200 overflow-y-auto overflow-x-hidden bg-bg-deep/70 border border-border-base/10 backdrop-blur-md rounded-lg shadow-2xl z-99">
        <TagToken v-for="(tag, index) in modelValue" :key="tag.id || index" :tag="tag"
          :is-editing="editingIndex === index"
          @remove="removeTag(index)" @edit-start="editingIndex = index"
          @edit-cancel="cancelEditing" @update-value="(val) => stopEditing(index, val)" />
      </TransitionGroup>
    </div>

    <div class="flex-none">
      <slot name="right"></slot>
    </div>
    <!-- 搜索说明：默认使用 controller 生成的字段说明，传空字符串时不显示。 -->
    <label v-if="searchTooltipText" v-tooltip="{content: searchTooltipText, html:true}" class="absolute -top-1.5 -right-2.5 size-4 rounded-md text-sm text-center text-text-dim hover:text-text-main cursor-help">?</label>
  </div>
</template>

<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import vDragScroll from '../../directives/dragScroll.js'
import TagToken from './TagToken.vue'
import { DEFAULT_TAG_SEARCH_INPUT_HELP_TEXT } from './tagSearchEngine'

const props = defineProps({
  // v-model 绑定解析后的 token 数组，格式由 controller.parse 统一生成。
  modelValue: { type: Array, default: () => [] },
  placeholder: { type: String, default: '' },
  // v-model:logic 传出 AND/OR，用于外部决定多条件关系。
  logic: { type: String, default: 'AND' },
  // 输入控制器只负责解析、建议和提示文本，实际搜索由外部流程决定。
  controller: { type: Object, default: null },
  circle: { type: Boolean, default: false },
  showLogic: { type: Boolean, default: true },
  listColor: { type: String, default: 'primary' },
  // undefined 使用 controller 默认搜索说明；传入空字符串表示关闭右上角帮助入口。
  searchHelpText: { type: String, default: undefined },
  // undefined 使用 controller 默认输入提示；传入空字符串表示关闭输入区提示。
  inputHelpText: { type: String, default: undefined },
})

const emit = defineEmits(['update:modelValue', 'update:logic', 'search'])

// --- 输入状态 ---
const inputValue = ref('')
const logicMode = ref(props.logic)
const isExpanded = ref(false)
const showSuggestions = ref(false)
const highlightIndex = ref(0)
const inputRef = ref(null)
const scrollContainer = ref(null)
const editingIndex = ref(-1)
const searchController = computed(() => props.controller || null)

watch(() => props.logic, (value) => {
  if (value && value !== logicMode.value) logicMode.value = value
})

// 没有传入 engine 时仍能作为普通关键词输入框使用。
const fallbackParse = (input) => {
  const trimmed = String(input || '').trim()
  if (!trimmed) return null
  const isExclude = trimmed.startsWith('-')
  return { type: 'text', key: null, value: isExclude ? trimmed.slice(1) : trimmed, displayValue: isExclude ? trimmed.slice(1) : trimmed, exclude: isExclude }
}

const parseInput = (input) => searchController.value?.parse?.(input) || fallbackParse(input)
const isFullRuleInput = (value) => /^-?[^:]+:/.test(String(value || '').trim())

const isSameTag = (left, right) => (
  left.type === right.type && left.key === right.key && left.value === right.value && left.exclude === right.exclude
)

const suggestionList = computed(() => searchController.value?.getSuggestions?.(inputValue.value) || [])

// 提交当前输入为 token。重复条件直接忽略，避免 UI 里出现多个等价过滤条件。
const addTag = (rawInput) => {
  if (!rawInput && inputValue.value) rawInput = inputValue.value
  const input = String(rawInput || '').trim()
  if (!input) return

  const newTag = parseInput(input)
  if (!newTag) return
  newTag.id = Date.now() + Math.random()

  const isDuplicate = props.modelValue.some(tag => isSameTag(tag, newTag))
  if (isDuplicate) {
    inputValue.value = ''
    showSuggestions.value = false
    return
  }

  emit('update:modelValue', [...props.modelValue, newTag])
  inputValue.value = ''
  showSuggestions.value = false
  nextTick(() => {
    if (scrollContainer.value) scrollContainer.value.scrollLeft = scrollContainer.value.scrollWidth
  })
}

// 应用建议：字段建议只补上 key:，值建议直接生成完整 token。
const applySuggestion = (item) => {
  if (item.type === 'key') {
    inputValue.value = item.value
    inputRef.value?.focus()
    highlightIndex.value = 0
    return
  }
  addTag(item.value)
}

// 删除 token 后把焦点还给输入框，保持连续编辑体验。
const removeTag = (index) => {
  const newTags = [...props.modelValue]
  newTags.splice(index, 1)
  emit('update:modelValue', newTags)
  nextTick(() => inputRef.value?.focus())
}

// 清空条件属于显式搜索动作，需要通知外部刷新结果。
const clearAll = () => {
  emit('update:modelValue', [])
  inputValue.value = ''
  emit('search')
}

// 切换 AND/OR 后立刻触发外部搜索，避免按钮状态和结果列表不一致。
const toggleLogic = () => {
  logicMode.value = logicMode.value === 'AND' ? 'OR' : 'AND'
  emit('update:logic', logicMode.value)
  emit('search')
}

// 编辑已有 token：普通输入只改当前字段值；输入完整 key:value 时重新解析成新规则。
const stopEditing = (index, val) => {
  if (editingIndex.value === -1) return
  const trimmedValue = String(val || '').trim()
  if (!trimmedValue) {
    removeTag(index)
  } else if (trimmedValue !== String(props.modelValue[index].displayValue ?? props.modelValue[index].value ?? '')) {
    const currentTag = props.modelValue[index]
    const displayKey = currentTag.originalKey || currentTag.displayKey || currentTag.key
    // 普通编辑只改当前字段的值；输入完整 key:value 时才按新规则重新解析。
    const rawInput = currentTag.type === 'rule' && displayKey && !isFullRuleInput(trimmedValue)
      ? `${currentTag.exclude ? '-' : ''}${displayKey}:${trimmedValue}`
      : trimmedValue
    const parsedTag = parseInput(rawInput)
    if (!parsedTag) {
      editingIndex.value = -1
      return
    }
    parsedTag.id = Date.now() + Math.random()

    const isDuplicate = props.modelValue.some((tag, tagIndex) => tagIndex !== index && isSameTag(tag, parsedTag))
    if (isDuplicate) {
      editingIndex.value = -1
      nextTick(() => inputRef.value?.focus())
      return
    }

    const newTags = [...props.modelValue]
    newTags[index] = parsedTag
    emit('update:modelValue', newTags)
    emit('search')
  }
  editingIndex.value = -1
  nextTick(() => inputRef.value?.focus())
}

const cancelEditing = () => {
  editingIndex.value = -1
}

// 键盘：Enter 提交，Tab 应用建议，空输入 Backspace 删除最后一个 token。
const handleKeydown = (event) => {
  if (event.key === 'Enter') {
    if (inputValue.value) addTag(inputValue.value)
    emit('search')
  } else if (event.key === 'Tab' && showSuggestions.value && suggestionList.value.length > 0) {
    event.preventDefault()
    applySuggestion(suggestionList.value[highlightIndex.value])
  } else if (event.key === 'Backspace' && !inputValue.value && props.modelValue.length) {
    removeTag(props.modelValue.length - 1)
  } else if (event.key === 'ArrowDown') {
    event.preventDefault()
    if (highlightIndex.value < suggestionList.value.length - 1) highlightIndex.value++
  } else if (event.key === 'ArrowUp') {
    event.preventDefault()
    if (highlightIndex.value > 0) highlightIndex.value--
  }
}

const handleBlur = () => {
  // 延迟关闭，保证鼠标点击建议项时 mousedown 能先触发。
  setTimeout(() => {
    showSuggestions.value = false
  }, 200)
}

const handleInput = () => {
  showSuggestions.value = true
  highlightIndex.value = 0
}

const placeholderText = computed(() => {
  if (props.modelValue.length > 0) return '添加条件...'
  return props.placeholder || '输入关键词或条件'
})

const inputTooltipText = computed(() => {
  if (props.inputHelpText !== undefined) return props.inputHelpText
  return searchController.value?.inputHelpText ?? DEFAULT_TAG_SEARCH_INPUT_HELP_TEXT
})
const searchTooltipText = computed(() => {
  if (props.searchHelpText !== undefined) return props.searchHelpText
  return searchController.value?.searchHelpText ?? searchController.value?.getSearchHelpText?.() ?? ''
})

const tagTooltip = (item) => {
  if (item.type !== 'key') return ''
  return `**${item.desc}**\n原始格式：${item.meta?.fullKey || ''}\n其它格式：${item.meta?.aliases || ''}\n使用示例：${item.meta?.usage || ''}`
}

defineExpose({ addTag })
</script>

<style scoped>
.custom-scrollbar {
  overflow-x: auto;
  scrollbar-gutter: stable;
  overflow: overlay;
}
.custom-scrollbar::-webkit-scrollbar {
  width: 1px;
  height: 2px;
  scroll-behavior: smooth;
}
.tag-list-move,
.tag-list-enter-active,
.tag-list-leave-active {
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}
.tag-list-enter-from,
.tag-list-leave-to {
  opacity: 0;
  transform: scale(0.8);
  width: 0 !important;
  padding: 0 !important;
  margin: 0 !important;
  border-width: 0 !important;
}
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
