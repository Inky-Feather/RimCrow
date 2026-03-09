<template>
  <div :style="{ '--drag-color': `var(--color-accent-${listColor})`, '--rgb-components': hexToRgb(groupData.color) }"
    :class="isHighlight ? 'ring-2 ring-accent-highlight rounded-lg' : ''">
    <!-- 标题区 -->
    <div @click="toggle" :class="['list-none select-none px-1.5 flex text-text-dim hover:text-text-main items-center justify-between gap-0.5 rounded-lg font-medium',
      'bg-[rgba(var(--rgb-components),0.4)] hover:bg-[rgba(var(--rgb-components),0.6)] border border-text-main/5']">
      <!-- 抓取图标 -->
      <div v-tooltip="`移动`" class="drag-handle cursor-move p-1 text-text-dim hover:text-text-main hover:scale-130 transition-all">
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
      <div @click.stop v-tooltip="`改变颜色`" class="relative inline-flex items-center justify-center text-text-main hover:text-transparent transition-all">
        <ColorPicker v-model:pureColor="groupData.color" @pureColorChange="saveGroupColor" shape="circle" format="hex" picker-type="fk" disable-alpha round-history />
        <svg :class="expanded ? '-rotate-180' : ''" class="absolute pointer-events-none t-0 size-4 transition-transform duration-300" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"></path>
        </svg>
      </div>

      <!-- 标题 - 根据编辑状态显示输入框或文本 -->
      <span v-tooltip="groupData.name" :class="`flex-1 flex min-w-0 text-sm px-1 mx-1 text-text-main font-bold tracking-wider items-center gap-2`">
        <input class="flex-1 px-0 py-0.5 min-w-0 rounded bg-bg-deep/70 border border-text-main/10 text-text-main focus:border-accent-primary focus:outline-none" 
          v-show="isEditingName" v-model="editingGroupName" @click.stop @keyup.enter="saveGroupName" @blur="handleInputBlur" ref="nameInputRef"/>
        <span v-show="!isEditingName" class="min-w-0 truncate">{{ groupData.name }}</span>
      </span>

      <span :class="`text-xs bg-black/30 px-2 py-0.5 rounded text-[rgba(var(--rgb-components),1)]`">
        {{ groupData.mod_ids.length }}
      </span>

      <!-- 编辑/保存 与 删除 -->
      <span class="flex items-center">
        <!-- 编辑/保存按钮 -->
        <button @mousedown.prevent @click.stop="toggleEditName" v-tooltip="`编辑分组名称`" :class="`rounded-lg p-1 hover:bg-text-dim/30 cursor-pointer text-text-dim text-xs font-bold shadow-lg hover:shadow-bg-deep/50 transition-all`">
          <svg v-show="!isEditingName" class="hover:text-accent-secondary size-4.5" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M7 42H43" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round" />
            <path d="M11 26.7199V34H18.3172L39 13.3081L31.6951 6L11 26.7199Z" fill="none" stroke="currentColor" stroke-width="4" stroke-linejoin="round" />
          </svg>
          <svg v-show="isEditingName" class="hover:text-accent-success size-4.5" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M24 44C29.5228 44 34.5228 41.7614 38.1421 38.1421C41.7614 34.5228 44 29.5228 44 24C44 18.4772 41.7614 13.4772 38.1421 9.85786C34.5228 6.23858 29.5228 4 24 4C18.4772 4 13.4772 6.23858 9.85786 9.85786C6.23858 13.4772 4 18.4772 4 24C4 29.5228 6.23858 34.5228 9.85786 38.1421C13.4772 41.7614 18.4772 44 24 44Z" fill="none" stroke="currentColor" stroke-width="4" stroke-linejoin="round" />
            <path d="M16 24L22 30L34 18" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
        </button>
        <!-- 删除按钮 -->
        <button @click.stop="deleteGroup" v-tooltip="`删除分组`" :class="`rounded-lg p-1 hover:bg-text-dim/30 cursor-pointer 
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
    <Transition
      enter-active-class="grid transition-[grid-template-rows] duration-200 ease-out"
      enter-from-class="grid-rows-[0fr]"
      enter-to-class="grid-rows-[1fr]"
      leave-active-class="grid transition-[grid-template-rows] duration-200 ease-in"
      leave-from-class="grid-rows-[1fr]"
      leave-to-class="grid-rows-[0fr]"
    >
      <!-- 内容区 -->
      <div v-show="expanded" >
        <!-- pointer-events-none 确保分组本身被拖拽时禁用鼠标交互，进而禁止被意外拖入内部列表 -->
        <div class="min-h-0 overflow-hidden" :class="{ 'pointer-events-none': groupStore.isDraggingGroup }">
          <div class="p-1 mx-1 min-h-15 bg-[rgba(var(--rgb-components),0.2)] border border-b-text-main/5 border-x-text-main/5 border-t-transparent rounded-b-lg shadow-2xsl relative">
            <div v-show="groupData.mod_ids.length === 0" class="absolute flex rounded-lg top-0 bottom-0 left-0 right-0 m-1 items-center justify-center border-2 border-dashed text-gray-600 text-xs bg-bg-deep/30 select-none pointer-events-none">
              可拖拽模组到此
              <!-- 点阵背景 -->
              <div class="absolute inset-0 opacity-[0.05] pointer-events-none" style="background-image: radial-gradient(#fff 1px, transparent 1px); background-size: 20px 20px;"></div>
            </div>

            <VirtualList v-model="internalModList" dataKey="id" :keeps="50" class="max-h-[45vh] min-h-15 transition-all duration-200" ref="vListRef"
              placeholderClass="ghost" wrapClass="mb-5" :fallbackOnBody="true" :appendToBody="true" :scrollSpeed="{ x: 0, y: 10 }" :delay="appStore.settings.ui.drag_delay"
              :group="{ name: 'mods', pull: 'clone', put:['mods'], revertDrag: true }" :animation="150" :size="itemHeight" handle=".drag-handle"
              @drop="updateChildren" @drag="startDrag"
              v-selectable-list="{ 
                data: groupData.mod_ids, 
                selectedIds: modStore.selectedIds, 
                onSelect: (ids, anchor) => modStore.selectMods(ids, anchor),
                onClear: () => modStore.clearSelection(),
                clickClass: 'select-trigger', 
                swipeClass: 'swipe-trigger'
              }">
              <template v-slot:item="{ record, index, dataKey }">

                <div class="relative group">
                  <ModItem :item_id="dataKey" :index="index" :key="dataKey" :list-color="listColor" 
                          :is-selected="modStore.selectedIds.includes(dataKey)" 
                          :show-index="appStore.settings.ui.show_group_index"  
                          :show-icon="appStore.settings.ui.show_group_icon"
                          :simple="true">
                  </ModItem>
                  
                  <!-- 右上角移除按钮（阻止冒泡，避免触发选择） -->
                  <button @click.stop="removeItem(dataKey)" @mousedown.stop v-tooltip="`移除`"
                    class="absolute top-1 right-1 w-3 h-3 bg-accent-danger text-text-main rounded-full 
                          opacity-0 group-hover:opacity-80 transition-opacity duration-200
                          flex items-center justify-center text-xs z-10 hover:scale-110">×
                  </button>
                  <div v-if="modStore.activeIds.includes(dataKey)" v-tooltip="'已启用'" tabindex="0" class="absolute w-3 h-3 bg-accent-success text-text-main rounded-full 
                          transition-opacity duration-200 flex items-center justify-center text-xs z-10 hover:scale-110"
                          :class="[appStore.settings.ui.show_group_index?'top-0 left-6':'top-0 left-0']">
                  </div>
                </div>

              </template>
            </VirtualList>
          </div>
        </div>
      </div>
    </Transition>
  </div>
</template>

<script setup lang="ts">
import { watch, ref, nextTick, computed } from 'vue' // 引入 ref
import VirtualList from 'vue-virtual-sortable';
import ModItem from './ModItem.vue'
import { useDebounceFn } from '@vueuse/core'
import { ColorPicker } from "vue3-colorpicker";
import "vue3-colorpicker/style.css";
import { useModStore } from '../../stores/modStore';
import { useGroupStore } from '../../stores/groupStore';
import { useAppStore } from '../../stores/appStore';
import { createToastInterface } from 'vue-toastification';

const props = defineProps({
  id: { type: String, required: true },
  index: { type: Number, required: true },
  groupData: { type: Object, required: true },
  isHighlight: { type: Boolean, default: false }, // 用于外部控制样式
  expanded: { type: Boolean, default: false }, // 这个 props 会由父组件 GroupList 传递
  listColor: { type: String, default: 'primary' }, // 用于不同列表的颜色区分
  isDragging: { type: Boolean, default: false } // 用于外部控制样式
})

const toast = createToastInterface()
const modStore = useModStore()
const appStore = useAppStore()
const groupStore = useGroupStore()
const internalModList = ref([])
const vListRef = ref(null)
const emit = defineEmits(['toggle', 'delete-group', 'remove-item', 'update-group', 'update-children'])


const itemHeight = computed(() => appStore.scalePx(30)+4 )
// 计算属性computed无法直接修改props.groupData.mod_ids，因为它是只读的。
// 监听 props 变化，同步到本地 (单向数据流：父 -> 子)
watch(
  () => props.groupData.mod_ids,
  (newIds) => {
    // 将纯 ID 转换为 VirtualList 需要的对象格式
    // 注意：这里要创建一个新的数组引用，防止污染
    internalModList.value = newIds.map(id => ({ id: id }))
  },
  { immediate: true, deep: true }
  // 设置immediate: true后，监听器会在初始化时立即执行一次回调，无需等待数据首次变化。
  // 设置deep: true后，监听器会 “递归遍历” 嵌套结构，感知所有层级属性的变化，确保嵌套数据修改时能触发回调。
)

// --- 数据传递与事件处理 ---
// 切换展开状态
const toggle = () => {
  emit('toggle', props.id)
}
// 删除分组
const deleteGroup = () => {
  emit('delete-group', props.id)
}
// 移除模组
const removeItem = (itemId: string) => {
  emit('remove-item', props.id, [itemId])
}
// 更新分组信息
const updateGroup = (data = props.groupData) => {
  emit('update-group', props.id, data)
}
// 保存分组名称
const saveGroupName = () => {
  if (!isEditingName.value) return  // 确保在编辑状态下调用
  let newName = editingGroupName.value.trim()
  if(groupStore.allGroupNames.includes(newName)) {
    // 名称冲突，添加序号
    let index = 1
    while (groupStore.allGroupNames.includes(`${newName}-${index}`)) {
      index++
    }
    newName = `${newName}-${index}`
    toast.warning(`分组名称已存在，已添加序号 ${index}`)
  }
  if (newName && newName !== props.groupData.name) {
    emit('update-group', props.id, { name: newName })
  }
  isEditingName.value = false
}
// 保存分组颜色
const saveGroupColor = useDebounceFn((color) => {
  console.log("保存颜色:", color)
  emit('update-group', props.id, { color: color })
}, 1000)

const startDrag = (e) => {
  console.log("开始拖拽:", e)
}
// 更新子项的排序
const updateChildren = (e) => {
  console.log("更新子项排序:", e)
  const oldIds = props.groupData.mod_ids  // 原始顺序
  const newIds = internalModList.value.map(item => item.id)  // 获取当前的最新顺序 ID列表
  const tempSelectedIds = modStore.selectedIds
  // 检查是否是当前分组的列表，排除当前列表自身的触发
  const currentListDom = vListRef.value.$el
  if (e.event.from === currentListDom || e.event.from === e.event.to) {
    console.log(props.groupData.name, "排序结束:", e)
    // 只有顺序真的变了才发请求
    if (JSON.stringify(newIds) !== JSON.stringify(oldIds)) {
      emit('update-children', props.id, newIds)
    }
    return
  }

  // 拖动项来自分组，不允许插入
  if (e.item?.group_id) {
    console.log("分组错误插入:", e)
    return
  }

  console.log(props.groupData.name, "插入结束:", e)
  // 去除重复, 保持拖动项的位置（保留除已选项外的其他项，已选择的项后续插入）
  const uniqueIds = newIds.filter((id, index) => {
    // 检测是否是拖动项（值和索引都匹配），是则保留（用于标记位置）
    if (index === e.newIndex && id === e.item.id) return true
    // 排除已选择的项（过滤重复）
    if (tempSelectedIds.includes(id)) return false
    // 其他未选择项，保留
    return true
  })
  const newIndex = uniqueIds.indexOf(e.item.id)
  // 根据拖动项，插入选中项（因选中项包含拖动项，所以插入时需要移除拖动项）
  uniqueIds.splice(newIndex, 1, ...tempSelectedIds)
  // （修复漏洞：如果拖入相同项到相邻位置，去重后实际列表顺序不变，但组件会渲染拖入的相同项，所以目前必须强制更新）
  internalModList.value = uniqueIds.map(id => ({ id: id }))
  console.log("排序前:", oldIds)
  console.log("排序后:", uniqueIds)
  // 只有顺序真的变了才发请求
  if (JSON.stringify(uniqueIds) !== JSON.stringify(oldIds)) {
    emit('update-children', props.id, uniqueIds)
  }
}

// ===== 分组名称编辑逻辑 =====
const isEditingName = ref(false)
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

const handleInputBlur = () => {
  // 失焦时，退出编辑状态
  isEditingName.value = false
}

// 颜色格式转换
const hexToRgb = (hex) => {
  if (!hex || typeof hex !== 'string') return `0, 0, 0`; // 返回纯组件字符串
  let cleanHex = hex.replace('#', '');
  if (cleanHex.length === 3) {
    cleanHex = cleanHex.split('').map(char => char + char).join('');
  }
  // 确保是六位
  if (cleanHex.length !== 6) {
    console.error(`Invalid hex color: ${hex}`);
    return `0, 0, 0`;
  }
  // 提取 R, G, B 分量，并从十六进制转换为十进制
  const r = parseInt(cleanHex.substring(0, 2), 16);
  const g = parseInt(cleanHex.substring(2, 4), 16);
  const b = parseInt(cleanHex.substring(4, 6), 16);
  return `${r}, ${g}, ${b}`;
};

</script>

<style scoped>
.ghost {
  opacity: 0.5;
  border: 2px dashed var(--drag-color);
  scale: 90%;
  padding: 5px;
  border-radius: 10px;
  /* transform: scale(0.9); */
  /* transition: none; */
}

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