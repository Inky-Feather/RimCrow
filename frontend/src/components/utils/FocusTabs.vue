<template>
  <div ref="containerRef" class="relative flex p-0.5 rounded-lg backdrop-blur-[5px]"
    :class="{'bg-text-main/5 border border-text-main/10 ': showBorder}"
    >
    <button
      v-for="(tab, index) in tabs"
      :key="tab"
      :ref="(el) => (itemRefs[index] = el as HTMLButtonElement)"
      @click="emit('update:modelValue', tab)"
      class="relative z-10 px-2 py-0 transition-all duration-500 cursor-pointer"
      :style="{
        filter: modelValue === tab ? 'blur(0px)' : `blur(${blurAmount}px)`,
        opacity: modelValue === tab ? 1 : 0.4
      }"
      :class="modelValue === tab ? ' text-accent-highlight' : 'text-text-main'"
    >
      {{ tab }}
    </button>

    <div
      class="absolute pointer-events-none transition-all duration-500 cubic-bezier(0.16, 1, 0.3, 1)"
      :style="{
        left: `${focusRect.x}px`,
        top: `${focusRect.y}px`,
        width: `${focusRect.width}px`,
        height: `${focusRect.height}px`,
        opacity: focusRect.width > 0 ? 1 : 0,
        '--border-color': borderColor
      }"
    >
      <span class="corner top-left" />
      <span class="corner top-right" />
      <span class="corner bottom-left" />
      <span class="corner bottom-right" />
    </div>
  </div>
</template>

<script lang="ts" setup>
import { ref, watch, nextTick, onMounted, onBeforeUnmount } from 'vue';

const props = withDefaults(defineProps<{
  tabs: string[];
  modelValue: string;
  borderColor?: string;
  blurAmount?: number; // 允许调节模糊程度
  showBorder?: boolean;
}>(), {
  borderColor: '#00ffcc',
  blurAmount: 2 // 默认模糊 2px，不要太大否则看不清字
});

const emit = defineEmits(['update:modelValue']);

const containerRef = ref<HTMLElement | null>(null);
const itemRefs = ref<HTMLElement[]>([]);
const focusRect = ref({ x: 0, y: 0, width: 0, height: 0 });

const updateFocus = async () => {
  await nextTick();
  const activeIndex = props.tabs.indexOf(props.modelValue);
  const activeEl = itemRefs.value[activeIndex];
  const containerEl = containerRef.value;

  if (activeEl && containerEl) {
    const parentRect = containerEl.getBoundingClientRect();
    const targetRect = activeEl.getBoundingClientRect();

    focusRect.value = {
      x: targetRect.left - parentRect.left,
      y: targetRect.top - parentRect.top,
      width: targetRect.width,
      height: targetRect.height,
    };
  }
};

watch(() => props.modelValue, updateFocus);

onMounted(() => {
  updateFocus();
  window.addEventListener('resize', updateFocus);
});

onBeforeUnmount(() => {
  window.removeEventListener('resize', updateFocus);
});
</script>

<style scoped>
.corner {
  position: absolute;
  width: 6px;
  height: 6px;
  border: 1.5px solid var(--border-color);
  filter: drop-shadow(0px 0px 4px var(--border-color));
  transition: border-color 0.3s ease;
}

.top-left { top: -2px; left: -2px; border-right: none; border-bottom: none; border-top-left-radius: 4px; }
.top-right { top: -2px; right: -2px; border-left: none; border-bottom: none; border-top-right-radius: 4px; }
.bottom-left { bottom: -2px; left: -2px; border-right: none; border-top: none; border-bottom-left-radius: 4px; }
.bottom-right { bottom: -2px; right: -2px; border-left: none; border-top: none; border-bottom-right-radius: 4px; }

/* 贝塞尔曲线让移动更具有“高级感” */
.cubic-bezier {
  transition-timing-function: cubic-bezier(0.16, 1, 0.3, 1);
}
</style>