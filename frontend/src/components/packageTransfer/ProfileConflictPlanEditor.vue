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

    <div v-for="row in rows" :key="row.archive_key" class="modal-section-subtle p-3" >
      <div class="flex flex-wrap items-center justify-between gap-2">
        <div class="text-sm font-bold text-text-main">{{ row.name || row.archive_key }}</div>
        <span class="text-[0.68rem] text-text-dim">
          {{ row.conflicts.length > 0 ? `本地找到 ${row.conflicts.length} 个同名环境` : '本地没有重名环境' }}
        </span>
      </div>

      <div class="mt-3 grid grid-cols-3 gap-3">
        <div class="text-xs text-text-dim">
          <CommonSelect v-model="row.mode" label="处理方式" :options="buildModeOptions(row)" />
        </div>
        <div v-if="row.mode === 'overwrite'" class="col-span-2 text-xs text-text-dim">
          <CommonSelect v-model="row.target_profile_id" label="覆盖到" :options="buildConflictOptions(row)" />
        </div>

        <div v-else-if="row.mode === 'create'" class="col-span-2 text-xs text-text-dim">
          <CommonSelect v-model="row.game_install_path" label="要使用的游戏目录" :options="availableInstallOptions" />
        </div>

        <div v-else class="col-span-2 rounded-lg border border-border-base/10 bg-bg-inset/45 px-3 py-2 text-xs text-text-dim">
          这项将跳过。
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import CommonSelect from '../common/input/CommonSelect.vue'

const props = defineProps({
  rows: { type: Array, required: true },
  availableInstalls: { type: Array, default: () => [] },
})

const emit = defineEmits(['strategy'])

const strategy = ref('per_item')

const strategyOptions = [
  { value: 'overwrite_all', label: '全部覆盖' },
  { value: 'create_all', label: '全部新建' },
  { value: 'skip_all', label: '全部跳过' },
  { value: 'per_item', label: '逐项处理' },
]

const availableInstallOptions = computed(() => props.availableInstalls.map(item => ({
  value: String(item.install_path || ''),
  label: `${item.game_version || '版本未知'} | ${item.install_path || '路径未知'}`,
})))

const buildModeOptions = (row) => [
  { value: 'create', label: '新建环境' },
  { value: 'overwrite', label: '覆盖现有环境' },
  { value: 'skip', label: '跳过' },
].filter(option => option.value !== 'overwrite' || row.conflicts.length > 0)

const buildConflictOptions = (row) => [
  { value: '', label: '请选择要覆盖的环境' },
  ...(row.conflicts || []).map(item => ({
    value: String(item.profile_id || ''),
    label: `${item.name || '未命名环境'} | ${item.game_version || '版本未知'} | ${item.game_install_path || '暂未绑定游戏目录'}`,
  })),
]

watch(strategy, (value) => emit('strategy', value))
</script>
