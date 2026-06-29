<template>
  <div v-tooltip="item.tooltip || '自定义颜色'"
    class="context-color-picker relative flex items-center justify-center aspect-square w-[33px] rounded-md border border-border-base/10 bg-bg-overlay/5 hover:border-border-base/18 hover:bg-bg-overlay/10 transition-all duration-200"
    @click.stop @mousedown.stop>
    <!-- 把弹层挂回当前菜单节点内，避免 Teleport 到 body 后触发父级菜单的 mouseleave 关闭链路。 -->
    <ColorPicker v-model:pureColor="item.color" @pureColorChange="handleColorChange"
      :picker-container="pickerContainer || 'body'" format="hex" picker-type="fk" disable-alpha round-history />
  </div>
</template>

<script setup>
import { defineAsyncComponent } from 'vue'

const ColorPicker = defineAsyncComponent(async () => {
  await import('vue3-colorpicker/style.css')
  const module = await import('vue3-colorpicker')
  return module.ColorPicker
})

const props = defineProps({
  item: { type: Object, required: true },
  pickerContainer: { type: [Object, String], default: 'body' }
})

const handleColorChange = (color) => {
  if (props.item.disabled || !props.item.action) return
  props.item.action(color)
}
</script>

<style scoped>
/* 菜单里的取色器只保留“方块触发器”外观，完整面板仍然使用库默认样式。 */
.context-color-picker :deep(.vc-color-wrap) {
  width: 100%;
  height: 100%;
  margin-right: 0;
  border-radius: 0.375rem;
  box-shadow: none;
  display: block;
}

/* 库默认触发器是 50x24 的长条，这里强制铺满菜单色块尺寸。 */
.context-color-picker :deep(.vc-color-wrap .current-color) {
  width: 100%;
  height: 100%;
  border-radius: inherit;
}

.context-color-picker :deep(.vc-color-wrap.transparent) {
  background-image: none;
}
</style>
