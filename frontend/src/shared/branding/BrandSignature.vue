<template>
  <LuxBreatheIcon v-if="decorated && logoUrl">
    <span v-if="renderMode === 'mask'" :class="maskClass" :style="logoMaskStyle" role="img" :aria-label="logoAlt"></span>
    <img v-else :src="logoUrl" :alt="logoAlt" :class="imageClass" />
  </LuxBreatheIcon>
  <span v-else-if="logoUrl && renderMode === 'mask'" :class="maskClass" :style="logoMaskStyle" role="img" :aria-label="logoAlt"></span>
  <img v-else-if="logoUrl" :src="logoUrl" :alt="logoAlt" :class="imageClass" />
  <LuxBreatheIcon v-else-if="decorated" />
</template>

<script setup>
import { computed } from 'vue'
import LuxBreatheIcon from '../decorations/LuxBreatheIcon.vue'
import brandProfile from './brandProfile'

const props = defineProps({
  logoClass: { type: String, default: 'size-60' },
  toneClass: { type: String, default: 'text-text-main' },
  decorated: { type: Boolean, default: false },
})

const logoUrl = computed(() => String(brandProfile.branding?.logoUrl || '').trim())
const logoAlt = computed(() => String(brandProfile.branding?.logoAlt || brandProfile.project?.name || '项目标识'))
const renderMode = computed(() => String(brandProfile.branding?.renderMode || 'image').trim() || 'image')
const maskClass = computed(() => [props.logoClass, props.toneClass, 'brand-signature-mask'])
const imageClass = computed(() => [props.logoClass, 'block object-contain'])
const logoMaskStyle = computed(() => {
  if (!logoUrl.value) return {}
  const logo = `url("${logoUrl.value}")`
  return {
    WebkitMaskImage: logo,
    maskImage: logo,
  }
})
</script>

<style scoped>
.brand-signature-mask {
  display: block;
  flex-shrink: 0;
  background-color: currentColor;
  -webkit-mask-position: center;
  mask-position: center;
  -webkit-mask-repeat: no-repeat;
  mask-repeat: no-repeat;
  -webkit-mask-size: contain;
  mask-size: contain;
}
</style>
