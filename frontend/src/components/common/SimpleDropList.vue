<template>
  <!--
    小型投放列表：用于规则编辑器这类“数量很少但需要接收模组拖入”的场景。

    设计边界：
    1. 不做虚拟滚动：规则项通常不超过几十个，引入虚拟列表反而会增加定位和可读性成本。
    2. 不做内部排序：当前业务只需要“从模组列表拖入规则”，顺序由父组件自己的规则数据决定。
    3. 只读取全局拖拽会话：VirtualDragList 负责创建 session，本组件只判断来源是否可投放。
       这样规则编辑器、主列表、分组列表使用同一套拖拽协议，不需要各自拼 DataTransfer。
  -->
  <div
    class="relative"
    @dragover.prevent="handleDragOver"
    @drop.prevent="handleDrop"
    @dragleave="handleDragLeave"
  >
    <div :class="wrapClass">
      <div
        v-for="(record, index) in items"
        :key="getRowKey(record, index)"
        :data-drag-index="index"
      >
        <slot name="item" :record="record" :index="index" :dataKey="getRowKey(record, index)" />
      </div>
    </div>
    <div
      v-if="isDropActive"
      class="pointer-events-none absolute inset-0 rounded-lg border border-dashed border-accent-special/70 bg-accent-special/10"
    ></div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'

const props = defineProps({
  modelValue: { type: Array, default: () => [] },
  dataKey: { type: String, required: true },
  wrapClass: { type: [String, Array, Object], default: '' },
  disabled: { type: Boolean, default: false },
  group: { type: [Object, String], default: null },
})

const emit = defineEmits(['drop'])

const isDropActive = ref(false)
const items = computed(() => Array.isArray(props.modelValue) ? props.modelValue : [])

const getRowKey = (record, index) => record?.[props.dataKey] ?? record?.id ?? index
const normalizeGroupName = (group) => {
  // group 兼容字符串和 SortableJS 风格对象，便于小列表和虚拟列表共享同一套拖拽会话。
  if (!group) return ''
  if (typeof group === 'string') return group
  return String(group.name || '')
}
const canPutFrom = (sourceGroup) => {
  // 只判断“来源组是否允许投放”，具体去重、批量导入等业务规则交给父组件处理。
  // 这里刻意不读取目标列表内容，避免 SimpleDropList 变成规则编辑器的业务组件。
  if (props.disabled) return false
  const put = props.group?.put
  if (put === false) return false
  if (put === true || put == null) return true
  if (Array.isArray(put)) return put.includes(sourceGroup)
  return String(put) === sourceGroup
}

const handleDragOver = () => {
  // VirtualDragList 在 dragstart 时写入 window.__RMM_DRAG_SESSION__；
  // 小型 drop zone 只读取这份会话，避免每个小组件都实现一套拖拽协议。
  const session = window.__RMM_DRAG_SESSION__
  isDropActive.value = !!session && canPutFrom(session.sourceGroup)
}
const handleDragLeave = (event) => {
  // dragleave 会在子元素之间移动时频繁触发，只在真正离开整个 drop zone 时关闭高亮。
  if (!event.currentTarget.contains(event.relatedTarget)) {
    isDropActive.value = false
  }
}
const handleDrop = (event) => {
  const session = window.__RMM_DRAG_SESSION__
  isDropActive.value = false
  if (!session || !canPutFrom(session.sourceGroup)) return
  const item = session.item
  // 这里永远投放到末尾；规则列表不承担排序职责，父组件只需要知道“拖入了哪些模组”。
  emit('drop', {
    item,
    key: item?.[props.dataKey] ?? item?.id,
    newIndex: items.value.length,
    list: [...items.value, item],
    event: {
      ...event,
      from: session.sourceEl || null,
      to: event.currentTarget,
      target: event.currentTarget,
    },
  })
}
</script>
