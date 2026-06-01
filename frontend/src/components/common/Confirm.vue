<template>
  <Teleport to="body">
    <!-- 统一过渡容器 -->
    <Transition :name="isMini ? 'mini-zoom' : 'modal-fade'">
      <div v-if="confirmStore.isVisible"
        class="fixed inset-0 z-9999 font-sans text-text-main selection:bg-bg-overlay/10"
        :class="isMini ? 'pointer-events-none' : 'flex items-center justify-center'"
        @keydown.esc="handleCancel"
        @keydown.enter="handleEnterKey"
      >

        <!-- 1. 全屏模式下的环境光遮罩 -->
        <div v-if="!isMini" @mousedown="handleBackdropClick" class="absolute inset-0 bg-bg-deep/20 backdrop-blur-xs transition-opacity duration-500"></div>

        <!-- 2. 弹窗主体容器 -->
        <div ref="modalRef"
          class="relative flex flex-col overflow-hidden transition-all pointer-events-auto box-border"
          :class="[
            // 核心质感：极深色玻璃 + 顶部高光边框 + 强阴影
            'bg-glass-heavy backdrop-blur-2xl shadow-2xl ring-1 ring-border-base/10',
            // 模式区分
            isMini
              ? 'rounded-xl w-80 absolute shadow-[0_20px_30px_var(--shadow-color)]'
              : 'rounded-2xl w-140 max-w-[90vw] shadow-[0_20px_50px_var(--shadow-color)]',
            // 抖动动画类
            shake ? 'animate-shake' : ''
          ]"
          :style="containerStyle"
        >
          <!-- A. 顶部装饰光条 (根据类型变色) -->
          <div class="absolute top-0 inset-x-0 h-px bg-linear-to-r from-transparent via-current to-transparent opacity-80 shadow-[0_0_15px_currentColor]" :class="theme.text"></div>

          <!-- B. 内部环境光晕 (氛围感) -->
          <div class="absolute -top-20 -right-20 w-48 h-48 rounded-full blur-3xl opacity-15 pointer-events-none"
               :class="theme.bg"></div>

          <!-- C. 内容区域 -->
          <div class="flex relative z-10" :class="isMini ? 'p-3 pb-2 gap-2' : 'p-6 pb-4 gap-5'">

            <!-- 左侧：全息图标容器 -->
            <div class="shrink-0 pt-1">
              <div class="relative flex items-center justify-center"
                :class="isMini ? 'w-8 h-8' : 'w-12 h-12 '">
                <!-- 图标背景框 -->
                <div class="absolute inset-0 rounded-xl opacity-20" :class="theme.text"></div>
                <div class="absolute inset-0 rounded-xl opacity-10 bg-current blur-lg" :class="theme.text"></div>
                <!-- 核心图标 -->
                <component :is="theme.icon" class="w-6 h-6 stroke-2 relative z-10 drop-shadow-md" :class="theme.text" />
                <!-- 呼吸光效 -->
                <div class="absolute inset-0 rounded-xl bg-current blur-md opacity-20 animate-pulse-slow" :class="theme.text"></div>
              </div>
            </div>

            <!-- 右侧：文本与交互 -->
            <div class="flex-1 min-w-0 flex flex-col justify-center">
              <h3 class="text-base font-bold text-text-main tracking-wide text-wrap break-all leading-snug mb-1.5 flex items-center gap-2">
                {{ confirmStore.state.title }}
              </h3>

              <div v-if="confirmStore.state.message" class="text-xs text-text-dim leading-relaxed text-pretty font-medium">
                <span v-if="confirmStore.state.isHtml" v-html="confirmStore.state.message" class="text-wrap break-all"></span>
                <span v-else class="text-wrap break-all">{{ confirmStore.state.message }}</span>
              </div>
            </div>
          </div>

          <!-- 输入框容器 -->
          <div class="p-2">
            <!-- Prompt 输入框 -->
            <div v-if="confirmStore.state.mode === 'prompt'" class="relative group">
              <input v-model="confirmStore.state.inputValue"
                ref="inputRef" type="text" spellcheck="false"
                :placeholder="confirmStore.state.placeholder"
                class="input-glass block w-full px-2 py-1 font-mono text-sm text-text-main placeholder:text-text-disabled focus:outline-none"
              />
              <!-- 输入框角落装饰 -->
              <div class="absolute bottom-0 right-0 w-2 h-2 border-b border-r border-border-base/18 rounded-br-lg pointer-events-none group-focus-within:border-border-base/10 transition-colors"></div>
            </div>

            <div v-else-if="confirmStore.state.showDeleteOptions" class="space-y-2">
              <label class="flex items-start gap-3 rounded-xl border border-border-base/10 bg-bg-inset/60 px-3 py-2 cursor-pointer transition-colors hover:border-border-base/18">
                <input
                  v-model="confirmStore.state.forceDelete"
                  class="mt-0.5 accent-accent-danger"
                  type="radio"
                  :value="false"
                  name="delete-mode"
                >
                <div class="min-w-0">
                  <div class="text-sm font-semibold text-text-main">{{ confirmStore.state.trashOptionText }}</div>
                  <div class="text-xs text-text-dim leading-relaxed">更安全，文件会进入系统回收站，可在系统中恢复。</div>
                </div>
              </label>

              <label class="flex items-start gap-3 rounded-xl border border-accent-danger/25 bg-accent-danger/8 px-3 py-2 cursor-pointer transition-colors hover:border-accent-danger/40">
                <input
                  v-model="confirmStore.state.forceDelete"
                  class="mt-0.5 accent-accent-danger"
                  type="radio"
                  :value="true"
                  name="delete-mode"
                >
                <div class="min-w-0">
                  <div class="text-sm font-semibold text-accent-danger">{{ confirmStore.state.forceOptionText }}</div>
                  <div class="text-xs text-text-dim leading-relaxed">直接彻底删除，不进入回收站，通常无法恢复。</div>
                </div>
              </label>

              <p v-if="confirmStore.state.deleteOptionsHint" class="px-1 text-xs leading-relaxed text-text-dim">
                {{ confirmStore.state.deleteOptionsHint }}
              </p>
            </div>

            <!-- 队列弹窗条目区：每个检查项独立处理，成功后由 store 从列表移除。 -->
            <div v-else-if="confirmStore.state.promptItems?.length" class="space-y-2 max-h-[46vh] overflow-y-auto pr-1">
              <div
                v-for="item in confirmStore.state.promptItems"
                :key="item.id"
                class="rounded-xl border border-border-base/10 bg-bg-inset/60 px-3 py-2"
              >
                <div class="flex items-start justify-between gap-3">
                  <div class="min-w-0">
                    <div class="text-sm font-semibold text-text-main break-all">{{ item.title }}</div>
                    <div v-if="item.description" class="mt-1 text-xs text-text-dim leading-relaxed break-all">{{ item.description }}</div>
                    <div v-if="item.meta?.length" class="mt-1 flex flex-wrap gap-1">
                      <span
                        v-for="meta in item.meta"
                        :key="meta"
                        class="rounded-md border border-border-base/10 bg-bg-overlay/5 px-1.5 py-0.5 text-[10px] text-text-dim"
                      >
                        {{ meta }}
                      </span>
                    </div>
                    <div
                      v-if="item.statusMessage"
                      class="mt-1 text-xs"
                      :class="item.status === 'failed' ? 'text-accent-danger' : item.status === 'success' ? 'text-accent-success' : 'text-text-dim'"
                    >
                      {{ item.statusMessage }}
                    </div>
                  </div>
                  <div class="shrink-0 flex flex-wrap justify-end gap-1">
                    <button
                      v-for="action in item.actions"
                      :key="action.id"
                      :disabled="item.status !== 'pending' || confirmStore.state.isResolving"
                      @click="confirmStore.choosePromptItemAction(item.id, action.id)"
                      class="rounded-lg px-2 py-1 text-xs font-bold transition-all disabled:cursor-not-allowed disabled:opacity-50"
                      :class="action.kind === 'primary'
                        ? `${theme.btnBg} text-on-accent-primary`
                        : action.kind === 'danger'
                          ? 'bg-accent-danger/90 text-on-accent-danger'
                          : 'text-text-dim hover:text-text-main hover:bg-bg-overlay/10 border border-border-base/5'"
                    >
                      {{ action.label }}
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- D. 底部操作栏 (玻璃分割线) -->
          <div class="modal-footer flex items-center justify-end gap-3"
            :class="isMini ? 'px-2 py-1' : 'px-4 py-2'">

            <!-- 自定义底部按钮用于“全部处理/全部稍后”等窗口级动作，保持普通确认弹窗的旧按钮逻辑不变。 -->
            <template v-if="Array.isArray(confirmStore.state.actionButtons) && confirmStore.state.actionButtons.length > 0">
              <button
                v-for="action in confirmStore.state.actionButtons"
                :key="action.value?.action || action.label"
                :disabled="confirmStore.state.isResolving"
                @click="confirmStore.chooseAction(action.value)"
                class="rounded-lg text-xs font-bold transition-all duration-200 disabled:cursor-not-allowed disabled:opacity-50"
                :class="[
                  isMini ? 'px-2 py-1' : 'px-4 py-1.5',
                  action.kind === 'primary'
                    ? `${theme.btnBg} text-on-accent-primary shadow-lg`
                    : action.kind === 'danger'
                      ? 'bg-accent-danger/90 text-on-accent-danger shadow-lg shadow-accent-danger/20'
                      : 'text-text-dim hover:text-text-main hover:bg-bg-overlay/10 border border-transparent hover:border-border-base/5'
                ]"
              >
                {{ action.label }}
              </button>
            </template>

            <!-- Cancel Button -->
            <button v-else-if="confirmStore.state.mode !== 'alert'"
              @click="handleCancel"
              class=" rounded-lg text-xs font-bold text-text-dim hover:text-text-main hover:bg-bg-overlay/10 border border-transparent hover:border-border-base/5 transition-all duration-200"
              :class="isMini ? 'px-2 py-1' : 'px-4 py-1.5'">
              {{ confirmStore.state.cancelText }}
            </button>

            <!-- Confirm Button (流光按钮) -->
            <button v-if="!confirmStore.state.actionButtons?.length"
              @click="handleConfirm"
              class="relative overflow-hidden  rounded-lg text-xs font-bold text-on-accent-primary shadow-lg transition-transform active:scale-95 group/btn"
              :class="[theme.btnBg, isMini ? 'px-3 py-1' : 'px-6 py-1.5']"
            >
              <!-- 按钮内部高光扫描动画 -->
              <div class="absolute inset-0 -translate-x-full group-hover/btn:translate-x-full transition-transform duration-700 bg-linear-to-r from-transparent via-text-main/40 to-transparent skew-x-12"></div>

              <div class="relative flex items-center gap-1.5">
                <span>{{ confirmStore.state.confirmText }}</span>
                <svg v-if="confirmStore.state.mode === 'prompt'" class="w-3 h-3 opacity-60 group-hover/btn:translate-x-0.5 transition-transform" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="9 18 15 12 9 6"></polyline></svg>
              </div>
            </button>
          </div>

        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
import { computed, ref, nextTick, watch } from 'vue'
import { useConfirmStore } from '../../stores/confirmStore'
import { useAppStore } from '../../stores/appStore'
import { onClickOutside, useWindowSize } from '@vueuse/core'
import { Info, CircleAlert, CircleX, CircleCheckBig } from 'lucide-vue-next'

// --- SVG 图标 (纯净无依赖) ---
const Icons = {
  info:    Info,
  warning: CircleAlert,
  error:   CircleX,
  success: CircleCheckBig
}

const appStore = useAppStore()
const confirmStore = useConfirmStore()
const { width: winW, height: winH } = useWindowSize()

const modalRef = ref(null)
const inputRef = ref(null)
const shake = ref(false)

// --- 计算属性 ---

const isMini = computed(() => !!confirmStore.state.targetRect)

// 主题映射：将 type 映射到 Tailwind 类
const theme = computed(() => {
  const t = confirmStore.state.type || 'info'
  // btnBg: 按钮背景，需要高亮色
  // text: 文字和图标颜色
  // bg: 环境光晕颜色
  const maps = {
    info:    { text: 'text-accent-primary',   bg: 'bg-accent-primary',   btnBg: 'bg-accent-primary shadow-accent-primary/20 hover:bg-accent-primary/90', icon: Icons.info },
    warning: { text: 'text-accent-warn',      bg: 'bg-accent-warn',      btnBg: 'bg-accent-warn shadow-accent-warn/20 hover:bg-accent-warn/90',       icon: Icons.warning },
    error:   { text: 'text-accent-danger',    bg: 'bg-accent-danger',    btnBg: 'bg-accent-danger shadow-accent-danger/20 hover:bg-accent-danger/90',   icon: Icons.error },
    success: { text: 'text-accent-success',   bg: 'bg-accent-success',   btnBg: 'bg-accent-success shadow-accent-success/20 hover:bg-accent-success/90', icon: Icons.success }
  }
  return maps[t] || maps.info
})

// 位置计算 (仅用于 Mini 模式)
const containerStyle = computed(() => {
  if (!isMini.value) return {}

  const rect = confirmStore.state.targetRect
  const GAP = appStore.scalePx(12)
  const X_MARGEN = appStore.scalePx(50)
  const MODAL_WIDTH = appStore.scalePx(300)
  // 预估高度，如果内容多可能要调整，或者用 nextTick 动态获取
  const ESTIMATED_HEIGHT = appStore.scalePx(180)

  // 1. 垂直定位逻辑：优先下方，溢出则翻转到上方
  let top = rect.bottom + GAP
  let transformOriginY = 'top' // 动画锚点

  if (top + ESTIMATED_HEIGHT > winH.value) {
    // 空间不足，放上面
    // 注意：这里需要配合 CSS translateY(-100%) 或者直接计算 bottom 坐标
    // 为了简单，计算 top 坐标为：目标顶部 - 弹窗高度 - 间隙
    // 但因为高度不确定，更好的方式是用 bottom 定位
    // 这里简单处理：假设高度固定，实际项目中可用 Floating UI
    top = rect.top - GAP - ESTIMATED_HEIGHT
    transformOriginY = 'bottom'
  }

  // 2. 水平定位逻辑：居中对齐，边缘修正
  let left = rect.left + (rect.width / 2) - (MODAL_WIDTH / 2)
  let transformOriginX = 'center'

  if (left < X_MARGEN) {
    left = X_MARGEN
    transformOriginX = 'left'
  } else if (left + MODAL_WIDTH > winW.value - X_MARGEN) {
    left = winW.value - MODAL_WIDTH - X_MARGEN
    transformOriginX = 'right'
  }

  return {
    position: 'absolute',
    top: `${top}px`,
    left: `${left}px`,
    transformOrigin: `${transformOriginX} ${transformOriginY}`
  }
})

// --- 交互处理 ---

const handleConfirm = () => confirmStore.confirm()
const handleCancel = () => confirmStore.cancel()

// 只有在非 IME 输入状态下，回车才提交
const handleEnterKey = (e) => {
  if (e.isComposing) return
  confirmStore.confirm()
}

// 遮罩层点击反馈
const handleBackdropClick = () => {
  if (isMini.value) {
    confirmStore.cancel()
  } else {
    // 全屏模式下，如果强制要求操作，则拒绝并抖动
    shake.value = true
    setTimeout(() => shake.value = false, 400)
  }
}

// 自动聚焦
watch(() => confirmStore.isVisible, async (val) => {
  if (val && confirmStore.state.mode === 'prompt') {
    await nextTick()
    inputRef.value?.focus()
  }
})

// Mini 模式下点击外部关闭
onClickOutside(modalRef, () => {
  if (isMini.value && confirmStore.isVisible) {
    confirmStore.cancel()
  }
})

</script>

<style scoped>
/* 1. 全屏 Modal 动画：舒展的缩放与淡入 */
.modal-fade-enter-active {
  transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
}
.modal-fade-leave-active {
  transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
}
.modal-fade-enter-from {
  opacity: 0;
  transform: scale(0.92) translateY(15px);
  filter: blur(4px);
}
.modal-fade-leave-to {
  opacity: 0;
  transform: scale(0.96);
  filter: blur(2px);
}

/* 2. Mini Popover 动画：快速弹出 */
.mini-zoom-enter-active {
  transition: all 0.25s cubic-bezier(0.34, 1.56, 0.64, 1);
}
.mini-zoom-leave-active {
  transition: all 0.15s ease-in;
}
.mini-zoom-enter-from {
  opacity: 0;
  transform: scale(0.8) translateY(-5px);
}
.mini-zoom-leave-to {
  opacity: 0;
  transform: scale(0.9);
}

/* 3. 拒绝抖动动画 (物理阻尼感) */
@keyframes shake-physics {
  0% { transform: translateX(0); }
  15% { transform: translateX(-5px) rotate(-1deg); }
  30% { transform: translateX(4px) rotate(1deg); }
  45% { transform: translateX(-3px) rotate(0); }
  60% { transform: translateX(2px); }
  100% { transform: translateX(0); }
}
.animate-shake {
  animation: shake-physics 0.4s ease-in-out;
}

/* 4. 缓慢呼吸灯 */
@keyframes pulse-slow {
  0%, 100% { opacity: 0.15; transform: scale(1); }
  50% { opacity: 0.05; transform: scale(0.85); }
}
.animate-pulse-slow {
  animation: pulse-slow 3s infinite ease-in-out;
}
</style>
