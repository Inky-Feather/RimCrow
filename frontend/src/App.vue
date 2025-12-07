<template>
  <div class="h-dvh w-screen flex flex-col p-1 overflow-hidden font-sans bg-bg-deep text-text-main select-none">
    <RimHeader/>
    <!-- 容器：深色背景，添加内边距 制造悬浮感 -->
    <div ref="containerRef" class="flex flex-1 w-full overflow-hidden relative ">
      
      <!-- ================= COLUMN 1: 详情 (Details) ================= -->
      <div class="h-full p-1 overflow-hidden relative transition-opacity"
          :style="{ width: colWidths[0] + 'px' }">
          <div class="h-full rounded-2xl overflow-hidden bg-bg-surface/40 backdrop-blur-sm border border-white/5 shadow-2xl">
            <ModDetails />
          </div>
      </div>

      <!-- 分割线 1 -->
      <Resizer :active="resizeState.activeIndex === 0" 
               @mousedown="startResize(0, $event)" />


      <!-- ================= COLUMN 2: 待选库 (Library) ================= -->
      <div class="h-full p-1 overflow-hidden relative transition-opacity"
           :style="{ width: colWidths[1] + 'px' }">
          <div class="h-full rounded-2xl overflow-hidden bg-bg-surface/40 backdrop-blur-sm border border-white/5 shadow-2xl">
            <!-- 光圈 -->
            <div class="absolute inset-0 border-2 border-accent-success/10 rounded-2xl pointer-events-none z-0"></div>
            <ModList v-model="store.inactiveIds" title="inactive" listColor="primary" />

          </div>
      </div>

      <!-- 分割线 2 -->
      <Resizer :active="resizeState.activeIndex === 1" 
               @mousedown="startResize(1, $event)" />

      <!-- ================= COLUMN 3: 启用/排序 (Active) ================= -->
      <div class="h-full p-1 overflow-hidden relative transition-opacity"
           :style="{ width: colWidths[2] + 'px' }">
          <div class="h-full rounded-2xl overflow-hidden bg-bg-surface/40 backdrop-blur-sm border border-white/5 shadow-2xl">
            
            <ModList v-model="store.activeIds" title="active" :hasSidebar=true listColor="success" />
            
          </div>
      </div>

      <!-- 分割线 3 -->
      <Resizer :active="resizeState.activeIndex === 2" 
               @mousedown="startResize(2, $event)" />


      <!-- ================= COLUMN 4: 辅助/分组 (Tabs) ================= -->
      <div class="h-full p-1 flex flex-col overflow-hidden relative transition-opacity"
           :style="{ width: colWidths[3] + 'px' }">
          <div class="flex-1 rounded-t-2xl overflow-hidden bg-bg-surface/40 backdrop-blur-sm border border-white/5 ">
            <!-- 标签页切换 -->
            <div class="absolute right-10 flex border-b border-white/5 text-xs font-bold ">
              <button v-for="tab in ['Temp', 'Groups']" :key="tab" @click="activeTab = tab"
                class="flex-1 py-2 text-center transition-colors relative m-0.5 cursor-pointer "
                :class="activeTab === tab ? 'text-accent-secondary' : 'text-gray-500 hover:text-text-main'"
              >
                {{ tab }}
                <!-- <div v-if="activeTab === tab" class="absolute bottom-0 left-0 right-0 h-0.5 bg-accent-primary"></div> -->
              </button>
            </div>

            <ModList v-if="activeTab === 'Temp'" v-model="store.tempIds" title="temp" listColor="warning"/>
            <GroupList v-if="activeTab === 'Groups'" v-model="store.groupList" variant="group" listColor="special"/>

          </div>
          
          <!-- 按钮组 -->
          <div class="p-3 rounded-b-2xl grid grid-cols-2 gap-1 bg-bg-surface/80 shadow-2xl ">
            <button class="col-span-1 py-2 rounded-lg bg-white/5 hover:bg-white/10 text-[10px] text-gray-300 border border-white/5 transition-all uppercase font-bold"
              @click="store.scanMods()">{{ store.isLoading ? '扫描中...' : '刷新' }}</button>
            <button class="col-span-1 py-2 rounded-lg bg-accent-primary hover:bg-[#0891b2] text-black text-[10px] font-bold shadow-lg shadow-accent-primary/10 transition-all uppercase"
              @click="store.saveLoadOrder()">保存</button>
            <button class="col-span-2 py-3 rounded-lg bg-accent-success hover:bg-[#059669] text-white text-xs font-bold shadow-lg shadow-accent-success/20 flex items-center justify-center gap-2 transition-all uppercase mt-1"
              @click="store.launchGame()">启动游戏</button>
          </div>
      </div>

    </div>
    <!-- 悬浮面板 -->
     
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onUnmounted, h } from 'vue'
import { useModStore } from './stores/modStore'
import RimHeader from './components/RimHeader.vue'
import ModDetails from './components/ModDetails.vue'
import ModList from './components/ModList.vue'
import GroupList from './components/GroupList.vue'

const store = useModStore()
const activeTab = ref('Temp')

// --- 拖拽调整宽度逻辑 ---
const containerRef = ref(null)
const MIN_WIDTH = 200 // 每一列的最小宽度
// 核心状态：4个列的宽度
// 初始值给0，mounted时会立刻计算
const colWidths = reactive([0, 0, 0, 0])

const resizeState = reactive({
  isDragging: false,
  activeIndex: -1,
  startX: 0,
  startLeftW: 0,
  startRightW: 0
})

// --- 拖拽逻辑 ---
// 1. 初始化：平均分配宽度
const distributeEvenly = () => {
  if (!containerRef.value) return
  const totalW = containerRef.value.clientWidth
  const avg = totalW / 4
  // 填充数组
  for (let i = 0; i < 4; i++) colWidths[i] = avg
}
// 2. 开始拖动
const startResize = (index, e) => {
  e.preventDefault()
  resizeState.isDragging = true
  resizeState.activeIndex = index // 0, 1, 2
  resizeState.startX = e.clientX
  
  // 记录当前受影响的两列（左侧列 和 右侧列）的初始宽度
  resizeState.startLeftW = colWidths[index]
  resizeState.startRightW = colWidths[index + 1]

  // 全局监听
  document.addEventListener('mousemove', onMouseMove)
  document.addEventListener('mouseup', stopResize)
  document.body.style.cursor = 'col-resize' // 强制光标
  document.body.style.userSelect = 'none'   // 防止选中文字
}
// 3. 拖动中
const onMouseMove = (e) => {
  if (!resizeState.isDragging) return
  
  const idx = resizeState.activeIndex
  const delta = e.clientX - resizeState.startX
  
  // 理论新宽度
  let newLeft = resizeState.startLeftW + delta
  let newRight = resizeState.startRightW - delta
  
  // 限制逻辑 (Constraint Logic)
  // 如果左边太小
  if (newLeft < MIN_WIDTH) {
    const diff = MIN_WIDTH - newLeft
    newLeft = MIN_WIDTH
    newRight -= diff // 右边吐出来
  }
  // 如果右边太小
  if (newRight < MIN_WIDTH) {
    const diff = MIN_WIDTH - newRight
    newRight = MIN_WIDTH
    newLeft -= diff // 左边吐出来
  }
  
  // 赋值
  colWidths[idx] = newLeft
  colWidths[idx + 1] = newRight
}
// 4. 停止拖动
const stopResize = () => {
  resizeState.isDragging = false
  resizeState.activeIndex = -1
  document.removeEventListener('mousemove', onMouseMove)
  document.removeEventListener('mouseup', stopResize)
  document.body.style.cursor = ''
  document.body.style.userSelect = ''
}
// 5. 窗口缩放自适应 (高级功能)
// 当用户缩放浏览器时，我们希望按当前比例重新缩放所有列，而不是写死像素导致溢出
let resizeObserver = null

// 渲染时初始化
onMounted(() => {
  console.log("应用已启动，正在初始化存储……")
  store.initialize()  // 初始化存储（加载数据）

  // === 动态尺寸调整 ===
  distributeEvenly()  // 初始平均分配宽度
  // 监听容器尺寸变化
  if (containerRef.value) {
    resizeObserver = new ResizeObserver((entries) => {
      for (let entry of entries) {
        const newTotalWidth = entry.contentRect.width
        // 计算当前总宽度（可能和新宽度不一致）
        const currentTotalWidth = colWidths.reduce((a, b) => a + b, 0)
        
        if (currentTotalWidth === 0) return distributeEvenly()
        
        // 按比例缩放每一列
        const scale = newTotalWidth / currentTotalWidth
        for (let i = 0; i < 4; i++) {
          colWidths[i] = colWidths[i] * scale
        }
      }
    })
    resizeObserver.observe(containerRef.value)
  }
})

// 卸载时清理
onUnmounted(() => {
  if (resizeObserver) resizeObserver.disconnect()
  stopResize() // 保险起见清理事件
})
</script>

<script>
/**
 * ============================================================
 * 高级调节线组件 (Functional Component)
 * 特点：
 * 1. 视觉上很细致，但感应区域大 (w-4 + -mx-2)
 * 2. 带有高亮状态和 Hover 动画
 * ============================================================
 */
const Resizer = (props, { emit }) => {
  return h('div', {
    // 容器：透明，宽热区，z-index高，负margin抵消宽度以保持布局紧凑
    class: [
      'w-4 h-full cursor-col-resize z-50 flex justify-center items-center flex-shrink-0 -mx-2 select-none outline-none touch-none', 
      'group' // 用于 hover 状态控制子元素
    ],
    onMousedown: (e) => emit('mousedown', e)
  }, [
    // 视觉线：平时是细线，Active/Hover 时变色
    h('div', {
      class: [
        'w-[1px] rounded-full transition-all duration-200 ease-out pointer-events-none',
        // 高度变化：平时短一点显得优雅，交互时变全高
        props.active ? 'h-9/10' : 'h-2/5 group-hover:h-8/10',
        // 颜色与发光变化
        props.active 
          ? 'bg-accent-special w-[2px] shadow-[0_0_10px_rgba(var(--color-accent-special),0.8)]' 
          : 'bg-white/10 group-hover:bg-accent-special/50'
      ]
    })
  ])
}

</script>

<style>

</style>