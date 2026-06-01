<!-- frontend/src/components/AIDefinitionManager.vue -->
<template>
  <CommonModalShell :show="appStore.uiState.showAIDefinitionManager" title="AI 定义管理" description="在这里集中管理 AI 助手、任务和模板。"
    size="xl" :z-index="130" accent="special" panel-class="border-accent-special/30" content-class="h-full flex flex-col"
    @close="closeModal" >
    <template #icon>
      <Drama class="size-5 text-accent-special" />
    </template>

        <div class="relative z-10 flex h-full flex-1 overflow-hidden">
          <!-- 左侧导航栏：入口/模板切换、搜索与列表 -->
          <div class="sidebar-surface flex w-88 shrink-0 flex-col">
            <div class="space-y-3 border-b border-border-base/5 p-4">
              <div class="flex gap-2">
                <button v-for="tab in TABS" :key="tab.id" @click="activeTab = tab.id"
                  class="flex-1 rounded-lg border px-3 py-2 text-xs font-bold transition-colors"
                  :class="activeTab === tab.id ? 'border-accent-special/30 bg-accent-special/15 text-accent-special' : 'border-border-base/10 bg-bg-inset/70 text-text-dim hover:text-text-main'"
                >
                  {{ tab.label }}
                </button>
              </div>
              <button v-if="activeTab === 'prompts'" @click="createNewPrompt" class="flex w-full items-center justify-center gap-2 rounded-lg border border-accent-special/30 bg-accent-special/10 py-2 text-sm font-bold text-accent-special transition-all hover:bg-accent-special/20" >
                <Plus class="size-4" /> 创建自定义模板
              </button>
              <CommonInput v-model="searchText" :placeholder="tabSearchPlaceholder" />
            </div>

            <div class="flex-1 overflow-y-auto p-2">
              <template v-if="activeTab === 'entries'">
                <div class="space-y-1">
                  <div v-for="entry in filteredEntries" :key="entry.id" @click="selectEntry(entry)"
                    class="cursor-pointer rounded-lg px-3 py-2 transition-all" :class="currentEntryId === entry.id ? 'bg-accent-special/20 shadow-[inset_3px_0_0_rgba(var(--rgb-accent-special),1)]' : 'hover:bg-bg-overlay/5'" >
                    <div class="min-w-0" v-tooltip="entryTooltip(entry)">
                      <div class="truncate text-sm font-bold" :class="currentEntryId === entry.id ? 'text-accent-special' : 'text-text-main'">{{ entry.name }}</div>
                      <div class="truncate font-mono text-[0.65rem] text-text-dim">{{ entry.id }}</div>
                    </div>
                  </div>
                </div>
              </template>

              <template v-else>
                <div v-if="groupedPromptEntries.system.length > 0" class="mb-3">
                  <div class="px-2 pb-1 text-[0.7rem] font-black uppercase tracking-[0.22em] text-text-disabled">系统模板</div>
                  <div class="space-y-1">
                    <div v-for="[promptId, prompt] in groupedPromptEntries.system" :key="promptId" @click="selectPrompt(promptId)"
                      class="cursor-pointer rounded-lg px-3 py-2 transition-all" :class="currentPromptId === promptId ? 'bg-accent-special/20 shadow-[inset_3px_0_0_rgba(var(--rgb-accent-special),1)]' : 'hover:bg-bg-overlay/5'" >
                      <div class="mb-1 flex items-start justify-between gap-2">
                        <span class="truncate text-sm font-bold" :class="currentPromptId === promptId ? 'text-accent-special' : 'text-text-main'">{{ prompt.name }}</span>
                        <Lock class="size-3 shrink-0 text-text-dim" />
                      </div>
                      <div class="truncate font-mono text-[0.65rem] text-text-dim">{{ promptId }}</div>
                    </div>
                  </div>
                </div>
                <div v-if="groupedPromptEntries.custom.length > 0">
                  <div class="px-2 pb-1 text-[0.7rem] font-black uppercase tracking-[0.22em] text-text-disabled">自定义模板</div>
                  <div class="space-y-1">
                    <div v-for="[promptId, prompt] in groupedPromptEntries.custom" :key="promptId" @click="selectPrompt(promptId)"
                      class="cursor-pointer rounded-lg px-3 py-2 transition-all" :class="currentPromptId === promptId ? 'bg-accent-special/20 shadow-[inset_3px_0_0_rgba(var(--rgb-accent-special),1)]' : 'hover:bg-bg-overlay/5'" >
                      <div class="mb-1 flex items-start justify-between gap-2">
                        <span class="truncate text-sm font-bold" :class="currentPromptId === promptId ? 'text-accent-special' : 'text-text-main'">{{ prompt.name }}</span>
                        <User class="size-3 shrink-0 text-accent-primary" />
                      </div>
                      <div class="truncate font-mono text-[0.65rem] text-text-dim">{{ promptId }}</div>
                    </div>
                  </div>
                </div>
              </template>
            </div>
          </div>

          <div class="content-surface flex flex-1 flex-col">
            <template v-if="activeTab === 'entries' && currentEntryForm">
              <div class="toolbar-surface flex h-12 shrink-0 items-center justify-between px-6">
                <div class="flex items-center gap-2">
                  <span class="rounded border border-accent-special/20 bg-accent-special/10 px-2 py-0.5 font-mono text-xs text-accent-special">
                    ID: {{ currentEntryId }}
                  </span>
                  <span class="rounded border border-border-base/10 bg-bg-inset/70 px-2 py-0.5 text-[0.7rem] text-text-dim">
                    {{ currentEntryKindLabel }}
                  </span>
                </div>
                <button @click="handleSaveEntry" class="rounded bg-accent-special px-6 py-1.5 text-xs font-bold text-on-accent-special transition-all hover:bg-accent-special/80">
                  保存入口配置
                </button>
              </div>

              <div class="flex-1 overflow-y-auto p-6 space-y-6">
                <div class="grid grid-cols-[1fr_1fr] gap-x-8 gap-y-5">
                  <div>
                    <div class="mb-1 text-xs font-bold uppercase tracking-widest text-text-dim">名称</div>
                    <div class="text-sm font-bold text-text-main">{{ currentEntry?.name || '未命名入口' }}</div>
                  </div>
                  <CommonSelect v-model="currentEntryForm.prompt_id" label="使用的模板" :options="currentEntryPromptOptions" />
                  <div class="col-span-2">
                    <div class="mb-1 text-xs font-bold uppercase tracking-widest text-text-dim">描述</div>
                    <div class="text-sm text-text-main">{{ currentEntry?.description || '无描述' }}</div>
                  </div>
                </div>

                <div v-if="currentEntryType === 'assistant'" class="pt-2">
                  <div class="mb-5">
                    <div class="mb-2 text-sm font-bold text-text-main">可返回的操作</div>
                    <div class="flex flex-wrap gap-2">
                      <span v-for="actionType in currentEntry?.action_types || []" :key="`assistant-action-${actionType}`" v-tooltip="getActionDescription(actionType) || actionType"
                        class="rounded border border-accent-primary/20 bg-accent-primary/10 px-2 py-1 text-xs text-accent-primary" >
                        {{ getActionLabel(actionType) }}
                      </span>
                      <span v-if="!(currentEntry?.action_types || []).length" class="text-xs text-text-dim">这个助手只回答问题，不会给出可直接执行的操作。</span>
                    </div>
                  </div>
                  <div class="mb-3 text-sm font-bold text-text-main">可用工具</div>
                  <p class="mb-3 text-xs text-text-dim">这里决定这个助手能使用哪些工具。新会话默认会全部开启，你也可以在会话里临时关闭部分工具。</p>
                  <div class="grid grid-cols-2 gap-2">
                    <label v-for="tool in toolDefinitionEntries" :key="`assistant-${tool.id}`" class="modal-section-subtle flex items-start gap-2 px-3 py-2 text-xs text-text-main">
                      <input :checked="currentEntryForm.tool_scope_selectable.includes(tool.id)" type="checkbox" @change="toggleAssistantTool(tool.id, $event.target.checked)" />
                      <div class="min-w-0">
                        <div class="font-semibold" v-tooltip="getToolTooltip(tool)">{{ tool.label || tool.id }}</div>
                      </div>
                    </label>
                  </div>
                </div>
              </div>
            </template>

            <template v-else-if="activeTab === 'prompts' && currentPromptForm">
              <div class="toolbar-surface flex h-12 shrink-0 items-center justify-between px-6">
                <div class="flex items-center gap-2">
                  <span class="rounded border border-accent-special/20 bg-accent-special/10 px-2 py-0.5 font-mono text-xs text-accent-special">
                    ID: {{ currentPromptId || '保存后自动生成' }}
                  </span>
                  <span class="rounded border px-2 py-0.5 text-[0.7rem]" :class="currentPromptForm.is_system ? 'border-border-base/10 bg-bg-inset/70 text-text-dim' : 'border-accent-primary/20 bg-accent-primary/10 text-accent-primary'">
                    {{ currentPromptForm.is_system ? '系统模板' : '自定义模板' }}
                  </span>
                </div>
                <div class="flex items-center gap-2">
                  <span v-if="currentPromptForm.is_system" class="text-xs text-text-dim">系统模板只读</span>
                  <button v-if="!currentPromptForm.is_system && !isPromptNew" @click="handleDeletePrompt" class="rounded border border-accent-danger/30 bg-accent-danger/10 px-4 py-1.5 text-xs font-bold text-accent-danger transition-all hover:bg-accent-danger hover:text-on-accent-danger">
                    删除模板
                  </button>
                  <button v-if="!currentPromptForm.is_system" @click="handleSavePrompt" class="rounded bg-accent-special px-6 py-1.5 text-xs font-bold text-on-accent-special transition-all hover:bg-accent-special/80">
                    保存模板
                  </button>
                </div>
              </div>

              <div class="flex-1 overflow-y-auto p-6 space-y-2">
                <div v-if="currentPromptForm.is_system" class="grid grid-cols-2 gap-4">
                  <div class="space-y-1">
                    <div class="text-xs font-bold uppercase tracking-widest text-text-dim">模板名称</div>
                    <div class="text-sm font-bold text-text-main">{{ currentPromptForm.name }}</div>
                  </div>
                  <div class="space-y-1">
                    <div class="text-xs font-bold uppercase tracking-widest text-text-dim">分类</div>
                    <div class="text-sm text-text-main">{{ selectedPromptCategory?.label || currentPromptForm.category || '未分类' }}</div>
                  </div>
                  <div class="space-y-1 col-span-2">
                    <div class="text-xs font-bold uppercase tracking-widest text-text-dim">模板描述</div>
                    <div class="text-sm text-text-main">{{ currentPromptForm.description || '无描述' }}</div>
                  </div>
                </div>
                <div v-else class="grid grid-cols-2 gap-4">
                  <CommonInput v-model="currentPromptForm.name" label="模板名称" />
                  <CommonSelect v-model="currentPromptForm.category" label="分类" :options="promptCategoryOptions" :editable="false" />
                  <CommonInput class="col-span-2" v-model="currentPromptForm.description" label="模板描述" />
                </div>

                <div class="grid grid-cols-[1.2fr_auto] gap-6">
                </div>

                <div v-if="currentPromptForm.is_system" class="rounded-lg border border-accent-primary/20 bg-accent-primary/5 p-4 text-xs text-text-dim">
                  系统模板只能查看，不能直接修改。你仍然可以查看它会使用哪些附件和变量。
                </div>

                <div class="pt-2">
                  <div class="mb-3 flex items-center gap-2 text-sm font-bold text-text-main">
                    <Paperclip class="size-4 text-accent-special" /> 可用附件
                  </div>
                  <div class="grid grid-cols-2 gap-2">
                    <label v-for="attachment in attachmentDefinitionEntries" :key="attachment.kind" class="modal-section-subtle flex items-center gap-2 px-3 py-2 text-xs text-text-main" :class="currentPromptForm.is_system ? 'opacity-80' : ''">
                      <input :checked="currentPromptForm.attachment_kinds.includes(attachment.kind)" :disabled="currentPromptForm.is_system" type="checkbox" @change="togglePromptAttachment(attachment.kind, $event.target.checked)" />
                      <span>{{ attachment.label }}</span>
                    </label>
                  </div>
                </div>

                <div v-if="selectedAttachmentDefinitions.length > 0" class="modal-section p-4">
                  <div class="mb-3 text-sm font-bold text-text-main">发送给 AI 的附件内容</div>
                  <p class="mb-4 text-xs text-text-dim">控制附件里哪些信息会发给 AI。取消勾选后，这部分内容通常不会发送。</p>
                  <div class="space-y-4">
                    <div v-for="attachment in selectedAttachmentDefinitions" :key="`projection-${attachment.kind}`" class="modal-section-subtle p-3">
                      <div class="mb-2 text-xs font-bold uppercase tracking-widest text-text-dim">{{ attachment.label }}</div>
                      <div class="grid grid-cols-2 gap-2">
                        <label v-for="field in attachment.projection_options || []" :key="`${attachment.kind}-${field.path}`"
                          class="flex items-start gap-2 rounded-lg border border-border-base/10 bg-bg-inset/60 px-3 py-2 text-xs text-text-main" >
                          <input :checked="isProjectionFieldEnabled(attachment.kind, field.path)" :disabled="currentPromptForm.is_system"
                            type="checkbox" @change="toggleProjectionField(attachment.kind, field.path, $event.target.checked)" />
                          <div class="min-w-0">
                            <div class="font-semibold" v-tooltip="field.description || field.path">{{ field.label }}</div>
                            <div class="font-mono text-[0.7rem] text-text-dim">{{ field.path }}</div>
                          </div>
                        </label>
                      </div>
                    </div>
                  </div>
                </div>

                <div class="rounded-lg border border-accent-primary/20 bg-accent-primary/5 p-4">
                  <div class="mb-3 flex items-center gap-2 text-sm font-bold text-accent-primary">
                    <Braces class="size-4" /> 可用变量
                  </div>
                  <div class="space-y-4">
                    <div>
                      <div class="mb-2 text-xs font-bold uppercase tracking-widest text-text-dim">通用变量</div>
                      <div class="flex flex-wrap gap-2">
                        <button v-for="variable in baseVariables" :key="`base-${variable.key}`" :disabled="currentPromptForm.is_system" v-tooltip="variable.description || variable.key"
                          class="rounded-md border border-accent-primary/30 bg-bg-inset/80 px-2 py-1 text-left text-xs text-accent-primary transition-colors hover:bg-accent-primary hover:text-on-accent-primary disabled:cursor-default disabled:opacity-70 disabled:hover:bg-bg-inset/80 disabled:hover:text-accent-primary"
                          @click="insertVariable(variable.key)">
                          <div class="font-semibold">{{ variable.label }}</div>
                          <div class="font-mono text-[0.7rem] opacity-70">{{ '{' + variable.key + '}' }}</div>
                        </button>
                      </div>
                    </div>

                    <div v-for="attachment in selectedAttachmentDefinitions" :key="attachment.kind">
                      <div class="mb-2 text-xs font-bold uppercase tracking-widest text-text-dim">{{ attachment.label }}</div>
                      <div class="flex flex-wrap gap-2">
                        <button v-for="variable in attachment.prompt_variables" :key="`${attachment.kind}-${variable.key}`" :disabled="currentPromptForm.is_system" v-tooltip="variable.description || variable.key"
                          class="rounded-md border border-accent-primary/30 bg-bg-inset/80 px-2 py-1 text-left text-xs text-accent-primary transition-colors hover:bg-accent-primary hover:text-on-accent-primary disabled:cursor-default disabled:opacity-70 disabled:hover:bg-bg-inset/80 disabled:hover:text-accent-primary"
                          @click="insertVariable(variable.key)">
                          <div class="font-semibold">{{ variable.label }}</div>
                          <div class="font-mono text-[0.7rem] opacity-70">{{ '{' + variable.key + '}' }}</div>
                        </button>
                      </div>
                    </div>
                  </div>
                </div>

                <div class="space-y-2">
                  <label class="flex items-center justify-between text-xs font-bold uppercase tracking-widest text-text-dim">
                    <span class="flex items-center gap-2"><Bot class="size-4 text-accent-special" /> 系统提示词</span>
                    <span class="font-mono text-[0.6rem] opacity-50">给 AI 的固定说明</span>
                  </label>
                  <textarea v-model="currentPromptForm.system" :disabled="currentPromptForm.is_system" class="input-glass min-h-60 w-full resize-y p-3 font-mono text-sm leading-relaxed text-accent-cool focus:outline-none disabled:opacity-70"></textarea>
                </div>

                <div class="space-y-2">
                  <label class="flex items-center justify-between text-xs font-bold uppercase tracking-widest text-text-dim">
                    <span class="flex items-center gap-2"><User class="size-4 text-accent-primary" /> 用户输入模板</span>
                    <span class="font-mono text-[0.6rem] opacity-50">每次发送时的输入格式</span>
                  </label>
                  <textarea v-model="currentPromptForm.user_template" :disabled="currentPromptForm.is_system" class="input-glass min-h-60 w-full resize-y p-3 font-mono text-sm leading-relaxed text-text-main focus:outline-none disabled:opacity-70"></textarea>
                </div>
              </div>
            </template>

            <div v-else class="flex flex-1 flex-col items-center justify-center text-text-disabled">
              <TerminalSquare class="mb-4 size-16 opacity-20" />
              <p class="text-sm uppercase tracking-widest">请选择左侧项目</p>
            </div>
          </div>
        </div>
  </CommonModalShell>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { Bot, Braces, Drama, Lock, Paperclip, Plus, TerminalSquare, User } from 'lucide-vue-next'
import CommonModalShell from './common/CommonModalShell.vue'
import CommonInput from './common/input/CommonInput.vue'
import CommonSelect from './common/input/CommonSelect.vue'
import { useAppStore } from '../stores/appStore'
import { useAiStore } from '../stores/aiStore'
import { useConfirmStore } from '../stores/confirmStore'
import { deepClone, normalizeText } from '../utils/common'

// -----------------------------------------------------------------
// Store 依赖 (Stores)
// -----------------------------------------------------------------
const appStore = useAppStore()
const aiStore = useAiStore()
const confirmStore = useConfirmStore()

// -----------------------------------------------------------------
// 视图配置 (View Config)
// -----------------------------------------------------------------
const TABS = [
  { id: 'entries', label: '入口' },
  { id: 'prompts', label: '模板' },
]

// -----------------------------------------------------------------
// 状态定义 (State / Refs)
// -----------------------------------------------------------------
const activeTab = ref('entries')
const searchText = ref('')
const EMPTY_PROMPT_EDITOR_META = { categories: {}, attachments: {}, actions: {}, tools: {} }

const prompts = ref({})
const assistants = ref({})
const tasks = ref({})
const definitionEditorMeta = ref(EMPTY_PROMPT_EDITOR_META)

const currentPromptId = ref(null)
const currentPromptForm = ref(null)
const isPromptNew = ref(false)

const currentEntryId = ref(null)
const currentEntryForm = ref(null)

// -----------------------------------------------------------------
// 计算属性 (Computed)
// -----------------------------------------------------------------
const promptEntries = computed(() => Object.entries(prompts.value || {}))
const sortedPromptEntries = computed(() => [...promptEntries.value].sort((a, b) => String(a[0]).localeCompare(String(b[0]))))
const sortById = (list) => [...list].sort((a, b) => String(a[0]).localeCompare(String(b[0])))
const assistantPromptEntries = computed(() => sortById(promptEntries.value.filter(([, prompt]) => prompt?.category === 'assistant')))
const taskPromptEntries = computed(() => sortById(promptEntries.value.filter(([, prompt]) => prompt?.category === 'task')))
const promptCategoryOptions = computed(() => (
  Object.values(definitionEditorMeta.value?.categories || {}).sort((a, b) => String(a.id).localeCompare(String(b.id))).map(category => ({
    label: category.label,
    value: category.id,
    desc: category.description || '',
  }))
))
const attachmentDefinitionEntries = computed(() => Object.values(definitionEditorMeta.value?.attachments || {}).sort((a, b) => String(a.label || a.kind).localeCompare(String(b.label || b.kind))))
const toolDefinitionEntries = computed(() => (
  Object.values(aiStore.getToolDefinitions() || {})
    .sort((a, b) => String(a.label || a.id || '').localeCompare(String(b.label || b.id || '')))
))
const getEntryTypeLabel = (entryType = '') => (entryType === 'assistant' ? '系统助手' : '系统任务')

const entryList = computed(() => {
  const assistantEntries = Object.entries(assistants.value || {}).map(([id, data]) => ({
    id,
    type: 'assistant',
    name: data?.name || id,
    description: data?.description || '',
    prompt_id: data?.prompt_id || '',
    tool_scope_selectable: Array.isArray(data?.tool_scope_selectable) ? data.tool_scope_selectable : [],
    action_types: Array.isArray(data?.action_types) ? data.action_types : [],
    raw: data,
  }))
  const taskEntries = Object.entries(tasks.value || {}).map(([id, data]) => ({
    id,
    type: 'task',
    name: data?.name || id,
    description: data?.description || '',
    prompt_id: data?.prompt_id || '',
    raw: data,
  }))
  return [...assistantEntries, ...taskEntries].sort((a, b) => String(a.id).localeCompare(String(b.id)))
})
const entryMap = computed(() => (
  Object.fromEntries(entryList.value.map(entry => [entry.id, entry]))
))
const currentEntry = computed(() => entryMap.value[currentEntryId.value] || null)
const currentEntryType = computed(() => currentEntry.value?.type || '')

const filteredEntries = computed(() => {
  const keyword = searchText.value.trim().toLowerCase()
  if (!keyword) return entryList.value
  return entryList.value.filter(entry => `${entry.id} ${entry.name} ${entry.description}`.toLowerCase().includes(keyword))
})

const tabSearchPlaceholder = computed(() => (
  activeTab.value === 'entries' ? '搜索系统入口名称或 ID' : '搜索模板名称或 ID'
))

const groupedPromptEntries = computed(() => {
  const keyword = searchText.value.trim().toLowerCase()
  const entries = Object.entries(prompts.value || {}).filter(([id, data]) => {
    if (!keyword) return true
    return `${id} ${data?.name || ''} ${data?.description || ''}`.toLowerCase().includes(keyword)
  })
  const sortEntries = (list) => list.sort((a, b) => String(a[0]).localeCompare(String(b[0])))
  return {
    system: sortEntries(entries.filter(([, data]) => !!data?.is_system)),
    custom: sortEntries(entries.filter(([, data]) => !data?.is_system)),
  }
})

const selectedPromptCategory = computed(() => {
  const categoryId = currentPromptForm.value?.category
  return categoryId ? definitionEditorMeta.value?.categories?.[categoryId] || null : null
})

const selectedAttachmentDefinitions = computed(() => {
  const kinds = currentPromptForm.value?.attachment_kinds || []
  return kinds
    .map(kind => definitionEditorMeta.value?.attachments?.[kind])
    .filter(Boolean)
})
const baseVariables = computed(() => selectedPromptCategory.value?.base_variables || [])
const currentEntryKindLabel = computed(() => getEntryTypeLabel(currentEntryType.value))
const currentEntryPromptOptions = computed(() => {
  const source = currentEntryType.value === 'assistant' ? assistantPromptEntries.value : taskPromptEntries.value
  return source.map(([promptId, prompt]) => ({
    label: `${prompt.name} (${promptId})`,
    value: promptId,
    desc: prompt.description || '',
  }))
})

const getActionDefinition = (actionType) => definitionEditorMeta.value?.actions?.[actionType] || null
const getActionLabel = (actionType) => getActionDefinition(actionType)?.label || actionType
const getActionDescription = (actionType) => getActionDefinition(actionType)?.description || ''
const getToolTooltip = (tool = {}) => {
  const title = normalizeText(tool?.label || tool?.id, tool?.id || '工具')
  const details = [
    normalizeText(tool?.id) ? `ID: ${normalizeText(tool.id)}` : '',
    normalizeText(tool?.description),
  ].filter(Boolean)
  return details.length > 0 ? `${title}\n\n${details.join('\n')}` : title
}

// -----------------------------------------------------------------
// 数据加载与同步 (Lifecycle / Watch)
// -----------------------------------------------------------------
const loadData = async () => {
  const config = await aiStore.getAiConfig()
  prompts.value = config?.prompts || {}
  assistants.value = config?.assistants || {}
  tasks.value = config?.tasks || {}
  definitionEditorMeta.value = config?.definition_editor_meta || EMPTY_PROMPT_EDITOR_META

  if (!currentEntryId.value && filteredEntries.value.length > 0) selectEntry(filteredEntries.value[0])
  if (!currentPromptId.value && sortedPromptEntries.value.length > 0) selectPrompt(sortedPromptEntries.value[0][0])
}

watch(() => appStore.uiState.showAIDefinitionManager, (val) => {
  if (val) loadData()
})

// -----------------------------------------------------------------
// 业务方法 (Methods)
// -----------------------------------------------------------------
const entryTooltip = (entry) => {
  const promptName = prompts.value?.[entry?.prompt_id || '']?.name || entry?.prompt_id || ''
  return `${entry.name} (${entry.id})\n\n<${promptName}>\n__${entry.description || ''}__`
}

const closeModal = () => {
  appStore.uiState.showAIDefinitionManager = false
}

const normalizeAssistantEntryOverrideForm = (entry = {}) => ({
  prompt_id: entry?.prompt_id || '',
  tool_scope_selectable: Array.isArray(entry?.tool_scope_selectable) ? [...entry.tool_scope_selectable] : [],
})

const selectEntry = (entry) => {
  currentEntryId.value = entry.id
  currentEntryForm.value = entry.type === 'assistant'
    ? normalizeAssistantEntryOverrideForm(entry.raw)
    : deepClone(entry.raw)
}

const selectPrompt = (promptId) => {
  currentPromptId.value = promptId
  isPromptNew.value = false
  currentPromptForm.value = deepClone(prompts.value[promptId])
  currentPromptForm.value.attachment_kinds = Array.isArray(currentPromptForm.value.attachment_kinds)
    ? [...currentPromptForm.value.attachment_kinds]
    : []
  currentPromptForm.value.attachment_projection_overrides = currentPromptForm.value.attachment_projection_overrides
    && typeof currentPromptForm.value.attachment_projection_overrides === 'object'
    ? deepClone(currentPromptForm.value.attachment_projection_overrides)
    : {}
}

const createNewPrompt = () => {
  activeTab.value = 'prompts'
  currentPromptId.value = null
  isPromptNew.value = true
  currentPromptForm.value = {
    is_system: false,
    name: '新建自定义提示词',
    description: '',
    category: 'assistant',
    attachment_kinds: [],
    attachment_projection_overrides: {},
    system: '你是一个乐于助人的助手。',
    user_template: '{message}\n\n{attachments_block}',
  }
}

const insertVariable = (varName) => {
  if (!currentPromptForm.value || currentPromptForm.value.is_system) return
  currentPromptForm.value.user_template += ` {${varName}} `
}

const toggleAssistantTool = (toolName, checked) => {
  if (!currentEntryForm.value || currentEntryType.value !== 'assistant') return
  const next = new Set(currentEntryForm.value.tool_scope_selectable || [])
  if (checked) next.add(toolName)
  else next.delete(toolName)
  currentEntryForm.value.tool_scope_selectable = [...next]
}

const togglePromptAttachment = (attachmentKind, checked) => {
  if (!currentPromptForm.value || currentPromptForm.value.is_system) return
  const next = new Set(currentPromptForm.value.attachment_kinds || [])
  if (checked) next.add(attachmentKind)
  else {
    next.delete(attachmentKind)
    if (currentPromptForm.value.attachment_projection_overrides) {
      delete currentPromptForm.value.attachment_projection_overrides[attachmentKind]
    }
  }
  currentPromptForm.value.attachment_kinds = [...next]
}

const getAttachmentProjectionDefaults = (attachmentKind) => {
  const attachment = definitionEditorMeta.value?.attachments?.[attachmentKind] || {}
  return Array.isArray(attachment.projection_options)
    ? attachment.projection_options.filter(field => field.default_enabled !== false).map(field => field.path)
    : []
}

const isProjectionFieldEnabled = (attachmentKind, fieldPath) => {
  const overrides = currentPromptForm.value?.attachment_projection_overrides?.[attachmentKind]
  const includeFields = Array.isArray(overrides?.include_fields) && overrides.include_fields.length > 0
    ? overrides.include_fields
    : getAttachmentProjectionDefaults(attachmentKind)
  return includeFields.includes(fieldPath)
}

const toggleProjectionField = (attachmentKind, fieldPath, checked) => {
  if (!currentPromptForm.value || currentPromptForm.value.is_system) return
  if (!currentPromptForm.value.attachment_projection_overrides || typeof currentPromptForm.value.attachment_projection_overrides !== 'object') {
    currentPromptForm.value.attachment_projection_overrides = {}
  }

  const defaults = getAttachmentProjectionDefaults(attachmentKind)
  const currentOverride = currentPromptForm.value.attachment_projection_overrides[attachmentKind] || {}
  const nextSet = new Set(
    Array.isArray(currentOverride.include_fields) && currentOverride.include_fields.length > 0
      ? currentOverride.include_fields
      : defaults
  )

  if (checked) nextSet.add(fieldPath)
  else nextSet.delete(fieldPath)

  const nextIncludeFields = [...nextSet]
  // 默认值不落盘，避免定义文件被“全部勾选”的冗余数据刷满。
  const matchesDefault = nextIncludeFields.length === defaults.length
    && nextIncludeFields.every(path => defaults.includes(path))

  if (matchesDefault) {
    delete currentPromptForm.value.attachment_projection_overrides[attachmentKind]
    return
  }

  currentPromptForm.value.attachment_projection_overrides[attachmentKind] = {
    include_fields: nextIncludeFields,
    exclude_fields: [],
  }
}

const handleSaveEntry = async () => {
  if (!currentEntryId.value || !currentEntryForm.value) return
  if (currentEntryType.value === 'assistant') {
    const payload = {
      prompt_id: currentEntryForm.value.prompt_id || '',
      tool_scope_selectable: Array.isArray(currentEntryForm.value.tool_scope_selectable)
        ? [...currentEntryForm.value.tool_scope_selectable]
        : [],
    }
    const resData = await aiStore.saveAssistant(currentEntryId.value, payload)
    if (resData) {
      assistants.value = resData
      const nextEntry = entryList.value.find(entry => entry.id === currentEntryId.value && entry.type === 'assistant')
      if (nextEntry) selectEntry(nextEntry)
    }
    return
  }

  const resData = await aiStore.saveTask(currentEntryId.value, currentEntryForm.value)
  if (resData) {
    tasks.value = resData
    const nextEntry = entryList.value.find(entry => entry.id === currentEntryId.value && entry.type === 'task')
    if (nextEntry) selectEntry(nextEntry)
  }
}

const handleSavePrompt = async () => {
  const resData = await aiStore.savePrompt(currentPromptId.value || '', currentPromptForm.value)
  if (resData) {
    prompts.value = resData.prompts || {}
    selectPrompt(resData.prompt_id)
  }
}

const handleDeletePrompt = async () => {
  if (!currentPromptId.value) return
  const ok = await confirmStore.confirmAction('危险操作', `确定要删除模板 ${currentPromptId.value} 吗？此操作不可逆。`, { type: 'error' })
  if (!ok) return
  const resData = await aiStore.deletePrompt(currentPromptId.value)
  if (resData) {
    prompts.value = resData
    currentPromptForm.value = null
    currentPromptId.value = null
    if (sortedPromptEntries.value.length > 0) selectPrompt(sortedPromptEntries.value[0][0])
  }
}
</script>

<style scoped>
/* --- 动画 (Motion) --- */
.fade-enter-active, .fade-leave-active { transition: opacity 0.3s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }

/* --- 滚动条 (Scrollbar) --- */
.custom-scrollbar::-webkit-scrollbar { width: 6px; }
.custom-scrollbar::-webkit-scrollbar-thumb { background: var(--color-border-strong); border-radius: 10px; }
.custom-scrollbar::-webkit-scrollbar-thumb:hover { background: rgba(var(--rgb-accent-special), 0.5); }
</style>
