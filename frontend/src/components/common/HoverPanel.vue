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
        damping: hoverStore.type === 'text' ? 20 : 30, // 阻尼，文本提示可以更灵敏一点
        stiffness: 350,  // 刚度：控制回弹力度 (参考代码值)
        mass: 1          // 质量：控制惯性
      }"
    >
      <!-- 模式 A: 复杂预览卡片 (data 是对象) -->
      <div v-if="hoverStore.type === 'preview'" 
        class="relative flex flex-col h-full overflow-visible select-none"
        :style="{ 
          '--accent-rgb': hexToRgb(hoverStore.data.sign_color || '#a1a1aa'),
          '--accent': hoverStore.data.sign_color || '#a1a1aa'
        }">
        
        <!-- 悬浮装饰：分组标签 (破格设计，浮在卡片上方) -->
        <div v-if="modGroups.length" class="absolute bottom-full -mb-1 right-4 flex gap-0.5 z-0 opacity-80 ">
          <div v-for="g in modGroups" :key="g.group_id" 
               class="px-1 py-0.5 rounded-t-md text-xs font-bold shadow-lg flex items-center gap-1 border-t border-x border-text-main/10"
               :style="{ backgroundColor: g.color, color: getContrastColor(g.color) }">
             {{ g.name }}
          </div>
        </div>

        <!-- 背景层：图片 + 模糊 + 渐变 -->
        <div class="absolute inset-0 overflow-hidden rounded-xl bg-bg-deep m-0.5">
          <img v-if="hoverStore.data.preview_url" :src="hoverStore.data.preview_url" 
              class="absolute inset-0 w-full h-full object-cover opacity-90 blur-xs scale-100" />
          <!-- 渐变遮罩：底部更黑以显示文字 -->
          <div class="absolute inset-0 bg-linear-to-t from-bg-deep via-bg-deep/70 to-bg-deep/30"></div>
          <!-- 强调色光晕 -->
          <div class="absolute -top-10 -right-10 w-32 h-32 bg-[rgb(var(--accent-rgb))] opacity-20 blur-[50px] rounded-full mix-blend-screen"></div>
        </div>

        <!-- 装饰性边框 -->
        <div class="absolute inset-0 rounded-xl border-2 border-[rgb(var(--accent-rgb))] opacity-30 pointer-events-none z-0"></div>
        <div class="absolute -top-px -left-px w-8 h-8 border-t-4 border-l-4 border-[rgb(var(--accent-rgb))] rounded-tl-xl opacity-60 z-0"></div>

        <!-- 内容层 -->
        <div class="relative z-10 p-4 flex flex-col gap-1 h-full">
          
          <!-- 第一行：元数据 (ID & Ver & Type) -->
          <div class="flex items-center justify-between text-xs font-mono text-text-main/80 border-b border-text-main/5 pb-1">
            <span class="truncate opacity-70 tracking-tighter">{{ hoverStore.data.package_id }}</span>
            <div class="flex items-center gap-2 shrink-0">
              <span v-if="hoverStore.data.version" class="text-accent-primary">v{{ hoverStore.data.version }}</span>
              <!-- Mod类型徽章 -->
              <span class="px-1.5 rounded-sm bg-text-main/5 border border-text-main/10 text-text-main/80">
                {{ MOD_TYPE_MAP[modStore.displayModType(hoverStore.data)] || 'MOD' }}
              </span>
            </div>
          </div>

          <!-- 第二行：标题 -->
          <div>
            <!-- 别名 -->
            <div v-if="hoverStore.data.alias_name" class="text-xs text-text-dim truncate font-mono ">
              {{ hoverStore.data.name }}
            </div>
            <!-- 主名称 -->
            <h2 class="font-medium truncate">
              {{ modStore.displayModName(hoverStore.data) }}
            </h2>
          </div>

          <!-- 第三行：作者与语言 -->
          <div>
            <div class="flex items-center gap-2 mt-0.5">
              <span class="text-xs text-text-dim flex items-center gap-1">
                <svg class="size-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
                {{ hoverStore.data.author?.join(', ') || 'Unknown' }}
              </span>
            </div>
            <div class="flex items-center gap-2 mt-0.5">
              <span class="text-xs text-text-dim flex items-center gap-1">
                <svg class="size-3.5" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M28.2857 37H39.7143M42 42L39.7143 37L42 42ZM26 42L28.2857 37L26 42ZM28.2857 37L34 24L39.7143 37H28.2857Z" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M16 6L17 9" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M6 11H28" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M10 16C10 16 11.7895 22.2609 16.2632 25.7391C20.7368 29.2174 28 32 28 32" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M24 11C24 11 22.2105 19.2174 17.7368 23.7826C13.2632 28.3478 6 32 6 32" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg>
                {{ hoverStore.data.supported_languages?.join(', ') || 'Unknown' }}
              </span>
            </div>
            <div class="flex items-center gap-2 mt-0.5">
              <span class="text-xs text-text-dim flex items-center gap-1">
                <Milestone class="size-3.5"/>
                {{ hoverStore.data.supported_versions?.join(', ') || 'Unknown' }}
              </span>
            </div>
          </div>

          <!-- 第四行：描述/备注 -->
          <div class="grow min-h-0 relative">
            <!-- 如果有备注，显示备注(黄色)，否则显示描述 -->
            <p v-if="hoverStore.data.notes" class="text-xs text-accent-warn/90 leading-relaxed line-clamp-3 font-medium italic border-l-2 border-accent-warn pl-2">
              {{ hoverStore.data.notes }}
            </p>
            <p v-else class="text-xs text-text-dim/80 leading-relaxed line-clamp-4 font-mono">
              {{ cleanDescription }}
            </p>
          </div>

          <!-- 第五行：Tags 流 -->
          <div v-if="hoverStore.data.tags?.length" class="flex flex-wrap gap-1 mt-auto pt-2 border-t border-text-main/5">
            <span v-for="tag in hoverStore.data.tags.slice(0, 7)" :key="tag" 
                  class="text-[0.65rem] px-1.5 py-px rounded-full bg-text-main/5 text-text-main/70 border border-text-main/5 whitespace-nowrap">
              #{{ tag }}
            </span>
            <span v-if="hoverStore.data.tags.length > 7" class="text-[0.65rem] text-text-dim px-1">...</span>
          </div>

        </div>

      </div>
      <!-- 模式 B: 纯文本 Tooltip (data 是字符串) -->
      <div v-else-if="hoverStore.type === 'text'" class="text-sm font-medium text-text-main text-pretty wrap-break-word whitespace-pre-wrap">
        <!-- {{ parseMarkup(hoverStore.) }} -->
        <div v-html="parseMarkup(hoverStore.data)"></div>
      </div>
      <!-- 模式 3: 全自定义组件 -->
       <div v-else-if="hoverStore.type === 'component'">
        <component :is="hoverStore.customComponent" v-bind="hoverStore.componentProps" />
      </div>

    </Motion>
  </Teleport>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted, nextTick,h } from 'vue'
import { Milestone } from 'lucide-vue-next';
import { Motion } from 'motion-v'
import { useHoverStore } from '../../stores/hoverStore'
import { useAppStore } from '../../stores/appStore'
import { useModStore } from '../../stores/modStore'
import { useGroupStore } from '../../stores/groupStore';

const appStore = useAppStore()
const hoverStore = useHoverStore()
const modStore = useModStore()
const groupStore = useGroupStore()

// --- 1. 显隐控制逻辑 ---
const isVisible = ref(false)
const shouldRender = ref(false) // 用于控制 v-if，确保动画执行完再销毁 DOM
let showTimer = null
let hideTimer = null
const lastX = ref(0)
const lastY = ref(0)


// 监听悬停状态变化
watch(() => hoverStore.isHovering, (hovering) => {
  if (hovering) {
    if (hideTimer) clearTimeout(hideTimer) // 如果正在准备销毁，取消销毁
    shouldRender.value = true // 立即渲染 DOM
    
    if (showTimer) clearTimeout(showTimer)
    showTimer = setTimeout(() => {
      isVisible.value = true // 触发 opacity 1 动画
    }, appStore.settings.ui.tooltip_hover_time)
  } else {
    if (showTimer) clearTimeout(showTimer)
    isVisible.value = false // 触发 opacity 0 动画
    
    // 等待弹簧动画大概结束后再销毁 DOM (避免动画突然截断)
    hideTimer = setTimeout(() => {
      shouldRender.value = false
    }, 300) 
  }
})

// --- 动态样式 ---
const containerClasses = computed(() => {
  if (hoverStore.type === 'text') {
    // Tooltip 样式：紧凑、黑底白字、圆角小
    return 'px-2 py-1.5 max-w-[30dvw] rounded-md break-all text-pretty whitespace-normal bg-black/50 backdrop-blur-sm border border-text-main/20 shadow-lg'
  }
  // 让组件自己决定长什么样
  if (hoverStore.type === 'component') {
    return 'shadow-2xl' // 可能只留个阴影，或者连阴影都不要，完全由组件内部控制
  }
  // Preview 样式：宽大、有背景、圆角大
  return 'w-[340px] max-h-[240px] rounded-xl shadow-2xl overflow-visible' 
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
  if (!hoverStore.isHovering) return lastX.value
  const x = hoverStore.targetX
  const w = winWidth.value
  const pW = realWidth.value // 使用真实宽度
  
  // 策略：如果鼠标在屏幕右半边，面板就显示在鼠标左侧 (靠右基准)
  const isRightSide = x > w - pW - GAP
  
  if (isRightSide) {
    // 锚点在右侧：鼠标位置 - 面板宽度 - 间距
    // 同时也做一下左侧防溢出 (防止屏幕太窄时出界)
    lastX.value = Math.round(isRightSide ? Math.max(10, x - pW - GAP) : x + GAP)
    return lastX.value
  } else {
    // 锚点在左侧：鼠标位置 + 间距
    lastX.value = x + GAP
    return lastX.value
  }
})

const safeY = computed(() => {
  if (!hoverStore.isHovering) return lastY.value
  const y = hoverStore.targetY
  const h = winHeight.value
  const pH = realHeight.value // 使用真实高度
  
  // 策略：如果鼠标在屏幕下半边，面板就显示在鼠标上方 (底部基准)
  const isBottomSide = y > h - pH - GAP
  
  if (isBottomSide) {
    // 锚点在底部：鼠标位置 - 面板高度 - 间距
    // 这样当 pH 变大时，Y 值变小，面板视觉上是"向上生长"
    lastY.value = Math.round(isBottomSide ? Math.max(10, y - pH - GAP) : y + GAP)
    return lastY.value
  } else {
    // 锚点在顶部
    lastY.value = y + GAP
    return lastY.value
  }
})

// --- 4. 速度与倾斜计算 (核心效果) ---
let lastY_ = 0
const rotation = ref(0)
let resetRotationTimer = null

// 监听 Y 轴变化计算速度
watch(() => hoverStore.targetY, (newY) => {
  if (!isVisible.value) {
    lastY_ = newY
    return
  }

  // 计算垂直速度
  const velocityY = newY - lastY_
  lastY_ = newY

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

// --- 辅助函数：解析提示文本 (支持简单的富文本标记) ---
const parseMarkup = (text) => {
  if (!text) return ''

  // 0. 如果标记为 HTML，则直接返回
  if (hoverStore.isHtml) return text

  // 1. HTML 转义 (防止 XSS 和标签冲突)
  let html = text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;")

  // 2. 预处理换行 (支持 \n 或 | 或 ;;)
  // 建议根据习惯选一种，这里演示兼容 | 和 \n
  html = html.replace(/\n/g, '<br>')

  // 3. 语法解析规则配置
  const rules = [
    // [Custom Color] {{#hex|text}} -> <span style="color:#hex">text</span>
    { 
      regex: /\{\{(#[0-9a-fA-F]{3,6})\|(.*?)\}\}/g, 
      repl: '<span style="color: $1">$2</span>' 
    },
    // [Bold] **text** -> font-bold
    { 
      regex: /\*\*(.*?)\*\*/g, 
      repl: '<span class="font-bold text-text-main text-base">$1</span>' 
    },
    // [Italic] __text__ -> italic opacity-80
    { 
      regex: /__(.*?)__/g, 
      repl: '<span class="italic opacity-80">$1</span>' 
    },
    // [Error/Red] !!text!! -> text-red-400
    { 
      regex: /!!(.*?)!!/g, 
      repl: '<span class="text-red-400 font-bold">$1</span>' 
    },
    // [Warn/Yellow] ^^text^^ -> text-yellow-400
    { 
      regex: /\^\^(.*?)\^\^/g, 
      repl: '<span class="text-yellow-400 font-bold">$1</span>' 
    },
    // [Info/Blue] [[text]] -> text-blue-400 (类似链接)
    { 
      regex: /\[\[(.*?)\]\]/g, 
      repl: '<span class="text-accent-primary font-bold">$1</span>' 
    },
    // [Code/Mono] `text` -> bg-black/30 font-mono
    { 
      regex: /··(.*?)··/g, 
      repl: '<span class="font-mono text-xs bg-text-main/10 px-1 rounded mx-0.5 text-text-main">$1</span>' 
    }
  ]

  // 4. 执行替换
  rules.forEach(rule => {
    html = html.replace(rule.regex, rule.repl)
  })

  return html
}

// --- 辅助逻辑 ---

// 获取 Mod 所属分组
const modGroups = computed(() => {
  if (hoverStore.type !== 'preview' || !hoverStore.data) return []
  return groupStore.takeGroupsByModId(hoverStore.data.package_id)
})

// 存档破坏性 映射逻辑
const saveBreakingVal = computed(() => parseInt(hoverStore.data?.save_breaking ?? -99))

const saveBreakingColor = computed(() => {
  const v = saveBreakingVal.value
  if (v === 1) return 'text-accent-success border-accent-success/30 bg-accent-success/10' // 安全
  if (v === -1) return 'text-accent-danger border-accent-danger/30 bg-accent-danger/10' // 危险
  return 'text-text-dim border-text-main/5' // 未知
})

const saveBreakingText = computed(() => {
  const v = saveBreakingVal.value
  if (v === 1) return 'SAFE'
  if (v === -1) return 'RISK'
  return 'UNKN'
})

// 简单的 SVG 图标渲染函数
const IconSafe = () => h('svg', { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': 2 }, [h('path', { d: 'M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z' })])
const IconRisk = () => h('svg', { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': 2 }, [h('path', { d: 'M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z' }), h('line', { x1:12, y1:9, x2:12, y2:13 }), h('line', { x1:12, y1:17, x2:12, y2:17 })])
const IconUnknown = () => h('svg', { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': 2 }, [h('circle', { cx:12, cy:12, r:10 }), h('path', { d: 'M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3' }), h('line', { x1:12, y1:17, x2:12, y2:17 })])

const saveBreakingIcon = computed(() => {
  const v = saveBreakingVal.value
  if (v === 1) return IconSafe
  if (v === -1) return IconRisk
  return IconUnknown
})

// Mod 类型简写映射
const MOD_TYPE_MAP = {
  'LanguagePack': 'LANG',
  'XML': 'XML',
  'Assembly': 'DLL',
  'Texture': 'TEX',
  'Audio': 'SND',
  'Mixed': 'MIX',
  'Unknown': 'UNK'
}

// 清理描述文本 (移除 HTML 标签，只留纯文本做预览)
const cleanDescription = computed(() => {
  const desc = hoverStore.data?.description || 'No description available.'
  return desc.replace(/<[^>]+>/g, '') // 简单移除 HTML 标签
})

// 计算对比色 (用于分组标签文字颜色)
const getContrastColor = (hex) => {
  if (!hex) return '#fff'
  const r = parseInt(hex.substr(1, 2), 16)
  const g = parseInt(hex.substr(3, 2), 16)
  const b = parseInt(hex.substr(5, 2), 16)
  const yiq = ((r * 299) + (g * 587) + (b * 114)) / 1000
  return (yiq >= 128) ? '#000' : '#fff'
}

// 颜色转换工具 (如果 script 里没有的话)
const hexToRgb = (hex) => {
  if (!hex || typeof hex !== 'string') return '100, 100, 100'
  let c = hex.substring(1).split('')
  if (c.length === 3) c = [c[0], c[0], c[1], c[1], c[2], c[2]]
  c = '0x' + c.join('')
  return `${(c >> 16) & 255}, ${(c >> 8) & 255}, ${c & 255}`
}
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
  image-rendering: -webkit-optimize-contrast; 
}
</style>
