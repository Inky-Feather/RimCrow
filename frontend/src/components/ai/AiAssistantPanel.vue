<template>
  <transition name="slide-right">
    <div v-if="modelValue" class="w-130 shrink-0 rounded-2xl bg-bg-surface/90 ring-1 ring-border-base/10 flex flex-col h-full z-40 relative shadow-2xl">
      <!-- 顶部控制栏：标题、会话统计、工具配置与关闭操作 -->
      <div class="h-14 border-b border-border-base/10 rounded-t-2xl flex items-center justify-between px-4 shrink-0 bg-bg-inset/60">
        <div class="flex items-center gap-3">
          <div class="w-7 h-7 rounded-lg bg-linear-to-br from-accent-special to-accent-primary flex items-center justify-center text-on-accent-special shadow-[0_0_10px_rgba(var(--rgb-accent-special),0.3)]">
            <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
          </div>
          <div class="flex flex-col">
            <span class="font-bold text-sm text-text-main leading-tight">{{ title }}</span>
            <div class="flex items-center gap-1.5" v-tooltip="'当前会话累计消耗的 token。数值过高时，AI 更容易忽略前面的内容。'">
              <div class="w-1.5 h-1.5 rounded-full" :class="sessionTokenIndicatorClass"></div>
              <span class="text-[0.7rem] text-text-dim font-mono">{{ sessionTokenDisplay }}</span>
            </div>
          </div>
        </div>

        <div class="flex items-center gap-1.5">
          <button class="rounded border border-border-base/10 bg-bg-overlay/5 px-2.5 py-1 text-xs transition-colors hover:border-accent-special/30 hover:text-accent-special"
            v-if="showTraceButton" @click="openTracePanel" >
            查看请求记录
          </button>
          <div class="relative group/tools">
            <button @click="showToolSelector = !showToolSelector" class="p-1.5 transition-all rounded-md relative" v-tooltip="enabledTools.length === 0 ? '当前不会调用工具，只根据现有内容回答。' : '选择本轮允许 AI 使用的工具'"
              :class="enabledTools.length === 0 ? 'text-accent-warn hover:bg-accent-warn/10' : 'text-text-dim hover:text-accent-special hover:bg-bg-overlay/5'" >
              <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" /><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" /></svg>
              <span v-if="enabledTools.length === 0" class="absolute top-1 right-1 w-1.5 h-1.5 bg-accent-warn rounded-full"></span>
            </button>

            <transition name="fade-up">
              <!-- 工具选择浮层：控制本轮请求允许使用的工具集合 -->
              <div v-if="showToolSelector" class="absolute right-0 top-full mt-2 w-64 bg-glass-heavy backdrop-blur-2xl border border-border-base/10 rounded-xl shadow-2xl z-50 overflow-hidden flex flex-col">
                <div class="px-3 py-2 border-b border-border-base/10 bg-bg-inset/80 flex items-center justify-between">
                  <span class="text-xs font-bold text-text-main">AI 可用工具</span>
                  <div class="flex gap-2">
                    <button @click="toggleAllTools(true)" class="text-[0.7rem] text-accent-special hover:text-text-inverse transition-colors">全部开启</button>
                    <button @click="toggleAllTools(false)" class="text-[0.7rem] text-text-dim hover:text-accent-warn transition-colors">关闭工具</button>
                  </div>
                </div>

                <div class="p-2 flex flex-col gap-1 max-h-100 overflow-y-auto custom-scrollbar">
                  <label v-for="tool in availableTools" :key="tool.id" class="flex items-start gap-2.5 p-2 rounded-lg hover:bg-bg-overlay/5 cursor-pointer transition-colors group">
                    <input type="checkbox" :value="tool.id" v-model="enabledTools"
                      class="mt-0.5 accent-accent-special w-3.5 h-3.5 bg-bg-inset/90 border border-border-base/18 rounded cursor-pointer" />
                    <div class="flex flex-col min-w-0">
                      <span class="text-xs font-bold transition-colors" :class="enabledTools.includes(tool.id) ? 'text-text-main' : 'text-text-disabled'">{{ tool.label || tool.id }}</span>
                      <span class="text-[0.7rem] text-text-disabled leading-tight mt-0.5 group-hover:text-text-dim transition-colors">{{ tool.description || '暂无说明' }}</span>
                    </div>
                  </label>
                </div>
              </div>
            </transition>
          </div>

          <button @click="clearChat" class="p-1.5 text-text-dim hover:text-accent-danger hover:bg-bg-overlay/5 transition-all rounded-md" v-tooltip="'清空当前会话，重新开始'">
            <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
          </button>
          <button @click="emit('update:modelValue', false)" class="p-1.5 text-text-dim hover:text-text-main hover:bg-accent-danger/25 transition-all rounded-md">
            <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" /></svg>
          </button>
        </div>
      </div>

      <!-- 会话正文区：空态、消息流、附件、工具调用与动作卡片 -->
      <div class="flex-1 overflow-y-auto p-4 flex flex-col gap-5 custom-scrollbar" ref="chatContainer">
        <div v-if="chatHistory.length === 0" class="flex flex-col items-center justify-center h-full text-center opacity-80 mt-10">
          <div class="w-16 h-16 rounded-2xl bg-linear-to-br from-accent-special/20 to-transparent flex items-center justify-center mb-4 border border-accent-special/20">
            <svg class="w-8 h-8 text-accent-special" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" /></svg>
          </div>
          <p class="text-sm font-bold text-text-main mb-2">{{ emptyTitle }}</p>
          <p class="text-xs text-text-dim max-w-65 leading-relaxed">{{ emptyDescription }}</p>
        </div>

        <div v-for="(msg, idx) in chatHistory" :key="idx" class="flex flex-col relative" :class="msg.role === 'user' ? 'items-end' : 'items-start'">
          <!-- 单条消息卡片：角色标签 + 内容主体 -->
          <div class="text-[0.7rem] text-text-dim mb-1 ml-1 mr-1 transition-opacity">
            <p :class="[msg.role === 'user' ? 'text-right' : 'text-left']">{{ msg.role === 'user' ? '你' : 'AI' }}</p>
          </div>

          <div class="max-w-[92%] w-full rounded-2xl px-3.5 py-2.5 text-sm shadow-sm group/msg relative"
              :class="msg.role === 'user' ? 'bg-bg-highlight text-text-main rounded-tr-xs' : 'bg-accent-special/15 backdrop-blur-md border border-border-base/10 text-text-main rounded-tl-xs'">
            <div v-if="hasAssistantText(msg)" class="absolute top-2 right-2 flex items-center gap-2 py-0.5 px-1.5 ring-1 ring-border-base/5 bg-bg-overlay/10 rounded-md shadow-md/20 backdrop-blur-sm opacity-0 group-hover/msg:opacity-100 text-xs transition-opacity">
              <Copy class="size-3" />
              <button @click="copyMessage(msg, false)" class="text-text-main hover:text-accent-primary transition-colors flex items-center gap-1" v-tooltip="'复制纯文本'">纯文本</button>
              /
              <button @click="copyMessage(msg, true)" class="text-text-main hover:text-accent-primary transition-colors flex items-center gap-1" v-tooltip="'复制 Markdown'">Markdown</button>
            </div>

            <div v-if="msg.attachments && msg.attachments.length > 0" class="mb-2 flex flex-wrap gap-2">
              <!-- 附件摘要：展示当前消息随附上下文 -->
              <div v-for="(attachment, attachmentIdx) in msg.attachments" :key="`${idx}-${attachmentIdx}`"
                class="flex w-fit items-center gap-2 rounded-lg border border-border-base/10 bg-bg-inset/70 p-2 text-xs opacity-90 shadow-inner backdrop-blur-sm">
                <svg class="h-3.5 w-3.5 text-accent-special" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>
                <div class="flex flex-col min-w-0">
                  <span>{{ getAttachmentDisplayMeta(attachment).summary }}</span>
                  <span v-if="getAttachmentDisplayMeta(attachment).detail" class="text-[0.7rem] text-text-dim">{{ getAttachmentDisplayMeta(attachment).detail }}</span>
                </div>
              </div>
            </div>

            <div v-if="msg.tools && msg.tools.length > 0" class="mb-3 flex flex-col gap-1.5">
              <!-- 工具调用折叠区：展示参数、摘要和结果 -->
              <div v-for="t in msg.tools" :key="t.id" class="rounded-md border border-border-base/10 bg-bg-inset/80 overflow-hidden">
                <button class="w-full flex items-center justify-between gap-2 px-2.5 py-1.5 text-xs text-left hover:bg-bg-overlay/5 transition-colors" @click="toggleToolExpanded(t)">
                  <div class="flex items-center gap-2 min-w-0">
                    <svg v-if="t.status === 'running'" class="w-3.5 h-3.5 animate-spin text-accent-special shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg>
                    <svg v-else-if="t.status === 'error'" class="w-3.5 h-3.5 text-accent-danger shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-7.938 4h15.876c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L2.34 16c-.77 1.333.192 3 1.732 3z"/></svg>
                    <svg v-else class="w-3.5 h-3.5 text-accent-success shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/></svg>
                    <div class="min-w-0">
                      <div class="text-text-dim font-mono truncate">{{ t.displayName || t.name || '系统工具' }}<span v-if="t.argumentsPreview" class="text-text-disabled"> {{ t.argumentsPreview }}</span></div>
                      <div v-if="t.summary" class="text-[0.7rem] text-text-dim truncate">{{ t.summary }}</div>
                    </div>
                  </div>
                  <div class="flex items-center gap-2 shrink-0">
                    <span v-if="t.durationMs != null" class="text-[0.7rem] text-text-disabled font-mono">{{ t.durationMs }}ms</span>
                    <svg class="w-3.5 h-3.5 text-text-dim transition-transform" :class="t.expanded ? 'rotate-180' : ''" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" /></svg>
                  </div>
                </button>
                <div v-if="t.expanded" class="px-2.5 pb-2.5 pt-1 border-t border-border-base/10 bg-bg-inset/70 space-y-2">
                  <div>
                      <div class="text-[0.7rem] text-text-dim mb-1">工具输入</div>
                    <pre class="text-[0.7rem] select-text leading-relaxed whitespace-pre-wrap break-all bg-bg-inset/80 rounded-md p-2 border border-border-base/10 text-text-soft">{{ t.argumentsPretty || t.arguments || '无输入内容' }}</pre>
                  </div>
                  <div>
                    <div class="text-[0.7rem] text-text-dim mb-1">工具结果</div>
                    <pre class="text-[0.7rem] select-text leading-relaxed whitespace-pre-wrap break-all bg-bg-inset/80 rounded-md p-2 border border-border-base/10" :class="t.status === 'error' ? 'text-accent-danger' : 'text-text-soft'">{{ t.resultPretty || t.result || '暂无结果' }}</pre>
                  </div>
                </div>
              </div>
            </div>

            <template v-if="msg.role === 'assistant'">
              <!-- 助手扩展内容：思考流、正文渲染与可执行动作 -->
              <div v-if="getAssistantWarnings(msg).length > 0" class="mb-3 flex flex-col gap-1.5">
                <div v-for="warning in getAssistantWarnings(msg)" :key="warning.code || warning.message"
                  class="flex items-start gap-2 rounded-lg border border-accent-warn/30 bg-accent-warn/10 px-3 py-2 text-xs leading-relaxed text-accent-warn">
                  <svg class="mt-0.5 h-3.5 w-3.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v3m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" /></svg>
                  <span>{{ warning.message }}</span>
                </div>
              </div>

              <details v-if="msg.reasoning" class="group/think mb-3 text-wrap break-all" :open="isThinking && msg === chatHistory[chatHistory.length - 1]">
                <summary class="flex items-center gap-2">
                  <template v-if="isThinking && msg === chatHistory[chatHistory.length - 1]">
                    <LoaderCircle class="w-3.5 h-3.5 animate-spin text-accent-special" />
                    <span class="text-accent-special animate-pulse">正在思考...</span>
                  </template>
                  <template v-else>
                    <svg class="w-3.5 h-3.5 text-text-dim" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
                    <span class="text-text-dim">思考过程</span>
                  </template>
                </summary>
                <div class="prose prose-sm prose-invert max-w-none select-text text-text-dim mt-2" v-html="renderMarkdown(msg.reasoning)"></div>
              </details>

              <div class="prose prose-sm prose-invert prose-p:my-1.5 prose-ul:my-1.5 prose-li:my-0.5 max-w-none select-text text-wrap break-all relative">
                <div v-if="shouldShowAssistantLoading(msg)" class="flex items-center gap-2 py-1 text-text-dim">
                  <LoaderCircle class="w-4 h-4 animate-spin text-accent-special shrink-0"></LoaderCircle>
                  <span class="text-xs font-mono">正在生成回答...</span>
                </div>
                <div v-else-if="hasAssistantText(msg)" v-html="renderMarkdown(msg.content)"></div>
              </div>

              <div v-if="shouldShowAssistantUsage(msg)" class="mt-3 pt-3 border-t border-border-base/10 text-[0.7rem] font-mono text-text-dim space-y-2">
                <div class="flex flex-wrap gap-5">
                  <div class="flex items-center gap-1 text-text-soft">
                    <span>消息输出 {{ formatTokenCount(getAssistantMessageTokenTotal(msg)) }} token</span>
                    <button class="text-text-dim hover:text-accent-special transition-colors" :data-no-copy="true" v-tooltip="assistantMessageUsageTooltip(msg)">
                      <CircleHelp class="w-3 h-3" />
                    </button>
                  </div>
                  <div class="flex items-center gap-1 text-text-soft">
                    <span>本轮总请求 {{ formatTokenCount(msg.tokenUsage.estimated_total_tokens || 0) }} token</span>
                    <button class="text-text-dim hover:text-accent-special transition-colors" :data-no-copy="true" v-tooltip="requestTotalUsageTooltip(msg)">
                      <CircleHelp class="w-3 h-3" />
                    </button>
                  </div>
                </div>
              </div>
            </template>

            <template v-else-if="msg.content">
              <div class="whitespace-pre-wrap select-text leading-relaxed text-sm">{{ msg.content }}</div>
              <div v-if="shouldShowUserUsage(msg)" class="mt-3 pt-3 border-t border-border-base/10 text-[0.7rem] font-mono text-text-dim">
                <div class="flex items-center gap-1 text-text-soft">
                  <span>消息输入 {{ formatTokenCount(getUserMessageTokenTotal(msg)) }} token</span>
                  <button class="text-text-dim hover:text-accent-special transition-colors" :data-no-copy="true" v-tooltip="userMessageUsageTooltip(msg)">
                    <CircleHelp class="w-3 h-3" />
                  </button>
                </div>
              </div>
            </template>

            <div v-if="getRenderableActions(msg).length > 0" class="mt-4 pt-3 border-t border-border-base/10 flex flex-col gap-2.5">
              <p class="text-xs text-text-dim font-bold flex items-center gap-1.5 mb-1">
                <svg class="w-3.5 h-3.5 text-accent-special" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
                可直接操作
              </p>
              <AiActionCard v-for="(action, aIdx) in getRenderableActions(msg)"
                :key="action._renderKey || aIdx" :action="action"
                :title="getActionTitle(action)"
                :description="getActionDescription(action)"
                :preview="getActionPreview(action)"
                :preview-parts="getActionPreviewParts(action)"
                :execute-label="getActionExecuteLabel(action)"
                :tone="getActionCardTone(action)"
                @execute="executeAction"
              />
            </div>
          </div>
        </div>
      </div>

      <!-- 底部操作栏 -->
      <div class="modal-footer z-50 shrink-0 rounded-b-2xl p-3">
        <div class="input-glass relative flex flex-col rounded-xl shadow-inner transition-all duration-300 focus-within:border-accent-special/50">
          <slot name="composer-context" :attachments="composerAttachments"></slot>

          <transition name="fade-up">
            <div v-if="composerAttachments.length > 0" class="px-3 pt-2 pb-1">
              <div class="flex flex-wrap gap-2">
                <div v-for="entry in composerAttachments" :key="entry.key" class="flex items-center gap-2 bg-accent-special/10 border border-accent-special/20 rounded-lg px-2.5 py-1.5" >
                  <svg class="w-3.5 h-3.5 text-accent-special shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" /></svg>
                  <div class="flex flex-col min-w-0">
                    <span class="text-xs text-accent-special font-bold">{{ getAttachmentDisplayMeta(entry.draft).summary }}</span>
                    <span v-if="getAttachmentDisplayMeta(entry.draft).detail" class="text-[0.7rem] text-text-dim">{{ getAttachmentDisplayMeta(entry.draft).detail }}</span>
                  </div>
                  <button @click="removeComposerAttachment(entry.key)" class="text-text-dim hover:text-accent-danger p-0.5 rounded-full bg-bg-overlay/5 transition-colors" v-tooltip="'本轮不发送这条附件'">
                    <svg class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" /></svg>
                  </button>
                </div>
              </div>
            </div>
          </transition>

          <textarea v-model="userInput" :placeholder="inputPlaceholder"
            class="w-full bg-transparent border-none py-3 px-3.5 text-sm text-text-main focus:outline-none resize-none h-14 placeholder:text-text-disabled"
            @keydown.enter.exact.prevent="sendMessage">
          </textarea>

          <div class="absolute right-2 bottom-2 flex items-center gap-2">
            <button v-if="isThinking" @click="cancelCurrentRequest()"
              class="p-1.5 rounded-lg bg-accent-danger/15 text-accent-danger hover:bg-accent-danger hover:text-text-inverse transition-all duration-300 flex items-center justify-center">
              <Square class="w-4 h-4 fill-current" />
            </button>
            <button v-else @click="sendMessage" :disabled="isSendDisabled" class="p-1.5 rounded-lg transition-all duration-300 flex items-center justify-center"
              :class="isSendDisabled ? 'text-text-disabled bg-transparent' : 'bg-linear-to-b from-accent-special to-accent-primary text-on-accent-special hover:shadow-[0_0_15px_rgba(var(--rgb-accent-special),0.5)]'">
              <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
              </svg>
            </button>
          </div>
        </div>

        <div class="mt-2 flex items-center gap-1 w-full px-1 text-xs text-text-dim">
          <CommonNumber v-model="sessionTemperature" mini :step="0.1" :min="0" :max="2" label="随机性" :description="sessionTemperatureTooltip" />
          <CommonSelect :key="`assistant-model-${globalConnectionSignature}`" mini v-model="sessionModel" :options="availableModelOptions" label="模型" :description="sessionModelTooltip" placeholder="跟随全局模型" />
          <CommonSelect mini v-model="reasoningMode" :options="reasoningOptions" label="思考模式" :description="reasoningModeTooltip" />
        </div>
      </div>
    </div>
  </transition>
</template>

<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { useToast } from 'vue-toastification'
import { useAppStore } from '../../stores/appStore'
import { useAiStore } from '../../stores/aiStore'
import { useLogStore } from '../../stores/logStore'
import { useModStore } from '../../stores/modStore'
import { useRuleStore } from '../../stores/ruleStore'
import { useConfirmStore } from '../../stores/confirmStore'
import { CircleHelp, Copy, LoaderCircle, Square } from 'lucide-vue-next'
import CommonSelect from '../common/input/CommonSelect.vue'
import CommonNumber from '../common/input/CommonNumber.vue'
import AiActionCard from './AiActionCard.vue'
import { renderMarkdownContent } from '../../utils/markdown'
import { createActionExecutorRegistry, createActionPresentationRuntime } from '../../runtime/aiActionRuntime'
import {
  buildAssistantMessageUsageTooltip,
  buildRequestTotalUsageTooltip,
  buildUserMessageUsageTooltip,
  formatTokenCount,
} from '../../runtime/aiUsageTooltips'

// -----------------------------------------------------------------
// Props / Emits
// -----------------------------------------------------------------
const props = defineProps({
  modelValue: { type: Boolean, default: false },
  assistantId: { type: String, required: true },
  ownerType: { type: String, default: 'assistant' },
  ownerKey: { type: String, required: true },
  title: { type: String, default: 'AI 助手' },
  emptyTitle: { type: String, default: '需要 AI 帮助吗？' },
  emptyDescription: { type: String, default: '输入问题后直接发送给 AI。' },
  inputPlaceholder: { type: String, default: '输入消息...' },
  sessionMeta: { type: Object, default: () => ({}) },
  requestPayload: { type: Object, default: () => ({}) },
  autoStartRequest: { type: Object, default: null },
  showTraceButton: { type: Boolean, default: true },
})

const emit = defineEmits(['update:modelValue'])

// -----------------------------------------------------------------
// Store 依赖 (Stores)
// -----------------------------------------------------------------
const appStore = useAppStore()
const aiStore = useAiStore()
const logStore = useLogStore()
const modStore = useModStore()
const ruleStore = useRuleStore()
const confirmStore = useConfirmStore()
const toast = useToast()

// -----------------------------------------------------------------
// 状态定义 (State / Refs)
// -----------------------------------------------------------------
const chatContainer = ref(null)
const showToolSelector = ref(false)
const availableModelOptions = ref([])
const reasoningCapabilities = ref({
  supports_reasoning: false,
  supports_reasoning_effort: false,
  reasoning_mode_kind: 'pending',
  reasoning_options: [
    { value: 'off', label: '关闭' },
    { value: 'auto', label: '自动' },
  ],
  default_session_reasoning_mode: 'auto',
})

// -----------------------------------------------------------------
// 计算属性与运行时映射 (Computed / Runtime)
// -----------------------------------------------------------------
const assistantToolConfig = computed(() => aiStore.getAssistantToolConfig(props.assistantId))
const allowedToolIds = computed(() => assistantToolConfig.value.allowedToolIds)
const defaultEnabledToolIds = computed(() => assistantToolConfig.value.defaultEnabledToolIds)
const getAttachmentDisplayMeta = aiStore.getAttachmentDisplayMeta
// 这里统一按助手定义裁剪工具范围，避免旧会话残留已经不允许的工具开关。
const normalizeEnabledToolIds = (value) => {
  /**
   * 把会话里勾选的工具列表裁剪到当前助手允许范围内。
   *
   * 这样即使助手定义变更、旧会话残留历史选择，也不会把已下线工具继续发给后端。
   */
  const allowedSet = new Set(allowedToolIds.value.map(item => String(item || '').trim()).filter(Boolean))
  const next = []
  for (const item of Array.isArray(value) ? value : []) {
    const toolId = String(item || '').trim()
    if (!toolId || !allowedSet.has(toolId) || next.includes(toolId)) continue
    next.push(toolId)
  }
  return next
}
const toolDefinitionMap = computed(() => (
  Object.fromEntries(
    Object.entries(aiStore.getToolDefinitions() || {}).map(([id, tool]) => [id, { id, ...tool }])
  )
))
const availableTools = computed(() => (
  Object.values(toolDefinitionMap.value)
    .filter(tool => allowedToolIds.value.includes(String(tool.id || '').trim()))
    .sort((a, b) => String(a.label || a.id || '').localeCompare(String(b.label || b.id || '')))
))
const actionPresentation = createActionPresentationRuntime({
  getActionDefinition: (actionType) => {
    const definition = aiStore.getActionDefinitions()?.[actionType] || null
    return definition ? { type: actionType, ...definition } : null
  },
  getModDisplayName: (modId) => modStore.displayModName(modId, '未知模组'),
  getModPreviewData: (modId) => modStore.takeModById(modId, '未知模组'),
})
const {
  getActionType,
  getActionVariant,
  getActionExecuteLabel,
  getActionTitle,
  getActionDescription,
  getActionPreview,
  getActionMissingPayloadMessage,
  getActionBlockedMessage,
  getActionConfirmMeta,
  getActionPostSuccessMeta,
  getActionSuccessMessage,
  getActionExecutionConfig,
  getActionPreviewParts,
  getActionCardTone,
  getRenderableActions,
} = actionPresentation

const syncBoundSession = () => aiStore.getOrCreateBoundSession(props.ownerKey, {
  assistantId: props.assistantId,
  ownerType: props.ownerType,
  ownerKey: props.ownerKey,
  title: props.title,
  sourceType: String(props.sessionMeta?.sourceType || ''),
  filename: String(props.sessionMeta?.filename || ''),
})

watch(
  [() => props.ownerKey, () => props.assistantId, () => props.title, defaultEnabledToolIds, () => props.sessionMeta?.sourceType, () => props.sessionMeta?.filename],
  () => {
    if (!props.ownerKey) return
    syncBoundSession()
  },
  { immediate: true },
)

const currentSessionId = computed(() => aiStore.getCurrentSessionIdForOwner(props.ownerKey))
const currentSession = () => aiStore.getSession(currentSessionId.value) || null
const chatHistory = computed(() => currentSession()?.messages || [])
const composerAttachments = computed(() => aiStore.getSessionComposerAttachments(currentSessionId.value, props.assistantId))
const globalAiConfig = computed(() => (
  appStore.settings?.ai
  || aiStore.runtimeAiConfig?.config
  || {}
))
const globalAiConfigSignature = computed(() => [
  String(globalAiConfig.value?.provider || '').trim(),
  String(globalAiConfig.value?.base_url || '').trim(),
  String(globalAiConfig.value?.api_key || '').trim(),
  String(globalAiConfig.value?.model || '').trim(),
  String(globalAiConfig.value?.temperature ?? '').trim(),
].join('|'))
const globalConnectionSignature = computed(() => [
  String(globalAiConfig.value?.provider || '').trim(),
  String(globalAiConfig.value?.base_url || '').trim(),
].join('|'))
const modelListQuerySignature = computed(() => [
  String(globalAiConfig.value?.provider || '').trim(),
  String(globalAiConfig.value?.base_url || '').trim(),
  String(globalAiConfig.value?.api_key || '').trim(),
].join('|'))
const runtimePrefs = computed(() => aiStore.getAssistantRuntimePrefs(props.ownerKey, {
  enabledTools: [...defaultEnabledToolIds.value],
}))

const userInput = computed({
  get: () => currentSession()?.userInput || '',
  set: (value) => {
    const session = currentSession()
    if (session) session.userInput = String(value ?? '')
  }
})
const isThinking = computed(() => !!currentSession()?.isThinking)
const sessionModel = computed({
  get: () => {
    const explicitModel = runtimePrefs.value?.modelTouched ? String(runtimePrefs.value?.model || '').trim() : ''
    if (explicitModel) return explicitModel
    return String(globalAiConfig.value?.model || '').trim()
  },
  set: (value) => {
    aiStore.updateAssistantRuntimePrefs(props.ownerKey, { model: String(value || '').trim() })
  }
})
const sessionTemperature = computed({
  get: () => {
    const explicitTemperature = runtimePrefs.value?.temperatureTouched ? runtimePrefs.value?.temperature : null
    if (explicitTemperature != null && Number.isFinite(Number(explicitTemperature))) {
      return Number(explicitTemperature)
    }
    const globalTemperature = Number(globalAiConfig.value?.temperature)
    return Number.isFinite(globalTemperature) ? globalTemperature : 0.7
  },
  set: (value) => {
    const numeric = Number(value)
    aiStore.updateAssistantRuntimePrefs(props.ownerKey, {
      temperature: Number.isFinite(numeric) ? Math.min(2, Math.max(0, numeric)) : 0.7,
    })
  }
})
const sessionModelConfig = computed(() => {
  const config = globalAiConfig.value || {}
  return {
    provider: String(config.provider || '').trim(),
    base_url: String(config.base_url || '').trim(),
    api_key: String(config.api_key || '').trim(),
    model: String(sessionModel.value || config.model || '').trim(),
    temperature: Number(sessionTemperature.value),
  }
})
const reasoningOptions = computed(() => {
  const options = Array.isArray(reasoningCapabilities.value?.reasoning_options)
    ? reasoningCapabilities.value.reasoning_options
    : []
  return options.length > 0 ? options : [{ value: 'off', label: '关闭' }]
})
const reasoningMode = computed({
  get: () => {
    const supportedValues = new Set(reasoningOptions.value.map(item => String(item?.value || '').trim().toLowerCase()))
    const currentValue = runtimePrefs.value?.reasoningModeTouched
      ? String(runtimePrefs.value?.reasoningMode || '').trim().toLowerCase()
      : ''
    if (currentValue && supportedValues.has(currentValue)) {
      return currentValue
    }
    const fallback = String(reasoningCapabilities.value?.default_session_reasoning_mode || 'off').trim().toLowerCase()
    return supportedValues.has(fallback) ? fallback : (reasoningOptions.value[0]?.value || 'off')
  },
  set: (value) => {
    aiStore.updateAssistantRuntimePrefs(props.ownerKey, {
      reasoningMode: String(value || 'off').trim().toLowerCase() || 'off',
    })
  }
})
const sessionModelTooltip = computed(() => {
  const provider = String(sessionModelConfig.value.provider || 'unknown')
  const model = String(sessionModel.value || '未选择')
  return [
    '当前助手面板临时使用的模型。',
    `服务类型 ^^${provider}^^`,
    `模型 ^^${model}^^`,
    '没有单独修改时，会沿用全局 AI 设置；新建会话后仍保留本面板的临时选择。',
  ].join('\n')
})
const sessionTemperatureTooltip = computed(() => {
  const temperature = Number(sessionTemperature.value).toFixed(1)
  return [
    '当前助手面板临时使用的输出随机性。',
    `temperature ^^${temperature}^^`,
    '值越低越稳定，适合需要精确回答的情况，值越高越发散，适合需要创意回答的情况。',
    '没有单独修改时，会沿用全局 AI 设置；新建会话后仍保留本面板的临时选择。',
  ].join('\n')
})
const reasoningModeTooltip = computed(() => {
  const kind = String(reasoningCapabilities.value?.reasoning_mode_kind || 'unsupported')
  if (kind === 'pending') {
    return [
      '正在检查当前模型支持哪些思考模式。',
      '暂时会先按“自动”处理。',
    ].join('\n')
  }
  if (kind === 'unsupported') {
    return [
      '当前模型不支持思考模式。',
      '发送时会按普通回答处理。',
    ].join('\n')
  }
  return [
    '当前助手面板临时使用的思考模式。',
    '自动：由系统按当前模型选择合适方式。',
    '如果模型支持更多等级，这里会显示对应选项。',
  ].join('\n')
})
const enabledTools = computed({
  get: () => {
    if (Array.isArray(runtimePrefs.value?.enabledTools)) {
      return normalizeEnabledToolIds(runtimePrefs.value.enabledTools)
    }
    return [...defaultEnabledToolIds.value]
  },
  set: (value) => {
    aiStore.updateAssistantRuntimePrefs(props.ownerKey, { enabledTools: normalizeEnabledToolIds(value) })
  }
})

const resetUntouchedRuntimePrefsForGlobalConfig = () => {
  const prefs = runtimePrefs.value
  if (!prefs) return
  const patch = {}
  if (!prefs.modelTouched) {
    patch.model = ''
    patch.modelTouched = false
  }
  if (!prefs.temperatureTouched) {
    patch.temperature = null
    patch.temperatureTouched = false
  }
  if (!prefs.reasoningModeTouched) {
    patch.reasoningMode = String(reasoningCapabilities.value?.default_session_reasoning_mode || 'auto').trim().toLowerCase() || 'auto'
    patch.reasoningModeTouched = false
  }
  if (!prefs.enabledToolsTouched) {
    patch.enabledTools = [...defaultEnabledToolIds.value]
    patch.enabledToolsTouched = false
  }
  if (Object.keys(patch).length > 0) {
    aiStore.updateAssistantRuntimePrefs(props.ownerKey, patch)
  }
}

const resetRuntimePrefsForConnectionSwitch = () => {
  aiStore.updateAssistantRuntimePrefs(props.ownerKey, {
    model: '',
    modelTouched: false,
    temperature: null,
    temperatureTouched: false,
    reasoningMode: 'auto',
    reasoningModeTouched: false,
    enabledTools: [...defaultEnabledToolIds.value],
    enabledToolsTouched: false,
  })
}

watch([allowedToolIds, defaultEnabledToolIds], () => {
  const prefs = runtimePrefs.value
  if (!prefs) return
  if (!prefs.enabledToolsTouched) {
    aiStore.updateAssistantRuntimePrefs(props.ownerKey, {
      enabledTools: [...defaultEnabledToolIds.value],
      enabledToolsTouched: false,
    })
    return
  }
  aiStore.updateAssistantRuntimePrefs(props.ownerKey, {
    enabledTools: normalizeEnabledToolIds(prefs.enabledTools),
    enabledToolsTouched: true,
  })
}, { immediate: true })

// -----------------------------------------------------------------
// 远程能力刷新 (Data Loading)
// -----------------------------------------------------------------
const refreshModelOptions = async ({ forceRefresh = true } = {}) => {
  /**
   * 刷新当前会话可选模型列表。
   *
   * 助手面板这里统一走后端 ai_get_models 流程，避免前端继续沿用旧协议/
   * 旧 base_url 对应的展示缓存；真正的短期缓存交给后端维护。
   */
  const config = globalAiConfig.value || {}
  if (!config?.provider) {
    availableModelOptions.value = []
    return
  }
  const query = {
    provider: config.provider,
    base_url: config.base_url,
    api_key: config.api_key,
  }
  const models = await aiStore.getAiModels(query, {
    forceRefresh,
    warnOnEmpty: false,
    silent: true,
  })
  const modelSet = new Set(
    (Array.isArray(models) ? models : [])
      .map(item => String(item || '').trim())
      .filter(Boolean)
  )
  const currentModel = String(sessionModel.value || config.model || '').trim()
  if (currentModel) {
    modelSet.add(currentModel)
  }
  availableModelOptions.value = [...modelSet]
    .sort((a, b) => a.localeCompare(b))
    .map(model => ({ label: model, value: model }))
}

const refreshReasoningCapability = () => {
  /** 根据当前模型配置刷新“思考模式”能力描述。 */
  const config = sessionModelConfig.value
  const capabilities = aiStore.resolveAiModelCapabilities(config)
  reasoningCapabilities.value = {
    supports_reasoning: !!capabilities?.supports_reasoning,
    supports_reasoning_effort: !!capabilities?.supports_reasoning_effort,
    reasoning_mode_kind: String(capabilities?.reasoning_mode_kind || 'pending'),
    reasoning_options: Array.isArray(capabilities?.reasoning_options) && capabilities.reasoning_options.length > 0
      ? capabilities.reasoning_options
      : [{ value: 'off', label: '关闭' }],
    default_session_reasoning_mode: String(capabilities?.default_session_reasoning_mode || 'auto'),
  }
}

const removeComposerAttachment = (attachmentKey) => {
  /** 从当前会话输入区移除一条附件。 */
  aiStore.removeComposerAttachment(currentSessionId.value, attachmentKey)
}

const resetChatState = () => {
  /**
   * 为当前 ownerKey 重建一条全新会话。
   *
   * 这不是简单清空消息，而是彻底更换 sessionId，避免旧请求、旧附件屏蔽态
   * 和旧 token 统计继续污染新会话。
   */
  const session = aiStore.resetBoundSession(props.ownerKey, {
    assistantId: props.assistantId,
    ownerType: props.ownerType,
    ownerKey: props.ownerKey,
    title: props.title,
    sourceType: String(props.sessionMeta?.sourceType || ''),
    filename: String(props.sessionMeta?.filename || ''),
  })
}

const clearChat = async () => {
  /** 清空当前会话；如果仍在推理，会先尝试取消当前请求。 */
  if (isThinking.value) {
    await cancelCurrentRequest({ keepBubble: false, silent: true })
  }
  resetChatState()
}

// -----------------------------------------------------------------
// 文本渲染与复制 (Rendering)
// -----------------------------------------------------------------
const stripMarkdownToPlainText = (value) => String(value ?? '')
  .replace(/\r\n/g, '\n')
  .replace(/```[\w-]*\n?/g, '')
  .replace(/```/g, '')
  .replace(/!\[([^\]]*)\]\([^)]+\)/g, '$1')
  .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
  .replace(/`([^`]+)`/g, '$1')
  .replace(/^>\s?/gm, '')
  .replace(/^#{1,6}\s*/gm, '')
  .replace(/^\s*[-*+]\s+/gm, '')
  .replace(/^\s*\d+\.\s+/gm, '')
  .replace(/\*\*([^*]+)\*\*/g, '$1')
  .replace(/\*([^*]+)\*/g, '$1')
  .replace(/__([^_]+)__/g, '$1')
  .replace(/_([^_]+)_/g, '$1')
  .replace(/\n{3,}/g, '\n\n')
  .trim()

// 模型偶尔会把结构化动作、工具标签或其他中间产物混进可见回答里。
// 这里在展示层做一次清理，保证用户看到的是最终说明文本。
const getAssistantText = (content) => {
  /** 从 assistant 消息内容里提取真正要展示的正文文本。 */
  if (content == null) return ''
  let text = String(content)
  text = text.replace(/```(?:json)?\s*(?:\{|\[)[\s\S]*?"actions"[\s\S]*?(?:```|$)/gi, '')
  text = text.replace(/<｜｜DSML｜｜tool_calls>[\s\S]*?<\/｜｜DSML｜｜tool_calls>/gi, '')
  text = text.replace(/<｜｜DSML｜｜invoke[\s\S]*?<\/｜｜DSML｜｜invoke>/gi, '')
  return text.trim()
}

const hasAssistantText = (msg) => getAssistantText(msg?.content).trim().length > 0
const getAssistantWarnings = (msg) => {
  if (!Array.isArray(msg?.warnings)) return []
  return msg.warnings
    .map((warning) => {
      if (warning && typeof warning === 'object') {
        return {
          code: String(warning.code || ''),
          message: String(warning.message || warning.detail || '').trim(),
        }
      }
      return { code: '', message: String(warning || '').trim() }
    })
    .filter(warning => warning.message)
}
const shouldShowAssistantLoading = (msg) => {
  const isLatestMessage = chatHistory.value[chatHistory.value.length - 1] === msg
  return isLatestMessage && isThinking.value && !hasAssistantText(msg)
}
const renderMarkdown = (text) => {
  /** 渲染并净化助手输出的 Markdown。 */
  return renderMarkdownContent(getAssistantText(text))
}

const copyMessage = async (msg, isMarkdown = false) => {
  /** 复制当前消息，可选保留 Markdown 或转换成纯文本。 */
  try {
    const rawText = getAssistantText(msg.content)
    const finalOutput = isMarkdown ? rawText : stripMarkdownToPlainText(rawText)
    await navigator.clipboard.writeText(finalOutput)
    toast.success(isMarkdown ? '已复制 Markdown 格式' : '已复制纯文本格式')
  } catch (err) {
    toast.error(`复制失败: ${err.message}`)
  }
}

const scrollToBottom = async (force = false) => {
  /**
   * 在用户仍停留在底部附近时自动滚动到底。
   *
   * 这样既能在流式输出时保持追随，又不会打断用户向上翻历史记录。
   */
  await nextTick()
  if (!chatContainer.value) return
  const container = chatContainer.value
  // 用户回看旧消息时不要强行抢回滚动条，只在接近底部时自动跟随。
  const isNearBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 50
  if (force || isNearBottom) {
    container.scrollTop = container.scrollHeight
  }
}

// -----------------------------------------------------------------
// 监听与自动同步 (Watchers)
// -----------------------------------------------------------------
watch(chatHistory, () => {
  scrollToBottom()
}, { deep: true })

watch(
  [() => props.autoStartRequest?.nonce, () => props.modelValue],
  async ([nonce, isOpen]) => {
    const session = currentSession()
    if (!session || !nonce || !isOpen || isThinking.value) return
    if (session.consumedAutoStartNonce === nonce) return
    session.consumedAutoStartNonce = nonce
    await clearChat()
    userInput.value = props.autoStartRequest?.question || ''
    await nextTick()
    await sendMessage()
  },
)

watch(globalAiConfigSignature, () => {
  resetUntouchedRuntimePrefsForGlobalConfig()
}, { immediate: true })

watch(globalConnectionSignature, (nextSignature, previousSignature) => {
  if (!previousSignature || nextSignature === previousSignature) return
  availableModelOptions.value = []
  resetRuntimePrefsForConnectionSwitch()
}, { immediate: true })

watch(modelListQuerySignature, () => {
  refreshModelOptions({ forceRefresh: true }).catch(() => {
    availableModelOptions.value = []
  })
}, { immediate: true })

watch(
  () => [sessionModel.value, sessionModelConfig.value?.provider, sessionModelConfig.value?.base_url],
  () => {
    refreshReasoningCapability()
  },
  { immediate: true },
)

watch(reasoningOptions, (options) => {
  const normalizedOptions = Array.isArray(options)
    ? options.map(item => String(item?.value || '').trim().toLowerCase()).filter(Boolean)
    : []
  if (normalizedOptions.length === 0) return
  const hasExplicitOverride = !!runtimePrefs.value?.reasoningModeTouched
  const currentMode = hasExplicitOverride
    ? String(runtimePrefs.value?.reasoningMode || '').trim().toLowerCase()
    : ''
  if (currentMode && normalizedOptions.includes(currentMode)) {
    return
  }
  const preferredMode = String(reasoningCapabilities.value?.default_session_reasoning_mode || normalizedOptions[0] || 'off').trim().toLowerCase()
  aiStore.updateAssistantRuntimePrefs(props.ownerKey, {
    reasoningMode: normalizedOptions.includes(preferredMode) ? preferredMode : normalizedOptions[0],
    reasoningModeTouched: hasExplicitOverride,
  })
}, { immediate: true })

const sessionUsageSummary = computed(() => currentSession()?.sessionUsageSummary || null)
const sessionTokenTotal = computed(() => {
  const summaryTotal = Number(sessionUsageSummary.value?.request_usage?.total_tokens || 0)
  if (Number.isFinite(summaryTotal) && summaryTotal > 0) {
    return summaryTotal
  }
  return chatHistory.value.reduce((total, message) => {
    const messageTokens = Number(message?.tokenUsage?.estimated_total_tokens || 0)
    return total + (Number.isFinite(messageTokens) ? messageTokens : 0)
  }, 0)
})
const sessionTokenIndicatorClass = computed(() => {
  if (sessionTokenTotal.value <= 0) {
    return isThinking.value ? 'bg-accent-warn animate-pulse' : 'bg-bg-overlay/10'
  }
  return sessionTokenTotal.value > 16000 ? 'bg-accent-danger animate-pulse' : 'bg-accent-success'
})
const sessionTokenDisplay = computed(() => {
  if (sessionTokenTotal.value <= 0) {
    return isThinking.value ? '会话总计 计算中' : '会话总计 暂无'
  }
  return `会话总计 ${(sessionTokenTotal.value / 1000).toFixed(1)}k token`
})

const getMainPromptTokenTotal = (message) => Number(message?.tokenUsage?.estimated_prompt_tokens || 0)
const getMainAssistantOutputTokenTotal = (message) => Number(message?.tokenUsage?.estimated_completion_tokens || 0)
const getUserMessageTokenTotal = (message) => {
  const mappedTotal = Number(message?.messageUsage?.user?.total_tokens || 0)
  if (mappedTotal > 0) return mappedTotal
  return getMainPromptTokenTotal(message)
}
const getAssistantMessageTokenTotal = (message) => {
  const mappedTotal = Number(message?.messageUsage?.assistant?.total_tokens || 0)
  if (mappedTotal > 0) return mappedTotal
  return getMainAssistantOutputTokenTotal(message)
}
const getReasoningTokenTotal = (message) => Number(message?.tokenUsage?.estimated_reasoning_completion_tokens || 0)
const getAnswerTokenTotal = (message) => Number(message?.tokenUsage?.estimated_answer_completion_tokens || 0)
const getToolCallTokenTotal = (message) => Number(message?.tokenUsage?.estimated_tool_call_completion_tokens || 0)
const shouldShowUserUsage = (message) => getUserMessageTokenTotal(message) > 0
const shouldShowAssistantUsage = (message) => getAssistantMessageTokenTotal(message) > 0 || Number(message?.tokenUsage?.estimated_total_tokens || 0) > 0
const userMessageUsageTooltip = (message) => buildUserMessageUsageTooltip({
  totalTokens: getUserMessageTokenTotal(message),
  promptTokens: getMainPromptTokenTotal(message),
  promptTemplateTokens: Number(message?.promptInputBreakdown?.prompt_template_tokens || 0),
  memoryTokens: Number(message?.promptInputBreakdown?.memory_tokens || 0),
  attachmentTokens: Number(message?.promptInputBreakdown?.attachment_tokens || 0),
  userInputTokens: Number(message?.promptInputBreakdown?.user_input_tokens || 0),
  toolContextTokens: Number(message?.promptInputBreakdown?.tool_context_tokens || 0),
  forcedSummaryTokens: Number(message?.promptInputBreakdown?.forced_summary_tokens || 0),
})
const requestTotalUsageTooltip = (message) => buildRequestTotalUsageTooltip({
  totalTokens: Number(message?.tokenUsage?.estimated_total_tokens || 0),
  promptTokens: getMainPromptTokenTotal(message),
  completionTokens: getMainAssistantOutputTokenTotal(message),
  toolRounds: Number(message?.tokenUsage?.tool_rounds || 0),
})
const assistantMessageUsageTooltip = (message) => buildAssistantMessageUsageTooltip({
  totalTokens: getAssistantMessageTokenTotal(message),
  completionTokens: getMainAssistantOutputTokenTotal(message),
  reasoningTokens: getReasoningTokenTotal(message),
  toolCallTokens: getToolCallTokenTotal(message),
  answerTokens: getAnswerTokenTotal(message),
})

// -----------------------------------------------------------------
// 动作执行与发送控制 (Actions / Requests)
// -----------------------------------------------------------------
const ACTION_EXECUTORS = createActionExecutorRegistry({
  modStore,
  ruleStore,
  appStore,
  confirmStore,
  toast,
  getActionVariant,
  getActionMissingPayloadMessage,
  getActionSuccessMessage,
  getActionConfirmMeta,
  getActionPostSuccessMeta,
  getActionExecutionConfig,
  getActionBlockedMessage,
  getActionPreview,
  getActionDescription,
})
const executeAction = async (action) => {
  /** 执行一条助手返回的前端动作。 */
  const executor = ACTION_EXECUTORS[getActionType(action)]
  if (!executor) {
    toast.warning(`暂不支持的操作类型: ${getActionType(action) || '未知'}`)
    return
  }
  try {
    await executor(action.payload || {}, action)
  } catch (error) {
    toast.error(`操作执行失败: ${error?.message || error}`)
  }
}

const toggleAllTools = (state) => {
  /** 一键全开或全关当前会话允许使用的工具。 */
  enabledTools.value = state ? availableTools.value.map(tool => tool.id) : []
}
const toggleToolExpanded = (tool) => {
  /** 切换单条工具调用记录的展开状态。 */
  tool.expanded = !tool.expanded
}
const isSendDisabled = computed(() => isThinking.value || (composerAttachments.value.length === 0 && userInput.value.trim() === ''))
const openTracePanel = async () => {
  /** 打开当前会话对应的请求链路面板。 */
  if (!currentSessionId.value) return
  await aiStore.openSessionTraceViewer(currentSessionId.value)
}

const sendMessage = async () => {
  /**
   * 向当前会话发送一轮用户消息。
   *
   * 这里会一起提交：
   * - 当前会话输入框文本
   * - 当前会话可见附件
   * - 当前助手组件实例的模型/温度/思考模式/工具覆写
   */
  const session = currentSession() || syncBoundSession()
  if (!session || isSendDisabled.value) return
  const questionText = userInput.value.trim()
  userInput.value = ''
  await nextTick()
  await scrollToBottom(true)
  const requestMeta = await aiStore.sendAssistantMessage({
    sessionId: session.id,
    assistantId: props.assistantId,
    ownerType: props.ownerType,
    ownerKey: props.ownerKey,
    question: questionText,
    enabledTools: enabledTools.value,
    overrideConfig: {
      model: sessionModel.value,
      temperature: Number(sessionTemperature.value),
      reasoning_mode: reasoningMode.value,
    },
    requestPayload: { ...(props.requestPayload || {}) },
  })
  if (requestMeta?.error) {
    toast.error(requestMeta.error?.message || String(requestMeta.error))
  }
}

const cancelCurrentRequest = async ({ keepBubble = true, silent = false } = {}) => {
  /**
   * 取消当前正在进行的助手请求。
   *
   * `keepBubble=true` 时会保留当前助手气泡，只在内容尾部追加“已中断”提示，
   * 这样用户还能看到 AI 已经产出的部分内容。
   */
  const session = currentSession()
  if (!session?.activeRequestId) return
  const requestId = session.activeRequestId
  const aiMessage = aiStore.findSessionMessage(session.id, { requestId, role: 'assistant' })
  // 先在当前气泡上写入中断提示，避免取消成功但界面看起来像“无响应”。
  if (keepBubble && aiMessage) {
    const currentText = getAssistantText(aiMessage.content)
    const tip = '🛑 本次分析已由用户手动中断。'
    if (!currentText && !aiMessage.reasoning && (!aiMessage.tools || aiMessage.tools.length === 0)) {
      aiMessage.content = tip
    } else if (!currentText.includes(tip)) {
      aiMessage.content = `${currentText}\n\n> ${tip}`.trim()
    }
  }
  try {
    await aiStore.cancelAssistantSession(session.id)
    if (!silent) toast.info('已请求中断本次 AI 分析')
  } catch (error) {
    if (!silent) toast.warning(`已停止等待这次回答，但取消请求没有完成: ${error?.message || error}`)
  }
}

</script>

<style scoped>
/* --- 动画 (Motion) --- */
.slide-right-enter-active, .slide-right-leave-active { transition: transform 0.4s cubic-bezier(0.16, 1, 0.3, 1); }
.slide-right-enter-from, .slide-right-leave-to { transform: translateX(100%); opacity: 0; }

.fade-up-enter-active, .fade-up-leave-active { transition: all 0.3s ease; }
.fade-up-enter-from, .fade-up-leave-to { opacity: 0; transform: translateY(10px); }

/* --- Markdown 内容 (Rich Text) --- */
:deep(.prose) { line-height: 1.6; }
:deep(.prose pre) {
  margin: 0.5rem 0;
  padding: 0.75rem;
  background-color: var(--shadow-color);
  border: 1px solid var(--color-border-subtle);
  border-radius: 0.5rem;
}
:deep(.prose code) {
  font-family: 'Fira Code', Consolas, Monaco, 'Andale Mono', 'Ubuntu Mono', monospace;
  font-size: 0.85em;
}

/* --- 思考过程折叠区 (Reasoning) --- */
:deep(details) {
  background-color: var(--shadow-color);
  border: 1px solid var(--color-border-strong);
  border-radius: 0.5rem;
  padding: 0.75rem;
  margin: 0.75rem 0;
  cursor: pointer;
  transition: all 0.2s ease;
  box-shadow: inset 0 2px 4px 0 var(--shadow-color);
}
:deep(summary) {
  font-weight: 700;
  color: var(--color-accent-special);
  outline: none;
  display: flex;
  align-items: center;
  user-select: none;
  font-size: 0.75rem;
}
:deep(summary::marker), :deep(summary::-webkit-details-marker) {
  color: var(--color-accent-special);
  margin-right: 0.5rem;
}
:deep(details[open] summary) {
  border-bottom: 1px solid var(--color-border-strong);
  padding-bottom: 0.5rem;
  margin-bottom: 0.5rem;
}
:deep(details pre) {
  background-color: transparent !important;
  border: none !important;
  padding: 0 !important;
  margin: 0 !important;
}
</style>
