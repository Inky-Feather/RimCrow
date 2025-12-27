<template>
  <Teleport to="body">
    <!-- 
      使用 Motion 组件替换原有的 div 和 Transition 
      initial: 初始状态
      animate: 目标状态 (位置、旋转、透明度)
      transition: 动画物理参数 (Spring 效果核心)
    -->
    <Motion v-if="shouldRender" ref="panelRef"
      class="gpu-text-fix fixed top-0 left-0 z-9999 pointer-events-none will-change-transform"
      :class="containerClasses" :initial="{ opacity: 0, scale: 0.9 }"
      :animate="{
        x: safeX,
        y: safeY,
        rotate: rotation, // 文本模式下我们可以减小旋转幅度，或者直接设为0
        opacity: isVisible ? 1 : 0,
        scale: isVisible ? 1 : 0.9
      }"
      :transition="{
        type: 'spring',
        damping: store.type === 'text' ? 20 : 30, // 阻尼，文本提示可以更灵敏一点
        stiffness: 350,  // 刚度：控制回弹力度 (参考代码值)
        mass: 1          // 质量：控制惯性
      }"
    >
      <!-- 模式 A: 复杂预览卡片 (data 是对象) -->
      <div v-if="store.type === 'preview'" class="flex flex-col gap-3">
        <!-- 预览图区域 -->
        <div class="relative w-full h-32 rounded-lg overflow-hidden bg-black/50 border border-white/5 group">
          <img 
            v-if="store.data?.preview_url" 
            :src="store.data.preview_url" 
            class="w-full h-full object-cover transition-transform duration-700 group-hover:scale-110"
          />
          <div v-else class="w-full h-full flex items-center justify-center text-text-dim text-xs">
            无预览图
          </div>
          
          <!-- 版本号 -->
          <div class="absolute bottom-2 right-2">
            <span v-if="store.data?.version" class="px-1.5 py-0.5 rounded bg-black/60 backdrop-blur-sm text-white text-[10px] font-mono border border-white/10">
              v{{ store.data.version }}
            </span>
          </div>
        </div>

        <!-- 文本信息 -->
        <div>
          <h3 class="font-bold text-text-main text-sm leading-tight mb-1 line-clamp-1">{{ store.data?.name }}</h3>
          <p class="text-xs text-text-dim mb-2 flex items-center gap-1">
            <span>{{ store.data?.author }}</span>
            <span v-if="store.data?.source === 'steam'" class="text-[9px] px-1 bg-[#1b2838] text-blue-300 rounded">Steam</span>
          </p>
          
          <p class="text-[10px] text-text-dim/80 line-clamp-3 leading-relaxed font-mono">
            {{ store.data?.description }}
          </p>
        </div>
        
        <!-- 底部 Tags -->
        <div class="pt-2 border-t border-white/5 flex flex-wrap gap-1" v-if="store.data?.tags?.length">
          <span v-for="tag in store.data.tags.slice(0, 5)" :key="tag" 
            class="text-[9px] px-1.5 py-0.5 rounded-md bg-accent-primary/10 text-accent-primary border border-accent-primary/10">
            {{ tag }}
          </span>
        </div>
      </div>
      <!-- 模式 B: 纯文本 Tooltip (data 是字符串) -->
      <div v-else-if="store.type === 'text'" class="text-xs font-medium text-white">
        {{ store.data }}
      </div>
      <!-- 模式 3: 全自定义组件 -->
       <div v-else-if="store.type === 'component'">
        <component :is="store.customComponent" v-bind="store.componentProps" />
      </div>

    </Motion>
  </Teleport>
</template>

<script setup>
import { useHoverStore } from '../stores/hoverStore'
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { Motion } from 'motion-v'

const store = useHoverStore()

// --- 1. 显隐控制逻辑 ---
const isVisible = ref(false)
const shouldRender = ref(false) // 用于控制 v-if，确保动画执行完再销毁 DOM
let showTimer = null
let hideTimer = null
const DELAY_MS = 1000


// --- 动态样式 ---
const containerClasses = computed(() => {
  if (store.type === 'text') {
    // Tooltip 样式：紧凑、黑底白字、圆角小
    return 'px-2 py-1.5 max-w-[30dvw] rounded-md break-all text-pretty whitespace-normal bg-black/50 backdrop-blur-sm border border-white/20 shadow-lg'
  }
  // 让组件自己决定长什么样
  if (store.type === 'component') {
    return 'shadow-2xl' // 可能只留个阴影，或者连阴影都不要，完全由组件内部控制
  }
  // Preview 样式：宽大、有背景、圆角大
  return 'p-4 w-[320px] rounded-xl border border-white/10 bg-bg-deep/90 backdrop-blur-xl shadow-2xl flex flex-col gap-3'
})

watch(() => store.isHovering, (hovering) => {
  if (hovering) {
    if (hideTimer) clearTimeout(hideTimer) // 如果正在准备销毁，取消销毁
    shouldRender.value = true // 立即渲染 DOM
    
    if (showTimer) clearTimeout(showTimer)
    showTimer = setTimeout(() => {
      isVisible.value = true // 触发 opacity 1 动画
    }, DELAY_MS)
  } else {
    if (showTimer) clearTimeout(showTimer)
    isVisible.value = false // 触发 opacity 0 动画
    
    // 等待弹簧动画大概结束后再销毁 DOM (避免动画突然截断)
    hideTimer = setTimeout(() => {
      shouldRender.value = false
    }, 300) 
  }
})

// --- 2. 窗口尺寸监听 ---
const winWidth = ref(window.innerWidth)
const winHeight = ref(window.innerHeight)
const updateSize = () => {
  winWidth.value = window.innerWidth
  winHeight.value = window.innerHeight
}
onMounted(() => window.addEventListener('resize', updateSize))
onUnmounted(() => window.removeEventListener('resize', updateSize))

// --- 3. 动态位置计算 (边界检测) ---
const panelRef = ref(null)
const realWidth = ref(320) // 默认值
const realHeight = ref(200) // 默认值
// 更新尺寸的方法
const updateDimensions = () => {
  if (panelRef.value?.$el) { // motion-v 组件通常通过 $el 访问 DOM
    const el = panelRef.value.$el
    realWidth.value = el.offsetWidth
    realHeight.value = el.offsetHeight
  } else if (panelRef.value instanceof HTMLElement) {
    // 兼容普通 DOM ref
    realWidth.value = panelRef.value.offsetWidth
    realHeight.value = panelRef.value.offsetHeight
  }
}

// 监听 DOM 尺寸变化 (关键：处理图片加载或内容撑开)
let resizeObserver = null
watch(() => shouldRender.value, (render) => {
  if (render) {
    nextTick(() => {
      // 尝试获取 DOM 元素
      const el = panelRef.value?.$el || panelRef.value
      if (el) {
        // 立即测量一次
        updateDimensions()
        // 启动监听
        if (!resizeObserver) {
          resizeObserver = new ResizeObserver(() => updateDimensions())
        }
        resizeObserver.observe(el)
      }
    })
  } else {
    // 销毁监听
    if (resizeObserver) resizeObserver.disconnect()
  }
})


// --- 智能坐标计算 (核心算法) ---
const GAP = 16 // 鼠标与面板的间距

const safeX = computed(() => {
  const x = store.targetX
  const w = winWidth.value
  const pW = realWidth.value // 使用真实宽度
  
  // 策略：如果鼠标在屏幕右半边，面板就显示在鼠标左侧 (靠右基准)
  const isRightSide = x > w - pW - GAP
  
  if (isRightSide) {
    // 锚点在右侧：鼠标位置 - 面板宽度 - 间距
    // 同时也做一下左侧防溢出 (防止屏幕太窄时出界)
    return Math.round(isRightSide ? Math.max(10, x - pW - GAP) : x + GAP)
  } else {
    // 锚点在左侧：鼠标位置 + 间距
    return x + GAP
  }
})

const safeY = computed(() => {
  const y = store.targetY
  const h = winHeight.value
  const pH = realHeight.value // 使用真实高度
  
  // 策略：如果鼠标在屏幕下半边，面板就显示在鼠标上方 (底部基准)
  const isBottomSide = y > h - pH - GAP
  
  if (isBottomSide) {
    // 锚点在底部：鼠标位置 - 面板高度 - 间距
    // 这样当 pH 变大时，Y 值变小，面板视觉上是"向上生长"
    return Math.round(isBottomSide ? Math.max(10, y - pH - GAP) : y + GAP)
  } else {
    // 锚点在顶部
    return y + GAP
  }
})


// --- 4. 速度与倾斜计算 (核心效果) ---
let lastY = 0
const rotation = ref(0)
let resetRotationTimer = null

// 监听 Y 轴变化计算速度
watch(() => store.targetY, (newY) => {
  if (!isVisible.value) {
    lastY = newY
    return
  }

  // 计算垂直速度
  const velocityY = newY - lastY
  lastY = newY

  // 参考代码的核心算法: rotate = -velocityY * 0.6
  // 这会产生当鼠标快速向下移动时，卡片顶部向后仰的效果
  const sensitivity = 0.6 
  const maxRotation = 10
  
  // 计算目标角度并限制最大值
  const targetRotation = Math.max(Math.min(-velocityY * sensitivity, maxRotation), -maxRotation)
  
  rotation.value = targetRotation

  // 鼠标停止后回正
  if (resetRotationTimer) clearTimeout(resetRotationTimer)
  resetRotationTimer = setTimeout(() => {
    rotation.value = 0
  }, 100)
})
</script>

<style scoped>
/* 文字渲染优化 */
.gpu-text-fix {
  /* 1. 防止 3D 变换时的边缘闪烁 */
  /* -webkit-backface-visibility: hidden;
  backface-visibility: hidden; */

  /* 2. 强制开启硬件加速 (有时能解决抖动) */
  transform: translateZ(0);

  /* 3. 使用灰阶抗锯齿，文字会变细一点但更清晰 */
  /* -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale; */
  
  /* 4. 优化图片和合成层的渲染质量 */
  /* image-rendering: -webkit-optimize-contrast;  */
}
</style>
