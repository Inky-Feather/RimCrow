<!-- frontend/src/components/utils/AiDiagnosticSidebar.vue -->
<template>
  <transition name="slide-right">
    <div v-if="modelValue" data-tour="log-ai-sidebar" class="w-[450px] shrink-0 bg-bg-surface/90 backdrop-blur-xl border-l border-text-main/10 flex flex-col h-full z-40 relative shadow-2xl">
      
      <!-- 1. 标题栏 (增加 Token 监控仪) -->
      <div class="h-14 border-b border-white/5 flex items-center justify-between px-4 shrink-0 bg-black/40">
        <div class="flex items-center gap-3">
          <div class="w-7 h-7 rounded-lg bg-linear-to-br from-accent-special to-accent-primary flex items-center justify-center text-white shadow-[0_0_10px_rgba(139,92,246,0.3)]">
            <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
          </div>
          <div class="flex flex-col">
            <span class="font-bold text-sm text-text-main leading-tight">AI 分析</span>
            <!-- 会话记忆指示器 -->
            <div class="flex items-center gap-1.5" v-tooltip="'当前会话累积消耗的 Token，过高会导致 AI 失忆'">
              <div class="w-1.5 h-1.5 rounded-full" :class="sessionTokens > 16000 ? 'bg-accent-danger animate-pulse' : 'bg-accent-success'"></div>
              <span class="text-[10px] text-text-dim font-mono">总计: {{ (sessionTokens / 1000).toFixed(1) }}k token</span>
            </div>
          </div>
        </div>
        
        <div class="flex items-center gap-1.5">
          <!-- 工具配置下拉菜单 -->
          <div class="relative group/tools">
            <button data-tour="log-ai-tool-selector" @click="showToolSelector = !showToolSelector" 
                    class="p-1.5 transition-all rounded-md relative"
                    :class="enabledTools.length === 0 ? 'text-accent-warn hover:bg-accent-warn/10' : 'text-text-dim hover:text-accent-special hover:bg-white/5'" 
                    v-tooltip="enabledTools.length === 0 ? '纯分析模式 (不调用工具)' : '配置 AI 工具权限'">
              <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" /><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" /></svg>
              <!-- 纯分析模式红点提示 -->
              <span v-if="enabledTools.length === 0" class="absolute top-1 right-1 w-1.5 h-1.5 bg-accent-warn rounded-full"></span>
            </button>

            <!-- 弹出面板 (点击外部关闭的简易实现：失焦隐藏或依靠 click outside) -->
            <transition name="fade-up">
              <div v-if="showToolSelector" class="absolute right-0 top-full mt-2 w-64 bg-bg-surface/95 backdrop-blur-2xl border border-white/10 rounded-xl shadow-2xl z-50 overflow-hidden flex flex-col">
                
                <div class="px-3 py-2 border-b border-white/5 bg-black/40 flex items-center justify-between">
                  <span class="text-xs font-bold text-text-main">AI 工具权限</span>
                  <div class="flex gap-2">
                    <button @click="toggleAllTools(true)" class="text-[10px] text-accent-special hover:text-white transition-colors">全选</button>
                    <button @click="toggleAllTools(false)" class="text-[10px] text-text-dim hover:text-accent-warn transition-colors">纯分析</button>
                  </div>
                </div>

                <div class="p-2 flex flex-col gap-1 max-h-[300px] overflow-y-auto custom-scrollbar">
                  <label v-for="tool in availableTools" :key="tool.id" class="flex items-start gap-2.5 p-2 rounded-lg hover:bg-white/5 cursor-pointer transition-colors group">
                    <input type="checkbox" :value="tool.id" v-model="enabledTools"
                      class="mt-0.5 accent-accent-special w-3.5 h-3.5 bg-black/50 border border-white/20 rounded cursor-pointer" />
                    <div class="flex flex-col min-w-0">
                      <span class="text-xs font-bold transition-colors" :class="enabledTools.includes(tool.id) ? 'text-text-main' : 'text-text-dim/60'">{{ tool.name }}</span>
                      <span class="text-[10px] text-text-dim/50 leading-tight mt-0.5 group-hover:text-text-dim/80 transition-colors">{{ tool.desc }}</span>
                    </div>
                  </label>
                </div>

                <div v-if="enabledTools.length === 0" class="px-3 py-2 bg-accent-warn/10 border-t border-accent-warn/20">
                  <span class="text-[10px] text-accent-warn flex items-center gap-1">
                    <svg class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                    当前为纯分析模式，AI 仅依靠文本推理，不再主动查阅任何后台资料。
                  </span>
                </div>

              </div>
            </transition>
          </div>

          <button @click="clearChat" class="p-1.5 text-text-dim hover:text-accent-danger hover:bg-white/5 transition-all rounded-md" v-tooltip="'清空记忆，开启新会话'">
            <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
          </button>
          <button @click="closeSidebar" class="p-1.5 text-text-dim hover:text-white hover:bg-white/5 transition-all rounded-md">
            <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" /></svg>
          </button>
        </div>
      </div>

      <!-- 2. 聊天消息流 -->
        <div data-tour="log-ai-chat" class="flex-1 overflow-y-auto p-4 flex flex-col gap-5 custom-scrollbar" ref="chatContainer">
        
        <!-- 欢迎/引导消息 -->
        <div v-if="chatHistory.length === 0" class="flex flex-col items-center justify-center h-full text-center opacity-80 mt-10">
          <div class="w-16 h-16 rounded-2xl bg-linear-to-br from-accent-special/20 to-transparent flex items-center justify-center mb-4 border border-accent-special/20">
            <svg class="w-8 h-8 text-accent-special" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" /></svg>
          </div>
          <p class="text-sm font-bold text-white mb-2">需要排错帮助吗？</p>
          <p class="text-xs text-text-dim max-w-[260px] leading-relaxed">
            在左侧勾选日志后，可以直接发送给 AI 做分析。
          </p>
        </div>

        <!-- 消息气泡渲染 -->
        <div v-for="(msg, idx) in chatHistory" :key="idx" class="flex flex-col relative" :class="msg.role === 'user' ? 'items-end' : 'items-start'">
          
          <div class="text-[10px] text-text-dim mb-1 ml-1 mr-1 transition-opacity">
            <p :class="[msg.role === 'user' ? 'text-right' : 'text-left']">{{ msg.role === 'user' ? '你' : 'AI' }}</p>
          </div>
          
          <div class="max-w-[92%] w-full rounded-2xl px-3.5 py-2.5 text-sm shadow-sm group/msg relative"
              :class="msg.role === 'user' ? 'bg-bg-highlight text-text-main rounded-tr-xs' : 'bg-accent-special/15 backdrop-blur-md border border-white/5 text-text-main rounded-tl-xs'">
            
            <!-- 复制操作区 (仅限 AI 回复显示) -->
            <div v-if="hasAssistantText(msg)" class="absolute top-2 right-2 flex items-center gap-2 py-0.5 px-1.5 ring-1 ring-text-main/5 bg-text-dim/30 rounded-md shadow-md/20 backdrop-blur-sm opacity-0 group-hover/msg:opacity-100 text-xs transition-opacity">
              <copy class="size-3" />
              <button @click="copyMessage(msg, false)" class="text-text-main hover:text-accent-primary transition-colors flex items-center gap-1" v-tooltip="'复制纯文本'">
                纯文本
              </button>
              /
              <button @click="copyMessage(msg, true)" class="text-text-main hover:text-accent-primary transition-colors flex items-center gap-1" v-tooltip="'复制 Markdown'">
                Markdown
              </button>
            </div>

            <!-- 用户发送的附件标识 -->
            <div v-if="msg.isLogPayload" class="flex items-center gap-2 bg-black/30 rounded-lg p-2 mb-2 opacity-90 text-[11px] border border-white/10 w-fit backdrop-blur-sm shadow-inner">
              <svg class="w-3.5 h-3.5 text-accent-special" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>
              <span>附件: {{ msg.logCount === 1 && msg._hidden_context ? '日志摘要 (含'+msg.errorCount+'项异常)' : msg.logCount + ' 条日志' }}</span>
            </div>
            
            <!-- AI 调用工具状态栏 (折叠与运行态) -->
            <div v-if="msg.tools && msg.tools.length > 0" class="mb-3 flex flex-col gap-1.5">
              <div v-for="t in msg.tools" :key="t.id" class="rounded-md border border-white/5 bg-black/40 overflow-hidden">
                <button class="w-full flex items-center justify-between gap-2 px-2.5 py-1.5 text-[11px] text-left hover:bg-white/5 transition-colors"
                  @click="toggleToolExpanded(t)">
                  <div class="flex items-center gap-2 min-w-0">
                    <svg v-if="t.status === 'running'" class="w-3.5 h-3.5 animate-spin text-accent-special shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg>
                    <svg v-else-if="t.status === 'error'" class="w-3.5 h-3.5 text-accent-danger shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-7.938 4h15.876c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L2.34 16c-.77 1.333.192 3 1.732 3z"/></svg>
                    <svg v-else class="w-3.5 h-3.5 text-accent-success shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/></svg>
                    <div class="min-w-0">
                      <div class="text-text-dim/90 font-mono truncate" v-html="formatToolName(t.name, t.arguments)"></div>
                      <div v-if="t.summary" class="text-[10px] text-text-dim/70 truncate">{{ t.summary }}</div>
                    </div>
                  </div>
                  <div class="flex items-center gap-2 shrink-0">
                    <span v-if="t.durationMs != null" class="text-[10px] text-text-dim/60 font-mono">{{ t.durationMs }}ms</span>
                    <svg class="w-3.5 h-3.5 text-text-dim transition-transform" :class="t.expanded ? 'rotate-180' : ''" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" /></svg>
                  </div>
                </button>

                <div v-if="t.expanded" class="px-2.5 pb-2.5 pt-1 border-t border-white/5 bg-black/30 space-y-2">
                  <div>
                    <div class="text-[10px] text-text-dim/70 mb-1">调用参数</div>
                    <pre class="text-[10px] select-text leading-relaxed whitespace-pre-wrap break-all bg-black/40 rounded-md p-2 border border-white/5 text-text-main/90">{{ prettyToolArguments(t.arguments) }}</pre>
                  </div>
                  <div>
                    <div class="text-[10px] text-text-dim/70 mb-1">返回详情</div>
                    <pre class="text-[10px] select-text leading-relaxed whitespace-pre-wrap break-all bg-black/40 rounded-md p-2 border border-white/5" :class="t.status === 'error' ? 'text-accent-danger' : 'text-text-main/90'">{{ prettyToolResult(t.result) }}</pre>
                  </div>
                </div>
              </div>
            </div>

            <!-- 普通文本 -->
            <template v-if="msg.role === 'assistant'">
              <!-- 思考过程 -->
              <details v-if="msg.reasoning" class="group/think mb-3 text-wrap break-all" :open="isThinking && msg === chatHistory[chatHistory.length - 1]">
                <summary class="flex items-center gap-2">
                  <template v-if="isThinking && msg === chatHistory[chatHistory.length - 1]">
                    <loader-circle class="w-3.5 h-3.5 animate-spin text-accent-special" />
                    <span class="text-accent-special animate-pulse">正在深度思考...</span>
                  </template>
                  <template v-else>
                    <svg class="w-3.5 h-3.5 text-text-dim" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
                    <span class="text-text-dim">深度思考过程</span>
                  </template>
                </summary>
                <!-- 思考内容，使用稍暗的文字颜色区分 -->
                <div class="prose prose-sm prose-invert max-w-none select-text text-text-dim/80 mt-2" v-html="renderMarkdown(msg.reasoning)"></div>
              </details>
              <!-- 文本正文 (支持高级 Markdown 渲染) -->
              <div class="prose prose-sm prose-invert prose-p:my-1.5 prose-ul:my-1.5 prose-li:my-0.5 max-w-none select-text text-wrap break-all relative">
                <div v-if="shouldShowAssistantLoading(msg)" class="flex items-center gap-2 py-1 text-text-dim/80">
                  <loader-circle class="w-4 h-4 animate-spin text-accent-special shrink-0"></loader-circle>
                  <span class="text-xs font-mono">分析中...</span>
                </div>
                <div v-else-if="hasAssistantText(msg)" v-html="renderMarkdown(msg.content)"></div>
              </div>
              <div v-if="msg.tokenUsage" class="mt-3 pt-2 border-t border-white/5 text-[10px] text-text-dim/60 font-mono flex flex-wrap items-center gap-x-3 gap-y-1">
                <span>输入 {{ msg.tokenUsage.estimated_prompt_tokens || 0 }}</span>
                <span>输出 {{ msg.tokenUsage.estimated_completion_tokens || 0 }}</span>
                <span>总计 {{ msg.tokenUsage.estimated_total_tokens || 0 }}</span>
                <!-- 显示诊断调用的工具轮数 -->
                <span v-if="msg.tokenUsage.tool_rounds > 0" class="text-accent-special/80 bg-accent-special/10 px-1 rounded border border-accent-special/20">
                  历经 {{ msg.tokenUsage.tool_rounds }} 轮检测
                </span>
              </div>
            </template>
            
            <div v-else-if="msg.content" class="whitespace-pre-wrap select-text leading-relaxed text-[13.5px]">{{ msg.content }}</div>

            <!-- 【优雅的 Actionable JSON 渲染】 -->
            <div v-if="msg.actions && msg.actions.length > 0" class="mt-4 pt-3 border-t border-white/10 flex flex-col gap-2.5">
              <p class="text-[11px] text-text-dim font-bold flex items-center gap-1.5 mb-1">
                <svg class="w-3.5 h-3.5 text-accent-special" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
                AI 建议操作
              </p>
              
              <div v-for="(action, aIdx) in msg.actions" :key="aIdx" 
                  class="group/action bg-linear-to-b from-white/5 to-transparent border border-white/10 hover:border-accent-special/50 rounded-xl p-3 transition-all duration-300">
                <div class="flex items-center justify-between mb-1.5">
                  <span class="font-bold text-accent-special text-xs">{{ action.title }}</span>
                </div>
                <p class="text-[11px] text-text-dim leading-relaxed mb-3">{{ action.description }}</p>
                <button @click="executeAction(action)" 
                        class="w-full py-1.5 rounded-lg bg-accent-special/10 hover:bg-accent-special text-accent-special hover:text-white transition-all duration-300 text-xs font-bold border border-accent-special/20 hover:border-transparent flex items-center justify-center gap-1.5">
                  <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
                  {{ getActionLabel(action.type) }}
                </button>
              </div>
            </div>
          </div>
        </div>

      </div>

      <!-- 3. 输入区 -->
        <div data-tour="log-ai-input" class="p-3 bg-black/60 backdrop-blur-xl border-t border-white/5 shrink-0 z-50">
        
        <div class="relative bg-white/5 border border-white/10 rounded-xl transition-all duration-300 focus-within:border-accent-special/50 focus-within:bg-black/50 flex flex-col shadow-inner">
          
          <!-- 【核心修改】悬浮附件 (Payload Indicator) -->
          <transition name="fade-up">
            <div v-if="pendingLogs.length > 0" class="px-3 pt-2 pb-1">
              <div class="flex items-center justify-between bg-accent-special/10 border border-accent-special/20 rounded-lg px-2.5 py-1.5">
                <div class="flex items-center gap-2">
                  <svg class="w-3.5 h-3.5 text-accent-special" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" /></svg>
                  <span class="text-xs text-accent-special font-bold">附件: {{ pendingLogs[0]?.id === 'global_mock' ? '日志摘要 (含'+(tokenInfo.condensedData?.stats?.error_block_count || 0 )+'项异常)' : pendingLogs.length + ' 条日志' }}</span>
                  <span v-if="!tokenInfo.isLoading" class="text-[10px] text-text-dim ml-1">
                    (约 {{ (tokenInfo.estimated/1000).toFixed(1) }}k token)
                  </span>
                  <span v-else class="text-[10px] text-text-dim ml-1">计算中...</span>
                </div>
                <button @click="$emit('clear-selection')" class="text-text-dim hover:text-accent-danger p-0.5 rounded-full bg-white/5 transition-colors" v-tooltip="'移除附件'">
                  <svg class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" /></svg>
                </button>
              </div>
              <div v-if="tokenInfo.isOverLimit" class="text-[10px] text-accent-danger mt-1.5 pl-1 flex items-center gap-1">
                <svg class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" /></svg>
                数据过大，建议取消部分勾选。
              </div>
            </div>
          </transition>

          <textarea v-model="userInput" 
                    @keydown.enter.exact.prevent="sendMessage"
                    placeholder="输入其它要求或直接点击右下角发送分析..." 
                    class="w-full bg-transparent border-none py-3 px-3.5 text-sm text-text-main focus:outline-none resize-none h-14 custom-scrollbar placeholder:text-text-dim/40"></textarea>
          
          <div class="absolute right-2 bottom-2 flex items-center gap-2">
            <button v-if="isThinking" @click="cancelCurrentRequest()" v-tooltip="'中断当前 AI 分析'"
              class="p-1.5 rounded-lg bg-accent-danger/15 text-accent-danger hover:bg-accent-danger hover:text-white transition-all duration-300 flex items-center justify-center"
              >
              <Square class="w-4 h-4 fill-current" />
            </button>
            <button v-else data-tour="log-ai-send" @click="sendMessage" :disabled="isSendDisabled"
              class="p-1.5 rounded-lg transition-all duration-300 flex items-center justify-center"
              :class="isSendDisabled ? 'text-text-dim/30 bg-transparent' : 'bg-linear-to-b from-accent-special to-accent-primary text-white hover:shadow-[0_0_15px_rgba(139,92,246,0.5)]'"
            >
              <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
              </svg>
            </button>
          </div>

        </div>

      </div>
    </div>
  </transition>
</template>

<script setup>
import { ref, computed, nextTick, onMounted, onUnmounted, watch } from 'vue'
import { useToast } from 'vue-toastification'
import { useAppStore } from '../../stores/appStore'
import { useModStore } from '../../stores/modStore'
import { useRuleStore } from '../../stores/ruleStore'
import { useConfirmStore } from '../../stores/confirmStore'
import DOMPurify from 'dompurify'
import MarkdownIt from 'markdown-it'
import hljs from 'highlight.js'
import 'highlight.js/styles/atom-one-dark.css' // 引入酷炫的暗黑代码高亮主题
import { Copy, LoaderCircle, Square } from 'lucide-vue-next'
import { checkResult } from '../../utils/tools'

const props = defineProps({
  modelValue: { type: Boolean, default: false }, // 控制侧边栏显隐
  // 从父组件(LogViewer)直接接收处理好的状态
  pendingLogs: { type: Array, default: () => [] },
  filename: { type: String, default: '' }, // 从父组件接收文件名
  tokenInfo: { type: Object, default: () => ({ isLoading: false, condensedData: null }) },
  autoStartRequest: { type: Object, default: null }, // 父组件发来的自动诊断触发信号
  sourceType: { type: String, default: 'game' }
})
const emit = defineEmits(['update:modelValue', 'clear-selection'])

const appStore = useAppStore()
const modStore = useModStore()
const toast = useToast()

const chatContainer = ref(null)
const chatHistory = ref([])
const userInput = ref('')
const isThinking = ref(false)
const currentDiagnosisContext = ref(null)
const consumedAutoStartNonce = ref(null)

const activeSessionId = ref(null)
const abortedSessionIds = new Set()

const closeSidebar = () => emit('update:modelValue', false)

const resetChatState = () => {
  chatHistory.value = []
  userInput.value = ''
  currentDiagnosisContext.value = null
  isThinking.value = false
  activeSessionId.value = null
}
const clearChat = async () => {
  if (isThinking.value) {
    await cancelCurrentRequest({ keepBubble: false, silent: true })
  }
  resetChatState()
}

// 初始化 Markdown-it
const md = new MarkdownIt({
  html: true, // 允许渲染 <details> <summary> 等安全的 HTML
  linkify: true,
  typographer: true,
  highlight: function (str, lang) {
    if (lang && hljs.getLanguage(lang)) {
      try {
        return `<pre class="hljs p-3 rounded-lg text-xs overflow-x-auto custom-scrollbar my-2 border border-white/5 bg-black/50"><code>${hljs.highlight(str, { language: lang, ignoreIllegals: true }).value}</code></pre>`
      } catch (__) {}
    }
    return `<pre class="hljs p-3 rounded-lg text-xs overflow-x-auto custom-scrollbar my-2 border border-white/5 bg-black/50"><code>${md.utils.escapeHtml(str)}</code></pre>`
  }
})

const sanitizeRenderedHtml = (html) => DOMPurify.sanitize(html, {
  USE_PROFILES: { html: true },
  ADD_TAGS: ['details', 'summary'],
  ADD_ATTR: ['class', 'target', 'rel']
})

const sanitizeInlineHtml = (html) => DOMPurify.sanitize(html, {
  ALLOWED_TAGS: ['code'],
  ALLOWED_ATTR: ['class']
})

const escapeHtml = (value) => md.utils.escapeHtml(String(value ?? ''))
// 统一提取 AI 文本，避免对象内容被模板直接渲染成空 JSON/对象字面量
const getAssistantText = (content) => {
  if (content == null) return ''
  let text = typeof content === 'object' ? String(content.analysis || '') : String(content)
  // 【核心拦截 1】：屏蔽标准 XML 标签包裹的动作数据
  // 匹配 <actions> 到 </actions>，如果还没输出完 </actions>，就匹配到末尾 ($)
  text = text.replace(/<actions>[\s\S]*?(?:<\/actions>|$)/gi, '')
  // 【核心拦截 2】：兜底屏蔽大模型忘记写 XML，只写了 Markdown JSON 的动作数据
  // 匹配 ```json 开始，且内部包含 "actions"，直到结束或文本末尾
  text = text.replace(/```(?:json)?\s*(?:\{|\[)[\s\S]*?"actions"[\s\S]*?(?:```|$)/gi, '')
  return text.trim()
}

const hasAssistantText = (msg) => getAssistantText(msg?.content).trim().length > 0

const shouldShowAssistantLoading = (msg) => {
  // 仅让当前仍在等待结果的最后一条 AI 消息显示 loading，避免旧消息误显示占位态
  const isLatestMessage = chatHistory.value[chatHistory.value.length - 1] === msg
  return isLatestMessage && isThinking.value && !hasAssistantText(msg)
}

const renderMarkdown = (text) => {
  const content = getAssistantText(text)
  // Markdown 处理后，针对普通内联 code 进行一点样式增强
  const rendered = md.render(content).replace(/<code>/g, '<code class="bg-black/30 text-accent-special px-1.5 py-0.5 rounded text-[12px] font-mono border border-white/5">')
  return sanitizeRenderedHtml(rendered)
}

// 提供双格式复制逻
const copyMessage = async (msg, isMarkdown = false) => {
  try {
    const rawText = getAssistantText(msg.content);
    let finalOutput = rawText;

    if (!isMarkdown) {
      // 转换为纯文本：通过浏览器 DOMParser 解析渲染出的 HTML，剥离所有 Markdown 格式和标签
      const htmlString = md.render(rawText);
      const doc = new DOMParser().parseFromString(htmlString, 'text/html');
      // 为了让换行保留，我们在拿 textContent 之前，可以稍微处理下段落
      doc.querySelectorAll('p, h1, h2, h3, h4, h5, h6, li').forEach(el => {
        el.appendChild(doc.createTextNode('\n'));
      });
      finalOutput = doc.body.textContent.trim();
    }

    await navigator.clipboard.writeText(finalOutput);
    toast.success(isMarkdown ? "已复制 Markdown 格式" : "已复制纯文本格式");
  } catch (err) {
    toast.error("复制失败: " + err.message);
  }
}

// === 其余逻辑保持不变 ===
watch(() => `${props.sourceType}:${props.filename}`, (newKey, oldKey) => {
  if (oldKey !== undefined && newKey !== oldKey) { 
    clearChat(); 
    consumedAutoStartNonce.value = null 
  }
})

watch(
  [
    () => props.autoStartRequest?.nonce,
    () => props.modelValue,
    () => props.tokenInfo?.isLoading,
    () => !!props.tokenInfo?.condensedData,
  ],
  async ([nonce, isOpen, tokenLoading, hasCondensed]) => {
  // 只认 nonce，因为只要 nonce 变了，就算没有 PendingLogs 我们也强制让AI跑起来
  if (!nonce || consumedAutoStartNonce.value === nonce) return
  if (!isOpen || isThinking.value) return
  const needsAttachment = props.pendingLogs.length > 0
  if (needsAttachment && (tokenLoading || !hasCondensed)) return
  consumedAutoStartNonce.value = nonce
  clearChat()
  userInput.value = props.autoStartRequest?.question || '请深度分析我提交的日志数据，并给出修复建议。'
  await nextTick()
  await sendMessage()
})

const scrollToBottom = async (force = false) => {
  await nextTick()
  if (!chatContainer.value) return
  const container = chatContainer.value
  // 如果滚动条距离底部小于 150px，或者被强行触发 (如刚发消息时)，则执行滚动
  const isNearBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 50
  if (force || isNearBottom) {
    container.scrollTop = container.scrollHeight
  }
}
const getMessageTextForTokenEstimate = (m) => {
  if (!m) return ''
  if (m.role === 'assistant') return getAssistantText(m.content)
  return String(m.requestContent ?? m.content ?? '')
}
// 会话 Token 粗略估算 (用于 UI 顶部指示器)
// 中英文混合，1 Token 约等于 2.5 字符
const sessionTokens = computed(() => {
  // 1. 如果有来自后端的准确数据，直接信赖最后一个准确的 AI 上下文大小
  const lastAiMsg = chatHistory.value.slice().reverse().find(m => m.role === 'assistant' && m.tokenUsage?.estimated_total_tokens);
  
  let exactTokens = lastAiMsg ? Number(lastAiMsg.tokenUsage.estimated_total_tokens) : 0;

  // 2. 对于那些前端刚写入、还没发给后端的最新文字或刚挂载的全局大对象，我们需要用公式粗略补充
  let uncalculatedChars = 0;
  // 计算在 lastAiMsg 之后产生的用户消息长度
  const indexOfLastAi = lastAiMsg ? chatHistory.value.lastIndexOf(lastAiMsg) : -1
  const newMessages = chatHistory.value.slice(indexOfLastAi + 1);
  
  newMessages.forEach(m => {
    uncalculatedChars += getMessageTextForTokenEstimate(m).length
    if (m._hidden_context) {
      uncalculatedChars += JSON.stringify(m._hidden_context).length
    }
  })

  // 如果连第一句话都没发（历史还没有 AI 回复），检查当前是否挂载了附件
  if (exactTokens === 0) {
      if (props.pendingLogs.length > 0) {
          exactTokens += Number(props.tokenInfo?.estimated || 0);
      }
      exactTokens += Math.round(userInput.value.length / 2.5);
  } else {
      exactTokens += Math.round(uncalculatedChars / 2.5);
  }
  return exactTokens;
});
// 核心判断：发送按钮何时置灰
const isSendDisabled = computed(() => {
  if (isThinking.value) return true
  if (props.tokenInfo.isLoading) return true // Token 计算中不准发
  if (props.pendingLogs.length > 0 && !props.tokenInfo.condensedData) return true
  // 如果没有挂载日志附件，且没输入文字，不能发
  if (props.pendingLogs.length === 0 && userInput.value.trim() === '') return true
  return false
})
// 工具名称格式化，解析 arguments 让界面更友好
const formatToolName = (name, argsStr) => {
  let args = {}
  try { args = argsStr ? JSON.parse(argsStr) : {} } catch(e){}

  const formatLineTargets = () => {
    if (args.target_line) return `行号 #${args.target_line}`
    const lines = Array.isArray(args.target_lines) ? args.target_lines.filter(v => v != null) : []
    if (lines.length > 0) return `行号 #${lines.slice(0, 3).join(', #')}${lines.length > 3 ? '…' : ''}`
    return `未知行号`
  }
  
  switch(name) {
    case 'get_log_context':
      return sanitizeInlineHtml(`读取日志 <code>${escapeHtml(formatLineTargets())}</code>`)
    case 'search_mods':
      return sanitizeInlineHtml(`搜索已安装模组 <code>${escapeHtml(args.keyword || '')}</code>`)
    case 'get_active_mod_list':
      return `获取启用模组排序`
    case 'get_mod_info':
      return sanitizeInlineHtml(`检索模组元数据 <code>${escapeHtml(args.package_id || '')}</code>`)
    case 'get_mod_rules':
      return sanitizeInlineHtml(`读取模组规则 <code>${escapeHtml(args.package_id || '')}</code>`)
    case 'get_mod_user_context':
      return sanitizeInlineHtml(`读取用户定义信息 <code>${escapeHtml(args.package_id || '')}</code>`)
    case 'get_group_mods':
      return sanitizeInlineHtml(`读取分组成员 <code>${escapeHtml(args.group_name || '')}</code>`)
    default:
      return sanitizeInlineHtml(`调用系统工具 <code>${escapeHtml(name)}</code>`)
  }
}

const toggleToolExpanded = (tool) => {
  tool.expanded = !tool.expanded
}

const prettyToolArguments = (argsStr) => {
  if (!argsStr) return '无参数'
  try {
    return JSON.stringify(JSON.parse(argsStr), null, 2)
  } catch (e) {
    return String(argsStr)
  }
}

const prettyToolResult = (result) => {
  if (!result) return '暂无结果'
  try {
    return JSON.stringify(JSON.parse(result), null, 2)
  } catch (e) {
    return String(result)
  }
}

// ====== 新增：生命周期监听后端流事件 ======
const handleStream = (e) => {
  const { session_id, type, chunk } = e.detail || {}
  if (!session_id || abortedSessionIds.has(session_id)) return
  const msg = chatHistory.value.find(m => m.session_id === session_id)
  if (msg) {
    if (type === 'reasoning') {
      msg.reasoning = (msg.reasoning || '') + chunk
    } else {
      if (typeof msg.content === 'object') {
        msg.content.analysis = (msg.content.analysis || '') + chunk
      } else {
        msg.content = String(msg.content || '') + chunk
      }
    }
    scrollToBottom()
  }
}

const handleToolCall = (e) => {
  const { session_id, tool_id, name, arguments: args } = e.detail || {}
  if (!session_id || abortedSessionIds.has(session_id)) return
  const msg = chatHistory.value.find(m => m.session_id === session_id)
  if (msg) {
    if (!msg.tools) msg.tools = []
    msg.tools.push({
      id: tool_id,
      name,
      arguments: args,
      status: 'running',
      summary: '',
      result: '',
      durationMs: null,
      expanded: false
    })
    scrollToBottom()
  }
}

const handleToolResult = (e) => {
  const { session_id, tool_id, status, summary, result, duration_ms } = e.detail || {}
  if (!session_id || abortedSessionIds.has(session_id)) return
  const msg = chatHistory.value.find(m => m.session_id === session_id)
  if (msg && msg.tools) {
    const tool = msg.tools.find(t => t.id === tool_id)
    if (tool) {
      tool.status = status || 'done'
      tool.summary = summary || ''
      tool.result = result || ''
      tool.durationMs = duration_ms ?? null
    }
    scrollToBottom()
  }
}

onMounted(() => {
  window.addEventListener('ai-chat-stream', handleStream)
  window.addEventListener('ai-tool-call', handleToolCall)
  window.addEventListener('ai-tool-result', handleToolResult)
  window.addEventListener('ai-chat-cancelled', handleCancelled)
  document.addEventListener('click', closeToolSelector)
})
onUnmounted(() => {
  if (activeSessionId.value && window.pywebview?.api?.cancel_ai_diagnostic) {
    window.pywebview.api.cancel_ai_diagnostic(activeSessionId.value).catch(() => {})
  }
  window.removeEventListener('ai-chat-stream', handleStream)
  window.removeEventListener('ai-tool-call', handleToolCall)
  window.removeEventListener('ai-tool-result', handleToolResult)
  window.removeEventListener('ai-chat-cancelled', handleCancelled)
  document.removeEventListener('click', closeToolSelector)
})


// ================== 发送与处理逻辑 ==================

// 发送选中日志
const sendMessage = async () => {
  if (isSendDisabled.value || !window.pywebview) return
  isThinking.value = true

  let questionText = userInput.value.trim()
  const hasAttachment = props.pendingLogs.length > 0 && props.tokenInfo.condensedData
  const shouldKeepAttachment = hasAttachment && props.pendingLogs.some(log => log.id === 'global_mock')
  
  // 如果用户啥都没写，但是有日志附件，就补一个默认提示词
  if (hasAttachment && questionText === '') {
    questionText = "请深度分析我提交的日志数据，并给出修复建议。"
  }

  const displayQuestionText = questionText === '请深度分析我提交的日志数据，并给出修复建议。' ? '' : questionText

  // 1. 生成会话 ID 绑定流
  const sessionId = `chat_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`
  activeSessionId.value = sessionId
  abortedSessionIds.delete(sessionId)

  // 2. 将数据推入本地聊天气泡以供展示
  chatHistory.value.push({ 
    role: 'user', 
    content: displayQuestionText,
    requestContent: questionText,
    isLogPayload: hasAttachment,
    logCount: props.pendingLogs.length,
    errorCount: (props.tokenInfo.condensedData?.stats?.error_block_count || 0),
    _hidden_context: hasAttachment ? props.tokenInfo.condensedData : null
  })
  if (hasAttachment) {
    currentDiagnosisContext.value = props.tokenInfo.condensedData
  }

  // 构造发给后端的 history；诊断上下文走独立字段，避免逐轮塞回历史
  const historyForBackend = chatHistory.value.map(m => {
    let finalContent = m.role === 'user' ? (m.requestContent ?? m.content ?? "") : (m.content || "")
    if (m.role === 'assistant') {
      if (typeof finalContent === 'object') {
        finalContent = finalContent.analysis || ""
      }
      // 匹配已经被前端转化为折叠面板的 <details> 思考内容
      finalContent = finalContent.replace(/<details(?: open)?>\s*<summary>.*?深度思考.*?<\/summary>[\s\S]*?<\/details>/gi, '')
    }
    return { role: m.role, content: finalContent.trim() }
  })

  // 移除最后一条刚才 push 的 user 消息，因为它等下会被包含在 historyForBackend 中
  // 但为了不让 historyForBackend 最后一项变成 user 导致对话错乱，其实我们可以直接传
  // 但是后端的逻辑是把 question 独立处理，所以我们把最后一项 pop 出来
  const lastUserMsg = historyForBackend.pop()

  const requestPayload = {
    session_id: sessionId,
    log_source_type: props.sourceType, // 【修复 1】传入正确的源类型
    filename: props.filename,          // 【修复 1】传入文件名
    diagnosis_context: currentDiagnosisContext.value,
    history: historyForBackend,        // 带有完整记忆的历史
    question: lastUserMsg.content,      // 组装好的当前问题（含隐藏附件）
    enabled_tools: enabledTools.value // 【新增】告诉后端启用了哪些工具
  }

  const aiMsg = {
    role: 'assistant',
    session_id: sessionId,
    tools: [],
    content: { analysis: '', actions: [] },
    reasoning: '', // 思考过程
    actions: [],   // 动作
    tokenUsage: null
  }
  chatHistory.value.push(aiMsg)
  userInput.value = ''

  if (hasAttachment && !shouldKeepAttachment) {
    emit('clear-selection')
  }

  await nextTick()
  scrollToBottom()
  try {
    const res = await window.pywebview.api.ai_diagnostic_chat(requestPayload)
    if (abortedSessionIds.has(sessionId)) return
    if (checkResult(res,'AI请求')) {
      if (res.data?.cancelled) {
        if (typeof aiMsg.content === 'object' && !getAssistantText(aiMsg.content)) {
          aiMsg.content.analysis = '🛑 本次分析已中断。'
        }
        return
      }
      aiMsg.actions = res.data.actions || res.data.solutions || []
      aiMsg.tokenUsage = res.data.token_usage || null
      if (typeof aiMsg.content === 'object') {
        aiMsg.content.analysis = String(res.data.analysis || '')
      }
    } else {
      throw new Error(res.message)
    }
  } catch(e) {
    if (abortedSessionIds.has(sessionId)) return
    aiMsg.content.analysis += `\n\n⚠️ 分析过程中发生错误: ${e.message}`
  } finally {
    if (activeSessionId.value === sessionId) {
      activeSessionId.value = null
    }
    if (!abortedSessionIds.has(sessionId)) {
      isThinking.value = false
    }
    scrollToBottom()
  }
}

// 可用工具注册表
const availableTools =[
  { id: 'get_log_context', name: '日志追溯', desc: '反查原始日志堆栈详情' },
  { id: 'search_mods', name: '模糊搜索', desc: '根据名称或作者搜查包名' },
  { id: 'get_mod_info', name: '模组元数据', desc: '读取模组的版本、状态等属性' },
  { id: 'get_mod_rules', name: '排序规则', desc: '核对依赖与不兼容规则' },
  { id: 'get_mod_user_context', name: '用户自定义信息', desc: '读取自定义备注与分组' },
  { id: 'get_active_mod_list', name: '活动列表', desc: '检查整体加载顺序' },
  { id: 'get_group_mods', name: '分组检索', desc: '读取分组成员与相关模组' },
]
// 读取本地缓存，初始化选中的工具
const showToolSelector = ref(false)
const loadEnabledTools = () => {
  try {
    const raw = localStorage.getItem('ai_enabled_tools')
    const parsed = raw ? JSON.parse(raw) : null
    return Array.isArray(parsed) ? parsed : availableTools.map(t => t.id)
  } catch {
    return availableTools.map(t => t.id)
  }
}
const enabledTools = ref(loadEnabledTools())

// 监听器：用户更改配置后实时存入本地
watch(enabledTools, (newVal) => {
  localStorage.setItem('ai_enabled_tools', JSON.stringify(newVal))
}, { deep: true })

// 快速全选/全不选工具
const toggleAllTools = (state) => {
  enabledTools.value = state ? availableTools.map(t => t.id) :[]
}
const closeToolSelector = (e) => {
  const target = e?.target
  if (!(target instanceof Element)) return
  if (showToolSelector.value && !target.closest('.group\\/tools')) {
    showToolSelector.value = false
  }
}
// ================== 动作执行 (Actionable JSON) ==================

const getActionLabel = (type) => {
  switch (type) {
    case 'ENABLE_MOD': return '一键启用 Mod'
    case 'DISABLE_MOD': return '一键停用 Mod'
    case 'ADD_RULE': return '应用排序规则'
    case 'REPORT_BUG': return '复制反馈模板'
    default: return '执行操作'
  }
}

const executeAction = async (action) => {
  const payload = action.payload || {}
  
  try {
    switch (action.action || action.type) {
      case 'ENABLE_MOD':
        // 兼容单数与复数参数
        const enableIds = payload.mod_ids || (payload.mod_id ? [payload.mod_id] :[])
        if (enableIds.length > 0) {
          modStore.changeModsActive(enableIds, true)
          toast.success(`已启用: ${enableIds.join(', ')}`)
        }
        break;

      case 'DISABLE_MOD':
        const disableIds = payload.mod_ids || (payload.mod_id ? [payload.mod_id] :[])
        if (disableIds.length > 0) {
          modStore.changeModsActive(disableIds, false)
          toast.success(`已停用选中 Mod`)
        }
        break;
        
      case 'ADD_RULE':
        // 调用 ruleStore 写入用户规则
        const ruleStore = useRuleStore()
        {
          const rawType = String(payload.rule_type || 'loadAfter')
          const typeMap = {
            load_after: 'loadAfter',
            loadAfter: 'loadAfter',
            load_before: 'loadBefore',
            loadBefore: 'loadBefore',
            incompatible: 'incompatibleWith',
            incompatibleWith: 'incompatibleWith',
          }
          const normalizedType = typeMap[rawType] || 'loadAfter'
          await ruleStore.addUserModRule(payload.mod_id, normalizedType, payload.target_id)
        }
        
        // 询问用户是否立刻重新排序
        const confirmStore = useConfirmStore()
        if (await confirmStore.confirmAction('规则已应用', '是否立即重新执行自动排序以使规则生效？', {type: 'success'})) {
          await modStore.autoSortMods()
        }
        break;
        
      case 'REPORT_BUG':
        if (payload.report_text) {
          await navigator.clipboard.writeText(payload.report_text)
          toast.success("反馈模板已复制到剪贴板")
        }
        break;
        
      default:
        toast.warning(`暂不支持的操作类型: ${action.type}`)
    }
  } catch (e) {
    toast.error(`操作执行失败: ${e.message}`)
  }
}
const handleCancelled = (e) => {
  const { session_id } = e.detail || {}
  if (!session_id) return
  abortedSessionIds.add(session_id)
  if (activeSessionId.value === session_id) {
    activeSessionId.value = null
    isThinking.value = false
  }
}
const cancelCurrentRequest = async ({ keepBubble = true, silent = false } = {}) => {
  const sessionId = activeSessionId.value
  if (!sessionId) return
  abortedSessionIds.add(sessionId)
  activeSessionId.value = null
  isThinking.value = false
  const aiMsg = chatHistory.value.find(m => m.session_id === sessionId)
  if (keepBubble && aiMsg && typeof aiMsg.content === 'object') {
    const currentText = getAssistantText(aiMsg.content)
    const tip = '🛑 本次分析已由用户手动中断。'
    if (!currentText && !aiMsg.reasoning && (!aiMsg.tools || aiMsg.tools.length === 0)) {
      aiMsg.content.analysis = tip
    } else if (!currentText.includes(tip)) {
      aiMsg.content.analysis = `${currentText}\n\n> ${tip}`.trim()
    }
  }
  try {
    if (window.pywebview?.api?.cancel_ai_diagnostic) {
      await window.pywebview.api.cancel_ai_diagnostic(sessionId)
    }
    if (!silent) toast.info('已请求中断本次 AI 分析')
  } catch (e) {
    if (!silent) toast.warning(`已在前端停止等待，但后端取消通知失败: ${e.message || e}`)
  }
  scrollToBottom()
}

</script>

<style scoped>
.slide-right-enter-active, .slide-right-leave-active { transition: transform 0.4s cubic-bezier(0.16, 1, 0.3, 1); }
.slide-right-enter-from, .slide-right-leave-to { transform: translateX(100%); opacity: 0; }

.fade-up-enter-active, .fade-up-leave-active { transition: all 0.3s ease; }
.fade-up-enter-from, .fade-up-leave-to { opacity: 0; transform: translateY(10px); }

/* 代码块外层的自适应 */
:deep(.prose) {
  line-height: 1.6;
}
:deep(.prose pre) {
  margin: 0.5rem 0;
  padding: 0.75rem;
  background-color: rgba(0, 0, 0, 0.4);
  border: 1px solid rgba(255, 255, 255, 0.05);
  border-radius: 0.5rem;
}
:deep(.prose code) {
  font-family: 'Fira Code', Consolas, Monaco, 'Andale Mono', 'Ubuntu Mono', monospace;
  font-size: 0.85em;
}
/* === 美化 details 展开面板，适用于后端的错误兜底和 AI <think> 过程 === */
:deep(details) {
  background-color: rgba(0, 0, 0, 0.4);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 0.5rem;
  padding: 0.75rem;
  margin: 0.75rem 0;
  cursor: pointer;
  transition: all 0.2s ease;
  box-shadow: inset 0 2px 4px 0 rgba(0, 0, 0, 0.05);
}

:deep(summary) {
  font-weight: 700;
  color: var(--color-accent-special, #b92a0a); /* 带有兜底色的紫紫色 */
  outline: none;
  display: flex;
  align-items: center;
  user-select: none;
  font-size: 0.75rem;
}

:deep(summary::marker), :deep(summary::-webkit-details-marker) {
  color: var(--color-accent-special, #b92a0a);
  margin-right: 0.5rem;
}

:deep(details[open] summary) {
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
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
