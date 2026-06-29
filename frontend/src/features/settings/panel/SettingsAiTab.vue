<template>
              <section data-tour="settings-ai-section" class="animate-in fade-in slide-in-from-right-4">
                <div class="mb-6 flex items-center justify-between">
                  <h3 class="text-lg font-bold text-text-main flex items-center gap-2">
                    人工智能
                    <span class="px-2 py-0.5 rounded bg-accent-special/20 text-accent-special text-xs font-black uppercase">实验性</span>
                  </h3>

                  <button v-if="formData.ai.enabled" @click="appStore.uiState.showAIDefinitionManager = true"
                    class="px-4 py-1.5 rounded-lg bg-accent-special/10 hover:bg-accent-special/20 text-accent-special border border-accent-special/30 text-xs font-bold transition-colors flex items-center gap-2">
                    <Drama class="size-4" /> AI 定义管理
                  </button>
                </div>
                <div class="space-y-6">
                  <div data-tour="settings-ai-enable">
                    <CommonSwitch label="启用 AI 功能" v-model="formData.ai.enabled" description="用于日志分析、模组说明和 AI 助手对话等功能。" />
                  </div>
                  <div v-if="formData.ai.enabled" class="space-y-6 animate-in slide-in-from-top-2">
                      
                    <!-- 2. 动态表单区 -->
                    <div data-tour="settings-ai-connection" class="p-4 rounded-xl bg-bg-overlay/5 border border-border-base/10 space-y-5">
                      <div class="grid grid-cols-2 gap-3">
                        <!-- 厂商/协议选择 -->
                        <CommonSelect label="接口协议" description="大多数中转服务、本地运行时、国产模型平台都优先兼容 OpenAI-compatible 接口。只有目标服务没有稳定的 OpenAI-compatible API 时，才建议切换到原生协议。"
                          v-model="formData.ai.provider" :options="currentAiProviders" @change="handleProviderChange"/>
                        <!-- 模型选择 (带刷新动作) -->
                        <div class="relative flex items-end gap-2">
                          <div class="flex-1">
                            <!-- 加上 editable 允许用户手输未被探测到的模型名 -->
                            <CommonSelect label="模型" editable v-model="formData.ai.model" :options="currentAiModels" 
                              placeholder="下拉选择或手动输入模型名称" @visible-change="(val) => val && fetchAiModels({ silent: true })"/>
                          </div>
                          <!-- 对于自定义模式，提供显式的刷新按钮让用户主动拉取 -->
                          <button @click="fetchAiModels({ forceRefresh: true, warnOnEmpty: true, silent: false })" v-tooltip="'重新获取模型列表'"
                            class="h-9 px-3 bg-bg-inset/70 hover:bg-accent-special/20 text-accent-special border border-accent-special/30 rounded-lg flex items-center justify-center transition-colors">
                            <svg class="size-4" :class="{'animate-spin': aiStore.isLoading}" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/><path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16"/><path d="M16 21v-5h5"/></svg>
                          </button>
                        </div>

                        <!-- Base URL (自定义必填，官方高级选填) -->
                        <CommonInput label="Base URL" v-model="formData.ai.base_url" class="col-span-2"
                          placeholder="留空使用协议默认地址；也可填写 http://127.0.0.1:11434 或 https://api.deepseek.com/v1"
                          description="留空时使用当前协议的默认地址。Ollama 默认连接本机 127.0.0.1:11434；中转服务或非默认本地地址需要手动填写。"
                        />
                        <!-- API Key -->
                        <CommonSecretInput label="API Key" v-model="formData.ai.api_key" class="col-span-2"
                          secret-key="ai.api_key" :secret-status="aiSecretStatus" :preserved="isSecretPreserved('ai.api_key')" :reveal-secret="revealSecret"
                          placeholder="接口需要时填写 API Key；本地部署通常可以留空。"
                          @preserve="$emit('preserve-secret', $event)" @clear="$emit('clear-secret', $event)"
                        />
                      </div>

                    </div>

                    <!-- 3. 测试与高级参数区 -->
                    <div data-tour="settings-ai-advanced" class="">
                      <div class="grid grid-cols-3 gap-2">
                        <CommonNumber label="最大并发数" v-model="formData.ai.max_concurrency" :step="1" :min="1" :max="100" description="同时发出的请求数量。大多数情况下设为 3 到 5 就够了。" />
                        <CommonNumber label="输出随机性" v-model="formData.ai.temperature" :step="0.1" :min="0" :max="2.0" description="值越低越稳定，值越高越发散。一般用 0.7 左右即可。" />
                        <CommonNumber label="上下文窗口" v-model="formData.ai.context_window_tokens" :step="1024" :min="0"
                          description="模型总上下文窗口。0 表示按模型名自动预设；本地模型如果服务端限制了上下文，建议填实际值。" />
                        <CommonNumber label="最大输入预算" v-model="formData.ai.max_input_tokens" :step="1024" :min="0"
                          description="日志、附件、批量任务最多喂给模型的输入预算。0 表示自动按上下文窗口扣除输出预算。" />
                        <CommonNumber label="最大输出预算" v-model="formData.ai.max_output_tokens" :step="512" :min="0"
                          description="单次回复的输出保护阀。0 表示按模型预设自动控制；只有排查成本、延迟或长回复截断时才需要手动设置。" />
                        <CommonSelect v-if="formData.ai.provider === 'openai_compatible'"
                          label="接口模式" v-model="formData.ai.endpoint_mode"
                          description="用于指定 OpenAI-compatible 接口应走哪一类 endpoint。`Auto` 会根据模型能力和请求结构自动选择更稳妥的路径；只有在排查特定中转服务或本地运行时兼容问题时，才建议手动切换。"
                          :options="[
                            { label: 'Auto', value: 'auto' },
                            { label: 'Chat Completions API', value: 'chat_completions' },
                            { label: 'Responses API', value: 'responses' }
                          ]" />
                      </div>

                      <!-- 测试区 -->
                      <div data-tour="settings-ai-test" class="pt-4 flex gap-3">
                        <CommonInput label="测试内容" class="flex-1" v-model="testPrompt" placeholder="输入一句简单的话测试连接，例如：你好" @keydown.enter="testModel"></CommonInput>
                        <button class="mt-[1.3rem] flex items-center justify-center bg-accent-special/70 hover:bg-accent-special hover:text-text-main text-text-dim px-6 py-2 rounded-lg font-bold transition-all" 
                          :class="[aiStore.isLoading?'cursor-not-allowed pointer-events-none opacity-50':'cursor-pointer']"
                          @click="testModel">
                          <svg v-if="aiStore.isLoading" class="animate-spin size-4 mr-2" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>
                          发起测试
                        </button>
                      </div>

                      <div v-if="testResponse" class="p-4 mt-2 rounded-xl text-text-soft bg-accent-special/10 border border-border-base/10 relative">
                        <button @click="clearTestResult" class="absolute top-2 right-2 text-text-dim hover:text-text-main">×</button>
                        <div class="text-xs text-text-dim mb-1 font-bold">AI 响应结果：</div>
                        <div class="text-sm whitespace-pre-wrap leading-relaxed">{{ testResponse }}</div>
                        <details v-if="testRawResponse" class="modal-section-subtle mt-3 p-3 text-xs text-text-dim">
                          <summary class="cursor-pointer font-bold text-text-main">查看原始返回内容</summary>
                          <pre class="mt-2 whitespace-pre-wrap break-all rounded-lg border border-border-base/10 bg-bg-inset/70 p-3 text-xs text-text-main">{{ prettyTestRawResponse }}</pre>
                        </details>
                      </div>

                    </div>
                  </div>
                </div>
              </section>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { Drama } from 'lucide-vue-next'
import CommonSwitch from '../../../shared/components/input/CommonSwitch.vue'
import CommonInput from '../../../shared/components/input/CommonInput.vue'
import CommonSecretInput from '../../../shared/components/input/CommonSecretInput.vue'
import CommonNumber from '../../../shared/components/input/CommonNumber.vue'
import CommonSelect from '../../../shared/components/input/CommonSelect.vue'
import { toast, toUserMessage } from '../../../shared/lib/common'
import { useAppStore } from '../../../app/stores/appStore'
import { useAiStore } from '../../ai/aiStore'

const props = defineProps({
  formData: { type: Object, required: true },
  revealSecret: { type: Function, default: null },
  isSecretPreserved: { type: Function, default: () => false },
})

defineEmits(['preserve-secret', 'clear-secret'])

const appStore = useAppStore()
const aiStore = useAiStore()

const testPrompt = ref('介绍一下自己')
const testResponse = ref('')
const testRawResponse = ref(null)

// 每个协议保留一份连接草稿，用户来回切换协议时不会丢失已填写的 URL、Key 和模型名。
const aiProviderDrafts = ref({})
const activeAiProvider = ref('')

const DEFAULT_AI_BASE_URLS = {
  openai_compatible: 'https://api.openai.com/v1',
  anthropic: 'https://api.anthropic.com',
  gemini: 'https://generativelanguage.googleapis.com',
  ollama: 'http://127.0.0.1:11434',
}

const currentAiProviders = computed(() => aiStore.listAiProviders())
const aiSecretStatus = computed(() => props.formData?._secret_status?.['ai.api_key'] || {})
const aiModelQuery = computed(() => ({
  ...(props.formData?.ai || {}),
  api_key_fingerprint: props.formData?.ai?.api_key ? '' : (aiSecretStatus.value?.hint || ''),
}))
const currentAiModels = computed(() => aiStore.getCachedAiModelOptions(aiModelQuery.value))

// 原始响应可能是对象或字符串，统一转成可读文本，便于排查模型兼容问题。
const prettyTestRawResponse = computed(() => {
  if (testRawResponse.value == null) return ''
  try {
    return JSON.stringify(testRawResponse.value, null, 2)
  } catch {
    return String(testRawResponse.value)
  }
})

const normalizeAiProvider = (provider = '') => {
  const normalized = String(provider || '').trim().toLowerCase()
  if (['openai', 'custom_openai'].includes(normalized)) return 'openai_compatible'
  return normalized || 'openai_compatible'
}

// 协议名作为草稿 key，避免 OpenAI-compatible 的历史别名生成多份重复草稿。
const createAiProviderDraft = (ai = {}, providerOverride = undefined) => ({
  provider: normalizeAiProvider(providerOverride ?? ai.provider),
  base_url: String(ai.base_url || '').trim(),
  api_key: String(ai.api_key || '').trim(),
  model: String(ai.model || '').trim(),
  endpoint_mode: String(ai.endpoint_mode || 'auto').trim().toLowerCase() || 'auto',
})

const syncAiProviderDraft = (provider = activeAiProvider.value) => {
  const ai = props.formData?.ai
  if (!ai) return
  const normalizedProvider = normalizeAiProvider(provider || ai.provider)
  aiProviderDrafts.value[normalizedProvider] = createAiProviderDraft(ai, normalizedProvider)
}

const hydrateAiProviderDrafts = () => {
  const ai = props.formData?.ai
  if (!ai) return
  const provider = normalizeAiProvider(ai.provider)
  activeAiProvider.value = provider
  aiProviderDrafts.value = {
    [provider]: createAiProviderDraft(ai, provider),
  }
}

const applyAiDraftForProvider = (provider) => {
  const ai = props.formData?.ai
  if (!ai) return
  const normalizedProvider = normalizeAiProvider(provider)
  const hasDraft = Object.prototype.hasOwnProperty.call(aiProviderDrafts.value, normalizedProvider)
  const draft = hasDraft ? aiProviderDrafts.value[normalizedProvider] : null
  // 没有历史草稿时填入协议默认地址，让新协议切换后能直接看到合理的连接起点。
  ai.provider = normalizedProvider
  ai.base_url = draft ? String(draft.base_url || '') : (DEFAULT_AI_BASE_URLS[normalizedProvider] || '')
  ai.api_key = draft ? String(draft.api_key || '') : ''
  ai.model = draft ? String(draft.model || '') : ''
  ai.endpoint_mode = draft ? (String(draft.endpoint_mode || 'auto').trim().toLowerCase() || 'auto') : 'auto'
  activeAiProvider.value = normalizedProvider
}

const clearTestResult = () => {
  testResponse.value = ''
  testRawResponse.value = null
}

const testModel = async () => {
  clearTestResult()
  const res = await aiStore.chatWithAI(testPrompt.value, props.formData.ai)
  testRawResponse.value = res?.raw ?? null
  if (res?.ok) {
    testResponse.value = res.text
    toast.success('模型测试成功')
    return
  }
  if (res?.isEmpty) {
    testResponse.value = '模型已返回，但内容为空。可尝试切换模型、检查代理兼容策略或改用正式助手会话测试。'
    toast.warning('模型返回了空内容')
    return
  }
  testResponse.value = toUserMessage(res?.error, '模型测试失败。请检查模型配置、网络连接、代理设置和 API Key 是否可用。')
  toast.error(testResponse.value)
}

// CommonSelect 会先更新 v-model 再触发 change，因此这里显式保存“上一个协议”的草稿。
const handleProviderChange = (selectedProvider) => {
  const previousProvider = activeAiProvider.value || normalizeAiProvider(props.formData?.ai?.provider)
  syncAiProviderDraft(previousProvider)
  const nextProvider = normalizeAiProvider(selectedProvider?.value ?? selectedProvider ?? props.formData?.ai?.provider)
  applyAiDraftForProvider(nextProvider)
}

const fetchAiModels = async ({ forceRefresh = false, warnOnEmpty = false, silent = true } = {}) => {
  const ai = props.formData?.ai
  if (!ai?.provider || !ai.enabled) return
  await aiStore.getAiModels(aiModelQuery.value, { forceRefresh, warnOnEmpty, silent })
}

watch(() => props.formData?.ai, async (ai) => {
  if (!ai) return
  // 设置面板每次重新灌入表单对象时，同步当前协议草稿并预热已有模型缓存。
  hydrateAiProviderDrafts()
  if (ai.enabled && ai.provider) {
    await fetchAiModels({ silent: true })
  }
}, { immediate: true })
</script>
