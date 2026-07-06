<!-- frontend/src/components/AIDefinitionManager.vue -->
<template>
  <CommonModalShell :show="appStore.uiState.showAIDefinitionManager" :title="t('dialog.ai_definitions.title', 'AI 定义管理')" :description="t('dialog.ai_definitions.description', '在这里集中管理 AI 助手、任务和模板。')"
    size="page" :z-index="130" accent="special" panel-class="border-accent-special/30" content-class="h-full flex flex-col"
    @close="closeModal" >
    <template #icon>
      <Drama class="size-5 text-accent-special" />
    </template>

        <div class="relative z-10 flex h-full flex-1 overflow-hidden">
          <!-- 左侧导航栏：入口/模板切换、搜索与列表 -->
          <div class="sidebar-surface flex w-88 shrink-0 flex-col">
            <div class="space-y-3 border-b border-border-base/5 p-4">
              <div class="flex gap-2">
                <button v-for="tab in TABS" :key="tab" @click="activeTab = tab"
                  class="flex-1 rounded-lg border px-3 py-2 text-xs font-bold transition-colors"
                  :class="activeTab === tab ? 'border-accent-special/30 bg-accent-special/15 text-accent-special' : 'border-border-base/10 bg-bg-inset/70 text-text-dim hover:text-text-main'"
                >
                  {{ getTabLabel(tab) }}
                </button>
              </div>
              <button v-if="activeTab === 'prompts'" @click="createNewPrompt" class="flex w-full items-center justify-center gap-2 rounded-lg border border-accent-special/30 bg-accent-special/10 py-2 text-sm font-bold text-accent-special transition-all hover:bg-accent-special/20" >
                <Plus class="size-4" /> {{ t('dialog.ai_definitions.create_custom_prompt', '创建自定义模板') }}
              </button>
              <CommonInput v-model="searchText" :placeholder="tabSearchPlaceholder" />
            </div>

            <div class="flex-1 overflow-y-auto p-2">
              <div v-if="isLoadingDefinitions" class="flex h-full items-center justify-center px-4 text-sm text-text-dim">
                {{ t('dialog.ai_definitions.loading_detail', '正在加载 AI 定义...') }}
              </div>
              <div v-else-if="loadErrorText" class="px-3 py-4 text-sm text-accent-danger">
                {{ loadErrorText }}
              </div>
              <template v-else-if="activeTab === 'entries'">
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
                  <div class="px-2 pb-1 text-[0.7rem] font-black uppercase tracking-[0.22em] text-text-disabled">{{ t('dialog.ai_definitions.system_prompts', '系统模板') }}</div>
                  <div class="space-y-1">
                    <div v-for="[promptId, prompt] in groupedPromptEntries.system" :key="promptId" @click="selectPrompt(promptId)"
                      class="cursor-pointer rounded-lg px-3 py-2 transition-all" :class="currentPromptId === promptId ? 'bg-accent-special/20 shadow-[inset_3px_0_0_rgba(var(--rgb-accent-special),1)]' : 'hover:bg-bg-overlay/5'" >
                      <div class="mb-1 flex items-start justify-between gap-2">
                        <span class="truncate text-sm font-bold" :class="currentPromptId === promptId ? 'text-accent-special' : 'text-text-main'">{{ getPromptName(promptId, prompt) }}</span>
                        <Lock class="size-3 shrink-0 text-text-dim" />
                      </div>
                      <div class="truncate font-mono text-[0.65rem] text-text-dim">{{ promptId }}</div>
                    </div>
                  </div>
                </div>
                <div v-if="groupedPromptEntries.custom.length > 0">
                  <div class="px-2 pb-1 text-[0.7rem] font-black uppercase tracking-[0.22em] text-text-disabled">{{ t('dialog.ai_definitions.custom_prompts', '自定义模板') }}</div>
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
            <div v-if="isLoadingDefinitions" class="flex flex-1 flex-col items-center justify-center text-text-disabled">
              <TerminalSquare class="mb-4 size-16 opacity-20" />
              <p class="text-sm uppercase tracking-widest">{{ t('dialog.ai_definitions.loading', '正在加载 AI 定义') }}</p>
            </div>

            <div v-else-if="loadErrorText" class="flex flex-1 flex-col items-center justify-center px-8 text-center text-text-disabled">
              <TerminalSquare class="mb-4 size-16 opacity-20" />
              <p class="mb-2 text-sm uppercase tracking-widest">{{ t('dialog.ai_definitions.load_failed', '读取失败') }}</p>
              <p class="text-sm text-accent-danger">{{ loadErrorText }}</p>
            </div>

            <template v-else-if="activeTab === 'entries' && currentEntryForm">
              <div class="toolbar-surface flex h-12 shrink-0 items-center justify-between px-6">
                <div class="flex items-center gap-2">
                  <span class="rounded border border-accent-special/20 bg-accent-special/10 px-2 py-0.5 font-mono text-xs text-accent-special">
                    {{ t('common.id', 'ID') }}: {{ currentEntryId }}
                  </span>
                  <span class="rounded border border-border-base/10 bg-bg-inset/70 px-2 py-0.5 text-[0.7rem] text-text-dim">
                    {{ currentEntryKindLabel }}
                  </span>
                </div>
                <button @click="handleSaveEntry" class="rounded bg-accent-special px-6 py-1.5 text-xs font-bold text-on-accent-special transition-all hover:bg-accent-special/80">
                  {{ t('dialog.ai_definitions.save_entry', '保存入口配置') }}
                </button>
              </div>

              <div class="flex-1 overflow-y-auto p-6 space-y-6">
                <div class="grid grid-cols-[1fr_1fr] gap-x-8 gap-y-5">
                  <div>
                    <div class="mb-1 text-xs font-bold uppercase tracking-widest text-text-dim">{{ t('common.name', '名称') }}</div>
                    <div class="text-sm font-bold text-text-main">{{ currentEntry?.name || t('dialog.ai_definitions.unnamed_entry', '未命名入口') }}</div>
                  </div>
                  <CommonSelect v-model="currentEntryForm.prompt_id" :label="t('dialog.ai_definitions.prompt_used', '使用的模板')" :options="currentEntryPromptOptions" />
                  <div class="col-span-2">
                    <div class="mb-1 text-xs font-bold uppercase tracking-widest text-text-dim">{{ t('common.description', '描述') }}</div>
                    <div class="text-sm text-text-main">{{ currentEntry?.description || t('common.no_description', '无描述') }}</div>
                  </div>
                </div>

                <div v-if="currentEntryType === 'assistant'" class="pt-2">
                  <div class="mb-5">
                    <div class="mb-2 text-sm font-bold text-text-main">{{ t('dialog.ai_definitions.available_actions', '可返回的操作') }}</div>
                    <div class="flex flex-wrap gap-2">
                      <span v-for="actionType in currentEntry?.action_types || []" :key="`assistant-action-${actionType}`" v-tooltip="getActionDescription(actionType) || actionType"
                        class="rounded border border-accent-primary/20 bg-accent-primary/10 px-2 py-1 text-xs text-accent-primary" >
                        {{ getActionLabel(actionType) }}
                      </span>
                      <span v-if="!(currentEntry?.action_types || []).length" class="text-xs text-text-dim">{{ t('dialog.ai_definitions.no_actions', '这个助手只回答问题，不会给出可直接执行的操作。') }}</span>
                    </div>
                  </div>
                  <div class="mb-3 text-sm font-bold text-text-main">{{ t('dialog.ai_definitions.available_tools', '可用工具') }}</div>
                  <p class="mb-3 text-xs text-text-dim">{{ t('dialog.ai_definitions.available_tools_desc', '这里决定这个助手能使用哪些工具。新会话默认会全部开启，你也可以在会话里临时关闭部分工具。') }}</p>
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
                    {{ t('common.id', 'ID') }}: {{ currentPromptId || t('dialog.ai_definitions.auto_id_after_save', '保存后自动生成') }}
                  </span>
                  <span class="rounded border px-2 py-0.5 text-[0.7rem]" :class="currentPromptForm.is_system ? 'border-border-base/10 bg-bg-inset/70 text-text-dim' : 'border-accent-primary/20 bg-accent-primary/10 text-accent-primary'">
                    {{ currentPromptForm.is_system ? t('dialog.ai_definitions.system_prompt', '系统模板') : t('dialog.ai_definitions.custom_prompt', '自定义模板') }}
                  </span>
                </div>
                <div class="flex items-center gap-2">
                  <span v-if="currentPromptForm.is_system" class="text-xs text-text-dim">{{ t('dialog.ai_definitions.system_prompt_readonly', '系统模板只读') }}</span>
                  <button v-if="!currentPromptForm.is_system && !isPromptNew" @click="handleDeletePrompt" class="rounded border border-accent-danger/30 bg-accent-danger/10 px-4 py-1.5 text-xs font-bold text-accent-danger transition-all hover:bg-accent-danger hover:text-on-accent-danger">
                    {{ t('dialog.ai_definitions.delete_prompt', '删除模板') }}
                  </button>
                  <button v-if="!currentPromptForm.is_system" @click="handleSavePrompt" class="rounded bg-accent-special px-6 py-1.5 text-xs font-bold text-on-accent-special transition-all hover:bg-accent-special/80">
                    {{ t('dialog.ai_definitions.save_prompt', '保存模板') }}
                  </button>
                </div>
              </div>

              <div class="flex-1 overflow-y-auto p-6 space-y-2">
                <div v-if="currentPromptForm.is_system" class="grid grid-cols-2 gap-4">
                  <div class="space-y-1">
                    <div class="text-xs font-bold uppercase tracking-widest text-text-dim">{{ t('dialog.ai_definitions.prompt_name', '模板名称') }}</div>
                    <div class="text-sm font-bold text-text-main">{{ getPromptName(currentPromptId, currentPromptForm) }}</div>
                  </div>
                  <div class="space-y-1">
                    <div class="text-xs font-bold uppercase tracking-widest text-text-dim">{{ t('common.category', '分类') }}</div>
                    <div class="text-sm text-text-main">{{ selectedPromptCategory?.label || currentPromptForm.category || t('common.uncategorized', '未分类') }}</div>
                  </div>
                  <div class="space-y-1 col-span-2">
                    <div class="text-xs font-bold uppercase tracking-widest text-text-dim">{{ t('dialog.ai_definitions.prompt_description', '模板描述') }}</div>
                    <div class="text-sm text-text-main">{{ getPromptDescription(currentPromptId, currentPromptForm) || t('common.no_description', '无描述') }}</div>
                  </div>
                </div>
                <div v-else class="grid grid-cols-2 gap-4">
                  <CommonInput v-model="currentPromptForm.name" :label="t('dialog.ai_definitions.prompt_name', '模板名称')" />
                  <CommonSelect v-model="currentPromptForm.category" :label="t('common.category', '分类')" :options="promptCategoryOptions" :editable="false" />
                  <CommonInput class="col-span-2" v-model="currentPromptForm.description" :label="t('dialog.ai_definitions.prompt_description', '模板描述')" />
                </div>

                <div class="grid grid-cols-[1.2fr_auto] gap-6">
                </div>

                <div v-if="currentPromptForm.is_system" class="rounded-lg border border-accent-primary/20 bg-accent-primary/5 p-4 text-xs text-text-dim">
                  {{ t('dialog.ai_definitions.system_prompt_view_only', '系统模板只能查看，不能直接修改。你仍然可以查看它会使用哪些附件和变量。') }}
                </div>

                <div class="pt-2">
                  <div class="mb-3 flex items-center gap-2 text-sm font-bold text-text-main">
                    <Paperclip class="size-4 text-accent-special" /> {{ t('dialog.ai_definitions.available_attachments', '可用附件') }}
                  </div>
                  <div class="grid grid-cols-2 gap-2">
                    <label v-for="attachment in attachmentDefinitionEntries" :key="attachment.kind" class="modal-section-subtle flex items-center gap-2 px-3 py-2 text-xs text-text-main" :class="currentPromptForm.is_system ? 'opacity-80' : ''">
                      <input :checked="currentPromptForm.attachment_kinds.includes(attachment.kind)" :disabled="currentPromptForm.is_system" type="checkbox" @change="togglePromptAttachment(attachment.kind, $event.target.checked)" />
                      <span>{{ getAttachmentLabel(attachment) }}</span>
                    </label>
                  </div>
                </div>

                <div v-if="selectedAttachmentDefinitions.length > 0" class="modal-section p-4">
                  <div class="mb-3 text-sm font-bold text-text-main">{{ t('dialog.ai_definitions.attachment_projection_title', '发送给 AI 的附件内容') }}</div>
                  <p class="mb-4 text-xs text-text-dim">{{ t('dialog.ai_definitions.attachment_projection_desc', '控制附件里哪些信息会发给 AI。取消勾选后，这部分内容通常不会发送。') }}</p>
                  <div class="space-y-4">
                    <div v-for="attachment in selectedAttachmentDefinitions" :key="`projection-${attachment.kind}`" class="modal-section-subtle p-3">
                      <div class="mb-2 text-xs font-bold uppercase tracking-widest text-text-dim">{{ getAttachmentLabel(attachment) }}</div>
                      <div class="grid grid-cols-2 gap-2">
                        <label v-for="field in attachment.projection_options || []" :key="`${attachment.kind}-${field.path}`"
                          class="flex items-start gap-2 rounded-lg border border-border-base/10 bg-bg-inset/60 px-3 py-2 text-xs text-text-main" >
                          <input :checked="isProjectionFieldEnabled(attachment.kind, field.path)" :disabled="currentPromptForm.is_system"
                            type="checkbox" @change="toggleProjectionField(attachment.kind, field.path, $event.target.checked)" />
                          <div class="min-w-0">
                            <div class="font-semibold" v-tooltip="getProjectionDescription(attachment.kind, field) || field.path">{{ getProjectionLabel(attachment.kind, field) }}</div>
                            <div class="font-mono text-[0.7rem] text-text-dim">{{ field.path }}</div>
                          </div>
                        </label>
                      </div>
                    </div>
                  </div>
                </div>

                <div class="rounded-lg border border-accent-primary/20 bg-accent-primary/5 p-4">
                  <div class="mb-3 flex items-center gap-2 text-sm font-bold text-accent-primary">
                    <Braces class="size-4" /> {{ t('dialog.ai_definitions.available_variables', '可用变量') }}
                  </div>
                  <div class="space-y-4">
                    <div>
                      <div class="mb-2 text-xs font-bold uppercase tracking-widest text-text-dim">{{ t('dialog.ai_definitions.base_variables', '通用变量') }}</div>
                      <div class="flex flex-wrap gap-2">
                        <button v-for="variable in baseVariables" :key="`base-${variable.key}`" :disabled="currentPromptForm.is_system" v-tooltip="getBaseVariableDescription(variable) || variable.key"
                          class="rounded-md border border-accent-primary/30 bg-bg-inset/80 px-2 py-1 text-left text-xs text-accent-primary transition-colors hover:bg-accent-primary hover:text-on-accent-primary disabled:cursor-default disabled:opacity-70 disabled:hover:bg-bg-inset/80 disabled:hover:text-accent-primary"
                          @click="insertVariable(variable.key)">
                          <div class="font-semibold">{{ getBaseVariableLabel(variable) }}</div>
                          <div class="font-mono text-[0.7rem] opacity-70">{{ '{' + variable.key + '}' }}</div>
                        </button>
                      </div>
                    </div>

                    <div v-for="attachment in selectedAttachmentDefinitions" :key="attachment.kind">
                      <div class="mb-2 text-xs font-bold uppercase tracking-widest text-text-dim">{{ attachment.label }}</div>
                      <div class="flex flex-wrap gap-2">
                        <button v-for="variable in attachment.prompt_variables" :key="`${attachment.kind}-${variable.key}`" :disabled="currentPromptForm.is_system" v-tooltip="getAttachmentVariableDescription(attachment.kind, variable) || variable.key"
                          class="rounded-md border border-accent-primary/30 bg-bg-inset/80 px-2 py-1 text-left text-xs text-accent-primary transition-colors hover:bg-accent-primary hover:text-on-accent-primary disabled:cursor-default disabled:opacity-70 disabled:hover:bg-bg-inset/80 disabled:hover:text-accent-primary"
                          @click="insertVariable(variable.key)">
                          <div class="font-semibold">{{ getAttachmentVariableLabel(attachment.kind, variable) }}</div>
                          <div class="font-mono text-[0.7rem] opacity-70">{{ '{' + variable.key + '}' }}</div>
                        </button>
                      </div>
                    </div>
                  </div>
                </div>

                <div class="space-y-2">
                  <label class="flex items-center justify-between text-xs font-bold uppercase tracking-widest text-text-dim">
                    <span class="flex items-center gap-2"><Bot class="size-4 text-accent-special" /> {{ t('dialog.ai_definitions.system_prompt_body', '系统提示词') }}</span>
                    <span class="font-mono text-[0.6rem] opacity-50">{{ t('dialog.ai_definitions.system_prompt_body_hint', '给 AI 的固定说明') }}</span>
                  </label>
                  <textarea v-model="currentPromptForm.system" :disabled="currentPromptForm.is_system" class="input-glass min-h-60 w-full resize-y p-3 font-mono text-sm leading-relaxed text-accent-cool focus:outline-none disabled:opacity-70"></textarea>
                </div>

                <div class="space-y-2">
                  <label class="flex items-center justify-between text-xs font-bold uppercase tracking-widest text-text-dim">
                    <span class="flex items-center gap-2"><User class="size-4 text-accent-primary" /> {{ t('dialog.ai_definitions.user_template', '用户输入模板') }}</span>
                    <span class="font-mono text-[0.6rem] opacity-50">{{ t('dialog.ai_definitions.user_template_hint', '每次发送时的输入格式') }}</span>
                  </label>
                  <textarea v-model="currentPromptForm.user_template" :disabled="currentPromptForm.is_system" class="input-glass min-h-60 w-full resize-y p-3 font-mono text-sm leading-relaxed text-text-main focus:outline-none disabled:opacity-70"></textarea>
                </div>
              </div>
            </template>

            <div v-else class="flex flex-1 flex-col items-center justify-center text-text-disabled">
              <TerminalSquare class="mb-4 size-16 opacity-20" />
              <p class="text-sm uppercase tracking-widest">{{ t('dialog.ai_definitions.select_left_item', '请选择左侧项目') }}</p>
            </div>
          </div>
        </div>
  </CommonModalShell>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { Bot, Braces, Drama, Lock, Paperclip, Plus, TerminalSquare, User } from 'lucide-vue-next'
import CommonModalShell from '../../shared/components/modal/CommonModalShell.vue'
import CommonInput from '../../shared/components/input/CommonInput.vue'
import CommonSelect from '../../shared/components/input/CommonSelect.vue'
import { useAppStore } from '../../app/stores/appStore'
import { useAiStore } from './aiStore'
import { useConfirmStore } from '../../shared/components/modal/confirmStore'
import { deepClone, normalizeText } from '../../shared/lib/common'
import { t } from '../../shared/i18n'

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
  'entries',
  'prompts',
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
const isLoadingDefinitions = ref(false)
const loadErrorText = ref('')

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
    label: getCategoryLabel(category),
    value: category.id,
    desc: getCategoryDescription(category),
  }))
))
const attachmentDefinitionEntries = computed(() => Object.values(definitionEditorMeta.value?.attachments || {}).sort((a, b) => String(getAttachmentLabel(a) || a.kind).localeCompare(String(getAttachmentLabel(b) || b.kind))))
const toolDefinitionEntries = computed(() => (
  Object.values(aiStore.getToolDefinitions() || {})
    .sort((a, b) => String(a.label || a.id || '').localeCompare(String(b.label || b.id || '')))
))
const getEntryTypeLabel = (entryType = '') => (entryType === 'assistant'
  ? t('dialog.ai_definitions.entry_type.assistant', '系统助手')
  : t('dialog.ai_definitions.entry_type.task', '系统任务'))
const getTabLabel = (id = '') => {
  if (id === 'entries') return t('dialog.ai_definitions.tabs.entries', '入口')
  if (id === 'prompts') return t('dialog.ai_definitions.tabs.prompts', '模板')
  return id
}

const entryList = computed(() => {
  const assistantEntries = Object.entries(assistants.value || {}).map(([id, data]) => ({
    id,
    type: 'assistant',
    name: getEntryName('assistants', id, data),
    description: getEntryDescription('assistants', id, data),
    prompt_id: data?.prompt_id || '',
    tool_scope_selectable: Array.isArray(data?.tool_scope_selectable) ? data.tool_scope_selectable : [],
    action_types: Array.isArray(data?.action_types) ? data.action_types : [],
    raw: data,
  }))
  const taskEntries = Object.entries(tasks.value || {}).map(([id, data]) => ({
    id,
    type: 'task',
    name: getEntryName('tasks', id, data),
    description: getEntryDescription('tasks', id, data),
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
  activeTab.value === 'entries'
    ? t('dialog.ai_definitions.search_entries', '搜索系统入口名称或 ID')
    : t('dialog.ai_definitions.search_prompts', '搜索模板名称或 ID')
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
    label: `${getPromptName(promptId, prompt)} (${promptId})`,
    value: promptId,
    desc: getPromptDescription(promptId, prompt),
  }))
})

const getActionDefinition = (actionType) => definitionEditorMeta.value?.actions?.[actionType] || null
const getActionLabel = (actionType) => t(`ai.actions.${actionType}.label`, getActionDefinition(actionType)?.label || actionType)
const getActionDescription = (actionType) => t(`ai.actions.${actionType}.description`, getActionDefinition(actionType)?.description || '')
const getToolTooltip = (tool = {}) => {
  const title = normalizeText(tool?.label || tool?.id, tool?.id || t('dialog.ai_definitions.tool', '工具'))
  const details = [
    normalizeText(tool?.id) ? `${t('common.id', 'ID')}: ${normalizeText(tool.id)}` : '',
    normalizeText(tool?.description),
  ].filter(Boolean)
  return details.length > 0 ? `${title}\n\n${details.join('\n')}` : title
}

const getEntryLocaleId = (group, id) => {
  const value = String(id || '')
  if (group === 'assistants' && value.startsWith('assistant.')) return value.slice('assistant.'.length)
  if (group === 'tasks' && value.startsWith('task.')) return value.slice('task.'.length)
  return value
}
const getEntryName = (group, id, data = {}) => t(`ai.definitions.${group}.${getEntryLocaleId(group, id)}.name`, data?.name || id)
const getEntryDescription = (group, id, data = {}) => t(`ai.definitions.${group}.${getEntryLocaleId(group, id)}.description`, data?.description || '')
const getPromptName = (promptId, prompt = {}) => {
  if (!prompt?.is_system) return prompt?.name || promptId || ''
  return t(`ai.prompts.${promptId}.name`, prompt?.name || promptId || '')
}
const getPromptDescription = (promptId, prompt = {}) => {
  if (!prompt?.is_system) return prompt?.description || ''
  return t(`ai.prompts.${promptId}.description`, prompt?.description || '')
}
const getCategoryLabel = (category = {}) => t(`ai.definitions.categories.${category?.id}.label`, category?.label || category?.id || '')
const getCategoryDescription = (category = {}) => t(`ai.definitions.categories.${category?.id}.description`, category?.description || '')
const getAttachmentLabel = (attachment = {}) => t(`ai.definitions.attachments.${attachment?.kind}.label`, attachment?.label || attachment?.kind || '')
const getProjectionLabel = (attachmentKind, field = {}) => t(`ai.definitions.attachments.${attachmentKind}.projection_options.${field?.path}.label`, field?.label || field?.path || '')
const getProjectionDescription = (attachmentKind, field = {}) => t(`ai.definitions.attachments.${attachmentKind}.projection_options.${field?.path}.description`, field?.description || '')
const getBaseVariableLabel = (variable = {}) => t(`ai.definitions.categories.${currentPromptForm.value?.category}.base_variables.${variable?.key}.label`, variable?.label || variable?.key || '')
const getBaseVariableDescription = (variable = {}) => t(`ai.definitions.categories.${currentPromptForm.value?.category}.base_variables.${variable?.key}.description`, variable?.description || '')
const getAttachmentVariableLabel = (attachmentKind, variable = {}) => t(`ai.definitions.attachments.${attachmentKind}.prompt_variables.${variable?.key}.label`, variable?.label || variable?.key || '')
const getAttachmentVariableDescription = (attachmentKind, variable = {}) => t(`ai.definitions.attachments.${attachmentKind}.prompt_variables.${variable?.key}.description`, variable?.description || '')

// -----------------------------------------------------------------
// 数据加载与同步 (Lifecycle / Watch)
// -----------------------------------------------------------------
const loadData = async () => {
  isLoadingDefinitions.value = true
  loadErrorText.value = ''
  try {
    const config = await aiStore.getAiConfig({ silent: true })
    if (!config) {
      loadErrorText.value = t('dialog.ai_definitions.not_ready', 'AI 定义暂时还没准备好，请稍后重试。')
      return
    }

    prompts.value = config.prompts || {}
    assistants.value = config.assistants || {}
    tasks.value = config.tasks || {}
    definitionEditorMeta.value = config.definition_editor_meta || EMPTY_PROMPT_EDITOR_META

    if (!currentEntryId.value && filteredEntries.value.length > 0) selectEntry(filteredEntries.value[0])
    if (!currentPromptId.value && sortedPromptEntries.value.length > 0) selectPrompt(sortedPromptEntries.value[0][0])
  } catch (error) {
    console.error('加载 AI 定义失败:', error)
    loadErrorText.value = t('dialog.ai_definitions.read_failed', '读取 AI 定义失败，请稍后重试。')
  } finally {
    isLoadingDefinitions.value = false
  }
}

onMounted(() => {
  loadData()
})

// -----------------------------------------------------------------
// 业务方法 (Methods)
// -----------------------------------------------------------------
const entryTooltip = (entry) => {
  const promptId = entry?.prompt_id || ''
  const promptName = getPromptName(promptId, prompts.value?.[promptId] || {}) || promptId
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
    name: t('dialog.ai_definitions.new_custom_prompt_name', '新建自定义提示词'),
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
  const ok = await confirmStore.confirmAction(
    t('dialog.ai_definitions.delete_title', '危险操作'),
    t('dialog.ai_definitions.delete_message', '确定要删除模板 {id} 吗？此操作不可逆。', { id: currentPromptId.value }),
    { type: 'error' },
  )
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
