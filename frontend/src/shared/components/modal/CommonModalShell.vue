<template>
  <Teleport to="body" :disabled="!teleport">
    <Transition name="common-modal-fade">
      <div v-if="shouldRender" v-show="isOpen" class="fixed inset-0 flex items-center justify-center px-3 py-4 text-text-main selection:bg-bg-overlay/10" :style="{ zIndex }" >
        <div class="absolute inset-0 bg-overlay-scrim backdrop-blur-md" @mousedown="handleBackdropClick" ></div>
        <div class="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top_right,rgba(var(--rgb-accent-primary),0.10),transparent_32%),radial-gradient(circle_at_bottom_left,rgba(var(--rgb-accent-special),0.08),transparent_34%)]"></div>

        <section :class="[surfaceClass, sizeClass, panelClass]" role="dialog" aria-modal="true"  :aria-label="title || undefined" >
          <div v-if="!frameless" class="pointer-events-none absolute inset-x-0 top-0 h-px bg-linear-to-r from-transparent via-border-base/18 to-transparent"></div>
          <div v-if="!frameless && accentGlow" class="pointer-events-none absolute -right-20 -top-24 h-64 w-64 rounded-full blur-3xl" :class="accentGlow"></div>

          <header v-if="showHeader" class="modal-header relative z-10 flex shrink-0 items-start justify-between gap-4 px-5 py-4" :class="headerClass">
            <div class="flex min-w-0 items-start gap-3">
              <div v-if="$slots.icon" class="shrink-0 rounded-xl bg-bg-overlay/5 p-2 text-accent-primary">
                <slot name="icon"></slot>
              </div>
              <div class="min-w-0">
                <div class="flex min-w-0 flex-wrap items-center gap-2">
                  <h2 class="truncate text-lg font-black tracking-wide text-text-main">{{ title }}</h2>
                  <slot name="title-extra"></slot>
                </div>
                <p v-if="description" class="mt-1 text-xs leading-relaxed text-text-dim">{{ description }}</p>
              </div>
            </div>

            <div class="flex shrink-0 items-center gap-2">
              <slot name="header-actions"></slot>
              <button v-if="showClose" class="modal-close-button" type="button" aria-label="关闭"  @click="requestClose('button')" >
                <X class="size-4" />
              </button>
            </div>
          </header>

          <div class="relative z-10 min-h-0 flex-1 overflow-hidden" :class="contentClass">
            <slot></slot>
          </div>

          <footer v-if="$slots.footer" class="modal-footer relative z-10 shrink-0 px-5 py-4" :class="footerClass">
            <slot name="footer"></slot>
          </footer>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
import { computed, onBeforeUnmount, watch } from 'vue'
import { X } from 'lucide-vue-next'
import { useConfirmStore } from './confirmStore'

const props = defineProps({
  show: { type: Boolean, default: false },
  persistent: { type: Boolean, default: false },
  title: { type: String, default: '' },
  description: { type: String, default: '' },
  size: { type: String, default: 'page' },
  zIndex: { type: [Number, String], default: 120 },
  teleport: { type: Boolean, default: true },
  showHeader: { type: Boolean, default: true },
  showClose: { type: Boolean, default: true },
  frameless: { type: Boolean, default: false },
  closeOnBackdrop: { type: Boolean, default: true },
  closeOnEsc: { type: Boolean, default: true },
  panelClass: { type: [String, Array, Object], default: '' },
  headerClass: { type: [String, Array, Object], default: '' },
  contentClass: { type: [String, Array, Object], default: '' },
  footerClass: { type: [String, Array, Object], default: '' },
  accent: { type: String, default: 'primary' },
})

const emit = defineEmits(['close', 'backdrop'])
const confirmStore = useConfirmStore()
const modalId = Symbol('common-modal')
const modalStack = window.__commonModalStack || (window.__commonModalStack = [])

const isOpen = computed(() => props.show)
const shouldRender = computed(() => props.persistent || isOpen.value)
const surfaceClass = computed(() => (
  props.frameless
    ? 'relative z-10 flex max-h-[calc(100vh-2rem)] flex-col overflow-visible'
    : 'modal-surface relative z-10 flex max-h-[calc(100vh-2rem)] flex-col overflow-hidden rounded-2xl'
))
const sizeClass = computed(() => {
  const map = {
    compact: 'w-[min(760px,94vw)]',
    default: 'w-[75vw] h-[80vh]',
    page: 'h-[90vh] w-[92vw] -top-[1vh] max-w-screen-2xl',
    wide: 'h-[88vh] w-[92vw] max-w-screen-2xl',
    full: 'h-[calc(100vh-2.5rem)] w-[calc(100vw-2.5rem)]',
    custom: '',
    // 兼容旧写法，新的页面级弹窗统一走 page。
    md: 'w-[min(760px,94vw)]',
    lg: 'w-[75vw] h-[80vh]',
    xl: 'w-[75vw] h-[80vh]',
  }
  return map[props.size] || map.page
})
const accentGlow = computed(() => {
  const map = {
    primary: 'bg-accent-primary/10',
    special: 'bg-accent-special/10',
    highlight: 'bg-accent-highlight/10',
    cool: 'bg-accent-cool/10',
    tip: 'bg-accent-tip/10',
    warn: 'bg-accent-warn/10',
    danger: 'bg-accent-danger/10',
    warning: 'bg-accent-warning/10',
    success: 'bg-accent-success/10',
  }
  return map[props.accent] || map.primary
})

const removeFromStack = () => {
  const index = modalStack.indexOf(modalId)
  if (index !== -1) modalStack.splice(index, 1)
}

const requestClose = (reason) => {
  emit('close', reason)
}

const handleBackdropClick = () => {
  emit('backdrop')
  if (props.closeOnBackdrop) requestClose('backdrop')
}

const handleKeydown = (event) => {
  if (!props.closeOnEsc || event.key !== 'Escape') return
  // 确认弹窗层级最高，打开时不让底层普通弹窗误响应 Esc。
  if (confirmStore.isVisible) return
  if (modalStack[modalStack.length - 1] !== modalId) return
  event.preventDefault()
  requestClose('esc')
}

watch(isOpen, (visible) => {
  if (visible) {
    removeFromStack()
    modalStack.push(modalId)
    window.addEventListener('keydown', handleKeydown)
    return
  }
  removeFromStack()
  window.removeEventListener('keydown', handleKeydown)
}, { immediate: true })

onBeforeUnmount(() => {
  removeFromStack()
  window.removeEventListener('keydown', handleKeydown)
})
</script>

<style scoped>
.common-modal-fade-enter-active,
.common-modal-fade-leave-active {
  transition: opacity 0.22s ease;
}

.common-modal-fade-enter-from,
.common-modal-fade-leave-to {
  opacity: 0;
}

.common-modal-fade-enter-active section,
.common-modal-fade-leave-active section {
  transition: transform 0.22s cubic-bezier(0.16, 1, 0.3, 1), opacity 0.22s ease;
}

.common-modal-fade-enter-from section,
.common-modal-fade-leave-to section {
  opacity: 0;
  transform: translateY(10px) scale(0.985);
}
</style>
