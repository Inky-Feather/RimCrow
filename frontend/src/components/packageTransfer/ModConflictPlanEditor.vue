<template>
  <div class="space-y-3">
    <div class="flex flex-wrap items-center gap-2">
      <span class="text-xs font-bold uppercase tracking-wide text-text-dim">批量处理</span>
      <label v-for="option in strategyOptions" :key="option.value" class="rounded-full flex items-center border px-2 py-1 text-xs"
        :class="strategy === option.value ? 'border-accent-primary/35 bg-accent-primary/10 text-accent-primary' : 'border-border-base/10 bg-bg-inset/55 text-text-dim'" >
        <input class="mr-1 accent-accent-primary" type="radio" :checked="strategy === option.value" @change="strategy = option.value" >
        {{ option.label }}
      </label>
    </div>

    <div v-for="row in rows" :key="row.folder_name" class="modal-section-subtle p-3" >
      <div class="flex flex-wrap items-center justify-between gap-2">
        <div class="text-sm font-bold text-text-main">{{ row.folder_name }}</div>
        <div class="text-[0.68rem] text-text-dim">{{ row.existing_path }}</div>
      </div>

      <div class="mt-3 grid grid-cols-3 gap-3">
        <div class="text-xs text-text-dim">
          <CommonSelect v-model="row.mode" label="处理方式" :options="modeOptions" />
        </div>
        <div v-if="row.mode === 'rename'" class="col-span-2 text-xs text-text-dim">
          <CommonInput v-model="row.rename_to" label="新文件夹名" placeholder="留空会自动补一个新名字" />
        </div>
        <div v-else class="col-span-2 rounded-lg border border-border-base/10 bg-bg-inset/45 px-3 py-2 text-xs text-text-dim">
          {{ row.mode === 'overwrite' ? '导入后会直接替换本地同名文件夹。' : '这项将跳过。' }}
        </div>

      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import CommonInput from '../common/input/CommonInput.vue'
import CommonSelect from '../common/input/CommonSelect.vue'

defineProps({
  rows: { type: Array, required: true },
})

const emit = defineEmits(['strategy'])

const strategy = ref('per_item')

const strategyOptions = [
  { value: 'overwrite_all', label: '全部替换' },
  { value: 'skip_all', label: '全部跳过' },
  { value: 'rename_all', label: '全部另存' },
  { value: 'per_item', label: '逐项处理' },
]

const modeOptions = [
  { value: 'overwrite', label: '替换原文件' },
  { value: 'skip', label: '跳过' },
  { value: 'rename', label: '另存为新文件夹' },
]

watch(strategy, (value) => emit('strategy', value))
</script>
