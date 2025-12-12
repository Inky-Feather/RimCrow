<template>
  <div :style="{ '--drag-color': `var(--color-accent-${listColor})`, '--rgb-components': hexToRgb(groupData.color) }">
    <!-- 标题区 -->
    <div @click="toggle" :class="['list-none select-none px-1.5 flex text-text-dim hover:text-text-main items-center justify-between gap-0.5 rounded-lg font-medium',
      'bg-[rgba(var(--rgb-components),0.2)] hover:bg-[rgba(var(--rgb-components),0.4)]']">
      <!-- 抓取图标 -->
      <div title="移动" class="drag-handle cursor-move p-1 text-text-dim hover:text-text-main hover:scale-130 transition-all">
        <svg width="18" height="18" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
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
      <div @click.stop title="改变颜色" class="relative inline-flex items-center justify-center text-text-main hover:text-transparent transition-all">
        <ColorPicker v-model:pureColor="groupData.color" shape="circle" format="hex" picker-type="fk" disable-alpha round-history />
        <svg :class="expanded ? '-rotate-180' : ''" class="absolute pointer-events-none t-0 transition-transform duration-300" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"></path>
        </svg>
      </div>

      <!-- 标题 - 根据编辑状态显示输入框或文本 -->
      <span :title="groupData.name" :class="`flex-1 flex min-w-0 text-sm px-1 mx-1 text-text-main font-bold tracking-wider items-center gap-2`">
        <input v-show="isEditingName" v-model="editingGroupName" @click.stop @keyup.enter="saveGroupName" @blur="saveGroupName"
          class="flex-1 px-0 py-0.5 min-w-0 rounded bg-bg-deep/70 border border-white/10 text-white focus:border-accent-primary focus:outline-none" />
        <span v-show="!isEditingName" class="min-w-0 truncate">{{ groupData.name }}</span>
      </span>

      <span :class="`text-[10px] bg-black/30 px-2 py-0.5 rounded text-[rgba(var(--rgb-components),1)]`">
        {{ groupData.modIds.length }}
      </span>

      <!-- 编辑/保存 与 删除 -->
      <span class="flex items-center">
        <!-- 编辑/保存按钮 -->
        <button @click.stop="toggleEditName" title="编辑分组名称" :class="`rounded-lg p-1 hover:bg-text-dim/30 cursor-pointer text-text-dim text-xs font-bold shadow-lg hover:shadow-bg-deep/50 transition-all`">
          <svg v-show="!isEditingName" class="hover:text-accent-secondary" width="18" height="18" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M7 42H43" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round" />
            <path d="M11 26.7199V34H18.3172L39 13.3081L31.6951 6L11 26.7199Z" fill="none" stroke="currentColor" stroke-width="4" stroke-linejoin="round" />
          </svg>
          <svg v-show="isEditingName" class="hover:text-accent-success" width="18" height="18" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M24 44C29.5228 44 34.5228 41.7614 38.1421 38.1421C41.7614 34.5228 44 29.5228 44 24C44 18.4772 41.7614 13.4772 38.1421 9.85786C34.5228 6.23858 29.5228 4 24 4C18.4772 4 13.4772 6.23858 9.85786 9.85786C6.23858 13.4772 4 18.4772 4 24C4 29.5228 6.23858 34.5228 9.85786 38.1421C13.4772 41.7614 18.4772 44 24 44Z" fill="none" stroke="currentColor" stroke-width="4" stroke-linejoin="round" />
            <path d="M16 24L22 30L34 18" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
        </button>
        <!-- 删除按钮 -->
        <button @click.stop="deleteGroup" title="删除分组" :class="`rounded-lg p-1 hover:bg-text-dim/30 cursor-pointer 
          text-text-dim hover:text-accent-danger text-xs font-bold shadow-lg hover:shadow-bg-deep/50 
          transition-all`">
          <svg width="18" height="18" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M8 11L40 11" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round" />
            <path d="M18 5L30 5" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round" />
            <path d="M12 17H36V40C36 41.6569 34.6569 43 33 43H15C13.3431 43 12 41.6569 12 40V17Z" fill="none" stroke="currentColor" stroke-width="4" stroke-linejoin="round" />
              <path d="M20 25L28 33" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round" />
              <path d="M28 25L20 33" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
        </button>
      </span>
    </div>

    <!-- 内容区 -->
    <div class="grid transition-[grid-template-rows] duration-200"
      :class="expanded ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]'">
      <div class="h-full overflow-hidden">
        <div :class="`p-1 mx-1 min-h-15 bg-[rgba(var(--rgb-components),0.1)] rounded-b-lg shadow-2xsl relative`">
          <div v-show="groupData.modIds.length === 0" class="absolute flex rounded-lg top-0 bottom-0 left-0 right-0 m-1 items-center justify-center border-2 border-dashed text-gray-600 text-xs bg-bg-deep/30 select-none pointer-events-none">
            可拖拽模组到此
            <!-- 点阵背景 -->
            <div class="absolute inset-0 opacity-[0.05] pointer-events-none" style="background-image: radial-gradient(#fff 1px, transparent 1px); background-size: 20px 20px;"></div>
          </div>

          <VirtualList v-model="getGroupModIds" dataKey="id" :keeps="50" class="h-full p-1 min-h-15"
            placeholderClass="ghost" wrapClass="space-y-1" :fallbackOnBody="true" :scrollSpeed="{ x: 0, y: 10 }"
            :group="{ name: 'mods', pull: 'clone', put: 'mods', revertDrag: true }" :animation="150">
            <template v-slot:item="{ record, index, dataKey }">

              <div class="relative group">
                <ModItem :id="dataKey" :index="index" :key="dataKey" :list-color="listColor"
                        @click.stop="handleClick($event, dataKey)">
                </ModItem>
                
                <!-- 右上角移除按钮 -->
                <button @click.stop="removeItem(dataKey)" title="移除"
                  class="absolute top-1 right-1 w-3 h-3 bg-accent-danger text-text-main rounded-full 
                        opacity-0 group-hover:opacity-80 transition-opacity duration-200
                        flex items-center justify-center text-xs z-10 hover:scale-110">×
                </button>
              </div>

            </template>
          </VirtualList>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue' // 引入 ref
import { useModStore } from '../../stores/modStore'
import VirtualList from 'vue-virtual-sortable';
import ModItem from './ModItem.vue'
import { ColorPicker } from "vue3-colorpicker";
import "vue3-colorpicker/style.css";

const props = defineProps({
  id: { type: String, required: true },
  index: { type: Number, required: true },
  groupData: { type: Object, required: true },
  expanded: { type: Boolean, default: false }, // 这个 props 会由父组件 GroupList 传递
  listColor: { type: String, default: 'primary' }, // 用于不同列表的颜色区分
  isDragging: { type: Boolean, default: false } // 用于外部控制样式
})

const store = useModStore()
const emit = defineEmits(['toggle', 'delete-group', 'remove-item']) // 注册新的事件

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
  emit('remove-item', props.id, itemId)
}

// --- 分组名称编辑逻辑 ---
const isEditingName = ref(false)
const editingGroupName = ref('')
// 切换编辑状态
const toggleEditName = () => {
  if (isEditingName.value) {
    // 如果当前是编辑状态，点击时保存并退出编辑
    saveGroupName()
  } else {
    // 如果当前是非编辑状态，点击时进入编辑
    editingGroupName.value = props.groupData.name
    isEditingName.value = true
  }
}
// 保存分组名称
const saveGroupName = () => {
  if (editingGroupName.value.trim() && editingGroupName.value !== props.groupData.name) {
    props.groupData.name = editingGroupName.value.trim()
    store.markDirty() // 标记数据已修改
  }
  isEditingName.value = false
}

// 计算属性：获取和设置分组内的模组 ID 列表
const getGroupModIds = computed({
  get() {
    return props.groupData.modIds.map(id => ({ id: id }));
  },
  set(val: any[]) { // val 将是 { id: string }[]
    const idList = val.map(item => item.id);
    if (JSON.stringify(props.groupData.modIds) !== JSON.stringify(idList)) { // 只有数据真正改变时才更新
      props.groupData.modIds = idList;
      store.markDirty();
    }
  }
})

// ModItem 内部的点击事件，可以保持不变或根据需要调整
const handleClick = (event, modId) => {
  // 可以在这里处理 ModItem 的点击事件，例如选中/取消选中
  // console.log('ModItem clicked:', modId);
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