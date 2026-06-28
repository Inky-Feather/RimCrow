<template>
  <AiAssistantPanel :model-value="modelValue" :assistant-id="assistantId" :title="panelTitle"
    owner-type="log_viewer" :owner-key="ownerKey" empty-title="需要排错帮助吗？"
    empty-description="在左侧勾选日志后，可以直接发送给 AI 做分析。"
    input-placeholder="输入其它要求或直接点击右下角发送分析..."
    footer-hint="深度思考通常会增加时延与 token 消耗，但对复杂排错更稳。"
    :session-meta="{ sourceType, filename }"
    :request-payload="{ log_source_type: sourceType, filename }"
    :auto-start-request="autoStartRequest"
    @update:modelValue="(value) => emit('update:modelValue', value)"
  />
</template>

<script setup>
import { computed } from 'vue'
import AiAssistantPanel from '../ai/AiAssistantPanel.vue'

// -----------------------------------------------------------------
// Props / Emits
// -----------------------------------------------------------------
const props = defineProps({
  modelValue: { type: Boolean, default: false },
  assistantId: { type: String, required: true },
  autoStartRequest: { type: Object, default: null },
  sourceType: { type: String, default: 'game' },
  filename: { type: String, default: '' },
})

const emit = defineEmits(['update:modelValue'])

// -----------------------------------------------------------------
// 计算属性 (Computed)
// -----------------------------------------------------------------
// 同一日志文件应该稳定绑定到同一会话键，避免切换侧栏显隐时丢上下文。
const ownerKey = computed(() => `log:${props.sourceType}:${props.filename || '__no_file__'}`)
const panelTitle = computed(() => props.sourceType === 'app' ? '软件日志分析' : '游戏日志分析')
</script>
