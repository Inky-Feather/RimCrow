<template>
  <Teleport to="body">
    <div v-if="isOpen" ref="pickerRef" class="fixed z-9000 max-h-[calc(100vh-1.5rem)] w-[min(17.5rem,calc(100vw-1.5rem))] overflow-x-auto overflow-y-auto overscroll-contain custom-scrollbar" :style="pickerStyle" @click.stop>
      <ColorPicker :key="pickerKey" :pureColor="modelValue" is-widget :format="format" picker-type="fk"
        :disable-alpha="disableAlpha" @update:pureColor="emit('update:modelValue', $event)"
      />
    </div>
  </Teleport>
</template>

<script setup>
import { computed, defineAsyncComponent, onBeforeUnmount, ref, watch } from 'vue'
import { onClickOutside } from '@vueuse/core'

const ColorPicker = defineAsyncComponent(async () => {
  await import('vue3-colorpicker/style.css')
  const module = await import('vue3-colorpicker')
  return module.ColorPicker
})

const props = defineProps({
  modelValue: { type: String, default: '' },
  isOpen: { type: Boolean, default: false },
  anchorRect: { type: Object, default: null },
  format: { type: String, default: 'hex' },
  disableAlpha: { type: Boolean, default: true },
})

const emit = defineEmits(['update:modelValue', 'close'])

const pickerRef = ref(null)
const pickerPosition = ref({ left: 12, top: 12 })
const pickerKey = computed(() => `${props.format}-${props.disableAlpha ? 'solid' : 'alpha'}`)
const pickerStyle = computed(() => ({
  left: `${pickerPosition.value.left}px`,
  top: `${pickerPosition.value.top}px`,
}))

const getRootFontSize = () => {
  if (typeof window === 'undefined') return 16
  return Number.parseFloat(getComputedStyle(document.documentElement).fontSize) || 16
}

const updatePosition = () => {
  if (!props.anchorRect || typeof window === 'undefined') return

  const rootFontSize = getRootFontSize()
  const margin = rootFontSize * 0.75
  const gap = rootFontSize * 0.625
  const panelWidth = Math.min(rootFontSize * 17.5, Math.max(rootFontSize * 12, window.innerWidth - margin * 2))
  const panelHeight = Math.min(rootFontSize * 22.5, Math.max(rootFontSize * 12, window.innerHeight - margin * 2))
  const preferredRight = props.anchorRect.right + gap
  const preferredLeft = props.anchorRect.left - panelWidth - gap
  const left = preferredRight + panelWidth <= window.innerWidth - margin
    ? preferredRight
    : Math.max(margin, preferredLeft)
  const top = Math.min(Math.max(props.anchorRect.top - 12, margin), Math.max(margin, window.innerHeight - panelHeight - margin))
  pickerPosition.value = { left, top }
}

const stopListeners = () => {
  window.removeEventListener('resize', updatePosition)
}

watch(() => props.isOpen, (isOpen) => {
  if (!isOpen) {
    stopListeners()
    return
  }
  updatePosition()
  window.addEventListener('resize', updatePosition)
})

watch(() => props.anchorRect, () => {
  if (props.isOpen) updatePosition()
})

onClickOutside(pickerRef, () => {
  if (props.isOpen) emit('close')
})

onBeforeUnmount(stopListeners)
</script>
