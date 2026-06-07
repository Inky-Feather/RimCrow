<template>
  <section class="animate-in fade-in slide-in-from-right-4">
    <div class="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h3 class="text-lg font-bold text-text-main">快捷键</h3>
        <p class="mt-1 text-xs leading-5 text-text-dim">
          管理全局命令的键盘入口；分区命令和插件命令会继续复用这里的规则。
        </p>
      </div>
      <button class="rounded-lg border border-accent-warn/20 bg-accent-warn/10 px-3 py-1.5 text-xs font-bold text-accent-warn transition-colors hover:bg-accent-warn/18"
        @click="resetAllKeybindings" >
        恢复全部默认
      </button>
    </div>

    <div class="mb-4 grid grid-cols-[minmax(0,1fr)_180px] gap-3">
      <div class="relative">
        <Search class="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-text-disabled" />
        <input v-model="searchQuery" placeholder="搜索命令名称、ID 或分类" class="input-glass h-10 w-full pl-9 pr-3 text-sm text-text-main outline-none" >
      </div>
      <CommonSelect v-model="selectedCategory" :options="categoryOptions" mini />
    </div>

    <div v-if="conflicts.length" class="mb-4 rounded-md border border-accent-warn/20 bg-accent-warn/8 px-4 py-3 text-xs leading-5 text-accent-warn" >
      <div class="mb-1 flex items-center gap-2 font-bold text-text-main">
        <AlertTriangle class="size-4 text-accent-warn" />
        发现 {{ conflicts.length }} 处快捷键复用
      </div>
      <div class="text-text-dim">
        严重冲突会影响触发结果；跨区域复用允许保留，运行时会按浮层、当前区域、最近区域、全局的顺序执行。
      </div>
    </div>

    <div class="overflow-hidden rounded-md border border-border-base/10 bg-bg-muted/35">
      <div class="grid grid-cols-[minmax(0,1.3fr)_minmax(220px,0.9fr)_120px] border-b border-border-base/10 bg-bg-surface/70 px-4 py-2 text-[11px] font-black uppercase tracking-wider text-text-disabled">
        <div>命令</div>
        <div>快捷键</div>
        <div class="text-right">操作</div>
      </div>

      <div v-if="filteredRows.length === 0" class="px-4 py-10 text-center text-sm text-text-dim">
        没有匹配的命令
      </div>

      <div v-for="row in filteredRows" :key="row.command.id" :ref="el => { if (el) rowRefs[row.command.id] = el }" class="grid grid-cols-[minmax(0,1.3fr)_minmax(220px,0.9fr)_120px] items-center gap-3 border-b border-border-base/5 px-4 py-3 last:border-b-0" >
        <div class="min-w-0">
          <div class="flex flex-wrap items-center gap-2">
            <span class="truncate text-sm font-bold text-text-main">{{ row.command.title }}</span>
            <span class="rounded border border-border-base/10 bg-bg-overlay/5 px-1.5 py-0.5 text-[10px] text-text-dim">{{ row.command.category }}</span>
            <span class="rounded border border-border-base/10 bg-bg-overlay/5 px-1.5 py-0.5 text-[10px] text-text-dim">{{ scopeLabel(row.command.scope) }}</span>
            <span v-if="row.command.source !== 'builtin'" class="rounded border border-accent-cool/20 bg-accent-cool/10 px-1.5 py-0.5 text-[10px] text-accent-cool">
              插件
            </span>
            <span v-if="row.command.dangerLevel !== 'normal'" class="rounded border border-accent-warn/20 bg-accent-warn/10 px-1.5 py-0.5 text-[10px] text-accent-warn">
              需谨慎
            </span>
          </div>
          <div class="mt-1 truncate font-mono text-[11px] text-text-disabled">{{ row.command.id }}</div>
          <div v-if="row.command.description" class="mt-1 line-clamp-2 text-xs leading-5 text-text-dim">{{ row.command.description }}</div>
          <div v-if="row.conflicts.length" class="mt-2 flex flex-wrap gap-1.5">
            <span v-for="conflict in row.conflicts"
              :key="`${row.command.id}:${conflict.keybinding}:${conflict.commandIds.join('-')}`"
              class="cursor-pointer rounded px-1.5 py-0.5 text-[10px] font-bold transition-transform hover:scale-105"
              :class="conflictClass(conflict.level)"
              v-tooltip="conflictTooltip(conflict)"
              @click="jumpToConflictTarget(row.command.id, conflict)" >
              [{{ formatKeybindingLabel(conflict.keybinding) }}] 冲突
            </span>
          </div>
        </div>

        <div class="min-w-0">
          <div class="flex flex-wrap gap-1.5">
            <span  v-for="keybinding in row.keys" :key="`${row.command.id}:${keybinding}`"
              class="inline-flex items-center gap-1 rounded-md border border-border-base/10 bg-bg-inset px-2 py-1 font-mono text-xs text-text-main" >
              {{ formatKeybindingLabel(keybinding) }}
              <LockKeyhole v-if="isLockedKeybinding(row.command, keybinding)" class="size-3 text-text-disabled" />
              <button v-else-if="!row.command.keybindingReadonly" class="text-text-disabled transition-colors hover:text-accent-danger"
                @click="removeKeybinding(row.command, keybinding)" >
                ×
              </button>
            </span>
            <span v-if="row.keys.length === 0" class="text-xs text-text-disabled">未绑定</span>
          </div>
          <div v-if="row.command.keybindingReadonly" class="mt-2 text-xs text-text-dim">
            固定操作，仅用于说明和冲突提示。
          </div>
          <div v-else class="mt-2 flex flex-wrap items-center gap-1.5">
            <button v-for="modifier in modifierOptions" :key="`${row.command.id}:${modifier.value}`" class="rounded border px-1.5 py-0.5 text-[10px] font-bold transition-colors"
              :class="isDraftModifierActive(row.command.id, modifier.value) ? 'border-accent-primary/40 bg-accent-primary/15 text-accent-primary' : 'border-border-base/10 bg-bg-overlay/5 text-text-dim hover:text-text-main'"
              @click="toggleDraftModifier(row.command.id, modifier.value)" >
              {{ modifier.label }}
            </button>
            <span class="text-xs font-black text-text-disabled">+</span>
            <div class="min-w-34 flex-1">
              <CommonSelect :model-value="getDraftMainKey(row.command.id)" :options="mainKeyOptions" mini editable placeholder="选择主键或鼠标键"
                @update:model-value="setDraftMainKey(row.command.id, $event)"
              />
            </div>
            <button class="rounded-md border border-accent-primary/20 bg-accent-primary/10 px-2 py-1 text-xs font-bold text-accent-primary transition-colors hover:bg-accent-primary/18 disabled:cursor-not-allowed disabled:opacity-40"
              :disabled="!buildDraftKeybinding(row.command.id)"
              @click="addDraftKeybinding(row.command)" >
              添加
            </button>
          </div>
        </div>

        <div v-if="row.command.keybindingReadonly" class="flex justify-end">
          <span class="rounded-md border border-border-base/10 bg-bg-overlay/5 px-2 py-1 text-xs font-bold text-text-disabled">
            锁定
          </span>
        </div>
        <div v-else class="flex justify-end gap-2">
          <button class="rounded-md border border-border-base/10 bg-bg-overlay/5 px-2 py-1 text-xs font-bold text-text-dim transition-colors hover:text-text-main"
            @click="resetCommandKeybindings(row.command.id)" >
            默认
          </button>
          <button class="rounded-md border border-border-base/10 bg-bg-overlay/5 px-2 py-1 text-xs font-bold text-text-dim transition-colors hover:text-accent-danger"
            @click="clearCommandKeybindings(row.command.id)" >
            清空
          </button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed, nextTick, reactive, ref } from 'vue'
import { AlertTriangle, LockKeyhole, Search } from 'lucide-vue-next'
import { getAllCommands } from '../../../shared/commands/commandRegistry'
import { createDefaultKeybindingConfig, detectKeybindingConflicts, getCommandDisplayKeys, getCommandEffectiveKeys } from '../../../shared/commands/keybindingConflicts'
import { formatKeybindingLabel, normalizeKeybinding, normalizeKeybindingList } from '../../../shared/commands/keybindingParser'
import CommonSelect from '../../../shared/components/input/CommonSelect.vue'

const props = defineProps({
  formData: { type: Object, required: true },
})

const searchQuery = ref('')
const selectedCategory = ref('all')
const rowRefs = ref({})
const draftByCommand = reactive({})

const ensureKeybindingConfig = () => {
  // 设置面板直接编辑表单副本，这里把旧配置或异常配置补齐到当前版本，避免保存时丢字段。
  if (!props.formData.ui || typeof props.formData.ui !== 'object') {
    props.formData.ui = {}
  }
  if (!props.formData.ui.keybindings || typeof props.formData.ui.keybindings !== 'object') {
    props.formData.ui.keybindings = createDefaultKeybindingConfig()
  }
  if (!props.formData.ui.keybindings.bindings || typeof props.formData.ui.keybindings.bindings !== 'object') {
    props.formData.ui.keybindings.bindings = {}
  }
  if (!props.formData.ui.keybindings.disabledDefaults || typeof props.formData.ui.keybindings.disabledDefaults !== 'object') {
    props.formData.ui.keybindings.disabledDefaults = {}
  }
  props.formData.ui.keybindings.version = 1
  return props.formData.ui.keybindings
}

const keybindingConfig = computed(() => ensureKeybindingConfig())
const commands = computed(() => getAllCommands())
const categories = computed(() => [...new Set(commands.value.map(command => command.category))].sort((left, right) => left.localeCompare(right, 'zh-CN')))
const categoryOptions = computed(() => [
  { label: '全部分类', value: 'all' },
  ...categories.value.map(category => ({ label: category, value: category })),
])
const conflicts = computed(() => detectKeybindingConflicts(commands.value, keybindingConfig.value))

const modifierOptions = [
  { label: 'Ctrl', value: 'Ctrl' },
  { label: 'Alt', value: 'Alt' },
  { label: 'Shift', value: 'Shift' },
]

const mainKeyOptions = [
  { label: '无主键（仅修饰键）', value: '__modifier_only__' },
  ...'ABCDEFGHIJKLMNOPQRSTUVWXYZ'.split('').map(key => ({ label: key, value: key })),
  ...'0123456789'.split('').map(key => ({ label: key, value: key })),
  ...Array.from({ length: 12 }, (_, index) => ({ label: `F${index + 1}`, value: `F${index + 1}` })),
  { label: 'Enter', value: 'Enter' },
  { label: '空格', value: 'Space' },
  { label: 'Tab', value: 'Tab' },
  { label: 'ESC', value: 'Escape' },
  { label: 'Backspace', value: 'Backspace' },
  { label: 'Delete', value: 'Delete' },
  { label: '↑', value: 'ArrowUp' },
  { label: '↓', value: 'ArrowDown' },
  { label: '←', value: 'ArrowLeft' },
  { label: '→', value: 'ArrowRight' },
  { label: 'Home', value: 'Home' },
  { label: 'End', value: 'End' },
  { label: 'PageUp', value: 'PageUp' },
  { label: 'PageDown', value: 'PageDown' },
  { label: '鼠标左键', value: 'MouseLeft' },
  { label: '鼠标中键', value: 'MouseMiddle' },
  { label: '鼠标右键', value: 'MouseRight' },
  { label: '鼠标后退键', value: 'MouseBack' },
  { label: '鼠标前进键', value: 'MouseForward' },
]

const conflictsByCommand = computed(() => {
  // 冲突按命令反查，列表行只关心自己相关的提示，点击时再跳到另一个命令。
  const map = new Map()
  conflicts.value.forEach(conflict => {
    conflict.commandIds.forEach(commandId => {
      if (!map.has(commandId)) map.set(commandId, [])
      map.get(commandId).push(conflict)
    })
  })
  return map
})

const commandRows = computed(() => commands.value.map(command => ({
  command,
  keys: getCommandDisplayKeys(command, keybindingConfig.value),
  conflicts: conflictsByCommand.value.get(command.id) || [],
})))

const filteredRows = computed(() => {
  const query = String(searchQuery.value || '').trim().toLowerCase()
  return commandRows.value.filter(({ command }) => {
    if (selectedCategory.value !== 'all' && command.category !== selectedCategory.value) return false
    if (!query) return true
    return [
      command.title,
      command.id,
      command.category,
      command.description,
    ].some(value => String(value || '').toLowerCase().includes(query))
  })
})

const scopeLabel = (scope = '') => {
  if (scope === 'global') return '全局'
  return scope
}

const conflictLevelLabel = (level = '') => {
  const labels = { critical: '严重', high: '较高', medium: '提示', low: '轻微' }
  return labels[level] || '提示'
}

const conflictClass = (level = '') => {
  const classes = {
    critical: 'bg-accent-danger/15 text-accent-danger border border-accent-danger/20',
    high: 'bg-accent-warn/15 text-accent-warn border border-accent-warn/20',
    medium: 'bg-accent-cool/12 text-accent-cool border border-accent-cool/18',
    low: 'bg-bg-overlay/5 text-text-dim border border-border-base/10',
  }
  return classes[level] || classes.medium
}

const conflictTooltip = (conflict) => {
  const [leftTitle, rightTitle] = conflict.commandTitles
  const [leftId, rightId] = conflict.commandIds
  return [
    `[[${leftTitle}]] 和 [[${rightTitle}]] 的 ^^[${formatKeybindingLabel(conflict.keybinding)}]^^ 快捷键冲突。`,
    conflict.message,
    `作用域：${conflict.scopes.join(' / ')}`,
    '__点击跳转到另一条冲突命令。__',
  ].join('\n')
}

const jumpToConflictTarget = async (currentCommandId, conflict) => {
  const targetCommandId = conflict.commandIds.find(commandId => commandId !== currentCommandId)
  if (!targetCommandId) return
  selectedCategory.value = 'all'
  searchQuery.value = ''
  await nextTick()
  const targetEl = rowRefs.value[targetCommandId]
  if (!targetEl?.scrollIntoView) return
  targetEl.scrollIntoView({ block: 'center', behavior: 'smooth' })
  targetEl.classList.add('ring-1', 'ring-accent-primary/70')
  window.setTimeout(() => targetEl.classList.remove('ring-1', 'ring-accent-primary/70'), 1200)
}

const getEditableKeys = (command) => {
  const currentKeys = getCommandEffectiveKeys(command, keybindingConfig.value)
  return currentKeys.filter(keybinding => !command.lockedKeys.includes(keybinding))
}

const isLockedKeybinding = (command, keybinding) => (
  (command.lockedKeys || []).includes(keybinding) || (command.displayKeys || []).includes(keybinding)
)

const setCommandEditableKeys = (commandId, keys = []) => {
  const config = ensureKeybindingConfig()
  // 只保存用户覆盖的可编辑键位；锁定键和展示键始终来自命令声明。
  config.bindings[commandId] = normalizeKeybindingList(keys)
  delete config.disabledDefaults[commandId]
}

const ensureDraft = (commandId) => {
  if (!draftByCommand[commandId]) {
    draftByCommand[commandId] = {
      modifiers: [],
      mainKey: '',
    }
  }
  return draftByCommand[commandId]
}

const isDraftModifierActive = (commandId, modifier) => ensureDraft(commandId).modifiers.includes(modifier)

const toggleDraftModifier = (commandId, modifier) => {
  const draft = ensureDraft(commandId)
  draft.modifiers = draft.modifiers.includes(modifier)
    ? draft.modifiers.filter(item => item !== modifier)
    : [...draft.modifiers, modifier]
}

const getDraftMainKey = (commandId) => ensureDraft(commandId).mainKey

const setDraftMainKey = (commandId, mainKey) => {
  ensureDraft(commandId).mainKey = String(mainKey || '')
}

const buildDraftKeybinding = (commandId) => {
  const draft = ensureDraft(commandId)
  const mainKey = draft.mainKey === '__modifier_only__' ? '' : draft.mainKey
  const keybinding = normalizeKeybinding([...draft.modifiers, mainKey].filter(Boolean).join('+'))
  // 裸鼠标键会吞掉常规点击/右键，不允许保存；带修饰键的鼠标手势可以作为说明或后续扩展。
  return isUnsafeBareMouseKeybinding(keybinding) ? '' : keybinding
}

const addDraftKeybinding = (command) => {
  const keybinding = buildDraftKeybinding(command.id)
  if (!keybinding) return
  setCommandEditableKeys(command.id, [...getEditableKeys(command), keybinding])
}

const isUnsafeBareMouseKeybinding = (keybinding = '') => ['MouseLeft', 'MouseMiddle', 'MouseRight'].includes(keybinding)

const removeKeybinding = (command, keybinding) => {
  setCommandEditableKeys(command.id, getEditableKeys(command).filter(item => item !== keybinding))
}

const resetCommandKeybindings = (commandId) => {
  const config = ensureKeybindingConfig()
  delete config.bindings[commandId]
  delete config.disabledDefaults[commandId]
}

const clearCommandKeybindings = (commandId) => {
  setCommandEditableKeys(commandId, [])
}

const resetAllKeybindings = () => {
  const config = ensureKeybindingConfig()
  // 保持同一个响应式对象，只清空用户覆盖项；直接替换对象时列表行可能仍读到旧引用。
  Object.keys(config.bindings).forEach(commandId => delete config.bindings[commandId])
  Object.keys(config.disabledDefaults).forEach(commandId => delete config.disabledDefaults[commandId])
  config.version = createDefaultKeybindingConfig().version
  Object.keys(draftByCommand).forEach(commandId => delete draftByCommand[commandId])
}
</script>
