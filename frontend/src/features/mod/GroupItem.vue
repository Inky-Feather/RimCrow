<template>
  <div :style="{ '--rgb-components': hexToRgb(groupData.color) }"
    :class="isHighlight ? 'ring-2 ring-accent-highlight rounded-lg' : ''">
    <!-- 标题区：分组面板现在由外层统一虚拟滚动，标题只负责分组自身操作。 -->
    <div @click="toggle" :class="['list-none select-none px-1 flex text-text-dim hover:text-text-main items-center justify-between gap-0.5 rounded-lg font-medium',
      'bg-[rgba(var(--rgb-components),0.5)] hover:bg-[rgba(var(--rgb-components),0.6)] border border-border-base/5']">
      <!-- 抓取图标。真正的拖拽会话由外层 VirtualDragList 接管，避免嵌套列表互相抢事件。 -->
      <div v-tooltip="`移动`" class="select-trigger cursor-move p-1 text-text-dim hover:text-text-main hover:scale-130 transition-all">
        <svg class="size-5" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path
            d="M24 44C35.0457 44 44 35.0457 44 24C44 12.9543 35.0457 4 24 4C12.9543 4 4 12.9543 4 24C4 35.0457 12.9543 44 24 44Z"
            fill="none" stroke="currentColor" stroke-width="4" stroke-linejoin="round" />
          <path d="M20 20L24 16L28 20" stroke="currentColor" stroke-width="4" stroke-linecap="round"
            stroke-linejoin="round" />
          <path d="M20 28L24 32L28 28" stroke="currentColor" stroke-width="4" stroke-linecap="round"
            stroke-linejoin="round" />
        </svg>
      </div>

      <!-- 颜色选择与展开显示 -->
      <div @click.stop v-tooltip="`改变颜色`" class="no-drag relative inline-flex items-center justify-center text-text-main hover:text-transparent transition-all">
        <!--
          取色器内部会创建 Popper/Teleport 和拖拽监听，不适合在虚拟滚动标题行里常驻。
          默认只渲染轻量色块；用户明确点击改色时再挂载真实 ColorPicker，避免滚动穿过大量分组时反复创建重组件。
        -->
        <button v-if="!isColorPickerOpen" type="button" class="size-4 rounded-full border border-border-base/18 shadow-sm transition-transform hover:scale-125"
          :style="{ backgroundColor: groupData.color || 'var(--color-text-subtle)888' }"
          @mousedown.stop
          @click.stop="isColorPickerOpen = true">
        </button>
        <ColorPicker v-else v-model:pureColor="groupData.color" @pureColorChange="saveGroupColor" shape="circle" format="hex" picker-type="fk" disable-alpha round-history default-popup blur-close />
        <svg :class="expanded ? '-rotate-180' : ''" class="absolute pointer-events-none t-0 size-4 transition-transform duration-300" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"></path>
        </svg>
      </div>

      <!-- 标题 - 根据编辑状态显示输入框或文本 -->
      <span v-tooltip="groupData.name" :class="`flex-1 flex min-w-0 text-sm px-1 mx-1 text-text-main font-bold tracking-wider items-center gap-2`">
        <input class="input-glass min-w-0 flex-1 px-2 py-0.5 text-text-main focus:outline-none"
          v-if="isEditingName" v-model="editingGroupName" @click.stop @keyup.enter="saveGroupName" @blur="saveGroupName" ref="nameInputRef"/>
        <span v-if="!isEditingName" class="min-w-0 truncate">{{ groupData.name }}</span>
      </span>

      <span :class="`text-xs bg-bg-inset/70 px-2 py-0.5 rounded text-[rgba(var(--rgb-components),1)]`">
        {{ groupModIds.length }}
      </span>

      <!-- 编辑/保存 与 删除 -->
      <span class="flex items-center">
        <button @mousedown.prevent @click.stop="openExportDialog" v-tooltip="`打包导出分组模组`" :class="`rounded-lg p-1 hover:bg-bg-overlay/10 cursor-pointer text-text-dim text-xs font-bold shadow-lg hover:shadow-bg-deep/50 transition-all`">
          <Package class="size-4.5 hover:text-accent-special" />
        </button>
        <!-- 编辑/保存按钮 -->
        <button @mousedown.prevent @click.stop="toggleEditName" v-tooltip="`编辑分组名称`" :class="`rounded-lg p-1 hover:bg-bg-overlay/10 cursor-pointer text-text-dim text-xs font-bold shadow-lg hover:shadow-bg-deep/50 transition-all`">
          <svg v-if="!isEditingName" class="hover:text-accent-secondary size-4.5" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M7 42H43" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round" />
            <path d="M11 26.7199V34H18.3172L39 13.3081L31.6951 6L11 26.7199Z" fill="none" stroke="currentColor" stroke-width="4" stroke-linejoin="round" />
          </svg>
          <svg v-if="isEditingName" class="hover:text-accent-success size-4.5" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M24 44C29.5228 44 34.5228 41.7614 38.1421 38.1421C41.7614 34.5228 44 29.5228 44 24C44 18.4772 41.7614 13.4772 38.1421 9.85786C34.5228 6.23858 29.5228 4 24 4C18.4772 4 13.4772 6.23858 9.85786 9.85786C6.23858 13.4772 4 18.4772 4 24C4 29.5228 6.23858 34.5228 9.85786 38.1421C13.4772 41.7614 18.4772 44 24 44Z" fill="none" stroke="currentColor" stroke-width="4" stroke-linejoin="round" />
            <path d="M16 24L22 30L34 18" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
        </button>
        <!-- 删除按钮 -->
        <button @click.stop="deleteGroup($event)" v-tooltip="`删除分组`" :class="`rounded-lg p-1 hover:bg-bg-overlay/10 cursor-pointer
          text-text-dim hover:text-accent-danger text-xs font-bold shadow-lg hover:shadow-bg-deep/50
          transition-all`">
          <svg class="size-4.5" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M8 11L40 11" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round" />
            <path d="M18 5L30 5" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round" />
            <path d="M12 17H36V40C36 41.6569 34.6569 43 33 43H15C13.3431 43 12 41.6569 12 40V17Z" fill="none" stroke="currentColor" stroke-width="4" stroke-linejoin="round" />
              <path d="M20 25L28 33" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round" />
              <path d="M28 25L20 33" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
        </button>
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent, nextTick, onBeforeUnmount, ref } from 'vue'
import { useDebounceFn } from '@vueuse/core'
import { Package } from 'lucide-vue-next'
import { useAppStore } from '../../app/stores/appStore';
import { useGroupStore } from './stores/groupStore';
import { hexToRgbComponents } from '../../shared/lib/color'
import { toast } from '../../shared/lib/common';

const props = defineProps({
  id: { type: String, required: true },
  index: { type: Number, required: true },
  groupData: { type: Object, required: true },
  isHighlight: { type: Boolean, default: false }, // 用于外部控制样式
  expanded: { type: Boolean, default: false }, // 这个 props 会由父组件 GroupList 传递
  listColor: { type: String, default: 'primary' }, // 用于不同列表的颜色区分
})

const appStore = useAppStore()
const groupStore = useGroupStore()
const emit = defineEmits(['toggle', 'delete-group', 'update-group'])
const ColorPicker = defineAsyncComponent(async () => {
  await import('vue3-colorpicker/style.css')
  const module = await import('vue3-colorpicker')
  return module.ColorPicker
})

const groupModIds = computed(() => Array.isArray(props.groupData?.mod_ids) ? props.groupData.mod_ids : [])
// 分组标题上的打包导出是原有模组包功能，和推荐导出入口分开处理。
const openExportDialog = () => {
  appStore.openCustomModExportDialog({
    title: `导出分组模组: ${props.groupData?.name || '未命名分组'}`,
    description: '可按需附带依赖、联锁项和语言包。',
    modIds: [...groupModIds.value],
    summary: `分组内共 ${groupModIds.value.length} 个模组。`,
  })
}
// 切换展开状态
const toggle = () => {
  emit('toggle', props.id)
}
// 删除分组
const deleteGroup = (event) => {
  emit('delete-group', props.id, event)
}
// 生成唯一分组名
const resolveUniqueGroupName = (rawName: string) => {
  const trimmedName = String(rawName ?? '').trim()
  const currentName = String(props.groupData.name ?? '').trim()
  if (!trimmedName) {
    return { name: currentName, renamed: false, index: null, valid: false }
  }
  // 判重时排除当前分组自身，避免“未改名保存”也被追加序号
  const takenNames = groupStore.allGroupNames
    .map(name => String(name ?? '').trim())
    .filter(name => name && name !== currentName)
  if (!takenNames.includes(trimmedName)) {
    return { name: trimmedName, renamed: false, index: null, valid: true }
  }
  let index = 1
  while (takenNames.includes(`${trimmedName}-${index}`)) {
    index++
  }
  return { name: `${trimmedName}-${index}`, renamed: true, index, valid: true }
}
// 保存分组名称
const saveGroupName = () => {
  if (!isEditingName.value) return  // 确保在编辑状态下调用
  const result = resolveUniqueGroupName(editingGroupName.value)
  if (result.renamed) {
    // 分组名称冲突时沿用旧行为：自动添加序号，而不是阻断用户输入。
    toast.warning(`分组名称已存在，已添加序号 ${result.index}`)
  }
  if (result.valid && result.name !== props.groupData.name) {
    emit('update-group', props.id, { name: result.name })
  }
  isEditingName.value = false
}
// 保存分组颜色
const saveGroupColor = useDebounceFn((color) => {
  emit('update-group', props.id, { color: color })
}, 1000)

onBeforeUnmount(() => {
  saveGroupColor.flush?.()
})

// ===== 分组名称编辑逻辑 =====
const isEditingName = ref(false)
const isColorPickerOpen = ref(false)
const editingGroupName = ref('')
const nameInputRef = ref(null) // 绑定 input DOM
// 切换编辑状态
const toggleEditName = async () => {
  if (isEditingName.value) {
    // 如果当前是编辑状态，点击时保存并退出编辑
    saveGroupName()
  } else {
    // 如果当前是非编辑状态，点击时进入编辑
    editingGroupName.value = props.groupData.name
    isEditingName.value = true
    // 等待 DOM 显示 input 后，立即聚焦并全选文本
    await nextTick()
    if (nameInputRef.value) {
      nameInputRef.value.focus()
      // 可选：全选文本，方便用户直接修改
      nameInputRef.value.select()
    }
  }
}

// 颜色格式转换统一复用公共 util，避免分组卡片和其它组件各维护一份。
const hexToRgb = hexToRgbComponents
</script>

<style scoped>
/* 取色器样式优化 */
:deep(.vc-color-wrap.round) {
  width: 1rem !important;
  height: 1rem !important;
  border: none !important;
  margin-right: 0 !important;
  transition: all 0.15s ease;
}

:deep(.vc-color-wrap.round:hover) {
  transform: scale(1.3);
  z-index: 10;
}

:deep(.vc-color-wrap.transparent) {
  background-image: none !important;
}
</style>
