<template>
  <div class="relative h-dvh w-screen flex flex-col p-1 overflow-hidden font-sans bg-bg-deep text-text-main select-none">
    <RimHeader/>
    <!-- 容器：深色背景，添加内边距 制造悬浮感 -->
    <div ref="containerRef" class="flex flex-1 w-full overflow-hidden relative ">
      
      <!-- ================= COLUMN 1: 详情 (Details) ================= -->
      <div class="h-full p-1 relative transition-opacity min-w-[230px]"
          :style="{ width: colWidths[0] + 'px' }">
          <div class="h-full rounded-2xl overflow-hidden bg-bg-surface/40 backdrop-blur-sm border border-white/5 shadow-2xl">
            <ModDetails />
          </div>
      </div>

      <!-- 分割线 1 -->
      <Resizer :active="resizeState.activeIndex === 0" 
               @mousedown="startResize(0, $event)" />


      <!-- ================= COLUMN 2: 待选库 (Library) ================= -->
      <div class="h-full p-1 transition-opacity" :style="{ width: colWidths[1] + 'px' }">
           <ModList v-model="store.inactiveIds" title="未启用" listColor="primary" listId="inactive" />
      </div>

      <!-- 分割线 2 -->
      <Resizer :active="resizeState.activeIndex === 1" 
               @mousedown="startResize(1, $event)" />

      <!-- ================= COLUMN 3: 启用/排序 (Active) ================= -->
      <div class="h-full p-1 transition-opacity"
           :style="{ width: colWidths[2] + 'px' }">
            <ModList v-model="store.activeIds" title="启用" :hasSidebar=true listColor="success" listId="active" />
      </div>

      <!-- 分割线 3 -->
      <Resizer :active="resizeState.activeIndex === 2" 
               @mousedown="startResize(2, $event)" />


      <!-- ================= COLUMN 4: 辅助/分组 (Tabs) ================= -->
      <div class="h-full p-1 flex flex-col transition-opacity relative"
           :style="{ width: colWidths[3] + 'px' }">
          <div class="flex-1 overflow-hidden grid grid-cols-1 grid-rows-1">
            <Transition
              enter-active-class="transition-opacity duration-300 ease-out"
              enter-from-class="opacity-0"
              enter-to-class="opacity-100"
              leave-active-class="transition-opacity duration-300 ease-in"
              leave-from-class="opacity-100"
              leave-to-class="opacity-0">
              <KeepAlive>

                <ModList v-if="activeTab === tabs[0]" v-model="store.tempIds" title="temp" listColor="warning" listId="temp"
                  class="rounded-b-none col-start-1 row-start-1 w-full"/>
                <GroupList v-else-if="activeTab === tabs[1]" v-model="store.groupList" title="Groups" listColor="special" 
                  class="rounded-b-none col-start-1 row-start-1 w-full"/>
                <BackupList v-else-if="activeTab === tabs[2]" class="rounded-b-none col-start-1 row-start-1 w-full"/>

              </KeepAlive>
            </Transition>
          </div>

          <!-- 标签页切换 -->
          <div class="absolute left-7 top-2.5 flex text-sm font-bold ">
            <FocusTabs v-model="activeTab" :tabs="tabs" 
            :blurAmount="3" borderColor="#059669" class=" top-0 opacity-100"
            />
          </div>
          
          <!-- 按钮组 -->
          <div class="p-3 rounded-b-2xl grid grid-cols-2 gap-2 bg-bg-surface/80 shadow-2xl backdrop-blur-md border-t border-white/5">
            
            <!-- 刷新按钮 -->
            <button :class="{'scan': store.scanProgress.scanning}"
              class="col-span-1 py-1 rounded-lg bg-white/5 border border-white/5 
                     text-sm text-gray-300 font-bold uppercase tracking-wider
                     hover:bg-white/10 hover:text-white hover:border-white/20
                     active:scale-95 transition-all duration-200 group flex items-center justify-center gap-1"
              @click="store.scanMods()"
              :disabled="store.scanProgress.scanning"
            >
              <!-- <svg v-if="store.scanProgress.scanning" class="animate-spin w-3 h-3 text-accent-primary" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg> -->
              <span >{{ store.scanProgress.scanning ? '扫描中...' : '刷新' }}</span>
            </button>

            <!-- 保存按钮 (Dirty 状态提示) -->
            <button class="col-span-1 py-1 rounded-lg text-sm font-bold uppercase tracking-wider
                     flex items-center justify-center gap-1 transition-all duration-300 relative overflow-hidden"
              :class="[store.isDirty 
                  ? 'bg-accent-warn text-black hover:bg-yellow-400 shadow-[0_0_15px_rgba(234,179,8,0.4)] animate-pulse-soft' 
                  : 'bg-accent-primary text-black hover:bg-cyan-400 shadow-lg shadow-accent-primary/10'
              ]"
              @click="store.saveLoadOrder()"
            >
              <!-- Dirty 状态下的流光效果 -->
              <div v-if="store.isDirty" class="absolute inset-0 bg-white/20 -translate-x-full animate-shimmer skew-x-12"></div>
              
              <svg v-if="store.isDirty" class="w-3 h-3" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M15.2 3a2 2 0 0 1 1.4.6l3.8 3.8a2 2 0 0 1 .6 1.4V19a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z"/><path d="M17 21v-8H7v8"/><path d="M7 3v5h8"/></svg>
              <svg v-else class="w-3 h-3" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg>
              
              <span>{{ store.isDirty ? '保存变动' : '保存' }}</span>
            </button>

            <!-- 启动游戏 -->
            <button class="col-span-2 py-3 mt-1 rounded-lg bg-accent-success text-white text-mdfont-bold 
                     shadow-lg shadow-accent-success/20 flex items-center justify-center gap-2 
                     transition-all duration-200 uppercase tracking-widest
                     hover:bg-[#059669] hover:shadow-accent-success/40 hover:-translate-y-0.5 active:translate-y-0 active:scale-[0.98]"
              @click="store.launchGame()"
            >
              <svg class="w-4 h-4 fill-current" viewBox="0 0 24 24"><path d="M5 3l14 9-14 9V3z"/></svg>
              启动游戏
            </button>
          </div>

      </div>

    </div>
    <!-- 列表对比抽屉 -->
    <Teleport to="body">
      <Transition 
        enter-active-class="transition-transform duration-300 ease-out"
        enter-from-class="-translate-x-full"
        enter-to-class="translate-x-0"
        leave-active-class="transition-transform duration-300 ease-in"
        leave-from-class="translate-x-0"
        leave-to-class="-translate-x-full"
      >
        <div v-if="store.showDiffDrawer" 
          class="fixed inset-y-8 top-18 left-0 w-[50vw] z-100 flex flex-col"
        >
          <!-- 
            核心修改区域：
            为了方便定位附属的边角，我们将原有的样式拆分。
            外层 div 负责定位和尺寸，内层 div 负责样式（模糊、边框、背景）。
          -->

          <!-- 1. 上方内凹边角 -->
          <div class="absolute -top-4.5 left-0 w-5 h-5 z-10">
            <!-- 模糊与背景层：利用 mask 裁剪出内凹形状 -->
            <div class="w-full h-full bg-bg-surface/80 
              mask-[radial-gradient(circle_at_100%_0,transparent_1.25rem,black_1rem)]">
            </div>
            <!-- 边框层：SVG 绘制弧线 -->
            <svg class="absolute inset-0 w-full h-full text-white/10 fill-none pointer-events-none" viewBox="0 0 20 20">
              <!-- 从左上(0,0) 画弧到 右下(20,20) -->
              <path d="M0,0 A20,20 0 0,0 20,20" stroke="currentColor" stroke-width="1" />
            </svg>
          </div>

          <!-- 2. 抽屉主体 -->
          <div class="flex-1 flex flex-col bg-transparent backdrop-blur-xl rounded-r-2xl border-y border-r border-white/10 shadow-2xl overflow-hidden relative">
            
            <!-- 抽屉内容：Diff 组件 -->
            <div class="flex-1 overflow-hidden">
                <ListDiffView v-if="store.showDiffDrawer"
                  :list-a="store.activeIds" title-a="当前启用"
                  :list-b="store.backupIds||[]" title-b="对比文件"
                  class="rounded-b-none rounded-tl-none col-start-1 row-start-1 w-full"
                />
            </div>
            
            <!-- 底部动作栏 -->
            <div class="p-2 px-5 bg-black/20 flex items-center justify-between border-t border-white/5">
              <h2 class="text-white/80 font-bold">Mod序列对比</h2>
              <div class="flex items-center gap-2">
                <button @click="store.applyBackup()" class="px-3 py-1.5 rounded-lg bg-accent-success/20 hover:bg-accent-success/40 text-accent-success border border-accent-success/30 text-xs font-bold transition-all">加载文件序列</button>
                <button @click="store.showDiffDrawer = false" class="px-3 py-1.5 rounded-lg bg-accent-danger/10 hover:bg-accent-danger/20 text-text-dim border border-white/10 text-xs font-bold transition-all">关闭</button>
              </div>
            </div>

          </div>

          <!-- 3. 下方内凹边角 -->
          <div class="absolute -bottom-[19px] left-0 w-5 h-5 z-10">
            <!-- 模糊与背景层 -->
            <div class="w-full h-full bg-transparent backdrop-blur-xl mask-[radial-gradient(circle_at_100%_100%,transparent_1.25rem,black_1.3rem)]">
            </div>
            <!-- 边框层 -->
            <svg class="absolute inset-0 w-full h-full text-white/10 fill-none pointer-events-none" viewBox="0 0 20 20">
              <!-- 从右上(20,0) 画弧到 左下(0,20) -->
              <path d="M20,0 A20,20 0 0,0 0,20" stroke="currentColor" stroke-width="1" />
            </svg>
          </div>

        </div>
      </Transition>
    </Teleport>

    <!-- 日志 --><!-- translate-x-1/2  -->
    <div v-show="store.showLogDrawer" @click.self="store.showLogDrawer = false" class="fixed top-0 left-0 w-full h-full p-20 bg-black/50 backdrop-blur-2xl rounded-lg z-999">
      <LogViewer />
    </div>

    <!-- 测试 -->
    <div v-show="store.showTestDrawer" class="fixed bottom-4 left-4 w-5/9 h-7/9 bg-black/50 backdrop-blur-md p-4 border border-white/10 overflow-auto z-999">
      <Temp2 />
      <Temp3 />
      <Temp4 />
    </div>

    <!-- 状态条 -->
    <StatusBar class="relative z-20 flex-none" />

    <!-- 右键菜单 -->
    <ContextMenu />

    <!-- 悬浮面板 -->
    <HoverPanel />

    <!-- 重复包名冲突弹窗 -->
    <ConflictResolver />
    
    <!-- 设置弹窗 -->
    <SettingsModal />

  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onUnmounted, h } from 'vue'
import { useModStore } from './stores/modStore'
import RimHeader from './components/RimHeader.vue'
import ModDetails from './components/ModDetails.vue'
import ModList from './components/ModList.vue'
import GroupList from './components/GroupList.vue'
import SettingsModal from './components/SettingsPanel.vue'
import StatusBar from './components/StatusBar.vue'
import FocusTabs from './components/utils/FocusTabs.vue'
import ContextMenu from './components/ContextMenu.vue'
import HoverPanel from './components/HoverPanel.vue'
import BackupList from './components/BackupList.vue'
import ListDiffView from './components/ListDiffView.vue'
import LogViewer from './components/LogViewer.vue'
import ConflictResolver from './components/ConflictResolver.vue'
import Temp3 from './components/utils/temp3.vue'
import Temp2 from './components/utils/temp2.vue'
import Temp4 from './components/utils/temp4.vue'



const store = useModStore()

const tabs = ['临时', '分组', '备份']
const activeTab = ref(tabs[0])

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

<style scoped>
/* 自定义动画 Keyframes */
@keyframes shimmer {
  0% { transform: translateX(-100%) skewX(-12deg); }
  100% { transform: translateX(200%) skewX(-12deg); }
}
.animate-shimmer {
  animation: shimmer 2s infinite linear;
}

@keyframes pulse-soft {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.95; transform: scale(0.98); }
}
.animate-pulse-soft {
  animation: pulse-soft 2s ease-in-out infinite;
}

/* Vue Transition */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

/* 扫描效果 */
.scan {
  position: relative;
  font-weight: 600;
}
.scan span {
  animation: cut 2s infinite;
  transition: 1s cubic-bezier(0.175, 0.885, 0.32, 1.275);
}
.scan:hover {
  scale: 1.05;
}
.scan::after {
  position: absolute;
  content: "";
  width: 100%;
  height: 6px;
  border-radius: 4px;
  background-color: rgba(0, 242, 234, 0.5);
  top: 0px;
  filter: blur(10px);
  animation: scan 2s infinite;
  left: 0;
  z-index: 0;
  transition: 1s cubic-bezier(0.175, 0.885, 0.32, 1.275);
}

.scan::before {
  position: absolute;
  content: "";
  width: 98%;
  height: 6px;
  background: linear-gradient(
      to bottom,
      transparent 0%,
      rgba(0, 242, 234, 0.1) 48%,
      rgba(0, 242, 234, 0.5) 50%,
      rgba(0, 242, 234, 0.1) 52%,
      transparent 100%
    );
  top: 0px;
  animation: scan 2s infinite;
  left: 1%;
  z-index: 1;
  filter: opacity(0.9);
  transition: 1s cubic-bezier(0.175, 0.885, 0.32, 1.275);
}
@keyframes scan {
  0% {
    top: 10%;
  }
  25% {
    top: 80%;
  }
  50% {
    top: 10%;
  }
  75% {
    top: 80%;
  }
}
@keyframes cut {
  0% {
    clip-path: inset(0 0 0 0);
  }
  25% {
    clip-path: inset(100% 0 0 0);
  }
  50% {
    clip-path: inset(0 0 100% 0);
  }
  75% {
    clip-path: inset(0 0 0 0);
  }
}
</style>