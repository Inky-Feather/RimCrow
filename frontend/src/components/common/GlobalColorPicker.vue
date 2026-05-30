<template>
  <Teleport to="body">
    <div v-if="isOpen" ref="pickerRef" class="fixed z-9000" :style="pickerStyle" @click.stop>
      <ColorPicker :key="pickerKey" :pureColor="modelValue" is-widget :format="format" picker-type="fk"
        :disable-alpha="disableAlpha" @update:pureColor="emit('update:modelValue', $event)"
      />
    </div>
  </Teleport>
</template>

<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { onClickOutside } from '@vueuse/core'
import { ColorPicker } from 'vue3-colorpicker'

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
  width: '280px',
}))

const updatePosition = () => {
  if (!props.anchorRect || typeof window === 'undefined') return

  const panelWidth = 280
  const panelHeight = 360
  const gap = 10
  const margin = 12
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
